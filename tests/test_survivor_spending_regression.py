"""Survivor spending factor (Task S1).

Before this change, household spending did not respond to mortality at all:
``spend_base_yr`` was identical whether both members were alive or one had
died. Wellness already scales per-person (it roughly halves at the first
death), so the survivor factor must apply to core spending and recurring
extras ONLY -- applying it to wellness/LTC on top of their existing
per-person scaling would compound two reductions (0.53 x 0.65 ~ 0.34 of the
joint figure), which is wrong. Housing is excluded by explicit user decision:
a survivor lives in the same house.

The frozen fixture (tests/fixtures/sample_plan_frozen) has h_death_yr=2054 and
w_death_yr=2056, so 2052-2054 are both-alive years and 2055-2056 are
survivor years. plan_end == max(death years) == 2056, so there are no
both-dead rows here -- those belong to Task S2.

All pins below are the pre-S1 values, measured on this fixture at
commit a0ceab2 with RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1.
"""
from __future__ import annotations

import os
import unittest

import pytest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config

BOTH_ALIVE_YEARS = (2052, 2053, 2054)
SURVIVOR_YEARS = (2055, 2056)

SURVIVOR_SPEND_FACTOR_DEFAULT = 0.65

# Pre-S1 values for the two components the factor must NOT touch. These are
# the double-count guard: if the factor ever leaks into wellness or housing,
# these move and this test fails.
PRE_S1_WELLNESS_BASE = {2054: 137267.26, 2055: 72282.38, 2056: 76130.24}
PRE_S1_HOUSING_TOTAL = {2054: 132355.05, 2055: 135138.72, 2056: 137991.98}

# Pre-S1 whole-plan pins, used only to prove that a factor of 1.0 reproduces
# today's numbers bit-identically. These deliberately duplicate the frozen
# golden master's pins; they are NOT re-pinned by this task.
PRE_S1_TERMINAL_NW = 5824239.30
PRE_S1_LIFETIME_TAX = 1290848.91


def _rows(survivor_spend_factor=None):
    """Project the frozen fixture, optionally overriding the survivor factor."""
    from src.planning_engines import project
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

    # parse_client() prices holdings, so config construction must happen inside
    # the frozen-prices block -- same reasoning as the golden-master file.
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = _frozen_config()
        if survivor_spend_factor is not None:
            c["survivor_spend_factor"] = survivor_spend_factor
        rows = project(c)
    return {int(r["year"]): r for r in rows}, rows


