"""Remote mode: a build snapshot inside an uploaded plan file cannot name a plan file outside the workspace."""
from __future__ import annotations

import sqlite3

from src import build_snapshot


def _plan(path, marker: str) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t(v TEXT)")
    con.execute("INSERT INTO t VALUES (?)", (marker,))
    con.commit()
    con.close()


def test_snapshot_path_outside_the_workspace_is_refused_in_remote_mode(tmp_path, monkeypatch):
    workspace, other = tmp_path / "ws", tmp_path / "otheruser"
    workspace.mkdir()
    other.mkdir()
    monkeypatch.setenv("RETIREMENT_SYSTEM_REMOTE_MODE", "1")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(workspace))
    victim = other / "plan.rpx"
    _plan(victim, "OTHER USERS DATA")
    active = workspace / "plan.rpx"
    _plan(active, "mine")
    snapshot = {"schema": build_snapshot.SNAPSHOT_SCHEMA, "build_id": "b1",
                "sqlite_database_snapshot": {"path": str(victim), "sha256": ""}}
    for path in (str(victim), r"..\otheruser\plan.rpx"):
        snapshot["sqlite_database_snapshot"]["path"] = path
        out = build_snapshot.restore_sqlite_database_from_snapshot(snapshot, active, output_dir=workspace / "output")
        assert out["success"] is False, out
        assert str(other) not in repr(out)  # the refusal does not echo the path either
    con = sqlite3.connect(active)
    assert con.execute("SELECT v FROM t").fetchall() == [("mine",)]
    con.close()
