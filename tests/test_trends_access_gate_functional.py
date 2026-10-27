"""Remote access: the two listeners, the sign-in gate, sessions, idle timeout, password change."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from financial_trends_reporter.access_store import AccessStore
from financial_trends_reporter.listeners import ListenerApp, check_funnel_target
from financial_trends_reporter.main import create_app
from financial_trends_reporter.sessions import SessionTable

PW = "correct horse"


class Rig:
    def __init__(self, tmp_path: Path):
        base = tmp_path / "workspace"
        (base / "input").mkdir(parents=True)
        (base / "local_state").mkdir(parents=True)
        self.now = [1000.0]
        self.store = AccessStore(tmp_path / "access.db", scrypt_n=2**4)
        self.sessions = SessionTable(clock=lambda: self.now[0])
        self.app = create_app(base, log_path=tmp_path / "log.jsonl", access_store=self.store,
                              sessions=self.sessions, clock=lambda: self.now[0])
        self.remote = ListenerApp(self.app, "remote")
        self.local = ListenerApp(self.app, "local")

    def add(self, username="ann", must_change=False):
        uid = self.store.add_user(username.title(), username, PW)
        if not must_change:
            self.store.set_password(uid, PW, must_change=False)
        return uid

    def call(self, listener, method, path, body=None, cookie=None, headers=None):
        hdrs = {"Host": "pc.tail1234.ts.net" if listener is self.remote else "127.0.0.1:5057"}
        hdrs.update(headers or {})
        raw = b""
        if body is not None:
            raw = json.dumps(body).encode()
            hdrs["Content-Type"] = "application/json"
        if cookie:
            hdrs["Cookie"] = f"trends_session={cookie}"
        return listener.handle_http(method, path, hdrs, raw)

    def signin(self, username="ann", password=PW):
        resp = self.call(self.remote, "POST", "/api/signin", {"username": username, "password": password})
        cookie = resp.headers.get("Set-Cookie", "")
        token = cookie.split(";")[0].split("=", 1)[1] if cookie.startswith("trends_session=") else None
        return resp, token


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def test_remote_data_api_requires_sign_in(rig):
    resp = rig.call(rig.remote, "GET", "/api/history")
    assert resp.status_code == 401
    assert resp.get_json()["success"] is False


def test_remote_page_redirects_to_signin(rig):
    resp = rig.call(rig.remote, "GET", "/")
    assert resp.status_code == 302 and resp.headers["Location"] == "/signin"
    assert rig.call(rig.remote, "GET", "/signin").status_code == 200


def test_remote_signin_sets_secure_httponly_strict_cookie_and_unlocks_the_app(rig):
    rig.add()
    resp, token = rig.signin()
    assert resp.status_code == 200 and token
    cookie = resp.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=Strict" in cookie
    assert rig.call(rig.remote, "GET", "/api/history", cookie=token).status_code == 200


def test_spoofed_localhost_host_header_on_remote_is_still_remote(rig):
    resp = rig.call(rig.remote, "GET", "/api/history", headers={"Host": "127.0.0.1:5057"})
    assert resp.status_code == 401


def test_tampered_or_unknown_cookie_gets_401_not_500(rig):
    for bad in ("garbage", "A" * 200, "../../etc"):
        assert rig.call(rig.remote, "GET", "/api/history", cookie=bad).status_code == 401


def test_signin_error_body_identical_for_unknown_user_and_wrong_password(rig):
    rig.add()
    unknown, _ = rig.signin("nobody", "whatever whatever")
    wrong, _ = rig.signin("ann", "whatever whatever")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.get_data() == wrong.get_data()


def test_lockout_returns_429(rig):
    rig.add()
    for _ in range(5):
        rig.signin("ann", "nope nope nope")
    resp, token = rig.signin("ann", PW)
    assert resp.status_code == 429 and token is None


def test_remote_has_no_owner_only_routes_even_when_signed_in(rig):
    rig.add()
    _, token = rig.signin()
    for path in ("/api/people", "/api/activity", "/access.js"):
        assert rig.call(rig.remote, "GET", path, cookie=token).status_code == 404
        assert rig.call(rig.remote, "GET", path).status_code == 404


def test_local_needs_no_sign_in_and_reports_the_owner(rig):
    assert rig.call(rig.local, "GET", "/api/history").status_code == 200
    who = rig.call(rig.local, "GET", "/api/whoami").get_json()
    assert who["listener"] == "local" and who["name"] == "owner (PC)"


def test_local_rejects_foreign_host_and_forwarded_headers(rig):
    assert rig.call(rig.local, "GET", "/api/history", headers={"Host": "evil.example.com"}).status_code == 421
    assert rig.call(rig.local, "GET", "/api/history", headers={"X-Forwarded-For": "1.2.3.4"}).status_code == 403
    assert rig.call(rig.local, "GET", "/api/history", headers={"Tailscale-User-Login": "a@b"}).status_code == 403
    assert rig.call(rig.local, "GET", "/api/history", headers={"Host": "localhost:5057"}).status_code == 200


def test_signout_ends_only_that_session(rig):
    rig.add("ann")
    rig.add("bob")
    _, a = rig.signin("ann")
    _, b = rig.signin("bob")
    assert rig.call(rig.remote, "POST", "/api/signout", {}, cookie=a).status_code == 200
    assert rig.call(rig.remote, "GET", "/api/history", cookie=a).status_code == 401
    assert rig.call(rig.remote, "GET", "/api/history", cookie=b).status_code == 200


def test_exit_on_local_never_touches_sessions_or_server(rig):
    rig.add()
    _, token = rig.signin()
    assert rig.call(rig.local, "POST", "/api/signout", {}).status_code == 200
    assert rig.call(rig.remote, "GET", "/api/history", cookie=token).status_code == 200


def test_ping_without_new_interaction_does_not_extend_idle(rig):
    rig.add()
    _, token = rig.signin()
    for step in range(1, 12):
        rig.now[0] = 1000.0 + step * 50
        idle_ms = (rig.now[0] - 1000.0) * 1000
        resp = rig.call(rig.remote, "POST", "/api/ping", {"idle_ms": idle_ms}, cookie=token)
        if rig.now[0] - 1000.0 >= 600:
            assert resp.status_code == 401
            break
        assert resp.status_code == 200


def test_interaction_reported_by_ping_extends_idle(rig):
    rig.add()
    _, token = rig.signin()
    rig.now[0] = 1500.0
    assert rig.call(rig.remote, "POST", "/api/ping", {"idle_ms": 0}, cookie=token).status_code == 200
    rig.now[0] = 2000.0
    assert rig.call(rig.remote, "GET", "/api/history", cookie=token).status_code == 200


def test_must_change_blocks_other_apis_until_changed(rig):
    rig.add(must_change=True)
    resp, token = rig.signin()
    assert resp.get_json()["must_change"] is True
    blocked = rig.call(rig.remote, "GET", "/api/history", cookie=token)
    assert blocked.status_code == 409 and blocked.get_json()["must_change"] is True
    ok = rig.call(rig.remote, "POST", "/api/change-password", {"current": PW, "new": "a brand new pass"}, cookie=token)
    assert ok.status_code == 200
    assert rig.call(rig.remote, "GET", "/api/history", cookie=token).status_code == 200
    assert rig.signin("ann", "a brand new pass")[1]


def test_change_password_rejects_wrong_current_and_short_new(rig):
    rig.add()
    _, token = rig.signin()
    assert rig.call(rig.remote, "POST", "/api/change-password", {"current": "wrong wrong", "new": "a brand new pass"}, cookie=token).status_code == 400
    assert rig.call(rig.remote, "POST", "/api/change-password", {"current": PW, "new": "short"}, cookie=token).status_code == 400


def test_deleted_user_loses_the_session_on_the_next_request(rig):
    uid = rig.add()
    _, token = rig.signin()
    rig.store.delete_user(uid)
    assert rig.call(rig.remote, "GET", "/api/history", cookie=token).status_code == 401


def test_funnel_guard_flags_5057_target_and_skips_when_tailscale_missing():
    class Out:
        def __init__(self, stdout):
            self.stdout = stdout

    bad = json.dumps({"Web": {"pc.ts.net:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:5057"}}}}})
    good = json.dumps({"Web": {"pc.ts.net:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:5058"}}}}})
    assert "5057" in check_funnel_target(run=lambda *a, **k: Out(bad))
    assert check_funnel_target(run=lambda *a, **k: Out(good)) is None

    def missing(*a, **k):
        raise FileNotFoundError

    assert check_funnel_target(run=missing) is None
