"""legacy_conversion runner (WP10.1): runs the ordered conversion steps against one plan file.

* ``ConversionContext`` carries the workspace, the folders the old files live in, the open plan
  store and the dry-run flag.
* Every step is a ``Step(id, run)``; ``run(ctx)`` returns a small privacy-safe dict (counts and
  names only, never plan values). Steps carry their own idempotency markers in ``plan_meta``
  (``legacy_conversion.<step>``), so a re-run converts only what is missing.
* ``run_conversion`` snapshots every source file before and after (size + SHA-256) and raises
  ``SourceModifiedError`` if any original changed: the originals are never modified.
* Dry run converts into a throwaway copy of the target plan and leaves the real one untouched.
* A failing step stops the run (later steps may depend on it); the report says which step and
  the exception type (the message is withheld, it can quote plan values).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from ..stores import PlanStore

DONE_MARKER = "legacy_conversion.done"


class SourceModifiedError(RuntimeError):
    """A legacy source file changed during a conversion run (never expected)."""


@dataclass
class ConversionContext:
    workspace: Path
    store: PlanStore
    dry_run: bool = False
    extra: dict[str, Any] = field(default_factory=dict)
    # The folder the file-reading steps read: ``input/`` unless step SRC staged the sources
    # chosen by precedence (``sources.discover``) into a temp folder.
    source_dir: Path | None = None
    plan_file: Path | None = None  # the real target (not the dry-run copy)
    cleanup: list[Path] = field(default_factory=list)  # temp folders removed after the run

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

    def as_dict(self) -> dict[str, Any]:
        return {"dry_run": self.dry_run, "ok": self.ok, "sources_unchanged": self.sources_unchanged,
                "source_files": self.source_files, "steps": [s.as_dict() for s in self.steps]}


def snapshot_sources(paths: Iterable[str | Path]) -> dict[str, tuple[int, str]]:
    """``{path: (size, sha256)}`` of every file under the given files/folders (folders walked)."""
    out: dict[str, tuple[int, str]] = {}
    for root in paths:
        root = Path(root)
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file()) if root.is_dir() else []
        for f in files:
            h = hashlib.sha256()
            with open(f, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            out[str(f)] = (f.stat().st_size, h.hexdigest())
    return out


def default_source_paths(workspace: Path) -> list[Path]:
    """The old files a conversion may read; none of them may change."""
    return [workspace / n for n in ("input", "client_files", "plan_snapshots", "saved_plans", "data")] + \
           [workspace / "system_config.csv", workspace / "local_state" / "secrets.local.json"]


def _execute(steps: Sequence[Step], ctx: ConversionContext, report: ConversionReport) -> None:
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


SEEDED_MARKER = "legacy_conversion.seeded_from"


def _copy_db(src: Path, dest: Path) -> None:
    """Raw copy of a database and its ``-wal`` (the source is never opened)."""
    shutil.copyfile(src, dest)
    wal = src.with_name(src.name + "-wal")
    if wal.is_file():
        shutil.copyfile(wal, dest.with_name(dest.name + "-wal"))


def _backup_db(src: Path, dest: Path) -> None:
    """Consistent copy of an open-able database (``sqlite3`` backup API, WAL included)."""
    import sqlite3  # noqa: PLC0415
    from contextlib import closing  # noqa: PLC0415

    with closing(sqlite3.connect(src)) as a, closing(sqlite3.connect(dest)) as b:
        a.backup(b)


def _seed_target(seed: Path, target: Path) -> None:
    """Make ``target`` a plan file holding a copy of ``seed`` (schema brought up to date on the
    copy; ``seed`` itself is only copied). An existing ``target`` is kept beside it as
    ``<name>.pre_conversion_<ts>`` first."""
    from ..plan_db_replace import remove_sidecars  # noqa: PLC0415

    target.parent.mkdir(parents=True, exist_ok=True)
    work = target.with_name(target.name + ".seeding")
    for stale in (work, work.with_name(work.name + "-wal"), work.with_name(work.name + "-shm")):
        stale.unlink(missing_ok=True)
    _copy_db(seed, work)
    with PlanStore.open(work, create=False) as store:
        store.set_meta(SEEDED_MARKER, seed.name)
    remove_sidecars(work)
    if target.is_file():
        _backup_db(target, target.with_name(f"{target.name}.pre_conversion_{time.strftime('%Y%m%d_%H%M%S')}"))
    remove_sidecars(target)
    os.replace(str(work), str(target))


def _already_seeded(target: Path) -> bool:
    if not target.is_file():
        return False
    try:
        with PlanStore.open(target, create=False, readonly=True) as store:
            return store.get_meta(SEEDED_MARKER) is not None
    except Exception:  # noqa: BLE001 - not a plan file: seed it
        return False


def run_conversion(workspace: str | Path, plan_file: str | Path, steps: Sequence[Step], *,
                   dry_run: bool = False, source_paths: Iterable[str | Path] | None = None,
                   extra: dict[str, Any] | None = None, seed_plan: str | Path | None = None) -> ConversionReport:
    """Run ``steps`` in order into ``plan_file`` (created when missing).

    ``seed_plan`` (mid-demo upgrade: ``plan.rpx.before_demo``) is a plan file the target starts
    from: its copy replaces ``plan_file`` (whose old content is kept as
    ``<name>.pre_conversion_<ts>``) unless ``plan_file`` was already seeded by an earlier run.
    ``dry_run`` works on a temporary copy of ``plan_file`` (or of the seed) and discards it. The
    done marker (``DONE_MARKER``) is set only on a real run where every step succeeded."""
    workspace, plan_file = Path(workspace), Path(plan_file)
    seed = Path(seed_plan) if seed_plan else None
    sources = list(source_paths) if source_paths is not None else default_source_paths(workspace)
    before = snapshot_sources(sources)
    report = ConversionReport(dry_run=dry_run, source_files=len(before))
    tmp = tempfile.mkdtemp(prefix="conversion_dry_") if dry_run else None
    ctx: ConversionContext | None = None
    try:
        target = plan_file
        if dry_run:
            target = Path(tmp) / plan_file.name
            if seed is not None and not _already_seeded(plan_file):
                _copy_db(seed, target)
            elif plan_file.is_file():
                _backup_db(plan_file, target)
        elif seed is not None and not _already_seeded(plan_file):
            _seed_target(seed, plan_file)
        with PlanStore.open(target) as store:
            ctx = ConversionContext(workspace, store, dry_run, dict(extra or {}), plan_file=plan_file)
            _execute(steps, ctx, report)
            if report.ok and not dry_run and report.converted:
                store.set_meta(DONE_MARKER, time.strftime("%Y-%m-%dT%H:%M:%S"))
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
        for path in (ctx.cleanup if ctx else []):
            shutil.rmtree(path, ignore_errors=True)
    after = snapshot_sources(sources)
    if after != before:
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


def _src(ctx: ConversionContext) -> dict[str, Any]:
    """SRC: choose every legacy file's source (``sources.discover``) and stage what the plan
    still needs into a temp folder the later steps read (``ctx.source_dir``). The plan CSV set
    (and the override files) only when the plan has no household and C3 has not run; a flat
    dataset's file only when its table is empty."""
    from . import sources  # noqa: PLC0415
    from .steps import c3_plan_rows  # noqa: PLC0415

    plan = ctx.extra.get("_sources") or sources.discover(ctx.workspace, ctx.extra)
    names: list[str] = []
    if ctx.store.get_meta(c3_plan_rows.MARKER_KEY) is None and not plan_has_household(ctx.store):
        names += [*sources.PLAN_CSV_FILES, *sources.OVERRIDE_FILES]
    names += [f for n, f in sources.DATASET_FILES.items() if ctx.store.dataset(n).count() == 0]
    names += list(sources.EXTRA_FILES)
    staging = Path(tempfile.mkdtemp(prefix="conversion_sources_"))
    ctx.cleanup.append(staging)
    staged = sources.stage(plan, staging, names)
    ctx.source_dir = staging
    origins = plan.origins()
    return {"skipped": not staged, "mode": plan.mode, "plan_seed": bool(plan.plan_seed),
            "legacy_db": bool(plan.legacy_db), "staged": {n: origins[n] for n in staged}}


