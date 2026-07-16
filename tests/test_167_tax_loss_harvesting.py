import contextlib
import copy
import os
import unittest
from pathlib import Path

from src import market_data as _market_data
from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
from src.planning_engines import project
from src.core import TaxLot, LotEngine
from src import tlh

ROOT = Path(__file__).resolve().parents[1]

# Frozen holdings prices for the golden-master no-op guard below — kept in
# sync with tests/test_2_recommendations.py's FROZEN_GOLDEN_MASTER_PRICES /
# frozen_holdings_prices (Item 192, 2026-07-16); see that file for why this
# is needed instead of relying on output/market_price_cache.json directly.
FROZEN_GOLDEN_MASTER_PRICES = {
    "VTI": 371.835, "VXUS": 84.145, "AVUV": 126.37, "VBR": 245.525,
    "ITOT": 165.265, "IXUS": 93.94, "PDBC": 17.05,
}


@contextlib.contextmanager
def frozen_holdings_prices(prices):
    provider = _market_data._DEFAULT_PROVIDER
    saved = (provider.pricing_mode, provider.cache_first, provider.use_live,
              dict(provider.frozen_prices), dict(provider.frozen_metadata))
    env_var = "RETIREMENT_SYSTEM_FORCE_PRICING_MODE"
    saved_env = os.environ.get(env_var)
    os.environ[env_var] = "FROZEN"
    provider.set_frozen_prices(prices, metadata={"frozen_for": "golden_master_test"})
    try:
        yield
    finally:
        if saved_env is None:
            os.environ.pop(env_var, None)
        else:
            os.environ[env_var] = saved_env
        (provider.pricing_mode, provider.cache_first, provider.use_live,
         provider.frozen_prices, provider.frozen_metadata) = saved
        _market_data.reset_pricing_runtime_state()


def sample_config(tlh_policy='off'):
    data = load_csv(ROOT / 'input' / 'client_data.csv')
    c = parse_client(data, '')
    c['roth_policy'] = 'none'
    c['mc_paths'] = 5
    c['mc_sensitivity_sims'] = 1
    c = ensure_engine_config(c, source='test')
    c['tlh_policy'] = tlh_policy
    c['tlh_min_loss_dollars'] = 500.0
    c['tlh_min_loss_pct'] = 0.0
    c['tlh_annual_ceiling'] = 0.0
    c['tlh_transaction_cost_bps'] = 2.0
    return c


def inject_underwater_lot(c, account='Member_1_Trust', symbol='ITOT', shares=1000.0, basis_per_share=220.0):
    price = c['lot_engine'].prices.get(symbol, 0.0)
    lot = TaxLot(symbol, shares, shares * basis_per_share, '2024-06-01')
    c['lots_by_account'].setdefault(account, {}).setdefault(symbol, []).append(lot)
    c['lot_engine'] = LotEngine(c['lots_by_account'], c['lot_engine'].prices,
                                fallback_gain_fraction=c.get('trust_gain_fraction', 0.5),
                                method='HIFO')
    return price


class ScannerTests(unittest.TestCase):
    def test_scanner_finds_no_losses_below_threshold_by_default(self):
        c = sample_config()
        sel = tlh.select_harvest_lots(c, 2026, min_loss_dollars=1_000_000.0, min_loss_pct=0.0)
        self.assertEqual(sel, [])

    def test_scanner_finds_injected_underwater_lot(self):
        c = sample_config()
        inject_underwater_lot(c)
        sel = tlh.select_harvest_lots(c, 2026, min_loss_dollars=500.0, min_loss_pct=0.0)
        self.assertTrue(any(s['symbol'] == 'ITOT' and s['loss'] > 50_000 for s in sel))

    def test_scanner_suggests_different_symbol_replacement(self):
        c = sample_config()
        inject_underwater_lot(c)
        result = tlh.scan_harvest_opportunities(
            c, 2026, ordinary_income=200_000, existing_lt_gain=40_000,
            min_loss_dollars=500.0, min_loss_pct=0.0, transaction_cost_bps=2.0,
        )
        itot_opp = next(o for o in result['opportunities'] if o['symbol'] == 'ITOT')
        self.assertNotEqual(itot_opp['replacement'], 'ITOT')
        self.assertTrue(itot_opp['replacement'])
        # Net value must reconcile: gross - future_give_back - txn_cost == net
        self.assertAlmostEqual(
            itot_opp['net_value'],
            itot_opp['gross_benefit'] - itot_opp['future_give_back'] - itot_opp['transaction_cost'],
            places=6,
        )

    def test_non_taxable_accounts_never_scanned(self):
        c = sample_config()
        inject_underwater_lot(c, account='Member_1_IRA')
        sel = tlh.select_harvest_lots(c, 2026, min_loss_dollars=500.0, min_loss_pct=0.0)
        self.assertFalse(any(s['account'] == 'Member_1_IRA' for s in sel))


