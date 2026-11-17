"""Hostile-client checks against a real gateway with two real users and an admin (same-account launcher, no elevation).

``test_multi_user_isolation_integration.py`` shows the happy-path isolation. This file attacks it: copied
sessions and CSRF tokens, forged Host and Origin, spoofed forwarding headers against the throttle, odd framing,
expiry, logout and disabling, and leakage of paths, ids, tokens and secrets into responses and logs. Run it once
per change (each module starts its own gateway and workers).
"""
from __future__ import annotations

import http.client
import re
import socket
import sqlite3
import time

import pytest

from test_multi_user_isolation_integration import (  # noqa: F401 - gateway is the module fixture
    HOME, PUBLIC_ORIGIN, PW, SHARED_KEY, Client, _pid_alive, _port_info, launch_gateway)

pytestmark = [pytest.mark.integration, pytest.mark.e2e]

BOB_HOME_VALUE = "$7,654,321"


@pytest.fixture(scope="module")
def gateway(tmp_path_factory):
    yield from launch_gateway(tmp_path_factory.mktemp("attacks"), {"alice": "user", "bob": "user", "root": "admin"})


def _mint(gateway, name: str, stage: str = "active") -> Client:
    """A client holding a fresh gateway session for ``name`` (made straight in gateway.db: codes are single-use)."""
    c = Client(gateway["ready"]["local_port"])
    token, csrf = gateway["store"].create_session(gateway["users"][name][0], stage, time.time(), "127.0.0.1")
    c.cookie, c.csrf = f"__Host-rp_session={token}", csrf
    return c


@pytest.fixture(scope="module")
def clients(gateway):
    out = {n: _mint(gateway, n) for n in ("alice", "bob", "root")}
    status, body = out["bob"].json("GET", "/api/config/rows")
    assert status == 200, body
    row = next(r for r in body["rows"] if (r["section"], r["subsection"], r["label"]) == HOME)
    status, body = out["bob"].json("POST", "/api/config/rows",
                                   {"updates": [{"row_index": row["row_index"], "value": BOB_HOME_VALUE}], "sync": True})
    assert status == 200 and body.get("updated") == 1, body
    return out


def _db(gateway) -> sqlite3.Connection:
    return sqlite3.connect(gateway["base"] / "gateway.db", timeout=10, isolation_level=None)


def test_a_copied_session_id_needs_the_matching_csrf_token_and_never_crosses_users(gateway, clients):
    alice, bob = clients["alice"], clients["bob"]
    thief = Client(gateway["ready"]["local_port"])
    thief.cookie = alice.cookie  # session id copied from Alice's browser
    status, body = thief.json("POST", "/api/config/rows", {"updates": [], "sync": True})
    assert status == 403, body  # no CSRF token: the cookie alone cannot change anything
    thief.csrf = bob.csrf  # Bob's token with Alice's cookie
    status, body = thief.json("POST", "/api/config/rows", {"updates": [], "sync": True})
    assert status == 403, body
    status, _h, raw = thief.request("GET", "/api/config/rows")
    assert status == 200 and BOB_HOME_VALUE.encode() not in raw  # Alice's cookie is only ever Alice
    for bad in ("", "x", "x" * 5000, alice.csrf[:-1]):
        status, body = thief.json("POST", "/api/config/rows", {"updates": [], "sync": True},
                                  headers={"X-CSRF-Token": bad}, csrf=False)
        assert status == 403, (bad[:10], body)


def test_missing_garbage_and_pending_sessions_reach_no_worker(gateway, clients):
    anon = Client(gateway["ready"]["local_port"])
    for path in ("/api/config/rows", "/api/ping", "/api/plan/download", "/files/anything", "/api/auth/admin/users"):
        status, _h, raw = anon.request("GET", path)
        assert status in (302, 401), (path, status)
        assert BOB_HOME_VALUE.encode() not in raw
    anon.cookie = "__Host-rp_session=" + "A" * 43
    assert anon.request("GET", "/api/config/rows")[0] == 401
    pending = _mint(gateway, "alice", "pending")
    for path in ("/api/config/rows", "/api/ping", "/api/plan/download"):
        assert pending.request("GET", path)[0] == 401, path
    assert pending.request("POST", "/api/config/rows", {"updates": []})[0] in (401, 403)


