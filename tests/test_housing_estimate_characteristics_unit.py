# Slice 2 (docs/superpowers/plans/2026-09-09-housing-estimate-realism-and-
# dollar-convention-design.md, §3.3): the five realism characteristics that
# replace the Estimator's fixed 3BR/2BA/single-family/1800-2500sqft profile.
# Pure-function coverage per §6 item 2 -- no plan-file or HTTP mocking needed.

from src.server_services.strategy_asset_service import (
    BATHROOM_MULT,
    BEDROOM_MULT,
    PROPERTY_TYPE_MULT,
    SQFT_BAND_MULT,
    built_within_years_mult,
    housing_state_estimate_payload,
)


def _base_purchase_price(state="TX", **overrides):
    payload, status = housing_state_estimate_payload({"state": state, "type": "purchase", **overrides})
    assert status == 200
    return payload["estimate"]["purchase_price"]


def test_bedroom_multiplier_moves_price_monotonically():
    prices = {n: _base_purchase_price(bedrooms=n) for n in (2, 3, 4, 5)}
    assert prices[2] < prices[3] < prices[4] < prices[5]
    # 3 is the default/neutral bedroom count (design §3.3's stated default).
    assert BEDROOM_MULT[3] == 1.00


def test_bedrooms_outside_range_clamp_to_2_5():
    assert _base_purchase_price(bedrooms=1) == _base_purchase_price(bedrooms=2)
    assert _base_purchase_price(bedrooms=9) == _base_purchase_price(bedrooms=5)
    assert _base_purchase_price(bedrooms="not-a-number") == _base_purchase_price(bedrooms=3)


def test_bathroom_multiplier_moves_price_monotonically():
    prices = {n: _base_purchase_price(bathrooms=n) for n in (1, 1.5, 2, 2.5, 3, 3.5)}
    ordered = [prices[n] for n in (1, 1.5, 2, 2.5, 3, 3.5)]
    assert ordered == sorted(ordered)
    assert BATHROOM_MULT[2] == 1.00


def test_bathrooms_accepts_the_3_5_plus_label():
    assert _base_purchase_price(bathrooms="3.5+") == _base_purchase_price(bathrooms=3.5)


def test_bathrooms_unrecognized_value_falls_back_to_default():
    assert _base_purchase_price(bathrooms="nonsense") == _base_purchase_price(bathrooms=2)


def test_property_type_multiplier_ordering():
    prices = {t: _base_purchase_price(property_type=t) for t in PROPERTY_TYPE_MULT}
    assert prices["condo"] < prices["townhome"] < prices["duplex"] < prices["single_family"]
    assert PROPERTY_TYPE_MULT["single_family"] == 1.00


def test_property_type_unrecognized_value_falls_back_to_single_family():
    assert _base_purchase_price(property_type="mansion") == _base_purchase_price(property_type="single_family")


def test_apartment_is_the_cheapest_property_type():
    # Apartment is rental-only in the optimizer (see actions_for_location in
    # candidates.py); its price multiplier still needs to exist here for the
    # manual Housing page's "Estimate fields" button and the state-level
    # fallback price estimate (plan_variant._estimate_for_location), both of
    # which price any property_type unconditionally.
    prices = {t: _base_purchase_price(property_type=t) for t in PROPERTY_TYPE_MULT}
    assert prices["apartment"] < prices["condo"]


def test_sqft_band_multiplier_ordering():
    prices = {
        b: _base_purchase_price(sqft_band=b)
        for b in ("under_1200", "1200_1800", "1800_2500", "2500_3500", "over_3500")
    }
    assert prices["under_1200"] < prices["1200_1800"] < prices["1800_2500"] < prices["2500_3500"] < prices["over_3500"]
    assert SQFT_BAND_MULT["1800_2500"] == 1.00


def test_sqft_band_unrecognized_value_falls_back_to_default_band():
    assert _base_purchase_price(sqft_band="huge") == _base_purchase_price(sqft_band="1800_2500")


def test_built_within_years_banding_function():
    assert built_within_years_mult(None) == 1.00
    assert built_within_years_mult(0) == 1.15
    assert built_within_years_mult(2) == 1.15
    assert built_within_years_mult(3) == 1.05
    assert built_within_years_mult(10) == 1.05
    assert built_within_years_mult(11) == 1.00
    assert built_within_years_mult(30) == 1.00
    assert built_within_years_mult(31) == 0.90


def test_built_within_years_blank_is_the_no_preference_default():
    assert _base_purchase_price(built_within_years="") == _base_purchase_price()
    assert _base_purchase_price() == _base_purchase_price(built_within_years=None)


def test_built_within_years_negative_input_clamped_to_zero():
    assert _base_purchase_price(built_within_years=-5) == _base_purchase_price(built_within_years=0)


