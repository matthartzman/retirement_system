"""legacy_conversion runner (WP10.1, WP10.3): runs the ordered conversion steps against one plan file.

* ``ConversionContext`` carries the workspace, the folders the old files live in, the open plan
  store, the dry-run flag, the run's private scratch folder (``workdir``) and the
  ``checkpoints`` verification reads (the plan as it was before any step, the plan just before
  the tier mapping).
* Every step is a ``Step(id, run)``; ``run(ctx)`` returns a small privacy-safe dict (counts and
  names only, never plan values). Steps carry their own idempotency markers in ``plan_meta``
  (``legacy_conversion.<step>``), so a re-run converts only what is missing.
* The steps come in two phases (WP10.3). ``PLAN_STEPS`` write only the plan file they are given:
  ``convert_workspace`` runs them into a STAGING copy and verifies the copy before anything
  becomes live. ``INSTALL_STEPS`` write install state (app.db settings, the credential store,
  the plan registry) and run only after the verified copy replaced the live plan.
* ``run_conversion`` (low level: tests and tools) snapshots every source file before and after
  (size + SHA-256) and raises ``SourceModifiedError`` if any original changed: the originals are
  never modified. It never sets the done marker; only ``convert_workspace`` does, after
  verification.
* Dry run converts into a throwaway copy of the target plan and leaves the real one untouched.
* A failing step stops the run (later steps may depend on it); the report says which step and
  the exception type (the message is withheld, it can quote plan values).
"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from ..active_plan import PlanStore  # product code reaches PlanStore through active_plan

DONE_MARKER = "legacy_conversion.done"
VERIFIED_MARKER = "legacy_conversion.verified"
SEEDED_MARKER = "legacy_conversion.seeded_from"
PRE_TIER_FILE = "pre_tier.rpx"  # checkpoint copy of the staging plan just before T8 (in workdir)


class SourceModifiedError(RuntimeError):
    """A legacy source file changed during a conversion run (never expected)."""


@dataclass
class ConversionContext:
    workspace: Path
    store: PlanStore
    dry_run: bool = False
    extra: dict[str, Any] = field(default_factory=dict)
    # The folder the file-reading steps read: ``input/`` unless step SRC staged the sources
    # chosen by precedence (``sources.discover``) into a scratch folder.
    source_dir: Path | None = None
    plan_file: Path | None = None  # the real target (the live plan), never the staging copy
    cleanup: list[Path] = field(default_factory=list)  # scratch folders removed after the run
    workdir: Path | None = None  # this run's private scratch folder (None: system temp)
    checkpoints: dict[str, Any] = field(default_factory=dict)

    @property
    def input_dir(self) -> Path:
        return self.source_dir or self.workspace / "input"


@dataclass(frozen=True)
class Step:
    id: str
    run: Callable[[ConversionContext], dict[str, Any]]
    # applies(ctx) False -> status "not_applicable" (e.g. no legacy files for this dataset)
    applies: Callable[[ConversionContext], bool] = lambda ctx: True


@dataclass
class StepResult:
    step: str
    status: str  # converted | skipped | not_applicable | failed
    detail: dict[str, Any] = field(default_factory=dict)
    seconds: float = 0.0
    error_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out = {"step": self.step, "status": self.status, "detail": self.detail, "seconds": round(self.seconds, 3)}
        if self.error_type:
            out["error_type"] = self.error_type
        return out


@dataclass
class ConversionReport:
    dry_run: bool
    steps: list[StepResult] = field(default_factory=list)
    sources_unchanged: bool = True
    source_files: int = 0

    @property
    def ok(self) -> bool:
        return self.sources_unchanged and all(s.status != "failed" for s in self.steps)

    @property
    def converted(self) -> bool:
        return any(s.status == "converted" for s in self.steps)

    def step(self, step_id: str) -> StepResult | None:
        return next((s for s in self.steps if s.step == step_id), None)

    def as_dict(self) -> dict[str, Any]:
        return {"dry_run": self.dry_run, "ok": self.ok, "sources_unchanged": self.sources_unchanged,
                "source_files": self.source_files, "steps": [s.as_dict() for s in self.steps]}


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_sources(paths: Iterable[str | Path]) -> dict[str, tuple[int, str]]:
    """``{path: (size, sha256)}`` of every file under the given files/folders (folders walked)."""
    out: dict[str, tuple[int, str]] = {}
    for root in paths:
        root = Path(root)
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file()) if root.is_dir() else []
        for f in files:
            out[str(f)] = (f.stat().st_size, file_sha256(f))
    return out


def default_source_paths(workspace: Path) -> list[Path]:
    """The old files a conversion may read; none of them may change."""
    return [workspace / n for n in ("input", "client_files", "plan_snapshots", "saved_plans", "data")] + \
           [workspace / "system_config.csv", workspace / "local_state" / "secrets.local.json"]


def execute(steps: Sequence[Step], ctx: ConversionContext, report: ConversionReport) -> None:
    """Run ``steps`` in order, appending a ``StepResult`` each; stop at the first failure."""
    for step in steps:
        t0 = time.monotonic()
        try:
            if not step.applies(ctx):
                res = StepResult(step.id, "not_applicable")
            else:
                detail = step.run(ctx) or {}
                res = StepResult(step.id, "skipped" if detail.get("skipped") else "converted", detail)
        except Exception as exc:  # noqa: BLE001 - report the type only; messages can quote plan values
            res = StepResult(step.id, "failed", error_type=type(exc).__name__)
        res.seconds = time.monotonic() - t0
        report.steps.append(res)
        if res.status == "failed":
            return


_execute = execute  # WP10.1 name


def marker_keys() -> tuple[str, ...]:
    """Every ``plan_meta`` key a conversion writes."""
    from .steps import c3_plan_rows, c3b_plan_overrides, c4a_datasets, c4b_spending, c4c_ytd, c6a_settings, c6c_register, t8_tier_mapping  # noqa: PLC0415

    c4b_units = [c4b_spending.DATASET_MARKER_PREFIX + n for n in (*c4b_spending.FILES, *c4b_spending.RECOVERY_FILES)]
    return (c3_plan_rows.MARKER_KEY, c3b_plan_overrides.MARKER_KEY, c4a_datasets.MARKER_KEY, c4b_spending.MARKER_KEY,
            *c4b_units, c4c_ytd.MARKER_KEY, c6a_settings.MARKER_KEY, t8_tier_mapping.MARKER_KEY,
            c6c_register.MARKER_KEY, SEEDED_MARKER, VERIFIED_MARKER, DONE_MARKER)


def capture_initial(store: PlanStore) -> dict[str, Any]:
    """What verification needs from the plan before any step ran: its rows (engine view), the
    conversion markers present and each flat dataset's row count."""
    from ..csv_exchange import FLAT_DATASET_FILES  # noqa: PLC0415

    markers = {k: v for k in marker_keys() if (v := store.get_meta(k)) is not None}
    return {"rows": store.sectioned_data(), "markers": markers,
            "counts": {n: store.dataset(n).count() for n in FLAT_DATASET_FILES}}


