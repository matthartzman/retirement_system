"""Optimization-refactor Phase 2 follow-on ("Not done" item 1 in
documentation/OPTIMIZATION_REFACTOR_STATUS.md): "Redirecting actual
withdrawal amounts by tier priority inside the MC engines (today's uniform
cut_mult would become tier-prioritized)."

The vectorized engine's ``spend_cut_frac`` previously shrank every spend
tier (discretionary/important/essential) by the identical fraction, so an
elective spending cut hit essential spending exactly as hard as a vacation
budget. ``_mc_tier_priority_retained`` (src/planning_engines.py) now
redistributes the SAME total dollar cut by cut priority instead --
discretionary absorbs it first, then important, essential protected last --
mirroring the cascade ``spending_priority_cut_check`` already uses to
report a solved cut_frac.

This WAS deliberately still a reporting/attribution change when first
written: for a fixed spend_cut_frac, the aggregate dollars pulled from
taxable/pretax/roth/cash and hence unfunded/liquid/total/success_rate were
unaffected by which tier absorbed the cut -- only the per-tier attribution
(spend_{tier}_real, essential_shortfall_real, essential_fully_funded)
changed.

That invariant was deliberately SUPERSEDED by the "Genuinely redirecting
withdrawal requests... by tier priority" increment (Option B,
docs/superpowers/plans/2026-08-27-mc-tier-priority-withdrawal-redirection-
spec.md): `_mc_tier_priority_retained`'s per-tier "need" figures now
genuinely DRIVE which bucket each tier's spending draws from
(SPENDING_TIER_BUCKET_POLICY: essential/contingent_liability keep the full
HSA->pretax->taxable->Roth cascade; important loses Roth access;
discretionary is restricted to taxable/pretax only), rather than being a
purely-after-the-fact attribution of one blended, uniformly-scaled
withdrawal. `_mc_tier_priority_retained` itself is UNCHANGED (still a pure
cascade-math helper, still covered by TierPriorityRetainedUnitTests below
exactly as before) -- what changed is that its OUTPUT now feeds real
withdrawal requests instead of only a reporting step run after the
recursion had already finished. The two tests below that encoded the old
uniform-withdrawal invariant were updated accordingly; see each test's own
docstring for the corrected invariant.
"""
from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import (
    _mc_tier_priority_retained,
    _mc_vectorized_batch,
    _mc_vectorized_projection,
    project,
)

ROOT = Path(__file__).resolve().parents[1]


def _base_config():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["plan_end"] = min(int(c["plan_end"]), int(c["plan_start"]) + 8)
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    return c


class TierPriorityRetainedUnitTests(unittest.TestCase):
    """Direct unit coverage of the cascade helper, independent of the MC
    plumbing around it."""

    def test_small_cut_absorbed_entirely_by_discretionary(self):
        # discretionary=100, important=50, essential=200; a cut smaller than
        # discretionary alone must leave important/essential untouched.
        tier_scaled = {
            'discretionary': np.array([[100.0]]),
            'important': np.array([[50.0]]),
            'essential': np.array([[200.0]]),
        }
        # total=350; retained fraction 0.8 -> target_cut=70, all absorbable
        # by discretionary (100) alone.
        retained = _mc_tier_priority_retained(tier_scaled, np.array([0.8]))
        self.assertAlmostEqual(float(retained['discretionary'][0, 0]), 30.0, places=6)
        self.assertAlmostEqual(float(retained['important'][0, 0]), 50.0, places=6)
        self.assertAlmostEqual(float(retained['essential'][0, 0]), 200.0, places=6)

    def test_essential_only_absorbs_the_uncovered_remainder(self):
        # Same tiers; retained fraction 0.1 -> target_cut=315, which exceeds
        # discretionary+important (150), so essential must absorb the rest.
        tier_scaled = {
            'discretionary': np.array([[100.0]]),
            'important': np.array([[50.0]]),
            'essential': np.array([[200.0]]),
        }
        retained = _mc_tier_priority_retained(tier_scaled, np.array([0.1]))
        self.assertAlmostEqual(float(retained['discretionary'][0, 0]), 0.0, places=6)
        self.assertAlmostEqual(float(retained['important'][0, 0]), 0.0, places=6)
        # target_cut=315; discretionary+important absorb 150, essential
        # absorbs the remaining 165, leaving 35 retained.
        self.assertAlmostEqual(float(retained['essential'][0, 0]), 35.0, places=6)

    def test_total_retained_matches_uniform_reduction(self):
        # Regardless of tier attribution, the SUM across the three cuttable
        # tiers must equal the old uniform-cut_mult total exactly.
        rng = np.random.default_rng(0)
        d = rng.uniform(0, 500, size=(20, 5))
        i = rng.uniform(0, 500, size=(20, 5))
        e = rng.uniform(0, 500, size=(20, 5))
        mult = rng.uniform(0.0, 1.0, size=20)
        retained = _mc_tier_priority_retained(
            {'discretionary': d, 'important': i, 'essential': e}, mult
        )
        total_retained = retained['discretionary'] + retained['important'] + retained['essential']
        expected = (d + i + e) * mult.reshape(-1, 1)
        self.assertTrue(np.allclose(total_retained, expected, atol=1e-6))

    def test_contingent_liability_keeps_uniform_treatment_and_is_excluded_from_cascade(self):
        tier_scaled = {
            'discretionary': np.array([[100.0]]),
            'important': np.array([[50.0]]),
            'essential': np.array([[200.0]]),
            'contingent_liability': np.array([[40.0]]),
        }
        retained = _mc_tier_priority_retained(tier_scaled, np.array([0.5]))
        # contingent_liability gets the plain uniform mult, unaffected by
        # the discretionary/important/essential cascade.
        self.assertAlmostEqual(float(retained['contingent_liability'][0, 0]), 20.0, places=6)
        # target_cut is computed from discretionary+important+essential only
        # (350 * 0.5 = 175), so essential absorbs 175 - 100 - 50 = 25.
        self.assertAlmostEqual(float(retained['discretionary'][0, 0]), 0.0, places=6)
        self.assertAlmostEqual(float(retained['important'][0, 0]), 0.0, places=6)
        self.assertAlmostEqual(float(retained['essential'][0, 0]), 175.0, places=6)


