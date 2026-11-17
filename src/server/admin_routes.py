# System review 4.9: explicit name list instead of `from .app_core import *`
# (app_core.py's __all__ is dynamically every module-level name, so the star
# import re-exported its entire namespace). Determined via AST analysis of
# every Name this module actually loads that isn't locally defined or
# otherwise imported.
from .app_core import (
    BASE_DIR,
    Response,
    _audit,
    _record_admin_config_change,
    _require,
    _runtime_config,
    _system_config_path,
    _workspace_id,
    app,
    jsonify,
    load_system_config,
    os,
    redirect,
    request,
    system_config_setting,
    workspace_output_dir,
)
try:
    from ..version import VERSION
except Exception:
    from src.version import VERSION
try:
    from ..server_services import admin_service
except Exception:
    from src.server_services import admin_service


ADMIN_APP_URL = "http://127.0.0.1:5056/"
_HAND_OFF_PAGE = (
    "<!doctype html><meta charset=\"utf-8\"><title>System configuration moved</title>"
    "<body style=\"font:16px system-ui;max-width:40em;margin:3em auto;padding:0 1em\">"
    "<h2>System configuration now lives in the Admin app</h2>"
    "<p>Users, install-wide settings and system tools moved out of the planner. Start the Admin app "
    "(<code>python -m admin_app</code>, or its launcher), then open "
    "<a href=\"" + ADMIN_APP_URL + "\">" + ADMIN_APP_URL + "</a>.</p>"
    "<p>Plan-level engine settings are on the planner's <b>Plan assumptions</b> pages.</p></body>"
)


def _admin_app_running() -> bool:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(ADMIN_APP_URL + "api/ping", timeout=0.4):  # noqa: S310 - fixed loopback URL
            return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError):
        return False


@app.route("/admin")
@app.route("/system-configuration")
def admin_index():
    denied = _require("manage_clients")
    if denied:
        return denied
    if _admin_app_running():
        return redirect(ADMIN_APP_URL, code=302)
    return Response(_HAND_OFF_PAGE, status=200, content_type="text/html; charset=utf-8")


@app.route("/api/admin/tax-law-dashboard", methods=["GET"])
def admin_tax_law_dashboard():
    denied = _require("manage_clients")
    if denied:
        return denied
    try:
        from ..governance import tax_law_dashboard
    except Exception:
        from src.governance import tax_law_dashboard
    data = load_system_config(_system_config_path())
    try:
        max_lag = int(float(system_config_setting(data, "Tax Governance", "max_tax_table_lag_years", "1") or 1))
    except Exception:
        max_lag = 1
    rows = tax_law_dashboard(max_lag_years=max_lag)
    return jsonify({"success": True, "version": VERSION if 'VERSION' in globals() else "9", "rows": rows, "max_lag_years": max_lag})


@app.route("/plan-assumptions")
def plan_assumptions_page():
    denied = _require("manage_clients")
    if denied:
        return denied
    return redirect("/frontend/plan_assumptions.html", code=302)


@app.route("/api/workspace/diagnostics", methods=["GET"])
@app.route("/api/admin/diagnostics", methods=["GET"])
def admin_diagnostics():
    denied = _require("manage_clients")
    if denied:
        return denied
    return jsonify(admin_service.diagnostics_payload(workspace_output_dir(_workspace_id(), BASE_DIR)))


@app.route("/api/admin/server/shutdown", methods=["POST"])
def admin_shutdown_server():
    denied = _require("manage_clients")
    if denied:
        return denied
    func = request.environ.get("werkzeug.server.shutdown")
    if func:
        func()
        return jsonify({"success": True, "status": "shutting down"})
    import threading
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return jsonify({"success": True, "status": "shutting down"})


@app.route("/api/plan/engine-assumptions", methods=["GET"])
def plan_engine_assumptions():
    denied = _require("manage_clients")
    if denied:
        return denied
    return jsonify(admin_service.engine_assumptions_payload())


@app.route("/api/plan/engine-assumptions", methods=["POST"])
def save_plan_engine_assumptions():
    denied = _require("manage_clients")
    if denied:
        return denied
    payload, status, before_rows, after_rows = admin_service.save_engine_assumptions(request.get_json(silent=True) or {})
    if status != 200:
        return jsonify(payload), status
    change_event = _record_admin_config_change("plan", "engine_assumptions", "active plan", before_rows, after_rows)
    payload["change_event"] = change_event
    _audit("plan_engine_assumptions_saved", {"change_count": (change_event or {}).get("change_count", 0)})
    return jsonify(payload)


@app.route("/api/workspace/csv-backup", methods=["GET"])
@app.route("/api/admin/csv-backup", methods=["GET"])
def admin_csv_backup():
    denied = _require("manage_clients")
    if denied:
        return denied
    if not _runtime_config().allow_downloads:
        return jsonify({"success": False, "error": "Downloads are disabled"}), 403
    data, filename = admin_service.build_csv_backup_zip(BASE_DIR)
    _audit("admin_csv_backup_exported", {"bytes": len(data)})
    return Response(
        data,
        status=200,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        content_type="application/zip",
    )
