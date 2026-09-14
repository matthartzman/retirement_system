"""Design doc §8.2 P0: the engine's second-sale pathway.

A ``next_housing_steps`` purchase step (how the engine represents a home
bought via a housing move, e.g. a housing_optimizer.py move-2 candidate) can
now be sold with the same gain/§121/cascade-visible-deposit treatment
``home_sale.py`` already gives the household's original home -- see
``apply_next_housing_sale``. These tests exercise that pathway directly
against a hand-built plan config (not through housing_optimizer.py, which
has its own engine-backed coverage in test_housing_optimizer_integration.py)
so the gain/§121/tax math and the cascade-visible deposit can be checked
against hand-computed expected values.
"""
from __future__ import annotations

import unittest

from src.data_io import build_plan_from_json
from src.plan_config import ensure_engine_config
from src.planning_engines import monte_carlo, project

from tests.synthetic_plans import base_plan, _no_voluntary_roth


def _config(**overrides):
    c = build_plan_from_json(base_plan(), "")
    c = ensure_engine_config(c, source="test")
    _no_voluntary_roth(c)
    # No original-home sale in any of these -- isolates the next_housing_steps
    # pathway under test from the pre-existing c['home_sale_yr'] one.
    c["home_val"] = 0.0
    c["home_sale_yr"] = 0
    c.update(overrides)
    return c


def _purchase_step(*, start_year, price, sale_year=None, down_payment_pct=1.0):
    """An all-cash purchase (down_payment_pct=1.0) by default so the sale's
    mortgage payoff is always 0 -- keeps the expected gross/net proceeds
    formula simple to hand-compute without also replicating the engine's
    amortization schedule."""
    step = {
        "id": "opt_move1", "type": "purchase",
        "start_year": start_year, "end_year": (sale_year - 1) if sale_year else 0,
        "purchase_price": price, "down_payment_pct": down_payment_pct,
        "mortgage_rate_pct": 0.05, "monthly_rent": 0.0,
        "insurance_annual": 0.0, "utilities_annual": 0.0, "maintenance_annual": 0.0,
        "real_estate_tax_pct": 0.0, "hoa_pct": 0.0,
    }
    if sale_year:
        step["sale_year"] = sale_year
    return step


def _by_year(rows):
    return {int(r["year"]): r for r in rows}


class NextHousingSaleGainAndSec121Tests(unittest.TestCase):
    def test_gain_exceeding_sec121_exclusion_is_taxed(self):
        # Large enough that the taxable gain clears the 0%-bracket LTCG
        # threshold even with $0 ordinary income in the sale year (this
        # synthetic household has no earned/pension income left by 2036) --
        # otherwise a small taxable gain can correctly owe $0 LTCG tax by
        # sitting entirely in the 0% bracket, which is a different (also
        # correct) test, not this one.
        start_year, sale_year, price = 2026, 2036, 5_000_000.0
        c = _config(next_housing_steps=[_purchase_step(start_year=start_year, price=price, sale_year=sale_year)])
        rows = project(c)
        row = _by_year(rows)[sale_year]

        appr = c["home_appr"]
        expected_gross = price * ((1.0 + appr) ** (sale_year - 1 - start_year + 1))
        expected_costs = expected_gross * c["home_sell_cost_pct"]
        expected_gain = expected_gross - expected_costs - price
        expected_sec121 = 500000.0  # MFJ
        expected_taxable = expected_gain - expected_sec121
        self.assertGreater(expected_taxable, 0, "test setup should produce a gain above the exclusion")

        self.assertAlmostEqual(row["next_housing_sale_gross"], expected_gross, delta=1.0)
        self.assertAlmostEqual(row["next_housing_sale_costs"], expected_costs, delta=1.0)
        self.assertAlmostEqual(row["next_housing_sale_mort_off"], 0.0, delta=1.0)
        self.assertAlmostEqual(row["next_housing_sale_gain"], expected_gain, delta=1.0)
        self.assertAlmostEqual(row["next_housing_sale_sec121_exclusion"], expected_sec121, delta=1.0)
        self.assertAlmostEqual(row["next_housing_sale_taxable"], expected_taxable, delta=1.0)
        self.assertAlmostEqual(row["next_housing_sale_net"], expected_gross - expected_costs, delta=1.0)
        self.assertGreater(row["next_housing_sale_tax"], 0.0)
        # No original-home sale happened this year, so home_sale_tax should
        # not absorb any of the next-housing sale's tax (the apportionment
        # in resolve_home_sale_gain_tax is a no-op with nothing to share).
        self.assertAlmostEqual(row["home_sale_tax"], 0.0, delta=0.01)

    def test_gain_under_sec121_exclusion_owes_no_tax_but_still_deposits_proceeds(self):
        start_year, sale_year, price = 2026, 2029, 300_000.0
        c = _config(next_housing_steps=[_purchase_step(start_year=start_year, price=price, sale_year=sale_year)])
        rows = project(c)
        row = _by_year(rows)[sale_year]

        self.assertGreater(row["next_housing_sale_gain"], 0.0)
        self.assertLess(row["next_housing_sale_gain"], 500000.0)
        self.assertEqual(row["next_housing_sale_taxable"], 0.0)
        self.assertEqual(row["next_housing_sale_tax"], 0.0)
        self.assertGreater(row["next_housing_sale_net"], 0.0)


