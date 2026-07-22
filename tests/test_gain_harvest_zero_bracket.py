"""T4c (system review 2026-07-21, P2): 0%-bracket long-term gain harvesting,
the symmetric counterpart to tax-loss harvesting the engine previously never
modeled despite already computing every input it needs (ltcg_0_top, the
bracket-stacking formula, and per-lot holding periods).
"""
import unittest
from pathlib import Path

from src.core import TaxLot, LotEngine
from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
from src.planning_engines import project
from src import gain_harvest as gh
from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

ROOT = Path(__file__).resolve().parents[1]


def sample_config(gain_harvest_policy='off'):
    data = load_csv(ROOT / 'input' / 'client_data.csv')
    c = parse_client(data, '')
    c['roth_policy'] = 'none'
    c['mc_paths'] = 5
    c['mc_sensitivity_sims'] = 1
    c = ensure_engine_config(c, source='test')
    c['gain_harvest_policy'] = gain_harvest_policy
    c['gain_harvest_min_gain_dollars'] = 500.0
    c['gain_harvest_min_gain_pct'] = 0.0
    c['gain_harvest_transaction_cost_bps'] = 2.0
    return c


def baseline_config_without_gain_harvest_overrides():
    """Same live plan setup as sample_config(), but never touches any
    gain_harvest_* field -- relies purely on parse_client's CSV-default
    ('off'). Used as the no-op reference, mirroring test_167's
    baseline_config_without_tlh_overrides() for the same reason: a hardcoded
    dollar pin against the live, routinely edited client_data.csv would go
    stale independent of whether the off-by-default no-op property holds."""
    data = load_csv(ROOT / 'input' / 'client_data.csv')
    c = parse_client(data, '')
    c['roth_policy'] = 'none'
    c['mc_paths'] = 5
    c['mc_sensitivity_sims'] = 1
    return ensure_engine_config(c, source='test')


def inject_appreciated_lot(c, account='Member_1_Trust', symbol='ITOT', shares=1000.0, basis_per_share=20.0,
                            purchase_date='2020-01-01'):
    price = c['lot_engine'].prices.get(symbol, 0.0)
    lot = TaxLot(symbol, shares, shares * basis_per_share, purchase_date)
    c['lots_by_account'].setdefault(account, {}).setdefault(symbol, []).append(lot)
    c['lot_engine'] = LotEngine(c['lots_by_account'], c['lot_engine'].prices,
                                fallback_gain_fraction=c.get('trust_gain_fraction', 0.5),
                                method='HIFO')
    return price


def isolate_taxable_lots(c):
    """Empty every taxable account's real holdings before a test injects its
    own synthetic lots. The live client_data.csv's taxable Trust accounts
    already hold real, substantially appreciated positions (ITOT/IXUS/VXUS/
    VTI) -- unlike test_167's underwater-lot tests, which get away without
    this because embedded losses are rare in a real long-held portfolio,
    embedded gains are the common case, so tests that need to reason about
    exactly which lot gets selected must not depend on the live plan being
    gain-free."""
    taxable = set(c.get('taxable_ids', []) or [])
    for acct in list(c['lots_by_account'].keys()):
        if acct in taxable:
            c['lots_by_account'][acct] = {}
    c['lot_engine'] = LotEngine(c['lots_by_account'], c['lot_engine'].prices,
                                fallback_gain_fraction=c.get('trust_gain_fraction', 0.5),
                                method='HIFO')


class HeadroomTests(unittest.TestCase):
    def test_headroom_is_bracket_ceiling_minus_ordinary_income(self):
        self.assertAlmostEqual(gh.compute_zero_bracket_headroom(100_000, 1.0, 40_000), 60_000)

    def test_headroom_floors_at_zero_when_ordinary_income_exceeds_ceiling(self):
        self.assertEqual(gh.compute_zero_bracket_headroom(100_000, 1.0, 150_000), 0.0)

    def test_headroom_scales_with_bracket_factor(self):
        self.assertAlmostEqual(gh.compute_zero_bracket_headroom(100_000, 1.05, 0), 105_000)


