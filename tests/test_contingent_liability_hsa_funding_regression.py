"""Optimization refactor: contingent-liability spending draws the HSA first.

Design: docs/superpowers/plans/2026-08-26-contingent-liability-funding-rules-design.md

The `contingent_liability` spending tier (`ltc_prem_yr + wellness_shock_yr`)
previously had NO dedicated funding treatment -- both components were summed
into `total_spend_need` and funded by whatever the withdrawal cascade reached
first. In particular the scheduled HSA draw did not cover them: the
deterministic engine calls `withdraw_hsa_window` with
`wellness_cost=row['wellness_base_yr']`, which is
`wellness_premium_yr + wellness_detail_budget_yr` and excludes both.

`fund_contingent_liability_from_hsa` now funds that tier from the HSA ahead
of the ordinary cascade, since both components are qualified medical expense
and HSA dollars come out tax-free for exactly that.

The load-bearing guard here is `ScheduledModesAreUnaffectedTests`: the draw
defers to `hsa_withdrawal_mode` rather than overriding it, because an
unscheduled draw stacked on a scheduled one is the shape of a real
user-reported defect (2026-08-20, see `withdraw_hsa_gap`'s docstring) where
gap-fills drained an account years before the household expected. A future
refactor that "simplifies" the gate away would re-introduce it, and these
tests are what should turn red when that happens.
"""
from __future__ import annotations

import unittest

from src.planning_engines import (
    fund_contingent_liability_from_hsa,
    hsa_unscheduled_draw_allowed,
    liquidity_reserve_floor,
)


def _cfg(**over):
    c = {
        "hsa_ids": ["Member_1_HSA"],
        "hsa_withdrawal_mode": "spend_as_needed",
    }
    c.update(over)
    return c


class GateTests(unittest.TestCase):
    """`hsa_unscheduled_draw_allowed` is the shared predicate; these pin its
    rule directly so a change is visible here and not only through a
    downstream dollar figure."""

    def test_spend_as_needed_always_allows(self):
        self.assertTrue(hsa_unscheduled_draw_allowed(_cfg(), 2030))

    def test_optimize_never_allows(self):
        self.assertFalse(
            hsa_unscheduled_draw_allowed(_cfg(hsa_withdrawal_mode="optimize"), 2030))

    def test_window_modes_blocked_before_and_during_window_allowed_after(self):
        for mode in ("smooth_window", "annual_pct"):
            c = _cfg(hsa_withdrawal_mode=mode, hsa_win_start=2031, hsa_win_end=2040)
            self.assertFalse(hsa_unscheduled_draw_allowed(c, 2030), f"{mode}: before window")
            self.assertFalse(hsa_unscheduled_draw_allowed(c, 2035), f"{mode}: during window")
            self.assertFalse(hsa_unscheduled_draw_allowed(c, 2040), f"{mode}: window end year")
            self.assertTrue(hsa_unscheduled_draw_allowed(c, 2041), f"{mode}: after window")

    def test_year_zero_default_skips_the_window_comparison(self):
        # Callers that don't thread a year pass year=0. A naive window check
        # against year 0 would suppress every such call; the original inline
        # form guarded on `year > 0` and that must be preserved.
        c = _cfg(hsa_withdrawal_mode="smooth_window", hsa_win_start=2031, hsa_win_end=2040)
        self.assertTrue(hsa_unscheduled_draw_allowed(c, 0))


class FundingTests(unittest.TestCase):
    def test_hsa_fully_covers_the_contingent_liability(self):
        bal = {"Member_1_HSA": 50_000.0}
        res = fund_contingent_liability_from_hsa(
            _cfg(), bal, ltc_prem_yr=6_000.0, wellness_shock_yr=0.0, year=2030)
        self.assertAlmostEqual(res["amount"], 6_000.0, places=6)
        self.assertAlmostEqual(res["residual"], 0.0, places=6)
        self.assertAlmostEqual(bal["Member_1_HSA"], 44_000.0, places=6)

    def test_both_components_are_funded_together(self):
        bal = {"Member_1_HSA": 200_000.0}
        res = fund_contingent_liability_from_hsa(
            _cfg(), bal, ltc_prem_yr=6_000.0, wellness_shock_yr=150_000.0, year=2030)
        self.assertAlmostEqual(res["amount"], 156_000.0, places=6)
        self.assertAlmostEqual(bal["Member_1_HSA"], 44_000.0, places=6)

    def test_insufficient_balance_drains_hsa_and_reports_the_residual(self):
        bal = {"Member_1_HSA": 10_000.0}
        res = fund_contingent_liability_from_hsa(
            _cfg(), bal, wellness_shock_yr=150_000.0, year=2030)
        self.assertAlmostEqual(res["amount"], 10_000.0, places=6)
        self.assertAlmostEqual(res["residual"], 140_000.0, places=6)
        self.assertAlmostEqual(bal["Member_1_HSA"], 0.0, places=6)

    def test_no_hsa_accounts_is_a_no_op_reporting_the_whole_need(self):
        bal = {"Member_1_Trust": 500_000.0}
        res = fund_contingent_liability_from_hsa(
            _cfg(hsa_ids=[]), bal, ltc_prem_yr=6_000.0, year=2030)
        self.assertAlmostEqual(res["amount"], 0.0, places=6)
        self.assertAlmostEqual(res["residual"], 6_000.0, places=6)
        self.assertAlmostEqual(bal["Member_1_Trust"], 500_000.0, places=6,
                                msg="a no-op draw must not touch any other account")

    def test_zero_contingent_liability_is_a_no_op(self):
        bal = {"Member_1_HSA": 50_000.0}
        res = fund_contingent_liability_from_hsa(_cfg(), bal, year=2030)
        self.assertAlmostEqual(res["amount"], 0.0, places=6)
        self.assertAlmostEqual(res["residual"], 0.0, places=6)
        self.assertAlmostEqual(bal["Member_1_HSA"], 50_000.0, places=6)

    def test_draw_is_split_pro_rata_across_multiple_hsa_accounts(self):
        bal = {"H_HSA": 75_000.0, "W_HSA": 25_000.0}
        res = fund_contingent_liability_from_hsa(
            _cfg(hsa_ids=["H_HSA", "W_HSA"]), bal, wellness_shock_yr=20_000.0, year=2030)
        self.assertAlmostEqual(res["amount"], 20_000.0, places=6)
        self.assertAlmostEqual(res["by_account"]["H_HSA"], 15_000.0, places=6)
        self.assertAlmostEqual(res["by_account"]["W_HSA"], 5_000.0, places=6)


