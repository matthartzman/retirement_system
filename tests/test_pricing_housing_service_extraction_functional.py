from pathlib import Path

# The "service exists" + "routes delegate" checks that used to live here are
# generalized (system review 2026-07-21, Q6) into SERVICE_ROUTE_PAIRS in
# test_service_extraction_functional.py, alongside every other extracted service's
# equivalent pair. Only this file's genuine behavior + manifest tests remain.


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


def test_housing_state_estimate_scales_hoa_by_geography():
    from src.server_services.strategy_asset_service import STATE_ESTIMATES, housing_state_estimate_payload

    base_hoa_pct = STATE_ESTIMATES["TX"]["hoa_pct"]

    urban_payload, _ = housing_state_estimate_payload({"state": "TX", "type": "purchase", "city_type": "urban", "population_size": 600_000})
    suburban_payload, _ = housing_state_estimate_payload({"state": "TX", "type": "purchase", "city_type": "suburban", "population_size": 25_000})
    rural_payload, _ = housing_state_estimate_payload({"state": "TX", "type": "purchase", "city_type": "rural", "population_size": 5_000})

    urban_hoa = urban_payload["estimate"]["hoa_pct"]
    suburban_hoa = suburban_payload["estimate"]["hoa_pct"]
    rural_hoa = rural_payload["estimate"]["hoa_pct"]

    # A flat per-state hoa_pct (the pre-fix behavior) would make all three equal.
    assert urban_hoa > suburban_hoa > rural_hoa
    # Suburban/25k population is the multiplier baseline (city_mult=1.00, pop_mult=1.00).
    assert suburban_hoa == round(base_hoa_pct, 4)


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
