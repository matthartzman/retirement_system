"""Install-wide settings, system status, pricing tester and tax-law dashboard routes.

Every write is recorded in ``admin_audit`` (counts and labels only, never a value).
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Callable

from src.http_runtime.wsgi_facade import Response, request
from src.identity import IdentityStore
from src.server_services.pricing_service import PriceSymbolTestRegistry

from admin_app.routes_users import ADMIN_NAME
from admin_app.settings import SettingsService


def _json(payload, status: int = 200) -> Response:
    return Response(json.dumps(payload), status=status, content_type="application/json")


def register_system(app, store: IdentityStore, settings: SettingsService, clock: Callable[[], float] = time.time,
                    admin: str = ADMIN_NAME, price_tests: PriceSymbolTestRegistry | None = None) -> None:
    tests = price_tests or PriceSymbolTestRegistry()

    def audit(action: str, details: str = "") -> None:
        store.log_admin(admin, action, "", details, now=clock())

    def body() -> dict:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}

    @app.route("/api/settings", methods=["GET"])
    def settings_get():
        return _json(settings.payload())

    @app.route("/api/settings", methods=["POST"])
    def settings_save():
        data = body()
        payload, status = settings.save(data["rows"] if "rows" in data else data.get("csv_content"))
        if status == 200:
            audit("settings.save", f"{payload.get('changed', 0)} setting(s) changed")
        return _json(payload, status)

    @app.route("/api/settings/pricing-test/start", methods=["POST"])
    def pricing_test_start():
        payload, status = tests.start_payload(body(), workspace_id="admin")
        if status == 200:
            audit("pricing.test", f"symbol {payload.get('symbol', '')}")
        return _json(payload, status)

    @app.route("/api/settings/pricing-test/status/<job_id>", methods=["GET"])
    def pricing_test_status(job_id):
        payload, status = tests.status_payload(job_id)
        return _json(payload, status)

    @app.route("/api/tax-law-dashboard", methods=["GET"])
    def tax_law():
        return _json(settings.tax_law_dashboard())

    @app.route("/api/system/status", methods=["GET"])
    def system_status():
        return _json(settings.server_status())

    @app.route("/api/system/clear-webview-cache", methods=["POST"])
    def clear_cache():
        result = settings.clear_webview_cache()
        audit("system.clear-webview-cache", f"{len(result.get('cleared', []))} cleared")
        return _json(result)

    @app.route("/api/system/planner-shutdown", methods=["POST"])
    def planner_shutdown():
        result = settings.shutdown_planner()
        audit("system.planner-shutdown", "ok" if result.get("success") else "failed")
        return _json(result, 200 if result.get("success") else 502)

    @app.route("/api/system/shutdown", methods=["POST"])
    def admin_shutdown():
        audit("system.admin-shutdown")
        threading.Timer(0.5, lambda: os._exit(0)).start()
        return _json({"success": True, "status": "shutting down"})
