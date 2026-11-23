"""X-1 (security review 2026-11-23): the Admin app (5056) and the Financial Insights owner listener (5057) need a per-boot
local token, because worker accounts on the same host can reach loopback too. Both apps share ``src/http_runtime/local_token_gate.py``."""
from __future__ import annotations

import json
import os
import stat
import sys
import threading
import urllib.error
import urllib.request

import pytest

from admin_app import main as admin_main
from financial_trends_reporter import main as insights_main
from financial_trends_reporter.listeners import ListenerApp
from financial_trends_reporter.sessions import SessionTable
from src.http_runtime import local_token_gate as gate_mod
from src.http_runtime.server import LocalHTTPServer
from src.http_runtime.wsgi_facade import HeaderMap, LocalRequest
from src.identity import IdentityStore
from src.http_runtime.local_token_gate import LocalTokenGate

ADMIN_HOST = {"Host": "127.0.0.1:5056"}
INSIGHTS_HOST = {"Host": "127.0.0.1:5057"}
JSON = {"Content-Type": "application/json"}


class Rig:
    """One gated app of either kind behind a uniform ``call(method, path, headers, body)``."""

    def __init__(self, kind, tmp_path):
        self.kind, self.now = kind, [1000.0]
        self.gate = LocalTokenGate.start("admin" if kind == "admin" else "insights", tmp_path, clock=lambda: self.now[0])
        store = IdentityStore(tmp_path / "identity.db", scrypt_n=2**4)
        if kind == "admin":
            store.add_user("Owner", "owner", "correct horse", role="admin", insights=False)
            self.app = admin_main.create_app(store, local_gate=self.gate)
            self.host = ADMIN_HOST
            self.read, self.write = ("GET", "/api/users"), ("POST", "/api/users")
            self.write_body = json.dumps({"display_name": "A", "username": "a", "temp_password": "correct horse"}).encode()
            self.handle = lambda m, t, h, b: self.app.dispatch_request(LocalRequest(m, t, HeaderMap(h), b))
        else:
            base = tmp_path / "workspace"
            (base / "input").mkdir(parents=True)
            self.app = insights_main.create_app(base, log_path=tmp_path / "log.jsonl", access_store=store,
                                                sessions=SessionTable(clock=lambda: self.now[0]), clock=lambda: self.now[0],
                                                local_gate=self.gate)
            self.host = INSIGHTS_HOST
            self.read, self.write = ("GET", "/api/history"), ("POST", "/api/run-cancel")
            self.write_body = b"{}"
            self.local = ListenerApp(self.app, "local")
            self.remote = ListenerApp(self.app, "remote")
            self.handle = lambda m, t, h, b: self.local.handle_http(m, t, h, b)

    def call(self, method, path, headers=None, body=b""):
        return self.handle(method, path, {**self.host, **JSON, **(headers or {})}, body)

    def token(self):
        return {gate_mod.TOKEN_HEADER: self.gate.token}

    def handoff(self):
        """The launcher's flow: header token -> nonce -> open URL -> cookie."""
        nonce = json.loads(self.call("POST", gate_mod.NONCE_PATH, self.token(), b"{}").get_data(as_text=True))["nonce"]
        opened = self.call("GET", f"{gate_mod.OPEN_PATH}?n={nonce}")
        return nonce, opened


@pytest.fixture(params=["admin", "insights"])
def rig(request, tmp_path):
    return Rig(request.param, tmp_path)


def cookie_header(resp):
    return resp.headers["Set-Cookie"].split(";", 1)[0]


# ---- unauthenticated requests are refused ----
def test_unauthenticated_requests_get_401_on_read_and_write_routes(rig):
    for (method, path), body in ((rig.read, b""), (rig.write, rig.write_body)):
        resp = rig.call(method, path, None, body)
        assert resp.status_code == 401, (rig.kind, method, path)
        assert resp.get_json()["success"] is False
    assert rig.call("GET", "/api/ping").status_code == 401 or rig.kind == "insights"  # insights has no GET /api/ping route


def test_the_root_page_answers_a_small_open_from_the_launcher_page(rig):
    for path in ("/", "/charts.js" if rig.kind == "insights" else "/users.js"):
        resp = rig.call("GET", path)
        assert resp.status_code == 401
        text = resp.get_data(as_text=True)
        assert resp.mimetype == "text/html" and "Open this app from its launcher" in text and len(text) < 2000


def test_existing_gates_still_run_before_the_token_check(rig):
    assert rig.handle("GET", rig.read[1], {"Host": "evil.example", **rig.token()}, b"").status_code in (403, 421)
    assert rig.handle(rig.read[0], rig.read[1], {**rig.host, "X-Forwarded-For": "1.2.3.4", **rig.token()}, b"").status_code == 403
    assert rig.handle(rig.read[0], rig.read[1], {**rig.host, "Origin": "http://evil.example", **rig.token()}, b"").status_code == 403


