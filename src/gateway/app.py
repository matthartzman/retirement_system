"""The gateway app: the gate (Host, Origin, CSRF, session, two-factor stage, role), sign-in, admin and pages.

Everything not owned by the gateway (``/login``, ``/gateway/*``, ``/api/auth/*``) goes to the
``Upstream`` after the gate has authenticated it; see ``upstream.py`` and
``documentation/future/multi-user-server-gateway-design.md``.
"""
from __future__ import annotations

import hmac
import json
import logging
import math
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import quote

import segno
from src.access_core import FailureThrottle, KeyedThrottle, has_proxy_headers, is_loopback_host
from src.http_runtime.wsgi_facade import Flask, HeaderMap, LocalRequest, Response, request

from . import totp
from .store import Actor, GatewayStore, HashBusyError, LastAdminError
from .upstream import Identity, PlaceholderUpstream, Upstream

LOG = logging.getLogger("retirement.gateway")
COOKIE_NAME = "__Host-rp_session"
PAGES_DIR = Path(__file__).resolve().parent / "pages"
PAGES = {"login": "login.html", "enrol": "enrol.html", "account": "account.html", "users": "users.html"}
STATIC = {"gateway.js": "text/javascript; charset=utf-8", "gateway.css": "text/css; charset=utf-8"}
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
BODY_TYPES = frozenset({"application/json", "text/plain"})
# data: images only for the enrolment QR code, which is drawn here as an SVG data URI (no remote images).
CSP = "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'"
QR_SCALE, QR_BORDER = 5, 4
PUBLIC = frozenset({("GET", "/login"), ("POST", "/api/auth/login"), ("GET", "/api/auth/session")})
PENDING_ALLOWED = frozenset({"/api/auth/totp/enrol/start", "/api/auth/totp/enrol/confirm", "/api/auth/totp/verify",
                             "/api/auth/logout", "/gateway/enrol"})
MUST_CHANGE_ALLOWED = frozenset({"/api/auth/password", "/api/auth/logout", "/api/auth/session", "/gateway/account"})
LOGIN_ERROR = "Incorrect username or password, or the account is temporarily locked."
CODE_ERROR = "That code is not right. Check the time on your phone and try the newest code."


@dataclass(frozen=True)
class GatewayConfig:
    public_origins: tuple[str, ...] = ()  # e.g. "https://<node>.ts.net:8443"; the Funnel listener's allowed Origins
    throttle_window: float = 600.0
    ip_free_failures: int = 10
    ip_max_delay: float = 300.0
    global_free_failures: int = 50
    global_max_delay: float = 60.0
    # P7-O3: bodies the gateway itself reads (login, two-factor, password, admin forms) are small. Only a request
    # that passed the gate and is forwarded to a worker may carry a plan upload.
    max_body_bytes: int = 32 * 1024
    proxy_body_bytes: int = 64 * 1024 * 1024


class GatewayLifecycle(Protocol):
    """Told about account changes after the store change succeeded (Phase 3: the supervisor, which
    starts and stops workers and manages each user's Windows account)."""

    def user_created(self, user_id: int) -> None: ...
    def user_disabled(self, user_id: int, disabled: bool) -> None: ...
    def user_deleted(self, user_id: int) -> None: ...
    def signed_out(self, user_id: int, sessions_left: int) -> None: ...


PREFLIGHT_OK_HEADER = "X-Gateway-Preflight"


