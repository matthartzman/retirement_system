import sqlite3
from pathlib import Path

from src.build_snapshot import (
    SNAPSHOT_DB_FILENAME,
    SNAPSHOT_FILENAME,
    compare_snapshot_to_current,
    read_build_snapshot,
    restore_sqlite_database_from_snapshot,
    write_build_snapshot,
)


def _make_db(path: Path, value: str):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS marker(value TEXT)")
    conn.execute("DELETE FROM marker")
    conn.execute("INSERT INTO marker(value) VALUES (?)", (value,))
    conn.commit()
    conn.close()


def _read_value(path: Path) -> str:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT value FROM marker").fetchone()[0]
    finally:
        conn.close()


def test_build_snapshot_captures_sqlite_database_copy_and_hash(tmp_path):
    output = tmp_path / "output"
    db = tmp_path / "active.rpx"
    _make_db(db, "snapshot")
    (output / "plan_summary.json").parent.mkdir(parents=True, exist_ok=True)
    (output / "plan_summary.json").write_text('{"ok": true}', encoding="utf-8")

    snapshot = write_build_snapshot(output, build_id="b1", sqlite_db_path=db, output_files=["plan_summary.json"])

    assert snapshot["sqlite_database"]["sha256"]
    assert snapshot["sqlite_database_snapshot"]["file"] == SNAPSHOT_DB_FILENAME
    assert Path(snapshot["sqlite_database_snapshot"]["path"]).exists()
    assert read_build_snapshot(output / SNAPSHOT_FILENAME)["sqlite_database_snapshot"]["sha256"] == snapshot["sqlite_database_snapshot"]["sha256"]


def test_snapshot_compare_and_restore_round_trip(tmp_path):
    output = tmp_path / "output"
    db = tmp_path / "active.rpx"
    _make_db(db, "original")
    snapshot = write_build_snapshot(output, build_id="b2", sqlite_db_path=db, output_files=[])
    _make_db(db, "changed")

    compare = compare_snapshot_to_current(snapshot, sqlite_db_path=db)
    assert compare["schema"] == "plan_snapshot_compare_v1"
    assert compare["database_matches"] is False

    restored = restore_sqlite_database_from_snapshot(output / SNAPSHOT_FILENAME, db, backup_suffix="test")
    assert restored["success"] is True
    assert restored["schema"] == "plan_snapshot_restore_v1"
    assert Path(restored["backup_database"]).exists()
    assert _read_value(db) == "original"