# ---- the X-Local-Token header ----
def test_header_token_is_accepted_and_a_wrong_or_partial_token_is_not(rig):
    assert rig.call(*rig.read, rig.token()).status_code == 200
    assert rig.call(rig.write[0], rig.write[1], rig.token(), rig.write_body).status_code != 401
    for bad in ("", "wrong", rig.gate.token[:-1], rig.gate.token + "x", rig.gate.token.upper()):
        assert rig.call(*rig.read, {gate_mod.TOKEN_HEADER: bad}).status_code == 401, bad


def test_the_token_is_compared_in_constant_time(rig, monkeypatch):
    seen = []
    real = gate_mod.hmac.compare_digest
    monkeypatch.setattr(gate_mod.hmac, "compare_digest", lambda a, b: seen.append(1) or real(a, b))
    rig.call(*rig.read, rig.token())
    assert seen


# ---- the cookie handoff ----
def test_handoff_sets_an_httponly_samesite_cookie_that_then_works_and_the_token_never_leaves(rig):
    nonce, opened = rig.handoff()
    assert opened.status_code == 302 and opened.headers["Location"] == "/"
    set_cookie = opened.headers["Set-Cookie"]
    assert "HttpOnly" in set_cookie and "SameSite=Strict" in set_cookie and set_cookie.startswith(rig.gate.cookie_name + "=")
    assert rig.gate.token not in set_cookie and rig.gate.token not in opened.headers["Location"] and rig.gate.token not in nonce
    cookie = {"Cookie": cookie_header(opened)}
    assert rig.call(*rig.read, cookie).status_code == 200
    assert rig.call("GET", "/", cookie).status_code == 200
    assert rig.call(rig.write[0], rig.write[1], cookie, rig.write_body).status_code != 401


def test_a_replayed_nonce_fails(rig):
    nonce, first = rig.handoff()
    assert first.status_code == 302
    again = rig.call("GET", f"{gate_mod.OPEN_PATH}?n={nonce}")
    assert again.status_code == 401 and "Set-Cookie" not in again.headers


def test_an_expired_nonce_fails(rig):
    nonce = json.loads(rig.call("POST", gate_mod.NONCE_PATH, rig.token(), b"{}").get_data(as_text=True))["nonce"]
    rig.now[0] += gate_mod.NONCE_TTL_SECONDS + 1
    assert rig.call("GET", f"{gate_mod.OPEN_PATH}?n={nonce}").status_code == 401


def test_nonces_cannot_be_minted_or_guessed_without_the_token(rig):
    assert rig.call("POST", gate_mod.NONCE_PATH, None, b"{}").status_code == 401
    assert rig.call("POST", gate_mod.NONCE_PATH, {gate_mod.TOKEN_HEADER: "nope"}, b"{}").status_code == 401
    for n in ("", "guess", rig.gate.token):  # the long-lived token is not a nonce either
        assert rig.call("GET", f"{gate_mod.OPEN_PATH}?n={n}").status_code == 401


def test_a_forged_or_other_apps_cookie_fails(rig, tmp_path):
    assert rig.call(*rig.read, {"Cookie": f"{rig.gate.cookie_name}=forged"}).status_code == 401
    other = Rig("insights" if rig.kind == "admin" else "admin", tmp_path / "other")
    other_cookie = cookie_header(other.handoff()[1])
    assert rig.call(*rig.read, {"Cookie": other_cookie}).status_code == 401
    assert Rig("admin", tmp_path / "a").gate.cookie_name != Rig("insights", tmp_path / "b").gate.cookie_name  # browsers share cookies across ports


def test_a_session_cookie_expires(rig):
    cookie = {"Cookie": cookie_header(rig.handoff()[1])}
    rig.now[0] += gate_mod.SESSION_TTL_SECONDS + 1
    assert rig.call(*rig.read, cookie).status_code == 401


# ---- the token file ----
def test_token_file_holds_the_token_and_is_owner_only(rig, tmp_path):
    path = gate_mod.token_file_path(tmp_path, rig.gate.name)
    assert path.read_text(encoding="utf-8").strip() == rig.gate.token and len(rig.gate.token) >= 43
    assert not list(path.parent.glob("*.tmp"))
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_each_start_makes_a_new_token(tmp_path):
    first = LocalTokenGate.start("admin", tmp_path)
    second = LocalTokenGate.start("admin", tmp_path)
    assert first.token != second.token and gate_mod.read_token(tmp_path, "admin") == second.token