def test_property_type_floors_hoa_pct_and_discounts_maintenance_for_condo_and_townhome():
    for ptype in ("condo", "townhome"):
        payload, _ = housing_state_estimate_payload({"state": "TX", "type": "purchase", "property_type": ptype})
        estimate = payload["estimate"]
        assert estimate["hoa_pct"] >= 0.004
        sf_payload, _ = housing_state_estimate_payload({"state": "TX", "type": "purchase", "property_type": "single_family"})
        sf_maintenance = sf_payload["estimate"]["maintenance_annual"]
        # condo/townhome price lower than single_family, so the 0.4x discount
        # on top of an already-lower base maintenance figure must land well
        # below the single_family baseline.
        assert estimate["maintenance_annual"] < sf_maintenance * 0.4 + 1e-6


def test_property_type_floor_does_not_lower_an_already_higher_hoa_pct():
    # Dense urban TX townhome purchase with large characteristics pushes
    # hoa_pct comfortably above the 0.004 floor before the property-type
    # adjustment; the floor must not clobber it back down to 0.004.
    args = {
        "state": "TX",
        "type": "purchase",
        "city_type": "urban",
        "population_size": 600_000,
        "bedrooms": 5,
        "bathrooms": 3.5,
        "property_type": "townhome",
        "sqft_band": "over_3500",
    }
    payload, _ = housing_state_estimate_payload(args)
    estimate = payload["estimate"]
    unfloored = round(
        0.003
        * 1.30  # city_mult (urban)
        * 1.20  # pop_mult (>500k)
        * BEDROOM_MULT[5]
        * BATHROOM_MULT[3.5]
        * PROPERTY_TYPE_MULT["townhome"]
        * SQFT_BAND_MULT["over_3500"],
        4,
    )
    assert unfloored > 0.004
    assert estimate["hoa_pct"] == unfloored


def test_single_family_property_type_does_not_apply_the_condo_townhome_adjustment():
    payload, _ = housing_state_estimate_payload({"state": "AZ", "type": "purchase", "property_type": "single_family"})
    estimate = payload["estimate"]
    assert estimate["hoa_pct"] < 0.004


def test_all_default_characteristics_are_multiplicatively_neutral():
    # Design §3.3: defaults match today's implicit fixed profile, so the
    # combined characteristic multiplier must be exactly 1.0x -- omitting the
    # new fields entirely must reproduce the pre-Slice-2 city_mult*pop_mult-only
    # pricing bit-for-bit.
    with_defaults, _ = housing_state_estimate_payload(
        {
            "state": "IL",
            "type": "purchase",
            "city_type": "suburban",
            "population_size": 20000,
            "bedrooms": 3,
            "bathrooms": 2,
            "property_type": "single_family",
            "sqft_band": "1800_2500",
            "built_within_years": None,
        }
    )
    without_new_fields, _ = housing_state_estimate_payload(
        {"state": "IL", "type": "purchase", "city_type": "suburban", "population_size": 20000}
    )
    assert with_defaults["estimate"]["purchase_price"] == without_new_fields["estimate"]["purchase_price"]
    assert with_defaults["estimate"]["monthly_rent"] == without_new_fields["estimate"]["monthly_rent"]
    assert with_defaults["estimate"]["maintenance_annual"] == without_new_fields["estimate"]["maintenance_annual"]
    assert with_defaults["estimate"]["hoa_pct"] == without_new_fields["estimate"]["hoa_pct"]


def test_estimate_response_echoes_the_five_characteristics():
    payload, _ = housing_state_estimate_payload(
        {
            "state": "IL",
            "type": "purchase",
            "bedrooms": 5,
            "bathrooms": "3.5+",
            "property_type": "condo",
            "sqft_band": "over_3500",
            "built_within_years": 1,
        }
    )
    estimate = payload["estimate"]
    assert estimate["bedrooms"] == 5
    assert estimate["bathrooms"] == 3.5
    assert estimate["property_type"] == "condo"
    assert estimate["sqft_band"] == "over_3500"
    assert estimate["built_within_years"] == 1
    assert "5+BR" in estimate["note"]
    assert "3.5+BA" in estimate["note"]
    assert "condo" in estimate["note"]


def test_rounding_stability_purchase_price_and_monthly_rent_land_on_expected_grids():
    payload, _ = housing_state_estimate_payload(
        {"state": "FL", "type": "purchase", "bedrooms": 4, "bathrooms": 2.5, "property_type": "duplex", "sqft_band": "2500_3500"}
    )
    estimate = payload["estimate"]
    assert estimate["purchase_price"] % 1000 == 0
    rent_payload, _ = housing_state_estimate_payload(
        {"state": "FL", "type": "rent", "bedrooms": 4, "bathrooms": 2.5, "property_type": "duplex", "sqft_band": "2500_3500"}
    )
    rent_estimate = rent_payload["estimate"]
    assert rent_estimate["monthly_rent"] % 10 == 0