class VectorizedEngineTierPriorityTests(unittest.TestCase):
    def test_first_year_no_cut_bit_identical_for_unrestricted_tiers(self):
        # spend_cut_frac=0 makes cut_mult=1, so every tier's DEMAND collapses
        # to its own unmodified deterministic value -- but under Option B,
        # whether that demand is fully FUNDED now also depends on
        # SPENDING_TIER_BUCKET_POLICY and on funding ORDER (essential/
        # contingent_liability/'other' are funded before important, which is
        # funded before discretionary -- see MC_TIER_FUNDING_ORDER). Checked
        # at year 0 only, before any path can have drawn down a bucket in a
        # PRIOR year: every path starts from the same known balances, so
        # essential/contingent_liability (unrestricted, highest funding
        # priority) must still exactly match the deterministic figure this
        # first year -- a real divergence here (not just in a later,
        # compounding-affected year) would mean a genuine bug, not an
        # expected consequence of re-deriving the cascade.
        c = _base_config()
        base_rows = project(c)
        batch = _mc_vectorized_batch(c, base_rows, 6, 5, 0.06, 0.12, 0.0, use_asset_classes=False)
        proj = batch["projection"]
        unrestricted_tiers = {'essential', 'contingent_liability'}
        for tier_key in ('spend_discretionary_real', 'spend_important_real', 'spend_essential_real'):
            self.assertIn(tier_key, proj)
        inf = float(c.get("inf", 0.025) or 0.025)
        row0 = base_rows[0]
        det_tiers = row0.get("spend_by_tier") or {}
        checked_any = False
        for tier, det_nominal in det_tiers.items():
            if tier not in unrestricted_tiers:
                continue
            key = f"spend_{tier}_real"
            if key not in proj:
                continue
            expected = float(det_nominal)
            self.assertTrue(
                np.allclose(proj[key][:, 0], expected, atol=1.0),
                f"tier {tier} year 0: no-cut real spend diverged from the deterministic value",
            )
            checked_any = True
        self.assertTrue(checked_any, "no unrestricted tier was available to check")

    def test_restricted_tiers_never_exceed_their_own_deterministic_demand(self):
        # No tier's genuinely-funded real spend can ever exceed its own
        # deterministic demand for that year, regardless of tier or year --
        # the cascade can fall short (a real funding shortfall, expected
        # under Option B) but never invents money. Checked across ALL tiers
        # and years, since this direction of the inequality holds even where
        # exact bit-identity does not (e.g. later years, where a prior
        # year's genuine shortfall or funding-order competition with
        # 'other'/importantdiscretionary can leave even essential short of
        # its own nominal demand -- a real, expected effect of re-deriving
        # the cascade rather than replaying one blended deterministic split).
        c = _base_config()
        base_rows = project(c)
        batch = _mc_vectorized_batch(c, base_rows, 6, 5, 0.06, 0.12, 0.0, use_asset_classes=False)
        proj = batch["projection"]
        inf = float(c.get("inf", 0.025) or 0.025)
        start = int(c["plan_start"])
        for j, row in enumerate(base_rows):
            year = int(row["year"])
            det_tiers = row.get("spend_by_tier") or {}
            for tier, det_nominal in det_tiers.items():
                key = f"spend_{tier}_real"
                if key not in proj:
                    continue
                expected = float(det_nominal) / ((1.0 + inf) ** max(0, year - start))
                self.assertTrue(
                    bool(np.all(proj[key][:, j] <= expected + 1.0)),
                    f"tier {tier} year {year}: real spend exceeded its own deterministic demand",
                )

    def test_a_cut_smaller_than_discretionary_plus_important_never_touches_essential(self):
        c = _base_config()
        base_rows = project(c)
        batch = _mc_vectorized_batch(c, base_rows, 6, 5, 0.06, 0.12, 0.0, use_asset_classes=False)
        det_tiers = base_rows[0].get("spend_by_tier") or {}
        if not {'discretionary', 'important', 'essential'}.issubset(det_tiers):
            self.skipTest("frozen fixture does not classify all three cuttable tiers at year 0")
        d0, i0, e0 = det_tiers['discretionary'], det_tiers['important'], det_tiers['essential']
        total_cuttable = d0 + i0 + e0
        if total_cuttable <= 0 or d0 + i0 <= 0:
            self.skipTest("frozen fixture has no cuttable discretionary/important spend at year 0")
        # Pick a cut_frac guaranteed to stay within discretionary+important.
        safe_cut_frac = min(0.9, (d0 + i0) / total_cuttable * 0.5)
        proj = _mc_vectorized_projection(
            c, base_rows, batch["returns"], batch["inflation_paths"], batch["max_death_years"],
            spend_cut_frac=safe_cut_frac,
        )
        self.assertIn('spend_essential_real', proj)
        essential_col0 = proj['spend_essential_real'][:, 0]
        no_cut = _mc_vectorized_projection(
            c, base_rows, batch["returns"], batch["inflation_paths"], batch["max_death_years"],
            spend_cut_frac=0.0,
        )
        essential_col0_no_cut = no_cut['spend_essential_real'][:, 0]
        self.assertTrue(
            np.allclose(essential_col0, essential_col0_no_cut, atol=1.0),
            "essential-tier real spend moved even though the cut fits entirely within discretionary+important",
        )

    def test_half_cut_never_produces_more_first_year_real_spend_than_no_cut(self):
        # Superseded headline invariant: this used to assert half_cut's
        # spend_total_real equals EXACTLY half of no_cut's, because the old
        # mechanism was pure post-hoc attribution of one uniformly-scaled
        # withdrawal -- reattributing which tier "absorbed" a cut could never
        # change the total. Under Option B the cut changes each tier's own
        # DEMAND (via _mc_tier_priority_retained, unchanged), but genuine
        # per-tier bucket restriction means how much of that reduced demand
        # is actually FUNDED depends on that tier's own account balances --
        # so the exact-half relationship no longer holds in general.
        #
        # Checked at year 0 only (not summed/compared across the whole
        # horizon): from year 1 onward, drawing LESS in an earlier year
        # under half_cut leaves MORE balance to compound forward, which can
        # let a later year fund MORE real spend under half_cut than a
        # no_cut path that already permanently depleted an account --  a
        # real, expected compounding effect of genuine redirection, not a
        # bug. At year 0 both runs share identical starting balances, so
        # asking for less cannot yet fund more.
        c = _base_config()
        base_rows = project(c)
        batch = _mc_vectorized_batch(c, base_rows, 5, 11, 0.06, 0.12, 0.0, use_asset_classes=False)
        no_cut = _mc_vectorized_projection(c, base_rows, batch["returns"], batch["inflation_paths"], batch["max_death_years"], spend_cut_frac=0.0)
        half_cut = _mc_vectorized_projection(c, base_rows, batch["returns"], batch["inflation_paths"], batch["max_death_years"], spend_cut_frac=0.5)
        self.assertTrue(bool(np.all(half_cut["spend_total_real"][:, 0] <= no_cut["spend_total_real"][:, 0] + 1.0)))


if __name__ == "__main__":
    unittest.main()
