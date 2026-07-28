from __future__ import annotations
"""Phase 0 (Android groundwork): callable build entry + BuildRunner abstraction.

Uses a stubbed build so the tests stay fast and deterministic; a real
subprocess-vs-in-process artifact parity check is covered by manual/integration
verification (a full build is minutes-long).
"""

import subprocess
import time

import pytest

import src.platform_runtime as platform_runtime
from src import build_entry
from src.server_services import build_runner


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


def test_should_run_in_process_tracks_build_mode(monkeypatch):
    monkeypatch.setenv(platform_runtime.BUILD_MODE_ENV, "subprocess")
    assert build_runner.should_run_in_process() is False
    monkeypatch.setenv(platform_runtime.BUILD_MODE_ENV, "inprocess")
    assert build_runner.should_run_in_process() is True


def test_build_outcome_matches_completed_process_surface():
    outcome = build_runner.BuildOutcome(returncode=0, stdout="hi", stderr="")
    # Downstream code reads these three attributes off subprocess.CompletedProcess.
    assert (outcome.returncode, outcome.stdout, outcome.stderr) == (0, "hi", "")


def test_run_inprocess_build_captures_and_streams(monkeypatch):
    lines: list[str] = []

    def _fake_build():
        print("Loading active configuration...")
        print("QC: 32 / 32 PASS")
        return build_entry.BuildResult(returncode=0, workspace_root="/ws")

    monkeypatch.setattr(build_runner, "_run_build", _fake_build)
    outcome = build_runner.run_inprocess_build(env=None, on_line=lines.append, timeout=30)

    assert outcome.returncode == 0
    assert "QC: 32 / 32 PASS" in outcome.stdout
    # Each complete line was streamed for progress updates.
    assert any("QC: 32 / 32 PASS" in ln for ln in lines)


def test_run_inprocess_build_restores_environment(monkeypatch):
    import os

    sentinel_before = os.environ.get("RS_TEST_SENTINEL")

    def _fake_build():
        # The build sees the injected env...
        assert os.environ.get("RS_TEST_SENTINEL") == "injected"
        return build_entry.BuildResult(returncode=0, workspace_root="/ws")

    monkeypatch.setattr(build_runner, "_run_build", _fake_build)
    injected = dict(os.environ)
    injected["RS_TEST_SENTINEL"] = "injected"
    build_runner.run_inprocess_build(env=injected, timeout=30)

    # ...and the process environment is restored afterward.
    assert os.environ.get("RS_TEST_SENTINEL") == sentinel_before


def test_run_inprocess_build_nonzero_on_exception(monkeypatch):
    def _boom():
        raise RuntimeError("projection failed")

    monkeypatch.setattr(build_runner, "_run_build", _boom)
    outcome = build_runner.run_inprocess_build(env=None, timeout=30)
    assert outcome.returncode == 1
    assert "projection failed" in outcome.stdout


def test_run_inprocess_build_times_out(monkeypatch):
    def _slow():
        time.sleep(5)
        return build_entry.BuildResult(returncode=0, workspace_root="/ws")

    monkeypatch.setattr(build_runner, "_run_build", _slow)
    with pytest.raises(subprocess.TimeoutExpired):
        build_runner.run_inprocess_build(env=None, timeout=0.2)
