from pathlib import Path


def test_pricing_service_owns_single_symbol_job_lifecycle():
    service = Path("src/server_services/pricing_service.py").read_text(encoding="utf-8")
    assert "class PriceSymbolTestRegistry" in service
    assert "def single_symbol_test_payload" in service
    assert "threading.Thread" in service
    assert "uuid.uuid4" in service
    assert "traceback.format_exc" in service
    # HTTP-runtime-independence itself is asserted once, for every service
    # module, by the AST-based check in test_126_service_extraction.py.


def test_plan_routes_keep_thin_pricing_tester_adapter():
    routes = Path("src/server/plan_routes.py").read_text(encoding="utf-8")
    assert "PriceSymbolTestRegistry()" in routes
    assert "single_symbol_test_payload(" in routes
    assert ".status_payload(job_id)" in routes
    assert "threading.Lock" not in routes
    assert "uuid.uuid4" not in routes
    assert "traceback.format_exc" not in routes
    assert "_PRICE_TEST_JOBS" not in routes


def test_housing_state_estimate_logic_lives_in_strategy_asset_service():
    service = Path("src/server_services/strategy_asset_service.py").read_text(encoding="utf-8")
    routes = Path("src/server/plan_routes.py").read_text(encoding="utf-8")
    assert "def housing_state_estimate_payload" in service
    assert "STATE_ESTIMATES" in service
    assert "population_size" in service
    assert "city_multipliers" in service
    assert "STATE_ESTIMATES" not in routes
    assert "housing_state_estimate_payload(" in routes


def test_housing_state_estimate_payload_purchase_and_rent_contracts():
    from src.server_services.strategy_asset_service import housing_state_estimate_payload

    payload, status = housing_state_estimate_payload({"state": "TX", "type": "purchase", "city_type": "suburban", "population_size": 20000})
    assert status == 200
    assert payload["success"] is True
    estimate = payload["estimate"]
    assert estimate["state"] == "TX"
    assert estimate["type"] == "purchase"
    assert estimate["purchase_price"] > 0
    assert estimate["maintenance_annual"] > 0
    assert estimate["mortgage_rate_pct"] > 0

    rent_payload, rent_status = housing_state_estimate_payload({"state": "TX", "type": "rent", "city_type": "rural", "population_size": 8000})
    assert rent_status == 200
    rent = rent_payload["estimate"]
    assert rent["type"] == "rent"
    assert rent["maintenance_annual"] == 0
    assert 180 <= rent["insurance_annual"] <= 450


def test_route_manifest_and_contract_registry_include_extracted_endpoints():
    manifest = Path("src/server/route_manifest.py").read_text(encoding="utf-8")
    contracts = Path("src/api_contracts.py").read_text(encoding="utf-8")
    assert '"/api/prices/test-symbol"' in manifest
    assert '"/api/prices/test-symbol/start"' in manifest
    assert '"/api/prices/test-symbol/status/<job_id>"' in manifest
    assert '"/api/housing/state-estimate"' in manifest
    assert "price_symbol_test_job_start_v1" in contracts
    assert "price_symbol_test_job_status_v1" in contracts
    assert "housing_state_estimate_v1" in contracts
