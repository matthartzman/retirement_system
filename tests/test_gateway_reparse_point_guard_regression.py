"""A user can create a directory junction inside their own workspace without any privilege. The gateway's own
privileged jobs (backup, restore, migrate, log housekeeping) must never follow one into another user's folder."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from src.gateway import backup_crypto as bc
from src.gateway import backup_store as bs
from src.gateway import fsguard, logs

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.name != "nt", reason="directory junctions are Windows")]


def _db(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
    con.execute("DELETE FROM t")
    con.execute("INSERT INTO t VALUES (?)", (value,))
    con.commit()
    con.close()


def _junction(link: Path, target: Path) -> None:
    import _winapi  # noqa: PLC0415

    _winapi.CreateJunction(str(target), str(link))


@pytest.fixture()
def tree(tmp_path):
    root = tmp_path / "data"
    for uid in (1, 2):
        (root / "users" / str(uid)).mkdir(parents=True)
        (root / "users" / str(uid) / "plan.rpx").write_bytes(b"plan-%d" % uid)
        _db(root / "users" / str(uid) / "local_state" / "app.db", f"secret-of-{uid}")
    return root


def test_guard_detects_a_junction_anywhere_under_the_root(tree):
    u1 = tree / "users" / "1"
    assert not fsguard.has_reparse_point(u1 / "plan.rpx", u1)
    (u1 / "local_state" / "app.db").unlink()
    (u1 / "local_state").rmdir()
    _junction(u1 / "local_state", tree / "users" / "2" / "local_state")
    assert fsguard.has_reparse_point(u1 / "local_state" / "app.db", u1)


def test_backup_does_not_archive_another_users_database_through_a_junction(tree, tmp_path):
    u1 = tree / "users" / "1"
    (u1 / "local_state" / "app.db").unlink()
    (u1 / "local_state").rmdir()
    _junction(u1 / "local_state", tree / "users" / "2" / "local_state")
    master = bc.generate_key()
    dest = tmp_path / "set.rpbak"
    _path, report = bs.write_archive(dest, master, data_root=tree, user_ids=[1, 2], gateway_db=None, now=1.0)
    assert "users/1/app.db" not in report["members"], report
    assert "users/2/app.db" in report["members"]
    assert any("user 1" in e for e in report["errors"]), report


def test_log_trim_skips_a_linked_log(tree, tmp_path):
    u1 = tree / "users" / "1"
    victim = tree / "elsewhere"  # not a users/<id> folder, so only a followed link could reach it
    other = victim / "logs"
    other.mkdir(parents=True)
    (other / "worker_console.log").write_bytes(b"x" * 100)
    (u1 / "local_state" / "app.db").unlink()
    (u1 / "local_state").rmdir()
    _junction(u1 / "local_state", victim)
    out = logs.prune_worker_logs(tree, lambda _uid: False, max_bytes=10)
    assert (other / "worker_console.log").read_bytes() == b"x" * 100
    assert out["trimmed"] == 0
