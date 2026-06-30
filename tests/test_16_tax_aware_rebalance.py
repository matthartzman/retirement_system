from __future__ import annotations

import unittest
from pathlib import Path

from src.core import TaxLot
from src.reporting import sheets_summary as ss

ROOT = Path(__file__).resolve().parents[1]


class TaxAwareRebalanceTests(unittest.TestCase):
    def test_taxable_sale_estimator_harvests_losses_before_gains(self):
        cfg = {
            'plan_start': 2026,
            'state': 'IL',
            'model_niit': True,
            'roth_target_bracket_rate': 0.24,
            'lots_by_account': {
                'Taxable': {
                    'ABC': [
                        TaxLot('ABC', 10, 1200, '2024-01-01'),  # loss at $100
                        TaxLot('ABC', 10, 500, '2026-01-01'),   # short-term gain
                    ]
                }
            },
        }
        est = ss._estimate_taxable_sale(cfg, 'Taxable', 'ABC', 500, 100)
        self.assertLess(est['tax_cost'], 0)
        self.assertLess(est['lt_loss'], 0)
        self.assertIn('Tax-loss-harvest candidate', est['note'])

    def test_taxable_sell_decision_defers_high_drag_short_term_gain(self):
        cfg = {
            'plan_start': 2026,
            'state': 'IL',
            'model_niit': True,
            'roth_target_bracket_rate': 0.24,
            'rebalance_max_tax_drag_pct': 0.015,
            'rebalance_force_taxable_sell_drift_pct': 0.08,
            'lots_by_account': {
                'Taxable': {'XYZ': [TaxLot('XYZ', 10, 500, '2026-01-01')]}
            },
        }
        allowed, est, note = ss._taxable_sell_decision(cfg, 'Taxable', 'XYZ', 500, 100, 0.03, 'taxable')
        self.assertFalse(allowed)
        self.assertGreater(est['st_gain'], 0)
        self.assertIn('Deferred: estimated tax drag', note)

    def test_workbook_trade_section_contains_tax_optimizer_disclosures(self):
        source = (ROOT / 'src' / 'reporting' / 'sheets_summary.py').read_text(encoding='utf-8')
        self.assertIn('account-level tax optimization', source)
        self.assertIn('Est. Tax Cost', source)
        self.assertIn('Tax-aware deferred taxable sales', source)
        self.assertIn('wash-sale', source.lower())
        self.assertIn('short-term vs long-term gains', source)

    def test_rebalancing_trades_are_grouped_by_account_subsections(self):
        source = (ROOT / 'src' / 'reporting' / 'sheets_summary.py').read_text(encoding='utf-8')
        self.assertIn('grouped by account subsections', source)
        self.assertIn('trades_by_acct', source)
        self.assertIn('Account-level subtotal; positive adds to account cash, negative deploys existing account cash.', source)
        self.assertIn('Positive = cash added; negative = existing account cash deployed. No cross-account transfers are assumed.', source)


    def test_cash_movement_rows_make_cash_deployment_visible(self):
        trades = [
            {'acct': 'Taxable', 'sym': 'VOO', 'action': 'BUY', 'amount': 750, 'bucket': 'US Large Cap'},
            {'acct': 'Taxable', 'sym': 'BND', 'action': 'SELL', 'amount': 250, 'bucket': 'Bonds'},
        ]
        out = ss._append_cash_movement_rows(trades, {'Taxable': {'CASH': 1000}}, {'Taxable': 'taxable'}, 100)
        cash_rows = [t for t in out if t.get('sym') == 'CASH' and t.get('action') == 'USE CASH']
        self.assertEqual(len(cash_rows), 1)
        self.assertEqual(cash_rows[0]['amount'], 500)
        self.assertIn('Total Portfolio Mix', cash_rows[0]['note'])

    def test_total_portfolio_mix_includes_after_trade_columns(self):
        source = (ROOT / 'src' / 'reporting' / 'sheets_summary.py').read_text(encoding='utf-8')
        self.assertIn('After Trades Value', source)
        self.assertIn('After Trades %', source)
        self.assertIn('After Trade Status', source)
        self.assertIn('Backfill the top Total Portfolio Mix table', source)
        self.assertIn('write_cell(ws, _row, 4, _after_val', source)


