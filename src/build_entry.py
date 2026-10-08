from __future__ import annotations
"""Callable workbook-build entry point.

Historically the only way to run a build was to launch ``tools/build_workbook.py``
as a subprocess. That is impossible on a mobile host, which cannot spawn a
second interpreter. This module extracts the build steps into an importable
``run_build`` function so the same logic can run either as a subprocess (desktop
default) or in-process on a worker thread (mobile).

The steps mirror the historical ``tools/build_workbook.py`` ``__main__`` block:
run the workbook builder (which reads the plan rows and the flat dataset tables of the active
plan file). Output is still
communicated the same way — ``output/plan_summary.json`` plus the ``QC: n/n
PASS`` stdout line — so existing progress-parsing and summary-reading callers
are unchanged.
"""

from dataclasses import dataclass
from pathlib import Path

from . import platform_runtime


@dataclass(frozen=True)
class BuildResult:
    """Outcome of an in-process build. ``returncode`` mirrors a process exit code."""

    returncode: int
    workspace_root: str


def run_build(root: str | Path | None = None) -> BuildResult:
    """Run a full workbook build in the current process.

    Returns a :class:`BuildResult` with ``returncode == 0`` on success. Callers
    that need process-style isolation (the desktop default) should use the
    subprocess build runner instead; this function performs no stdout capture or
    exception swallowing.
    """
    workspace = Path(root) if root is not None else platform_runtime.workspace_root()

    # Imported lazily: workbook_builder pulls in the full reporting/projection
    # stack, which is heavy and unnecessary for callers that only import the
    # build-entry contract (e.g. the build runner's mode selection).
    from .reporting.workbook_builder import main as _build_main

    _build_main()
    return BuildResult(returncode=0, workspace_root=str(workspace))
