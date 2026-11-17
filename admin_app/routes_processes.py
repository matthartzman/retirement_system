"""Process control (start / stop / status of the Planner and Financial Insights) and the live sessions list.

These routes sit behind the Admin app's loopback gate (``trust.check_request``), like every other route. They accept a
fixed app name only, and every start, stop and ended session is recorded in ``admin_audit``.
"""
from __future__ import annotations

import json
import os
import time
from typing import Callable

from src.http_runtime.wsgi_facade import Response, request
from src.identity import IdentityStore

from admin_app.processes import SPECS, ProcessManager
from admin_app.routes_users import ADMIN_NAME, mask_numbers

APP_LABEL = {"insights": "Financial Insights", "planner": "Retirement Planner"}
SESSION_IDLE_SECONDS = 660.0  # Financial Insights ends a session after 600 s idle; allow a little slack


def _json(payload, status: int = 200) -> Response:
    return Response(json.dumps(payload), status=status, content_type="application/json")


def register_processes(app, store: IdentityStore, manager: ProcessManager, clock: Callable[[], float] = time.time,
                       admin: str = ADMIN_NAME, admin_port: int = 5056) -> None:
    def audit(action: str, target: str = "", details: str = "") -> None:
        store.log_admin(admin, action, target, details, now=clock())

    def body() -> dict:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}

    def which(data: dict) -> str | None:
        name = data.get("app")
        return name if isinstance(name, str) and name in SPECS else None

    @app.route("/api/processes", methods=["GET"])
    def processes():
        return _json({"success": True, "apps": manager.statuses(), "admin": {"label": "Admin app", "pid": os.getpid(),
                                                                          "port": admin_port, "state": "running"}})

    @app.route("/api/processes/start", methods=["POST"])
    def process_start():
        name = which(body())
        if name is None:
            return _json({"success": False, "error": "unknown app"}, 400)
        payload, status = manager.start(name)
        if not payload.get("already"):
            audit("process.start", name, "ok" if status == 200 else payload.get("error", "failed"))
        return _json(payload, status)

    @app.route("/api/processes/stop", methods=["POST"])
    def process_stop():
        name = which(body())
        if name is None:
            return _json({"success": False, "error": "unknown app"}, 400)
        payload, status = manager.stop(name)
        if not payload.get("already"):
            audit("process.stop", name, "ok" if status == 200 else payload.get("error", "failed"))
        return _json(payload, status)

    @app.route("/api/sessions", methods=["GET"])
    def sessions():
        rows = store.list_live_sessions(now=clock(), max_idle=SESSION_IDLE_SECONDS)
        out = [{"user_id": r["user_id"], "person": mask_numbers(r["display_name"]), "username": r["username"],
                "app": r["app"], "app_label": APP_LABEL.get(r["app"], r["app"]), "where": r["listener"],
                "source": r["source"], "started_at": r["started_at"], "last_seen": r["last_seen"]} for r in rows]
        return _json({"success": True, "sessions": out,
                      "note": "The Retirement Planner has no sign-in on this computer, so it has no sessions to list."})

    @app.route("/api/sessions/end", methods=["POST"])
    def session_end():
        uid = body().get("user_id")
        user = store.get_user(uid) if isinstance(uid, int) and not isinstance(uid, bool) else None
        if user is None:
            return _json({"success": False, "error": "no such person"}, 404)
        store.end_sessions(user["id"])  # the epoch bump every app already honours; also clears the mirror rows
        audit("session.end", user["username"], "all of this person's sessions, in every app")
        return _json({"success": True})
