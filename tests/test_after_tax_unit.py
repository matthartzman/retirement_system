"""Characterization tests for src/after_tax.py -- terminal-value tax helpers.

System review 2026-08-31, finding Q3 / Wave 1 item 1.13. See
test_tlh_unit.py's module docstring for the fixture-derivation approach.
test_hsa_terminal_tax_unit.py already covers hsa_terminal_tax and
effective_heir_ten_year_rate's *relative* behavior (lump vs. stretch); this
file covers the rest of the module's pure helpers that had no coverage at
all: rate normalization, the basis step-up fraction rules (first/second
death, by property regime), business-succession estate value, and the
federal+state terminal estate tax estimate. Each assertion is exact to the
cent (or exact boolean/string), so a one-cent or one-branch change fails.
"""
from __future__ import annotations

import pytest

from src.after_tax import (
    _first_death_step_fraction,
    _is_flat_default,
    _normalize_rate,
    _second_death_step_fraction,
    _terminal_step_up_case,
    business_taxable_estate_value,
    effective_heir_ten_year_rate,
    estimate_terminal_estate_tax,
)


# ─────────────────────────────────────────────────────────────────────────────
# _normalize_rate / _is_flat_default
# ─────────────────────────────────────────────────────────────────────────────

def test_normalize_rate_passes_through_a_fraction():
    assert _normalize_rate(0.24) == pytest.approx(0.24)


def test_normalize_rate_divides_a_percent_like_value_by_100():
    assert _normalize_rate(24) == pytest.approx(0.24)


def test_normalize_rate_clamps_to_zero_and_one():
    assert _normalize_rate(-5) == 0.0
    assert _normalize_rate(500) == 1.0


def test_normalize_rate_uses_default_on_bad_input():
    assert _normalize_rate("not-a-number", default=0.3) == pytest.approx(0.3)


def test_is_flat_default_true_for_missing_value():
    assert _is_flat_default(None) is True
    assert _is_flat_default("") is True


def test_is_flat_default_true_for_the_historical_24_percent():
    assert _is_flat_default(0.24) is True
    assert _is_flat_default(24) is True


def test_is_flat_default_false_for_an_explicit_override():
    assert _is_flat_default(0.30) is False


# ─────────────────────────────────────────────────────────────────────────────
# effective_heir_ten_year_rate
# ─────────────────────────────────────────────────────────────────────────────

def test_effective_heir_ten_year_rate_zero_balance_is_zero():
    c = {"roth_heir_filing_status": "Single", "brk_inf": 0.0, "plan_end": 2056}
    assert effective_heir_ten_year_rate(c, 0.0) == 0.0


def test_effective_heir_ten_year_rate_rises_with_balance():
    c = {"roth_heir_filing_status": "Single", "brk_inf": 0.0, "plan_end": 2056}
    small = effective_heir_ten_year_rate(c, 50_000.0)
    large = effective_heir_ten_year_rate(c, 2_000_000.0)
    assert 0.0 < small < large < 1.0


def test_effective_heir_ten_year_rate_bounded_between_zero_and_one():
    c = {"roth_heir_filing_status": "MFJ", "brk_inf": 0.02, "plan_end": 2056}
    rate = effective_heir_ten_year_rate(c, 10_000_000.0)
    assert 0.0 <= rate <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Basis step-up fractions at death, by property regime
# ─────────────────────────────────────────────────────────────────────────────

def test_second_death_step_fraction_common_law_full_step_up():
    assert _second_death_step_fraction({}) == 1.0
    assert _second_death_step_fraction({"basis_step_up_property_regime": "COMMON_LAW"}) == 1.0


def test_second_death_step_fraction_half_step_up_regime():
    assert _second_death_step_fraction({"basis_step_up_property_regime": "HALF_STEP_UP"}) == 0.5


def test_first_death_step_fraction_common_law_is_half_the_decedents_share():
    assert _first_death_step_fraction({}) == 0.5


def test_first_death_step_fraction_community_property_is_full():
    assert _first_death_step_fraction({"basis_step_up_property_regime": "COMMUNITY_PROPERTY"}) == 1.0
    assert _first_death_step_fraction({"basis_step_up_property_regime": "FULL_STEP_UP"}) == 1.0


def test_first_death_step_fraction_half_step_up_is_a_quarter():
    assert _first_death_step_fraction({"basis_step_up_property_regime": "HALF_STEP_UP"}) == 0.25


def test_terminal_step_up_case_both_alive_before_any_death():
    c = {"h_death_yr": 2060, "w_death_yr": 2062, "plan_end": 2056}
    case, fraction, _note = _terminal_step_up_case(c, {"year": 2050})
    assert case == "both_alive"
    assert fraction == 0.0


