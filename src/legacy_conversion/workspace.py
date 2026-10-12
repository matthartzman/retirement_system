"""``convert_workspace``: the one entry point of the conversion (WP10.2, WP10.3; WP10.4 wires it
into first launch after the owner checkpoint, nothing calls it at startup yet).

It decides whether a workspace needs converting and from which source:

* **not needed** when the plan file carries the done marker (and no secrets are pending), or
  when no legacy source exists (a fresh install: nothing to convert, whatever the plan holds);
* **needed** when the done marker is absent and a legacy source exists: plan CSV set or flat
  dataset files in ``input/``, the legacy database (``client_files`` / ``plan_snapshots``), an
  old demo's ``*.before_demo`` backups, ``system_config.csv`` or ``secrets.local.json``; or when
  the plan was converted but the legacy secrets file is still waiting for a credential store
  (C6b had no store; every other step is then a no-op through its marker).

Source and mode come from ``sources.discover``: a **mid-demo** install (old demo open) starts
the target from a copy of ``plan.rpx.before_demo`` (the real plan; the current ``plan.rpx`` is
the demo copy, kept as ``plan.rpx.pre_conversion_<ts>``), or, before WP4.5 (no plan backup),
replaces the demo rows in ``plan.rpx`` with the real CSV set from the text / database backups;
the demo is recreated from the bundled seed as ``demo.rpx``.

A real run (WP10.3); nothing live changes before step 5:

1. **originals guard**: size + SHA-256 of every original (``sources.source_paths``);
2. **backup**: a verified copy of every original the conversion reads into
   ``<workspace>/backups/pre_conversion_<ts>/`` (``backup.ensure_backup``); a failure stops here;
3. **staging**: the plan is converted in a private copy under
   ``<workspace>/local_state/conversion_staging/`` (a copy of the live plan, or of
   ``plan.rpx.before_demo``), ``runner.PLAN_STEPS`` only;
4. **verification** (``verify.verify_conversion``): a blocking difference stops here (status
   ``blocked``, the user is asked) unless ``extra["accept_differences"]``; the originals guard is
   checked again (a change stops here);
5. **swap**: the verified copy replaces the live plan through ``plan_db_replace.replace_active_db``
   (validated copy, the live plan kept as ``plan.rpx.pre_conversion_<ts>``, atomic replace);
   skipped when nothing was converted;
6. **install**: ``runner.INSTALL_STEPS`` on the live plan (app.db flags, secrets, registration and
   activation);
7. done marker in the plan, ``APP_DONE_KEY`` in app.db; the result summary in app.db
   (``result.LAST_RESULT_KEY``) after every real run, blocked ones included.

A process killed at any point leaves the originals as they were and the live plan either as it
was (before 5) or replaced as a whole by the verified copy (after 5, without the done marker:
the next run finishes 6 and 7). A dry run does 3 and 4 in a temporary folder and writes nothing.
The converter deletes no original; ``secrets.local.json`` goes only through C6b with
``extra["delete_legacy_secrets"]`` after every key verified, which runs in 6, after verification.

``extra`` keys: ``delete_legacy_secrets`` (bool), ``backup_legacy_secrets`` (bool: include the
plain secrets file in the backup), ``accept_differences`` (bool: the user saw the differing key
names and converts anyway), ``tier_mapping`` (``"keep"``: the user keeps the plan's feature
switches; no tier mapping), ``legacy_db`` (an old-format ``.rpx`` / ``.db`` to read
``client_files`` / snapshots from instead of ``local_state/retirement_system_v10.db``),
``plan_file`` (target, default ``<workspace>/plan.rpx``), ``app_db`` (default
``app_state.app_store_path_for(workspace)``).

``convert_workspace`` points this process's plan and app.db at private copies while it computes
(``verify.Engine``): run it before the app serves requests.
"""
from __future__ import annotations

import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from ..active_plan import PlanStore  # product code reaches PlanStore through active_plan
from . import backup, runner, sources, verify
from .result import LAST_RESULT_KEY, ConversionResult
from .steps import c6a_settings, c6b_secrets

APP_DONE_KEY = "legacy_conversion.done"
STAGING_DIR = Path("local_state") / "conversion_staging"
_RUN_LOCK = threading.Lock()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _plan_meta(plan_file: Path, key: str) -> str | None:
    if not plan_file.is_file():
        return None
    try:
        with PlanStore.open(plan_file, create=False, readonly=True) as store:
            return store.get_meta(key)
    except Exception:  # noqa: BLE001 - not a plan file yet
        return None


