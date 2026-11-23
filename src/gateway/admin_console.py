"""The Admin console's Users UI, hosted by the gateway at ``/gateway/admin`` (integration design, phase 1).

This module adds no authorization of its own. Every path it registers is under an admin prefix, which the
gate in ``app.py`` refuses to anyone but an active admin session before any function here runs, and every change goes
through the same store calls, ``_admin_call`` error mapping and lifecycle hooks as the older
``/api/auth/admin/users`` routes. Only the JSON shapes differ: they are the ones ``admin_app/frontend/users.js``
already speaks, so the same script serves the standalone Admin app and the gateway.

What the gateway has no meaning for (planner/insights grants, the two-factor switch, activity by app, and, until
phase 2, expiry, notes, end-sessions and rename) is reported through ``features`` so the page hides it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from src.http_runtime.wsgi_facade import Response, request

from .store import KEEP, MIN_PASSWORD_LENGTH, GatewayStore

ADMIN_PAGE = "admin.html"
PAGES_DIR = Path(__file__).resolve().parent / "pages"
ADMIN_APP_FRONTEND = Path(__file__).resolve().parents[2] / "admin_app" / "frontend"
JS, CSS = "text/javascript; charset=utf-8", "text/css; charset=utf-8"
# The exact files the console page may load. Nothing else under admin_app/frontend (settings, processes, the
# standalone index page) is ever served by the gateway.
ADMIN_STATIC: dict[str, tuple[Path, str]] = {
    "users.js": (ADMIN_APP_FRONTEND, JS),
    "admin.css": (ADMIN_APP_FRONTEND, CSS),
    "admin-gateway.js": (PAGES_DIR, JS),
    "admin-gateway.css": (PAGES_DIR, CSS),
    "admin-viewers.js": (PAGES_DIR, JS),  # Phase 9: Add viewer; does nothing unless features.viewers is true
}
API_BASE = "/api/auth/admin/console"
# Shown to the page so it hides what the gateway does not have (grants, the two-factor switch, activity by app).
FEATURES = {
    "grants": False, "require_totp": False, "activity": False,
    "expiry": True, "notes": True, "end_sessions": True, "edit_name": True,
    "audit": True,
    # The Planner section is one "Can sign in" switch (the account's enabled state); Financial Insight's views are
    # stored per person but not enforced until it runs per user on the server.
    "modules": True,
}


VIEWER_DEFAULT_DAYS = 90  # a new viewer account's default access end (design 6.3)


def _console_user(u: dict, shared_views: bool = False) -> dict:
    out = {
        "id": u["id"], "username": u["username"], "display_name": u["display_name"], "role": u["role"],
        "status": "disabled" if u["disabled"] else "active", "expired": u["expired"], "locked": u["locked"],
        "must_change": u["must_change"], "totp_enrolled": u["totp"] == "enrolled", "totp_required": True,
        "expires_at": u["expires_at"], "notes": u["notes"], "modules": u["modules"], "last_signin_at": u["last_login_at"],
        "created_at": u["created_at"], "grants": [], "enrol_overdue": bool(u.get("enrol_overdue")),
    }
    if shared_views:
        # Counts only: admins never see, create or change a share (C30).
        out.update({"kind": "member" if u.get("kind") == "member" else "viewer",
                    "sponsor_id": u.get("sponsor_user_id"), "shares_owned": u.get("shares_owned", 0),
                    "shares_received": u.get("shares_received", 0)})
    return out


def register_admin_console(app, store: GatewayStore, *, clock: Callable[[], float], actor: Callable[[], object],
                           admin_call: Callable, notify: Callable, refused: Callable, page: Callable,
                           file_page: Callable, json_response: Callable, delete_account: Callable | None = None,
                           shared_views: bool = False, max_viewers_per_sponsor: int = 5,
                           enrol_fields: Callable[[int], dict] | None = None) -> None:
    codes = enrol_fields or (lambda _uid: {})  # SEC-04: the one-time enrolment code, shown to the admin once
    features = {**FEATURES, "viewers": bool(shared_views)}
    def body() -> dict:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}

    def target(data: dict) -> tuple[int | None, Response | None]:
        raw = data.get("id")
        if isinstance(raw, bool) or not isinstance(raw, int):
            return None, refused("id is required", 400)
        return raw, None

    @app.route("/gateway/admin", methods=["GET"])
    def admin_console_page():
        return page(ADMIN_PAGE)

    @app.route("/gateway/admin/static/<name>", methods=["GET"])
    def admin_console_static(name: str):
        entry = ADMIN_STATIC.get(name)
        if entry is None:
            return refused("Not found", 404)
        directory, ctype = entry
        return file_page(directory / name, ctype)

    @app.route(API_BASE + "/users", methods=["GET"])
    def console_users():
        return json_response({"success": True,
                              "users": [_console_user(u, shared_views) for u in store.list_users(now=clock())],
                              "features": features, "min_password": MIN_PASSWORD_LENGTH, "views": [], "apps": [],
                              "money_views": []})

    @app.route(API_BASE + "/users", methods=["POST"])
    def console_add():
        b = body()

        def create():
            extra = {k: b[k] for k in ("notes", "expires_at", "modules") if k in b}
            store.check_profile(**extra)  # refuse bad values before the person is created
            uid = store.create_user(str(b.get("username") or ""), str(b.get("display_name") or ""),
                                    str(b.get("role") or "user"), str(b.get("temp_password") or ""),
                                    now=clock(), actor=actor(), must_change=True)
            if extra:
                store.set_profile(uid, now=clock(), actor=actor(), **extra)
            return {"id": uid, **codes(uid)}
        return admin_call(create, after=lambda r: notify("user_created", r["id"], member=True))

    @app.route(API_BASE + "/viewers", methods=["POST"])
    def console_add_viewer():
        """Add viewer (Phase 9): a viewer account sponsored by one member. No lifecycle hook runs, so no workspace,
        Windows account or worker is created (design 6.3, F2)."""
        if not shared_views:
            return refused("Not found", 404)
        b = body()
        sponsor = b.get("sponsor_id")
        if isinstance(sponsor, bool) or not isinstance(sponsor, int):
            return refused("choose the member who sponsors this viewer", 400)
        expires_at = b.get("expires_at", clock() + VIEWER_DEFAULT_DAYS * 86400)
        def create_viewer() -> dict:
            uid = store.create_viewer(
                str(b.get("username") or ""), str(b.get("display_name") or ""), str(b.get("temp_password") or ""),
                sponsor_user_id=sponsor, expires_at=expires_at, now=clock(), actor=actor(), must_change=True,
                max_per_sponsor=max_viewers_per_sponsor)
            return {"id": uid, **codes(uid)}
        return admin_call(create_viewer)

    @app.route(API_BASE + "/users/update", methods=["POST"])
    def console_update():
        b = body()
        uid, bad = target(b)
        if bad:
            return bad
        row = store.get_user(uid)
        if row is None:
            return refused("no such user", 404)
        # Only keys the page sent are changed. ``expires_at: null`` clears the expiry.
        wanted = {k: b[k] for k in ("display_name", "notes", "expires_at", "modules") if k in b}
        role = b.get("role")

        def run():
            store.check_profile(**wanted)  # validate everything before changing anything
            if isinstance(role, str):
                store.set_role(uid, role, now=clock(), actor=actor())
            return store.set_profile(uid, now=clock(), actor=actor(), **wanted) if wanted else {}

        def after(result):
            if result.get("expiry_changed_access") and not row["disabled"]:
                return notify("user_disabled", uid, bool(result.get("expired")))
            return None
        return admin_call(run, after=after)

    @app.route(API_BASE + "/users/end-sessions", methods=["POST"])
    def console_end_sessions():
        uid, bad = target(body())
        if bad:
            return bad
        return admin_call(lambda: {"ended": store.end_sessions(uid, now=clock(), actor=actor())},
                          after=lambda _r: notify("signed_out", uid, 0))

    @app.route(API_BASE + "/users/reset-password", methods=["POST"])
    def console_reset_password():
        b = body()
        uid, bad = target(b)
        if bad:
            return bad
        def reset() -> dict:
            store.set_password(uid, str(b.get("temp_password") or ""), must_change=True, now=clock(), actor=actor(),
                               event="password reset")
            return codes(uid)
        return admin_call(reset)

    @app.route(API_BASE + "/users/disable", methods=["POST"])
    def console_disable():
        uid, bad = target(body())
        if bad:
            return bad
        return admin_call(lambda: store.set_disabled(uid, True, now=clock(), actor=actor()),
                          after=lambda _r: notify("user_disabled", uid, True))

    @app.route(API_BASE + "/users/enable", methods=["POST"])
    def console_enable():
        uid, bad = target(body())
        if bad:
            return bad
        return admin_call(lambda: store.set_disabled(uid, False, now=clock(), actor=actor()),
                          after=lambda _r: notify("user_disabled", uid, False))

    @app.route(API_BASE + "/users/unlock", methods=["POST"])
    def console_unlock():
        uid, bad = target(body())
        if bad:
            return bad
        return admin_call(lambda: store.unlock(uid, now=clock(), actor=actor()))

    @app.route(API_BASE + "/users/reset-totp", methods=["POST"])
    def console_reset_totp():
        uid, bad = target(body())
        if bad:
            return bad
        def reset() -> dict:
            store.reset_totp(uid, now=clock(), actor=actor())
            return codes(uid)
        return admin_call(reset)

    @app.route(API_BASE + "/users/enrol-code", methods=["POST"])
    def console_enrol_code():
        """Issue a fresh one-time enrolment code for an account that has not enrolled (SEC-04)."""
        uid, bad = target(body())
        if bad:
            return bad
        return admin_call(lambda: codes(uid))

    @app.route(API_BASE + "/users/delete", methods=["POST"])
    def console_delete():
        b = body()
        uid, bad = target(b)
        if bad:
            return bad
        row = store.get_user(uid)
        if row is None:
            return refused("no such user", 404)
        typed = b.get("confirm_username")
        if not isinstance(typed, str) or typed != row["username"]:
            return refused("Type the person's username to confirm. Deleting removes their plans and data.", 400)
        if delete_account is not None:
            return delete_account(uid)
        return admin_call(lambda: store.delete_user(uid, now=clock(), actor=actor()),
                          after=lambda _r: notify("user_deleted", uid))

    @app.route(API_BASE + "/audit", methods=["GET"])
    def console_audit():
        try:
            limit = int(request.args.get("limit") or 200)
        except (TypeError, ValueError):
            limit = 200
        rows = [{"at": e["at"], "admin": e["actor_username"], "action": e["event"], "target_user": e["target_username"],
                 "details": e["details"], "address": e["client_ip"], "listener": e["listener"]}
                for e in store.read_audit(limit=limit)]
        return json_response({"success": True, "audit": rows})
