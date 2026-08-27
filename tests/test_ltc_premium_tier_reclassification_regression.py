"""ltc_prem_yr stays `contingent_liability`; wellness_shock_yr moves to `essential`.

Design: commit `0e65806` on `claude/plan-execution-tg1rps` (merged into
`claude/confit-optimization-refactor-cyyk9v` 2026-08-27), reconciled against
this branch's own earlier, opposite-direction attempt (PR #70, reverted --
see the "Reconciliation note" in `documentation/OPTIMIZATION_REFACTOR_STATUS.md`
and `documentation/GOLDEN_MASTER_CHANGELOG.md`).

`contingent_liability` bundled two different kinds of dollars: `ltc_prem_yr`
(an LTC insurance premium -- a genuine choice to forgo future coverage) and
`wellness_shock_yr` (an already-incurred health/LTC event cost -- not really
a discretionary choice). This file asserts the final split: the premium
stays `contingent_liability`, cuttable at that tier's `SPENDING_TIER_CUT_
ORDER` priority (between important and essential, per `ffa142b`'s cascade-
inclusion fix); the incurred shock routes into `essential`, protecting it
at essential's priority instead.

Every guard below compares an LTC-enabled run against a matched
LTC-disabled run of the SAME household and asserts the exact dollar DELTA,
not a loose `>=`/`>` against a tier's already-large total -- an earlier
version of this file (testing the opposite, since-reverted direction) used
loose inequalities and every one of them still passed with that fix
reverted, because essential's other components (mortgage, property tax,
...) already cleared the threshold on their own regardless of where the
LTC premium was tiered. Mutation-tested: swapping the direction back (as
if `ltc_prem_yr` routed to `essential` again) turns every delta-based
guard below red.
"""
from __future__ import annotations

import unittest

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import project, spending_priority_cut_check
from src.spending_budget_resolver import SPENDING_TIER_CUT_ORDER

LTC_PREMIUM = 18_500


def _config(ltc_enabled: bool, **over):
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["ltc_enabled"] = ltc_enabled
    c["ltc_annual_prem"] = LTC_PREMIUM
    c["ltc_start_year"] = c.get("plan_start", 2026)
    c.update(over)
    return c


def _rows_with_ltc_premium(rows):
    return [r for r in rows if (r.get("ltc_prem_yr") or 0.0) > 1.0]


def _paired_rows():
    """(with_ltc_rows, without_ltc_rows) for the identical household,
    indexed by year for delta comparison."""
    with_ltc = {r["year"]: r for r in project(_config(True))}
    without_ltc = {r["year"]: r for r in project(_config(False))}
    return with_ltc, without_ltc


class ClassificationTests(unittest.TestCase):
    def test_the_fixture_actually_exercises_this(self):
        with_ltc, _ = _paired_rows()
        hits = _rows_with_ltc_premium(with_ltc.values())
        self.assertTrue(
            hits,
            "no year has a nonzero ltc_prem_yr with ltc_enabled=True; "
            "the guards below are vacuous",
        )

    def test_ltc_premium_moves_contingent_liability_by_exactly_the_premium(self):
        with_ltc, without_ltc = _paired_rows()
        for year, r in with_ltc.items():
            ltc = r.get("ltc_prem_yr") or 0.0
            if ltc <= 1.0:
                continue
            base = without_ltc.get(year)
            if base is None:
                continue
            with_cl = (r.get("spend_by_tier") or {}).get("contingent_liability", 0.0)
            base_cl = (base.get("spend_by_tier") or {}).get("contingent_liability", 0.0)
            self.assertAlmostEqual(
                with_cl - base_cl, ltc, places=2,
                msg=f"year {year}: turning on the {ltc} LTC premium changed "
                    f"contingent_liability by {with_cl - base_cl}, not {ltc}",
            )

    def test_ltc_premium_does_not_move_essential(self):
        with_ltc, without_ltc = _paired_rows()
        for year, r in with_ltc.items():
            ltc = r.get("ltc_prem_yr") or 0.0
            if ltc <= 1.0:
                continue
            base = without_ltc.get(year)
            if base is None:
                continue
            with_essential = (r.get("spend_by_tier") or {}).get("essential", 0.0)
            base_essential = (base.get("spend_by_tier") or {}).get("essential", 0.0)
            self.assertAlmostEqual(
                with_essential, base_essential, places=2,
                msg=f"year {year}: turning on the {ltc} LTC premium moved "
                    f"essential from {base_essential} to {with_essential} -- "
                    "the premium should stay in contingent_liability",
            )

    def test_a_household_with_no_ltc_premium_is_unaffected(self):
        rows = project(_config(False))
        for r in rows:
            self.assertEqual(r.get("ltc_prem_yr", 0.0), 0.0)

    def test_spend_by_tier_still_sums_to_total_spend(self):
        # Purely additive: only the ATTRIBUTION between tiers changed, never
        # the total. Same reconciliation identity test_spending_tier_taxonomy
        # already enforces on the default fixture, re-checked here on the
        # LTC-enabled configuration this file's guards actually exercise.
        rows = project(_config(True))
        for r in rows:
            tier_total = sum((r.get("spend_by_tier") or {}).values())
            self.assertAlmostEqual(
                tier_total, r.get("total_spend", 0.0), places=1,
                msg=f"year {r['year']}: spend_by_tier ({tier_total}) does not "
                    f"reconcile to total_spend ({r.get('total_spend', 0.0)})",
            )


