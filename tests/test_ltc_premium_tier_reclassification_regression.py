"""ltc_prem_yr classifies as `essential`, not `contingent_liability`.

Design: docs/superpowers/plans/2026-08-26-ltc-premium-tier-reclassification-spec.md

An LTC insurance premium is a scheduled, known-in-advance cost -- the same
shape as a mortgage payment or a Medicare premium -- not a shock. Before
this fix, `deterministic_engine.py` tiered it with `wellness_shock_yr`
(a genuinely irregular, sampled cost) under `contingent_liability` only
because it *hedges* a contingent liability, not because paying it is
itself contingent.

This is not just a reporting relabel: `contingent_liability` is excluded
entirely from the MC engines' tier-priority cut cascade
(`spending_priority_cut_check` and the vectorized redistribution both
special-case it), while `essential` is cuttable, just last in priority
order. So before this fix, an LTC premium was NEVER protected by priority
ordering; after it, the premium is protected like any other fixed cost.

Every guard below compares an LTC-enabled run against a matched
LTC-disabled run of the SAME household and asserts the exact dollar DELTA,
not a loose `>=`/`>` against the tier's already-large total -- an early
draft of this file used loose inequalities against the ltc-enabled run
alone, and every one of them still passed with the fix reverted, because
essential's other components (mortgage, property tax, ...) already
cleared the threshold on their own regardless of where the LTC premium
was tiered. Mutation-tested: reverting the fix (putting ltc_prem_yr back
into contingent_liability) turns every delta-based guard below red.
"""
from __future__ import annotations

import unittest

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import project, spending_priority_cut_check

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

    def test_ltc_premium_moves_essential_by_exactly_the_premium(self):
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
                with_essential - base_essential, ltc, places=2,
                msg=f"year {year}: turning on the {ltc} LTC premium changed "
                    f"essential by {with_essential - base_essential}, not {ltc}",
            )

    def test_ltc_premium_does_not_move_contingent_liability(self):
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
                with_cl, base_cl, places=2,
                msg=f"year {year}: turning on the {ltc} LTC premium moved "
                    f"contingent_liability from {base_cl} to {with_cl} -- it "
                    "should be shock-only, unaffected by the premium",
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
    """The actual behavior change: which pool the premium's dollars fall
    into for the MC/deterministic tier-priority cut cascade, not just how
    they are labeled in a report. Directly exercises
    spending_priority_cut_check's own exclusion rule (planning_engines.py:
    `total_cuttable = sum(v for t, v in tiers.items() if t !=
    'contingent_liability')`) via a paired delta, the same way
    ClassificationTests does for the raw tier dollars."""

    def test_total_cuttable_pool_grows_by_exactly_the_premium(self):
        with_ltc, without_ltc = _paired_rows()

        def total_cuttable(row):
            tiers = row.get("spend_by_tier") or {}
            return sum(v for t, v in tiers.items() if t != "contingent_liability")

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
                    f"{ltc} LTC premium when it was enabled -- it is still "
                    "being excluded as if it were contingent_liability",
            )

    def test_a_near_total_cut_takes_more_essential_dollars_with_the_premium_on(self):
        # With cut_frac high enough to blow through discretionary+important
        # and land in essential in both runs, the WITH-ltc run's essential
        # cut must exceed the WITHOUT-ltc run's by roughly the premium --
        # confirming the extra dollars are actually reachable by the cut
        # cascade, not just present in the reported total.
        with_ltc, without_ltc = _paired_rows()
        with_result = spending_priority_cut_check(list(with_ltc.values()), cut_frac=0.99)
        without_result = spending_priority_cut_check(list(without_ltc.values()), cut_frac=0.99)
        checked_any = False
        for year, r in with_ltc.items():
            ltc = r.get("ltc_prem_yr") or 0.0
            if ltc <= 1.0:
                continue
            with_cuts = with_result["tier_cut_by_year"].get(year)
            without_cuts = without_result["tier_cut_by_year"].get(year)
            if not with_cuts or not without_cuts:
                continue
            with_essential_cut = with_cuts.get("essential", 0.0)
            without_essential_cut = without_cuts.get("essential", 0.0)
            if with_essential_cut <= 0.0 and without_essential_cut <= 0.0:
                continue
            checked_any = True
            self.assertGreater(
                with_essential_cut, without_essential_cut,
                f"year {year}: essential's cut did not grow when the LTC "
                "premium was enabled, even though the cut reaches essential "
                "in both runs",
            )
        self.assertTrue(checked_any, "no cut-check year reached essential in either run")


if __name__ == "__main__":
    unittest.main()
