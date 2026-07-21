"""Wave 4 item 4.2 (system review P4): DAF contribution into the itemized
deduction stack, AGI-limited (60% cash / 30% appreciated) with a 5-year
carryforward — replacing daf_contrib_yr as an unlimited, untracked deduction.

Uses tests/synthetic_plans.py's base_plan() with a DAF contribution placed in
2026 (both members still earning, per base_plan's 2027/2028 retirement dates)
rather than synthetic_plans._enable_daf's default 2028 contribution year: this
engine computes the itemized-deduction stack (including the new DAF limit)
from a "first pass" AGI taken before the elective-withdrawal sizing loop
converges, which reads near zero for a retiree with no earned/SS/RMD income
yet -- exactly _enable_daf's 2028.

That first-pass-AGI gap is covered separately by
GapYearDafCarryforwardMakeUpTests below: deterministic_engine.py now runs a
narrow make-up pass (see "Item 4.2 follow-up" in the code, right after
Priority 4b in run_deterministic_projection_stage) that re-evaluates unused
DAF carryforward against the *converged* AGI once the elective-withdrawal
cascade settles, so a no-guaranteed-income gap year no longer strands
carryforward capacity that the household actually had room to use. salt and
mortgage interest are deliberately left at their first-pass values (a
one-year approximation with no lasting consequence); only DAF's multi-year
carryforward gets this treatment, since it's the one deduction where the
first-pass understatement can cost a permanent, unrecoverable deduction.
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
        with_daf = _by_year(project(_with_daf(250_000.0)))
        r = with_daf[2026]
        # Funding a $250k lump-sum DAF gift on top of regular spending itself
        # requires an elective IRA withdrawal that year (earned income alone
        # doesn't cover both), which raises this row's own converged AGI well
        # above a no-DAF baseline's -- that raised AGI is what the 60% cap
        # applies against (Item 4.2 follow-up's make-up pass; see the module
        # docstring), so the cap is checked against this run's own final agi
        # rather than a separate baseline run's.
        self.assertGreater(r["agi"], 180_000.0, "the DAF lump sum itself should have required an elective withdrawal")
        self.assertAlmostEqual(r["daf_deduction_yr"], r["agi"] * 0.60, places=2)
        self.assertAlmostEqual(r["daf_deduction_carryforward"], 250_000.0 - r["agi"] * 0.60, places=2)

    def test_appreciated_contribution_is_limited_to_30_percent_instead(self):
        with_daf = _by_year(project(_with_daf(250_000.0, appreciated=True)))
        r = with_daf[2026]
        self.assertAlmostEqual(r["daf_deduction_yr"], r["agi"] * 0.30, places=2)

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


class GapYearDafCarryforwardMakeUpTests(unittest.TestCase):
    """Item 4.2 follow-up: DAF carryforward during a no-guaranteed-income gap.

    base_plan()'s earned income ends in 2027 (earn_end = h_ret_yr, the earlier
    of the two retirement years); Social Security doesn't start until 2034
    (both members claim at 70, per base_plan's income.ss_claim_age); RMDs
    don't start until 2039/2041 (rmd_start_age 75, per each member's dob).
    2028-2033 is therefore a genuine zero-guaranteed-income gap, funded
    entirely by elective IRA withdrawals -- exactly the scenario where
    first-pass AGI (computed before those withdrawals are sized) reads near
    zero while the converged, final AGI is substantial.

    A DAF contribution made in 2028 carries forward for up to 5 succeeding
    tax years, i.e. it is usable through 2033 -- entirely inside this gap.
    Confirmed by temporarily reverting the Item 4.2 follow-up make-up pass
    and rerunning this exact scenario: without it, daf_deduction_yr is 0 in
    every gap year (first-pass AGI is ~0, so the 60%-of-AGI cap is ~0), the
    full $300,000 sits as carryforward through 2033, and then silently
    expires to $0 in 2034 -- an entirely unused deduction, despite the
    household funding six figures of AGI a year during the gap. This test
    guards against that regression.
    """

    def _gap_year_daf(self, amount, year=2028, use_start=2030, use_end=2038, use_amount=15_000.0):
        c = _config()
        c["daf_enabled"] = True
        c["daf_year"] = year
        c["daf_amount"] = amount
        c["daf_use_start"] = use_start
        c["daf_use_end"] = use_end
        c["daf_use_amount"] = use_amount
        return c

    def test_gap_years_have_no_earned_or_ss_income(self):
        # Confirms the scenario is the gap it's meant to be, independent of
        # any DAF activity, before trusting the assertions below.
        rows = _by_year(project(_config()))
        for year in range(2028, 2034):
            r = rows[year]
            self.assertEqual(r.get("state_earned_net", 0), 0, f"year {year} should have no earned income")
            self.assertEqual(r.get("ss_taxable", 0), 0, f"year {year} should have no SS income yet")
            self.assertGreater(r["agi"], 100_000, f"year {year} should be funded by a substantial elective withdrawal")

    def test_carryforward_from_a_gap_year_contribution_does_not_expire_unused(self):
        rows = _by_year(project(self._gap_year_daf(300_000.0)))
        # Fully consumed well inside the 5-year window (origin 2028 -> usable
        # through 2033), not merely swept to zero by expiration in 2034.
        self.assertEqual(rows[2030]["daf_deduction_carryforward"], 0)
        self.assertEqual(rows[2033]["daf_deduction_carryforward"], 0)
        self.assertEqual(rows[2034]["daf_deduction_carryforward"], 0)
        total_deducted = sum(rows[y]["daf_deduction_yr"] for y in range(2028, 2034))
        self.assertAlmostEqual(total_deducted, 300_000.0, delta=1.0)

    def test_contribution_year_itself_uses_converged_agi_not_first_pass(self):
        # The make-up pass runs within the same year as the contribution, so
        # even 2028 itself should reflect the converged (not near-zero
        # first-pass) AGI -- roughly 60% of the household's actual AGI that
        # year, not 60% of ~0.
        rows = _by_year(project(self._gap_year_daf(300_000.0)))
        r = rows[2028]
        self.assertAlmostEqual(r["daf_deduction_yr"], r["agi"] * 0.60, places=2)
        self.assertGreater(r["daf_deduction_yr"], 100_000.0)

    def test_a_contribution_small_enough_to_clear_in_one_year_still_works(self):
        # Sanity check at a smaller scale: no carryforward needed at all when
        # even the converged-AGI-based cap covers the full gift.
        rows = _by_year(project(self._gap_year_daf(50_000.0)))
        r = rows[2028]
        self.assertAlmostEqual(r["daf_deduction_yr"], 50_000.0, places=2)
        self.assertEqual(r["daf_deduction_carryforward"], 0)


if __name__ == "__main__":
    unittest.main()
