"""Unit coverage for #331 B1-B2 (2026-09-19 housing-optimizer-anchor-flow-
and-timing-design.md §6): plan_variant prices a future move in that move's
OWN year's dollars instead of today's, and the screen's budget bounds are
deflated to match.

Scope deliberately narrow: ``estimate_housing_cost``'s own Slice-1
today's-dollars -> start_year-dollars translation (the price/CPI factors,
the percentage fields staying untouched) already has coverage in
test_pricing_housing_service_extraction_functional.py. This file covers the
NEW code -- plan_variant threading start_year/home_appr/inflation_general
through to that translation, tier 2's own escalation of Location.est_price,
tier 1 staying unescalated, and screen.py's budget-bounds deflation -- not a
second copy of the Slice-1 math itself.
"""
from __future__ import annotations

import pytest

from src import platform_runtime
from src.housing.models import HousingCandidate, Location, Move, OriginalHome
from src.housing.plan_variant import (
    _apply_candidate,
    _purchase_price_for_location,
    _purchase_step,
    _years_out,
)
from src.housing.zip_screen.schema import ZipRecord
from src.housing.zip_screen.screen import ScreenRequest, run_screen

pytestmark = pytest.mark.unit

PLAN_START = platform_runtime.today().year


# ---------------------------------------------------------------------------
# _years_out
# ---------------------------------------------------------------------------

def test_years_out_zero_for_a_current_year_move():
    assert _years_out(PLAN_START) == 0


def test_years_out_zero_for_a_past_year_move():
    assert _years_out(PLAN_START - 5) == 0


def test_years_out_positive_for_a_future_move():
    assert _years_out(PLAN_START + 10) == 10


# ---------------------------------------------------------------------------
# plan_variant._purchase_price_for_location -- tier 2 (est_price) escalation
# ---------------------------------------------------------------------------

def test_tier2_est_price_escalates_by_home_appr_over_years_out():
    loc = Location(state="Texas", est_price=500000.0)
    price = _purchase_price_for_location(
        loc, start_year=PLAN_START + 10, home_appr=0.03, inflation_general=0.025)
    assert price == pytest.approx(500000.0 * (1.03 ** 10))


def test_tier2_est_price_unescalated_for_years_out_zero():
    loc = Location(state="Texas", est_price=500000.0)
    price = _purchase_price_for_location(
        loc, start_year=PLAN_START, home_appr=0.03, inflation_general=0.025)
    assert price == 500000.0


def test_tier2_uses_home_appr_not_inflation_general():
    """Purchase price tracks home_appr, the same rate the engine uses for
    the home's own post-purchase growth -- not CPI."""
    loc = Location(state="Texas", est_price=500000.0)
    price = _purchase_price_for_location(
        loc, start_year=PLAN_START + 10, home_appr=0.05, inflation_general=0.10)
    assert price == pytest.approx(500000.0 * (1.05 ** 10))


# ---------------------------------------------------------------------------
# plan_variant._purchase_price_for_location -- tier 1 stays unescalated
# ---------------------------------------------------------------------------

def test_tier1_price_range_midpoint_is_never_escalated():
    """OQ-2: an explicit target_purchase_price_range is already move-year
    dollars, so the midpoint is consumed as-is regardless of years_out --
    this is the fix's deliberate DELETION of escalation at this site, not
    an addition."""
    loc = Location(state="Texas", target_purchase_price_range=(400000.0, 500000.0),
                   est_price=999999.0)
    near = _purchase_price_for_location(
        loc, start_year=PLAN_START, home_appr=0.03, inflation_general=0.025)
    far = _purchase_price_for_location(
        loc, start_year=PLAN_START + 15, home_appr=0.03, inflation_general=0.025)
    assert near == far == 450000.0


# ---------------------------------------------------------------------------
# plan_variant._purchase_step -- percentages untouched, threading end to end
# ---------------------------------------------------------------------------

def test_purchase_step_percentages_are_identical_regardless_of_years_out():
    loc = Location(state="Texas", city_type="suburban", population_size=150000)
    near = _purchase_step("s", loc, PLAN_START, None, home_appr=0.03, inflation_general=0.025)
    far = _purchase_step("s", loc, PLAN_START + 20, None, home_appr=0.03, inflation_general=0.025)
    assert near["real_estate_tax_pct"] == far["real_estate_tax_pct"]
    assert near["hoa_pct"] == far["hoa_pct"]
    assert near["mortgage_rate_pct"] == far["mortgage_rate_pct"]
    assert near["down_payment_pct"] == far["down_payment_pct"]


def test_purchase_step_dollar_fields_grow_with_years_out():
    loc = Location(state="Texas", city_type="suburban", population_size=150000)
    near = _purchase_step("s", loc, PLAN_START, None, home_appr=0.03, inflation_general=0.025)
    far = _purchase_step("s", loc, PLAN_START + 20, None, home_appr=0.03, inflation_general=0.025)
    assert far["purchase_price"] > near["purchase_price"]
    assert far["insurance_annual"] > near["insurance_annual"]


