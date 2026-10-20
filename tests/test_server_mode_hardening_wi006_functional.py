"""WI-006 (ARC-001/ARC-009): Host allow-list, non-loopback start guard, body cap."""
from __future__ import annotations

import io

import pytest

from src.http_runtime import host_guard
from src.http_runtime import server as http_server
from src.server import create_app
from src.server import app_core


def _client():
    return create_app().test_client()


@pytest.mark.parametrize("host,origin", [
    ("evil.example", "http://evil.example"),            # fully spoofed pair
    ("evil.example:5050", "http://evil.example:5050"),
    ("127.0.0.1:5050", "http://evil.example"),           # real Host, foreign Origin
    ("evil.example", "http://127.0.0.1:5050"),           # spoofed Host, loopback Origin
    ("127.0.0.1.evil.example", "http://127.0.0.1.evil.example"),
])
def test_spoofed_host_origin_pairs_are_rejected(host, origin):
    resp = _client().post("/api/plan/blank", json={}, headers={"Host": host, "Origin": origin})
    assert resp.status_code == 403


def test_spoofed_host_is_rejected_on_get_too():
    assert _client().get("/api/ping", headers={"Host": "evil.example"}).status_code == 403


@pytest.mark.parametrize("host", ["localhost:5050", "127.0.0.1:5050", "[::1]:5050", "localhost"])
def test_loopback_hosts_are_allowed(host):
    assert _client().get("/api/ping", headers={"Host": host}).status_code == 200


def test_configured_host_is_allowed_and_wildcard_adds_nothing():
    assert host_guard.host_allowed("plans.example:443", "plans.example")
    assert not host_guard.host_allowed("evil.example", "plans.example")
    assert not host_guard.host_allowed("evil.example", "0.0.0.0")
    assert not host_guard.host_allowed("", "127.0.0.1")


def test_desktop_bridge_is_exempt_from_transport_gate():
    app = create_app()
    app._no_http_transport = True
    try:
        resp = app.test_client().get("/api/ping", headers={"Host": "evil.example"})
        assert resp.status_code == 200
    finally:
        app._no_http_transport = False


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20", "plans.example"])
def test_non_loopback_start_refused_without_token(host, monkeypatch):
    monkeypatch.setattr(http_server, "_configured_token", lambda: "")
    with pytest.raises(host_guard.ServerStartRefused):
        http_server.run_local_server(object(), host=host, port=0)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_start_needs_no_token(host):
    host_guard.assert_safe_to_bind(host, "")


def test_non_loopback_with_token_passes_guard():
    host_guard.assert_safe_to_bind("0.0.0.0", "s3cret")


def test_non_loopback_requests_require_the_token(monkeypatch):
    class Cfg:
        dashboard_host = "plans.example"

    monkeypatch.setattr(app_core, "_runtime_config", lambda: Cfg())
    monkeypatch.setattr("src.security.get_server_token", lambda: "s3cret")
    c = _client()
    assert c.get("/api/ping", headers={"Host": "plans.example"}).status_code == 200
    assert c.get("/api/auth/session", headers={"Host": "plans.example"}).status_code == 401
    ok = c.get("/api/auth/session", headers={"Host": "plans.example", "Authorization": "Bearer s3cret"})
    assert ok.status_code != 401


def test_body_cap_returns_413_without_reading_body():
    assert host_guard.body_too_large(host_guard.MAX_REQUEST_BODY_BYTES + 1)
    assert not host_guard.body_too_large(1024)

    class Fake(http_server._Handler):
        def __init__(self):  # no socket
            self.headers = {"Content-Length": str(host_guard.MAX_REQUEST_BODY_BYTES + 1)}
            self.rfile = io.BytesIO()
            self.wfile = io.BytesIO()
            self.sent = []
            self.command = "POST"
            self.path = "/"

        def send_response(self, code, message=None):
            self.sent.append(code)

        def send_header(self, *a):
            pass

        def end_headers(self):
            pass

    h = Fake()
    h._handle()
    assert h.sent == [413]
