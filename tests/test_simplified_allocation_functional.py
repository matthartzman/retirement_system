from __future__ import annotations

import unittest
from pathlib import Path

from src import allocation_policy as ap
from src.data_io import load_csv, parse_client
from src.optimization import compute_optimal_allocation

ROOT = Path(__file__).resolve().parents[1]

from _decomp_dashboard import dashboard_function_source, dashboard_js_text
from conftest import TEST_INPUT_DIR


class SimplifiedAllocationTests(unittest.TestCase):
    def test_default_target_mix_includes_cash_and_totals_100(self):
        self.assertIn('Cash', ap.DEFAULT_ALLOCATION_TARGETS)
        self.assertAlmostEqual(sum(ap.DEFAULT_ALLOCATION_TARGETS.values()), 1.0, places=8)
        for cls, examples in ap.ETF_CANDIDATES.items():
            self.assertGreaterEqual(len(examples), 3, cls)

    def test_client_policy_target_pct_drives_recommended_allocation(self):
        data = load_csv(TEST_INPUT_DIR / 'client_data.csv')
        c = parse_client(data, '')
        self.assertAlmostEqual(c['allocation_target_sum'], 1.0, places=8)
        opt = compute_optimal_allocation(c)
        self.assertEqual(opt['diagnostics']['allocation_policy_mode'], 'user_target_pct')
        self.assertAlmostEqual(sum(opt['liquid_targets'].values()), 1.0, places=8)
        self.assertAlmostEqual(opt['liquid_targets']['Cash'], 0.0625, places=8)
        self.assertAlmostEqual(opt['liquid_targets']['US Large Cap'], 0.4375, places=4)

    def test_ui_enforces_allocation_total_and_does_not_list_loaded_files(self):
        js = dashboard_js_text()
        html = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('allocationTargetsValid', js)
        self.assertIn('Active included/alternate target rows must total 100.00%', js)
        self.assertIn('id="pathModalInput"', html)
        manifest_fn = dashboard_function_source('showPlanDataFileManifest', js)
        self.assertNotIn('getElementById', manifest_fn)
        self.assertNotIn('These are the filenames found in the selected folder', js)
        self.assertNotIn('These are the filenames found in the selected folder', html)


if __name__ == '__main__':
    unittest.main()