def _plan_csv_staged(ctx: ConversionContext) -> bool:
    from ..csv_exchange import PLAN_CSV_FILES  # noqa: PLC0415
    return any((ctx.input_dir / n).is_file() for n in PLAN_CSV_FILES)


def _c3(ctx: ConversionContext) -> dict[str, Any]:
    from .steps import c3_plan_rows  # noqa: PLC0415
    cleared = 0
    if ctx.store.get_meta(c3_plan_rows.MARKER_KEY) is None and ctx.store.sections() and not plan_has_household(ctx.store):
        # Only backfilled / switch rows (an empty plan the new version opened): keep them as a
        # revision and convert into an empty plan.
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
    return t8_tier_mapping.run(ctx.store).as_dict()


def _t8_applies(ctx: ConversionContext) -> bool:
    # A plan with no household (nothing converted, nothing entered) keeps the default tier.
    return plan_has_household(ctx.store)


def _app_db(ctx: ConversionContext) -> Path:
    from ..app_state import app_store_path_for  # noqa: PLC0415
    return Path(ctx.extra.get("app_db") or app_store_path_for(ctx.workspace))


def _c6a(ctx: ConversionContext) -> dict[str, Any]:
    from .steps import c6a_settings  # noqa: PLC0415
    path = ctx.workspace / c6a_settings.LEGACY_FILE
    text = path.read_text(encoding="utf-8-sig") if path.is_file() else None
    return c6a_settings.run(ctx.store, text, _app_db(ctx), dry_run=ctx.dry_run).as_dict()


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
# The full conversion, in order (WP10.2): sources, plan rows and overrides, flat datasets, tier
# mapping (needs the converted switches and data), app.db settings, secrets, registration last
# (the plan is complete before it becomes the active plan).
CONVERSION_STEPS: tuple[Step, ...] = (
    Step("SRC", _src), *DATASET_STEPS, Step("T8", _t8, _t8_applies),
    Step("C6a", _c6a), Step("C6b", _c6b), Step("C6c", _c6c, _c6c_applies),
)
