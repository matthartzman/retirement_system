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
    _set_system_config_values,
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


@app.route("/admin")
@app.route("/system-configuration")
def admin_index():
    denied = _require("manage_clients")
    if denied:
        return denied
    p = BASE_DIR / "frontend" / "admin.html"
    if p.exists():
        # Redirect under /frontend/ (like "/" -> "/frontend/index.html") so
        # admin.html's relative css/admin.css, js/admin.js, and
        # js/pywebview_bridge.js references resolve against a URL the
        # /frontend/<path:filename> route actually serves.
        qs = request.query_string
        target = "/frontend/admin.html" + (f"?{qs}" if qs else "")
        return redirect(target, code=302)
    return "<h3>System Configuration UI not found.</h3>", 404


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


@app.route("/api/admin/diagnostics", methods=["GET"])
def admin_diagnostics():
    denied = _require("manage_clients")
    if denied:
        return denied
    return jsonify(admin_service.diagnostics_payload(workspace_output_dir(_workspace_id(), BASE_DIR)))


@app.route("/api/admin/clear-webview-cache", methods=["POST"])
def admin_clear_webview_cache():
    denied = _require("manage_clients")
    if denied:
        return denied
    result = admin_service.clear_webview_disk_cache(BASE_DIR)
    _audit("admin_webview_cache_cleared", {"cleared": result.get("cleared", []), "skipped_count": len(result.get("skipped", []))})
    return jsonify(result)


@app.route("/api/admin/server", methods=["GET"])
def admin_server_status():
    denied = _require("manage_clients")
    if denied:
        return denied
    return jsonify(admin_service.server_status_payload(version=VERSION, cfg=_runtime_config(), system_config_path=_system_config_path()))


@app.route("/api/admin/mode", methods=["POST"])
def admin_set_mode():
    denied = _require("manage_clients")
    if denied:
        return denied
    _set_system_config_values(admin_service.local_mode_updates())
    _audit("admin_local_mode_confirmed", {"mode": "LOCAL"})
    return jsonify({"success": True, "mode": "LOCAL", "restart_required": True, "system_config": str(_system_config_path())})


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


@app.route("/api/admin/system-config", methods=["GET"])
def admin_get_system_config():
    denied = _require("manage_clients")
    if denied:
        return denied
    return jsonify(admin_service.system_config_payload(_system_config_path()))


@app.route("/api/admin/system-config", methods=["POST"])
def admin_save_system_config():
    denied = _require("manage_clients")
    if denied:
        return denied
    payload, status, before_rows, after_rows = admin_service.save_system_config(request.get_json(silent=True) or {}, _system_config_path())
    if status != 200:
        return jsonify(payload), status
    change_event = _record_admin_config_change("system", _system_config_path().name, str(_system_config_path()), before_rows, after_rows)
    payload["change_event"] = change_event
    _audit("admin_system_config_saved", {"path": str(_system_config_path()), "change_count": (change_event or {}).get("change_count", 0)})
    return jsonify(payload)


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
