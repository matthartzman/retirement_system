"""People, grants, activity and audit routes. Every write is recorded in ``admin_audit``.

Nothing here puts a password, a code, a secret or an amount in the audit or in a response.
"""
from __future__ import annotations

import json
import re
import time
from typing import Callable

from src.http_runtime.wsgi_facade import Response, request
from src.identity import APPS, MONEY_VIEWS, IdentityStore, LastAdminError

# Views a Financial Insights grant can be limited to (null = all of them).
INSIGHTS_VIEWS = ("live", "trends", "projections")
ADMIN_NAME = "owner (PC)"
MAX_EVENTS = 1000
_LONG_NUMBER = re.compile(r"(?<![\w])(\d[ -]?){8,}(?![\w])")


def _json(payload, status: int = 200) -> Response:
    return Response(json.dumps(payload), status=status, content_type="application/json")


def _fail(message: str, status: int = 400) -> Response:
    return _json({"success": False, "error": message}, status)


def mask_numbers(text: str) -> str:
    """Account numbers stay masked to the last 4 everywhere, including activity written by other apps."""
    def keep_last4(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        return "****" + digits[-4:]
    return _LONG_NUMBER.sub(keep_last4, text or "")


def _clean_event(e: dict) -> dict:
    return {**e, "details": mask_numbers(str(e.get("details") or "")), "person": mask_numbers(str(e.get("person") or ""))}


def _parse_grant(app: str, body: dict) -> tuple[str | None, list[str] | None]:
    """``(money_view, views)`` for a grant request, or ValueError."""
    if app != "insights":
        return None, None
    money_view = str(body.get("money_view") or "percent")
    if money_view not in MONEY_VIEWS:
        raise ValueError("money view must be dollars, percent or both")
    views = body.get("views")
    if views is None:
        return money_view, None
    if not isinstance(views, list) or not views or not all(isinstance(v, str) for v in views):
        raise ValueError("views must be a list of view names, or empty to allow all")
    unknown = [v for v in views if v not in INSIGHTS_VIEWS]
    if unknown:
        raise ValueError(f"unknown view: {unknown[0]}")
    return money_view, [v for v in INSIGHTS_VIEWS if v in views]


def _expires(body: dict):
    """Epoch seconds, ``None`` (no expiry), or the string ``"keep"`` when the key is absent."""
    if "expires_at" not in body:
        return "keep"
    value = body["expires_at"]
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("expires_at must be a number of seconds, or null")
    return float(value)


def register_users(app, store: IdentityStore, clock: Callable[[], float] = time.time, admin: str = ADMIN_NAME) -> None:
    def audit(action: str, target: str = "", details: str = "") -> None:
        store.log_admin(admin, action, target, details, now=clock())

    def body() -> dict:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}

    def person(data: dict):
        try:
            uid = int(data.get("id"))
        except (TypeError, ValueError):
            return None
        return store.get_user(uid)

    def guarded(fn):
        """Run a store call: a refused rule is 400 (bad input) or 409 (last administrator)."""
        try:
            return fn(), None
        except LastAdminError as exc:
            return None, _fail(str(exc), 409)
        except ValueError as exc:
            return None, _fail(str(exc), 400)

    @app.route("/api/users", methods=["GET"])
    def users():
        return _json({"users": store.list_users(now=clock()), "apps": list(APPS), "money_views": list(MONEY_VIEWS),
                      "views": list(INSIGHTS_VIEWS)})

    @app.route("/api/users", methods=["POST"])
    def add_user():
        data = body()
        grants = data.get("grants") if isinstance(data.get("grants"), dict) else {}
        try:
            insights = grants.get("insights")
            planner = bool(grants.get("planner"))
            parsed = _parse_grant("insights", insights) if isinstance(insights, dict) else None
            expires = _expires(data)
        except ValueError as exc:
            return _fail(str(exc))
        username = str(data.get("username") or "").strip().lower()
        uid, err = guarded(lambda: store.add_user(
            str(data.get("display_name") or ""), username, str(data.get("temp_password") or ""), now=clock(),
            role=str(data.get("role") or "user"), expires_at=None if expires == "keep" else expires,
            notes=str(data.get("notes") or ""), insights=False, must_change=True, granted_by=admin,
            totp_required=data.get("totp_required") is not False))
        if err:
            return err
        if parsed:
            store.set_grant(uid, "insights", money_view=parsed[0], views=parsed[1], granted_by=admin, now=clock(), bump=False)
        if planner:
            store.set_grant(uid, "planner", granted_by=admin, now=clock(), bump=False)
        granted = [a for a, on in (("insights", bool(parsed)), ("planner", planner)) if on]
        audit("user.add", username, f"role={data.get('role') or 'user'}; grants={','.join(granted) or 'none'}")
        return _json({"success": True, "id": uid})

    @app.route("/api/users/update", methods=["POST"])
    def update_user():
        data = body()
        user = person(data)
        if user is None:
            return _fail("no such person", 404)
        try:
            expires = _expires(data)
        except ValueError as exc:
            return _fail(str(exc))
        kwargs = {k: data[k] for k in ("display_name", "role", "notes") if isinstance(data.get(k), str)}
        _, err = guarded(lambda: store.update_user(user["id"], expires_at=expires, now=clock(), **kwargs))
        if err:
            return err
        if isinstance(data.get("totp_required"), bool):
            store.set_totp_required(user["id"], data["totp_required"], now=clock())
            kwargs["totp_required"] = data["totp_required"]
        changed = sorted([*kwargs, *(["expires_at"] if expires != "keep" else [])])
        detail = "changed " + (", ".join(changed) or "nothing")
        if "role" in kwargs:
            detail += f"; role={kwargs['role']}"
        audit("user.update", user["username"], detail)
        return _json({"success": True})

    @app.route("/api/users/reset-password", methods=["POST"])
    def reset_password():
        data = body()
        user = person(data)
        if user is None:
            return _fail("no such person", 404)
        _, err = guarded(lambda: store.set_password(user["id"], str(data.get("temp_password") or ""), must_change=True, now=clock()))
        if err:
            return err
        audit("user.reset-password", user["username"], "sessions ended; must choose a new password")
        return _json({"success": True})

    @app.route("/api/users/disable", methods=["POST"])
    def disable():
        user = person(body())
        if user is None:
            return _fail("no such person", 404)
        _, err = guarded(lambda: store.set_status(user["id"], "disabled", now=clock()))
        if err:
            return err
        audit("user.disable", user["username"], "sessions ended")
        return _json({"success": True})

    @app.route("/api/users/enable", methods=["POST"])
    def enable():
        user = person(body())
        if user is None:
            return _fail("no such person", 404)
        store.set_status(user["id"], "active", now=clock())
        audit("user.enable", user["username"])
        return _json({"success": True})

    @app.route("/api/users/delete", methods=["POST"])
    def delete():
        user = person(body())
        if user is None:
            return _fail("no such person", 404)
        _, err = guarded(lambda: store.delete_user(user["id"], now=clock()))
        if err:
            return err
        audit("user.delete", user["username"])
        return _json({"success": True})

    @app.route("/api/users/reset-totp", methods=["POST"])
    def reset_totp():
        user = person(body())
        if user is None:
            return _fail("no such person", 404)
        had = store.reset_totp(user["id"])
        audit("user.reset-totp", user["username"], ("was enrolled" if had else "was not enrolled")
              + "; sessions ended; recovery codes removed")
        return _json({"success": True, "was_enrolled": had})

    @app.route("/api/users/end-sessions", methods=["POST"])
    def end_sessions():
        user = person(body())
        if user is None:
            return _fail("no such person", 404)
        store.end_sessions(user["id"])
        audit("user.end-sessions", user["username"])
        return _json({"success": True})

    @app.route("/api/users/grants", methods=["GET"])
    def grants():
        try:
            user = store.get_user(int(request.args.get("id")))
        except (TypeError, ValueError):
            user = None
        if user is None:
            return _fail("no such person", 404)
        return _json({"grants": store.list_grants(user["id"]), "views": list(INSIGHTS_VIEWS), "money_views": list(MONEY_VIEWS)})

    @app.route("/api/users/grants", methods=["POST"])
    def set_grant():
        data = body()
        user = person(data)
        if user is None:
            return _fail("no such person", 404)
        app_name = str(data.get("app") or "")
        if app_name not in APPS:
            return _fail("app must be insights or planner")
        if data.get("enabled") is False:
            store.revoke_grant(user["id"], app_name)
            audit("grant.revoke", user["username"], f"app={app_name}; sessions ended")
            return _json({"success": True})
        try:
            money_view, views = _parse_grant(app_name, data)
        except ValueError as exc:
            return _fail(str(exc))
        store.set_grant(user["id"], app_name, money_view=money_view, views=views, granted_by=admin, now=clock())
        shown = f"; money_view={money_view}; views={','.join(views) if views else 'all'}" if app_name == "insights" else ""
        audit("grant.set", user["username"], f"app={app_name}{shown}")
        return _json({"success": True})

    @app.route("/api/activity", methods=["GET"])
    def activity():
        def num(name):
            try:
                return float(request.args.get(name))
            except (TypeError, ValueError):
                return None
        app_name = str(request.args.get("app") or "")
        if app_name and app_name not in APPS:
            return _fail("app must be insights or planner")
        limit = request.args.get("limit", MAX_EVENTS, type=int)
        events = store.read_events(person=request.args.get("person") or None, since=num("from"), until=num("to"),
                                   limit=max(1, min(int(limit), MAX_EVENTS)), app=app_name or None)
        people = sorted({mask_numbers(p) for p in store.activity_people(app_name or None)}, key=str.casefold)
        return _json({"events": [_clean_event(e) for e in events], "people": people})

    @app.route("/api/audit", methods=["GET"])
    def audit_log():
        limit = request.args.get("limit", MAX_EVENTS, type=int)
        return _json({"audit": store.read_audit(limit=max(1, min(int(limit), MAX_EVENTS)))})
