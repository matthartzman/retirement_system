from __future__ import annotations

import unittest
from pathlib import Path

from src.data_io import load_csv
from src.report_compute import prepare_config_from_sectioned_data
from src.planning_engines import monte_carlo

ROOT = Path(__file__).resolve().parents[1]

from conftest import TEST_INPUT_DIR


class ReleaseMonteCarloBehaviorTests(unittest.TestCase):
    def test_monte_carlo_defaults_to_vectorized_and_exact_scalar_is_opt_in(self):
        data = load_csv(TEST_INPUT_DIR / "client_data.csv")
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
        # Exact scalar is now the opt-in validation oracle, not the default.
        cfg["mc_engine_mode"] = "exact_scalar"
        mc_scalar = monte_carlo(cfg, seed=81)
        self.assertIn("exact_scalar", str(mc_scalar["mc_engine"]).lower())

    def test_exact_scalar_oracle_agrees_with_vectorized_default_within_tolerance(self):
        """Fidelity gate for the A1 default flip (system review, item 1.1).

        exact_scalar is no longer the shipped default, but it must still agree
        with vectorized closely enough to serve as a validation oracle. The
        golden master does not exercise this -- it already pins vectorized
        output -- so this is the only test that would catch the two engines
        silently diverging. Tolerance (1 percentage point on the headline
        success rate) was set by planner sign-off during the system review.
        """
        data = load_csv(TEST_INPUT_DIR / "client_data.csv")
        try:
            cfg = prepare_config_from_sectioned_data(data, "")
        except ValueError as exc:
            self.skipTest(f"Sample legacy flat input is missing current engine registry fields: {exc}")
        cfg["mc_sims"] = 200
        cfg["mc_sensitivity_sims"] = 1

        cfg_vec = dict(cfg)
        cfg_vec["mc_engine_mode"] = "vectorized"
        mc_vec = monte_carlo(cfg_vec, seed=2026)

        cfg_scalar = dict(cfg)
        cfg_scalar["mc_engine_mode"] = "exact_scalar"
        mc_scalar = monte_carlo(cfg_scalar, seed=2026)

        rate_vec = float(mc_vec["success_rate"])
        rate_scalar = float(mc_scalar["success_rate"])
        drift_pp = abs(rate_vec - rate_scalar) * 100.0
        self.assertLessEqual(
            drift_pp,
            1.0,
            f"vectorized success_rate={rate_vec:.4f} vs exact_scalar={rate_scalar:.4f} "
            f"({drift_pp:.2f} percentage points) exceeds the 1pp sign-off tolerance; "
            "investigate before relying on exact_scalar as a validation oracle.",
        )

    def test_plan_data_without_an_engine_row_resolves_to_vectorized(self):
        """A plan whose CSV omits (or blanks) mc_engine_mode gets vectorized."""
        from src.data_io import _mc_engine_mode_from_plan_data

        self.assertEqual(_mc_engine_mode_from_plan_data({}), "vectorized")
        self.assertEqual(
            _mc_engine_mode_from_plan_data(
                {"Model Constants": {"Monte Carlo": {"mc_engine_mode": "  "}}}
            ),
            "vectorized",
        )
        self.assertEqual(
            _mc_engine_mode_from_plan_data(
                {"Model Constants": {"Monte Carlo": {"mc_engine_mode": "advanced_exact_scalar"}}}
            ),
            "exact_scalar",
        )


if __name__ == "__main__":
    unittest.main()
