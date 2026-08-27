"""Phase 1 (optimization refactor) coverage: real, per-tier spend matrices
emitted by both Monte Carlo engines.

Phase 0 (see tests/test_spending_tier_taxonomy.py) added row['spend_by_tier']
to the deterministic engine. Phase 1 propagates that classification into
both Monte Carlo engines as real (plan-start-dollar) spend distributions,
per the "Final Optimization Implementation Plan" Phase 1 item 1: "Emit real,
plan-start-dollar matrices for spend_real, spend_essential_real,
spend_important_real, and spend_contingent_real."

Both additions are purely additive -- new output keys only, no existing
dollar total or success/failure computation is touched -- so this file
proves the reconciliation identity rather than any pinned dollar figure.
"""
from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import (
    _mc_row_bucket_flows,
    _mc_vectorized_batch,
    monte_carlo_exact_scalar,
    project,
)
from src.spending_budget_resolver import SPENDING_TIERS

ROOT = Path(__file__).resolve().parents[1]


def _base_config():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["plan_end"] = min(int(c["plan_end"]), int(c["plan_start"]) + 8)
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    return c


class RowBucketFlowsTierExtractionTests(unittest.TestCase):
    def test_flows_carry_spend_by_tier_matching_row_totals(self):
        c = _base_config()
        base_rows = project(c)
        self.assertTrue(any(r.get("spend_by_tier") for r in base_rows),
                         "frozen fixture produced no spend_by_tier at all -- Phase 0 regressed")
        flows = _mc_row_bucket_flows(c, base_rows)
        self.assertIn("spend_by_tier", flows)
        tier_arrays = flows["spend_by_tier"]
        self.assertTrue(set(tier_arrays.keys()).issubset(set(SPENDING_TIERS.keys()) | {"unclassified"}))
        for j, row in enumerate(base_rows):
            expected_total = sum((row.get("spend_by_tier") or {}).values())
            got_total = sum(float(arr[j]) for arr in tier_arrays.values())
            self.assertAlmostEqual(got_total, expected_total, places=1,
                                    msg=f"year {row.get('year')}: tier flow total {got_total} != row spend_by_tier total {expected_total}")


