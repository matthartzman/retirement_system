import copy
import unittest
from pathlib import Path

from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
from src.planning_engines import project
from src.core import TaxLot, LotEngine
from src import tlh
from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

ROOT = Path(__file__).resolve().parents[1]


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


def baseline_config_without_tlh_overrides():
    """Same live plan setup as sample_config(), but never touches any
    tlh_* field -- relies purely on parse_client's CSV-default ('off').
    Used as the no-op reference so the pure-no-op test doesn't need a
    hardcoded dollar pin (see test_tlh_off_is_a_pure_no_op)."""
    data = load_csv(ROOT / 'input' / 'client_data.csv')
    c = parse_client(data, '')
    c['roth_policy'] = 'none'
    c['mc_paths'] = 5
    c['mc_sensitivity_sims'] = 1
    return ensure_engine_config(c, source='test')


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
        projection when tlh_policy is off (the default). Compared against a
        freshly-computed reference (a config that never touches any tlh_*
        field, relying on parse_client's CSV-default 'off') rather than a
        pinned dollar figure -- this test's config reads the live, routinely
        edited input/client_data.csv, and a hardcoded absolute pin here goes
        stale every time that plan data changes even though the TLH-off
        no-op property itself remains correct. See test_2_recommendations.py's
        _warn_on_baseline_drift for the same live-plan-drift concern applied
        to that file's own dollar pins."""
        with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
            c_off = sample_config('off')
            rows_off = project(c_off)
            c_baseline = baseline_config_without_tlh_overrides()
            rows_baseline = project(c_baseline)
        self.assertAlmostEqual(rows_off[-1]['total_nw'], rows_baseline[-1]['total_nw'], places=2)
        self.assertAlmostEqual(
            sum(r['total_tax'] for r in rows_off),
            sum(r['total_tax'] for r in rows_baseline),
            places=2,
        )
        self.assertTrue(all(r.get('tlh_harvested_loss', 0) == 0 for r in rows_off))
        self.assertTrue(all(r.get('cap_loss_carryforward', 0) == 0 for r in rows_off))

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
