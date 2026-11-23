"""PR-01 / PR-02 / PR-03 / S-04: plan-file and stored-folder routes need write_config, honour the folder allowlist
(every configured root, symlinks resolved), and Save As only writes `.rpx` files over empty or plan files."""
from __future__ import annotations

import sqlite3

import pytest

from src.server import app, plan_routes
from tests.plan_fixture import make_plan

ADMIN = {"X-User-Role": "admin"}


@pytest.fixture
def own_workspace(tmp_path, monkeypatch):
    ws = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(ws.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    return ws


def _allowlist(monkeypatch, *roots):
    monkeypatch.setattr(plan_routes, "_server_path_requires_allowlist", lambda: True)
    monkeypatch.setattr(plan_routes, "_path_roots_from_config", lambda: [r.resolve() for r in roots])


def test_allowlist_tries_every_root_and_follows_symlinks(tmp_path, monkeypatch):
    a, b, outside = tmp_path / "a", tmp_path / "b", tmp_path / "out"
    for d in (a, b, outside):
        d.mkdir()
    _allowlist(monkeypatch, a, b)
    assert plan_routes._server_path_allowed(a / "x.rpx")[0]
    assert plan_routes._server_path_allowed(b / "x.rpx")[0]  # the second root used to be ignored
    assert not plan_routes._server_path_allowed(outside / "x.rpx")[0]
    (a / "link").symlink_to(outside, target_is_directory=True)
    assert not plan_routes._server_path_allowed(a / "link" / "x.rpx")[0]  # escapes through a symlink


@pytest.mark.parametrize("route,body", [
    ("/api/plan/save-as", {"path": "x.rpx"}),
    ("/api/plan/load-file", {"path": "x.rpx"}),
    ("/api/plan/exit-snapshot", {}),
])
def test_plan_file_routes_require_write_config(own_workspace, monkeypatch, route, body):
    asked = []

    def deny(permission):  # the local user is always an advisor, so the denial itself is simulated
        asked.append(permission)
        return plan_routes.jsonify({"success": False, "error": "denied"}), 403

    monkeypatch.setattr(plan_routes, "_require", deny)
    resp = app.test_client().post(route, headers=ADMIN, json=body)
    assert resp.status_code == 403 and asked == ["write_config"]


def test_save_as_and_load_file_refuse_paths_outside_the_allowlist(own_workspace, tmp_path, monkeypatch):
    inside, outside = tmp_path / "inside", tmp_path / "outside"
    inside.mkdir()
    outside.mkdir()
    _allowlist(monkeypatch, inside)
    client = app.test_client()
    assert client.post("/api/plan/save-as", headers=ADMIN, json={"path": str(outside / "p.rpx")}).status_code == 403
    assert not (outside / "p.rpx").exists()
    (outside / "p.rpx").write_bytes(b"SQLite format 3\x00")
    assert client.post("/api/plan/load-file", headers=ADMIN, json={"path": str(outside / "p.rpx")}).status_code == 403
    ok = client.post("/api/plan/save-as", headers=ADMIN, json={"path": str(inside / "p.rpx"), "activate": False})
    assert ok.status_code == 200 and ok.get_json()["success"] is True


def test_save_as_requires_rpx_and_never_overwrites_a_non_plan_file(own_workspace, tmp_path):
    client = app.test_client()
    bad_ext = client.post("/api/plan/save-as", headers=ADMIN, json={"path": str(tmp_path / "notes.txt")}).get_json()
    assert bad_ext["success"] is False and not (tmp_path / "notes.txt").exists()
    victim = tmp_path / "victim.rpx"
    victim.write_text("important text, not a plan")
    out = client.post("/api/plan/save-as", headers=ADMIN, json={"path": str(victim)}).get_json()
    assert out["success"] is False and victim.read_text() == "important text, not a plan"
    other_db = tmp_path / "other.rpx"
    sqlite3.connect(other_db).executescript("create table t(x); insert into t values (1);")
    assert client.post("/api/plan/save-as", headers=ADMIN, json={"path": str(other_db)}).get_json()["success"] is False
    empty = tmp_path / "empty.rpx"
    empty.write_bytes(b"")
    assert client.post("/api/plan/save-as", headers=ADMIN, json={"path": str(empty), "activate": False}).get_json()["success"] is True


def test_backup_and_monarch_folders_are_checked_on_save_and_at_run_time(own_workspace, tmp_path, monkeypatch):
    inside, outside = tmp_path / "inside", tmp_path / "outside"
    inside.mkdir()
    outside.mkdir()
    client = app.test_client()
    # Saved while no allowlist applies (desktop), then the server becomes allowlisted: run time must refuse.
    assert client.post("/api/plan/backups/config", headers=ADMIN, json={"backup_dir": str(outside)}).status_code == 200
    assert client.post("/api/plan/monarch-autoupdate/config", headers=ADMIN, json={"source_dir": str(outside)}).status_code == 200
    _allowlist(monkeypatch, inside)
    assert client.post("/api/plan/backups/config", headers=ADMIN, json={"backup_dir": str(outside)}).status_code == 403
    assert client.post("/api/plan/backups/run", headers=ADMIN, json={"force": True}).status_code == 403
    assert client.post("/api/plan/monarch-autoupdate/config", headers=ADMIN, json={"source_dir": str(inside), "field_map_path": str(outside / "m.json")}).status_code == 403
    assert client.post("/api/plan/monarch-autoupdate/run", headers=ADMIN, json={}).status_code == 403
    assert client.post("/api/plan/backups/config", headers=ADMIN, json={"backup_dir": str(inside)}).status_code == 200