# ------------------------------------------------------------------ plan files
def copy_db(src: Path, dest: Path) -> None:
    """Raw copy of a database and its ``-wal`` (the source is never opened)."""
    shutil.copyfile(src, dest)
    wal = src.with_name(src.name + "-wal")
    if wal.is_file():
        shutil.copyfile(wal, dest.with_name(dest.name + "-wal"))


def backup_db(src: Path, dest: Path) -> None:
    """Consistent copy of an open-able database (``sqlite3`` backup API, WAL included)."""
    from ..plan_db_replace import copy_sqlite_file  # noqa: PLC0415

    copy_sqlite_file(src, dest)


_copy_db, _backup_db = copy_db, backup_db  # WP10.2 names


def already_seeded(target: Path) -> bool:
    if not target.is_file():
        return False
    try:
        with PlanStore.open(target, create=False, readonly=True) as store:
            return store.get_meta(SEEDED_MARKER) is not None
    except Exception:  # noqa: BLE001 - not a plan file: seed it
        return False


_already_seeded = already_seeded  # WP10.2 name


def prepare_staging(target: Path, staging: Path, seed: Path | None = None) -> str:
    """Lay down the plan file a conversion works on: a copy of ``seed`` (mid-demo upgrade:
    ``plan.rpx.before_demo``, raw-copied because it is an original, then stamped
    ``SEEDED_MARKER``) unless ``target`` was seeded by an earlier run, else a consistent copy of
    the live ``target``, else nothing (the steps create an empty plan). ``target`` and ``seed``
    are only read. Returns how the staging plan started: ``seed`` | ``copy`` | ``new``."""
    staging.parent.mkdir(parents=True, exist_ok=True)
    for stale in (staging, staging.with_name(staging.name + "-wal"), staging.with_name(staging.name + "-shm")):
        stale.unlink(missing_ok=True)
    if seed is not None and not already_seeded(target):
        copy_db(seed, staging)
        with PlanStore.open(staging, create=False) as store:
            store.set_meta(SEEDED_MARKER, seed.name)
        return "seed"
    if target.is_file():
        backup_db(target, staging)
        return "copy"
    return "new"


