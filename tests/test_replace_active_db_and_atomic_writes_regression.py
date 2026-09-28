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


def _service(active: Path, migrate=None) -> PlanFileService:
    return PlanFileService(PlanFileServiceContext(sqlite_db=lambda: active, audit=lambda e, p: None, migrate=migrate))


def test_load_non_sqlite_file_errors_and_leaves_active_db_unchanged(tmp_path):
    active = tmp_path / "state" / "retirement_system_v10.db"
    _make_db(active, "active")
    junk = tmp_path / "junk.rpx"
    junk.write_text("definitely not sqlite", encoding="utf-8")

    result = _service(active).load_file({"path": str(junk)})

    assert result["success"] is False
    assert "not a SQLite" in result["error"]
    assert _marker(active) == "active"
    assert not list(active.parent.glob("*.incoming"))
    assert not list(active.parent.glob("*before_load*"))


def test_load_sqlite_file_without_plan_tables_is_rejected(tmp_path):
    active = tmp_path / "active.db"
    _make_db(active, "active")
    other = tmp_path / "other.db"
    conn = sqlite3.connect(str(other))
    conn.execute("CREATE TABLE unrelated(x)")
    conn.commit()
    conn.close()

    result = _service(active).load_file({"path": str(other)})

    assert result["success"] is False and "client_files" in result["error"]
    assert _marker(active) == "active"


def test_load_valid_plan_replaces_backs_up_and_runs_migration(tmp_path):
    active = tmp_path / "active.db"
    _make_db(active, "old")
    src = tmp_path / "saved.rpx"
    _make_db(src, "new")
    seen = []

    result = _service(active, migrate=lambda p: seen.append(Path(p))).load_file({"path": str(src)})

    assert result["success"] is True and result["backup"]
    assert _marker(active) == "new"
    assert _marker(active.parent / result["backup"]) == "old"
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
    active = tmp_path / "active.db"
    src = tmp_path / "src.db"
    _make_db(src, "snapshot")
    write_build_snapshot(output, build_id="b", sqlite_db_path=src, output_files=[])
    _make_db(active, "active")
    Path(str(active) + "-wal").write_bytes(b"stale-wal-frames")
    Path(str(active) + "-shm").write_bytes(b"stale-shm")

    restored = restore_sqlite_database_from_snapshot(output / SNAPSHOT_FILENAME, active, backup_suffix="t")

    assert restored["success"] is True
    assert not Path(str(active) + "-wal").exists()
    assert not Path(str(active) + "-shm").exists()
    assert _marker(active) == "snapshot"
    assert _marker(Path(restored["backup_database"])) == "active"


def test_restore_rejects_snapshot_db_that_is_not_a_plan_db(tmp_path):
    output = tmp_path / "output"
    src = tmp_path / "src.db"
    _make_db(src, "snapshot")
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
    active = tmp_path / "active.db"
    _make_db(active, "active")

    restored = restore_sqlite_database_from_snapshot(snap_file, active)

    assert restored["success"] is False
    assert _marker(active) == "active"


def test_plan_routes_no_longer_reports_success_when_materialize_fails():
    text = (ROOT / "src/server/plan_routes.py").read_text(encoding="utf-8")
    block = text[text.index("def plan_load_file"):text.index("# DemoPlanService owns")]
    assert 'result["success"] = False' in block
    assert "materialize_warning" in block


# ----- WI-202 -----------------------------------------------------------------

def _boom(*_a, **_k):
    raise OSError("simulated crash mid-write")


def test_atomic_write_failure_keeps_original_holdings(tmp_path, monkeypatch):
    from src.server_services import holdings_service

    target = tmp_path / "input" / "client_holdings.csv"
    target.parent.mkdir(parents=True)
    target.write_text("original\n", encoding="utf-8")
    monkeypatch.setattr(plan_file_io.os, "replace", _boom)
    monkeypatch.setattr("src.workspace_context.workspace_file", lambda *a, **k: target)
    monkeypatch.setattr("src.config_backend.set_client_file", lambda *a, **k: None)

    for fn in (holdings_service.save_holdings, holdings_service.save_liabilities, holdings_service.save_hsa_schedule):
        with pytest.raises(OSError):
            fn(content="new,content\n", base_dir=tmp_path, workspace_id="local", client_id="local", user_id="u", db_path=tmp_path / "x.db")
        assert target.read_text(encoding="utf-8") == "original\n"
    assert not list(target.parent.glob("*.tmp"))


def test_secrets_store_failed_save_keeps_existing_keys(tmp_path, monkeypatch):
    from src import secrets_store

    path = tmp_path / "secrets.local.json"
    secrets_store._save({"k": "v"}, path)
    monkeypatch.setattr(plan_file_io.os, "replace", _boom)
    with pytest.raises(OSError):
        secrets_store._save({"k": "changed", "j": "w"}, path)
    assert secrets_store._load(path) == {"k": "v"}


def test_materialize_workspace_files_failure_keeps_existing_file(tmp_path, monkeypatch):
    from src import config_backend, platform_runtime

    monkeypatch.setattr(platform_runtime, "workspace_root", lambda: tmp_path)
    db = tmp_path / "plan.db"
    config_backend.init_sqlite(db)
    config_backend.set_client_file("client_holdings.csv", "from-db\n", "local", "local", "u", db)
    dest = tmp_path / "input" / "client_holdings.csv"
    dest.parent.mkdir(parents=True)
    dest.write_text("on-disk\n", encoding="utf-8")
    monkeypatch.setattr(plan_file_io.os, "replace", _boom)
    with pytest.raises(OSError):
        config_backend.materialize_workspace_files(db_path=db, file_names=["client_holdings.csv"], overwrite_existing=True)
    assert dest.read_text(encoding="utf-8") == "on-disk\n"


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
    ("src/config_backend.py", "materialize_workspace_files"),
])
def test_primary_user_data_writers_have_no_bare_write_text(rel, func):
    assert _bare_write_calls(ROOT / rel, func) == [], f"{rel} still uses a bare write_text/write_bytes"
