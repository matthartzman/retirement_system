import random
import unittest
from pathlib import Path
from src.data_io import load_csv, parse_client
from src.optimization import ASSET_CLASSES, apply_capital_market_config
from src.planning_engines import _run_one_mc_path, _success_rate_ci, monte_carlo
from src.secrets_store import require_secure_master_key

ROOT = Path(__file__).resolve().parents[1]


def fast_config():
    c = parse_client(load_csv(ROOT / "input" / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["plan_end"] = min(int(c["plan_end"]), int(c["plan_start"]) + 1)
    c["mc_sims"] = 4
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_prob"] = 1.0
    c["mc_wellness_mean"] = 1000.0
    return c


class RoadmapCompletionTests(unittest.TestCase):
    def test_requirements_manifest_lists_runtime_dependencies(self):
        text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        for package in ["numpy", "openpyxl", "reportlab", "matplotlib", "pillow", "cryptography", "pywebview"]:
            self.assertIn(package, text)
        self.assertNotIn("Flask", text)
        self.assertNotIn("Werkzeug", text)

    def test_local_secret_store_is_local_only_compatibility_layer(self):
        from src.secrets_store import encryption_status
        status = encryption_status()
        self.assertEqual(status["mode"], "local-only")
        self.assertTrue(status["configured"])
        self.assertTrue(require_secure_master_key("LOCAL"))

    def test_cma_reference_csv_is_authoritative(self):
        diag = apply_capital_market_config({"capital_market_config": {"horizon_years": 30, "preset": "BASELINE"}})
        self.assertTrue(diag["shipped_reference_data_loaded"])
        self.assertLess(ASSET_CLASSES["US Large Cap"]["ret"], 0.08)

    def test_monte_carlo_surfaces_ci_inflation_health_and_asset_model(self):
        c = fast_config()
        mc = monte_carlo(c, n_sims=4, seed=11)
        self.assertIn("success_rate_ci_low", mc)
        self.assertIn("success_rate_ci_high", mc)
        self.assertLessEqual(mc["success_rate_ci_low"], mc["success_rate_ci_high"])
        self.assertIn(mc["portfolio_return_model"], {"asset_class_covariance", "single_blended_mu_sigma"})
        self.assertIn("sampled_mean_inflation", mc)
        self.assertGreaterEqual(mc["sampled_wellness_shock_count"], 1)
        self.assertEqual(mc["sensitivity_sims"], 1)

    def test_path_level_wellness_shock_feeds_projection_rows(self):
        c = fast_config()
        rows, _years, _returns, _diag, paths = _run_one_mc_path(c, random.Random(123), 0.06, 0.12)
        self.assertGreaterEqual(sum(paths["wellness_shock_by_year"].values()), 0.0)
        self.assertIn("wellness_shock_yr", rows[0])

    def test_success_rate_ci_is_bounded(self):
        lo, hi = _success_rate_ci(8, 10)
        self.assertGreaterEqual(lo, 0.0)
        self.assertLessEqual(hi, 1.0)
        self.assertLess(lo, hi)


if __name__ == "__main__":
    unittest.main()
