import json
from pathlib import Path

from src.api_contracts import CONTRACT_BY_KEY, contract_summary, validate_payload
from src.terminology_aliases import canonical_id, contains_user_facing_legacy_wellness, healthcare_alias_payload, user_label

ROOT = Path(__file__).resolve().parents[1]


def test_documented_reconciliation_files_exist():
    expected = [
        ROOT / "src/api_contracts.py",
        ROOT / "src/server/route_manifest.py",
        ROOT / "frontend/js/dashboard_roadmap11.js",
        ROOT / "frontend/js/modules/phase3_module_manifest.js",
        ROOT / "frontend/js/api_client.js",
        ROOT / "frontend/js/app_store.js",
        ROOT / "src/server_services/pricing_service.py",
        ROOT / "src/server_services/holdings_service.py",
        ROOT / "tools/validate_clean_overlay.py",
    ]
    missing = [str(p.relative_to(ROOT)) for p in expected if not p.exists()]
    assert missing == []


def test_api_contracts_endpoint_is_framework_neutral_and_live():
    from src.server import app

    resp = app.test_client().get("/api/contracts")
    assert resp.status_code == 200
    payload = json.loads(resp.get_data(as_text=True))
    assert payload["success"] is True
    assert payload["schema"] == "api_contract_registry_v1"
    assert any(c["route"] == "/api/build/preflight" for c in payload["contracts"])
    assert payload["route_manifest"]["schema"] == "phase3_route_manifest_v1"


def test_contract_registry_validates_contract_shapes():
    assert "GET /api/contracts" in CONTRACT_BY_KEY
    assert "GET /api/build/preflight" in CONTRACT_BY_KEY
    assert all(c["route"] and c["method"] and c["schema"] for c in contract_summary())
    errors = validate_payload("GET", "/api/contracts", {"success": True, "schema": "api_contract_registry_v1", "contracts": []})
    assert errors == []


def test_frontend_extraction_scripts_are_loaded_before_dashboard():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    assert "js/api_client.js" in html
    assert "js/app_store.js" in html
    scripts = [part.split('"')[0] for part in html.split('src="')[1:]]
    dashboard_script = next(s for s in scripts if s.startswith("js/dashboard.js?v="))
    assert scripts.index("js/api_client.js?v=1") < scripts.index(dashboard_script)
    assert scripts.index("js/app_store.js?v=1") < scripts.index(dashboard_script)
    dashboard = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    assert "RetirementApiClient.request" in dashboard
    assert "RetirementAppStore" in dashboard


def test_backend_route_adapters_delegate_to_feature_services():
    plan_routes = (ROOT / "src/server/plan_routes.py").read_text(encoding="utf-8")
    workbook_routes = (ROOT / "src/server/workbook_routes.py").read_text(encoding="utf-8")
    assert "pricing_service.refresh_prices" in plan_routes
    assert "pricing_service.run_price_symbol_trace" in plan_routes
    assert "pricing_service.latest_price_snapshots" in plan_routes
    assert "holdings_service.read_holdings" in workbook_routes
    assert "holdings_service.save_holdings" in workbook_routes


def test_healthcare_terminology_aliases_support_legacy_ids_without_user_facing_premium_language():
    assert canonical_id("wellness_premium") == "healthcare_premium"
    assert canonical_id("pre65_wellness_premium") == "healthcare_premium"
    assert user_label("wellness_premium") == "Healthcare Premium"
    payload = healthcare_alias_payload()
    labels = {a["canonical_label"] for a in payload["aliases"]}
    assert "Healthcare Premium" in labels
    assert contains_user_facing_legacy_wellness("Annual Pre-65 Wellness Premium") is True
    assert contains_user_facing_legacy_wellness("Annual Pre-65 Healthcare Premium") is False


def test_clean_overlay_validator_covers_contract_route_and_new_modules():
    script = (ROOT / "tools/validate_clean_overlay.py").read_text(encoding="utf-8")
    assert '"/api/contracts"' in script
    assert "frontend/js/api_client.js" in script
    assert "frontend/js/app_store.js" in script
    assert "src/server_services/pricing_service.py" in script
    assert "src/server_services/holdings_service.py" in script
