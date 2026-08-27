"""Phase 1 items 4-6 (optimization refactor) acceptance-criterion fixture:
"a fixture proves that spending, benefit, and filing-status changes occur
after first death" in the VECTORIZED Monte Carlo engine specifically (the
scalar engine, monte_carlo_exact_scalar, already got this correct "for
free" -- see its docstring / tests/test_optimization_phase1_mc_spend_by_tier.py).

This compares the same fixed-seed batch run with
``mc_vectorized_survivor_economics`` on vs. off, on a real two-spouse
fixture with distinct ages (so first death is asymmetric across the
h/w-first cases and occurs within a realistic horizon).
"""
from __future__ import annotations

import copy
import unittest
from pathlib import Path

import numpy as np

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import _mc_vectorized_batch, project

ROOT = Path(__file__).resolve().parents[1]


def _base_config():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["plan_end"] = int(c["plan_start"]) + 30  # long enough horizon for
    # first-death events to actually occur within the plan for a meaningful
    # fraction of sampled paths (ages run into the 90s by plan end).
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    return c


class VectorizedSurvivorEconomicsFixtureTests(unittest.TestCase):
    def test_withdrawals_and_spend_diverge_only_after_first_death(self):
        c_on = _base_config()
        c_off = copy.deepcopy(c_on)
        c_off["mc_vectorized_survivor_economics"] = False

        base_rows = project(c_on)
        seed = 4242
        n_sims = 30

        batch_on = _mc_vectorized_batch(c_on, base_rows, n_sims, seed, 0.06, 0.12, 0.0, use_asset_classes=False)
        batch_off = _mc_vectorized_batch(c_off, base_rows, n_sims, seed, 0.06, 0.12, 0.0, use_asset_classes=False)

        self.assertIsNotNone(batch_on["survivor_buckets"], "expected survivor buckets to be built when the flag is on")
        self.assertIsNone(batch_off["survivor_buckets"], "expected no survivor buckets when the flag is off")

        # Same seed => same sampled death years, returns, and inflation paths
        # in both runs (survivor_buckets only affects how flows are BLENDED,
        # not what's sampled) -- so any difference below is attributable
        # entirely to the survivor-economics blending.
        np.testing.assert_array_equal(batch_on["h_death_years"], batch_off["h_death_years"])
        np.testing.assert_array_equal(batch_on["w_death_years"], batch_off["w_death_years"])

        h_death = batch_on["h_death_years"]
        w_death = batch_on["w_death_years"]
        first_death = np.minimum(h_death, w_death)
        years = np.array(batch_on["years"], dtype=int)

        proj_on = batch_on["projection"]
        proj_off = batch_off["projection"]

        self.assertTrue((first_death < years[-1]).any(),
                         "no sampled path had a first death within the plan horizon -- fixture needs a longer horizon or more sims")

        saw_pre_death_match = False
        saw_post_death_divergence = False
        for j, year in enumerate(years):
            pre_mask = year <= first_death
            post_mask = ~pre_mask
            if pre_mask.any():
                # Before any given path's own first death, "on" and "off"
                # must be IDENTICAL for that path/year (no survivor bucket
                # applies yet in either run).
                np.testing.assert_allclose(
                    proj_on["spend_total_real"][pre_mask, j], proj_off["spend_total_real"][pre_mask, j],
                    atol=1.0, err_msg=f"year {year}: pre-first-death spend differs between on/off",
                )
                saw_pre_death_match = True
            if post_mask.any():
                on_vals = proj_on["spend_total_real"][post_mask, j]
                off_vals = proj_off["spend_total_real"][post_mask, j]
                if not np.allclose(on_vals, off_vals, atol=1.0):
                    saw_post_death_divergence = True
                    # Survivor spend factor is <= 1.0 (deterministic_engine.py
                    # default 0.65), and no other change in this fixture
                    # would push a path's spend UP after death, so "on"
                    # should never exceed "off" by more than a rounding
                    # tolerance for spend specifically.
                    self.assertTrue(np.all(on_vals <= off_vals + 1.0),
                                     f"year {year}: survivor-economics spend exceeds the no-survivor-economics spend")

        self.assertTrue(saw_pre_death_match, "no year had any path still before its own first death")
        self.assertTrue(saw_post_death_divergence,
                         "no post-first-death path/year differed between survivor-economics on vs. off")

    def test_withdrawal_requests_also_diverge_not_just_the_reported_spend_metric(self):
        # Confirms items 4-6 changed the DRIVING withdrawal cascade (the
        # plan's own requirement), not merely the additive spend_total_real
        # side-metric from item 1 -- checked via the liquid-asset trajectory,
        # which only moves if actual withdrawal amounts changed.
        c_on = _base_config()
        c_off = copy.deepcopy(c_on)
        c_off["mc_vectorized_survivor_economics"] = False
        base_rows = project(c_on)
        seed = 99
        n_sims = 30

        batch_on = _mc_vectorized_batch(c_on, base_rows, n_sims, seed, 0.06, 0.12, 0.0, use_asset_classes=False)
        batch_off = _mc_vectorized_batch(c_off, base_rows, n_sims, seed, 0.06, 0.12, 0.0, use_asset_classes=False)

        liquid_on = batch_on["projection"]["liquid"]
        liquid_off = batch_off["projection"]["liquid"]
        first_death = np.minimum(batch_on["h_death_years"], batch_on["w_death_years"])
        years = np.array(batch_on["years"], dtype=int)

        if not (first_death < years[-1]).any():
            self.skipTest("no sampled path had a first death within the plan horizon at this seed")

        # A path with a first death well before plan end should show a
        # DIFFERENT terminal liquid balance between the two runs (lower
        # survivor spending after items 4-6 typically preserves more
        # assets) -- if liquid trajectories are identical, the withdrawal
        # cascade itself never changed and the fix is inert.
        late_first_death_paths = np.where(first_death <= years[len(years) // 2])[0]
        self.assertTrue(late_first_death_paths.size > 0,
                         "no path had an early-enough first death to meaningfully test terminal liquid divergence")
        terminal_on = liquid_on[late_first_death_paths, -1]
        terminal_off = liquid_off[late_first_death_paths, -1]
        self.assertFalse(np.allclose(terminal_on, terminal_off, atol=1.0),
                          "terminal liquid balance is identical with survivor economics on vs. off -- "
                          "the withdrawal cascade itself does not appear to have changed")


if __name__ == "__main__":
    unittest.main()
