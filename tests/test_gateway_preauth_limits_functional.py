"""P7-O3: the gateway must not let an unauthenticated client exhaust memory, threads or CPU.

Real sockets against ``_GatewayHTTPServer`` with the in-process rig app behind it.
"""
from __future__ import annotations

import json
import socket
import threading
import time

import pytest

from src import access_core
from src.gateway import server
from src.gateway.app import GatewayListener
from src.gateway.store import Actor, GatewayStore, HashBusyError
from tests.gateway_rig import PUBLIC_HOST, PUBLIC_ORIGIN, Rig

MIB = 1024 * 1024


@pytest.fixture()
def rig(tmp_path):
    return Rig(tmp_path)


def _serve(rig, **kw):
    srv = server._GatewayHTTPServer(("127.0.0.1", 0), None, **kw)
    srv.retirement_app = GatewayListener(rig.app, "funnel", srv.server_address[1])
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


@pytest.fixture()
def serve(rig):
    servers = []

    def make(**kw):
        srv = _serve(rig, **kw)
        servers.append(srv)
        return srv

    yield make
    for s in servers:
        s.shutdown()
        s.server_close()


def _head(method, path, length, extra="", host=PUBLIC_HOST):
    return (f"{method} {path} HTTP/1.1\r\nHost: {host}\r\nOrigin: {PUBLIC_ORIGIN}\r\nX-Forwarded-For: 203.0.113.9\r\n"
            f"Content-Type: application/json\r\nContent-Length: {length}\r\n{extra}\r\n").encode()


def _status_of(srv, raw: bytes, timeout=3.0) -> int:
    """Send ``raw`` (headers only, the body is never sent) and return the status line's code."""
    s = socket.create_connection(srv.server_address, timeout=timeout)
    try:
        s.sendall(raw)
        data = b""
        while b"\r\n" not in data:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        return int(data.split(b" ", 2)[1])
    finally:
        s.close()


def _auth_headers(rig):
    b, _uid = rig.signed_in()
    return f"Cookie: {'; '.join(f'{k}={v}' for k, v in b.cookies.items())}\r\nX-CSRF-Token: {b.csrf}\r\n"


# (a) the gate runs on the headers, before any body is read
def test_unauthenticated_upload_is_refused_without_reading_the_body(serve):
    srv = serve()
    assert _status_of(srv, _head("POST", "/api/plan/import", 60 * MIB)) == 401


def test_cross_origin_post_is_refused_without_reading_the_body(serve):
    srv = serve()
    raw = _head("POST", "/api/auth/login", 100).replace(PUBLIC_ORIGIN.encode(), b"https://evil.example")
    assert _status_of(srv, raw) == 403


# (b) gateway-owned bodies are small; the proxied upload cap applies only after authentication
def test_login_body_over_the_cap_is_refused_before_it_is_read(serve):
    srv = serve()
    assert _status_of(srv, _head("POST", "/api/auth/login", 100 * 1024)) == 413


def test_authenticated_gateway_form_over_the_cap_is_refused(rig, serve):
    srv = serve()
    assert _status_of(srv, _head("POST", "/api/auth/password", 100 * 1024, _auth_headers(rig))) == 413


def test_authenticated_proxied_upload_may_exceed_the_gateway_cap(rig, serve):
    srv = serve()
    body = b'{"x":"' + b"a" * (200 * 1024) + b'"}'
    s = socket.create_connection(srv.server_address, timeout=5)
    s.sendall(_head("POST", "/api/plan/import", len(body), _auth_headers(rig)) + body)
    data = s.recv(4096)
    s.close()
    assert int(data.split(b" ", 2)[1]) == 200
    assert rig.upstream.calls and rig.upstream.calls[-1][1] == "/api/plan/import"


def test_proxied_upload_over_the_proxy_cap_is_refused_unread(rig, serve):
    srv = serve()
    assert _status_of(srv, _head("POST", "/api/plan/import", 65 * MIB, _auth_headers(rig))) == 413


def test_small_login_still_works_through_the_socket(rig, serve):
    rig.add_user("ann")
    srv = serve()
    body = json.dumps({"username": "ann", "password": "a long enough password"}).encode()
    s = socket.create_connection(srv.server_address, timeout=5)
    s.sendall(_head("POST", "/api/auth/login", len(body)) + body)
    assert int(s.recv(4096).split(b" ", 2)[1]) == 200
    s.close()


# (c) bounded connections, with a clear refusal
def test_connections_beyond_the_limit_get_a_503_and_free_up(serve):
    srv = serve(max_connections=2)
    held = [socket.create_connection(srv.server_address, timeout=3) for _ in range(2)]
    time.sleep(0.3)  # let the server accept and start both handler threads
    refused = socket.create_connection(srv.server_address, timeout=3)
    assert refused.recv(4096).startswith(b"HTTP/1.0 503")
    refused.close()
    held[0].close()
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            if _status_of(srv, _head("GET", "/login", 0)) == 200:
                break
        except (OSError, ValueError, IndexError):
            pass
        time.sleep(0.1)
    else:
        pytest.fail("the slot was not released after a client disconnected")
    held[1].close()


# (e) a total deadline, not a per-read timeout
def test_a_slow_sender_cannot_reset_the_read_deadline(serve):
    srv = serve(request_deadline=1.0)
    s = socket.create_connection(srv.server_address, timeout=5)
    started = time.monotonic()
    closed = False
    try:
        s.sendall(b"GET /login HTTP/1.1\r\nHost: x\r\n")
        while time.monotonic() - started < 6:
            time.sleep(0.25)  # well under any per-read timeout: each byte would reset it
            s.sendall(b"X-Slow: a\r\n")
    except OSError:
        closed = True
    assert closed, "server kept reading a slow request past the deadline"
    assert time.monotonic() - started < 4


# (d) a semaphore around password hashing
def _slow_hash(monkeypatch, delay=0.15):
    state = {"now": 0, "max": 0}
    lock = threading.Lock()
    real = access_core.hash_password

    def slow(password, salt, n):
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        try:
            time.sleep(delay)
            return real(password, salt, n)
        finally:
            with lock:
                state["now"] -= 1

    monkeypatch.setattr(access_core, "hash_password", slow)
    return state


def test_concurrent_password_checks_are_capped(tmp_path, monkeypatch):
    store = GatewayStore(tmp_path / "g.db", scrypt_n=2**4, hash_concurrency=2)
    store.create_user("ann", "Ann", "user", "a long enough password", now=1.0,
                      actor=Actor(None, "t"))
    state = _slow_hash(monkeypatch)
    threads = [threading.Thread(target=store.verify_password, args=("ann", "wrong password!!", 2.0)) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert state["max"] <= 2


def test_password_hash_wait_is_bounded_and_login_answers_503(rig, monkeypatch):
    rig.add_user("ann")
    rig.store._hash_wait = 0.05
    rig.store._hash_slots = threading.BoundedSemaphore(1)
    rig.store._hash_slots.acquire()  # every slot is busy
    with pytest.raises(HashBusyError):
        rig.store.verify_password("ann", "wrong password!!", 2.0)
    r = rig.browser().login("ann")
    assert r.status_code == 503 and r.headers.get("Retry-After")