class GatewayListener:
    """Tags each request with the listener it arrived on ("funnel" or "local") and that listener's port."""

    def __init__(self, app: Flask, kind: str, port: int) -> None:
        if kind not in ("funnel", "local"):
            raise ValueError("listener must be funnel or local")
        self.app, self.kind, self.port = app, kind, int(port)

    def preflight(self, method: str, target: str, headers: dict | None = None,
                  remote_addr: str = "127.0.0.1") -> tuple[Response | None, int]:
        """Run the gate on the request line and headers alone, before any body is read (P7-O3).

        ``(refusal, 0)`` when the request must be refused as it stands, else ``(None, limit)``: the largest body
        the server may then read for it."""
        req = LocalRequest(method, target, HeaderMap(headers or {}), b"", remote_addr=remote_addr,
                           environ={"listener": self.kind, "listener_port": self.port, "gateway_preflight": True})
        resp = self.app.dispatch_request(req)
        if resp.headers.get(PREFLIGHT_OK_HEADER) == "ok":
            return None, int(req.environ["gateway_body_limit"])
        return resp, 0

    def handle_http(self, method: str, target: str, headers: dict | None = None, body: bytes = b"",
                    remote_addr: str = "127.0.0.1") -> Response:
        req = LocalRequest(method, target, HeaderMap(headers or {}), body, remote_addr=remote_addr,
                           environ={"listener": self.kind, "listener_port": self.port})
        return self.app.dispatch_request(req)


def safe_next(value: str | None) -> str:
    """``value`` when it is a same-site absolute path (not the login page), else "/"."""
    v = str(value or "")
    if (not v.startswith("/") or v.startswith("//") or v.startswith("/\\") or "\\" in v
            or any(ord(c) < 0x20 or ord(c) == 0x7F for c in v)):
        return "/"
    if v == "/login" or v.startswith("/login?"):
        return "/"
    return v


def qr_svg_data_uri(text: str) -> str:
    """``text`` as a QR code (error correction M), drawn on this machine as an SVG data URI."""
    return segno.make(text, error="m", micro=False).svg_data_uri(scale=QR_SCALE, border=QR_BORDER)


def _json(payload: dict, status: int = 200) -> Response:
    return Response(json.dumps(payload), status=status, content_type="application/json")


def _redirect(location: str) -> Response:
    resp = Response(b"", status=302)
    resp.headers["Location"] = location
    return resp


def _session_cookie(token: str) -> str:
    return f"{COOKIE_NAME}={token}; Path=/; Secure; HttpOnly; SameSite=Strict"


def _clear_cookie() -> str:
    return f"{COOKIE_NAME}=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Strict"


def _client_ip() -> str:
    """Right-most X-Forwarded-For entry on the Funnel listener (added by Funnel itself); the socket address otherwise."""
    if request.environ.get("listener") == "funnel":
        forwarded = str(request.headers.get("X-Forwarded-For", "") or "")
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1][:64]
    return str(request.remote_addr or "")[:64]


def _is_gateway_path(path: str) -> bool:
    return path == "/login" or path.startswith("/gateway/") or path.startswith("/api/auth/")


