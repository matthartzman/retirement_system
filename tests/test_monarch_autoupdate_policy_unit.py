"""Ticket 305: Monarch auto-update policy (enabled/source_dir) and run-status
("mark the update as complete") file handling, shaped after
src/local_backup_scheduler.py's policy pattern.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

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


def _touch_raw_file(base_dir, name, mtime: datetime) -> None:
    raw_dir = mau.extractor_raw_dir(base_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / name
    path.write_text("id,date,merchant,amount\n", encoding="utf-8")
    ts = mtime.timestamp()
    import os

    os.utime(path, (ts, ts))


def test_extractor_freshness_with_no_raw_files_is_stale(tmp_path):
    freshness = mau.get_extractor_freshness(tmp_path)
    assert freshness["last_extract_at"] is None
    assert freshness["stale"] is True


def test_extractor_freshness_recent_file_is_not_stale(tmp_path):
    now = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
    _touch_raw_file(tmp_path, "monarch-20260914-060000-attempt1.csv", now - timedelta(hours=6))
    freshness = mau.get_extractor_freshness(tmp_path, now=now)
    assert freshness["stale"] is False
    assert freshness["last_extract_at"] is not None
    assert freshness["age_hours"] == 6.0


def test_extractor_freshness_old_file_is_stale(tmp_path):
    """This is the exact shape of the 2026-09 outage: the extractor's own
    raw/ output goes untouched for days while the downstream import job
    keeps reporting success (nothing new to import isn't the same as
    nothing wrong)."""
    now = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
    _touch_raw_file(tmp_path, "monarch-20260909-114609-attempt1.csv", now - timedelta(days=5))
    freshness = mau.get_extractor_freshness(tmp_path, now=now)
    assert freshness["stale"] is True
    assert freshness["age_hours"] == pytest.approx(120.0)


def test_extractor_freshness_picks_newest_of_multiple_files(tmp_path):
    now = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
    _touch_raw_file(tmp_path, "monarch-20260903-075154-attempt2.csv", now - timedelta(days=11))
    _touch_raw_file(tmp_path, "monarch-20260909-114609-attempt1.csv", now - timedelta(days=5))
    freshness = mau.get_extractor_freshness(tmp_path, now=now)
    assert freshness["age_hours"] == pytest.approx(120.0)
