"""Ticket 305: after a successful upsert, the import job must acknowledge
each imported Monarch run_id back to the extractor's own outbox
(`python monarch_extract.py --mark-delivered <run_id>`), or that run's rows
keep reappearing in new_transactions.csv/changed_transactions.csv forever.
This is best-effort: a failure here must never fail an already-successful
import.
"""
from __future__ import annotations

from pathlib import Path

from src.monarch_autoimport_job import _mark_runs_delivered, _resolve_extractor_python


def test_no_run_ids_is_a_silent_no_op(tmp_path):
    assert _mark_runs_delivered(tmp_path, []) == []


def test_missing_extractor_script_is_reported(tmp_path):
    errors = _mark_runs_delivered(tmp_path, ["run-1"])
    assert len(errors) == 1
    assert "monarch_extract.py" in errors[0]


def test_missing_extractor_venv_is_reported(tmp_path):
    (tmp_path / "monarch_extract.py").write_text("# stub", encoding="utf-8")
    errors = _mark_runs_delivered(tmp_path, ["run-1"])
    assert len(errors) == 1
    assert "venv" in errors[0].lower()


def test_resolve_extractor_python_prefers_windows_venv_layout(tmp_path):
    scripts_dir = tmp_path / ".venv" / "Scripts"
    scripts_dir.mkdir(parents=True)
    python_exe = scripts_dir / "python.exe"
    python_exe.write_text("", encoding="utf-8")
    assert _resolve_extractor_python(tmp_path) == python_exe


def test_resolve_extractor_python_falls_back_to_posix_venv_layout(tmp_path):
    bin_dir = tmp_path / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    python_bin = bin_dir / "python"
    python_bin.write_text("", encoding="utf-8")
    assert _resolve_extractor_python(tmp_path) == python_bin


def test_resolve_extractor_python_returns_none_when_no_venv_exists(tmp_path):
    assert _resolve_extractor_python(tmp_path) is None


def test_mark_run_delivered_invokes_the_extractor_with_the_run_id(tmp_path):
    # A real venv layout with a fake python that just echoes its args and
    # exits 0 -- verifies the subprocess call shape without needing a real
    # Playwright install.
    scripts_dir = tmp_path / ".venv" / "Scripts"
    scripts_dir.mkdir(parents=True)
    fake_python = scripts_dir / "python.exe"
    fake_python.write_text("", encoding="utf-8")
    script = tmp_path / "monarch_extract.py"
    script.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")

    # fake_python.exe is not actually executable on this platform (it's a
    # stub file, not a real interpreter) -- exercised via a real Python
    # interpreter substituted in by monkeypatching subprocess.run instead of
    # trying to make an OS-runnable fake exe portable across CI platforms.
    import subprocess as subprocess_module
    import src.monarch_autoimport_job as job_module

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess_module.CompletedProcess(cmd, 0, stdout="", stderr="")

    original_run = job_module.subprocess.run
    job_module.subprocess.run = fake_run
    try:
        errors = _mark_runs_delivered(tmp_path, ["run-1", "run-2"])
    finally:
        job_module.subprocess.run = original_run

    assert errors == []
    assert len(calls) == 2
    assert calls[0][:2] == [str(fake_python), str(script)]
    assert calls[0][2:] == ["--mark-delivered", "run-1"]
    assert calls[1][2:] == ["--mark-delivered", "run-2"]


def test_a_nonzero_exit_is_reported_but_does_not_raise(tmp_path):
    scripts_dir = tmp_path / ".venv" / "Scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "python.exe").write_text("", encoding="utf-8")
    (tmp_path / "monarch_extract.py").write_text("", encoding="utf-8")

    import subprocess as subprocess_module
    import src.monarch_autoimport_job as job_module

    def fake_run(cmd, **kwargs):
        return subprocess_module.CompletedProcess(cmd, 1, stdout="", stderr="run not found")

    original_run = job_module.subprocess.run
    job_module.subprocess.run = fake_run
    try:
        errors = _mark_runs_delivered(tmp_path, ["run-1"])
    finally:
        job_module.subprocess.run = original_run

    assert len(errors) == 1
    assert "run-1" in errors[0]
    assert "run not found" in errors[0]
