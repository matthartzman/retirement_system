from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from src import allocation_policy as ap
from src import optimization as opt
from src.data_io import load_csv, parse_client
from src.market_data import MarketDataProvider

ROOT = Path(__file__).resolve().parents[1]


class CoveredAllocationTargetsTests(unittest.TestCase):
    def _config(self):
        return parse_client(load_csv(ROOT / 'input' / 'client_data.csv'), '')

    def test_selected_user_targets_exclude_fully_covered_fixed_income_from_active_liquid_recommendation(self):
        cfg = self._config()
        out = opt.compute_optimal_allocation(cfg)
        liquid = out.get('liquid_targets') or {}
        self.assertAlmostEqual(sum(liquid.values()), 1.0, places=8)
        self.assertNotIn('Bonds', liquid)
        self.assertNotIn('Short-Term Bonds', liquid)
        coverage = out['diagnostics'].get('coverage_adjustments') or {}
        self.assertIn('Bonds', coverage)
        self.assertIn('Short-Term Bonds', coverage)
        self.assertTrue(coverage['Bonds']['fully_covered'])
        self.assertTrue(coverage['Short-Term Bonds']['fully_covered'])

    def test_user_targets_exclude_fully_covered_alternate_classes_from_liquid_total(self):
        cfg = self._config()
        out = opt.compute_optimal_allocation(cfg, force_mode=ap.ALLOCATION_MODE_USER)
        liquid = out.get('liquid_targets') or {}
        self.assertAlmostEqual(sum(liquid.values()), 1.0, places=8)
        self.assertNotIn('Bonds', liquid)
        self.assertNotIn('Short-Term Bonds', liquid)
        self.assertAlmostEqual(out['total_targets'].get('Bonds', 0.0), 0.15, places=8)
        self.assertAlmostEqual(out['total_targets'].get('Short-Term Bonds', 0.0), 0.05, places=8)
        coverage = out['diagnostics'].get('coverage_adjustments') or {}
        self.assertIn('Bonds', coverage)
        self.assertIn('Short-Term Bonds', coverage)
        self.assertTrue(coverage['Bonds']['fully_covered'])
        self.assertTrue(coverage['Short-Term Bonds']['fully_covered'])
        self.assertEqual(coverage['Bonds']['coverage_scope'], 'fixed_income_sleeve')
        self.assertEqual(coverage['Short-Term Bonds']['coverage_scope'], 'fixed_income_sleeve')
        self.assertAlmostEqual(coverage['Bonds']['liquid_target_pct'], 0.0, places=8)
        self.assertAlmostEqual(coverage['Short-Term Bonds']['liquid_target_pct'], 0.0, places=8)

    def test_optimizer_excludes_home_equity_covered_reits_from_liquid_recommendation(self):
        cfg = self._config()
        cfg['allocation_selection_mode'] = ap.ALLOCATION_MODE_OPTIMIZER
        out = opt.compute_optimal_allocation(cfg)
        liquid = out.get('liquid_targets') or {}
        self.assertAlmostEqual(sum(liquid.values()), 1.0, places=8)
        self.assertNotIn('REITs', liquid)
        covered = out['diagnostics'].get('covered_existing_asset_classes') or []
        self.assertIn('REITs', covered)
        self.assertIn('Short-Term Bonds', covered)
        self.assertIn('TIPS', covered)
        self.assertIn('Municipal Bonds', covered)
        self.assertGreater(out['total_targets'].get('REITs', 0.0), 0.0)

    def test_excluded_classes_remain_out_after_coverage_normalization(self):
        cfg = self._config()
        cfg['asset_class_selection_action'] = dict(cfg.get('asset_class_selection_action') or {})
        cfg['asset_class_selection_action']['US Mid Cap'] = ap.SELECTION_EXCLUDE
        cfg['asset_class_enabled'] = dict(cfg.get('asset_class_enabled') or {})
        cfg['asset_class_enabled']['US Mid Cap'] = False
        out = opt.compute_optimal_allocation(cfg, force_mode=ap.ALLOCATION_MODE_USER)
        self.assertNotIn('US Mid Cap', out.get('liquid_targets') or {})
        self.assertAlmostEqual(sum((out.get('liquid_targets') or {}).values()), 1.0, places=8)


    def test_explicit_short_term_bond_alternate_is_removed_from_optimizer_liquid_targets(self):
        cfg = self._config()
        cfg['allocation_selection_mode'] = ap.ALLOCATION_MODE_OPTIMIZER
        cfg['asset_class_selection_action'] = dict(cfg.get('asset_class_selection_action') or {})
        cfg['asset_class_alternate_first'] = dict(cfg.get('asset_class_alternate_first') or {})
        cfg['asset_class_selection_action']['Short-Term Bonds'] = ap.SELECTION_ALTERNATE_FIRST
        cfg['asset_class_alternate_first']['Short-Term Bonds'] = 'Guaranteed income + note receivable'
        out = opt.compute_optimal_allocation(cfg)
        self.assertNotIn('Short-Term Bonds', out.get('liquid_targets') or {})
        self.assertIn('Short-Term Bonds', out['diagnostics'].get('covered_existing_asset_classes') or [])
        self.assertAlmostEqual(sum((out.get('liquid_targets') or {}).values()), 1.0, places=8)

    def test_workbook_summary_explains_covered_initial_targets_and_no_under_for_no_target_home_equity(self):
        source = (ROOT / 'src' / 'reporting' / 'sheets_summary.py').read_text(encoding='utf-8')
        self.assertIn('Orange italic percentages show the initial target', source)
        self.assertIn('excluded from the 100% liquid target completeness', source)
        self.assertIn('Shown for context; no liquid target', source)

    def test_rebalancing_collapses_unrepresented_sleeves_to_one_etf_per_account(self):
        source = (ROOT / 'src' / 'reporting' / 'sheets_summary.py').read_text(encoding='utf-8')
        self.assertIn('single ETF per account', source)
        self.assertIn('_single_etf_for_unrepresented_bucket', source)
        self.assertIn('single ETF selected for this account', source)
        self.assertNotIn('alternatives: {", ".join(_alts)}', source)


    def test_workbook_notes_selected_allocation_recommendation_source(self):
        source = (ROOT / 'src' / 'reporting' / 'sheets_summary.py').read_text(encoding='utf-8')
        self.assertIn('Asset Allocation Recommendation Source', source)
        self.assertIn('Recommendation Source', source)
        self.assertIn('User-defined allocation', source)
        self.assertIn('Optimizer-defined allocation', source)
        self.assertIn('Asset allocation recommendation source:', source)

    def test_market_data_summary_reports_cache_as_of_timestamp(self):
        with tempfile.TemporaryDirectory() as td:
            provider = MarketDataProvider(cache_path=Path(td) / 'cache.json', diagnostics_path=Path(td) / 'diag.json')
            provider.configure_holdings_pricing(mode='CACHE', cache_hours=24)
            provider.cache['VTI'] = {
                'symbol': 'VTI',
                'price': 100.0,
                'source': 'yahoo',
                'timestamp_iso': '2026-06-09T12:34:56+00:00',
                'timestamp_epoch': 1781008496,
            }
            provider.sources['VTI'] = 'fresh_cache_24h_from_yahoo'
            summary = provider.pricing_source_summary()
            self.assertEqual(summary['category'], 'CACHE')
            self.assertIn('2026-06-09T12:34:56+00:00', summary['cache_as_of_utc'])
            self.assertRegex(summary['cache_as_of_local'], r'\d{2}/\d{2}/\d{4} \d{2}:\d{2} (AM|PM)')
            self.assertIn(summary['cache_as_of_local'], summary['note'])
            self.assertNotIn('T12:34:56+00:00', summary['note'])
            self.assertRegex(summary['note'], r'\d{2}:\d{2} (AM|PM)')
            self.assertIn('Cached quotes were used as of', summary['note'])

    def test_workbook_notes_pricing_source_and_mode(self):
        source = (ROOT / 'src' / 'reporting' / 'sheets_summary.py').read_text(encoding='utf-8')
        self.assertIn('Workbook Pricing Source', source)
        self.assertIn('Workbook pricing source:', source)
        self.assertIn('CACHE — as of', source)
        self.assertIn('LIVE — provider quote(s) used during workbook build', source)
        self.assertIn('OFFLINE — cost-basis/cash fallback pricing', source)
        builder = (ROOT / 'src' / 'reporting' / 'workbook_builder.py').read_text(encoding='utf-8')
        self.assertIn('write_pricing_diagnostics', builder)


if __name__ == '__main__':
    unittest.main()
