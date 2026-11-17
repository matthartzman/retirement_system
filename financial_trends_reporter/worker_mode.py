"""Worker mode: Financial Insight served by a user's own planner worker (multi-user server).

The worker's workspace is pinned by environment and its active plan comes from that user's own registry, so
nothing here takes a user or plan id from a request. Per-plan data (history log, balances, preferences,
decisions) lives in ``<output>/plans/<plan_id>/insights/``; nothing is written outside the workspace.

Design: ``documentation/future/multi-user-insights-design.md``.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from src.http_runtime.wsgi_facade import Response, request

from . import plan_balance_sync, worker_allowlist
from .app_sync import sync_from_app
from .balance_store import DB_FILENAME
from .listeners import ListenerApp
from .trends_log import LOG_FILENAME

INSIGHTS_DIRNAME = "insights"
VIEWS = ("live", "trends", "projections")
SYNC_MIN_INTERVAL_SECONDS = 5.0
_sync_lock = threading.Lock()
_last_sync: dict[str, float] = {}


def insights_dir() -> Path:
    """The active plan's Financial Insight folder, inside the user's own workspace."""
    from src import workspace_context  # noqa: PLC0415

    return workspace_context.workspace_output_dir() / INSIGHTS_DIRNAME


def log_path() -> Path:
    return insights_dir() / LOG_FILENAME


def ensure_synced(workspace: str | Path, db_path: Path, *, clock=time.monotonic) -> None:
    """Bring the balance store up to date with the plan (and the plan's account mapping), at most every few seconds.

    Never raises: a plan that cannot be read just leaves the store as it was (the page shows what it has)."""
    key = str(db_path)
    now = clock()
    with _sync_lock:
        if now - _last_sync.get(key, float("-inf")) < SYNC_MIN_INTERVAL_SECONDS:
            return
        _last_sync[key] = now
        result = plan_balance_sync.sync(workspace, db_path)
        if result.get("success") and result.get("status") == "ok":
            sync_from_app(db_path, workspace)


class WorkerListenerApp(ListenerApp):
    """Tags requests as the ``worker`` listener and holds the plan read-only for the whole request."""

    def __init__(self, app: Any) -> None:
        super().__init__(app, "worker")

    def handle_http(self, method, target, headers=None, body=b"", remote_addr="127.0.0.1"):  # noqa: ANN001
        from src import active_plan  # noqa: PLC0415

        with active_plan.read_only_plan_access():
            return super().handle_http(method, target, headers, body, remote_addr)


def _json(payload, status=200) -> Response:
    import json  # noqa: PLC0415

    return Response(json.dumps(payload), status=status, content_type="application/json")


def register_worker(app) -> None:  # noqa: ANN001
    """The worker-mode gate and the few routes sign-in used to provide. The worker token, Host and Origin checks
    belong to the mount in front of this app; this adds the deny-by-default route list."""

    @app.before_request
    def _gate():
        route, _kwargs = app._match(request.path, request.method)
        if route is None:
            return _json({"success": False, "error": "Not found"}, 404)
        if request.method == "OPTIONS" or not worker_allowlist.route_allowed(request.method, route.rule):
            return _json({"success": False, "error": "Not available here."}, 403)
        return None

    @app.route("/api/whoami", methods=["GET"])
    def whoami():
        from src import plan_registry  # noqa: PLC0415

        try:
            record = plan_registry.active_record()
            plan = {"id": str(record.get("plan_id") or ""), "name": str(record.get("name") or "")}
        except Exception:  # noqa: BLE001 - the page just omits the plan name
            plan = {"id": "", "name": ""}
        return _json({"listener": "worker", "name": "", "must_change": False, "needs_totp": False,
                      "totp_enrolled": False, "money_view": "both", "views": list(VIEWS), "plan": plan})

    @app.route("/api/ping", methods=["POST"])
    def ping():
        return _json({"success": True})  # the gateway owns session timeouts; nothing to record here

    @app.route("/api/view", methods=["POST"])
    def view():
        return _json({"success": True})
