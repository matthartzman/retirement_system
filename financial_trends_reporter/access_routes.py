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

VIEWS = {"trends", "live", "accounts", "people", "activity"}
# POST path -> (event, details from the JSON body). Amounts are never logged.
ACTIONS = {
    "/api/account": ("account edit", lambda b: " ".join(str(b.get(k)) for k in ("account_key", "type", "app_account") if b.get(k) is not None)),
    "/api/account-prefs": ("account preferences", lambda b: f"{len(b['items']) if isinstance(b.get('items'), list) else 0} items"),
    "/api/passthrough-decision": ("passthrough decision", lambda b: f"{b.get('key')} {b.get('decision')}"),
    "/api/run-now": ("update started", lambda b: ""),
    "/api/run-cancel": ("run cancelled", lambda b: ""),
}
COOKIE = "trends_session"
OWNER_NAME = "owner (PC)"
ACCESS_JS_PATH = Path(__file__).resolve().parent / "frontend" / "access.js"
CHANGE_PASSWORD_HTML_PATH = Path(__file__).resolve().parent / "frontend" / "change_password.html"
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
    def _log(event: str, details: str = "", person: str | None = None) -> None:
        env = request.environ
        source = str(request.headers.get("X-Forwarded-For", "") or "").split(",")[0].strip() if current_listener() == "remote" else ""
        store.log_event(person or env.get("person") or "(not signed in)", current_listener(), event, details, source, now=clock())

    def _log_timeouts() -> None:
        while sessions.expired_user_ids:
            user = store.get_user(sessions.expired_user_ids.pop())
            if user:
                _log("session timed out", person=user["display_name"])

    def _log_action() -> None:
        if request.method == "POST" and request.path in ACTIONS:
            event, describe = ACTIONS[request.path]
            _log(event, describe(request.get_json(silent=True) or {}))

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
            _log_action()
            return None
        # ---- remote ----
        if _owner_only(path):
            return _json({"success": False, "error": "Not found"}, 404)
        if (request.method, path) in PUBLIC_REMOTE:
            return None
        token = request.cookies.get(COOKIE)
        sess = sessions.get(token)
        _log_timeouts()
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
        if user["must_change"] and path == "/":
            resp = Response(b"", status=302)
            resp.headers["Location"] = "/change-password"
            return resp
        if user["must_change"] and path.startswith("/api/") and path not in MUST_CHANGE_ALLOWED:
            return _json({"success": False, "must_change": True, "error": "choose a new password first"}, 409)
        _log_action()
        return None

    @app.route("/signin", methods=["GET"])
    def signin_page():
        return Response(SIGNIN_HTML_PATH.read_text(encoding="utf-8"), content_type="text/html; charset=utf-8")

    @app.route("/change-password", methods=["GET"])
    def change_password_page():
        return Response(CHANGE_PASSWORD_HTML_PATH.read_text(encoding="utf-8"), content_type="text/html; charset=utf-8")

    @app.route("/api/signin", methods=["POST"])
    def signin():
        body = request.get_json(silent=True) or {}
        now = clock()
        delay = store.global_delay(now)
        if delay and now - store.last_failure_at() < delay:
            _log("sign-in throttled", person="(not signed in)")
            return _json({"success": False, "error": "Too many attempts. Try again shortly."}, 429, {"Retry-After": str(int(delay) + 1)})
        result = store.verify_login(str(body.get("username") or ""), str(body.get("password") or ""), now)
        attempted = str(body.get("username") or "")[:64]
        if result.reason == "locked":
            _log("locked out", attempted, person="(not signed in)")
            return _json({"success": False, "error": "Too many attempts. Try again in a few minutes."}, 429, {"Retry-After": "900"})
        if not result.ok:
            _log("sign-in failed", attempted, person="(not signed in)")
            return _json({"success": False, "error": "Incorrect username or password."}, 401)
        store.touch_last_signin(result.user_id, now)
        token = sessions.create(result.user_id)
        _log("signed in", person=store.get_user(result.user_id)["display_name"])
        resp = _json({"success": True, "must_change": result.must_change})
        resp.set_cookie(COOKIE, token, secure=True, httponly=True, samesite="Strict", path="/")
        return resp

    @app.route("/api/signout", methods=["POST"])
    def signout():
        resp = _json({"success": True})
        if current_listener() == "remote":
            if request.environ.get("token"):
                _log("signed out")
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
        _log("password changed")
        return _json({"success": True})

    @app.route("/api/view", methods=["POST"])
    def view():
        name = str((request.get_json(silent=True) or {}).get("view") or "")
        if name not in VIEWS:
            return _json({"success": False, "error": "unknown view"}, 400)
        _log("view opened", name)
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

    # ---- owner-only (the gate answers 404 for these on the remote listener) ----
    @app.route("/access.js", methods=["GET"])
    def access_js():
        return Response(ACCESS_JS_PATH.read_text(encoding="utf-8"), content_type="text/javascript; charset=utf-8")

    @app.route("/api/people", methods=["GET"])
    def people():
        return _json({"people": store.list_users(now=clock())})

    @app.route("/api/people", methods=["POST"])
    def add_person():
        body = request.get_json(silent=True) or {}
        try:
            uid = store.add_user(str(body.get("display_name") or ""), str(body.get("username") or ""),
                                 str(body.get("temp_password") or ""), now=clock())
        except ValueError as exc:
            return _json({"success": False, "error": str(exc)}, 400)
        _log("person added", str(body.get("username") or "").strip().lower())
        return _json({"success": True, "id": uid})

    def _person_from_body():
        body = request.get_json(silent=True) or {}
        try:
            uid = int(body.get("id"))
        except (TypeError, ValueError):
            return None, body
        return store.get_user(uid), body

    @app.route("/api/people/reset", methods=["POST"])
    def reset_person():
        user, body = _person_from_body()
        if user is None:
            return _json({"success": False, "error": "no such person"}, 404)
        try:
            store.set_password(user["id"], str(body.get("temp_password") or ""), must_change=True, now=clock())
        except ValueError as exc:
            return _json({"success": False, "error": str(exc)}, 400)
        sessions.end_user(user["id"])
        _log("password reset", user["username"])
        return _json({"success": True})

    @app.route("/api/people/delete", methods=["POST"])
    def delete_person():
        user, _body = _person_from_body()
        if user is None:
            return _json({"success": False, "error": "no such person"}, 404)
        store.delete_user(user["id"])
        sessions.end_user(user["id"])
        _log("person deleted", user["username"])
        return _json({"success": True})

    @app.route("/api/activity", methods=["GET"])
    def activity():
        def num(name):
            try:
                return float(request.args.get(name))
            except (TypeError, ValueError):
                return None
        return _json({"events": store.read_events(person=request.args.get("person") or None, since=num("from"), until=num("to"))})
