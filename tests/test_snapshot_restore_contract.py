from pathlib import Path

from src.build_snapshot import (
    SNAPSHOT_DB_FILENAME,
    compare_snapshot_to_current,
    restore_sqlite_database_from_snapshot,
    make_build_snapshot,
)

import pytest

from src.stores import PlanStore

pytestmark = pytest.mark.contract


def _make_db(path: Path, value: str):
    """A plan file (``PlanStore``) holding one marker row; the snapshot is of the plan file (WP4.5)."""
    with PlanStore.open(path) as store:
        store.set_value("Marker", "", "value", value)


def _read_value(path: Path) -> str:
    with PlanStore.open(path, create=False, readonly=True) as store:
        return store.sectioned_data()["Marker"][""]["value"]


def test_build_snapshot_captures_sqlite_database_copy_and_hash(tmp_path):
    output = tmp_path / "output"
    db = tmp_path / "active.rpx"
    _make_db(db, "snapshot")
    snapshot = make_build_snapshot(output, build_id="b1", sqlite_db_path=db, summary={"ok": True}, output_files=[])

    assert snapshot["sqlite_database"]["sha256"]
    assert snapshot["sqlite_database_snapshot"]["file"] == SNAPSHOT_DB_FILENAME
    assert Path(snapshot["sqlite_database_snapshot"]["path"]).exists()
    assert {a["file"] for a in snapshot["artifacts"]} >= {"build_results.summary_json", "build_results.explorer_json"}


def test_snapshot_compare_and_restore_round_trip(tmp_path):
    output = tmp_path / "output"
    db = tmp_path / "active.rpx"
    _make_db(db, "original")
    snapshot = make_build_snapshot(output, build_id="b2", sqlite_db_path=db, output_files=[])
    _make_db(db, "changed")

    compare = compare_snapshot_to_current(snapshot, sqlite_db_path=db)
    assert compare["schema"] == "plan_snapshot_compare_v1"
    assert compare["database_matches"] is False

    restored = restore_sqlite_database_from_snapshot(snapshot, db, output_dir=output, backup_suffix="test")
    assert restored["success"] is True
    assert restored["schema"] == "plan_snapshot_restore_v1"
    assert Path(restored["backup_database"]).exists()
    assert _read_value(db) == "original"