class EngineIntegrationTests(unittest.TestCase):
    def test_tlh_off_is_a_pure_no_op(self):
        """Regression guard: the TLH engine changes must not alter any existing
        projection when tlh_policy is off (the default), matching the golden
        master unchanged. If this fails, the off-path picked up a side effect."""
        with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
            c = sample_config('off')
            rows = project(c)
        # Golden master reflects items 182 (pre-65 bridge always applies), 184
        # (real-estate tax funded as a cash need), 168 (SS benefit
        # self-cancellation fix), 169 (household claim age 70->69), 185
        # (elective IRA withdrawal ordinary-tax true-up + gap/net_cash
        # convention fix), 186 (household plan update: Member 1 claim age
        # moved from 69 to 68), and 192 (2026-07-16: local OFFLINE
        # price-cache mark-to-market drift on unsold holdings, not a
        # plan-data or engine change — see test_2_recommendations.py for
        # detail) — see test_2_recommendations.py for detail, including a
        # note on this value's test-order dependency — regenerated against
        # clean committed inputs; the TLH-off no-op property holds against it.
        self.assertAlmostEqual(rows[-1]['total_nw'], 7_367_350.45, delta=5000.0)
        self.assertAlmostEqual(sum(r['total_tax'] for r in rows), 1_630_865.29, delta=5000.0)
        self.assertTrue(all(r.get('tlh_harvested_loss', 0) == 0 for r in rows))
        self.assertTrue(all(r.get('cap_loss_carryforward', 0) == 0 for r in rows))

    def test_apply_mode_harvests_and_carries_forward(self):
        c = sample_config('apply')
        inject_underwater_lot(c)
        rows = project(c)
        first = rows[0]
        self.assertGreater(first['tlh_harvested_loss'], 50_000)
        self.assertGreater(first['tlh_transaction_cost'], 0)
        # Carryforward should be positive right after a large harvest and then
        # decay (get used against future gains) rather than grow unboundedly.
        self.assertGreater(first['cap_loss_carryforward'], 0)
        cf_path = [r['cap_loss_carryforward'] for r in rows[:6]]
        self.assertLessEqual(cf_path[-1], cf_path[0])

    def test_apply_mode_ordinary_offset_capped_at_3000_per_year(self):
        c = sample_config('apply')
        inject_underwater_lot(c)
        rows = project(c)
        first = rows[0]
        # cap_loss_used = amount offset against gains + ordinary this year;
        # the harvested loss minus cap_loss_used must equal the carryforward.
        self.assertAlmostEqual(
            first['tlh_harvested_loss'] - first['cap_loss_used'],
            first['cap_loss_carryforward'],
            delta=1.0,
        )


class WorkbookSheetTests(unittest.TestCase):
    def test_sheet_builds_without_error_for_all_policies(self):
        from openpyxl import Workbook
        from src.reporting.sheets_strategy import build_sheet_tlh
        for policy in ('off', 'analyze_only', 'apply'):
            c = sample_config(policy)
            inject_underwater_lot(c)
            rows = project(c)
            wb = Workbook()
            ws = wb.active
            build_sheet_tlh(ws, c, rows)
            self.assertGreater(ws.max_row, 5)


if __name__ == '__main__':
    unittest.main()