def run_plan_phase(workspace: Path, staging: Path, steps: Sequence[Step], *, extra: dict[str, Any] | None = None,
                   plan_file: Path | None = None, workdir: Path | None = None,
                   dry_run: bool = False) -> tuple[ConversionContext, ConversionReport]:
    """Run ``steps`` into the plan file ``staging`` (created when missing) and close it. The
    returned context keeps the staged sources (``ctx.source_dir``) and the checkpoints for
    verification; the caller removes ``ctx.cleanup`` (or ``workdir``) afterwards. ``ctx.store``
    is closed on return."""
    report = ConversionReport(dry_run=dry_run)
    with PlanStore.open(staging) as store:
        ctx = ConversionContext(Path(workspace), store, dry_run, dict(extra or {}), plan_file=plan_file, workdir=workdir)
        ctx.checkpoints["staging_file"] = staging
        ctx.checkpoints["initial"] = capture_initial(store)
        execute(steps, ctx, report)
    return ctx, report


def run_conversion(workspace: str | Path, plan_file: str | Path, steps: Sequence[Step], *,
                   dry_run: bool = False, source_paths: Iterable[str | Path] | None = None,
                   extra: dict[str, Any] | None = None) -> ConversionReport:
    """Low level: run ``steps`` in order into ``plan_file`` (created when missing), no
    verification and no done marker (``convert_workspace`` owns both). ``dry_run`` works on a
    temporary copy of ``plan_file`` and discards it. Raises ``SourceModifiedError`` when an
    original changed."""
    workspace, plan_file = Path(workspace), Path(plan_file)
    sources = list(source_paths) if source_paths is not None else default_source_paths(workspace)
    before = snapshot_sources(sources)
    tmp = Path(tempfile.mkdtemp(prefix="conversion_dry_")) if dry_run else None
    ctx: ConversionContext | None = None
    try:
        target = plan_file
        if tmp is not None:
            target = tmp / plan_file.name
            if plan_file.is_file():
                backup_db(plan_file, target)
        ctx, report = run_plan_phase(workspace, target, steps, extra=extra, plan_file=plan_file, workdir=tmp,
                                     dry_run=dry_run)
        report.source_files = len(before)
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)
        for path in (ctx.cleanup if ctx else []):
            shutil.rmtree(path, ignore_errors=True)
    if snapshot_sources(sources) != before:
        report.sources_unchanged = False
        raise SourceModifiedError("legacy source files changed during conversion")
    return report


# ------------------------------------------------------------------ step adapters
HOUSEHOLD_SECTION = "Household"
PRE_CONVERSION_REVISION = "pre-conversion"


def plan_has_household(store: PlanStore) -> bool:
    """True when the plan holds a household (a ``Household`` row with a value). The UI-row
    backfill and a feature switch write rows into an empty plan, but never Household rows, so
    "has rows" alone does not mean the plan was converted or entered."""
    return any(str(r["value"] or "").strip() for r in store.rows(HOUSEHOLD_SECTION))


def plan_is_placeholder(ctx: ConversionContext) -> bool:
    """The target's rows are not the user's plan: no household yet, or (``_replace_plan_rows``)
    the plan file holds the demo household of an old mid-demo install whose real plan rows exist
    only as legacy files."""
    return bool(ctx.extra.get("_replace_plan_rows")) or not plan_has_household(ctx.store)


