"""Auth gate and account routes for the two listeners.

Local (5057): no password sign-in, but every request needs the per-boot local token (src/http_runtime/local_token_gate.py); Host must
be loopback and proxy headers are refused. Remote (5058):
every request needs a session except the sign-in page and API; local-only paths are 404.

People live in the shared identity store (src/identity) and are managed in the Admin app. A remote session ends on the
next request when the person is disabled or expired, the Financial Insights grant is gone, or the session epoch moved.
"""
from __future__ import annotations

import json
import logging
import secrets
import time
from pathlib import Path
from typing import Callable

from src.http_runtime.wsgi_facade import Response, request

from src.http_runtime import security_headers
from src.identity import totp as totp_lib
from src.identity.store import IdentityStore
from src.secrets_store import SecretStoreUnavailable

from . import percent_view
from .listeners import current_listener, has_proxy_headers, is_loopback_host
from .sessions import SessionTable

INSIGHTS_VIEWS = ("live", "trends", "projections")  # the tabs a grant can limit; the Admin app offers the same list
VIEWS = set(INSIGHTS_VIEWS) | {"accounts"}
# Route rule -> the one tab whose panels call it (the page asks only while that tab exists). A grant that lists its tabs
# is refused every route of a tab it does not list, so a hidden tab's data cannot be read by URL. Every other /api/ rule
# belongs to no single tab and is named in TAB_FREE_ROUTES; a contract test fails on a rule in neither table.
VIEW_ROUTES: dict[str, str] = {
    "/api/history": "trends", "/api/balances": "trends", "/api/flows": "trends", "/api/liquid-change": "trends",
    "/api/spending": "trends", "/api/spending/transactions": "trends", "/api/account-prefs": "trends",
    "/api/passthrough-decision": "trends",
    "/api/live-snapshot": "live", "/api/realized": "live",
    "/api/projections": "projections",
}
TAB_FREE_ROUTES: frozenset[str] = frozenset({
    "/api/whoami", "/api/ping", "/api/view", "/api/run-status", "/api/run-now", "/api/run-cancel", "/api/exit",
    "/api/signin", "/api/signout", "/api/change-password", "/api/totp/begin", "/api/totp/confirm",
    "/api/totp/recovery-codes",
    "/api/accounts", "/api/app-accounts", "/api/account",  # the "accounts" view: account settings, no amounts
})
VIEW_REFUSED = "this view is not available to you"
READ_ONLY_REFUSED = "this view is read-only for guests"
# Guests are VIEW-ONLY (owner decision, security review F-01). Every POST route is classified in exactly one of these two
# sets; a contract test fails on a POST route in neither. The remote gate refuses a guest session any non-GET request
# that is not in GUEST_WRITABLE_POST. The owner's local listener is unchanged, and worker mode has its own deny-by-default
# allowlist (worker_allowlist.py; the plan owner edits their own per-plan store there, gateway viewers are refused).
OWNER_ONLY_POST: frozenset[str] = frozenset({
    "/api/account", "/api/account-prefs", "/api/passthrough-decision", "/api/run-now", "/api/run-cancel",
})
GUEST_WRITABLE_POST: frozenset[str] = frozenset({  # session management and no-op/log-only calls; none touch the owner's data
    "/api/signin", "/api/signout", "/api/change-password", "/api/totp/begin", "/api/totp/confirm",
    "/api/totp/recovery-codes", "/api/ping", "/api/view", "/api/exit",
})
# POST path -> (event, details from the JSON body). Amounts are never logged. Only the owner's local listener reaches
# these (OWNER_ONLY_POST below: guests are refused the writes before they are logged).
ACTIONS = {
    "/api/account": ("account edit", lambda b: " ".join(str(b.get(k)) for k in ("account_key", "type", "app_account") if b.get(k) is not None)),
    "/api/account-prefs": ("account preferences", lambda b: f"{len(b['items']) if isinstance(b.get('items'), list) else 0} items"),
    "/api/passthrough-decision": ("passthrough decision", lambda b: f"{b.get('key')} {b.get('decision')}"),
    "/api/run-now": ("update started", lambda b: ""),
    "/api/run-cancel": ("run cancelled", lambda b: ""),
}
COOKIE = "trends_session"
OWNER_NAME = "owner (PC)"
CHANGE_PASSWORD_HTML_PATH = Path(__file__).resolve().parent / "frontend" / "change_password.html"
SIGNIN_HTML_PATH = Path(__file__).resolve().parent / "frontend" / "signin.html"
LOCAL_ONLY_PREFIXES: tuple[str, ...] = ()  # paths the remote listener answers 404 for; none now that people live in the Admin app
PUBLIC_REMOTE = {("GET", "/signin"), ("POST", "/api/signin")}
MUST_CHANGE_ALLOWED = {"/api/change-password", "/api/signout", "/api/whoami"}
ENROL_ALLOWED = {"/api/totp/begin", "/api/totp/confirm", "/api/change-password", "/api/signout", "/api/whoami"}
TOTP_HTML_PATH = Path(__file__).resolve().parent / "frontend" / "totp.html"
# Percent-only people: this one route is refused, every other /api/ JSON body is scaled unless listed here.
WITHHELD_FOR_PERCENT = {"/api/spending/transactions"}
PASS_THROUGH_FOR_PERCENT = {"/api/whoami", "/api/ping", "/api/view", "/api/signin", "/api/signout", "/api/change-password",
                            "/api/run-status", "/api/run-cancel", "/api/passthrough-decision", "/api/account-prefs",
                            "/api/totp/begin", "/api/totp/confirm", "/api/totp/recovery-codes"}
