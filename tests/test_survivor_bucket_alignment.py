"""Bucket-ID round-trip invariant tests for the Phase 1 items 4-6
survivor-economics vectorized MC engine rewire.

The single highest-risk correctness point in that design is
``bucket_id = spouse_first * n_years + year_idx``, which must be computed
identically on the WRITE side (``_mc_survivor_bucket_flows``, building the
stacked bucket arrays) and the READ side (``_mc_vectorized_projection``,
selecting each path's bucket). A drift here would silently select the wrong
bucket for every path, with no exception. This file guards against that in
two independent ways: (1) recomputing a handful of buckets directly via
``run_scenario`` and asserting an EXACT match against what the bucket
builder stored, and (2) constructing synthetic per-path death-year arrays
with known values and asserting ``_mc_vectorized_projection`` selects
exactly the bucket those death years imply.
"""
from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import (
    _mc_row_bucket_flows,
    _mc_survivor_bucket_flows,
    _mc_vectorized_projection,
    project,
    run_scenario,
)

ROOT = Path(__file__).resolve().parents[1]


def _base_config():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["plan_end"] = min(int(c["plan_end"]), int(c["plan_start"]) + 12)
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    return c


class BucketBuilderWriteSideTests(unittest.TestCase):
    def test_bucket_arrays_match_independent_run_scenario_recompute(self):
        c = _base_config()
        base_rows = project(c)
        years = [int(r["year"]) for r in base_rows]
        n_years = len(years)

        buckets = _mc_survivor_bucket_flows(c, base_rows)
        self.assertIsNotNone(buckets, "two-spouse fixture unexpectedly produced no survivor buckets")
        self.assertEqual(buckets["n_years"], n_years)
        self.assertEqual(buckets["n_buckets"], 2 * n_years)

        far_future = int(c["plan_end"]) + 200
        # Spot-check a handful of (spouse_first, fd_year) combinations, not
        # all of them -- each check reruns project() independently, so this
        # stays fast while still exercising the write-side formula at
        # several points (first year, a middle year, the last year).
        check_year_idxs = sorted({0, n_years // 2, n_years - 1})
        for spouse_first in (0, 1):
            for year_idx in check_year_idxs:
                fd_year = years[year_idx]
                overrides = {"first_death_yr": fd_year}
                if spouse_first == 0:
                    overrides["h_death_yr"] = fd_year
                    overrides["w_death_yr"] = far_future
                else:
                    overrides["w_death_yr"] = fd_year
                    overrides["h_death_yr"] = far_future
                _c2, rows2 = run_scenario(c, overrides=overrides)
                expected_flows = _mc_row_bucket_flows(_c2, rows2)
                bucket_id = spouse_first * n_years + year_idx

                np.testing.assert_array_equal(
                    buckets["arrays"]["withdrawals.taxable"][bucket_id, :],
                    expected_flows["withdrawals"]["taxable"],
                    err_msg=f"spouse_first={spouse_first} fd_year={fd_year}: withdrawals.taxable mismatch",
                )
                np.testing.assert_array_equal(
                    buckets["arrays"]["total_tax"][bucket_id, :],
                    expected_flows["total_tax"],
                    err_msg=f"spouse_first={spouse_first} fd_year={fd_year}: total_tax mismatch",
                )
                for tier, arr in (expected_flows.get("spend_by_tier") or {}).items():
                    np.testing.assert_array_equal(
                        buckets["spend_by_tier"][tier][bucket_id, :], arr,
                        err_msg=f"spouse_first={spouse_first} fd_year={fd_year}: spend_by_tier[{tier}] mismatch",
                    )

    def test_single_person_household_returns_none(self):
        c = _base_config()
        c["members"] = [c["members"][0]] if c.get("members") else []
        base_rows = project(c)
        self.assertIsNone(_mc_survivor_bucket_flows(c, base_rows))


class BucketReadSideAlignmentTests(unittest.TestCase):
    """Confirms _mc_vectorized_projection's read-side bucket_id formula
    selects exactly the bucket a path's own sampled death years imply, using
    synthetic h_death_years/w_death_years arrays with known values."""

    def test_read_side_selects_expected_bucket_for_known_death_years(self):
        c = _base_config()
        base_rows = project(c)
        years = [int(r["year"]) for r in base_rows]
        n_years = len(years)
        plan_start = int(c["plan_start"])
        inf = float(c.get("inf", 0.025) or 0.025)
        buckets = _mc_survivor_bucket_flows(c, base_rows)
        self.assertIsNotNone(buckets)

        far_away = plan_start + 500
        # Path 0: H dies first in years[0] (year_idx 0) -> bucket_id 0.
        # Path 1: W dies first in years[0] (year_idx 0) -> bucket_id n_years.
        h_death = np.array([years[0], far_away], dtype=int)
        w_death = np.array([far_away, years[0]], dtype=int)
        max_death = np.maximum(h_death, w_death)
        n_sims = 2
        returns = np.zeros((n_sims, n_years))
        inflation_paths = {
            "inflation_index_matrix": np.ones((n_sims, n_years)),
            "medical_index_matrix": np.ones((n_sims, n_years)),
            "wellness_shock_matrix": np.zeros((n_sims, n_years)),
            "inflation_by_year_matrix": np.zeros((n_sims, n_years)),
        }
        proj = _mc_vectorized_projection(
            c, base_rows, returns, inflation_paths, max_death,
            h_death_years=h_death, w_death_years=w_death, survivor_buckets=buckets,
        )

        # With inf_idx == 1 and cut_mult == 1 everywhere in this synthetic
        # setup, spending_scale[:, j] == 1 / det_idx[j], so
        # spend_total_real[path, j] == bucket_tier_sum[bucket_id, j] / det_idx[j]
        # for any year j strictly after that path's own first death, and
        # == the ORIGINAL joint trajectory's tier sum / det_idx[j] for year 0
        # itself (first death == year 0 is not masked -- the mask is a
        # strict ">").
        def det_idx(j):
            return (1.0 + inf) ** (years[j] - plan_start)

        joint_tier_sum_0 = sum((base_rows[0].get("spend_by_tier") or {}).values())
        self.assertAlmostEqual(proj["spend_total_real"][0, 0], joint_tier_sum_0 / det_idx(0), places=2)
        self.assertAlmostEqual(proj["spend_total_real"][1, 0], joint_tier_sum_0 / det_idx(0), places=2)

        for j in range(1, n_years):
            expected_path0 = sum(buckets["spend_by_tier"][tier][0, j] for tier in buckets["spend_by_tier"]) / det_idx(j)
            expected_path1 = sum(buckets["spend_by_tier"][tier][n_years, j] for tier in buckets["spend_by_tier"]) / det_idx(j)
            self.assertAlmostEqual(proj["spend_total_real"][0, j], expected_path0, places=2,
                                    msg=f"year {years[j]}: path 0 (H first) did not select bucket_id=0")
            self.assertAlmostEqual(proj["spend_total_real"][1, j], expected_path1, places=2,
                                    msg=f"year {years[j]}: path 1 (W first) did not select bucket_id=n_years")


if __name__ == "__main__":
    unittest.main()
