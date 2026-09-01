from __future__ import annotations

import inspect
import unittest
from pathlib import Path

from src.data_io import load_csv, parse_client
from src.planning_engines import aca_premium_tax_credit, monte_carlo, project, illinois_estate_tax
from src.reporting import sheets_strategy

ROOT = Path(__file__).resolve().parents[1]

from conftest import TEST_INPUT_DIR


class FullChecklistRemainingTests(unittest.TestCase):
    def _fast_cfg(self):
        cfg = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
        cfg["plan_end"] = cfg["plan_start"] + 2
        cfg["roth_policy"] = "none"
        cfg["mc_sims"] = 3
        cfg["mc_sensitivity_sims"] = 1
        return cfg

    def test_social_security_sheet_uses_a_genuine_coarse_then_refine_projection_sweep(self):
        src = inspect.getsource(sheets_strategy.build_sheet10)
        # #230, updated for item 2.3 (A4): the sheet no longer runs a flat
        # h_floor..70 x w_floor..70 double loop (up to 81 pairs) -- it scores
        # a coarse every-other-age grid first, then exhaustively refines the
        # full individual-age neighborhood around the coarse best. Both
        # bounds still clamp to each person's current age (never sweep a
        # claim age already passed) and cap at 70.
        self.assertIn("range(h_floor, 71, _COARSE_STEP)", src)
        self.assertIn("range(w_floor, 71, _COARSE_STEP)", src)
        self.assertIn("h_floor = max(62, min(70, h_cur_age))", src)
        self.assertIn("w_floor = max(62, min(70, w_cur_age))", src)
        # Every coarse AND refine candidate must still go through the real
        # per-pair evaluator (which calls the real projection engine below),
        # not a shortcut/approximation.
        self.assertIn("_coarse_pairs, _evaluate_pair", src)
        self.assertIn("_coarse_pairs + _refine_pairs,\n        _evaluate_pair,", src)
        # Wave 4.4 (system review 2026-08-04, `no-shared-scenario-runner`):
        # the per-pair deepcopy+override+project() call moved into the shared
        # planning_engines.run_scenario() helper, so the literal "project(c2)"
        # call no longer appears in this sheet's own source -- check that it
        # delegates to the shared runner instead.
        self.assertIn("_run_scenario(c, mutate=_mutate)", src)
        self.assertNotIn("[67, 68, 69, 70]", src)
        self.assertNotIn("claim at age 70 to maximize", src)

    def test_aca_ptc_recomputed_after_roth_conversion_magi(self):
        cfg = self._fast_cfg()
        cfg["plan_start"] = 2026
        cfg["plan_end"] = 2026
        cfg["h_ret_yr"] = 2026
        cfg["w_ret_yr"] = 2026
        cfg["h_dob_yr"] = 1962  # age 64 in 2026
        cfg["w_dob_yr"] = 1961  # age 65 in 2026, one bridge person only
        cfg["earned"] = 0
        cfg["biz_exp"] = 0
        cfg["wage_salary"] = 0
        cfg["scorp_salary"] = 0
        cfg["forced_roth"] = {2026: 250_000}
        cfg["roth_policy"] = "none"
        cfg["aca_ptc_enabled"] = True
        cfg["aca_enhanced_subsidies_through_year"] = 2026
        rows = project(cfg)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIn("aca_premium_tax_credit_pre_conversion", row)
        self.assertIn("aca_ptc_loss_from_conversion", row)
        self.assertGreaterEqual(row["aca_premium_tax_credit_pre_conversion"], row["aca_premium_tax_credit"])
        self.assertAlmostEqual(
            row["aca_ptc_loss_from_conversion"],
            row["aca_premium_tax_credit_pre_conversion"] - row["aca_premium_tax_credit"],
            delta=1.0,
        )
        self.assertGreater(row["total_spend"], 0)

    def test_monte_carlo_default_is_vectorized_with_exact_scalar_available(self):
        cfg = self._fast_cfg()
        mc = monte_carlo(cfg, seed=7)
        self.assertEqual(mc["mc_engine"], "vectorized_batched_tax_withdrawal")
        self.assertIn(mc["mc_approximation_status"], {"APPROXIMATE_PENDING_SCALAR_PARITY", "EXACT"})
        cfg["mc_engine_mode"] = "vectorized"
        mc_vec = monte_carlo(cfg, seed=7)
        self.assertEqual(mc_vec["mc_engine"], "vectorized_batched_tax_withdrawal")

    def test_aca_and_illinois_external_style_boundaries(self):
        c = {
            'aca_ptc_enabled': True,
            'aca_fpl_base': 20_000,
            'inf': 0.0,
            'plan_start': 2026,
            'aca_enhanced_subsidies_through_year': 2026,
            'aca_applicable_pct_cap': 0.085,
            'aca_benchmark_silver_premium': 24_000,
            'bridge_premium': 24_000,
            'aca_household_size': 2,
        }
        self.assertGreater(aca_premium_tax_credit(c, year=2026, magi=40_000, bridge_people=2), 20_000)
        c['aca_enhanced_subsidies_through_year'] = 2025
        self.assertEqual(aca_premium_tax_credit(c, year=2026, magi=90_000, bridge_people=2), 0.0)
        self.assertEqual(illinois_estate_tax(4_000_000, 4_000_000), 0.0)
        self.assertTrue(660_000 <= illinois_estate_tax(8_000_000, 4_000_000) <= 700_000)


if __name__ == "__main__":
    unittest.main()