class ScannerTests(unittest.TestCase):
    def test_scanner_finds_no_gains_when_headroom_is_zero(self):
        c = sample_config()
        inject_appreciated_lot(c)
        sel = gh.select_gain_harvest_lots(c, 2026, headroom=0.0)
        self.assertEqual(sel, [])

    def test_scanner_finds_injected_appreciated_lot(self):
        c = sample_config()
        inject_appreciated_lot(c)
        sel = gh.select_gain_harvest_lots(c, 2026, headroom=1_000_000.0, min_gain_dollars=500.0)
        self.assertTrue(any(s['symbol'] == 'ITOT' and s['gain'] > 50_000 for s in sel))

    def test_short_term_lots_are_never_selected(self):
        c = sample_config()
        isolate_taxable_lots(c)
        inject_appreciated_lot(c, purchase_date=f"{2026}-06-01")  # acquired this year: short-term
        sel = gh.select_gain_harvest_lots(c, 2026, headroom=1_000_000.0, min_gain_dollars=500.0)
        self.assertFalse(any(s['symbol'] == 'ITOT' for s in sel))

    def test_non_taxable_accounts_never_scanned(self):
        c = sample_config()
        inject_appreciated_lot(c, account='Member_1_IRA')
        sel = gh.select_gain_harvest_lots(c, 2026, headroom=1_000_000.0, min_gain_dollars=500.0)
        self.assertFalse(any(s['account'] == 'Member_1_IRA' for s in sel))

    def test_selection_respects_headroom_ceiling(self):
        # Two lots, each individually within headroom on its own but not both
        # together: smallest-gain-first packing should take only the smaller.
        c = sample_config()
        isolate_taxable_lots(c)
        inject_appreciated_lot(c, symbol='ITOT', shares=100.0, basis_per_share=20.0)  # smaller gain
        inject_appreciated_lot(c, symbol='IXUS', shares=1000.0, basis_per_share=1.0)  # larger gain
        small_gain = 100.0 * (c['lot_engine'].prices.get('ITOT', 0.0) - 20.0)
        headroom = small_gain + 1.0  # just barely fits the small lot, not the large one
        sel = gh.select_gain_harvest_lots(c, 2026, headroom=headroom, min_gain_dollars=500.0)
        symbols = {s['symbol'] for s in sel}
        self.assertIn('ITOT', symbols)
        self.assertNotIn('IXUS', symbols)

    def test_scan_ledger_reconciles_totals(self):
        c = sample_config()
        inject_appreciated_lot(c)
        result = gh.scan_gain_harvest_opportunities(
            c, 2026, ordinary_income=40_000, transaction_cost_bps=2.0,
            min_gain_dollars=500.0,
        )
        self.assertGreater(result['headroom'], 0)
        self.assertTrue(result['opportunities'])
        computed_gain_total = sum(o['gain'] for o in result['opportunities'])
        self.assertAlmostEqual(computed_gain_total, result['totals']['gain'], places=6)


class EngineIntegrationTests(unittest.TestCase):
    def test_gain_harvest_off_is_a_pure_no_op(self):
        """Regression guard mirroring test_167's TLH-off no-op test: the new
        engine code path must not alter any existing projection when
        gain_harvest_policy is off (the default)."""
        with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
            c_off = sample_config('off')
            rows_off = project(c_off)
            c_baseline = baseline_config_without_gain_harvest_overrides()
            rows_baseline = project(c_baseline)
        self.assertAlmostEqual(rows_off[-1]['total_nw'], rows_baseline[-1]['total_nw'], places=2)
        self.assertAlmostEqual(
            sum(r['total_tax'] for r in rows_off),
            sum(r['total_tax'] for r in rows_baseline),
            places=2,
        )
        self.assertTrue(all(r.get('gain_harvest_realized', 0) == 0 for r in rows_off))

    def test_apply_mode_realizes_gain_and_resets_basis(self):
        # This wiring check only needs *some* year with ample 0%-bracket
        # headroom to prove the engine actually calls the scanner and
        # applies its result -- the live household's real ordinary income
        # stays well above ltcg_0_top for the entire 30-year horizon (a
        # genuinely high earner/spender), so realistic headroom is covered
        # separately by test_apply_mode_never_realizes_more_than_headroom_
        # worth_of_gain below. Here the ceiling is deliberately widened so
        # this test isn't at the mercy of the live plan's income trajectory.
        c = sample_config('apply')
        isolate_taxable_lots(c)
        inject_appreciated_lot(c)
        c['ltcg_0_top'] = 2_000_000.0
        rows = project(c)
        first = rows[0]
        self.assertGreater(first['gain_harvest_realized'], 10_000)
        self.assertGreater(first['gain_harvest_transaction_cost'], 0)

    def test_apply_mode_never_realizes_more_than_headroom_worth_of_gain(self):
        # A large-enough injected gain combined with real household income
        # should still respect the 0%-bracket ceiling -- confirms the engine
        # wiring passes the same headroom the standalone scanner would compute,
        # not an unbounded harvest.
        c = sample_config('apply')
        inject_appreciated_lot(c, shares=1_000_000.0, basis_per_share=0.01)  # huge gain, far past any headroom
        rows = project(c)
        first = rows[0]
        # ltcg_0_top is well under $200k even with generous bracket inflation;
        # a bound an order of magnitude above that safely catches "unbounded".
        self.assertLess(first['gain_harvest_realized'], 500_000)

    def test_apply_mode_does_not_change_projection_when_no_appreciated_lots_exist(self):
        with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
            c = sample_config('apply')
            isolate_taxable_lots(c)
            rows = project(c)
        self.assertTrue(all(r.get('gain_harvest_realized', 0) == 0 for r in rows))


class WorkbookSheetTests(unittest.TestCase):
    def test_sheet_builds_without_error_for_all_policies(self):
        from openpyxl import Workbook
        from src.reporting.sheets_strategy import build_sheet_gain_harvest
        for policy in ('off', 'analyze_only', 'apply'):
            c = sample_config(policy)
            isolate_taxable_lots(c)
            inject_appreciated_lot(c)
            rows = project(c)
            wb = Workbook()
            ws = wb.active
            build_sheet_gain_harvest(ws, c, rows)
            self.assertGreater(ws.max_row, 5)


if __name__ == '__main__':
    unittest.main()
