"""The Admin app has no sign-in, so its only protection is the loopback trust boundary. Pin every part of it."""
from __future__ import annotations

import json
import socket
import subprocess
import threading
from types import SimpleNamespace

import pytest

from admin_app.main import PAGES, _port_in_use, create_app, main
from admin_app.trust import check_funnel_target
from src.http_runtime.server import LocalHTTPServer
from src.http_runtime.wsgi_facade import HeaderMap, LocalRequest
from src.identity import IdentityStore

OK_HEADERS = {"Host": "127.0.0.1:5056"}
JSON_HEADERS = {**OK_HEADERS, "Content-Type": "application/json"}


@pytest.fixture
def app(tmp_path):
    store = IdentityStore(tmp_path / "identity.db", scrypt_n=2**4)
    store.add_user("Owner", "owner", "correct horse", role="admin", insights=False)
    return create_app(store)


def call(app, method, path, headers, body=b"", remote_addr="127.0.0.1"):
    resp = app.dispatch_request(LocalRequest(method, path, HeaderMap(headers), body, remote_addr=remote_addr))
    return resp.status_code


ADD = json.dumps({"display_name": "A", "username": "a", "temp_password": "correct horse"}).encode()


def test_loopback_hosts_are_answered(app):
    for host in ("127.0.0.1:5056", "localhost:5056", "[::1]:5056", "LOCALHOST"):
        assert call(app, "GET", "/api/users", {"Host": host}) == 200


@pytest.mark.parametrize("host", ["", "evil.example", "evil.example:5056", "192.168.1.5:5056", "100.64.0.2:5056",
                                  "127.0.0.1.evil.example", "localhost.evil.example", "0.0.0.0:5056", "[::]:5056"])
def test_non_loopback_host_is_refused_for_every_route(app, host):
    headers = {"Host": host} if host else {}
    for method, path in (("GET", "/"), ("GET", "/users.js"), ("GET", "/api/users"), ("GET", "/api/audit"), ("GET", "/api/ping")):
        assert call(app, method, path, headers) == 421, (method, path, host)
    assert call(app, "POST", "/api/users", {**headers, "Content-Type": "application/json"}, ADD) == 421


@pytest.mark.parametrize("header", ["X-Forwarded-For", "x-forwarded-host", "X-Forwarded-Proto", "Forwarded", "X-Real-IP", "Via",
                                    "Tailscale-User-Login", "tailscale-user-name"])
def test_proxy_and_funnel_headers_are_refused(app, header):
    assert call(app, "GET", "/api/users", {**OK_HEADERS, header: "203.0.113.9"}) == 403
    assert call(app, "POST", "/api/users", {**JSON_HEADERS, header: "x"}, ADD) == 403


@pytest.mark.parametrize("peer", ["203.0.113.9", "192.168.1.5", "100.64.0.2", "::2", ""])
def test_non_loopback_peer_is_refused_even_with_a_loopback_host(app, peer):
    assert call(app, "GET", "/api/users", OK_HEADERS, remote_addr=peer) == 403


@pytest.mark.parametrize("peer", ["127.0.0.1", "::1", "::ffff:127.0.0.1"])
def test_loopback_peers_are_answered(app, peer):
    assert call(app, "GET", "/api/users", OK_HEADERS, remote_addr=peer) == 200


def test_cross_origin_requests_are_refused(app):
    assert call(app, "POST", "/api/users", {**JSON_HEADERS, "Origin": "https://evil.example"}, ADD) == 403
    assert call(app, "POST", "/api/users", {**JSON_HEADERS, "Origin": "http://127.0.0.1:9999"}, ADD) == 403  # another local port
    assert call(app, "POST", "/api/users", {**JSON_HEADERS, "Origin": "null"}, ADD) == 403
    assert call(app, "GET", "/api/users", {**OK_HEADERS, "Origin": "http://evil.example"}) == 403
    assert call(app, "GET", "/api/users", {**OK_HEADERS, "Sec-Fetch-Site": "cross-site"}) == 403
    assert call(app, "GET", "/api/users", {**OK_HEADERS, "Sec-Fetch-Site": "same-site"}) == 403
    assert call(app, "GET", "/api/users", {**OK_HEADERS, "Sec-Fetch-Site": "same-origin"}) == 200
    assert call(app, "POST", "/api/users", {**JSON_HEADERS, "Origin": "http://127.0.0.1:5056"}, ADD) == 200


def test_writes_must_be_json_and_small(app):
    assert call(app, "POST", "/api/users", OK_HEADERS, ADD) == 415
    assert call(app, "POST", "/api/users", {**OK_HEADERS, "Content-Type": "application/x-www-form-urlencoded"}, b"id=1") == 415
    assert call(app, "POST", "/api/users", {**OK_HEADERS, "Content-Type": "text/plain"}, ADD) == 415
    assert call(app, "POST", "/api/users", JSON_HEADERS, b"x" * (64 * 1024 + 1)) == 413


