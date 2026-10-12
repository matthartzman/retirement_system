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

    @property
    def input_dir(self) -> Path:
        return self.workspace / "input"


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


def run_conversion(workspace: str | Path, plan_file: str | Path, steps: Sequence[Step], *,
                   dry_run: bool = False, source_paths: Iterable[str | Path] | None = None,
                   extra: dict[str, Any] | None = None) -> ConversionReport:
    """Run ``steps`` in order into ``plan_file`` (created when missing).

    ``dry_run`` works on a temporary copy of ``plan_file`` and discards it. The done marker
    (``DONE_MARKER``) is set only on a real run where every step succeeded."""
    workspace, plan_file = Path(workspace), Path(plan_file)
    sources = list(source_paths) if source_paths is not None else default_source_paths(workspace)
    before = snapshot_sources(sources)
    report = ConversionReport(dry_run=dry_run, source_files=len(before))
    tmp = tempfile.mkdtemp(prefix="conversion_dry_") if dry_run else None
    try:
        target = plan_file
        if dry_run:
            target = Path(tmp) / plan_file.name
            if plan_file.is_file():
                shutil.copy2(plan_file, target)
        with PlanStore.open(target) as store:
            ctx = ConversionContext(workspace, store, dry_run, dict(extra or {}))
            _execute(steps, ctx, report)
            if report.ok and not dry_run and report.converted:
                store.set_meta(DONE_MARKER, time.strftime("%Y-%m-%dT%H:%M:%S"))
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    after = snapshot_sources(sources)
    if after != before:
        report.sources_unchanged = False
        raise SourceModifiedError("legacy source files changed during conversion")
    return report


# ------------------------------------------------------------------ step adapters (C3 .. C4c)
def _c3(ctx: ConversionContext) -> dict[str, Any]:
    from .steps import c3_plan_rows  # noqa: PLC0415
    return c3_plan_rows.run(ctx.input_dir, ctx.store).as_dict()


def _c3_applies(ctx: ConversionContext) -> bool:
    return (ctx.input_dir / "client_data.csv").is_file() or ctx.store.get_meta("legacy_conversion.c3") is not None


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


DATASET_STEPS: tuple[Step, ...] = (
    Step("C3", _c3, _c3_applies), Step("C3b", _c3b), Step("C4a", _c4a), Step("C4b", _c4b), Step("C4c", _c4c),
)
