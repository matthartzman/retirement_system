"""The isolation gate: two users behind a real gateway process, each with their own real worker process.

``tests/conftest.py`` builds one workspace per session, so two users cannot share one test process; like
``tests/e2e/fixtures.js`` this starts the gateway (and through it the workers) as subprocesses with a temp
data root, the same-account launcher and no elevation. It shows that user A cannot read or change user B's
plan through the gateway, through a guessed worker port without the token, with a forged Host or Origin,
or with client-supplied credential headers, and that logout and gateway exit stop the workers.

Slow-ish (two worker starts, about 5-15 s) and Windows-sensitive: run it once per change, not in a loop.
"""
from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.gateway import totp
from src.gateway.store import Actor, GatewayStore

pytestmark = [pytest.mark.integration, pytest.mark.e2e]

ROOT = Path(__file__).resolve().parents[1]
PW = "isolation gate password 1"
PUBLIC_ORIGIN = "https://node.example.ts.net:8443"
PUBLIC_HOST = "node.example.ts.net:8443"
HOME = ("Other Assets", "Home", "value_as_of_plan_start")


def _pid_alive(pid: int) -> bool:
    try:
        from src.gateway import winapi  # noqa: PLC0415
        import ctypes  # noqa: PLC0415

        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = ctypes.c_void_p
        h = k.OpenProcess(0x1000 | 0x00100000, False, int(pid))
        if not h:
            return False
        try:
            return winapi.process_exit_code(h) is None
        finally:
            k.CloseHandle(ctypes.c_void_p(h))
    except OSError:
        return False


