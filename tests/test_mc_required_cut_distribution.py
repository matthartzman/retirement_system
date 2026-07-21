"""Wave 4 item 4.4 (system review P13 phase 1): required-cut distribution on
failing Monte Carlo paths.

``monte_carlo()`` already computes ``success_rate`` from ``path_success`` at
zero spending cut. This is purely additive post-processing on top of that:
for each path that failed, binary-search (via ``_mc_vectorized_projection``'s
new ``spend_cut_frac`` parameter, which defaults to 0.0 and is otherwise an
exact no-op) the smallest uniform spending cut that would have rescued it.
The success rate itself must never move.
"""
from __future__ import annotations

import copy
import unittest
from pathlib import Path

import numpy as np

from src.data_io import load_csv, parse_client
from src.planning_engines import (
    _mc_required_cut_distribution,
    _mc_vectorized_batch,
    _mc_vectorized_projection,
    monte_carlo,
    project,
)

ROOT = Path(__file__).resolve().parents[1]


def _base_config():
    c = parse_client(load_csv(ROOT / "input" / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["plan_end"] = min(int(c["plan_end"]), int(c["plan_start"]) + 10)
    c["mc_sims"] = 80
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    c["mc_sigma"] = 0.16
    return c


def _shrink_balances(c: dict, factor: float) -> dict:
    c = copy.deepcopy(c)
    c["balances"] = {k: float(v) * factor for k, v in (c.get("balances") or {}).items()}
    for acct in c.get("account_registry") or []:
        aid = acct.get("id")
        acct["balance"] = c["balances"].get(aid, float(acct.get("balance", 0.0) or 0.0) * factor)
    return c


class RequiredCutDistributionTests(unittest.TestCase):
    def test_zero_spend_cut_is_an_exact_no_op(self):
        c = _base_config()
        base_rows = project(c)
        batch = _mc_vectorized_batch(c, base_rows, 6, 7, 0.06, 0.12, 0.0, use_asset_classes=False)
        proj_default = _mc_vectorized_projection(c, base_rows, batch["returns"], batch["inflation_paths"], batch["max_death_years"])
        proj_explicit_zero = _mc_vectorized_projection(c, base_rows, batch["returns"], batch["inflation_paths"], batch["max_death_years"], spend_cut_frac=0.0)
        for key in ("liquid", "unfunded", "total"):
            self.assertTrue(np.array_equal(proj_default[key], proj_explicit_zero[key]), key)

    def test_distressed_plan_reports_required_cut_without_moving_success_rate(self):
        c = _shrink_balances(_base_config(), 0.2)
        mc = monte_carlo(c, n_sims=80, seed=7)
        rc = mc["required_cut_distribution"]
        self.assertGreater(rc["n_failing"], 0, "expected a shrunk-balance plan to produce MC failures")
        self.assertEqual(rc["n_failing"], len(rc["required_cuts"]) + rc["n_infeasible"])
        if rc["required_cut_median"] is not None:
            self.assertGreaterEqual(rc["required_cut_median"], 0.0)
            self.assertLessEqual(rc["required_cut_median"], rc["required_cut_p90"])
            self.assertLessEqual(rc["required_cut_p90"], 0.90)
        # Re-running with the same seed must reproduce the identical success rate —
        # the required-cut search must not perturb the primary result.
        mc_again = monte_carlo(c, n_sims=80, seed=7)
        self.assertEqual(mc["success_rate"], mc_again["success_rate"])
        self.assertEqual(mc["required_cut_distribution"]["n_failing"], mc_again["required_cut_distribution"]["n_failing"])

    def test_comfortable_plan_reports_no_failing_paths(self):
        c = _shrink_balances(_base_config(), 25.0)
        mc = monte_carlo(c, n_sims=20, seed=3)
        rc = mc["required_cut_distribution"]
        self.assertEqual(rc["n_failing"], 0)
        self.assertIsNone(rc["required_cut_median"])
        self.assertIsNone(rc["required_cut_p90"])

    def test_required_cut_actually_rescues_the_failing_path_it_is_reported_for(self):
        c = _shrink_balances(_base_config(), 0.2)
        base_rows = project(c)
        batch = _mc_vectorized_batch(c, base_rows, 80, 7, 0.06, 0.16, 0.0, use_asset_classes=False)
        fail_idx = np.where(~np.array(batch["path_success"]))[0]
        self.assertGreater(fail_idx.size, 0)

        rc = _mc_required_cut_distribution(c, base_rows, batch, 0.0)
        self.assertGreater(len(rc["required_cuts"]), 0, "expected at least one feasible rescue within the cut cap")

        # Isolate exactly one failing path and confirm its reported cut (plus a
        # small margin for the bisection's finite precision) actually flips it
        # from failure to success when replayed alone.
        one_idx = fail_idx[:1]
        one_batch = {
            "years": batch["years"],
            "path_success": [False],
            "returns": batch["returns"][one_idx],
            "inflation_paths": {k: v[one_idx] for k, v in batch["inflation_paths"].items()},
            "max_death_years": batch["max_death_years"][one_idx],
        }
        rc_one = _mc_required_cut_distribution(c, base_rows, one_batch, 0.0)
        self.assertEqual(rc_one["n_failing"], 1)
        self.assertEqual(rc_one["n_infeasible"], 0, "expected this path to be rescuable within the cut cap")
        required = rc_one["required_cuts"][0]

        years = np.array(batch["years"], dtype=int)
        max_death_one = batch["max_death_years"][one_idx]
        rescued_cut = min(0.90, required + 0.05)
        proj = _mc_vectorized_projection(
            c, base_rows, batch["returns"][one_idx],
            {k: v[one_idx] for k, v in batch["inflation_paths"].items()},
            max_death_one, spend_cut_frac=np.array([rescued_cut]),
        )
        active = years.reshape(1, -1) <= max_death_one.reshape(-1, 1)
        failure = ((proj["unfunded"] > 1.0) | (proj["liquid"] <= 0.0)) & active
        self.assertFalse(bool(np.any(failure)), f"cut {rescued_cut:.3f} (required {required:.3f}) should have rescued this path")


if __name__ == "__main__":
    unittest.main()
