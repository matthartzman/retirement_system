"""Test rig for the multi-user gateway: an in-process app, two listeners, and a cookie-keeping browser."""
from __future__ import annotations

import json
from pathlib import Path

from src.gateway import totp
from src.gateway.app import GatewayConfig, GatewayListener, create_gateway_app
from src.gateway.store import Actor, GatewayStore
from src.http_runtime.wsgi_facade import Response

PW = "a long enough password"
PUBLIC_ORIGIN = "https://node.example.ts.net:8443"
PUBLIC_HOST = "node.example.ts.net:8443"
FUNNEL_PORT = 5065
LOCAL_PORT = 5064
CLI = Actor(None, "test")


def build_old_gateway_db(path: Path, version: int, users: tuple[tuple[str, str], ...] = (("ann", "user"),),
                         enrolled: tuple[str, ...] = ()) -> None:
    """A gateway.db exactly as an older gateway left it: the schema steps up to ``version`` and a few user rows.

    ``enrolled`` names users with a finished TOTP enrolment. Built from the migration list itself, so it is the same
    SQL an old gateway ran, not a later schema with columns dropped."""
    import sqlite3

    from src.gateway import store as gstore

    con = sqlite3.connect(path)
    try:
        for target, statements in gstore._MIGRATIONS:
            if target > version:
                break
            for sql in statements:
                con.execute(sql)
        con.execute(f"PRAGMA user_version = {int(version)}")
        for name, role in users:
            cur = con.execute("INSERT INTO users(username, display_name, role, pw_hash, pw_salt, scrypt_n, must_change,"
                              " created_at, updated_at) VALUES (?,?,?,?,?,?,0,1000,1000)",
                              (name, name.title(), role, b"x" * 32, b"s" * 16, 16))
            if name in enrolled:
                con.execute("INSERT INTO totp_secrets(user_id, secret, created_at, enrolled_at) VALUES (?,?,1000,1000)",
                            (cur.lastrowid, "JBSWY3DPEHPK3PXP"))
        con.commit()
    finally:
        con.close()