def test_idle_and_absolute_expiry_are_enforced_and_logout_kills_the_cookie(gateway):
    db = _db(gateway)
    now = time.time()
    idle, absolute, out = _mint(gateway, "alice"), _mint(gateway, "alice"), _mint(gateway, "alice")
    assert idle.request("GET", "/api/ping")[0] == 200
    db.execute("UPDATE sessions SET last_seen=? WHERE csrf_token=?", (now - 16 * 60, idle.csrf))
    assert idle.request("GET", "/api/ping")[0] == 401  # idle for over 15 minutes
    db.execute("UPDATE sessions SET expires_at=? WHERE csrf_token=?", (now - 1, absolute.csrf))
    assert absolute.request("GET", "/api/ping")[0] == 401  # past the 12 hour limit even though in use
    stale_cookie = out.cookie
    assert out.json("POST", "/api/auth/logout", {})[0] == 200
    replay = Client(gateway["ready"]["local_port"])
    replay.cookie = stale_cookie
    assert replay.request("GET", "/api/ping")[0] == 401  # the old cookie value is dead server-side
    db.close()


def test_forged_forwarding_headers_do_not_buy_extra_login_attempts(gateway):
    """On the Funnel listener only the right-most X-Forwarded-For entry (added by Funnel) counts."""
    c = Client(gateway["ready"]["funnel_port"], "funnel")
    codes = []
    for i in range(16):
        status, _h, _b = c.request("POST", "/api/auth/login", {"username": f"nobody{i}", "password": "x" * 14},
                                   headers={"X-Forwarded-For": f"10.9.8.{i}, 198.51.100.7"})
        codes.append(status)
    assert 429 in codes, codes  # the real client (right-most) ran out of free attempts despite 16 left-most values
    local = Client(gateway["ready"]["local_port"])
    status, _h, _b = local.request("POST", "/api/auth/login", {"username": "x", "password": "y"},
                                   headers={"X-Forwarded-For": "1.2.3.4"})
    assert status == 403  # proxy headers are refused outright on the local listener
    status, _h, _b = local.request("GET", "/api/auth/session", headers={"Tailscale-User-Login": "root@x"})
    assert status == 403


def _raw(port: int, payload: bytes, timeout: float = 15.0) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
        s.sendall(payload)
        chunks = []
        try:
            while True:
                data = s.recv(65536)
                if not data:
                    break
                chunks.append(data)
        except (socket.timeout, ConnectionResetError):
            pass
        return b"".join(chunks)


def test_request_smuggling_attempts_yield_one_response_and_no_second_request(gateway, clients):
    port = gateway["ready"]["local_port"]
    alice = clients["alice"]
    inner = (f"GET /api/config/rows HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nCookie: {clients['bob'].cookie}\r\n\r\n").encode()
    head = (f"POST /api/config/rows HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nOrigin: http://127.0.0.1:{port}\r\n"
            f"Cookie: {alice.cookie}\r\nX-CSRF-Token: {alice.csrf}\r\nContent-Type: application/json\r\n")
    variants = {
        "cl+te": head + "Content-Length: 4\r\nTransfer-Encoding: chunked\r\n\r\n",
        "te+cl": head + "Transfer-Encoding: chunked\r\nContent-Length: 4\r\n\r\n",
        "dup-cl": head + "Content-Length: 2\r\nContent-Length: 4\r\n\r\n",
        "te-obfuscated": head + "Transfer-Encoding : chunked\r\nContent-Length: 4\r\n\r\n",
        "bad-cl": head + "Content-Length: +4\r\n\r\n",
    }
    for name, h in variants.items():
        out = _raw(port, h.encode() + b"0\r\n\r\n" + inner)
        responses = re.findall(rb"(?m)^HTTP/1\.[01] \d+", out)  # status lines only (the Server header also says HTTP/1.0)
        assert len(responses) == 1, (name, responses)  # the tail was never run as a second request
        assert BOB_HOME_VALUE.encode() not in out, name


def test_duplicate_and_oversized_headers_and_bodies_are_refused_cleanly(gateway, clients):
    port = gateway["ready"]["local_port"]
    alice = clients["alice"]
    base = f"GET /api/ping HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
    out = _raw(port, (base + f"Cookie: {alice.cookie}\r\nCookie: {clients['bob'].cookie}\r\n\r\n").encode())
    assert out.startswith(b"HTTP/1.") and out.split(b"\r\n", 1)[0].split()[1][:1] != b"5", out[:200]
    assert BOB_HOME_VALUE.encode() not in out
    out = _raw(port, (base + "X-Big: " + "a" * 70000 + "\r\n\r\n").encode())
    assert out.split(b"\r\n", 1)[0].split()[1] in (b"400", b"431"), out[:200]
    big = f"POST /api/config/rows HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Length: {70 * 1024 * 1024}\r\n\r\n"
    # P7-O3: the gate now runs on the headers first, so this originless POST is refused (403) before its size is looked at
    assert _raw(port, big.encode()).split(b"\r\n", 1)[0].split()[1] in (b"403", b"413")
    neg = f"POST /api/config/rows HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Length: -5\r\n\r\n"
    # read as an empty body, then refused by the gate (no Origin): never accepted
    assert _raw(port, neg.encode()).split(b"\r\n", 1)[0].split()[1] in (b"400", b"403")


