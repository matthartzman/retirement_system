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


def test_housing_state_estimate_blank_start_year_is_a_no_op():
    # housing-estimate-realism-and-dollar-convention-design.md sect3.2: if
    # start_year is blank, years_out = 0 and the translation factor is 1.0 --
    # the estimate must be byte-for-byte identical to the no-start_year call.
    from src.server_services.strategy_asset_service import housing_state_estimate_payload

    base = {"state": "IL", "type": "purchase", "city_type": "suburban", "population_size": 20000}
    without, _ = housing_state_estimate_payload(dict(base))
    with_blank, _ = housing_state_estimate_payload(dict(base, start_year=""))
    with_zero, _ = housing_state_estimate_payload(dict(base, start_year=0))
    assert without["estimate"] == with_blank["estimate"]
    assert without["estimate"] == with_zero["estimate"]


def test_housing_state_estimate_translates_purchase_price_by_home_appr():
    from src.server_services.strategy_asset_service import housing_state_estimate_payload

    plan_start = _current_plan_start()
    years_out = 5
    today_payload, _ = housing_state_estimate_payload(
        {"state": "IL", "type": "purchase", "city_type": "suburban", "population_size": 20000}
    )
    future_payload, _ = housing_state_estimate_payload({
        "state": "IL", "type": "purchase", "city_type": "suburban", "population_size": 20000,
        "start_year": plan_start + years_out, "home_appr": 0.04, "inflation_general": 0.025,
    })
    today_price = today_payload["estimate"]["purchase_price"]
    future_price = future_payload["estimate"]["purchase_price"]
    expected = round(today_price * (1.04 ** years_out) / 1000) * 1000
    assert future_price == expected
    assert future_price > today_price


def test_housing_state_estimate_translates_rent_and_recurring_costs_by_cpi():
    from src.server_services.strategy_asset_service import housing_state_estimate_payload

    plan_start = _current_plan_start()
    years_out = 8
    today_payload, _ = housing_state_estimate_payload(
        {"state": "TX", "type": "rent", "city_type": "rural", "population_size": 8000}
    )
    future_payload, _ = housing_state_estimate_payload({
        "state": "TX", "type": "rent", "city_type": "rural", "population_size": 8000,
        "start_year": plan_start + years_out, "home_appr": 0.03, "inflation_general": 0.03,
    })
    today_rent = today_payload["estimate"]["monthly_rent"]
    future_rent = future_payload["estimate"]["monthly_rent"]
    expected_rent = round(today_rent * (1.03 ** years_out) / 10) * 10
    assert future_rent == expected_rent

    today_insurance = today_payload["estimate"]["insurance_annual"]
    future_insurance = future_payload["estimate"]["insurance_annual"]
    assert future_insurance == round(today_insurance * (1.03 ** years_out))

    today_utilities = today_payload["estimate"]["utilities_annual"]
    future_utilities = future_payload["estimate"]["utilities_annual"]
    assert future_utilities == round(today_utilities * (1.03 ** years_out))


def test_housing_state_estimate_does_not_translate_pct_or_rate_fields():
    # re_tax_pct/hoa_pct (percentages of home value) and mortgage_rate_pct
    # (a rate assumption, not a monetary quantity) are exempt per sect3.2 --
    # translating purchase_price already keeps the pct fields consistent.
    from src.server_services.strategy_asset_service import housing_state_estimate_payload

    plan_start = _current_plan_start()
    today_payload, _ = housing_state_estimate_payload(
        {"state": "FL", "type": "purchase", "city_type": "urban", "population_size": 700000}
    )
    future_payload, _ = housing_state_estimate_payload({
        "state": "FL", "type": "purchase", "city_type": "urban", "population_size": 700000,
        "start_year": plan_start + 12, "home_appr": 0.035, "inflation_general": 0.025,
    })
    assert future_payload["estimate"]["re_tax_pct"] == today_payload["estimate"]["re_tax_pct"]
    assert future_payload["estimate"]["hoa_pct"] == today_payload["estimate"]["hoa_pct"]
    assert future_payload["estimate"]["mortgage_rate_pct"] == today_payload["estimate"]["mortgage_rate_pct"]


def test_housing_state_estimate_omitted_rates_fall_back_to_sane_defaults():
    # A caller that omits home_appr/inflation_general still gets a real
    # translation (not a crash, not a 0% rate) via HOME_APPR_DEFAULT /
    # INFLATION_GENERAL_DEFAULT.
    from src.server_services.strategy_asset_service import (
        HOME_APPR_DEFAULT,
        INFLATION_GENERAL_DEFAULT,
        housing_state_estimate_payload,
    )

    plan_start = _current_plan_start()
    years_out = 6
    today_payload, _ = housing_state_estimate_payload(
        {"state": "AZ", "type": "purchase", "city_type": "suburban", "population_size": 20000}
    )
    future_payload, _ = housing_state_estimate_payload({
        "state": "AZ", "type": "purchase", "city_type": "suburban", "population_size": 20000,
        "start_year": plan_start + years_out,
    })
    today_price = today_payload["estimate"]["purchase_price"]
    expected = round(today_price * ((1 + HOME_APPR_DEFAULT) ** years_out) / 1000) * 1000
    assert future_payload["estimate"]["purchase_price"] == expected
    assert HOME_APPR_DEFAULT > 0
    assert INFLATION_GENERAL_DEFAULT > 0


def test_housing_state_estimate_note_states_dollar_year_basis_when_start_year_given():
    from src.server_services.strategy_asset_service import housing_state_estimate_payload

    plan_start = _current_plan_start()
    no_year_payload, _ = housing_state_estimate_payload(
        {"state": "IL", "type": "purchase", "city_type": "suburban", "population_size": 20000}
    )
    assert str(plan_start + 9) not in no_year_payload["estimate"]["note"]
    assert "All values are editable." in no_year_payload["estimate"]["note"]

    future_payload, _ = housing_state_estimate_payload({
        "state": "IL", "type": "purchase", "city_type": "suburban", "population_size": 20000,
        "start_year": plan_start + 9, "home_appr": 0.03, "inflation_general": 0.025,
    })
    note = future_payload["estimate"]["note"]
    assert str(plan_start + 9) in note
    assert "All values are editable." in note


def _current_plan_start():
    from src.platform_runtime import today
    return today().year
