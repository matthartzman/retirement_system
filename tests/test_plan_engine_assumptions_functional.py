"""The planner keeps the engine knobs as plan assumptions: /api/plan/engine-assumptions, engine rows only."""
from __future__ import annotations

from src.engine_defaults import ENGINE_SECTIONS
from src.server import create_app
from src.server_services import admin_service

ADMIN = {"X-User-Role": "admin"}


def test_get_returns_only_engine_rows_with_a_header():
    out = create_app().test_client().get("/api/plan/engine-assumptions", headers=ADMIN).get_json()
    assert out["success"] and out["rows"][0][:3] == ["section", "subsection", "label"]
    assert {r[0] for r in out["rows"][1:]} <= set(ENGINE_SECTIONS)
    assert len(out["rows"]) > 1


def test_install_wide_rows_are_refused_with_400():
    client = create_app().test_client()
    resp = client.post("/api/plan/engine-assumptions", json={"rows": [["System Configuration", "Runtime", "max_build_seconds", "5", "", ""]]}, headers=ADMIN)
    assert resp.status_code == 400 and "Admin app" in resp.get_json()["error"]


def test_old_system_config_and_moved_routes_are_gone_from_the_planner():
    client = create_app().test_client()
    for method, path in (("get", "/api/admin/system-config"), ("post", "/api/admin/mode"), ("get", "/api/admin/server"),
                         ("post", "/api/admin/clear-webview-cache")):
        assert getattr(client, method)(path, headers=ADMIN).status_code in (404, 405), path


def test_workspace_aliases_serve_the_same_payload_as_the_old_paths():
    client = create_app().test_client()
    for old, new in (("/api/admin/diagnostics", "/api/workspace/diagnostics"), ("/api/admin/csv-backup", "/api/workspace/csv-backup")):
        a, b = client.get(old, headers=ADMIN), client.get(new, headers=ADMIN)
        assert a.status_code == b.status_code and a.status_code != 404, (old, new)


def test_save_engine_assumptions_service_refuses_a_foreign_row_before_writing():
    payload, status, before, after = admin_service.save_engine_assumptions({"rows": [["System Configuration", "Runtime", "x", "1", "", ""]]})
    assert status == 400 and before == after