def test_cross_site_and_wrong_origin_requests_are_refused(clients):
    alice = clients["alice"]
    status, _h, _b = alice.request("GET", "/api/ping", headers={"Sec-Fetch-Site": "cross-site"})
    assert status == 403
    for origin in ("null", "http://127.0.0.1", "https://evil.example", PUBLIC_ORIGIN):
        status, body = alice.json("POST", "/api/config/rows", {"updates": [], "sync": True}, origin=origin)
        assert status == 403, (origin, body)  # PUBLIC_ORIGIN is only valid on the Funnel listener
    status, body = alice.json("POST", "/api/config/rows", {"updates": [], "sync": True}, origin=False)
    assert status == 403, body


def test_a_guessed_worker_port_refuses_every_token_shape(gateway, clients):
    port = _port_info(gateway, "bob")["port"]
    shapes = [{}, {"X-API-Token": ""}, {"X-API-Token": " "}, {"X-API-Token": "A" * 20000}, {"Authorization": "Bearer "},
              {"Authorization": "Basic Ym9iOg=="}, {"X-API-Token": "a", "Cookie": clients["bob"].cookie}]
    for headers in shapes:
        for path in ("/api/ping", "/api/config/rows", "/files/x", "/frontend/probe"):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
            try:
                conn.request("GET", path + "?token=guess&api_token=guess", headers=headers)
                resp = conn.getresponse()
                body = resp.read()
            except (ConnectionResetError, http.client.HTTPException):
                continue
            finally:
                conn.close()
            assert resp.status in (400, 401, 403, 421), (path, list(headers), resp.status)
            assert BOB_HOME_VALUE.encode() not in body


def test_logs_and_error_bodies_hold_no_secrets_tokens_or_other_users_data(gateway, clients):
    for c in clients.values():
        c.request("POST", "/api/config/rows", {"updates": "not-a-list"})
        c.request("POST", "/api/sales/999999/void", {})
    log = gateway["log"].read_text(encoding="utf-8", errors="replace")
    needles = [SHARED_KEY, PW] + [c.cookie.split("=", 1)[1] for c in clients.values()] + [c.csrf for c in clients.values()]
    needles += [secret for (_uid, secret) in gateway["users"].values()]
    for needle in needles:
        assert needle not in log, f"the gateway log holds a secret ({needle[:6]}...)"
    for name, other in (("alice", "bob"), ("bob", "alice")):
        wlog = gateway["data_root"] / "users" / str(gateway["users"][name][0]) / "local_state" / "logs" / "worker_console.log"
        if wlog.is_file():
            text = wlog.read_text(encoding="utf-8", errors="replace")
            assert SHARED_KEY not in text and PW not in text
            assert str(gateway["data_root"] / "users" / str(gateway["users"][other][0])) not in text


def test_disabling_a_user_ends_their_session_and_stops_their_worker(gateway, clients):
    root, bob = clients["root"], clients["bob"]
    bob_id = gateway["users"]["bob"][0]
    pid = _port_info(gateway, "bob")["pid"]
    assert _pid_alive(pid)
    status, body = root.json("POST", f"/api/auth/admin/users/{bob_id}/disabled", {"disabled": True})
    assert status == 200, body
    assert bob.request("GET", "/api/ping")[0] == 401  # the live session died with the account
    deadline = time.time() + 30
    while time.time() < deadline and _pid_alive(pid):
        time.sleep(0.5)
    assert not _pid_alive(pid), "bob's worker still runs after the account was disabled"
    fresh = Client(gateway["ready"]["local_port"])
    status, _body = fresh.json("POST", "/api/auth/login", {"username": "bob", "password": PW})
    assert status == 401
    root_id = gateway["users"]["root"][0]
    status, _body = clients["alice"].json("POST", f"/api/auth/admin/users/{root_id}/disabled", {"disabled": True})
    assert status == 403  # a non-admin cannot do this to anyone