PERCENT_MARK = percent_view.PERCENT_MARK


def _json(payload, status=200, headers=None) -> Response:
    resp = Response(json.dumps(payload), status=status, content_type="application/json")
    if headers:
        resp.headers.update(headers)
    return resp


def register_access(app, store: IdentityStore, sessions: SessionTable, clock=time.time,
                    percent_basis: Callable[[], float | None] = lambda: None, local_gate=None) -> None:
    if local_gate is not None:
        local_gate.register(app, is_local=lambda: current_listener() == "local")
    def _log(event: str, details: str = "", person: str | None = None) -> None:
        env = request.environ
        source = str(request.headers.get("X-Forwarded-For", "") or "").split(",")[0].strip() if current_listener() == "remote" else ""
        store.log_event(person or env.get("person") or "(not signed in)", current_listener(), event, details, source, now=clock())

    store.clear_app_sessions("insights")  # a restarted app holds no sessions; mirror rows from before are stale

    def _log_timeouts() -> None:
        while sessions.expired_user_ids:
            user = store.get_user(sessions.expired_user_ids.pop())
            if user:
                _log("session timed out", person=user["display_name"])

    def _log_action() -> None:
        if request.method == "POST" and request.path in ACTIONS:
            event, describe = ACTIONS[request.path]
            _log(event, describe(request.get_json(silent=True) or {}))

    def _local_only(path: str) -> bool:
        return any(path == p or path.startswith(p + "/") for p in LOCAL_ONLY_PREFIXES)

    def _session_user(sess):
        """The signed-in person for a live session, or None when this session must end (person gone, disabled,
        expired, no Financial Insights grant, or the epoch moved because the Admin app ended their sessions)."""
        user = store.get_user(sess.user_id)
        if user is None or user["status"] != "active" or (user["expires_at"] is not None and user["expires_at"] <= clock()):
            return None, None
        grant = store.get_grant(user["id"], "insights")
        if grant is None or int(user["session_epoch"]) != sess.epoch:
            return None, None
        user["money_view"] = grant["money_view"] or "percent"
        user["totp_enrolled"] = store.totp_enrolled(user["id"])
        user["needs_totp"] = bool(user["totp_required"]) and not user["totp_enrolled"]
        return user, grant

    @app.before_request
    def _gate():
        env = request.environ
        path = request.path
        if current_listener() == "local":
            if not is_loopback_host(str(request.headers.get("Host", "") or "")):
                return _json({"success": False, "error": "misdirected request"}, 421)
            if has_proxy_headers(request.headers):
                return _json({"success": False, "error": "proxied requests are not allowed here"}, 403)
            if local_gate is not None and (refusal := local_gate.check()) is not None:
                return refusal  # X-1: loopback alone does not identify the owner on a host with worker accounts
            env["person"] = OWNER_NAME
            _log_action()
            return None
        # ---- remote ----
        if _local_only(path):
            return _json({"success": False, "error": "Not found"}, 404)
        if (request.method, path) in PUBLIC_REMOTE:
            return None
        token = request.cookies.get(COOKIE)
        sess = sessions.get(token)
        _log_timeouts()
        user, grant = _session_user(sess) if sess else (None, None)
        if sess is None or user is None:
            if sess is not None:
                sessions.end(token)
                store.drop_session(token)
            if path.startswith("/api/"):
                return _json({"success": False, "error": "sign in required"}, 401)
            resp = Response(b"", status=302)
            resp.headers["Location"] = "/signin"
            return resp
        env["token"], env["user"], env["grant"], env["person"] = token, user, grant, user["display_name"]
        if user["must_change"] and path == "/":
            resp = Response(b"", status=302)
            resp.headers["Location"] = "/change-password"
            return resp
        if user["must_change"] and path.startswith("/api/") and path not in MUST_CHANGE_ALLOWED:
            return _json({"success": False, "must_change": True, "error": "choose a new password first"}, 409)
        if user["needs_totp"] and path == "/":
            resp = Response(b"", status=302)
            resp.headers["Location"] = "/totp"
            return resp
        if user["needs_totp"] and path.startswith("/api/") and path not in ENROL_ALLOWED:
            return _json({"success": False, "needs_totp": True, "error": "set up two-factor sign-in first"}, 409)
        if user["money_view"] == "percent" and path in WITHHELD_FOR_PERCENT:
            return _json({"success": False, "error": "Not available in the percent view."}, 403)
        if _tab_refused(grant):
            return _json({"success": False, "error": VIEW_REFUSED}, 403)
        if request.method not in ("GET", "HEAD") and path not in GUEST_WRITABLE_POST:
            return _json({"success": False, "error": READ_ONLY_REFUSED}, 403)  # guests are view-only (F-01)
        _log_action()
        return None

    def _tab_refused(grant) -> bool:
        """The request's route belongs to a tab the grant's list leaves out (no list, or an empty one, means every tab).
        Matched on the routed rule, the same lookup that picks the handler, so no spelling of the path gets around it."""
        allowed = (grant or {}).get("views")
        if not allowed:
            return False
        route, _kwargs = app._match(request.path, request.method)
        tab = VIEW_ROUTES.get(route.rule) if route is not None else None
        return tab is not None and tab not in allowed

    @app.errorhandler(Exception)
    def _unhandled(exc):
        # Routed through after_request so a guest never sees class names, messages or paths (F-05): the detail goes to
        # the server log. The owner's local listener keeps the verbose message.
        logging.getLogger(__name__).error("unhandled error on %s", request.path, exc_info=exc)
        message = f"{exc.__class__.__name__}: {exc}" if str(exc) else exc.__class__.__name__
        return _json({"success": False, "error": message}, 500)

    def _opaque_error(resp):
        """A 5xx JSON body for a remote guest becomes a generic message plus an error id; the original body (which can
        carry exception text or filesystem paths) is logged server-side under that id (F-05)."""
        error_id = secrets.token_hex(6)
        logging.getLogger(__name__).error("remote 500 %s on %s: %s", error_id, request.path, resp.get_data(as_text=True)[:2000])
        return _json({"success": False, "error": "Something went wrong. Try again later.", "error_id": error_id}, resp.status_code)

    @app.after_request
    def _security_headers(resp):
        """SEC-07 / F-10: CSP (inline script blocks admitted by hash only), nosniff, no framing, no referrer; the remote
        listener's pages and API replies are also no-store so the back button shows no data after sign-out."""
        if resp.mimetype == "text/html":
            csp = security_headers.csp_for_html(resp.get_data(as_text=True))
        else:
            csp = security_headers.PLANNER_CSP
        security_headers.apply(resp.headers, csp, no_store=current_listener() == "remote")
        return resp

    @app.after_request
    def _percent_view(resp):
        user = request.environ.get("user")
        path = request.path
        if current_listener() == "remote" and user and resp.status_code >= 500 and resp.mimetype.endswith("json"):
            return _opaque_error(resp)
        if (current_listener() != "remote" or not user or user["money_view"] != "percent"
                or not path.startswith("/api/") or path in PASS_THROUGH_FOR_PERCENT or path in WITHHELD_FOR_PERCENT
                or not resp.mimetype.endswith("json")):
            return resp
        if resp.status_code >= 400:
            return _json({"success": False, "error": "Something went wrong. Try again later."}, resp.status_code)
        k = percent_basis()
        if k is None:
            return _json({"success": False, "error": "The percent view is not available until account balances are imported."}, 503)
        # resp's body may be a string shared through a cache: parse into a new structure, never edit it.
        return _json(percent_view.percent_body(path, json.loads(resp.get_data(as_text=True)), k), resp.status_code)

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
        code = str(body.get("code") or "")[:32]
        try:
            result = store.verify_login(str(body.get("username") or ""), str(body.get("password") or ""), now, code=code)
        except SecretStoreUnavailable:  # fail closed: a second factor that cannot be checked never lets anyone in
            return _json({"success": False, "error": "Two-factor sign-in is unavailable right now."}, 503)
        attempted = str(body.get("username") or "")[:64]
        if result.reason == "locked":
            _log("locked out", attempted, person="(not signed in)")
            return _json({"success": False, "error": "Too many attempts. Try again in a few minutes."}, 429, {"Retry-After": "900"})
        if result.reason == "totp":  # password was right; ask for the code (the grant is still checked once the code is in)
            if store.get_grant(result.user_id, "insights") is None:
                _log("sign-in failed", attempted, person="(not signed in)")
                return _json({"success": False, "error": "Incorrect username or password."}, 401)
            return _json({"success": False, "needs_code": True})
        if result.reason == "bad_code":
            _log("two-factor code failed", attempted, person="(not signed in)")
            return _json({"success": False, "needs_code": True, "error": "That code is not right."}, 401)
        if not result.ok:
            _log("sign-in failed", attempted, person="(not signed in)")
            return _json({"success": False, "error": "Incorrect username or password."}, 401)
        if store.get_grant(result.user_id, "insights") is None:  # same refusal as a wrong password
            _log("sign-in failed", attempted, person="(not signed in)")
            return _json({"success": False, "error": "Incorrect username or password."}, 401)
        store.touch_last_signin(result.user_id, now)
        token = sessions.create(result.user_id, store.session_epoch(result.user_id) or 0)
        store.register_session(token, result.user_id, "insights", current_listener(),
                               str(request.headers.get("X-Forwarded-For", "") or "").split(",")[0].strip(), now=now)
        who = store.get_user(result.user_id)["display_name"]
        if totp_lib.looks_like_recovery(code):
            _log("recovery code used", person=who)
        _log("signed in", person=who)
        resp = _json({"success": True, "must_change": result.must_change, "needs_totp": result.needs_enrolment})
        resp.set_cookie(COOKIE, token, secure=True, httponly=True, samesite="Strict", path="/")
        return resp

    @app.route("/api/signout", methods=["POST"])
    def signout():
        resp = _json({"success": True})
        if current_listener() == "remote":
            if request.environ.get("token"):
                _log("signed out")
            sessions.end(request.environ.get("token"))
            store.drop_session(request.environ.get("token"))
            resp.delete_cookie(COOKIE)
        return resp

    @app.route("/api/whoami", methods=["GET"])
    def whoami():
        user = request.environ.get("user")
        grant = request.environ.get("grant")
        views = (grant or {}).get("views") or list(INSIGHTS_VIEWS)  # no list on the grant means every view
        return _json({
            "listener": current_listener(),
            "name": request.environ.get("person", OWNER_NAME),
            "must_change": bool(user and user["must_change"]),
            "needs_totp": bool(user and user["needs_totp"]),
            "totp_enrolled": bool(user and user["totp_enrolled"]),
            "money_view": user["money_view"] if user else "both",
            "views": [v for v in INSIGHTS_VIEWS if v in views],
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
        # The new password ends this person's other sessions (epoch bump); this one carries on.
        sessions.set_epoch(request.environ.get("token"), store.session_epoch(user["id"]) or 0)
        _log("password changed")
        return _json({"success": True})

    @app.route("/totp", methods=["GET"])
    def totp_page():
        return Response(TOTP_HTML_PATH.read_text(encoding="utf-8"), content_type="text/html; charset=utf-8")

    def _totp_user():
        user = request.environ.get("user")
        if user is None:
            return None, _json({"success": False, "error": "Only signed-in guests use two-factor sign-in."}, 400)
        return user, None

    @app.route("/api/totp/begin", methods=["POST"])
    def totp_begin():
        user, err = _totp_user()
        if err:
            return err
        try:
            secret = store.begin_enrolment(user["id"], now=clock())
        except SecretStoreUnavailable:
            return _json({"success": False, "error": "Two-factor sign-in is unavailable right now."}, 503)
        except ValueError as exc:
            return _json({"success": False, "error": str(exc)}, 409)
        return _json({"success": True, "secret": secret,
                      "uri": totp_lib.provisioning_uri(secret, user["username"])}, headers={"Cache-Control": "no-store"})

    @app.route("/api/totp/confirm", methods=["POST"])
    def totp_confirm():
        user, err = _totp_user()
        if err:
            return err
        body = request.get_json(silent=True) or {}
        try:
            codes = store.confirm_enrolment(user["id"], str(body.get("code") or "")[:32], now=clock())
        except SecretStoreUnavailable:
            return _json({"success": False, "error": "Two-factor sign-in is unavailable right now."}, 503)
        except ValueError as exc:
            return _json({"success": False, "error": str(exc)}, 409)
        if codes is None:
            _log("two-factor code failed", "setup")
            return _json({"success": False, "error": "That code is not right. Check your authenticator and try again."}, 400)
        _log("two-factor enrolled")
        return _json({"success": True, "recovery_codes": codes}, headers={"Cache-Control": "no-store"})

    @app.route("/api/totp/recovery-codes", methods=["POST"])
    def totp_recovery_codes():
        user, err = _totp_user()
        if err:
            return err
        body = request.get_json(silent=True) or {}
        if not store.check_current_password(user["id"], str(body.get("current") or "")):
            return _json({"success": False, "error": "Your current password is not right."}, 400)
        try:
            codes = store.regenerate_recovery_codes(user["id"], str(body.get("code") or "")[:32], now=clock())
        except SecretStoreUnavailable:
            return _json({"success": False, "error": "Two-factor sign-in is unavailable right now."}, 503)
        if codes is None:
            _log("two-factor code failed", "recovery codes")
            return _json({"success": False, "error": "That code is not right."}, 400)
        _log("recovery codes replaced")
        return _json({"success": True, "recovery_codes": codes}, headers={"Cache-Control": "no-store"})

    @app.route("/api/view", methods=["POST"])
    def view():
        name = str((request.get_json(silent=True) or {}).get("view") or "")
        if name not in VIEWS:
            return _json({"success": False, "error": "unknown view"}, 400)
        allowed = (request.environ.get("grant") or {}).get("views")
        if allowed and name in INSIGHTS_VIEWS and name not in allowed:
            return _json({"success": False, "error": VIEW_REFUSED}, 403)
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
            store.touch_session(token, clock() - max(0, idle_ms) / 1000.0)
        return _json({"success": True})