class RecordingUpstream:
    """Stands in for Phase 3's proxy: records what the gate let through."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []

    def forward(self, req, identity):
        self.calls.append((req.method, req.path, identity))
        return Response(json.dumps({"upstream": True, "user_id": identity.user_id}), status=200,
                        content_type="application/json")


class Rig:
    def __init__(self, tmp_path: Path, upstream="recording", insights=False, shared_views=False, **app_kwargs) -> None:
        self.now = [1_000_000.0]
        self.tmp_path = tmp_path
        self.store = GatewayStore(tmp_path / "gateway.db", scrypt_n=2**4)
        if upstream == "recording":
            self.upstream = RecordingUpstream()
        elif upstream is None:
            self.upstream = None
        else:
            self.upstream = upstream
        kwargs = {"upstream": self.upstream} if self.upstream is not None else {}
        kwargs.update(app_kwargs)
        cfg = GatewayConfig(public_origins=(PUBLIC_ORIGIN,), insights=insights or shared_views, shared_views=shared_views)
        self.app = create_gateway_app(self.store, config=cfg, clock=lambda: self.now[0], **kwargs)
        self.funnel = GatewayListener(self.app, "funnel", FUNNEL_PORT)
        self.local = GatewayListener(self.app, "local", LOCAL_PORT)

    def advance(self, seconds: float) -> None:
        self.now[0] += seconds

    def add_user(self, username="ann", role="user", must_change=False, password=PW) -> int:
        return self.store.create_user(username, username.title(), role, password, now=self.now[0], actor=CLI,
                                      must_change=must_change)

    def add_viewer(self, username="vic", sponsor: int | None = None, must_change=False, password=PW,
                   expires_at: float | None = None) -> int:
        """A viewer account (Phase 9), sponsored by ``sponsor`` (a member's id)."""
        assert sponsor is not None, "a viewer needs a sponsor"
        return self.store.create_viewer(username, username.title(), password, sponsor_user_id=sponsor,
                                        now=self.now[0], actor=CLI, must_change=must_change, expires_at=expires_at)

    def enrol(self, b: "Browser", uid: int) -> None:
        """Finish first sign-in for a browser holding a pending session: enrol TOTP, become active."""
        b.post("/api/auth/totp/enrol/start")
        r = b.post("/api/auth/totp/enrol/confirm", json={"code": self.code(uid)})
        assert r.status_code == 200, r.get_data(as_text=True)
        b.refresh_csrf()
        self.advance(31)

    def signed_in_viewer(self, username="vic", sponsor: int | None = None, ip="203.0.113.9") -> tuple["Browser", int]:
        """A browser with an active session for a new, enrolled viewer account."""
        uid = self.add_viewer(username, sponsor)
        b = self.browser(ip)
        assert b.login(username).status_code == 200
        self.enrol(b, uid)
        return b, uid

    def browser(self, ip="203.0.113.5", listener="funnel") -> "Browser":
        return Browser(self, ip, listener)

    def code(self, user_id: int) -> str:
        secret = self.store._totp_secret(user_id)
        return totp.code_at(secret, int(self.now[0] // 30))

    def signed_in(self, username="ann", role="user", ip="203.0.113.5") -> tuple["Browser", int]:
        """A browser with an active session for a new, enrolled account."""
        uid = self.add_user(username, role)
        b = self.browser(ip)
        b.login(username)
        b.post("/api/auth/totp/enrol/start")
        r = b.post("/api/auth/totp/enrol/confirm", json={"code": self.code(uid)})
        assert r.status_code == 200, r.get_data(as_text=True)
        b.refresh_csrf()
        self.advance(31)  # next TOTP step for whoever signs in next
        return b, uid


class Browser:
    def __init__(self, rig: Rig, ip: str, listener: str) -> None:
        self.rig, self.ip, self.listener = rig, ip, listener
        self.cookies: dict[str, str] = {}
        self.csrf = ""
        self.last_set_cookie = ""

    @property
    def origin(self) -> str:
        return PUBLIC_ORIGIN if self.listener == "funnel" else f"http://127.0.0.1:{LOCAL_PORT}"

    def request(self, method: str, path: str, json_body=None, headers=None, origin=True, csrf=True,
                body: bytes | None = None, content_type: str | None = None) -> Response:
        hdrs = {"Host": PUBLIC_HOST if self.listener == "funnel" else f"127.0.0.1:{LOCAL_PORT}"}
        remote_addr = "127.0.0.1"
        if self.listener == "funnel":
            hdrs["X-Forwarded-For"] = self.ip
        else:
            remote_addr = self.ip
        if method not in ("GET", "HEAD") and origin:
            hdrs["Origin"] = self.origin if origin is True else origin
        if method not in ("GET", "HEAD") and csrf and self.csrf:
            hdrs["X-CSRF-Token"] = self.csrf
        if self.cookies:
            hdrs["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        data = b""
        if json_body is not None:
            data = json.dumps(json_body).encode()
            hdrs["Content-Type"] = "application/json"
        elif body is not None:
            data = body
            if content_type:
                hdrs["Content-Type"] = content_type
        hdrs.update(headers or {})
        hdrs = {k: v for k, v in hdrs.items() if v is not None}
        target = self.rig.funnel if self.listener == "funnel" else self.rig.local
        resp = target.handle_http(method, path, hdrs, data, remote_addr=remote_addr)
        self._take_cookie(resp)
        return resp

    def _take_cookie(self, resp: Response) -> None:
        raw = str(resp.headers.get("Set-Cookie", "") or "")
        if not raw:
            return
        self.last_set_cookie = raw
        name, _, rest = raw.partition("=")
        value = rest.split(";", 1)[0]
        if "Max-Age=0" in raw or not value:
            self.cookies.pop(name, None)
        else:
            self.cookies[name] = value

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, json=None, **kw):
        return self.request("POST", path, json_body=json if json is not None else {}, **kw)

    def login(self, username="ann", password=PW, **kw) -> Response:
        r = self.post("/api/auth/login", json={"username": username, "password": password}, **kw)
        if r.status_code == 200:
            self.csrf = r.get_json()["csrf_token"]
        return r

    def refresh_csrf(self) -> None:
        r = self.get("/api/auth/session")
        self.csrf = r.get_json().get("csrf_token", "") if r.status_code == 200 else ""
