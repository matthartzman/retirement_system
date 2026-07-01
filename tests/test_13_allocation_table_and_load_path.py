from __future__ import annotations

import unittest
from pathlib import Path

from src.config_backend import load_csv
from src.data_io import parse_client

ROOT = Path(__file__).resolve().parents[1]


class AllocationTableAndLoadPathTests(unittest.TestCase):
    def test_ui_first_allocation_table_has_target_and_existing_asset_source_dropdown(self):
        html = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('Asset-class allocation policy', html)
        self.assertIn('<th>Subcategory</th><th>Asset class</th><th>Selection</th><th>User Target %</th><th>Existing asset/source credited to this class</th>', html)
        self.assertIn('targetPctInput', html)
        self.assertIn('alternateAssetSourceOptions', html)
        self.assertIn('Guaranteed income + note receivable', html)
        self.assertIn('Home Equity', html)
        self.assertIn('Cash / checking', html)
        self.assertIn('assetCategory(asset)', html)

    def test_cash_target_and_existing_asset_credits_parse_from_first_table(self):
        cfg = parse_client(load_csv(ROOT / 'input' / 'client_data.csv'), '')
        self.assertAlmostEqual(cfg['cash_target_pct'], cfg['allocation_target_pct']['Cash'], places=8)
        self.assertIn(cfg['allocation_source_target_class']['Guaranteed income + note receivable'], {'Bonds', 'Short-Term Bonds', 'TIPS', 'Municipal Bonds'})
        self.assertEqual(cfg['allocation_source_target_class']['Home Equity'], 'REITs')
        self.assertTrue(cfg['allocation_coverage']['social_security_satisfies_fixed_income_target'])
        self.assertTrue(cfg['allocation_coverage']['pension_satisfies_fixed_income_target'])
        self.assertTrue(cfg['allocation_coverage']['annuities_satisfy_fixed_income_target'])
        self.assertTrue(cfg['allocation_coverage']['note_receivable_satisfies_fixed_income_target'])
        self.assertTrue(cfg['allocation_coverage']['home_equity_satisfies_reit_target'])

    def test_load_existing_plan_data_prompts_for_editable_server_path(self):
        html = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
        server = (ROOT / 'src' / 'server' / 'plan_routes.py').read_text(encoding='utf-8')
        self.assertIn('Import Plan Data CSV set', html)
        self.assertIn('pathModalInput', html)
        self.assertIn('Browse...', html)
        self.assertIn('plan-data/load-from-path', html)
        self.assertIn('Server-side path loading is disabled in local-only package', server)


if __name__ == '__main__':
    unittest.main()
