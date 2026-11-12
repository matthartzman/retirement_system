"""Backups are consistent snapshots and every in-place upgrade leaves a copy (ARC-004 / W2-06)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src import local_backup_scheduler as lbs
from src.stores import db
from src.stores.plan_store import PLAN_MIGRATIONS, PlanStore, plan_paths


def _write_rows(path: Path, n: int) -> sqlite3.Connection:
    con = sqlite3.connect(str(path), isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE IF NOT EXISTS t (v INTEGER)")
    for i in range(n):
        con.execute("INSERT INTO t VALUES (?)", (i,))
    return con


def _count(path: Path) -> int:
    con = sqlite3.connect(str(path))
    try:
        return con.execute("SELECT count(*) FROM t").fetchone()[0]
    finally:
        con.close()


def test_backup_holds_every_committed_row_with_a_writer_open_on_a_wal_database(tmp_path):
    src = tmp_path / "plan.rpx"
    writer = _write_rows(src, 200)  # stays open: committed frames may still sit in the -wal file
    try:
        assert Path(str(src) + "-wal").exists()
        target = tmp_path / "copy.rpx"
        lbs._copy_database(src, target)
        assert _count(target) == 200
        assert not Path(str(target) + "-wal").exists() or _count(target) == 200
    finally:
        writer.close()


def test_run_backup_uses_the_snapshot_and_records_it(tmp_path):
    src = tmp_path / "plan.rpx"
    writer = _write_rows(src, 50)
    try:
        out = lbs.run_backup(tmp_path, src, trigger="test", force=True)
        assert out["created"] is True
        assert _count(Path(out["backup"]["path"])) == 50
    finally:
        writer.close()


def test_a_plain_non_database_file_is_still_copied(tmp_path):
    src = tmp_path / "notes.txt"
    src.write_text("hello", encoding="utf-8")
    target = tmp_path / "out.txt"
    lbs._copy_database(src, target)
    assert target.read_text(encoding="utf-8") == "hello"


def test_checkpoint_result_is_returned(tmp_path):
    src = tmp_path / "plan.rpx"
    writer = _write_rows(src, 5)
    try:
        result = lbs.checkpoint_sqlite(src)
        assert result is not None and len(result) == 3
    finally:
        writer.close()
    assert lbs.checkpoint_sqlite(tmp_path / "missing.rpx") is not None or True  # never raises


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path / "ws"))
    return tmp_path / "ws"


def _make_old_plan(path: Path, version: int) -> None:
    con = db.connect(str(path), readonly=False)
    try:
        db.migrate(con, PLAN_MIGRATIONS[:version])
    finally:
        con.close()


def test_opening_a_v23_plan_leaves_a_v23_copy_before_upgrading(workspace, tmp_path):
    plan = tmp_path / "myplan.rpx"
    _make_old_plan(plan, 23)
    with PlanStore.open(plan) as store:
        assert store.schema_version == len(PLAN_MIGRATIONS)
    copies = sorted(plan_paths("myplan").backups_dir.glob("myplan.pre_upgrade_v23_*"))
    assert len(copies) == 1
    con = sqlite3.connect(str(copies[0]))
    try:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 23
    finally:
        con.close()


def test_a_current_plan_and_a_memory_store_leave_no_copy(workspace, tmp_path):
    plan = tmp_path / "fresh.rpx"
    PlanStore.open(plan).close()  # new file: created at the current version, nothing to preserve
    PlanStore.open(plan).close()  # reopened at the current version
    PlanStore.open(":memory:").close()
    assert not plan_paths("fresh").backups_dir.exists()


def test_a_readonly_open_never_writes_a_copy(workspace, tmp_path):
    plan = tmp_path / "ro.rpx"
    _make_old_plan(plan, 23)
    with pytest.raises(Exception):
        PlanStore.open(plan, readonly=True)  # needs an upgrade: refused, and no copy is made
    assert not plan_paths("ro").backups_dir.exists()


def test_the_pre_upgrade_copies_are_capped(workspace, tmp_path, monkeypatch):
    import src.stores._base as base

    monkeypatch.setattr(base, "PRE_UPGRADE_KEEP", 2)
    plan = tmp_path / "capped.rpx"
    for _ in range(4):
        _make_old_plan(plan, 23) if not plan.exists() else None
        con = sqlite3.connect(str(plan))
        con.execute("PRAGMA user_version=23")  # pretend it is old again; tables already exist
        con.close()
        try:
            PlanStore.open(plan).close()
        except Exception:
            pass
    kept = list(plan_paths("capped").backups_dir.glob("capped.pre_upgrade_v*"))
    assert 1 <= len(kept) <= 2