def test_a_refused_request_changes_nothing(tmp_path):
    store = IdentityStore(tmp_path / "identity.db", scrypt_n=2**4)
    api = create_app(store)
    call(api, "POST", "/api/users", {"Host": "evil.example", "Content-Type": "application/json"}, ADD)
    call(api, "POST", "/api/users", {**JSON_HEADERS, "X-Forwarded-For": "1.2.3.4"}, ADD)
    assert store.list_users() == [] and store.read_audit() == []


def test_unknown_paths_and_methods_stay_closed(app):
    assert call(app, "GET", "/api/people", OK_HEADERS) == 404
    assert call(app, "GET", "/access.js", OK_HEADERS) == 404
    assert call(app, "GET", "/..%2fsrc/identity/store.py", OK_HEADERS) == 404
    assert call(app, "DELETE", "/api/users", JSON_HEADERS) == 404
    assert sorted(PAGES) == ["/", "/admin.css", "/admin.js", "/settings_renderer.js", "/users.js"]  # the only files ever read from disk


def _tailscale(stdout: str):
    return lambda *a, **k: SimpleNamespace(stdout=stdout, returncode=0)


def test_funnel_check_refuses_when_tailscale_serves_the_admin_port():
    serving = json.dumps({"Web": {"host.ts.net:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:5056"}}}}})
    assert "5056" in check_funnel_target(5056, run=_tailscale(serving))
    other = json.dumps({"Web": {"host.ts.net:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:5058"}}}}})
    assert check_funnel_target(5056, run=_tailscale(other)) is None
    assert check_funnel_target(5056, run=_tailscale("{}")) is None


def test_funnel_check_is_skipped_when_tailscale_is_missing_or_unreadable():
    def missing(*a, **k):
        raise FileNotFoundError("tailscale")
    assert check_funnel_target(5056, run=missing) is None
    assert check_funnel_target(5056, run=_tailscale("not json")) is None
    assert check_funnel_target(5056, run=lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("tailscale", 10))) is None


def test_start_is_refused_when_funnel_targets_the_admin_port(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("admin_app.main.check_funnel_target", lambda port: "Tailscale is configured to serve port")
    monkeypatch.setattr("admin_app.main._port_in_use", lambda port: False)
    started = []
    monkeypatch.setattr("admin_app.main.LocalHTTPServer", lambda *a, **k: started.append(a))
    assert main(["--retirement-system-dir", str(tmp_path), "--no-open", "--port", "5999"]) == 1
    assert started == [] and "Tailscale" in capsys.readouterr().err
    assert not (tmp_path / "local_state").exists()  # refused before touching any data


def test_the_server_binds_loopback_only_and_has_no_host_option(monkeypatch, tmp_path):
    bound = []

    class FakeServer:
        def __init__(self, address, app):
            bound.append(address)

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass

    monkeypatch.setattr("admin_app.main.LocalHTTPServer", FakeServer)
    monkeypatch.setattr("admin_app.main.check_funnel_target", lambda port: None)
    monkeypatch.setattr("admin_app.main._port_in_use", lambda port: False)
    assert main(["--retirement-system-dir", str(tmp_path), "--no-open", "--port", "5999"]) == 0
    assert bound == [("127.0.0.1", 5999)]
    with pytest.raises(SystemExit):
        main(["--host", "0.0.0.0"])  # not an option at all


def test_second_start_detects_the_running_instance(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("admin_app.main._port_in_use", lambda port: True)
    monkeypatch.setattr("admin_app.main.LocalHTTPServer", lambda *a, **k: pytest.fail("must not bind a second server"))
    assert main(["--retirement-system-dir", str(tmp_path), "--no-open"]) == 0
    assert "already running" in capsys.readouterr().out


def test_live_socket_refuses_a_wrong_host_header_and_answers_the_right_one(tmp_path):
    """End to end over a real loopback socket, including the stdlib runtime's own request parsing."""
    store = IdentityStore(tmp_path / "identity.db", scrypt_n=2**4)
    server = LocalHTTPServer(("127.0.0.1", 0), create_app(store))
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert _port_in_use(port)

        def get(host: str, extra: str = "") -> str:
            with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
                s.sendall(f"GET /api/users HTTP/1.1\r\nHost: {host}\r\n{extra}Connection: close\r\n\r\n".encode())
                data = b""
                while chunk := s.recv(4096):
                    data += chunk
            return data.split(b"\r\n", 1)[0].decode()

        assert " 200 " in get(f"127.0.0.1:{port}")
        assert " 421 " in get("evil.example")
        assert " 403 " in get(f"127.0.0.1:{port}", "X-Forwarded-For: 1.2.3.4\r\n")
    finally:
        server.shutdown()
        server.server_close()