class GlobalTaxLocationOptimizerTests(unittest.TestCase):
    def test_rebalance_settings_expose_risk_controls(self):
        cfg = {
            'trade_optimizer_mode': 'GLOBAL_TAX_AWARE',
            'rebalance_max_turnover_pct': 0.10,
            'rebalance_wash_sale_policy': 'STRICT_AVOID',
            'rebalance_allow_taxable_gain_sales': 'WITHIN_BUDGET',
            'rebalance_asset_location_strength': 'STRONG',
        }
        settings = ss._rebalance_settings(cfg)
        self.assertEqual(settings['mode'], 'GLOBAL_TAX_AWARE')
        self.assertEqual(settings['wash_sale_policy'], 'STRICT_AVOID')
        self.assertEqual(settings['taxable_gain_policy'], 'WITHIN_BUDGET')
        self.assertEqual(settings['asset_location_strength'], 'STRONG')
        self.assertAlmostEqual(settings['max_turnover_pct'], 0.10)


    def test_global_optimizer_respects_account_cash_reserve_when_funding_buys(self):
        old_fetch = ss.fetch_price
        old_diag = ss.pricing_diagnostics
        old_price_cache = dict(ss.PRICE_CACHE)
        try:
            ss.fetch_price = lambda sym, url_template='': 1.0 if sym == 'CASH' else 100.0
            ss.pricing_diagnostics = lambda: {'pricing_mode': 'OFFLINE'}
            ss.PRICE_CACHE.clear()
            ss.PRICE_CACHE.update({'VOO': 100.0})
            cfg = {
                'plan_start': 2026,
                'trade_optimizer_mode': 'GLOBAL_TAX_AWARE',
                'rebalance_min_trade_amount': 100,
                'rebalance_max_turnover_pct': 1.0,
                'rebalance_turnover_penalty_per_dollar': 0.0,
                'rebalance_asset_location_strength': 'BALANCED',
                'rebalance_max_account_single_asset_pct': 1.0,
                'rebalance_taxable_gain_budget_annual': 999999,
                'cash_target_pct': 0.50,
            }
            trades, deferred, diagnostics = ss._build_global_tax_aware_rebalance_trades(
                cfg,
                {'Taxable': {'CASH': 1000}},
                {'CASH': 'Cash', 'VOO': 'US Large Cap'},
                {'US Large Cap': ['VOO']},
                {'US Large Cap': 1.0, 'Cash': 0.0},
                {'Cash': 1000},
                1000,
                {'Taxable': 'taxable'},
                {'taxable': ['VOO']},
                [],
            )
            buy_amount = sum(t['amount'] for t in trades if t.get('action') == 'BUY')
            self.assertLessEqual(buy_amount, 500)
            self.assertTrue(any('cash deployed' in row[2].lower() for row in diagnostics))
        finally:
            ss.fetch_price = old_fetch
            ss.pricing_diagnostics = old_diag
            ss.PRICE_CACHE.clear()
            ss.PRICE_CACHE.update(old_price_cache)

    def test_global_optimizer_can_swap_asset_location_without_changing_household_target(self):
        old_fetch = ss.fetch_price
        old_diag = ss.pricing_diagnostics
        old_price_cache = dict(ss.PRICE_CACHE)
        try:
            ss.fetch_price = lambda sym, url_template='': 100.0
            ss.pricing_diagnostics = lambda: {'pricing_mode': 'OFFLINE'}
            ss.PRICE_CACHE.clear()
            ss.PRICE_CACHE.update({'VOO': 100.0, 'BND': 100.0})
            cfg = {
                'plan_start': 2026,
                'trade_optimizer_mode': 'GLOBAL_TAX_AWARE',
                'rebalance_min_trade_amount': 100,
                'rebalance_max_turnover_pct': 1.0,
                'rebalance_turnover_penalty_per_dollar': 0.0,
                'rebalance_asset_location_strength': 'STRONG',
                'rebalance_max_account_single_asset_pct': 1.0,
                'rebalance_max_roth_high_growth_pct': 1.0,
                'rebalance_max_pre_tax_fixed_income_pct': 1.0,
                'rebalance_taxable_gain_budget_annual': 999999,
                'cash_target_pct': 0.0,
            }
            trades, deferred, diagnostics = ss._build_global_tax_aware_rebalance_trades(
                cfg,
                {'TraditionalIRA': {'VOO': 10}, 'RothIRA': {'BND': 10}},
                {'VOO': 'US Large Cap', 'BND': 'Bonds'},
                {'US Large Cap': ['VOO'], 'Bonds': ['BND']},
                {'US Large Cap': 0.50, 'Bonds': 0.50},
                {'US Large Cap': 1000, 'Bonds': 1000},
                2000,
                {'TraditionalIRA': 'pre_tax', 'RothIRA': 'roth'},
                {'pre_tax': ['BND', 'VOO'], 'roth': ['VOO', 'BND'], 'taxable': ['VOO', 'BND']},
                [],
            )
            self.assertFalse(deferred)
            actions = {(t['acct'], t['sym'], t['action']) for t in trades}
            self.assertIn(('TraditionalIRA', 'VOO', 'SELL'), actions)
            self.assertIn(('TraditionalIRA', 'BND', 'BUY'), actions)
            self.assertIn(('RothIRA', 'BND', 'SELL'), actions)
            self.assertIn(('RothIRA', 'VOO', 'BUY'), actions)
            self.assertTrue(any('Trade optimizer mode' in row[0] for row in diagnostics))
        finally:
            ss.fetch_price = old_fetch
            ss.pricing_diagnostics = old_diag
            ss.PRICE_CACHE.clear()
            ss.PRICE_CACHE.update(old_price_cache)


if __name__ == '__main__':
    unittest.main()
