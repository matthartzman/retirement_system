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

    def test_factor_of_one_applies_no_survivor_scaling(self):
        """A factor of 1.0 must leave survivor-year spending unscaled.

        This deliberately asserts on the COMPONENTS the factor touches rather
        than on terminal net worth. An earlier version pinned whole-plan
        terminal NW against a pre-S1 figure, which made it fail the moment
        Task S3 (the estate home sale) legitimately moved the plan -- a local
        property proved by a global pin breaks on every unrelated change.
        Whole-plan dollars are the golden master's job, not this file's.
        """
        for year in SURVIVOR_YEARS:
            unity = self.by_year_unity[year]
            default = self.by_year_default[year]
            self.assertAlmostEqual(
                default["spend_base_yr"],
                unity["spend_base_yr"] * SURVIVOR_SPEND_FACTOR_DEFAULT, places=6,
                msg=f"{year}: default run must be exactly the factor times the unscaled run",
            )
            self.assertAlmostEqual(
                default["rec_extra"],
                unity["rec_extra"] * SURVIVOR_SPEND_FACTOR_DEFAULT, places=6,
            )

        for year in BOTH_ALIVE_YEARS:
            self.assertAlmostEqual(
                self.by_year_unity[year]["spend_base_yr"],
                self.by_year_default[year]["spend_base_yr"], places=6,
                msg=f"{year} has both members alive; the factor must not apply",
            )

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


# ── Tasks S2 + S3 ───────────────────────────────────────────────────────────
# Past the second death nobody is alive, so there are no living expenses of any
# kind, and the home is disposed of rather than carried forever.
#
# These need an EXTENDED horizon to observe at all: a default plan has
# plan_end == max(death years) == the second death year, so it contains no
# both-dead rows. That is why this half of the defect was latent.

SECOND_DEATH_YEAR = 2056

LIVING_EXPENSE_KEYS = (
    "spend_base_yr", "rec_extra", "housing_total_yr", "housing_operating_yr",
    "housing_utilities_yr", "housing_maintenance_yr", "housing_other_yr",
    "real_estate_tax_yr", "mortgage_payment_yr", "rent_yr",
    "wellness_base_yr", "wellness_shock_yr", "ltc_prem_yr",
    "business_expenses_yr", "total_spend",
)


def _rows_extended(plan_end=2070):
    """Project past the second death so both-dead rows exist."""
    from src.planning_engines import project
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = _frozen_config()
        c["plan_end"] = plan_end
        rows = project(c)
    return {int(r["year"]): r for r in rows}, rows


@pytest.mark.golden_master
class EstateOnlyAfterSecondDeathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.by_year, cls.rows = _rows_extended()

    def test_every_living_expense_is_zero_after_the_second_death(self):
        """The defect: the plan charged a dead household core spending and
        housing forever, and the figures kept inflating."""
        for year in range(SECOND_DEATH_YEAR + 1, 2071):
            row = self.by_year[year]
            for key in LIVING_EXPENSE_KEYS:
                self.assertAlmostEqual(
                    float(row.get(key) or 0.0), 0.0, places=6,
                    msg=f"{key} is non-zero in {year}, when nobody is alive",
                )

    def test_no_unfunded_gap_can_arise_after_the_second_death(self):
        """A household that no longer exists cannot fail to fund itself.
        Pre-fix this reported a 232,874 gap by 2065."""
        for year in range(SECOND_DEATH_YEAR + 1, 2071):
            self.assertAlmostEqual(
                float(self.by_year[year].get("unfunded_gap") or 0.0), 0.0, places=6,
                msg=f"unfunded_gap is non-zero in {year}, when nobody is alive",
            )

    def test_both_alive_and_survivor_years_are_untouched_by_estate_mode(self):
        """Estate mode must not reach back into years someone is alive."""
        for year in (2053, 2054, 2055, 2056):
            self.assertGreater(
                float(self.by_year[year].get("total_spend") or 0.0), 0.0,
                msg=f"{year} has someone alive and must still spend",
            )


@pytest.mark.golden_master
class HomeSoldAtSecondDeathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.by_year, cls.rows = _rows_extended()

    def test_the_home_is_sold_in_the_second_death_year(self):
        row = self.by_year[SECOND_DEATH_YEAR]
        self.assertGreater(float(row.get("home_sale_gross") or 0.0), 0.0,
                           "the home must be disposed of at the second death")
        self.assertGreater(float(row.get("home_sale_net") or 0.0), 0.0,
                           "net proceeds must reach the estate")

    def test_the_estate_sale_uses_market_value_not_a_downsizing_price(self):
        """An estate sale is a forced disposition, not a planned downsizing.

        home_sale_px is the user's assumed price for a SPECIFIC planned
        downsizing transaction. If the estate sale reused it, a stale
        assumption (1,750,000 on this fixture) would silently replace the
        home's real appreciated market value at second death, destroying real
        estate value. Caught during implementation: measured 1.53M lost on
        the frozen fixture before this was fixed.
        """
        row = self.by_year[SECOND_DEATH_YEAR]
        appreciated_market_value = self.by_year[SECOND_DEATH_YEAR - 1]["home_val"] * (1 + 0.03)
        self.assertGreater(
            float(row.get("home_sale_gross") or 0.0), appreciated_market_value * 0.9,
            "estate sale gross proceeds look like a stale home_sale_px, not market value",
        )

    def test_the_home_is_not_carried_after_the_second_death(self):
        """Pre-fix home_val kept appreciating to 3.9M while the plan paid
        ~85k/yr to carry a house nobody lived in."""
        for year in range(SECOND_DEATH_YEAR + 1, 2071):
            self.assertAlmostEqual(
                float(self.by_year[year].get("home_val") or 0.0), 0.0, places=6,
                msg=f"home_val is non-zero in {year}, after the home was sold",
            )

    def test_death_triggered_sale_is_stepped_up_so_no_gain_is_taxed(self):
        """Assets receive a basis step-up at death, so a sale in the year of
        death realizes no taxable gain."""
        row = self.by_year[SECOND_DEATH_YEAR]
        self.assertAlmostEqual(float(row.get("home_sale_taxable") or 0.0), 0.0, places=6)
        self.assertAlmostEqual(float(row.get("home_sale_tax") or 0.0), 0.0, places=6)
