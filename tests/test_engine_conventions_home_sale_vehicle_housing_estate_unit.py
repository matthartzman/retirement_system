"""363 n / g / h / x / y: pin the conventions that were never directly tested (no engine change)."""
import copy
import os

import pytest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")


def _project(mutate=None):
    from src.planning_engines import project
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
    from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config

    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = _frozen_config()
        if mutate:
            mutate(c)
        return c, project(c)


@pytest.fixture(scope="module")
def frozen():
    return _project()


def test_n_home_sale_deposit_is_net_of_payoffs_and_leaves_other_liabilities_on_the_books():
    def mutate(c):
        c["home_sale_yr"] = 2035
        c["liabilities"] = [{"liability_id": "cc", "type": "credit_card", "label": "Card", "balance": 20000.0,
                             "interest_rate": 0.0, "monthly_payment": 0.0, "start_year": 0, "payoff_year": 0,
                             "payoff_month": 0, "carry_zero": True, "notes": ""}]

    _c, rows = _project(mutate)
    sale = next(r for r in rows if r["home_sale_gross"])
    assert sale["year"] == 2035
    # deposit = gross - selling costs - mortgage payoff - HELOC payoff (each once; the LTCG tax is funded later by the cascade)
    expected = (sale["home_sale_gross"] - sale["home_sale_costs"] - sale["home_sale_mort_off"]
                - sale["heloc_payoff"])
    assert sale["home_sale_net"] == pytest.approx(expected, abs=1.0)
    # the card is not netted against the proceeds: it stays a liability, subtracted once from net worth
    assert sale["additional_liabilities"] == pytest.approx(20000.0)
    assets = (sale["ann_nw"] + sale["pretax_nw"] + sale["roth_nw"] + sale["trust_nw"] + sale["cst_nw"]
              + sale["hsa_nw"] + sale["other_nw"])
    assert sale["total_nw"] == pytest.approx(assets - 20000.0, abs=1.0)
    assert sale["total_liabilities"] >= 20000.0


def test_g_vehicle_depreciation_counts_the_plan_start_year_and_ignores_deaths():
    def mutate(c):
        c["autos"], c["auto_dep_yrs"] = 40000.0, 8

    c, rows = _project(mutate)
    start = c["plan_start"]
    for r in rows:
        expect = max(0.0, 40000.0 - 40000.0 / 8 * (r["year"] - start + 1))
        assert r["autos_val"] == pytest.approx(expect), r["year"]
    by_year = {r["year"]: r["autos_val"] for r in rows}
    assert by_year[start] == pytest.approx(35000.0)          # the "+1": year 0 is already one year depreciated
    assert by_year[start + 7] == 0.0                          # fully depreciated after dep_yrs years, not dep_yrs + 1
    assert by_year[c["h_death_yr"]] == 0.0 and by_year[c["w_death_yr"]] == 0.0   # death years change nothing


def test_h_housing_total_is_the_sum_of_its_parts_and_property_tax_is_counted_once(frozen):
    _c, rows = frozen
    for r in rows:
        parts = (r["mortgage_payment_yr"] + r["real_estate_tax_yr"] + r["home_improvement_yr"] + r["rent_yr"]
                 + r["housing_operating_yr"])
        assert r["housing_total_yr"] == pytest.approx(parts), r["year"]
        assert r["mortgage"] == pytest.approx(r["mortgage_payment_yr"] + r["real_estate_tax_yr"] + r["home_improvement_yr"])
        assert r["housing_operating_yr"] == pytest.approx(
            r["housing_utilities_yr"] + r["housing_maintenance_yr"] + r["housing_other_yr"])
        if r["real_estate_tax_yr"] > 0:       # the SALT line uses the configured tax, never configured + estimated
            assert r["property_tax_for_salt"] == pytest.approx(r["real_estate_tax_yr"]) or \
                r["property_tax_for_salt"] <= r["real_estate_tax_yr"]


def test_y_survivor_factor_is_applied_once(frozen):
    c, rows = frozen
    by_year = {r["year"]: r for r in rows}
    first_survivor = c["h_death_yr"] + 1                      # the husband dies first in the frozen plan
    before, after = by_year[first_survivor - 2]["spend_base_yr"], by_year[first_survivor]["spend_base_yr"]
    assert after / before == pytest.approx(c["survivor_spend_factor"], rel=1e-6)   # 0.65, not 0.65 squared
    assert by_year[first_survivor]["survivor_spend_factor_yr"] == pytest.approx(c["survivor_spend_factor"])
    assert by_year[c["h_death_yr"]]["survivor_spend_factor_yr"] == 1.0     # the death year is still a two-person year


def test_x_estate_counts_the_bypass_trust_federally_and_the_business_once():
    from src.after_tax import business_taxable_estate_value, estimate_terminal_estate_tax

    c = _project()[0]
    c = copy.deepcopy(c)
    c.update({"model_state_est": False, "federal_portability_enabled": True, "fed_exempt": 10_000_000.0})
    terminal = {"year": c["plan_end"], "total_nw": 30_000_000.0, "cst_excluded_from_survivor_estate": 2_000_000.0}
    base = estimate_terminal_estate_tax(c, terminal)
    exempt = __import__("src.after_tax", fromlist=["indexed_federal_estate_exemption"]).indexed_federal_estate_exemption(
        10_000_000.0, c["plan_start"], c["plan_end"], c.get("brk_inf", 0.02))
    assert base == pytest.approx(0.40 * (30_000_000.0 - exempt))      # FIN-009: the combined exemption already covers the CST
    c["federal_portability_enabled"] = False
    assert estimate_terminal_estate_tax(c, terminal) == pytest.approx(0.40 * (30_000_000.0 - exempt))
    c["federal_portability_enabled"] = True
    assert business_taxable_estate_value(c) == 0.0                                   # module off: nothing added
    c["opt"] = dict(c.get("opt") or {}, business_succession=True)
    c["business_succession"] = [{"valuation_today": 1_000_000.0, "valuation_growth_rate": 0.0, "ownership_pct": 1.0,
                                 "transfer_year": 0}]
    assert estimate_terminal_estate_tax(c, terminal) - base == pytest.approx(0.40 * 1_000_000.0)