class NextHousingSaleCascadeVisibilityTests(unittest.TestCase):
    def test_deposit_lands_on_the_account_flow_ledger(self):
        start_year, sale_year, price = 2026, 2032, 800_000.0
        c = _config(next_housing_steps=[_purchase_step(start_year=start_year, price=price, sale_year=sale_year)])
        rows = project(c)
        row = _by_year(rows)[sale_year]

        deposited = sum(row["_account_deposits"].values())
        # >= rather than == : other ordinary-course deposits (income, etc.)
        # land in the same ledger this same year.
        self.assertGreaterEqual(deposited, row["next_housing_sale_net"] - row["next_housing_sale_tax"] - 1.0)

    def test_net_worth_reflects_the_sale_a_step_that_merely_ends_does_not(self):
        """The whole point of §8.2 P0: selling the step (a real deposit) must
        leave the household measurably better off in the engine's own net
        worth than a step that only stops accruing cash flow at end_year
        with no sale -- the bug this closes."""
        start_year, sale_year, price = 2026, 2032, 800_000.0
        c_sold = _config(next_housing_steps=[_purchase_step(start_year=start_year, price=price, sale_year=sale_year)])
        c_unsold = _config(next_housing_steps=[_purchase_step(start_year=start_year, price=price, sale_year=None)])
        # Match the "step just ends" plan's end_year to the sold plan's
        # implicit end_year (sale_year - 1) so the only difference between
        # the two runs is whether the home was actually sold.
        c_unsold["next_housing_steps"][0]["end_year"] = sale_year - 1

        rows_sold = _by_year(project(c_sold))
        rows_unsold = _by_year(project(c_unsold))
        nw_sold = float(rows_sold[sale_year]["total_nw"])
        nw_unsold = float(rows_unsold[sale_year]["total_nw"])
        self.assertGreater(
            nw_sold, nw_unsold,
            "selling the second home should deposit real proceeds the engine's "
            "own net worth reflects, not just drop the home from the balance sheet",
        )


class NextHousingSaleMonteCarloTests(unittest.TestCase):
    def test_monte_carlo_terminal_net_worth_reflects_the_real_deposit(self):
        start_year, sale_year, price = 2026, 2032, 800_000.0
        c_sold = _config(next_housing_steps=[_purchase_step(start_year=start_year, price=price, sale_year=sale_year)])
        c_unsold = _config(next_housing_steps=[_purchase_step(start_year=start_year, price=price, sale_year=None)])
        c_unsold["next_housing_steps"][0]["end_year"] = sale_year - 1

        mc_sold = monte_carlo(c_sold, n_sims=200, seed=42)
        mc_unsold = monte_carlo(c_unsold, n_sims=200, seed=42)
        final_year = c_sold["plan_end"]
        median_sold = mc_sold["pct_by_year"][final_year][50]
        median_unsold = mc_unsold["pct_by_year"][final_year][50]
        self.assertGreater(
            median_sold, median_unsold,
            "Monte Carlo terminal net worth should reflect the second home's "
            "real sale proceeds, not just the deterministic run",
        )


if __name__ == "__main__":
    unittest.main()
