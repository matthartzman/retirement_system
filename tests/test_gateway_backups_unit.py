"""BackupScheduler: set layout, consistency, retention, partial sets, errors."""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.gateway.backups import BackupScheduler

pytestmark = pytest.mark.unit

T0 = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()


class FakeClock:
    def __init__(self, now: float = T0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _make_db(path: Path, value: str = "hello", wal: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    try:
        if wal:
            con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE t (v TEXT)")
        con.execute("INSERT INTO t VALUES (?)", (value,))
        con.commit()
    finally:
        con.close()


def _values(path: Path) -> list[str]:
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return [r[0] for r in con.execute("SELECT v FROM t ORDER BY rowid")]
    finally:
        con.close()


def _setup(tmp_path: Path, users=(1, 2), with_gateway=True):
    data = tmp_path / "data"
    for uid in users:
        _make_db(data / "users" / str(uid) / "plan.rpx", f"plan{uid}")
        _make_db(data / "users" / str(uid) / "local_state" / "app.db", f"app{uid}")
    gw = tmp_path / "gateway.db"
    if with_gateway:
        _make_db(gw, "gw")
    return data, gw


def _scheduler(tmp_path, clock, users=(1, 2), **kw):
    data, gw = _setup(tmp_path, users)
    return BackupScheduler(
        data_root=data,
        gateway_db=gw,
        dest=tmp_path / "backups",
        user_ids=lambda: list(users),
        clock=clock,
        **kw,
    )


def test_set_layout_and_contents(tmp_path):
    clock = FakeClock()
    sched = _scheduler(tmp_path, clock)
    folder = sched.run_once()
    assert folder.name == "20261101T120000Z"
    assert _values(folder / "users" / "1" / "plan.rpx") == ["plan1"]
    assert _values(folder / "users" / "2" / "app.db") == ["app2"]
    assert _values(folder / "gateway.db") == ["gw"]
    assert not list((tmp_path / "backups").glob("*.partial"))
    result = sched.last_result()
    assert result["users"] == 2 and result["errors"] == []
    assert result["folder"] == str(folder)


def test_copy_is_consistent_while_another_connection_writes(tmp_path):
    data, gw = _setup(tmp_path, users=(1,))
    plan = data / "users" / "1" / "plan.rpx"
    plan.unlink()
    _make_db(plan, "committed", wal=True)
    writer = sqlite3.connect(str(plan), isolation_level=None)
    try:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO t VALUES ('uncommitted')")
        sched = BackupScheduler(
            data_root=data, gateway_db=None, dest=tmp_path / "b", user_ids=lambda: [1], clock=FakeClock()
        )
        folder = sched.run_once()
        assert _values(folder / "users" / "1" / "plan.rpx") == ["committed"]
        writer.execute("COMMIT")
    finally:
        writer.close()


def test_retention_keeps_newest_and_ignores_partials(tmp_path):
    clock = FakeClock()
    sched = _scheduler(tmp_path, clock, keep=2)
    made = []
    for _ in range(4):
        made.append(sched.run_once())
        clock.now += 3600
    names = sorted(p.name for p in (tmp_path / "backups").iterdir())
    assert names == [made[2].name, made[3].name]


def test_stale_partial_removed_and_fresh_partial_kept(tmp_path):
    clock = FakeClock()
    sched = _scheduler(tmp_path, clock)
    dest = tmp_path / "backups"
    stale = dest / "20261001T000000Z.partial"
    fresh = dest / "20261101T110000Z.partial"
    stale.mkdir(parents=True)
    fresh.mkdir(parents=True)
    os.utime(stale, (T0 - 3 * 86400, T0 - 3 * 86400))
    os.utime(fresh, (T0 - 60, T0 - 60))
    sched.run_once()
    assert not stale.exists()
    assert fresh.exists()
    # A partial never counts as a complete set.
    assert all(not p.name.endswith(".partial") for p in sched.complete_sets())


def test_missing_files_are_skipped(tmp_path):
    data, _gw = _setup(tmp_path, users=(1,))
    (data / "users" / "1" / "local_state" / "app.db").unlink()
    sched = BackupScheduler(
        data_root=data, gateway_db=None, dest=tmp_path / "b", user_ids=lambda: [1, 7], clock=FakeClock()
    )
    folder = sched.run_once()
    assert (folder / "users" / "1" / "plan.rpx").is_file()
    assert not (folder / "users" / "1" / "app.db").exists()
    assert not (folder / "gateway.db").exists()
    assert sched.last_result()["errors"] == []


def test_errors_collected_without_stopping_other_users(tmp_path):
    data, gw = _setup(tmp_path, users=(1, 2))
    bad = data / "users" / "1" / "plan.rpx"
    bad.unlink()
    bad.write_bytes(b"this is not a sqlite database at all" * 20)
    sched = BackupScheduler(
        data_root=data, gateway_db=gw, dest=tmp_path / "b", user_ids=lambda: [1, 2], clock=FakeClock()
    )
    folder = sched.run_once()
    result = sched.last_result()
    assert len(result["errors"]) == 1
    assert result["errors"][0].startswith("user 1")
    assert "not a sqlite" not in result["errors"][0]
    assert result["users"] == 1
    assert _values(folder / "users" / "2" / "plan.rpx") == ["plan2"]
    assert _values(folder / "gateway.db") == ["gw"]


def test_user_ids_failure_is_reported(tmp_path):
    def boom():
        raise RuntimeError("store down")

    sched = BackupScheduler(
        data_root=tmp_path, gateway_db=None, dest=tmp_path / "b", user_ids=boom, clock=FakeClock()
    )
    sched.run_once()
    assert sched.last_result()["errors"]


def test_backup_user_into_fresh_set_and_into_folder(tmp_path):
    clock = FakeClock()
    sched = _scheduler(tmp_path, clock)
    folder = sched.backup_user(2)
    assert _values(folder / "users" / "2" / "plan.rpx") == ["plan2"]
    assert not (folder / "users" / "1").exists()
    target = tmp_path / "elsewhere"
    assert sched.backup_user(1, into=target) == target
    assert _values(target / "users" / "1" / "app.db") == ["app1"]


def test_secure_dir_called_once(tmp_path):
    calls = []
    clock = FakeClock()
    sched = _scheduler(tmp_path, clock, secure_dir=calls.append)
    sched.run_once()
    clock.now += 10
    sched.run_once()
    assert calls == [tmp_path / "backups"]


def test_same_second_sets_do_not_collide(tmp_path):
    sched = _scheduler(tmp_path, FakeClock())
    a = sched.run_once()
    b = sched.run_once()
    assert a != b and a.is_dir() and b.is_dir()


def test_start_skips_when_recent_set_exists_then_stop(tmp_path):
    sched = _scheduler(tmp_path, time.time, interval_seconds=3600)
    first = sched.run_once()
    sched.start()
    time.sleep(0.4)
    sched.stop()
    assert sched.complete_sets() == [first]


def test_start_runs_when_no_set_exists(tmp_path):
    sched = _scheduler(tmp_path, time.time, interval_seconds=3600)
    sched.start()
    try:
        deadline = time.time() + 10
        while time.time() < deadline and not sched.complete_sets():
            time.sleep(0.05)
    finally:
        sched.stop()
    assert len(sched.complete_sets()) == 1
