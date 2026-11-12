"""ARC-001: per-year factor helpers lifted from the deterministic stage."""
import pytest

from src.projection_stages.year_factors import (
    basis_stepup_fraction,
    early_dist_tax_fn_for_year,
    infl_factor,
    spending_factor,
    ss_funding_factor,
    survivor_factor,
    taxable_portfolio_income_for_year,
)

C = {"plan_start": 2026, "inf": 0.03, "spend_inf": 0.01}


def test_inflation_and_spending_factors():
    assert infl_factor(C, 2036) == pytest.approx(1.03 ** 10)
    assert spending_factor(C, 2036) == pytest.approx(1.03 ** 10)
    manual = dict(C, core_spending_growth_mode="manual_override")
    assert spending_factor(manual, 2036) == pytest.approx(1.01 ** 10)
    assert spending_factor(manual, 2020) == 1.0


def test_survivor_factor_only_for_one_alive_in_a_couple():
    assert survivor_factor(True, 0.65, 1) == 0.65
    assert survivor_factor(True, 0.65, 2) == 1.0
    assert survivor_factor(True, 0.65, 0) == 1.0
    assert survivor_factor(False, 0.65, 1) == 1.0


def test_basis_step_up_regimes():
    assert basis_stepup_fraction({}, True) == 1.0
    assert basis_stepup_fraction({}, False) == 0.5
    assert basis_stepup_fraction({"basis_step_up_property_regime": "community_property"}, False) == 1.0
    assert basis_stepup_fraction({"basis_step_up_property_regime": "HALF_STEP_UP"}, True) == 0.5


def test_ss_funding_factor_cuts_from_the_configured_year():
    assert ss_funding_factor({}, 2031) == 1.0
    assert ss_funding_factor({}, 2032) == pytest.approx(0.78)
    assert ss_funding_factor({"ss_funding_discount_year": 2040, "ss_funding_discount_pct": 0.1}, 2040) == pytest.approx(0.9)
    assert ss_funding_factor({"ss_funding_discount_pct": 0.0}, 2050) == 1.0


def test_taxable_portfolio_income_counts_only_taxable_accounts():
    c = {"taxable_ids": ["brk"], "account_taxable_income_assumptions": {
        "brk": {"ordinary_yield": 0.01, "qualified_yield": 0.02, "tax_exempt_yield": 0.005},
        "ira": {"ordinary_yield": 0.5, "qualified_yield": 0.5, "tax_exempt_yield": 0.5}}}
    ordinary, qualified, exempt = taxable_portfolio_income_for_year(c, {"brk": 100_000.0, "ira": 1e6})
    assert (ordinary, qualified, exempt) == pytest.approx((1_000.0, 2_000.0, 500.0))


def test_early_distribution_fn_is_none_without_an_under_59_5_owner():
    c = {"members": [{"dob_yr": 1950, "dob_month": 1}], "account_registry": []}
    assert early_dist_tax_fn_for_year(c, 2030) is None
    assert early_dist_tax_fn_for_year({}, 2030) is None