class ScheduledModesAreUnaffectedTests(unittest.TestCase):
    """The mode-deference decision, pinned. See this module's docstring for
    why these are the guards that matter most in this file."""

    def test_optimize_mode_draws_nothing(self):
        bal = {"Member_1_HSA": 50_000.0}
        res = fund_contingent_liability_from_hsa(
            _cfg(hsa_withdrawal_mode="optimize"), bal,
            ltc_prem_yr=6_000.0, wellness_shock_yr=150_000.0, year=2030)
        self.assertAlmostEqual(res["amount"], 0.0, places=6)
        self.assertAlmostEqual(res["residual"], 156_000.0, places=6)
        self.assertAlmostEqual(bal["Member_1_HSA"], 50_000.0, places=6,
                                msg="optimize mode's schedule must remain the sole authority "
                                    "on the year's HSA draw")

    def test_inside_a_configured_window_draws_nothing(self):
        for mode in ("smooth_window", "annual_pct"):
            bal = {"Member_1_HSA": 50_000.0}
            res = fund_contingent_liability_from_hsa(
                _cfg(hsa_withdrawal_mode=mode, hsa_win_start=2031, hsa_win_end=2040),
                bal, wellness_shock_yr=150_000.0, year=2035)
            self.assertAlmostEqual(res["amount"], 0.0, places=6, msg=mode)
            self.assertAlmostEqual(bal["Member_1_HSA"], 50_000.0, places=6, msg=mode)

    def test_after_the_window_ends_the_draw_resumes(self):
        bal = {"Member_1_HSA": 50_000.0}
        res = fund_contingent_liability_from_hsa(
            _cfg(hsa_withdrawal_mode="smooth_window", hsa_win_start=2031, hsa_win_end=2040),
            bal, wellness_shock_yr=20_000.0, year=2041)
        self.assertAlmostEqual(res["amount"], 20_000.0, places=6)
        self.assertAlmostEqual(bal["Member_1_HSA"], 30_000.0, places=6)


class ReserveFloorTests(unittest.TestCase):
    """A liquidity reserve configured against the HSA bucket (P8) holds
    dollars back from this draw, exactly as it does for withdraw_hsa_gap."""

    def test_hsa_reserve_floor_caps_the_draw(self):
        c = _cfg(
            liquidity_buffer_schedule=[{
                "start_year": 2020, "end_year": 2060,
                "years_of_expenses": 2.0, "reserve_account": "HSA",
            }],
        )
        # Assert the fixture actually resolves a floor, rather than skipping:
        # a reserve guard that quietly skips is not a guard at all.
        floor = liquidity_reserve_floor(c, 2030, "hsa", 10_000.0)
        self.assertAlmostEqual(floor, 20_000.0, places=6,
                                msg="fixture did not resolve the intended HSA reserve floor")
        bal = {"Member_1_HSA": 50_000.0}
        res = fund_contingent_liability_from_hsa(
            c, bal, wellness_shock_yr=50_000.0, year=2030, spend_floor_base=10_000.0)
        self.assertAlmostEqual(res["amount"], 30_000.0, places=6)
        self.assertAlmostEqual(res["residual"], 20_000.0, places=6)
        self.assertAlmostEqual(bal["Member_1_HSA"], 20_000.0, places=6,
                                msg="the configured HSA reserve must survive the draw")

    def test_reserve_against_a_different_bucket_does_not_restrict_the_hsa_draw(self):
        c = _cfg(
            liquidity_buffer_schedule=[{
                "start_year": 2020, "end_year": 2060,
                "years_of_expenses": 2.0, "reserve_account": "Taxable/Trust",
            }],
        )
        bal = {"Member_1_HSA": 50_000.0}
        res = fund_contingent_liability_from_hsa(
            c, bal, wellness_shock_yr=50_000.0, year=2030, spend_floor_base=10_000.0)
        self.assertAlmostEqual(res["amount"], 50_000.0, places=6)
        self.assertAlmostEqual(bal["Member_1_HSA"], 0.0, places=6)


if __name__ == "__main__":
    unittest.main()
