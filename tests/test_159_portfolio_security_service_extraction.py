from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_portfolio_service_owns_drift_tool_orchestration():
    service = read("src/server_services/portfolio_service.py")
    routes = read("src/server/plan_routes.py")
    assert "def drift_payload" in service
    assert "tools\" / \"analyze_drift.py" in service
    assert "portfolio_drift.json" in service
    assert "subprocess.run" in service
    assert "@app.route" not in service
    assert "request.get_json" not in service
    assert "def portfolio_drift" in routes
    assert "portfolio_service.drift_payload(" in routes
    assert "tools\" / \"analyze_drift.py" not in routes
    assert "portfolio_drift.json" not in routes


def test_secret_service_owns_secret_payload_validation():
    service = read("src/server_services/secret_service.py")
    routes = read("src/server/plan_routes.py")
    assert "def set_secret_payload" in service
    assert "name and value are required" in service
    assert "set_secret_fn(name, value" in service
    assert "@app.route" not in service
    assert "jsonify" not in service
    assert "def set_secret_route" in routes
    assert "secret_service.set_secret_payload(" in routes
    assert "name and value are required" not in routes
    assert "_audit(\"secret_set\"" in routes


def test_base_service_owns_status_payload_shape():
    base = read("src/server_services/base_service.py")
    routes = read("src/server/plan_routes.py")
    assert "def status_payload" in base
    assert "portfolio_drift_analysis" in base
    assert "json_yaml_config" in base
    assert "base_service.status_payload(" in routes
    assert '"portfolio_drift_analysis": True' not in routes


def test_manifest_contracts_and_packaging_include_new_services():
    manifest = read("src/server/route_manifest.py")
    contracts = read("src/api_contracts.py")
    package = read("tools/build_release_package.py")
    validator = read("tools/validate_clean_overlay.py")
    assert '"portfolio": ["/api/portfolio/drift"]' in manifest
    assert '"security": ["/api/secrets"]' in manifest
    assert "portfolio_drift_v1" in contracts
    assert "secret_set_v1" in contracts
    assert "runtime_status_v1" in contracts
    assert "portfolio_service.py" in package
    assert "secret_service.py" in package
    assert "portfolio_service.py" in validator
    assert "secret_service.py" in validator
