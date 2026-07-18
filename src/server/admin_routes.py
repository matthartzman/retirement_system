from .app_core import *
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


ADMIN_PLAN_DATA_FILES = admin_service.ADMIN_PLAN_DATA_FILES


def _admin_csv_path(kind: str, file_name: str) -> Path:
    return admin_service.admin_csv_path(kind, file_name, base_dir=BASE_DIR, system_config_path=_system_config_path())


@app.route("/api/admin/csv-file/<kind>/<path:file_name>", methods=["GET"])
def admin_get_csv_file(kind, file_name):
    denied = _require("manage_clients")
    if denied:
        return denied
    try:
        return jsonify(admin_service.csv_file_payload(kind, file_name, base_dir=BASE_DIR, system_config_path=_system_config_path()))
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@app.route("/api/admin/csv-file/<kind>/<path:file_name>", methods=["POST"])
def admin_save_csv_file(kind, file_name):
    denied = _require("manage_clients")
    if denied:
        return denied
    try:
        payload, status, before_rows, after_rows = admin_service.save_csv_file(kind, file_name, request.get_json(silent=True) or {}, base_dir=BASE_DIR, system_config_path=_system_config_path())
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    if status != 200:
        return jsonify(payload), status
    change_event = _record_admin_config_change(str(kind).lower(), payload["file"], payload["path"], before_rows, after_rows)
    payload["change_event"] = change_event
    _audit("admin_csv_file_saved", {"kind": str(kind).lower(), "file": payload["file"], "path": payload["path"], "change_count": (change_event or {}).get("change_count", 0)})
    return jsonify(payload)


@app.route("/api/admin/tax-law-dashboard", methods=["GET"])
def admin_tax_law_dashboard():
    denied = _require("manage_clients")
    if denied:
        return denied
    try:
        from ..governance import tax_law_dashboard
    except Exception:
        from src.governance import tax_law_dashboard
    data = load_system_config(_system_config_path()) if _system_config_path().exists() else {}
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


@app.route("/api/admin/reference-files", methods=["GET"])
def admin_reference_files():
    denied = _require("manage_clients")
    if denied:
        return denied
    return jsonify(admin_service.reference_files_payload(BASE_DIR))


@app.route("/api/admin/reference-files/<path:file_name>", methods=["GET"])
def admin_get_reference_file(file_name):
    denied = _require("manage_clients")
    if denied:
        return denied
    try:
        payload, status, headers = admin_service.read_reference_file(BASE_DIR, file_name)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    if isinstance(payload, dict):
        return jsonify(payload), status
    return payload, status, headers


@app.route("/api/admin/reference-files/<path:file_name>", methods=["POST"])
def admin_save_reference_file(file_name):
    denied = _require("manage_clients")
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    content = body.get("csv_content")
    if content is None:
        content = request.get_data(as_text=True)
    try:
        payload, before_rows, after_rows = admin_service.save_reference_file(BASE_DIR, file_name, str(content or ""))
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    change_event = _record_admin_config_change("reference", payload["file"], payload["path"], before_rows, after_rows)
    payload["change_event"] = change_event
    _audit("admin_reference_file_saved", {"file": payload["file"], "bytes": payload["bytes"], "change_count": (change_event or {}).get("change_count", 0)})
    return jsonify(payload)


@app.route("/api/admin/csv-backup", methods=["GET"])
def admin_csv_backup():
    denied = _require("manage_clients")
    if denied:
        return denied
    if not _runtime_config().allow_downloads:
        return jsonify({"success": False, "error": "Downloads are disabled"}), 403
    payload, status = admin_service.csv_backup_zip(BASE_DIR, _system_config_path())
    if status != 200:
        return jsonify(payload), status
    _audit("admin_csv_backup_exported", {"file_count": len(payload["included"])})
    return Response(
        payload["data"],
        status=200,
        headers={"Content-Disposition": f'attachment; filename="{payload["filename"]}"'},
        content_type="application/zip",
    )
