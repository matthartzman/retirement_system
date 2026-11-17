"""Remote-mode routes that manage several plans: create, duplicate, rename, delete, download by id, limits."""
from __future__ import annotations

import base64

import pytest

from src import plan_limits, plan_registry, platform_runtime, remote_mode
from src.server import app_core, create_app, remote_allowlist

TOKEN = "test-worker-token-0123456789"


@pytest.fixture(autouse=True)
def _live_workspace_constant(monkeypatch):
    from src.server import base_routes, plan_routes, workbook_routes

    live = platform_runtime.workspace_root()
    for module in (app_core, base_routes, plan_routes, workbook_routes):
        monkeypatch.setattr(module, "WORKSPACE_ROOT", live, raising=False)
    monkeypatch.delenv(plan_limits.MAX_PLANS_ENV, raising=False)
    monkeypatch.delenv(plan_limits.QUOTA_ENV, raising=False)
    plan_limits.invalidate()
    plan_registry.invalidate()


@pytest.fixture
def remote(monkeypatch):
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    monkeypatch.setenv(remote_mode.TOKEN_ENV, TOKEN)
    return create_app().test_client()


def _h():
    return {"X-API-Token": TOKEN}


def _post(client, path, body):
    resp = client.post(path, json=body, headers=_h())
    return resp.status_code, resp.get_json()


def _cleanup(client, *ids):
    active = plan_registry.active_record()["plan_id"]
    keep = next(p for p in plan_registry.list_plans() if p["kind"] != "demo" and p["plan_id"] not in ids)
    plan_registry.activate(keep["plan_id"], check=False)
    for pid in ids:
        try:
            rec = plan_registry.get_plan(pid)
        except plan_registry.PlanRegistryError:
            continue
        plan_registry.forget(pid)
        __import__("pathlib").Path(rec["path"]).unlink(missing_ok=True)
    return active


def test_new_routes_are_allowed_and_forget_is_refused():
    for rule in ("/api/plans/create", "/api/plans/duplicate", "/api/plans/delete"):
        assert ("POST", rule) in remote_allowlist.ALLOWED
    assert ("POST", "/api/plans/forget") not in remote_allowlist.ALLOWED
    assert "quota" in remote_allowlist.REFUSED[("POST", "/api/plans/forget")]


def test_create_activates_the_new_plan_and_reports_limits(remote):
    status, body = _post(remote, "/api/plans/create", {"name": "What if", "from": "demo"})
    try:
        assert status == 200 and body["success"] is True, body
        new = body["plan"]
        assert body["active"]["plan_id"] == new["plan_id"] and new["name"] == "What if"
        assert set(body["limits"]) >= {"max_plans", "plan_count", "disk_quota_mb", "disk_used_mb"}
        assert str(platform_runtime.workspace_root()) not in str(body)  # no server paths in the reply
    finally:
        _cleanup(remote, new["plan_id"])


def test_get_plans_includes_limits_and_no_paths(remote):
    body = remote.get("/api/plans", headers=_h()).get_json()
    assert body["success"] and "limits" in body
    assert all("path" not in p for p in body["plans"])


def test_duplicate_keeps_the_current_plan_active(remote):
    before = plan_registry.active_record()["plan_id"]
    status, body = _post(remote, "/api/plans/duplicate", {"plan_id": before, "name": "Copy A"})
    try:
        assert status == 200, body
        assert body["active"]["plan_id"] == before and body["plan"]["name"] == "Copy A"
    finally:
        _cleanup(remote, body["plan"]["plan_id"])


def test_rename_and_delete_with_typed_name(remote):
    _, made = _post(remote, "/api/plans/create", {"name": "Temp", "from": "blank"})
    pid = made["plan"]["plan_id"]
    try:
        status, body = _post(remote, "/api/plans/rename", {"plan_id": pid, "name": "Temp two"})
        assert status == 200 and any(p["name"] == "Temp two" for p in body["plans"])
        base = next(p for p in plan_registry.list_plans() if p["plan_id"] != pid and p["kind"] != "demo")
        _post(remote, "/api/plans/switch", {"plan_id": base["plan_id"]})
        status, body = _post(remote, "/api/plans/delete", {"plan_id": pid, "confirm_name": "nope"})
        assert status == 400 and body["success"] is False
        status, body = _post(remote, "/api/plans/delete", {"plan_id": pid, "confirm_name": "Temp two"})
        assert status == 200 and pid not in [p["plan_id"] for p in body["plans"]]
    finally:
        _cleanup(remote, pid)


@pytest.mark.parametrize("path", ["/api/plans/duplicate", "/api/plans/rename", "/api/plans/delete", "/api/plans/switch"])
@pytest.mark.parametrize("bad", ["0" * 32, "../x", "CON", "", "x" * 99])
def test_unknown_or_crafted_ids_get_one_error(remote, path, bad):
    status, body = _post(remote, path, {"plan_id": bad, "name": "n", "confirm_name": "n"})
    assert status == 400 and body["success"] is False
    assert str(platform_runtime.workspace_root()) not in str(body)


def test_limits_answer_409_and_change_nothing(remote, monkeypatch):
    monkeypatch.setenv(plan_limits.MAX_PLANS_ENV, str(len([p for p in plan_registry.list_plans() if p["kind"] != "demo"])))
    before = [p["plan_id"] for p in plan_registry.list_plans()]
    status, body = _post(remote, "/api/plans/create", {"name": "Over", "from": "blank"})
    assert status == 409 and "limit" in body["error"]
    status, _ = _post(remote, "/api/plans/duplicate", {"plan_id": before[0]})
    assert status == 409
    content = remote.get("/api/plan/download", headers=_h()).get_data()
    status, _ = _post(remote, "/api/plan/upload", {"filename": "x.rpx", "content_base64": base64.b64encode(content).decode()})
    assert status == 409
    assert [p["plan_id"] for p in plan_registry.list_plans()] == before


def test_build_start_is_refused_when_over_quota(remote, monkeypatch):
    monkeypatch.setenv(plan_limits.QUOTA_ENV, "1")
    monkeypatch.setattr(plan_limits, "disk_used_bytes", lambda: 5 * 1024 * 1024)
    status, body = _post(remote, "/api/build/start", {})
    assert status == 409 and "disk" in body["error"]


def test_download_by_plan_id_and_uniform_error(remote):
    _, made = _post(remote, "/api/plans/create", {"name": "Dl", "from": "demo"})
    pid = made["plan"]["plan_id"]
    try:
        other = plan_registry.active_record()["plan_id"]
        assert other == pid  # create activated it; ask for another plan by id
        base = next(p for p in plan_registry.list_plans() if p["plan_id"] != pid and p["kind"] != "demo")
        ok = remote.get(f"/api/plan/download?plan_id={base['plan_id']}", headers=_h())
        assert ok.status_code == 200 and ok.get_data()[:16] == b"SQLite format 3\x00"
        for bad in ("0" * 32, "../x", "CON"):
            resp = remote.get(f"/api/plan/download?plan_id={bad}", headers=_h())
            assert resp.status_code == 404 and resp.get_json()["success"] is False
    finally:
        _cleanup(remote, pid)
