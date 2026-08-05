"""Retention coverage for result snapshots and orphaned backup copies.

Both paths were unbounded: `result_snapshots` had no reader and no cap, so it
grew to dominate the SQLite file, and every auto-backup copies that whole file.
Separately, a backup whose manifest went missing was invisible to retention.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import local_store
from src.local_backup_scheduler import orphaned_backups, prune_backups, run_backup, save_policy


def _count_results(db: Path) -> int:
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT COUNT(*) FROM result_snapshots").fetchone()[0]
    finally:
        con.close()


def _result_ids(db: Path) -> list[str]:
    con = sqlite3.connect(db)
    try:
        return [r[0] for r in con.execute("SELECT result_id FROM result_snapshots ORDER BY created_at DESC, result_id DESC")]
    finally:
        con.close()


def test_result_snapshots_are_capped_at_retention(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    for i in range(local_store.DEFAULT_RESULT_SNAPSHOT_RETENTION + 15):
        local_store.save_result_snapshot({"run": i}, [{"event": i}], db_path=db)

    assert _count_results(db) == local_store.DEFAULT_RESULT_SNAPSHOT_RETENTION


def test_pruning_keeps_the_newest_snapshot(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    for i in range(local_store.DEFAULT_RESULT_SNAPSHOT_RETENTION + 5):
        last_id = local_store.save_result_snapshot({"run": i}, db_path=db)

    assert last_id in _result_ids(db)


def test_explicit_prune_trims_existing_backlog(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    for i in range(30):
        local_store.save_result_snapshot({"run": i}, db_path=db)

    removed = local_store.prune_result_snapshots(keep=3, db_path=db)

    assert _count_results(db) == 3
    assert removed == local_store.DEFAULT_RESULT_SNAPSHOT_RETENTION - 3


def test_prune_result_snapshots_is_safe_on_missing_db(tmp_path: Path) -> None:
    assert local_store.prune_result_snapshots(db_path=tmp_path / "nope.db") == 0


def _make_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS t(v TEXT)")
    con.commit()
    con.close()


def test_backup_without_manifest_is_detected_as_orphan(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    _make_db(db)
    save_policy(tmp_path, {"enabled": True, "cadence": "per_build", "retention_count": 2})
    run_backup(tmp_path, db, trigger="build", force=True)

    bdir = tmp_path / "saved_plans" / "auto_backups"
    manifest = next(bdir.glob("*.manifest.json"))
    manifest.unlink()

    orphans = orphaned_backups(tmp_path)
    assert [p.name for p in orphans] == [manifest.name.replace(".manifest.json", "")]


def test_prune_removes_orphaned_backup_copies(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    _make_db(db)
    policy = save_policy(tmp_path, {"enabled": True, "cadence": "per_build", "retention_count": 2})["policy"]
    run_backup(tmp_path, db, trigger="build", force=True)

    bdir = tmp_path / "saved_plans" / "auto_backups"
    next(bdir.glob("*.manifest.json")).unlink()
    assert list(bdir.glob("*.rpx"))

    prune_backups(tmp_path, policy)

    assert list(bdir.glob("*.rpx")) == []


def test_retention_still_holds_across_repeated_backups(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    _make_db(db)
    save_policy(tmp_path, {"enabled": True, "cadence": "per_build", "retention_count": 3})

    for _ in range(8):
        run_backup(tmp_path, db, trigger="build", force=True)

    bdir = tmp_path / "saved_plans" / "auto_backups"
    assert len(list(bdir.glob("*.rpx"))) == 3
    assert len(list(bdir.glob("*.manifest.json"))) == 3