class VectorizedSpendByTierRealTests(unittest.TestCase):
    """No-cut invariant: with spend_cut_frac=0 (the default), every path
    must see the SAME real per-tier spend for a given year -- it's the
    deterministic plan's own tier composition, only deflated to real
    dollars -- and the tiers must sum to the deterministic real total."""

    def test_no_cut_paths_match_before_first_death_and_diverge_after(self):
        # Phase 1 items 4-6 superseded the old expectation here (every path
        # identical for a given year with no cut applied) -- that WAS the
        # bug: the vectorized engine used to ignore first death entirely.
        # A household's spending is only guaranteed identical across paths
        # BEFORE any path's own first death; after it, survivor economics
        # (spend factor, SS/pension changes, filing status) legitimately
        # make paths diverge from the joint-economics deterministic value
        # and from each other (different spouse dies first, different year).
        #
        # Genuine per-tier bucket redirection (Option B) adds a SECOND,
        # independent source of legitimate pre-death divergence: a path with
        # poor-enough returns can genuinely fail to fund its full deterministic
        # demand even before any death occurs -- unlike the pre-Option-B
        # reporting-only figures, which were pure deterministic-value replays
        # oblivious to whether the withdrawal cascade actually succeeded. So
        # the pre-death equality check below is additionally restricted to
        # paths/years with NO genuine shortfall (proj['unfunded'] <= $1) --
        # among those, demand was fully met, so the identity must still hold
        # exactly; a divergence there would be a real bug, not an expected
        # consequence of a path running short of money.
        c = _base_config()
        c["plan_end"] = int(c["plan_start"]) + 30  # full horizon (ages run
        # into the 90s), so first-death events actually occur within plan
        # for a meaningful fraction of paths -- the truncated 8-year config
        # other tests in this file use is too short for that.
        base_rows = project(c)
        batch = _mc_vectorized_batch(c, base_rows, 40, 7, 0.06, 0.12, 0.0, use_asset_classes=False)
        proj = batch["projection"]
        self.assertIn("spend_total_real", proj)
        h_death = batch["h_death_years"]
        w_death = batch["w_death_years"]
        first_death = np.minimum(h_death, w_death)

        start = int(c["plan_start"])
        inf = float(c.get("inf", 0.025) or 0.025)
        saw_pre_death_year = False
        saw_post_death_divergence = False
        for j, row in enumerate(base_rows):
            year = int(row["year"])
            det_real_total = float(row.get("total_spend", 0.0) or 0.0) / ((1.0 + inf) ** max(0, year - start))
            path_values = proj["spend_total_real"][:, j]
            fully_funded_mask = proj["unfunded"][:, j] <= 1.0
            pre_death_mask = (year <= first_death) & fully_funded_mask
            if pre_death_mask.any():
                pre_vals = path_values[pre_death_mask]
                self.assertTrue(np.allclose(pre_vals, det_real_total, atol=1.0),
                                 f"year {year}: a fully-funded path still in joint economics (first death "
                                 f"not yet reached) diverged from the deterministic real spend")
                saw_pre_death_year = True
            post_death_mask = (year > first_death) & fully_funded_mask
            if post_death_mask.any():
                post_vals = path_values[post_death_mask]
                if not np.allclose(post_vals, det_real_total, atol=1.0):
                    saw_post_death_divergence = True

        self.assertTrue(saw_pre_death_year, "no fully-funded year had any path still in pre-first-death joint economics")
        self.assertTrue(
            saw_post_death_divergence,
            "no fully-funded post-first-death path ever differed from the joint-economics deterministic "
            "value -- survivor economics may not be wired into the vectorized withdrawal recursion",
        )

    def test_per_tier_matrices_sum_to_spend_total_real(self):
        c = _base_config()
        base_rows = project(c)
        batch = _mc_vectorized_batch(c, base_rows, 8, 3, 0.06, 0.12, 0.0, use_asset_classes=False)
        proj = batch["projection"]
        tier_keys = [k for k in proj if k.startswith("spend_") and k.endswith("_real") and k != "spend_total_real"]
        self.assertTrue(tier_keys, "no per-tier spend_*_real matrices were emitted")
        summed = sum(proj[k] for k in tier_keys)
        self.assertTrue(np.allclose(summed, proj["spend_total_real"], atol=1.0))

    def test_spend_cut_frac_scales_real_spend_down_in_first_year(self):
        # Superseded from an exact-half assertion across the whole horizon:
        # under Option B, genuine per-tier bucket restriction means how much
        # of a (now smaller) cut demand gets funded depends on that tier's
        # own account balances, and less drawn in an earlier year compounds
        # forward -- see test_mc_tier_priority_cut_regression.py's matching
        # test for the full explanation. Checked at year 0, where both runs
        # share identical starting balances and the fixture is comfortably
        # funded enough that neither run should see a genuine shortfall.
        c = _base_config()
        base_rows = project(c)
        batch = _mc_vectorized_batch(c, base_rows, 5, 11, 0.06, 0.12, 0.0, use_asset_classes=False)
        from src.planning_engines import _mc_vectorized_projection
        no_cut = _mc_vectorized_projection(c, base_rows, batch["returns"], batch["inflation_paths"], batch["max_death_years"], spend_cut_frac=0.0)
        half_cut = _mc_vectorized_projection(c, base_rows, batch["returns"], batch["inflation_paths"], batch["max_death_years"], spend_cut_frac=0.5)
        self.assertTrue(np.allclose(half_cut["spend_total_real"][:, 0], no_cut["spend_total_real"][:, 0] * 0.5, atol=1.0))


class ScalarSpendByTierRealTests(unittest.TestCase):
    def test_scalar_engine_emits_percentiles_reconciling_near_deterministic(self):
        c = _base_config()
        base_rows = project(c)
        result = monte_carlo_exact_scalar(c, n_sims=10, seed=3, base_rows=base_rows)
        self.assertIn("spend_by_tier_real_pct_by_year", result)
        pct = result["spend_by_tier_real_pct_by_year"]
        self.assertTrue(pct, "scalar engine emitted no spend-by-tier percentiles at all")
        start = int(c["plan_start"])
        inf = float(c.get("inf", 0.025) or 0.025)
        by_year = {r["year"]: r for r in base_rows}
        first_year = base_rows[0]["year"]
        det_row_tiers = by_year[first_year].get("spend_by_tier") or {}
        for tier, det_nominal in det_row_tiers.items():
            det_real = det_nominal / ((1.0 + inf) ** max(0, first_year - start))
            self.assertIn(tier, pct)
            self.assertIn(first_year, pct[tier])
            median = pct[tier][first_year].get(50)
            self.assertIsNotNone(median, f"no median percentile reported for tier {tier}")
            # Loose tolerance: MC paths sample their own inflation/returns/
            # deaths, so this is a sanity check the figures are in the right
            # neighborhood, not a dollar-exact pin.
            if det_real > 0:
                self.assertLess(abs(median - det_real) / det_real, 0.5,
                                 f"tier {tier} year {first_year}: median {median} far from deterministic real {det_real}")


if __name__ == "__main__":
    unittest.main()