def _scratch(ctx: ConversionContext, prefix: str) -> Path:
    if ctx.workdir is not None:
        Path(ctx.workdir).mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix=prefix, dir=str(ctx.workdir) if ctx.workdir is not None else None))
    ctx.cleanup.append(path)
    return path


def _src(ctx: ConversionContext) -> dict[str, Any]:
    """SRC: choose every legacy file's source (``sources.discover``) and stage what the plan
    still needs into a scratch folder the later steps read (``ctx.source_dir``). The plan CSV set
    (and the override files) only when the plan has no household and C3 has not run; a flat
    dataset's file only when its table is empty."""
    from . import sources  # noqa: PLC0415
    from .steps import c3_plan_rows  # noqa: PLC0415

    plan = ctx.extra.get("_sources") or sources.discover(ctx.workspace, ctx.extra)
    names: list[str] = []
    if ctx.store.get_meta(c3_plan_rows.MARKER_KEY) is None and plan_is_placeholder(ctx):
        names += [*sources.PLAN_CSV_FILES, *sources.OVERRIDE_FILES]
    names += [f for n, f in sources.DATASET_FILES.items() if ctx.store.dataset(n).count() == 0]
    names += list(sources.EXTRA_FILES)
    staging = _scratch(ctx, "sources_")
    staged = sources.stage(plan, staging, names)
    ctx.source_dir = staging
    origins = plan.origins()
    done = all(ctx.store.get_meta(f"legacy_conversion.{k}") is not None for k in ("c3b", "c4a", "c4b", "c4c")) and (
        ctx.store.get_meta(c3_plan_rows.MARKER_KEY) is not None or not _plan_csv_staged(ctx))
    return {"skipped": not staged or done, "mode": plan.mode, "plan_seed": bool(plan.plan_seed),
            "legacy_db": bool(plan.legacy_db), "staged": {n: origins[n] for n in staged}}


def _plan_csv_staged(ctx: ConversionContext) -> bool:
    from ..csv_exchange import PLAN_CSV_FILES  # noqa: PLC0415
    return any((ctx.input_dir / n).is_file() for n in PLAN_CSV_FILES)


def _c3(ctx: ConversionContext) -> dict[str, Any]:
    from .steps import c3_plan_rows  # noqa: PLC0415
    cleared = 0
    if ctx.store.get_meta(c3_plan_rows.MARKER_KEY) is None and ctx.store.sections() and plan_is_placeholder(ctx):
        # Only backfilled / switch rows (an empty plan the new version opened), or an old demo's
        # rows: keep them as a revision and convert into an empty plan.
        with ctx.store.transaction():
            ctx.store.snapshot_revision(PRE_CONVERSION_REVISION, "rows before legacy conversion")
            cleared = ctx.store.clear_rows()
    out = c3_plan_rows.run(ctx.input_dir, ctx.store).as_dict()
    if cleared:
        out["placeholder_rows_replaced"] = cleared
    return out


def _c3_applies(ctx: ConversionContext) -> bool:
    return _plan_csv_staged(ctx) or ctx.store.get_meta("legacy_conversion.c3") is not None


def _c3b(ctx: ConversionContext) -> dict[str, Any]:
    from .steps import c3b_plan_overrides  # noqa: PLC0415
    files = {kind: (ctx.input_dir / name).read_text(encoding="utf-8-sig")
             for kind, name in c3b_plan_overrides.LEGACY_FILES.items() if (ctx.input_dir / name).is_file()}
    return c3b_plan_overrides.run(ctx.store, files).as_dict()


def _c4a(ctx: ConversionContext) -> dict[str, Any]:
    from .steps import c4a_datasets  # noqa: PLC0415
    return c4a_datasets.run(ctx.input_dir, ctx.store).as_dict()


def _c4b(ctx: ConversionContext) -> dict[str, Any]:
    from .steps import c4b_spending  # noqa: PLC0415
    return c4b_spending.run(ctx.input_dir, ctx.store).as_dict()


def _c4c(ctx: ConversionContext) -> dict[str, Any]:
    from .steps import c4c_ytd  # noqa: PLC0415
    return c4c_ytd.run(ctx.input_dir, ctx.store).as_dict()


