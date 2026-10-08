"""WI-201 (ARC-005/QA-004) and WI-202 (ARC-008) regression tests."""
from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from src import plan_file_io
from src.build_snapshot import (
    SNAPSHOT_DB_FILENAME,
    SNAPSHOT_FILENAME,
    restore_sqlite_database_from_snapshot,
    write_build_snapshot,
)
from src.plan_db_replace import replace_active_db
from src.server_services.plan_file_service import PlanFileService, PlanFileServiceContext
from src.stores import PlanStore

ROOT = Path(__file__).resolve().parent.parent


def _make_db(path: Path, marker: str, *, wal: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS client_files(file_name TEXT PRIMARY KEY, content TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS marker(value TEXT)")
    conn.execute("DELETE FROM marker")
    conn.execute("INSERT INTO marker(value) VALUES (?)", (marker,))
    conn.commit()
    if wal:
        return conn  # caller keeps it open
    conn.close()
    return None


def _marker(path: Path) -> str:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute("SELECT value FROM marker").fetchone()[0]
    finally:
        conn.close()


def _make_plan(path: Path, marker: str) -> None:
    """A plan file (``PlanStore``) with one marker row: the file Load / restore operate on (WP4.5)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with PlanStore.open(path) as store:
        store.set_value("Marker", "", "value", marker)


def _plan_marker(path: Path) -> str:
    with PlanStore.open(path, create=False, readonly=True) as store:
        return store.sectioned_data()["Marker"][""]["value"]


def _service(active: Path, migrate=None) -> PlanFileService:
    return PlanFileService(PlanFileServiceContext(
        sqlite_db=lambda: active.parent / "legacy.db", plan_db=lambda: active, audit=lambda e, p: None, migrate=migrate))


def test_load_non_sqlite_file_errors_and_leaves_active_db_unchanged(tmp_path):
    active = tmp_path / "state" / "plan.rpx"
    _make_plan(active, "active")
    junk = tmp_path / "junk.rpx"
    junk.write_text("definitely not sqlite", encoding="utf-8")

    result = _service(active).load_file({"path": str(junk)})

    assert result["success"] is False
    assert "not a SQLite" in result["error"]
    assert _plan_marker(active) == "active"
    assert not list(active.parent.glob("*.incoming"))
    assert not list(active.parent.glob("*before_load*"))


def test_load_sqlite_file_without_plan_tables_is_rejected(tmp_path):
    active = tmp_path / "plan.rpx"
    _make_plan(active, "active")
    other = tmp_path / "other.db"
    conn = sqlite3.connect(str(other))
    conn.execute("CREATE TABLE unrelated(x)")
    conn.commit()
    conn.close()
    legacy = tmp_path / "legacy_copy.db"  # the legacy local database is not a plan file
    _make_db(legacy, "legacy")

    for bad in (other, legacy):
        result = _service(active).load_file({"path": str(bad)})
        assert result["success"] is False and "plan_rows" in result["error"]
    assert _plan_marker(active) == "active"


def test_load_valid_plan_replaces_backs_up_and_runs_migration(tmp_path):
    active = tmp_path / "plan.rpx"
    _make_plan(active, "old")
    src = tmp_path / "saved.rpx"
    _make_plan(src, "new")
    seen = []

    result = _service(active, migrate=lambda p: seen.append(Path(p))).load_file({"path": str(src)})

    assert result["success"] is True and result["backup"] and result["backup"].startswith("plan.rpx.before_load_")
    assert _plan_marker(active) == "new"
    assert _plan_marker(active.parent / result["backup"]) == "old"
    assert seen == [active]


def test_busy_checkpoint_aborts_without_changes(tmp_path):
    active = tmp_path / "active.db"
    holder = _make_db(active, "old", wal=True)
    reader = sqlite3.connect(str(active))
    reader.execute("BEGIN")
    reader.execute("SELECT * FROM marker").fetchall()
    # A commit after the reader's snapshot means TRUNCATE cannot complete.
    holder.execute("INSERT INTO marker(value) VALUES ('later')")
    holder.commit()
    src = tmp_path / "saved.rpx"
    _make_db(src, "new")
    try:
        result = replace_active_db(src, active, backup_path=tmp_path / "bak")
    finally:
        reader.close()
        holder.close()
    assert result["success"] is False and "busy" in result["error"]
    assert not (tmp_path / "bak").exists()
    assert _marker(active) != "new"


def test_restore_leaves_no_stale_wal_and_uses_shared_validation(tmp_path):
    output = tmp_path / "output"
    active = tmp_path / "plan.rpx"
    src = tmp_path / "src.rpx"
    _make_plan(src, "snapshot")
    write_build_snapshot(output, build_id="b", sqlite_db_path=src, output_files=[])
    _make_plan(active, "active")
    Path(str(active) + "-wal").write_bytes(b"stale-wal-frames")
    Path(str(active) + "-shm").write_bytes(b"stale-shm")

    restored = restore_sqlite_database_from_snapshot(output / SNAPSHOT_FILENAME, active, backup_suffix="t")

    assert restored["success"] is True
    assert not Path(str(active) + "-wal").exists()
    assert not Path(str(active) + "-shm").exists()
    assert _plan_marker(active) == "snapshot"
    assert _plan_marker(Path(restored["backup_database"])) == "active"


def test_restore_rejects_snapshot_db_that_is_not_a_plan_db(tmp_path):
    output = tmp_path / "output"
    src = tmp_path / "src.rpx"
    _make_plan(src, "snapshot")
    snapshot = write_build_snapshot(output, build_id="b", sqlite_db_path=src, output_files=[])
    # Corrupt the copy but keep the recorded hash matching so only the shared
    # validation (not the sha256 check) can catch it.
    copy = Path(snapshot["sqlite_database_snapshot"]["path"])
    assert copy.name == SNAPSHOT_DB_FILENAME
    copy.write_bytes(b"garbage")
    import json
    from src.build_snapshot import sha256_file

    snap_file = output / SNAPSHOT_FILENAME
    data = json.loads(snap_file.read_text(encoding="utf-8"))
    data["sqlite_database_snapshot"]["sha256"] = sha256_file(copy)
    snap_file.write_text(json.dumps(data), encoding="utf-8")
    active = tmp_path / "plan.rpx"
    _make_plan(active, "active")

    restored = restore_sqlite_database_from_snapshot(snap_file, active)

    assert restored["success"] is False
    assert _plan_marker(active) == "active"


# ----- WI-202 -----------------------------------------------------------------

def _boom(*_a, **_k):
    raise OSError("simulated crash mid-write")


def test_failed_dataset_save_keeps_original_holdings(tmp_path, monkeypatch):
    """The flat datasets are plan file tables (WP6): a save that fails part way rolls back."""
    from src.active_plan import PLAN_DB_ENV
    from src.server_services import holdings_service
    from src.stores import datasets

    plan = tmp_path / "plan.rpx"
    monkeypatch.setenv(PLAN_DB_ENV, str(plan))
    kw = dict(base_dir=tmp_path, workspace_id="local", client_id="local", user_id="u", db_path=tmp_path / "x.db")
    holdings_service.save_holdings(content="account,symbol,shares\nA,VTI,1\n", **kw)
    original = holdings_service.read_holdings(base_dir=tmp_path, workspace_id="local", client_id="local", db_path=tmp_path / "x.db")["content"]

    def boom(self, rows):
        raise OSError("simulated crash mid-write")

    monkeypatch.setattr(datasets.FlatDatasetRepository, "_clean", boom)
    for fn in (holdings_service.save_holdings, holdings_service.save_liabilities, holdings_service.save_hsa_schedule):
        with pytest.raises(OSError):
            fn(content="account,symbol,year\nB,X,2030\n", **kw)
    monkeypatch.undo()
    monkeypatch.setenv(PLAN_DB_ENV, str(plan))
    assert holdings_service.read_holdings(base_dir=tmp_path, workspace_id="local", client_id="local", db_path=tmp_path / "x.db")["content"] == original


def test_secrets_store_failed_save_keeps_existing_keys(tmp_path, monkeypatch):
    from src import secrets_store

    path = tmp_path / "secrets.local.json"
    secrets_store._save({"k": "v"}, path)
    monkeypatch.setattr(plan_file_io.os, "replace", _boom)
    with pytest.raises(OSError):
        secrets_store._save({"k": "changed", "j": "w"}, path)
    assert secrets_store._load(path) == {"k": "v"}


def _bare_write_calls(path: Path, function: str | None = None) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [tree]
    if function:
        nodes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function]
        assert nodes, function
    hits = []
    for root in nodes:
        for n in ast.walk(root):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in {"write_text", "write_bytes"}:
                hits.append(n.lineno)
    return hits


@pytest.mark.parametrize("rel,func", [
    ("src/server_services/holdings_service.py", None),
    ("src/secrets_store.py", None),
    ("src/plan_data_migration.py", None),
])
def test_primary_user_data_writers_have_no_bare_write_text(rel, func):
    assert _bare_write_calls(ROOT / rel, func) == [], f"{rel} still uses a bare write_text/write_bytes"