# ---- insights: only the owner (local) listener is gated; the remote listener keeps its own sign-in ----
def test_remote_listener_is_unchanged_and_cannot_use_the_handoff(tmp_path):
    rig = Rig("insights", tmp_path)
    resp = rig.remote.handle_http("GET", "/api/history", {"Host": "x.ts.net"})
    assert resp.status_code == 401 and "sign in required" in resp.get_data(as_text=True)
    nonce = rig.gate.mint_nonce()
    opened = rig.remote.handle_http("GET", f"{gate_mod.OPEN_PATH}?n={nonce}", {"Host": "x.ts.net"})
    assert opened.status_code == 302 and opened.headers["Location"] == "/signin" and "Set-Cookie" not in opened.headers
    # a remote caller holding the header token is still not the owner
    assert rig.remote.handle_http("GET", "/api/history", {"Host": "x.ts.net", gate_mod.TOKEN_HEADER: rig.gate.token}).status_code == 401


# ---- main() always installs the gate ----
def test_admin_main_serves_a_gated_app_and_writes_the_token_file(monkeypatch, tmp_path):
    served = []

    class FakeServer:
        def __init__(self, address, app):
            served.append(app)

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass

    monkeypatch.setattr(admin_main, "LocalHTTPServer", FakeServer)
    monkeypatch.setattr(admin_main, "check_funnel_target", lambda port: None)
    monkeypatch.setattr(admin_main, "_port_in_use", lambda port: False)
    assert admin_main.main(["--retirement-system-dir", str(tmp_path), "--no-open", "--port", "5999"]) == 0
    app = served[0]
    assert app.local_gate is not None and gate_mod.read_token(tmp_path, "admin") == app.local_gate.token
    assert app.dispatch_request(LocalRequest("GET", "/api/users", HeaderMap(ADMIN_HOST))).status_code == 401


def test_insights_main_serves_a_gated_owner_listener_and_writes_the_token_file(monkeypatch, tmp_path):
    served = []

    class FakeServer:
        def __init__(self, address, app):
            served.append(app)

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass

    monkeypatch.setattr(insights_main, "LocalHTTPServer", FakeServer)
    monkeypatch.setattr(insights_main, "check_funnel_target", lambda port: None)
    monkeypatch.setattr(insights_main, "_port_in_use", lambda host, port: False)
    monkeypatch.setattr(insights_main, "sync_from_app", lambda *a, **k: None)
    (tmp_path / "input").mkdir()
    assert insights_main.main(["--retirement-system-dir", str(tmp_path), "--no-open", "--no-remote", "--port", "5999"]) == 0
    listener = served[0]
    assert listener.listener == "local" and listener.app.local_gate is not None
    assert gate_mod.read_token(tmp_path, "insights") == listener.app.local_gate.token
    assert listener.handle_http("GET", "/api/history", INSIGHTS_HOST).status_code == 401


def test_print_open_url_for_a_missing_or_unreadable_app_fails_cleanly(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(admin_main, "_port_in_use", lambda port: False)
    assert admin_main.main(["--retirement-system-dir", str(tmp_path), "--print-open-url"]) == 1
    monkeypatch.setattr(admin_main, "_port_in_use", lambda port: True)  # running, but no token file for this workspace
    assert admin_main.main(["--retirement-system-dir", str(tmp_path), "--print-open-url"]) == 1
    assert "token" in capsys.readouterr().err


# ---- the launcher flow over a real socket ----
def test_launcher_flow_over_a_real_socket(tmp_path, monkeypatch):
    """The exact sequence the launcher runs: token file -> POST nonce (header) -> open URL -> cookie -> same-origin API call."""
    store = IdentityStore(tmp_path / "identity.db", scrypt_n=2**4)
    gate = LocalTokenGate.start("admin", tmp_path)
    server = LocalHTTPServer(("127.0.0.1", 0), admin_main.create_app(store, local_gate=gate))
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(base + "api/users", timeout=5)
        assert err.value.code == 401
        opened, printed = [], []
        assert gate_mod.open_running_app(base, tmp_path, "admin", print_only=False, opener=opened.append) == 0
        assert gate_mod.open_running_app(base, tmp_path, "admin", print_only=True, opener=opened.append, out=printed.append) == 0
        assert len(opened) == 1 and opened[0].startswith(base + "_local/open?n=") and gate.token not in opened[0]

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None

        opener = urllib.request.build_opener(NoRedirect)
        with pytest.raises(urllib.error.HTTPError) as redirect:
            opener.open(opened[0], timeout=5)
        assert redirect.value.code == 302
        cookie = redirect.value.headers["Set-Cookie"].split(";", 1)[0]
        req = urllib.request.Request(base + "api/users", headers={"Cookie": cookie})
        assert urllib.request.urlopen(req, timeout=5).status == 200
        with pytest.raises(urllib.error.HTTPError) as replay:
            opener.open(opened[0], timeout=5)  # the same nonce a second time
        assert replay.value.code == 401
        assert printed and printed[0].startswith(base + "_local/open?n=")
    finally:
        server.shutdown()
        server.server_close()