@pytest.mark.golden_master
class SurvivorSpendingFactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.by_year_default, cls.rows_default = _rows(None)
        cls.by_year_unity, cls.rows_unity = _rows(1.0)

    def test_config_carries_the_survivor_spend_factor_default(self):
        from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

        with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
            c = _frozen_config()
        self.assertIn(
            "survivor_spend_factor", c,
            msg="data_io must parse survivor_spend_factor onto the engine config",
        )
        self.assertAlmostEqual(c["survivor_spend_factor"], SURVIVOR_SPEND_FACTOR_DEFAULT, places=6)

    def test_survivor_year_core_spending_is_scaled_by_the_factor(self):
        for year in SURVIVOR_YEARS:
            unscaled = self.by_year_unity[year]["spend_base_yr"]
            scaled = self.by_year_default[year]["spend_base_yr"]
            self.assertAlmostEqual(
                scaled, SURVIVOR_SPEND_FACTOR_DEFAULT * unscaled, places=2,
                msg=(
                    f"{year} is a survivor year (h_alive={self.by_year_default[year]['h_alive']}, "
                    f"w_alive={self.by_year_default[year]['w_alive']}); spend_base_yr should be "
                    f"{SURVIVOR_SPEND_FACTOR_DEFAULT} x {unscaled:,.2f} but is {scaled:,.2f}."
                ),
            )

    def test_survivor_year_recurring_extras_are_scaled_by_the_factor(self):
        for year in SURVIVOR_YEARS:
            unscaled = self.by_year_unity[year]["rec_extra"]
            self.assertGreater(unscaled, 0, msg="fixture must actually have recurring extras here")
            scaled = self.by_year_default[year]["rec_extra"]
            self.assertAlmostEqual(
                scaled, SURVIVOR_SPEND_FACTOR_DEFAULT * unscaled, places=2,
                msg=f"{year} rec_extra should be scaled for a survivor household",
            )

    def test_both_alive_years_are_completely_unmoved(self):
        # Every year up to and including the first death is untouched: two
        # people alive means no factor, and the factor must not reach back
        # into earlier years through any accumulated state either.
        for year in BOTH_ALIVE_YEARS:
            for key in ("spend_base_yr", "rec_extra", "total_spend",
                        "wellness_base_yr", "housing_total_yr", "total_nw"):
                self.assertAlmostEqual(
                    self.by_year_default[year][key], self.by_year_unity[year][key], places=2,
                    msg=f"{year} {key} moved, but both members are alive that year",
                )

    def test_wellness_and_housing_are_untouched_in_survivor_years(self):
        """The double-count guard.

        Wellness already scales per-person and housing is excluded by
        decision. Both must read exactly their pre-S1 values in the survivor
        years -- a naive implementation that scales all of total_spend_need
        fails here.
        """
        for year in SURVIVOR_YEARS:
            self.assertAlmostEqual(
                self.by_year_default[year]["wellness_base_yr"], PRE_S1_WELLNESS_BASE[year],
                places=2,
                msg=(
                    f"{year} wellness_base_yr changed. Wellness is already per-person; "
                    f"the survivor factor must not compound on top of it."
                ),
            )
            self.assertAlmostEqual(
                self.by_year_default[year]["housing_total_yr"], PRE_S1_HOUSING_TOTAL[year],
                places=2,
                msg=f"{year} housing_total_yr changed. A survivor lives in the same house.",
            )
        # And the last both-alive year, as a control.
        self.assertAlmostEqual(
            self.by_year_default[2054]["wellness_base_yr"], PRE_S1_WELLNESS_BASE[2054], places=2)
        self.assertAlmostEqual(
            self.by_year_default[2054]["housing_total_yr"], PRE_S1_HOUSING_TOTAL[2054], places=2)

    def test_total_spend_moves_by_exactly_the_core_and_extras_reduction(self):
        # Proves the factor lands in total_spend once and only once, and that
        # both total_spend_need assembly sites agree.
        for year in SURVIVOR_YEARS:
            base = self.by_year_unity[year]
            cut = (1 - SURVIVOR_SPEND_FACTOR_DEFAULT) * (base["spend_base_yr"] + base["rec_extra"])
            self.assertAlmostEqual(
                self.by_year_default[year]["total_spend"], base["total_spend"] - cut, places=2,
                msg=f"{year} total_spend did not move by exactly the core+extras reduction",
            )

    def test_factor_of_one_reproduces_todays_numbers_bit_identically(self):
        terminal_nw = self.rows_unity[-1]["total_nw"]
        lifetime_tax = sum(r["total_tax"] for r in self.rows_unity)
        self.assertAlmostEqual(
            terminal_nw, PRE_S1_TERMINAL_NW, places=2,
            msg=("survivor_spend_factor=1.0 must be a no-op against the pre-S1 engine; "
                 f"terminal NW is {terminal_nw:,.2f}, expected {PRE_S1_TERMINAL_NW:,.2f}"),
        )
        self.assertAlmostEqual(lifetime_tax, PRE_S1_LIFETIME_TAX, places=2)

    def test_a_genuinely_single_member_household_is_never_scaled(self):
        """A one-person plan is not a survivor plan.

        data_io forces ``w_death_yr = w_dob_yr`` ("already dead") for a
        single-member household, so ``w_alive`` is False in every year and a
        naive ``n_alive == 1`` test would scale the entire plan -- even though
        spend_base already IS one person's spending. The factor must key off
        household_size, not the alive count alone.
        """
        from tests.synthetic_plans import SCENARIOS

        scenario = SCENARIOS["single_filer"]
        configs = []
        for factor in (1.0, SURVIVOR_SPEND_FACTOR_DEFAULT):
            c = scenario.build()
            self.assertEqual(c["household_size"], 1)
            c["survivor_spend_factor"] = factor
            configs.append(c)

        from src.planning_engines import project
        unity_rows, scaled_rows = (project(x) for x in configs)
        self.assertEqual(len(unity_rows), len(scaled_rows))
        for u, s in zip(unity_rows, scaled_rows):
            self.assertAlmostEqual(
                s["spend_base_yr"], u["spend_base_yr"], places=2,
                msg=(f"{u['year']}: a single-member household must never receive "
                     f"the survivor factor"),
            )
            self.assertAlmostEqual(s["rec_extra"], u["rec_extra"], places=2)
        self.assertAlmostEqual(scaled_rows[-1]["total_nw"], unity_rows[-1]["total_nw"], places=2)

    def test_the_change_moves_terminal_net_worth_upward(self):
        # Direction check, recorded deliberately: spending less leaves more.
        self.assertGreater(self.rows_default[-1]["total_nw"], self.rows_unity[-1]["total_nw"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
