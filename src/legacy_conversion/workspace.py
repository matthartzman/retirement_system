"""``convert_workspace``: the one entry point of the conversion (WP10.2; WP10.4 wires it into
first launch after the owner checkpoint, nothing calls it at startup yet).

It decides whether a workspace needs converting and from which source, then runs
``runner.CONVERSION_STEPS`` into ``<workspace>/plan.rpx``:

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
the demo is recreated from the bundled seed as ``demo.rpx``. No original is modified, moved or
deleted (the runner's guard checks every one byte for byte), except ``secrets.local.json`` when
``extra["delete_legacy_secrets"]`` is true and every key verified.

``extra`` keys: ``delete_legacy_secrets`` (bool), ``legacy_db`` (an old-format ``.rpx`` / ``.db``
to read ``client_files`` / snapshots from instead of ``local_state/retirement_system_v10.db``),
``plan_file`` (target, default ``<workspace>/plan.rpx``), ``app_db`` (default
``app_state.app_store_path_for(workspace)``).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..stores import PlanStore
from . import runner, sources
from .steps import c6a_settings, c6b_secrets

APP_DONE_KEY = "legacy_conversion.done"


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
                      extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Convert ``workspace`` when needed (see the module docstring). Returns a privacy-safe
    report: ``{needed, reason, mode, dry_run, report}`` (``report`` = ``ConversionReport.as_dict``,
    or None when nothing ran). Raises ``runner.SourceModifiedError`` if an original changed."""
    from ..app_state import app_store_path_for, open_app_store  # noqa: PLC0415

    ws = Path(workspace)
    extra = dict(extra or {})
    d = decide(ws, extra)
    result: dict[str, Any] = {"needed": d["needed"], "reason": d["reason"], "mode": d["mode"],
                              "dry_run": dry_run, "report": None}
    if not d["needed"]:
        return result
    plan: sources.SourcePlan = d["sources"]
    mid_demo = plan.mode == "mid_demo"
    run_extra = {**extra, "_sources": plan, "_mid_demo": mid_demo,
                 "_replace_plan_rows": mid_demo and plan.plan_seed is None}
    rep = runner.run_conversion(ws, d["plan_file"], runner.CONVERSION_STEPS, dry_run=dry_run,
                                source_paths=sources.source_paths(ws, extra), extra=run_extra,
                                seed_plan=plan.plan_seed)
    result["report"] = rep.as_dict()
    if rep.ok and not dry_run:
        if d["plan_file"].is_file():  # also when every step was already done (nothing "converted")
            with PlanStore.open(d["plan_file"], create=False) as store:
                if store.get_meta(runner.DONE_MARKER) is None:
                    store.set_meta(runner.DONE_MARKER, time.strftime("%Y-%m-%dT%H:%M:%S"))
        app_db = Path(extra.get("app_db") or app_store_path_for(ws))
        with open_app_store(app_db) as app:
            app.set_setting(APP_DONE_KEY, f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {d['plan_file'].name}")
    return result