def _app_setting(app_db: Path, key: str) -> Any:
    from ..app_state import open_app_store  # noqa: PLC0415
    if not app_db.is_file():
        return None
    with open_app_store(app_db, readonly=True) as app:
        return app.get_setting(key)


def decide(workspace: str | Path, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """``{needed, reason, mode, plan_file, sources}`` (``sources`` is a ``SourcePlan``)."""
    from ..app_state import app_store_path_for  # noqa: PLC0415

    ws = Path(workspace)
    extra = dict(extra or {})
    plan_file = Path(extra.get("plan_file") or ws / sources.PLAN_FILE_NAME)
    app_db = Path(extra.get("app_db") or app_store_path_for(ws))
    secrets_file = ws / c6b_secrets.LEGACY_FILE
    secrets_pending = secrets_file.is_file() and _app_setting(app_db, c6b_secrets.MARKER_KEY) is None
    done = _plan_meta(plan_file, runner.DONE_MARKER) is not None
    out: dict[str, Any] = {"needed": False, "reason": "", "mode": "normal", "plan_file": plan_file, "sources": None}
    if done and not secrets_pending:
        out["reason"] = "already converted"
        return out
    plan = sources.discover(ws, extra)
    out["sources"], out["mode"] = plan, plan.mode
    if done:
        out.update(needed=True, reason="legacy secrets pending")
        return out
    legacy = plan.has_any or (ws / c6a_settings.LEGACY_FILE).is_file() or secrets_file.is_file()
    if not legacy:
        out["reason"] = "no legacy sources"
        return out
    out.update(needed=True, reason="mid-demo install" if plan.mode == "mid_demo" else "legacy sources found")
    return out


def convert_workspace(workspace: str | Path, *, dry_run: bool = False,
                      extra: dict[str, Any] | None = None) -> ConversionResult:
    """Convert ``workspace`` when needed (see the module docstring); returns the privacy-safe
    :class:`~.result.ConversionResult`. Never raises for a conversion problem: a blocked or
    failed run is a result. One conversion at a time per process (``busy`` otherwise)."""
    if not _RUN_LOCK.acquire(blocking=False):
        return ConversionResult(needed=True, reason="a conversion is already running", dry_run=dry_run,
                                status="blocked", blocked_reason="busy", started_at=_now(), finished_at=_now())
    try:
        return _convert(Path(workspace), dry_run, dict(extra or {}))
    finally:
        _RUN_LOCK.release()


def _block(res: ConversionResult, reason: str) -> ConversionResult:
    res.blocked_reason = reason
    res.status = "dry_run" if res.dry_run else "blocked"
    return res


def _fresh_dir(path: Path) -> Path:
    """Our own scratch folder, emptied first (a killed run may have left one)."""
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _live_state(plan_file: Path) -> str | None:
    """Content fingerprint of the live plan (rows and datasets), or None when it is missing."""
    from ..active_plan import plan_state  # noqa: PLC0415

    if not plan_file.is_file():
        return None
    try:
        return plan_state(plan_file)
    except Exception as exc:  # noqa: BLE001 - not a readable plan: compared by that fact
        return f"unreadable:{type(exc).__name__}"


def _unique(path: Path) -> Path:
    out, n = path, 1
    while out.exists():
        out = path.with_name(f"{path.name}_{n}")
        n += 1
    return out


def _keep_staging(dest: Any, staging: Path, res: ConversionResult) -> None:
    """The rehearsal's ``--out``: keep the converted (staging) plan, also when blocked."""
    from ..plan_db_replace import copy_sqlite_file  # noqa: PLC0415
    if not dest or not staging.is_file():
        return
    try:
        copy_sqlite_file(staging, Path(dest))
    except Exception:  # noqa: BLE001 - a rehearsal convenience; never masks the result
        res.warnings.append("staging_copy_failed")


def _persist(app_db: Path, res: ConversionResult) -> None:
    from ..app_state import open_app_store  # noqa: PLC0415
    try:
        with open_app_store(app_db) as app:
            app.set_setting(LAST_RESULT_KEY, res.summary())
    except Exception:  # noqa: BLE001 - the result is still returned; never fail a conversion over it
        res.warnings.append("last_result_not_saved")


def _convert(ws: Path, dry_run: bool, extra: dict[str, Any]) -> ConversionResult:
    from ..app_state import app_store_path_for  # noqa: PLC0415

    res = ConversionResult(needed=False, dry_run=dry_run, started_at=_now())
    try:
        d = decide(ws, extra)
        res.needed, res.reason, res.mode = d["needed"], d["reason"], d["mode"]
        if not d["needed"]:
            res.status, res.verified, res.finished_at = "not_needed", True, _now()
            return res
        app_db = Path(extra.get("app_db") or app_store_path_for(ws))
        guard = sources.source_paths(ws, extra)
        before = runner.snapshot_sources(guard)
    except Exception as exc:  # noqa: BLE001 - e.g. an original that cannot be read: nothing was written
        res.needed, res.error_type, res.finished_at = True, type(exc).__name__, _now()
        return _block(res, "sources_unreadable")
    workdir = Path(tempfile.mkdtemp(prefix="conversion_dry_")) if dry_run else _fresh_dir(ws / STAGING_DIR)
    try:
        _run(res, ws, d, extra, app_db, guard, before, workdir)
    except Exception as exc:  # noqa: BLE001 - a result, never a half state left unreported
        res.error_type = type(exc).__name__
        if res.status not in ("done", "failed"):
            _block(res, "internal_error")
    finally:
        _keep_staging(extra.get("_keep_staging"), workdir / Path(d["plan_file"]).name, res)
        shutil.rmtree(workdir, ignore_errors=True)
        try:
            unchanged = runner.snapshot_sources(guard) == before
        except OSError:
            unchanged = False
        if not unchanged:
            res.sources_unchanged = False
            if "sources_modified" not in res.warnings:
                res.warnings.append("sources_modified")
        res.finished_at = _now()
        if not dry_run:
            _persist(app_db, res)
    return res


def _run(res: ConversionResult, ws: Path, d: dict[str, Any], extra: dict[str, Any], app_db: Path,
         guard: list[Path], before: dict[str, tuple[int, str]], workdir: Path) -> None:
    from ..app_state import open_app_store  # noqa: PLC0415
    from ..plan_db_replace import PLAN_FILE_TABLES, copy_sqlite_file, replace_active_db, validate_plan_file  # noqa: PLC0415

    plan_file: Path = d["plan_file"]
    plan: sources.SourcePlan = d["sources"]
    mid_demo = plan.mode == "mid_demo"
    run_extra = {**extra, "_sources": plan, "_mid_demo": mid_demo,
                 "_replace_plan_rows": mid_demo and plan.plan_seed is None}
    stamp = time.strftime("%Y%m%d_%H%M%S")
    already_done = _plan_meta(plan_file, runner.DONE_MARKER) is not None

    # 2. backup of the originals (a plan already converted, secrets pending: nothing to protect)
    backup_name = ""
    if res.dry_run:
        res.backup = {"planned": True, **backup.plan_backup(ws, extra)}
    elif not already_done:
        b = backup.ensure_backup(ws, before, extra=extra, stamp=stamp)
        res.backup = b.as_dict(ws)
        if not b.verified:
            _block(res, "backup_failed")
            return
        backup_name = b.path.name if b.path else ""

    # 3. convert into a staging copy
    staging = workdir / plan_file.name
    live_before = _live_state(plan_file)
    origin = runner.prepare_staging(plan_file, staging, plan.plan_seed)
    ctx, report = runner.run_plan_phase(ws, staging, runner.PLAN_STEPS, extra=run_extra, plan_file=plan_file,
                                        workdir=workdir, dry_run=res.dry_run)
    res.steps = [s.as_dict() for s in report.steps]
    failed = next((s for s in report.steps if s.status == "failed"), None)
    if failed is not None:
        res.failed_step, res.error_type = failed.step, failed.error_type or ""
        _block(res, "step_failed")
        return

    # 4. verify
    res.checks = verify.verify_conversion(verify.VerifyInput(
        workspace=ws, staging_file=staging, pre_tier_file=ctx.checkpoints.get("pre_tier_file"),
        staged_dir=ctx.source_dir, initial=ctx.checkpoints["initial"],
        steps={s.step: s.as_dict() for s in report.steps}, workdir=workdir, app_db=app_db, mode=plan.mode,
        legacy_db=Path(extra["legacy_db"]) if extra.get("legacy_db") else None,
        disagreeing_files=plan.disagreeing_files(), skip_engine=bool(extra.get("_skip_engine"))))
    failing = verify.failed(res.checks)
    res.verified = not failing
    res.warnings += [f"{c.name}:{c.status}" for c in res.checks if not c.blocking and c.status in ("diff", "error")]
    c3, c6a = report.step("C3"), report.step("C6a")
    if c6a is not None and c6a.detail.get("knobs_written") and not (c3 is not None and c3.status == "converted"):
        # system_config.csv engine settings added to a plan that already lived in a plan file (C6a's
        # rule): its numbers now follow the old file's settings; names are in the C6a step detail.
        res.warnings.append(f"system_config_knobs_added:{len(c6a.detail['knobs_written'])}")
    if failing:
        if any(c.status == "diff" and c.name != "tier_mapping" for c in failing):
            reason = "verification_differences"
        elif any(c.status == "diff" for c in failing):
            reason = "tier_mapping_changes_results"
        else:
            reason = "verification_error"  # the engine raised: the numbers could not be compared
        if not extra.get("accept_differences"):
            _block(res, reason)
            return
        res.accepted_differences = True
        res.warnings.append(f"accepted:{reason}")
    if runner.snapshot_sources(guard) != before:
        res.sources_unchanged = False
        _block(res, "sources_modified")
        return
    if res.dry_run:
        # What the install steps would do (they write nothing in a dry run).
        install = runner.ConversionReport(dry_run=True)
        with PlanStore.open(staging, create=False) as store:
            runner.execute(runner.INSTALL_STEPS, runner.ConversionContext(
                ws, store, True, run_extra, plan_file=plan_file, workdir=workdir), install)
        res.steps += [s.as_dict() for s in install.steps]
        res.status = "dry_run"
        return

    # 5. swap the verified copy in (only when the run changed it)
    if report.converted or origin == "seed" or not plan_file.is_file():
        with PlanStore.open(staging, create=False) as store:
            store.set_meta(runner.VERIFIED_MARKER, f"{_now()} accepted={int(res.accepted_differences)} backup={backup_name}")
        swap_src = workdir / "verified.rpx"
        copy_sqlite_file(staging, swap_src)  # one self-contained file (WAL folded in)
        if _live_state(plan_file) != live_before:
            _block(res, "plan_changed_during_conversion")
            return
        keep = None
        if plan_file.is_file():
            # The live plan's rollback copy, checked before the swap (same rows and datasets).
            keep = _unique(plan_file.with_name(f"{plan_file.name}.pre_conversion_{stamp}"))
            runner.backup_db(plan_file, keep)
            if _live_state(keep) != live_before:
                _block(res, "plan_backup_failed")
                return
            res.plan_backup = keep.name
        out = replace_active_db(swap_src, plan_file, required_tables=PLAN_FILE_TABLES, validate=validate_plan_file)
        if not out.get("success"):
            _block(res, "swap_failed")
            return
        res.plan_replaced = True

    # 6. install steps on the live plan, then 7. the done markers
    install = runner.ConversionReport(dry_run=False)
    with PlanStore.open(plan_file) as store:
        ictx = runner.ConversionContext(ws, store, False, run_extra, plan_file=plan_file, workdir=workdir)
        runner.execute(runner.INSTALL_STEPS, ictx, install)
        res.steps += [s.as_dict() for s in install.steps]
        failed = next((s for s in install.steps if s.status == "failed"), None)
        if failed is not None:
            # The verified plan is live but not registered / activated; a later run finishes it.
            res.failed_step, res.error_type = failed.step, failed.error_type or ""
            res.status, res.blocked_reason = "failed", "step_failed"
            return
        if store.get_meta(runner.DONE_MARKER) is None:
            store.set_meta(runner.DONE_MARKER, _now())
    res.warnings += [f"secrets:{s.detail['warning']}" for s in install.steps
                     if s.step == "C6b" and s.detail.get("warning")]
    with open_app_store(app_db) as app:
        app.set_setting(APP_DONE_KEY, f"{_now()} {plan_file.name}")
    res.status = "done"
    res.removable = backup.removal_candidates(ws, res.plan_backup)
