from .app_core import *
try:
    from ..version import VERSION
except ImportError:
    from src.version import VERSION
try:
    from ..server_services import base_service
except ImportError:
    from src.server_services import base_service
# RELEASE_GATE_EXPECTED_VERSION_LITERAL: "version": "9"


def _safe_next_path(raw: object) -> str:
    return base_service.safe_next_path(raw)


def _package_instance_payload() -> dict:
    return base_service.package_instance_payload(BASE_DIR, VERSION)


@app.route("/api/ping", methods=["GET", "OPTIONS"])
def ping():
    return jsonify(base_service.ping_payload(version=VERSION, app_mode=_runtime_config().app_mode, base_dir=BASE_DIR))


@app.route("/login")
def login_page():
    return redirect("/", code=302)


@app.route("/api/auth/session", methods=["GET"])
def auth_session():
    ok, identity = _authorized_and_identity()
    return jsonify(base_service.auth_session_payload(ok=ok, identity=identity, cfg=_runtime_config(), csrf_token=_csrf_token_for_current_request() if ok else ""))


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    return jsonify(base_service.login_payload(_csrf_token_for_current_request()))


@app.route("/api/auth/logout", methods=["POST", "GET"])
def auth_logout():
    return jsonify(base_service.logout_payload())


@app.route("/")
def index():
    denied = _require("view_dashboard")
    if denied:
        return denied
    frontend = BASE_DIR / "frontend" / "index.html"
    if frontend.exists():
        return redirect("/frontend/index.html", code=302)
    out = _workspace_output()
    for name in UI_NAMES:
        p = out / name
        if p.exists():
            return send_file(str(p))
    for name in UI_NAMES:
        p = BASE_DIR / "output" / name
        if p.exists():
            return send_file(str(p))
    return "<h3>Dashboard has not been generated. Run a build first.</h3>", 404


@app.route("/frontend")
def frontend_index():
    denied = _require("view_dashboard")
    if denied:
        return denied
    p = BASE_DIR / "frontend" / "index.html"
    if p.exists():
        return redirect("/frontend/index.html", code=302)
    return index()


@app.route("/frontend/<path:filename>")
def frontend_file(filename):
    denied = _require("view_dashboard")
    if denied:
        return denied
    safe = Path(filename)
    if safe.is_absolute() or ".." in safe.parts:
        return jsonify({"success": False, "error": "Invalid frontend path"}), 400
    p = BASE_DIR / "frontend" / safe
    allowed = {".html", ".css", ".js", ".png", ".svg", ".ico"}
    if p.exists() and p.suffix.lower() in allowed:
        resp = send_from_directory(str(BASE_DIR / "frontend"), filename)
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp
    return jsonify({"success": False, "error": "Frontend asset not found"}), 404


@app.route("/api/prefs", methods=["GET"])
def get_prefs():
    return jsonify(base_service.read_prefs(BASE_DIR))


@app.route("/api/prefs", methods=["POST"])
def save_prefs():
    payload, status = base_service.save_prefs(BASE_DIR, request.get_json(silent=True) or {})
    return jsonify(payload), status


@app.route("/api/runtime", methods=["GET"])
def get_runtime():
    denied = _require("view_dashboard")
    if denied:
        return denied
    return jsonify(base_service.runtime_payload(version=VERSION, cfg=_runtime_config(), user=_current_user(), output_dir=_workspace_output()))


@app.route("/api/contracts", methods=["GET"])
def api_contracts():
    """Return the lightweight typed API contract registry."""
    denied = _require("view_dashboard")
    if denied:
        return denied
    try:
        from ..api_contracts import contract_summary
        from .route_manifest import route_manifest
    except ImportError:
        from src.api_contracts import contract_summary
        from src.server.route_manifest import route_manifest
    return jsonify({
        "success": True,
        "schema": "api_contract_registry_v1",
        "contracts": contract_summary(),
        "route_manifest": route_manifest(),
    })


@app.route("/api/glossary", methods=["GET"])
def api_glossary():
    """Return the canonical financial/planning-term glossary (system review
    2026-07-21, D3) -- the same source the workbook's Glossary sheet renders
    from, so the app's help panels and the printed plan can no longer drift
    out of reconciliation with each other."""
    denied = _require("view_dashboard")
    if denied:
        return denied
    try:
        from ..glossary import build_glossary
    except ImportError:
        from src.glossary import build_glossary
    return jsonify({
        "success": True,
        "schema": "glossary_v1",
        "terms": build_glossary(),
    })
