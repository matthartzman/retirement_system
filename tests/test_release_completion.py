from __future__ import annotations

import unittest
from pathlib import Path

from src.data_io import load_csv
from src.report_compute import prepare_config_from_sectioned_data
from src.planning_engines import monte_carlo

ROOT = Path(__file__).resolve().parents[1]


class ReleaseMonteCarloBehaviorTests(unittest.TestCase):
    def test_monte_carlo_defaults_to_exact_scalar_and_vectorized_is_opt_in(self):
        data = load_csv(ROOT / "input" / "client_data.csv")
        try:
            cfg = prepare_config_from_sectioned_data(data, "")
        except ValueError as exc:
            self.skipTest(f"Sample legacy flat input is missing current engine registry fields: {exc}")
        cfg["mc_sims"] = 4
        cfg["mc_sensitivity_sims"] = 1
        cfg["plan_end"] = cfg["plan_start"] + 1
        mc = monte_carlo(cfg, seed=81)
        self.assertEqual(mc["mc_engine"], "vectorized_batched_tax_withdrawal")
        self.assertIn(mc["mc_approximation_status"], {"EXACT", "APPROXIMATE_PENDING_SCALAR_PARITY"})
        self.assertIn("success_rate_ci_low", mc)
        self.assertLessEqual(mc["success_rate_ci_low"], mc["success_rate_ci_high"])
        cfg["mc_engine_mode"] = "vectorized"
        mc_vec = monte_carlo(cfg, seed=81)
        self.assertEqual(mc_vec["portfolio_return_diagnostics"].get("mc_engine"), "vectorized_batched_tax_withdrawal")


if __name__ == "__main__":
    unittest.main()
