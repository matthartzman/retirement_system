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

This is deliberately still a reporting/attribution change, not a change to
withdrawal totals: for a fixed spend_cut_frac, the aggregate dollars pulled
from taxable/pretax/roth/cash and hence unfunded/liquid/total/success_rate
are unaffected by which tier absorbs the cut (the household still needs the
same total funding regardless of which specific goods were cut) -- only the
per-tier attribution (spend_{tier}_real, essential_shortfall_real,
essential_fully_funded) changes.
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
    def test_no_cut_is_bit_identical_to_pre_change_behavior(self):
        # spend_cut_frac=0 (the default, used by every caller except the
        # required-cut-distribution/sustainable-spending-solve searches) must
        # be an exact no-op: cut_mult=1 collapses the cascade to the tier's
        # own unmodified value, matching the old tier * cut_mult(=1) formula.
        c = _base_config()
        base_rows = project(c)
        batch = _mc_vectorized_batch(c, base_rows, 6, 5, 0.06, 0.12, 0.0, use_asset_classes=False)
        proj = batch["projection"]
        for tier_key in ('spend_discretionary_real', 'spend_important_real', 'spend_essential_real'):
            self.assertIn(tier_key, proj)
        h_death = batch["h_death_years"]
        w_death = batch["w_death_years"]
        first_death = np.minimum(h_death, w_death)
        inf = float(c.get("inf", 0.025) or 0.025)
        start = int(c["plan_start"])
        checked_any_path_year = False
        for j, row in enumerate(base_rows):
            year = int(row["year"])
            pre_death_mask = year <= first_death
            if not pre_death_mask.any():
                continue
            det_tiers = row.get("spend_by_tier") or {}
            for tier, det_nominal in det_tiers.items():
                key = f"spend_{tier}_real"
                if key not in proj:
                    continue
                expected = float(det_nominal) / ((1.0 + inf) ** max(0, year - start))
                self.assertTrue(
                    np.allclose(proj[key][pre_death_mask, j], expected, atol=1.0),
                    f"tier {tier} year {year}: no-cut real spend diverged from the deterministic value "
                    f"for a path still in pre-first-death joint economics",
                )
                checked_any_path_year = True
        self.assertTrue(checked_any_path_year, "no pre-first-death year/path was available to check")

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

    def test_spend_total_real_unaffected_by_tier_priority_attribution(self):
        # The headline invariant this change must preserve: reattributing
        # WHICH tier absorbs a cut never changes the total dollar cut.
        c = _base_config()
        base_rows = project(c)
        batch = _mc_vectorized_batch(c, base_rows, 5, 11, 0.06, 0.12, 0.0, use_asset_classes=False)
        no_cut = _mc_vectorized_projection(c, base_rows, batch["returns"], batch["inflation_paths"], batch["max_death_years"], spend_cut_frac=0.0)
        half_cut = _mc_vectorized_projection(c, base_rows, batch["returns"], batch["inflation_paths"], batch["max_death_years"], spend_cut_frac=0.5)
        self.assertTrue(np.allclose(half_cut["spend_total_real"], no_cut["spend_total_real"] * 0.5, atol=1.0))


if __name__ == "__main__":
    unittest.main()