def test_apply_candidate_reads_home_appr_and_inf_from_the_config_not_a_default():
    """_apply_candidate must read c['home_appr']/c['inf'] (the same two
    keys, same fallbacks, priced_step in housing_comparison.py reads) --
    not silently fall back to the module defaults when the plan sets its
    own rate."""
    loc = Location(state="Texas", est_price=500000.0)
    move = Move(index=1, acquisition_year=PLAN_START + 10, action="buy", location=loc)
    cand = HousingCandidate(
        original_home=OriginalHome(disposition="sell", sale_year=PLAN_START + 9),
        moves=(move,),
    )
    c_low = {"state": "Illinois", "home_sale_yr": 0, "home_appr": 0.01, "inf": 0.02}
    c_high = {"state": "Illinois", "home_sale_yr": 0, "home_appr": 0.08, "inf": 0.02}
    _apply_candidate(c_low, cand, down_payment_pct=0.20, mortgage_rate_pct=0.065)
    _apply_candidate(c_high, cand, down_payment_pct=0.20, mortgage_rate_pct=0.065)
    price_low = c_low["next_housing_steps"][0]["purchase_price"]
    price_high = c_high["next_housing_steps"][0]["purchase_price"]
    assert price_high > price_low
    assert price_low == pytest.approx(500000.0 * (1.01 ** 10))
    assert price_high == pytest.approx(500000.0 * (1.08 ** 10))


# ---------------------------------------------------------------------------
# screen.py -- budget bounds deflated exactly once; funnel unchanged for a
# current-year window
# ---------------------------------------------------------------------------

def _rec(zcta="60601", lat=41.88, lon=-87.63, state="Illinois",
         median=300000.0, state_median=250000.0):
    """A record dense enough to clear the coverage floor on every percentile
    (mirrors test_zip_screen_filters_unit.py's fixture helper)."""
    return ZipRecord(
        zcta=zcta, state=state, state_abbrev="IL", primary_place=f"Place{zcta}",
        place_population=100000, zcta_population=40000, land_area_sqmi=10.0,
        lat=lat, lon=lon, median_home_value=median, state_median_home_value=state_median,
        upi=0.02,
        pctl_owner_occupied=0.80, pctl_poverty=0.80, pctl_non_student_poverty=0.80,
        pctl_tenure=0.80, pctl_tenure_nonstudent=0.80, pctl_vacancy_deviation=0.80,
        pctl_eviction_execution=None, pctl_eviction_filing=None, pctl_median_income=0.80,
    )


def _table():
    # Anchor plus one in-range candidate at a known price ratio, far enough
    # apart (~6.9 mi) to clear DEDUP_RADIUS_MILES (5.0) -- otherwise
    # deduplicate() collapses the identically-scored pair into one survivor
    # and all_passing would only ever show one of them.
    anchor = _rec("60601")
    candidate = _rec("60602", lat=41.98, median=300000.0, state_median=250000.0)
    return {"60601": anchor, "60602": candidate}


def _req(**kw):
    base = dict(
        anchor_zip="60601", radius_miles=10, min_quality_score=0.0,
        shortlist_size=5, property_spec={}, area_type="any", max_population=None,
    )
    base.update(kw)
    return ScreenRequest(**base)


def test_budget_bounds_deflated_once_for_a_future_reference_year():
    """A price range whose bounds are move-year dollars must be divided by
    the appreciation factor before the affordability comparison -- not
    applied to est_price (screen.estimate_price stays untouched)."""
    table = _table()
    # Candidate ZIP's today's-dollars est_price = 300000/250000 * base
    # (base = state_median_home_value = 250000) = 300000.
    today_price = 300000.0
    years_out = 10
    home_appr = 0.03
    deflator = (1.0 + home_appr) ** years_out
    move_year_bounds = (today_price * deflator - 1.0, today_price * deflator + 1.0)

    req = _req(
        property_spec={"target_purchase_price_range": list(move_year_bounds)},
        home_appr=home_appr, plan_start=PLAN_START,
        reference_year=PLAN_START + years_out,
    )
    result = run_screen(req, table=table, current_state="")
    passing_zips = {z.zcta for z in result.all_passing}
    assert "60602" in passing_zips, (
        "a ZIP priced at today's-dollars 300000 must pass a budget stated in "
        "move-year dollars once the bounds are deflated back to today's basis"
    )
    zip_row = next(z for z in result.all_passing if z.zcta == "60602")
    # est_price itself is untouched -- still today's dollars.
    assert zip_row.est_price == pytest.approx(today_price)


def test_budget_bounds_not_deflated_when_reference_year_is_not_in_the_future():
    """years_out floors at zero: a current-year (or past) reference_year
    must not move the bounds at all -- deflator 1.0, an exact no-op."""
    table = _table()
    today_price = 300000.0
    req_no_ref = _req(
        property_spec={"target_purchase_price_range": [today_price - 1.0, today_price + 1.0]},
    )
    req_current_year = _req(
        property_spec={"target_purchase_price_range": [today_price - 1.0, today_price + 1.0]},
        home_appr=0.03, plan_start=PLAN_START, reference_year=PLAN_START,
    )
    funnel_no_ref = run_screen(req_no_ref, table=table, current_state="").funnel
    funnel_current = run_screen(req_current_year, table=table, current_state="").funnel
    assert funnel_no_ref == funnel_current


def test_est_price_basis_year_is_plan_start():
    table = _table()
    req = _req(
        property_spec={"target_purchase_price_range": [0.0, 10_000_000.0]},
        home_appr=0.03, plan_start=PLAN_START, reference_year=PLAN_START + 5,
    )
    result = run_screen(req, table=table, current_state="")
    assert all(z.est_price_basis_year == PLAN_START for z in result.all_passing)