class Client:
    """A browser stand-in on one gateway listener: keeps the session cookie and CSRF token."""

    def __init__(self, port: int, listener: str = "local") -> None:
        self.port, self.listener = port, listener
        self.cookie = ""
        self.csrf = ""

    @property
    def origin(self) -> str:
        return PUBLIC_ORIGIN if self.listener == "funnel" else f"http://127.0.0.1:{self.port}"

    def request(self, method: str, path: str, body=None, headers: dict | None = None, *, origin=True,
                csrf=True) -> tuple[int, dict, bytes]:
        hdrs = {"Host": PUBLIC_HOST if self.listener == "funnel" else f"127.0.0.1:{self.port}"}
        if self.listener == "funnel":
            hdrs["X-Forwarded-For"] = "203.0.113.9"
        data = b""
        if body is not None:
            data = json.dumps(body).encode()
            hdrs["Content-Type"] = "application/json"
        if method not in ("GET", "HEAD"):
            if origin:
                hdrs["Origin"] = self.origin if origin is True else origin
            if csrf and self.csrf:
                hdrs["X-CSRF-Token"] = self.csrf
        if self.cookie:
            hdrs["Cookie"] = self.cookie
        hdrs.update(headers or {})
        hdrs["Content-Length"] = str(len(data))
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=120)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            for k, v in hdrs.items():
                conn.putheader(k, v)
            conn.endheaders(data)
            resp = conn.getresponse()
            raw = resp.read()
            rh = {k.lower(): v for k, v in resp.getheaders()}
        finally:
            conn.close()
        set_cookie = rh.get("set-cookie", "")
        if set_cookie:
            pair = set_cookie.split(";", 1)[0]
            self.cookie = "" if "Max-Age=0" in set_cookie else pair
        return resp.status, rh, raw

    def json(self, method: str, path: str, body=None, **kw) -> tuple[int, dict]:
        status, _h, raw = self.request(method, path, body, **kw)
        try:
            return status, json.loads(raw)
        except ValueError:
            return status, {"_raw": raw[:300].decode("utf-8", "replace")}

    def sign_in(self, username: str, secret: str, step_offset: int = 0) -> None:
        """``step_offset`` 1 for a user's second sign-in within one 30 s step (codes are single-use;
        the gateway accepts the next step's code too)."""
        status, body = self.json("POST", "/api/auth/login", {"username": username, "password": PW})
        assert status == 200 and body.get("next") == "totp", body
        self.csrf = body["csrf_token"]
        code = totp.code_at(secret, int(time.time() // 30) + step_offset)
        status, body = self.json("POST", "/api/auth/totp/verify", {"code": code})
        assert status == 200, body
        status, body = self.json("GET", "/api/auth/session")
        assert status == 200 and body["authenticated"] is True, body
        self.csrf = body["csrf_token"]


def _enrolled_user(store: GatewayStore, username: str) -> tuple[int, str]:
    actor = Actor(None, "isolation-test")
    now = time.time()
    uid = store.create_user(username, username.title(), "user", PW, now=now, actor=actor, must_change=False)
    secret = store.begin_totp_enrolment(uid, now - 3600)
    assert store.confirm_totp(uid, totp.code_at(secret, int((now - 3600) // 30)), now - 3600)
    return uid, secret


@pytest.fixture(scope="module")
def gateway(tmp_path_factory):
    base = tmp_path_factory.mktemp("isolation")
    db = base / "gateway.db"
    store = GatewayStore(db, scrypt_n=2**12)
    users = {name: _enrolled_user(store, name) for name in ("alice", "bob")}
    data_root = base / "data"
    ready_file = base / "ready.json"
    env = {k: v for k, v in os.environ.items() if not k.startswith("RETIREMENT_SYSTEM_")}
    cmd = [sys.executable, "-m", "src.gateway", "--db", str(db), "--local-port", "0", "--funnel-port", "0",
           "--public-origin", PUBLIC_ORIGIN, "--no-tailscale-check", "--data-root", str(data_root), "--provision", "demo",
           "--ready-file", str(ready_file), "--build-concurrency", "1",
           "--worker-env", "RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1",
           "--worker-env", "RETIREMENT_SYSTEM_FROZEN_TODAY=2026-08-04"]
    log = (base / "gateway.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
    deadline = time.time() + 60
    while not ready_file.is_file():
        if proc.poll() is not None or time.time() > deadline:
            log.close()
            pytest.fail("gateway did not start:\n" + (base / "gateway.log").read_text(encoding="utf-8")[-3000:])
        time.sleep(0.1)
    ready = json.loads(ready_file.read_text(encoding="utf-8"))
    assert ready["workers"] is True
    info = {"proc": proc, "ready": ready, "users": users, "data_root": data_root, "base": base, "store": store}
    try:
        yield info
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


@pytest.fixture(scope="module")
def signed_in(gateway):
    port = gateway["ready"]["local_port"]
    clients = {}
    for name, (_uid, secret) in gateway["users"].items():
        c = Client(port)
        c.sign_in(name, secret)
        clients[name] = c
    return clients


def _port_info(gateway, user: str) -> dict:
    uid = gateway["users"][user][0]
    path = gateway["data_root"] / "users" / str(uid) / "local_state" / "worker.port.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _home_row(client: Client) -> dict:
    status, body = client.json("GET", "/api/config/rows")
    assert status == 200, body
    return next(r for r in body["rows"] if (r["section"], r["subsection"], r["label"]) == HOME)


def test_each_user_reaches_their_own_worker(gateway, signed_in):
    for name in ("alice", "bob"):
        status, body = signed_in[name].json("GET", "/api/ping")
        assert status == 200 and body.get("remote_mode") is True, body
    a, b = _port_info(gateway, "alice"), _port_info(gateway, "bob")
    assert a["port"] != b["port"] and a["pid"] != b["pid"]
    uid_a, uid_b = gateway["users"]["alice"][0], gateway["users"]["bob"][0]
    assert (gateway["data_root"] / "users" / str(uid_a) / "plan.rpx").is_file()
    assert (gateway["data_root"] / "users" / str(uid_b) / "plan.rpx").is_file()


def test_a_plan_edit_by_one_user_is_invisible_to_the_other(signed_in):
    alice, bob = signed_in["alice"], signed_in["bob"]
    before_b = _home_row(bob)["value"]
    row = _home_row(alice)
    status, body = alice.json("POST", "/api/config/rows",
                              {"updates": [{"row_index": row["row_index"], "value": "$1,234,567"}], "sync": True})
    assert status == 200 and body.get("updated") == 1, body
    assert _home_row(alice)["value"] == "$1,234,567"
    assert _home_row(bob)["value"] == before_b != "$1,234,567"


def test_a_guessed_worker_port_without_the_token_is_refused(gateway, signed_in):
    b = _port_info(gateway, "bob")
    for headers in ({}, {"X-API-Token": "guessed-token"}, {"Authorization": "Bearer guessed-token"},
                    {"Host": "evil.example", "X-API-Token": "guessed-token"}):
        conn = http.client.HTTPConnection("127.0.0.1", b["port"], timeout=30)
        try:
            conn.request("GET", "/api/config/rows", headers=headers)
            resp = conn.getresponse()
            body = resp.read()
        finally:
            conn.close()
        assert resp.status in (401, 403, 421), (headers, resp.status)
        assert b"Home" not in body
    # A state-changing call straight at the port, with a forged Origin, changes nothing.
    conn = http.client.HTTPConnection("127.0.0.1", b["port"], timeout=30)
    try:
        conn.request("POST", "/api/config/rows", body=json.dumps({"updates": [], "sync": True}),
                     headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{b['port']}"})
        resp = conn.getresponse()
        resp.read()
    finally:
        conn.close()
    assert resp.status == 401


def test_forged_host_and_origin_are_refused_at_the_gateway(gateway, signed_in):
    alice = signed_in["alice"]
    status, _h, _b = alice.request("GET", "/api/config/rows", headers={"Host": "127.0.0.1:1"})
    assert status == 200  # any loopback Host is the local listener's own; the worker Host is rewritten
    status, _h, _b = alice.request("GET", "/api/config/rows", headers={"Host": "evil.example"})
    assert status == 421
    b = _port_info(gateway, "bob")
    status, body = alice.json("POST", "/api/config/rows", {"updates": [], "sync": True},
                              origin=f"http://127.0.0.1:{b['port']}")
    assert status == 403, body
    status, body = alice.json("POST", "/api/config/rows", {"updates": [], "sync": True}, origin="https://evil.example")
    assert status == 403, body


def test_client_credential_headers_never_reach_a_worker_or_switch_the_user(gateway, signed_in):
    port = gateway["ready"]["funnel_port"]
    alice = Client(port, "funnel")
    alice.sign_in("alice", gateway["users"]["alice"][1], step_offset=1)
    bob_cookie = signed_in["bob"].cookie
    hostile = {"X-API-Token": "client-chosen", "Authorization": "Bearer client-chosen",
               "X-Forwarded-Host": f"127.0.0.1:{_port_info(gateway, 'bob')['port']}", "X-Forwarded-Proto": "http",
               "Forwarded": "for=127.0.0.1;host=127.0.0.1", "X-Real-IP": "127.0.0.1", "X-Gateway-User": "bob"}
    # If any client credential reached the worker it would refuse the request (wrong token), and a
    # switched user would show Bob's value instead of the one Alice saved.
    row = _home_row(alice)
    status, _h, raw = alice.request("GET", "/api/config/rows", headers=hostile)
    assert status == 200, raw[:300]
    rows = json.loads(raw)["rows"]
    assert next(r for r in rows if (r["section"], r["subsection"], r["label"]) == HOME)["value"] == row["value"]
    # Bob's cookie carried alongside Alice's: refused outright rather than one of them being picked.
    try:
        status, _h, raw = alice.request("GET", "/api/config/rows", headers={"Cookie": f"{alice.cookie}; {bob_cookie}"})
        assert status == 400 and b"Home" not in raw, (status, raw[:200])
    finally:
        status, body = alice.json("POST", "/api/auth/logout", {})
        assert status == 200, body


def test_the_event_stream_route_and_the_synchronous_build_are_blocked(signed_in):
    alice = signed_in["alice"]
    status, body = alice.json("GET", "/api/build/events/abc123")
    assert status == 403, body
    status, body = alice.json("POST", "/api/build", {})
    assert status == 403, body
    status, body = alice.json("GET", "/api/build/progress/queued-0000000000000000")
    assert status == 404, body


def test_worker_responses_set_no_cookie_and_build_status_reports_running_state(signed_in):
    status, headers, raw = signed_in["bob"].request("GET", "/api/build/status")
    assert status == 200 and "set-cookie" not in headers
    assert json.loads(raw)["build_running"] is False


def test_logout_stops_the_users_worker_and_gateway_exit_stops_the_rest(gateway, signed_in):
    alice_pid, bob_pid = _port_info(gateway, "alice")["pid"], _port_info(gateway, "bob")["pid"]
    assert _pid_alive(alice_pid) and _pid_alive(bob_pid)
    status, body = signed_in["alice"].json("POST", "/api/auth/logout", {})  # her last session
    assert status == 200, body
    deadline = time.time() + 30
    while time.time() < deadline and _pid_alive(alice_pid):
        time.sleep(0.5)
    assert not _pid_alive(alice_pid), "alice's worker still runs after she signed out"
    assert _pid_alive(bob_pid)
    gateway["proc"].terminate()  # TerminateProcess: no clean-up code runs, only the kill-on-close jobs
    gateway["proc"].wait(timeout=20)
    deadline = time.time() + 15
    while time.time() < deadline and _pid_alive(bob_pid):
        time.sleep(0.5)
    assert not _pid_alive(bob_pid), "bob's worker outlived the gateway"
