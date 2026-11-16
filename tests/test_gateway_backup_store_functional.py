"""Encrypted backups of real fixture users: write, verify, retention, restore one user, failure modes."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.gateway import backup_crypto as bc
from src.gateway import backup_store as bs

pytestmark = pytest.mark.integration

T0 = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()


class Clock:
    def __init__(self, now: float = T0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _db(path: Path, value: str, wal: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    try:
        if wal:
            con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
        con.execute("DELETE FROM t")
        con.execute("INSERT INTO t VALUES (?)", (value,))
        con.commit()
    finally:
        con.close()


def _val(path: Path) -> str:
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute("SELECT v FROM t").fetchone()[0]
    finally:
        con.close()


@pytest.fixture()
def server(tmp_path):
    data, gw = tmp_path / "data", tmp_path / "state" / "gateway.db"
    for uid in (1, 2, 3):
        _db(data / "users" / str(uid) / "plan.rpx", f"plan{uid}-v1", wal=(uid == 2))
        _db(data / "users" / str(uid) / "local_state" / "app.db", f"app{uid}-v1")
    _db(gw, "gateway-v1")
    return {"data": data, "gw": gw, "dest": tmp_path / "bk", "key": bc.generate_key(), "tmp": tmp_path}


def _sched(server, clock=None, **kw):
    return bs.EncryptedBackupScheduler(
        data_root=server["data"], gateway_db=server["gw"], dest=server["dest"], master=server["key"],
        user_ids=lambda: [1, 2, 3], clock=clock or Clock(), **kw)


def test_archive_is_one_encrypted_file_with_no_plaintext_and_a_manifest(server):
    path = _sched(server).run_once()
    assert path.name == "20261101T120000Z.rpbak"
    blob = path.read_bytes()
    assert b"SQLite format 3" not in blob and b"plan1-v1" not in blob and b"gateway-v1" not in blob
    assert sorted(p.name for p in server["dest"].iterdir()) == [path.name]  # no staging or partial leftovers
    manifest = bs.verify_archive(path, server["key"])
    assert manifest["users"] == [1, 2, 3] and "gateway.db" in manifest["members"] and manifest["errors"] == []


def test_wrong_key_and_corruption_fail_loudly_and_change_nothing(server):
    path = _sched(server).run_once()
    with pytest.raises(bc.WrongKeyError):
        bs.verify_archive(path, bc.generate_key())
    before = (server["data"] / "users" / "1" / "plan.rpx").read_bytes()
    bad = bytearray(path.read_bytes())
    bad[len(bad) // 2] ^= 0xFF
    broken = path.with_name("20261101T130000Z.rpbak")
    broken.write_bytes(bytes(bad))
    with pytest.raises(bc.CorruptBackupError):
        bs.verify_archive(broken, server["key"])
    with pytest.raises(bc.CorruptBackupError):
        bs.restore_user(broken, server["key"], data_root=server["data"], user_id=1)
    with pytest.raises(bc.WrongKeyError):
        bs.restore_user(path, bc.generate_key(), data_root=server["data"], user_id=1)
    assert (server["data"] / "users" / "1" / "plan.rpx").read_bytes() == before
    cut = path.with_name("20261101T140000Z.rpbak")
    cut.write_bytes(path.read_bytes()[:-30])
    with pytest.raises(bc.CorruptBackupError):
        bs.verify_archive(cut, server["key"])
    assert not any(p.name.startswith(".restore") for p in (server["data"] / "users").iterdir())


def test_restore_one_user_leaves_every_other_user_byte_identical(server):
    path = _sched(server).run_once()
    users = server["data"] / "users"
    _db(users / "2" / "plan.rpx", "plan2-DAMAGED")
    _db(users / "2" / "local_state" / "app.db", "app2-DAMAGED")
    _db(users / "1" / "plan.rpx", "plan1-v2-newer")
    others = {p: p.read_bytes() for uid in (1, 3) for p in (users / str(uid)).rglob("*") if p.is_file()}
    stamps = {p: p.stat().st_mtime_ns for p in others}
    rep = bs.restore_user(path, server["key"], data_root=server["data"], user_id=2, stamp="t1")
    assert rep["restored"] == ["plan.rpx", "local_state/app.db"]
    assert _val(users / "2" / "plan.rpx") == "plan2-v1" and _val(users / "2" / "local_state" / "app.db") == "app2-v1"
    assert {p: p.read_bytes() for p in others} == others
    assert {p: p.stat().st_mtime_ns for p in others} == stamps
    assert _val(users / "2" / "plan.rpx.before-restore-t1") == "plan2-DAMAGED"  # the damaged copy is kept
    assert not list(users.glob(".restore-*"))


def test_restore_refuses_unknown_user_and_a_running_worker(server, monkeypatch):
    path = _sched(server).run_once()
    with pytest.raises(bs.RestoreError, match="no files for user 9"):
        bs.restore_user(path, server["key"], data_root=server["data"], user_id=9)
    port = server["data"] / "users" / "1" / "local_state" / "worker.port.json"
    port.write_text(json.dumps({"pid": os.getpid(), "port": 1}), encoding="utf-8")
    before = (server["data"] / "users" / "1" / "plan.rpx").read_bytes()
    with pytest.raises(bs.RestoreError, match="running"):
        bs.restore_user(path, server["key"], data_root=server["data"], user_id=1)
    assert (server["data"] / "users" / "1" / "plan.rpx").read_bytes() == before


def test_a_failed_swap_puts_the_users_files_back(server, monkeypatch):
    path = _sched(server).run_once()
    users = server["data"] / "users"
    _db(users / "1" / "plan.rpx", "plan1-current")
    real = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if ".restore-" in str(src) and str(src).endswith("app.db"):
            raise OSError("disk full")
        return real(src, dst)

    monkeypatch.setattr(bs.os, "replace", flaky)
    with pytest.raises(OSError):
        bs.restore_user(path, server["key"], data_root=server["data"], user_id=1)
    monkeypatch.setattr(bs.os, "replace", real)
    assert _val(users / "1" / "plan.rpx") == "plan1-current"
    assert _val(users / "1" / "local_state" / "app.db") == "app1-v1"


def test_gateway_db_restores_to_a_new_file_only(server):
    path = _sched(server).run_once()
    out = server["tmp"] / "gateway.restored.db"
    bs.restore_gateway_db(path, server["key"], out)
    assert _val(out) == "gateway-v1"
    with pytest.raises(bs.RestoreError, match="already exists"):
        bs.restore_gateway_db(path, server["key"], out)
    with pytest.raises(bs.RestoreError, match="already exists"):
        bs.restore_gateway_db(path, server["key"], server["gw"])


def test_retention_keeps_the_configured_count_and_user_snapshots_are_separate(server):
    clock = Clock()
    sched = _sched(server, clock, keep=3)
    for _ in range(5):
        sched.run_once()
        clock.now += 86400
    names = [a["name"] for a in bs.list_archives(server["dest"]) if a["kind"] == "full"]
    assert len(names) == 3 and names[-1].startswith("20261105")
    snap = sched.backup_user(2)
    assert snap.name.endswith(".user2.rpbak") and len(sched.complete_sets()) == 3
    assert bs.verify_archive(snap, server["key"])["users"] == [2]
    for _ in range(4):
        clock.now += 60
        sched.backup_user(2)
    assert len([a for a in bs.list_archives(server["dest"]) if a["kind"] == "user"]) == 3


def test_a_user_with_a_broken_database_is_reported_not_fatal(server):
    (server["data"] / "users" / "3" / "plan.rpx").write_bytes(b"this is not a database at all" * 20)
    sched = _sched(server)
    path = sched.run_once()
    manifest = bs.verify_archive(path, server["key"])
    assert manifest["users"] == [1, 2, 3]  # user 3 still has an app.db
    assert any("user 3 plan.rpx" in e for e in manifest["errors"])
    assert sched.last_result()["ok"] is False and sched.last_result()["errors"]


def test_a_crash_while_writing_leaves_no_finished_looking_file(server, monkeypatch):
    sched = _sched(server)
    monkeypatch.setattr(bs, "verify_archive", lambda *a, **k: (_ for _ in ()).throw(bc.CorruptBackupError("boom")))
    with pytest.raises(bc.CorruptBackupError):
        sched.run_once()
    assert list(server["dest"].iterdir()) == []
    assert sched.last_result()["ok"] is False


def test_backup_taken_while_a_worker_writes_is_consistent(server):
    users = server["data"] / "users"
    con = sqlite3.connect(str(users / "2" / "plan.rpx"))
    con.execute("BEGIN")
    con.execute("UPDATE t SET v = 'uncommitted'")
    path = _sched(server).run_once()
    con.rollback()
    con.close()
    bs.restore_user(path, server["key"], data_root=server["data"], user_id=2, stamp="t")
    assert _val(users / "2" / "plan.rpx") == "plan2-v1"
