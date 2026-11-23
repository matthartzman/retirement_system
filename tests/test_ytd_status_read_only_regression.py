"""PR-04: GET /api/ytd/status never recovers or merges account setup from sibling folders; the explicit POST does."""
from __future__ import annotations

from src.server import app
from src.server_services import ytd_service

HEADERS = {"X-User-Role": "admin"}


def test_status_payload_does_not_call_recovery(monkeypatch):
    calls = []
    monkeypatch.setattr(ytd_service.YtdService, "recover_account_setup", lambda self, **k: calls.append(k) or {"recovered": True})
    svc = ytd_service.YtdService.__new__(ytd_service.YtdService)
    svc.ytd = type("Y", (), {"status_payload": staticmethod(lambda root, period=None: {"success": True, "period": period})})()
    svc.input_root = lambda: "root"
    assert svc.status_payload(period="2026") == {"success": True, "period": "2026"}
    assert calls == []


def test_get_status_route_is_read_only_and_post_recover_is_the_explicit_path(monkeypatch):
    calls = []
    monkeypatch.setattr(ytd_service.YtdService, "recover_account_setup",
                        lambda self, **k: calls.append(k) or {"success": True, "recovered": False})
    client = app.test_client()
    assert client.get("/api/ytd/status", headers=HEADERS).status_code == 200
    assert calls == []
    assert client.post("/api/ytd/account-setup/recover", headers=HEADERS, json={"force": False}).status_code == 200
    assert calls and calls[0]["force"] is False