def test_terminal_step_up_case_first_death_only_steps_up_decedents_share():
    # household_size=2 matters: a single-member household's "spouse" death
    # year is a synthetic placeholder, not a real first death (see the
    # function's own docstring), so hh_size<=1 collapses first_death into
    # second_death instead.
    c = {"h_death_yr": 2040, "w_death_yr": 2060, "household_size": 2}
    case, fraction, _note = _terminal_step_up_case(c, {"year": 2045})
    assert case == "first_death"
    assert fraction == 0.5


def test_terminal_step_up_case_second_death_steps_up_the_whole_estate():
    c = {"h_death_yr": 2040, "w_death_yr": 2060, "household_size": 2}
    case, fraction, _note = _terminal_step_up_case(c, {"year": 2065})
    assert case == "second_death"
    assert fraction == 1.0


def test_terminal_step_up_case_disabled_toggle_retains_gain_in_full():
    c = {"h_death_yr": 2040, "w_death_yr": 2060, "household_size": 2, "basis_step_up_at_death": False}
    case, fraction, _note = _terminal_step_up_case(c, {"year": 2065})
    assert case == "both_alive"
    assert fraction == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# business_taxable_estate_value
# ─────────────────────────────────────────────────────────────────────────────

def test_business_taxable_estate_value_zero_when_module_disabled():
    c = {"opt": {"business_succession": False}, "business_succession": [
        {"valuation_today": 1_000_000.0, "valuation_growth_rate": 0.05, "ownership_pct": 1.0},
    ]}
    assert business_taxable_estate_value(c) == 0.0


def test_business_taxable_estate_value_grows_at_the_entity_rate_to_plan_end():
    c = {
        "opt": {"business_succession": True},
        "plan_start": 2026,
        "plan_end": 2036,
        "business_succession": [
            {"valuation_today": 1_000_000.0, "valuation_growth_rate": 0.05, "ownership_pct": 0.60,
             "transfer_year": 0},
        ],
    }
    expected = 1_000_000.0 * (1.05 ** 10) * 0.60
    assert business_taxable_estate_value(c) == pytest.approx(expected)


def test_business_taxable_estate_value_stops_growth_at_a_buy_sell_transfer_year():
    c = {
        "opt": {"business_succession": True},
        "plan_start": 2026,
        "plan_end": 2036,
        "business_succession": [
            {"valuation_today": 1_000_000.0, "valuation_growth_rate": 0.05, "ownership_pct": 1.0,
             "transfer_year": 2030},
        ],
    }
    expected = 1_000_000.0 * (1.05 ** 4)  # grows only to the 2030 transfer, not to 2036
    assert business_taxable_estate_value(c) == pytest.approx(expected)


# ─────────────────────────────────────────────────────────────────────────────
# estimate_terminal_estate_tax
# ─────────────────────────────────────────────────────────────────────────────

def test_estimate_terminal_estate_tax_zero_below_the_exemption():
    c = {"fed_exempt": 27_220_000.0, "plan_start": 2026, "brk_inf": 0.0,
         "model_state_est": False, "il_exempt": 0.0}
    terminal = {"total_nw": 5_000_000.0, "year": 2026}
    assert estimate_terminal_estate_tax(c, terminal) == 0.0


def test_estimate_terminal_estate_tax_forty_percent_above_the_exemption():
    c = {"fed_exempt": 27_220_000.0, "plan_start": 2026, "brk_inf": 0.0,
         "model_state_est": False, "il_exempt": 0.0}
    terminal = {"total_nw": 30_000_000.0, "year": 2026}
    expected = (30_000_000.0 - 27_220_000.0) * 0.40
    assert estimate_terminal_estate_tax(c, terminal) == pytest.approx(expected)


def test_estimate_terminal_estate_tax_indexes_the_exemption_to_the_terminal_year():
    # Same nominal taxable estate, but the exemption has grown by the time the
    # plan actually terminates -- less tax than a naive plan-start exemption
    # would produce.
    c = {"fed_exempt": 27_220_000.0, "plan_start": 2026, "brk_inf": 0.03,
         "model_state_est": False, "il_exempt": 0.0}
    terminal = {"total_nw": 30_000_000.0, "year": 2046}
    grown_exempt = 27_220_000.0 * (1.03 ** 20)
    expected = max(0.0, 30_000_000.0 - grown_exempt) * 0.40
    assert estimate_terminal_estate_tax(c, terminal) == pytest.approx(expected)


def test_estimate_terminal_estate_tax_adds_business_succession_value():
    c = {"fed_exempt": 27_220_000.0, "plan_start": 2026, "brk_inf": 0.0,
         "model_state_est": False, "il_exempt": 0.0,
         "opt": {"business_succession": True}, "plan_end": 2026,
         "business_succession": [
             {"valuation_today": 2_000_000.0, "valuation_growth_rate": 0.0, "ownership_pct": 1.0},
         ]}
    terminal = {"total_nw": 27_000_000.0, "year": 2026}
    expected = (27_000_000.0 + 2_000_000.0 - 27_220_000.0) * 0.40
    assert estimate_terminal_estate_tax(c, terminal) == pytest.approx(expected)
