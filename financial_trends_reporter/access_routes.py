"""Auth gate and account routes for the two listeners.

Local (5057): no sign-in; Host must be loopback and proxy headers are refused. Remote (5058):
every request needs a session except the sign-in page and API; owner-only paths are 404.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from src.http_runtime.wsgi_facade import Response, request

from .access_store import AccessStore
from .listeners import current_listener, has_proxy_headers, is_loopback_host
from .sessions import SessionTable

COOKIE = "trends_session"
OWNER_NAME = "owner (PC)"
SIGNIN_HTML_PATH = Path(__file__).resolve().parent / "frontend" / "signin.html"
OWNER_ONLY_PREFIXES = ("/api/people", "/api/activity", "/access.js")
PUBLIC_REMOTE = {("GET", "/signin"), ("POST", "/api/signin")}
MUST_CHANGE_ALLOWED = {"/api/change-password", "/api/signout", "/api/whoami"}


def _json(payload, status=200, headers=None) -> Response:
    resp = Response(json.dumps(payload), status=status, content_type="application/json")
    if headers:
        resp.headers.update(headers)
    return resp


def register_access(app, store: AccessStore, sessions: SessionTable, clock=time.time) -> None:
    def _owner_only(path: str) -> bool:
        return any(path == p or path.startswith(p + "/") for p in OWNER_ONLY_PREFIXES)

    @app.before_request
    def _gate():
        env = request.environ
        path = request.path
        if current_listener() == "local":
            if not is_loopback_host(str(request.headers.get("Host", "") or "")):
                return _json({"success": False, "error": "misdirected request"}, 421)
            if has_proxy_headers(request.headers):
                return _json({"success": False, "error": "proxied requests are not allowed here"}, 403)
            env["person"] = OWNER_NAME
            return None
        # ---- remote ----
        if _owner_only(path):
            return _json({"success": False, "error": "Not found"}, 404)
        if (request.method, path) in PUBLIC_REMOTE:
            return None
        token = request.cookies.get(COOKIE)
        sess = sessions.get(token)
        user = store.get_user(sess.user_id) if sess else None
        if sess is None or user is None:
            if sess is not None:
                sessions.end(token)
            if path.startswith("/api/"):
                return _json({"success": False, "error": "sign in required"}, 401)
            resp = Response(b"", status=302)
            resp.headers["Location"] = "/signin"
            return resp
        env["token"], env["user"], env["person"] = token, user, user["display_name"]
        if user["must_change"] and path.startswith("/api/") and path not in MUST_CHANGE_ALLOWED:
            return _json({"success": False, "must_change": True, "error": "choose a new password first"}, 409)
        return None

    @app.route("/signin", methods=["GET"])
    def signin_page():
        return Response(SIGNIN_HTML_PATH.read_text(encoding="utf-8"), content_type="text/html; charset=utf-8")

    @app.route("/api/signin", methods=["POST"])
    def signin():
        body = request.get_json(silent=True) or {}
        now = clock()
        delay = store.global_delay(now)
        if delay and now - store.last_failure_at() < delay:
            return _json({"success": False, "error": "Too many attempts. Try again shortly."}, 429, {"Retry-After": str(int(delay) + 1)})
        result = store.verify_login(str(body.get("username") or ""), str(body.get("password") or ""), now)
        if result.reason == "locked":
            return _json({"success": False, "error": "Too many attempts. Try again in a few minutes."}, 429, {"Retry-After": "900"})
        if not result.ok:
            return _json({"success": False, "error": "Incorrect username or password."}, 401)
        store.touch_last_signin(result.user_id, now)
        token = sessions.create(result.user_id)
        resp = _json({"success": True, "must_change": result.must_change})
        resp.set_cookie(COOKIE, token, secure=True, httponly=True, samesite="Strict", path="/")
        return resp

    @app.route("/api/signout", methods=["POST"])
    def signout():
        resp = _json({"success": True})
        if current_listener() == "remote":
            sessions.end(request.environ.get("token"))
            resp.delete_cookie(COOKIE)
        return resp

    @app.route("/api/whoami", methods=["GET"])
    def whoami():
        user = request.environ.get("user")
        return _json({
            "listener": current_listener(),
            "name": request.environ.get("person", OWNER_NAME),
            "must_change": bool(user and user["must_change"]),
        })

    @app.route("/api/change-password", methods=["POST"])
    def change_password():
        user = request.environ.get("user")
        if user is None:
            return _json({"success": False, "error": "Only signed-in guests have a password."}, 400)
        body = request.get_json(silent=True) or {}
        if not store.check_current_password(user["id"], str(body.get("current") or "")):
            return _json({"success": False, "error": "Your current password is not right."}, 400)
        try:
            store.set_password(user["id"], str(body.get("new") or ""), must_change=False, now=clock())
        except ValueError as exc:
            return _json({"success": False, "error": str(exc)}, 400)
        return _json({"success": True})

    @app.route("/api/ping", methods=["POST"])
    def ping():
        token = request.environ.get("token")
        if token:
            body = request.get_json(silent=True) or {}
            try:
                idle_ms = int(float(body.get("idle_ms") or 0))
            except (TypeError, ValueError):
                idle_ms = 0
            sessions.note_interaction(token, idle_ms)
        return _json({"success": True})
