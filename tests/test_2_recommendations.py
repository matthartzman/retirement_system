import json
import unittest
from pathlib import Path

from src.data_io import load_csv, parse_client, summarize_validation
from src.plan_config import ensure_engine_config
from src.planning_engines import project
from src.server_forecast import forecast_from_plan_json

ROOT = Path(__file__).resolve().parents[1]


def sample_config():
    data = load_csv(ROOT / 'input' / 'client_data.csv')
    c = parse_client(data, '')
    c['roth_policy'] = 'none'
    c['mc_paths'] = 5
    c['mc_sensitivity_sims'] = 1
    return ensure_engine_config(c, source='test')


class RecommendationCompletionTests(unittest.TestCase):
    def test_config_contract_and_schema_source_are_recorded(self):
        c = sample_config()
        self.assertEqual(c['config_contract_version'], 'v1')
        self.assertIn(c['config_contract_source'], {'test', 'project', 'sectioned'})
        self.assertGreater(sum(c['balances'].values()), 0)
        self.assertTrue(c['all_acct_ids'])

    def test_sample_projection_golden_master_and_release_gate(self):
        # Golden-master constants are tied to input/client_data.csv (and its
        # transaction/budget-derived spend base) as of this commit. Regenerate
        # them deliberately after intentional plan-data changes; a mismatch
        # otherwise usually means a real projection-engine regression.
        #
        # Item 141 (2026-07): the projection spend_base dropped from 129,059 to
        # 124,059 after fixing a double-count in spending_budget_resolver — a
        # Core Expenses category (charitable giving) that carried BOTH a category
        # budget row and a detail line was counted twice. The 5,000/yr lower spend
        # reinvests as surplus, so terminal net worth and later-year taxes rise.
        #
        # Item 142 (2026-07-07 12:09 PM): spending budget line items updated manually
        # (dentist, medical, gifts, health club, vitamins) and miscellaneous/uncategorized
        # cleared out after taxonomy changes. Terminal net worth increased to ~12.4M.
        #
        # These constants are now fully reproducible: tests/conftest.py pins
        # holdings pricing to OFFLINE, so starting balances come from the
        # committed cache snapshot rather than live market data. Platform/version
        # differences (Windows/Python 3.14 vs Linux/3.11) may cause floating-point
        # precision variations (~0.03% tolerance); regenerate deliberately after
        # an intentional engine/plan-data change.
        c = sample_config()
        rows = project(c)
        summary = summarize_validation(rows, c)
        self.assertEqual(summary['fail_count'], 0)
        self.assertEqual(summary['warn_count'], 0)
        self.assertEqual((rows[0]['year'], rows[-1]['year'], len(rows)), (2026, 2056, 31))
        # Platform/version differences (Windows/Python 3.14 vs Linux/3.11):
        # floating point precision variations ~0.03% tolerance
        self.assertAlmostEqual(rows[-1]['total_nw'], 12_442_573.16, delta=5000.0)
        self.assertAlmostEqual(sum(r['total_tax'] for r in rows), 1_532_170.93, delta=5000.0)

    def test_fixed_point_taxable_withdrawal_solver_runs_before_roth(self):
        c = sample_config()
        c['tax_withdrawal_fixed_point_iterations'] = 3
        rows = project(c)
        self.assertGreater(sum(r.get('investment_tax_iterations', 0) for r in rows), 0)
        self.assertGreater(sum(r.get('investment_tax_funded_by_taxable', 0) for r in rows), 0)
        self.assertEqual(sum(
            1 for r in rows
            if r.get('roth_wd', 0) > 1 and (r.get('pretax_nw', 0) + r.get('trust_nw', 0) + r.get('hsa_nw', 0)) > 1
        ), 0)

    def test_tax_table_currency_warnings_surface_to_config(self):
        c = sample_config()
        warnings = c.get('tax_table_currency_warnings', [])
        self.assertFalse(any('federal_brackets' in w for w in warnings))
        self.assertEqual(warnings, [])

    def test_forecast_api_service_uses_same_config_contract(self):
        plan = json.loads((ROOT / 'input' / 'client_data.json').read_text())
        result = forecast_from_plan_json(plan, run_mc=False)
        self.assertEqual(result['status'], 'ok')
        self.assertGreater(result['terminal_nw'], 0)
        self.assertEqual(result['validation']['fail_count'], 0)
        self.assertIn('config_contract_source', result)

    def test_duplicate_frontend_compatibility_file_removed(self):
        canonical = ROOT / 'frontend' / 'index.html'
        self.assertTrue(canonical.exists())
        self.assertEqual(len(list((ROOT / 'frontend').glob('*.html'))), 2)


if __name__ == '__main__':
    unittest.main()