def create_gateway_app(store: GatewayStore, *, config: GatewayConfig | None = None, upstream: Upstream | None = None,
                       clock: Callable[[], float] = time.time, lifecycle: GatewayLifecycle | None = None,
                       health: Callable[[], dict] | None = None) -> Flask:
    cfg = config or GatewayConfig()
    up: Upstream = upstream or PlaceholderUpstream()
    app = Flask("retirement_gateway")
    ip_throttle = KeyedThrottle(cfg.throttle_window, cfg.ip_free_failures, cfg.ip_max_delay)
    global_throttle = FailureThrottle(cfg.throttle_window, cfg.global_free_failures, cfg.global_max_delay)
    page_cache: dict[str, str] = {}

    def _notify(event: str, user_id: int, *args) -> str | None:
        """Run a lifecycle hook; a failure is logged and audited, never shown with details."""
        if lifecycle is None:
            return None
        try:
            getattr(lifecycle, event)(user_id, *args)
        except Exception:
            LOG.exception("lifecycle hook %s failed for user %s", event, user_id)
            store.audit("worker cleanup failed" if event == "user_deleted" else f"{event.replace('_', ' ')} hook failed",
                        now=clock(), actor=_actor(), target_user_id=user_id)
            return "The account change was saved, but the server could not finish preparing or cleaning up the user's workspace."
        return None

    def _page(name: str) -> Response:
        if name not in page_cache:
            page_cache[name] = (PAGES_DIR / name).read_text(encoding="utf-8")
        ctype = STATIC.get(name, "text/html; charset=utf-8")
        return Response(page_cache[name], content_type=ctype)

    def _actor(user_id: int | None = None, username: str = "") -> Actor:
        ident: Identity | None = request.environ.get("gateway_identity")
        if ident is not None and user_id is None:
            user_id, username = ident.user_id, ident.username
        return Actor(user_id, username, request.environ.get("client_ip", ""), request.environ.get("listener", "local"))

    def _unauthenticated(path: str) -> Response:
        if path.startswith("/api/"):
            return _json({"success": False, "authenticated": False, "error": "sign in required"}, 401)
        raw = request.full_path
        nxt = safe_next(raw)
        return _redirect("/login" if nxt != raw else "/login?next=" + quote(nxt, safe=""))

    def _refused(message: str, status: int = 403) -> Response:
        return _json({"success": False, "error": message}, status)

    @app.before_request
    def _gate():
        verdict = _run_gate()
        if request.environ.get("gateway_preflight") and verdict is None:
            return Response(b"", status=204, headers={PREFLIGHT_OK_HEADER: "ok"})
        return verdict

    def _run_gate():
        env = request.environ
        env["gateway_body_limit"] = cfg.max_body_bytes
        listener = env.setdefault("listener", "local")
        port = int(env.get("listener_port") or 0)
        path, method = request.path, request.method
        env["client_ip"] = _client_ip()
        if listener == "local":
            if not is_loopback_host(str(request.headers.get("Host", "") or "")):
                return _refused("misdirected request", 421)
            if has_proxy_headers(request.headers):
                return _refused("proxied requests are not allowed on this listener")
            allowed = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
        else:
            allowed = set(cfg.public_origins)
        if str(request.headers.get("Sec-Fetch-Site", "") or "").lower() == "cross-site":
            return _refused("cross-site requests are not allowed")
        unsafe = method in UNSAFE_METHODS
        if unsafe:
            origin = str(request.headers.get("Origin", "") or "").rstrip("/")
            if origin not in allowed:
                return _refused("cross-origin requests are not allowed")
            if path.startswith("/api/") and request.get_data():
                ctype = str(request.headers.get("Content-Type", "") or "").split(";", 1)[0].strip().lower()
                if ctype not in BODY_TYPES:
                    return _refused("unsupported Content-Type")
        now = clock()
        if str(request.headers.get("Cookie", "") or "").count(COOKIE_NAME + "=") > 1:
            # Two session cookies: the cookie parser would silently pick one. Refuse instead of guessing.
            return _refused("more than one session cookie", 400)
        token = request.cookies.get(COOKIE_NAME)
        sess = store.get_session(token, now) if token else None
        env["session"], env["session_token"] = sess, token if sess else None
        if (method, path) in PUBLIC or (method == "GET" and path.startswith("/gateway/static/")):
            return None
        if sess is None:
            return _unauthenticated(path)
        sent = str(request.headers.get("X-CSRF-Token", "") or "")
        if unsafe and not (sent and hmac.compare_digest(sent, sess["csrf_token"])):
            return _refused("missing or invalid CSRF token")
        if sess["stage"] != "active":
            if path in PENDING_ALLOWED:
                return None
            if path.startswith("/api/"):
                return _json({"success": False, "authenticated": False, "error": "finish two-factor sign-in"}, 401)
            if store.totp_status(sess["user_id"]) != "enrolled":
                return _redirect("/gateway/enrol")
            return _unauthenticated(path)
        store.touch_session(token, now)
        ident = Identity(sess["user_id"], sess["username"], sess["display_name"], sess["role"])
        env["gateway_identity"] = ident
        if sess["must_change"] and path not in MUST_CHANGE_ALLOWED:
            if path.startswith("/api/"):
                return _json({"success": False, "must_change": True, "error": "choose a new password first"}, 409)
            return _redirect("/gateway/account")
        if (path.startswith("/api/auth/admin/") or path == "/gateway/users") and not ident.is_admin:
            return _refused("admins only")
        if _is_gateway_path(path):
            return None
        env["gateway_body_limit"] = cfg.proxy_body_bytes
        if env.get("gateway_preflight"):
            return None
        return up.forward(request._get(), ident)  # the Phase 3 seam

    @app.after_request
    def _headers(resp: Response) -> Response:
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        if request.environ.get("listener") == "funnel":
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        if _is_gateway_path(request.path) or resp.status_code in (302, 401, 403, 409, 421, 429):
            resp.headers["Cache-Control"] = "no-store"
            resp.headers["X-Frame-Options"] = "DENY"
            resp.headers["Referrer-Policy"] = "no-referrer"
            resp.headers["Content-Security-Policy"] = CSP
        return resp

    @app.errorhandler(Exception)
    def _unhandled(exc):
        error_id = secrets.token_hex(6)
        LOG.error("gateway error %s", error_id, exc_info=exc)
        return _json({"success": False, "error": "Something went wrong.", "error_id": error_id}, 500)

    # Registered after the catch-all: handlers are tried newest first.
    @app.errorhandler(HashBusyError)
    def _hash_busy(_exc):
        resp = _refused("The server is busy. Try again in a moment.", 503)
        resp.headers["Retry-After"] = "5"
        return resp

    # ---- pages ----
    @app.route("/login", methods=["GET"])
    def login_page():
        sess = request.environ.get("session")
        if sess and sess["stage"] == "active":
            return _redirect(safe_next(request.args.get("next")))
        return _page(PAGES["login"])

    @app.route("/gateway/enrol", methods=["GET"])
    def enrol_page():
        sess = request.environ["session"]
        if sess["stage"] == "active" or store.totp_status(sess["user_id"]) == "enrolled":
            return _redirect("/")
        return _page(PAGES["enrol"])

    @app.route("/gateway/account", methods=["GET"])
    def account_page():
        return _page(PAGES["account"])

    @app.route("/gateway/users", methods=["GET"])
    def users_page():
        return _page(PAGES["users"])

    @app.route("/gateway/static/<name>", methods=["GET"])
    def static_file(name: str):
        if name not in STATIC:
            return _refused("Not found", 404)
        return _page(name)

    # ---- sign-in ----
    def _throttled(now: float) -> Response | None:
        ip = request.environ["client_ip"]
        wait = max(ip_throttle.retry_after(ip, now), global_throttle.retry_after(now))
        if wait <= 0:
            return None
        store.audit("login throttled", now=now, actor=_actor(), details=f"{math.ceil(wait)} s")
        resp = _refused("Too many attempts. Try again shortly.", 429)
        resp.headers["Retry-After"] = str(max(1, math.ceil(wait)))
        return resp

    def _count_failure(now: float) -> None:
        ip_throttle.record(request.environ["client_ip"], now)
        global_throttle.record(now)

    @app.route("/api/auth/login", methods=["POST"])
    def login():
        now = clock()
        refused = _throttled(now)
        if refused is not None:
            return refused
        body = request.get_json(silent=True) or {}
        username = str(body.get("username") or "").strip().lower()[:64]
        check = store.verify_password(username, str(body.get("password") or ""), now)
        if not check.ok:
            _count_failure(now)
            event = "account locked" if check.reason == "locked" else "login failed"
            store.audit(event, now=now, actor=_actor(check.user_id, username), details=f"reason {check.reason}")
            return _refused(LOGIN_ERROR, 401)
        old = request.environ.get("session_token")
        if old:
            store.end_session(old)
        token, csrf = store.create_session(check.user_id, "pending", now, request.environ["client_ip"])
        store.audit("password accepted", now=now, actor=_actor(check.user_id, username))
        resp = _json({"success": True, "next": "totp" if store.totp_status(check.user_id) == "enrolled" else "enrol",
                      "csrf_token": csrf})
        resp.headers["Set-Cookie"] = _session_cookie(token)
        return resp

    def _pending_user() -> tuple[dict, str] | Response:
        sess = request.environ["session"]
        if sess["stage"] != "pending":
            return _refused("already signed in", 409)
        return sess, request.environ["session_token"]

    def _promote(sess: dict, token: str, now: float, event: str) -> Response:
        new_token, csrf = store.rotate_session(token, "active", now)
        store.touch_login(sess["user_id"], now)
        actor = _actor(sess["user_id"], sess["username"])
        store.audit(event, now=now, actor=actor)
        store.audit("login succeeded", now=now, actor=actor)
        resp = _json({"success": True, "csrf_token": csrf})
        resp.headers["Set-Cookie"] = _session_cookie(new_token)
        return resp

    def _code_failed(sess: dict, now: float) -> Response:
        _count_failure(now)
        locked = store.record_failure(sess["user_id"], now)
        actor = _actor(sess["user_id"], sess["username"])
        store.audit("totp failed", now=now, actor=actor)
        if locked:
            store.audit("account locked", now=now, actor=actor, details="reason totp")
            store.end_session(request.environ["session_token"])
            resp = _json({"success": False, "authenticated": False, "error": LOGIN_ERROR}, 401)
            resp.headers["Set-Cookie"] = _clear_cookie()
            return resp
        return _refused(CODE_ERROR, 400)

    def _code_step(enrolled: bool, event: str) -> Response:
        pending = _pending_user()
        if isinstance(pending, Response):
            return pending
        sess, token = pending
        now = clock()
        refused = _throttled(now)
        if refused is not None:
            return refused
        if store.is_locked(sess["user_id"], now):
            store.end_session(token)
            return _json({"success": False, "authenticated": False, "error": LOGIN_ERROR}, 401)
        if (store.totp_status(sess["user_id"]) == "enrolled") != enrolled:
            return _refused("wrong two-factor step", 409)
        code = str((request.get_json(silent=True) or {}).get("code") or "")
        ok = (store.verify_totp if enrolled else store.confirm_totp)(sess["user_id"], code, now)
        return _promote(sess, token, now, event) if ok else _code_failed(sess, now)

    @app.route("/api/auth/totp/verify", methods=["POST"])
    def totp_verify():
        return _code_step(True, "totp verified")

    @app.route("/api/auth/totp/enrol/confirm", methods=["POST"])
    def totp_enrol_confirm():
        return _code_step(False, "totp enrolled")

    @app.route("/api/auth/totp/enrol/start", methods=["POST"])
    def totp_enrol_start():
        pending = _pending_user()
        if isinstance(pending, Response):
            return pending
        sess, _token = pending
        try:
            secret = store.begin_totp_enrolment(sess["user_id"], clock())
        except ValueError as exc:
            return _refused(str(exc), 409)
        uri = totp.provisioning_uri(secret, sess["username"])
        return _json({"success": True, "secret": secret, "otpauth_uri": uri, "qr_svg_data_uri": qr_svg_data_uri(uri)})

    @app.route("/api/auth/logout", methods=["POST"])
    def logout():
        sess = request.environ["session"]
        store.end_session(request.environ["session_token"])
        store.audit("logout", now=clock(), actor=_actor(sess["user_id"], sess["username"]))
        _notify("signed_out", sess["user_id"], store.count_user_sessions(sess["user_id"], clock()))
        resp = _json({"success": True, "logged_out": True})
        resp.headers["Set-Cookie"] = _clear_cookie()
        return resp

    @app.route("/api/auth/session", methods=["GET"])
    def session_info():
        sess = request.environ.get("session")
        if not sess:
            return _json({"success": False, "authenticated": False}, 401)
        return _json({
            "success": True, "authenticated": sess["stage"] == "active", "stage": sess["stage"],
            "csrf_token": sess["csrf_token"],
            "user": {"id": sess["user_id"], "username": sess["username"], "display_name": sess["display_name"],
                     "role": sess["role"], "must_change": bool(sess["must_change"])},
        })

    @app.route("/api/auth/password", methods=["POST"])
    def change_password():
        ident: Identity = request.environ["gateway_identity"]
        body = request.get_json(silent=True) or {}
        now = clock()
        if not store.check_current_password(ident.user_id, str(body.get("current") or "")):
            _count_failure(now)
            store.record_failure(ident.user_id, now)
            return _refused("Your current password is not right.", 400)
        try:
            store.set_password(ident.user_id, str(body.get("new") or ""), must_change=False, now=now, actor=_actor(),
                               event="password changed", keep_session=request.environ["session_token"])
        except ValueError as exc:
            return _refused(str(exc), 400)
        return _json({"success": True})

    # ---- admin (the gate has already checked the role) ----
    def _admin_call(fn: Callable[[], object], after: Callable[[object], str | None] | None = None) -> Response:
        try:
            result = fn()
        except LastAdminError as exc:
            return _json({"success": False, "last_admin": True, "error": str(exc)}, 409)
        except LookupError:
            return _refused("no such user", 404)
        except ValueError as exc:
            return _refused(str(exc), 400)
        warning = after(result) if after is not None else None
        extra = {"warning": warning} if warning else {}
        return _json({"success": True, **(result if isinstance(result, dict) else {}), **extra})

    def _body() -> dict:
        body = request.get_json(silent=True)
        return body if isinstance(body, dict) else {}

    @app.route("/api/auth/admin/users", methods=["GET"])
    def admin_users():
        return _json({"success": True, "users": store.list_users(now=clock())})

    @app.route("/api/auth/admin/users", methods=["POST"])
    def admin_create_user():
        b = _body()
        return _admin_call(lambda: {"id": store.create_user(
            str(b.get("username") or ""), str(b.get("display_name") or ""), str(b.get("role") or "user"),
            str(b.get("temp_password") or ""), now=clock(), actor=_actor(), must_change=True)},
            after=lambda r: _notify("user_created", r["id"]))

    @app.route("/api/auth/admin/users/<int:uid>/role", methods=["POST"])
    def admin_role(uid: int):
        role = str(_body().get("role") or "")
        return _admin_call(lambda: store.set_role(uid, role, now=clock(), actor=_actor()))

    @app.route("/api/auth/admin/users/<int:uid>/disabled", methods=["POST"])
    def admin_disabled(uid: int):
        disabled = _body().get("disabled")
        if not isinstance(disabled, bool):
            return _refused("disabled must be true or false", 400)
        return _admin_call(lambda: store.set_disabled(uid, disabled, now=clock(), actor=_actor()),
                           after=lambda _r: _notify("user_disabled", uid, disabled))

    @app.route("/api/auth/admin/users/<int:uid>/delete", methods=["POST"])
    def admin_delete(uid: int):
        return _admin_call(lambda: store.delete_user(uid, now=clock(), actor=_actor()),
                           after=lambda _r: _notify("user_deleted", uid))

    @app.route("/api/auth/admin/users/<int:uid>/unlock", methods=["POST"])
    def admin_unlock(uid: int):
        return _admin_call(lambda: store.unlock(uid, now=clock(), actor=_actor()))

    @app.route("/api/auth/admin/users/<int:uid>/reset-password", methods=["POST"])
    def admin_reset_password(uid: int):
        temp = str(_body().get("temp_password") or "")
        return _admin_call(lambda: store.set_password(uid, temp, must_change=True, now=clock(), actor=_actor(),
                                                      event="password reset"))

    @app.route("/api/auth/admin/users/<int:uid>/reset-totp", methods=["POST"])
    def admin_reset_totp(uid: int):
        return _admin_call(lambda: store.reset_totp(uid, now=clock(), actor=_actor()))

    @app.route("/api/auth/admin/health", methods=["GET"])
    def admin_health():
        """Admin-only (the gate above): loopback proves nothing behind Funnel, and workers can reach loopback."""
        try:
            payload = health() if health is not None else {"status": "unknown", "warnings": ["health provider not connected"]}
        except Exception:
            LOG.exception("health report failed")
            return _json({"success": False, "error": "the health report could not be built"}, 500)
        return _json({"success": True, **payload})

    @app.route("/api/auth/admin/audit", methods=["GET"])
    def admin_audit():
        try:
            limit = int(request.args.get("limit") or 200)
        except (TypeError, ValueError):
            limit = 200
        return _json({"success": True, "events": store.read_audit(limit=limit)})

    return app
