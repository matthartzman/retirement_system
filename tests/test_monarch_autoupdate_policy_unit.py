"""Ticket 305: Monarch auto-update policy (enabled/source_dir) and run-status
("mark the update as complete") file handling, shaped after
src/local_backup_scheduler.py's policy pattern.
"""
from __future__ import annotations

from src import monarch_autoupdate as mau


def test_default_policy_is_disabled_with_default_source_dir(tmp_path):
    loaded = mau.load_policy(tmp_path)
    assert loaded["policy"]["enabled"] is False
    assert loaded["policy"]["source_dir"] == mau.DEFAULT_SOURCE_DIR


def test_save_and_reload_policy_round_trips(tmp_path):
    mau.save_policy(tmp_path, {"enabled": True, "source_dir": "Monarch Extractor/output"})
    loaded = mau.load_policy(tmp_path)
    assert loaded["policy"]["enabled"] is True
    assert loaded["policy"]["source_dir"] == "Monarch Extractor/output"


def test_save_policy_rejects_source_dir_outside_workspace_root(tmp_path):
    """System review 2026-09-07 SEC-2: source_dir used to be accepted with no
    confinement check, and fed straight into a subprocess interpreter lookup
    -- a sibling-of-workspace (or any other out-of-tree) path must be
    rejected rather than silently persisted."""
    import pytest

    with pytest.raises(mau.SourceDirOutsideWorkspaceError):
        mau.save_policy(tmp_path, {"source_dir": "../Monarch Extractor/output"})
    with pytest.raises(mau.SourceDirOutsideWorkspaceError):
        mau.save_policy(tmp_path, {"source_dir": "/etc"})


def test_save_policy_only_updates_provided_keys(tmp_path):
    mau.save_policy(tmp_path, {"enabled": True, "source_dir": "custom/dir"})
    mau.save_policy(tmp_path, {"enabled": False})
    loaded = mau.load_policy(tmp_path)
    assert loaded["policy"]["enabled"] is False
    assert loaded["policy"]["source_dir"] == "custom/dir"


def test_no_status_file_yet_returns_none(tmp_path):
    assert mau.load_status(tmp_path) is None


def test_write_status_then_load_round_trips(tmp_path):
    mau.write_status(tmp_path, success=True, files_consumed=["a.csv"], rows_added=2, rows_updated=1, rows_skipped=0)
    status = mau.load_status(tmp_path)
    assert status["success"] is True
    assert status["files_consumed"] == ["a.csv"]
    assert status["rows_added"] == 2
    assert status["rows_updated"] == 1


def test_write_status_records_failure_with_errors(tmp_path):
    mau.write_status(tmp_path, success=False, errors=["source folder not found"])
    status = mau.load_status(tmp_path)
    assert status["success"] is False
    assert status["errors"] == ["source folder not found"]


def test_resolve_source_dir_is_relative_to_base_dir(tmp_path):
    mau.save_policy(tmp_path, {"source_dir": "Monarch Extractor/output"})
    policy = mau.load_policy(tmp_path)["policy"]
    resolved = mau.resolve_source_dir(tmp_path, policy)
    assert resolved.name == "output"
    assert resolved.parent.name == "Monarch Extractor"