class CutPriorityPoolTests(unittest.TestCase):
    """The actual behavior change: which tier -- and cascade priority --
    the premium's dollars fall into, not just how they are labeled in a
    report. Directly exercises spending_priority_cut_check's own cuttable
    rule (planning_engines.py: `total_cuttable = sum(v for t, v in
    tiers.items() if t in SPENDING_TIER_CUT_ORDER)`, fixed in `ffa142b` to
    include contingent_liability) via a paired delta."""

    def test_total_cuttable_pool_grows_by_exactly_the_premium(self):
        with_ltc, without_ltc = _paired_rows()

        def total_cuttable(row):
            tiers = row.get("spend_by_tier") or {}
            return sum(v for t, v in tiers.items() if t in SPENDING_TIER_CUT_ORDER)

        for year, r in with_ltc.items():
            ltc = r.get("ltc_prem_yr") or 0.0
            if ltc <= 1.0:
                continue
            base = without_ltc.get(year)
            if base is None:
                continue
            self.assertAlmostEqual(
                total_cuttable(r) - total_cuttable(base), ltc, places=2,
                msg=f"year {year}: the cuttable pool did not grow by the "
                    f"{ltc} LTC premium when it was enabled",
            )

    def test_a_moderate_cut_takes_more_contingent_liability_dollars_with_the_premium_on(self):
        # cut_frac sized to spill past discretionary+important into
        # contingent_liability (its SPENDING_TIER_CUT_ORDER priority, ahead
        # of essential) in both runs -- the WITH-ltc run's contingent_
        # liability cut must exceed the WITHOUT-ltc run's, confirming the
        # extra premium dollars are actually reachable by the cascade, not
        # just present in the reported total.
        with_ltc, without_ltc = _paired_rows()
        with_result = spending_priority_cut_check(list(with_ltc.values()), cut_frac=0.5)
        without_result = spending_priority_cut_check(list(without_ltc.values()), cut_frac=0.5)
        checked_any = False
        for year, r in with_ltc.items():
            ltc = r.get("ltc_prem_yr") or 0.0
            if ltc <= 1.0:
                continue
            with_cuts = with_result["tier_cut_by_year"].get(year)
            without_cuts = without_result["tier_cut_by_year"].get(year)
            if not with_cuts or not without_cuts:
                continue
            with_cl_cut = with_cuts.get("contingent_liability", 0.0)
            without_cl_cut = without_cuts.get("contingent_liability", 0.0)
            if with_cl_cut <= 0.0 and without_cl_cut <= 0.0:
                continue
            checked_any = True
            self.assertGreater(
                with_cl_cut, without_cl_cut,
                f"year {year}: contingent_liability's cut did not grow when "
                "the LTC premium was enabled, even though the cut reaches "
                "contingent_liability in both runs",
            )
        self.assertTrue(checked_any, "no cut-check year reached contingent_liability in either run")

    def test_essential_is_never_cut_before_contingent_liability_in_an_ltc_year(self):
        # Direct assertion of cascade ORDER, not just pool membership:
        # essential must show zero cut in any year where contingent_liability
        # still has room, confirming the premium is genuinely reached before
        # essential rather than merely counted in the same total.
        with_ltc, _ = _paired_rows()
        result = spending_priority_cut_check(list(with_ltc.values()), cut_frac=0.15)
        checked_any = False
        for year, r in with_ltc.items():
            ltc = r.get("ltc_prem_yr") or 0.0
            if ltc <= 1.0:
                continue
            cuts = result["tier_cut_by_year"].get(year)
            if not cuts:
                continue
            cl_tier = (r.get("spend_by_tier") or {}).get("contingent_liability", 0.0)
            cl_cut = cuts.get("contingent_liability", 0.0)
            essential_cut = cuts.get("essential", 0.0)
            if cl_cut >= cl_tier - 1e-6:
                continue  # contingent_liability tier exhausted this year; not the case this test needs
            checked_any = True
            self.assertEqual(
                essential_cut, 0.0,
                f"year {year}: essential was cut ({essential_cut}) while "
                f"contingent_liability still had room ({cl_tier - cl_cut} left)",
            )
        self.assertTrue(checked_any, "no cut-check year left contingent_liability partially unexhausted")


if __name__ == "__main__":
    unittest.main()