def _t8(ctx: ConversionContext) -> dict[str, Any]:
    from .steps import t8_tier_mapping  # noqa: PLC0415
    if ctx.workdir is not None and ctx.store.get_meta(t8_tier_mapping.MARKER_KEY) is None:
        # The tier safeguard (verification) compares the projection just before and just after
        # the mapping: keep the plan as it is now.
        pre = Path(ctx.workdir) / PRE_TIER_FILE
        backup_db(Path(ctx.checkpoints["staging_file"]), pre)
        ctx.checkpoints["pre_tier_file"] = pre
    return t8_tier_mapping.run(ctx.store, keep_switches=ctx.extra.get("tier_mapping") == "keep").as_dict()


def _t8_applies(ctx: ConversionContext) -> bool:
    # A plan with no household (nothing converted, nothing entered) keeps the default tier.
    return plan_has_household(ctx.store)


def _app_db(ctx: ConversionContext) -> Path:
    from ..app_state import app_store_path_for  # noqa: PLC0415
    return Path(ctx.extra.get("app_db") or app_store_path_for(ctx.workspace))


def _c6a_text(ctx: ConversionContext) -> str | None:
    from .steps import c6a_settings  # noqa: PLC0415
    path = ctx.workspace / c6a_settings.LEGACY_FILE
    return path.read_text(encoding="utf-8-sig") if path.is_file() else None


def _c6a(ctx: ConversionContext) -> dict[str, Any]:
    """C6a, plan part: the engine knobs go into the plan (staging); the runtime flags are only
    listed here (``flags_written`` = what step C6a.flags writes into app.db once the plan is live)."""
    from .steps import c6a_settings  # noqa: PLC0415
    if ctx.store.get_meta(c6a_settings.MARKER_KEY) is not None:
        return {"step": "C6a", "skipped": True}  # knobs done; C6a.flags handles app.db
    return c6a_settings.run(ctx.store, _c6a_text(ctx), _app_db(ctx), dry_run=True).as_dict()


def _c6a_flags(ctx: ConversionContext) -> dict[str, Any]:
    """C6a, install part: the changed runtime flags into app.db (the knobs are in the plan)."""
    from .steps import c6a_settings  # noqa: PLC0415
    return c6a_settings.run(ctx.store, _c6a_text(ctx), _app_db(ctx), dry_run=ctx.dry_run).as_dict()


def _c6b(ctx: ConversionContext) -> dict[str, Any]:
    from .steps import c6b_secrets  # noqa: PLC0415
    return c6b_secrets.run(ctx.workspace, _app_db(ctx), delete=bool(ctx.extra.get("delete_legacy_secrets")),
                           dry_run=ctx.dry_run).as_dict()


def _c6c(ctx: ConversionContext) -> dict[str, Any]:
    from .steps import c6c_register  # noqa: PLC0415
    plan_file = ctx.plan_file or ctx.workspace / "plan.rpx"
    return c6c_register.run(ctx.store, ctx.workspace, plan_file, mid_demo=bool(ctx.extra.get("_mid_demo")),
                            dry_run=ctx.dry_run).as_dict()


def _c6c_applies(ctx: ConversionContext) -> bool:
    return plan_has_household(ctx.store)


DATASET_STEPS: tuple[Step, ...] = (
    Step("C3", _c3, _c3_applies), Step("C3b", _c3b), Step("C4a", _c4a), Step("C4b", _c4b), Step("C4c", _c4c),
)
# Plan phase (WP10.3): writes only the plan file it is given (the staging copy). Order: sources,
# plan rows and overrides, flat datasets, engine knobs, then the tier mapping (needs the converted
# switches and data; the knobs never count as feature data).
PLAN_STEPS: tuple[Step, ...] = (Step("SRC", _src), *DATASET_STEPS, Step("C6a", _c6a), Step("T8", _t8, _t8_applies))
# Install phase: app.db settings, secrets, registration last (the plan is live and complete before
# it becomes the active plan). Runs only after the verified staging plan replaced the live one.
INSTALL_STEPS: tuple[Step, ...] = (Step("C6a.flags", _c6a_flags), Step("C6b", _c6b), Step("C6c", _c6c, _c6c_applies))
CONVERSION_STEPS: tuple[Step, ...] = (*PLAN_STEPS, *INSTALL_STEPS)
