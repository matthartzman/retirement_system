from __future__ import annotations
"""Callable build entry point.

Uses a stubbed build so the tests stay fast and deterministic.
"""

import src.platform_runtime as platform_runtime
from src import build_entry


def test_build_entry_exposes_callable_run_build():
    assert callable(build_entry.run_build)
    # BuildResult mirrors a process exit code contract.
    fields = build_entry.BuildResult.__dataclass_fields__
    assert "returncode" in fields and "workspace_root" in fields


def test_tools_wrapper_delegates_to_build_entry():
    # The CLI wrapper must not re-implement build logic; it delegates to run_build.
    text = (platform_runtime.package_root() / "tools" / "build_workbook.py").read_text(encoding="utf-8")
    assert "from src.build_entry import run_build" in text
    assert "run_build()" in text
