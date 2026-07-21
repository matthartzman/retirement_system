"""Wave 4 item 4.2 (system review P4): DAF contribution into the itemized
deduction stack, AGI-limited (60% cash / 30% appreciated) with a 5-year
carryforward — replacing daf_contrib_yr as an unlimited, untracked deduction.

Uses tests/synthetic_plans.py's base_plan() with a DAF contribution placed in
2026 (both members still earning, per base_plan's 2027/2028 retirement dates)
rather than synthetic_plans._enable_daf's default 2028 contribution year: this
engine computes the itemized-deduction stack (including the new DAF limit)
from a "first pass" AGI taken before the elective-withdrawal sizing loop
converges, which reads near zero for a retiree with no earned/SS/RMD income
yet -- exactly _enable_daf's 2028. A known limitation (see the code comment
above the daf_deduction_carryforward block in deterministic_engine.py and the
follow-up task it spawned), not something to route around silently in a test;
choosing a still-earning contribution year is the representative use case the
review itself describes (bunching gifts into a high-earned-income year).
"""
from __future__ import annotations

import unittest

from src.data_io import build_plan_from_json
from src.plan_config import ensure_engine_config
from src.planning_engines import project

from tests.synthetic_plans import _no_voluntary_roth, base_plan


def _config():
    c = build_plan_from_json(base_plan(), "")
    c = ensure_engine_config(c, source="test")
    _no_voluntary_roth(c)
    return c


def _with_daf(amount, appreciated=False, use_start=2027, use_end=2036, use_amount=25_000.0, year=2026):
    c = _config()
    c["daf_enabled"] = True
    c["daf_year"] = year
    c["daf_amount"] = amount
    c["daf_use_start"] = use_start
    c["daf_use_end"] = use_end
    c["daf_use_amount"] = use_amount
    c["daf_contribution_is_appreciated"] = appreciated
    return c


def _by_year(rows):
    return {int(r["year"]): r for r in rows}


class DafAgiLimitationTests(unittest.TestCase):
    def test_baseline_plan_has_no_daf_activity(self):
        rows = project(_config())
        self.assertFalse(any((r.get("daf_deduction_yr") or 0) > 0 for r in rows))

    def test_daf_contribution_over_the_agi_limit_is_capped_at_60_percent_of_agi(self):
        baseline = _by_year(project(_config()))
        with_daf = _by_year(project(_with_daf(250_000.0)))
        contribution_year = 2026
        agi_2026 = baseline[contribution_year]["agi"]  # unaffected by the deduction itself
        r = with_daf[contribution_year]
        self.assertAlmostEqual(r["daf_deduction_yr"], agi_2026 * 0.60, places=2)
        self.assertAlmostEqual(r["daf_deduction_carryforward"], 250_000.0 - agi_2026 * 0.60, places=2)

    def test_appreciated_contribution_is_limited_to_30_percent_instead(self):
        baseline = _by_year(project(_config()))
        with_daf = _by_year(project(_with_daf(250_000.0, appreciated=True)))
        agi_2026 = baseline[2026]["agi"]
        r = with_daf[2026]
        self.assertAlmostEqual(r["daf_deduction_yr"], agi_2026 * 0.30, places=2)

    def test_carryforward_is_consumed_in_a_later_year_and_reduces_thereafter(self):
        rows = _by_year(project(_with_daf(250_000.0)))
        self.assertGreater(rows[2026]["daf_deduction_carryforward"], 0)
        self.assertGreater(rows[2027]["daf_deduction_yr"], 0)
        self.assertLess(rows[2027]["daf_deduction_carryforward"], rows[2026]["daf_deduction_carryforward"])

    def test_a_contribution_within_the_agi_limit_needs_no_carryforward(self):
        rows = _by_year(project(_with_daf(20_000.0)))
        self.assertAlmostEqual(rows[2026]["daf_deduction_yr"], 20_000.0, places=2)
        self.assertEqual(rows[2026]["daf_deduction_carryforward"], 0)

    def test_grant_years_do_not_add_a_second_deduction(self):
        # daf_grant_yr fires 2027-2036; confirm the deduction total for those
        # years is explained entirely by carryforward consumption (already
        # checked above) plus char, never bumped further by the grant itself.
        rows = _by_year(project(_with_daf(20_000.0, use_start=2027, use_end=2030, use_amount=5_000.0)))
        # Contribution fully deducted in 2026 (within the limit) -> zero
        # carryforward, so every later year's daf_deduction_yr must be 0
        # even though grants are actively flowing 2027-2030.
        for year in range(2027, 2031):
            self.assertEqual(rows[year]["daf_deduction_yr"], 0, f"year {year} should have no carryforward left to deduct")
            self.assertGreater(rows[year]["daf_grant_yr"], 0, f"year {year} should show an active grant")

    def test_unused_carryforward_expires_after_five_succeeding_years(self):
        # A contribution so large relative to AGI that meaningful carryforward
        # would remain past year 5 if it didn't expire; use plan years deep
        # enough that plan_end covers origin+6.
        c = _with_daf(3_000_000.0, year=2026)
        rows = _by_year(project(c))
        origin_plus_5 = 2031
        origin_plus_6 = 2032
        self.assertGreater(rows[origin_plus_5]["daf_deduction_carryforward"], 0, "expected leftover carryforward still within its 5-year window")
        self.assertEqual(rows[origin_plus_6]["daf_deduction_carryforward"], 0, "carryforward older than 5 succeeding years must expire, not persist indefinitely")


if __name__ == "__main__":
    unittest.main()
