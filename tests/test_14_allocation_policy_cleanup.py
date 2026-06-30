from __future__ import annotations

import copy
import unittest
from pathlib import Path

from src.config_backend import load_csv
from src.data_io import parse_client
from src.planning_engines import project
from src import allocation_policy as ap

ROOT = Path(__file__).resolve().parents[1]


class AllocationPolicyCleanupTests(unittest.TestCase):
    def test_allocation_policy_page_has_supporting_inputs_not_mode_toggle(self):
        html = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('function renderAllocationPolicy', html)
        self.assertIn('Allocation policy settings', html)
        self.assertIn('Optimizer inputs', html)
        self.assertIn("case 'allocation_policy':return", html)
        self.assertNotIn("count_towards_asset_class", html)
        self.assertNotIn('Allocation mode and global settings', html)
        alloc_policy_case = html.split("case 'allocation_policy':return", 1)[1].split("case 'allocation_assets'", 1)[0]
        self.assertNotIn('allocation_selection_mode', alloc_policy_case)
        # The Allocation Recommendation page owns the global allocation source row.
        self.assertIn("case 'allocation_assets':return (sec==='Asset Allocation Policy'&&sub==='global'&&['allocation_selection_mode'", html)

    def test_advanced_options_pages_and_acronym_helpers_are_updated(self):
        html = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
        self.assertIn("id:'optional_functions'", html)
        self.assertIn("case 'optional_functions':return sec==='Optional Functions'", html)
        self.assertIn("title:'Scenarios'", html)
        self.assertIn("title:'Monte Carlo options'", html)
        self.assertIn("title:'Divorce options'", html)
        self.assertNotIn('Scenarios & Monte Carlo', html)
        self.assertNotIn("title:'Advanced configurations'", html)
        self.assertIn("pdia:'PDIA'", html)
        self.assertIn("PDIA:'Participating deferred income annuity'", html)
        self.assertIn('Acronym definitions', html)

    def test_optimizer_override_is_rendered_as_compact_table(self):
        html = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('function renderOptimizerOverrideTable', html)
        self.assertIn('allocation-override-table', html)
        self.assertIn('<th>Subcategory</th><th>Asset class</th><th>Override target %</th>', html)
        self.assertIn('Copy optimizer override to user-defined', html)

    def test_no_packaged_plan_data_or_schema_ships_legacy_count_inputs(self):
        forbidden = [
            '_'.join(parts) for parts in [
                ('count', 'social', 'security', 'toward', 'fixed', 'income', 'target'),
                ('count', 'pension', 'toward', 'fixed', 'income', 'target'),
                ('count', 'annuity', 'toward', 'fixed', 'income', 'target'),
                ('count', 'note', 'receivable', 'toward', 'fixed', 'income', 'target'),
                ('count', 'home', 'equity', 'toward', 'reit', 'target'),
            ]
        ]
        roots = [ROOT / 'input', ROOT / 'multi_user', ROOT / 'reference_data', ROOT / 'frontend']
        for base in roots:
            if not base.exists():
                continue
            for path in base.rglob('*'):
                if path.is_dir() or path.suffix.lower() in {'.db', '.xlsx', '.pdf', '.png'}:
                    continue
                text = path.read_text(encoding='utf-8', errors='ignore')
                for token in forbidden:
                    self.assertNotIn(token, text, f'{token} remained in {path.relative_to(ROOT)}')

    def test_switching_allocation_mode_changes_projection_assumptions_and_terminal_value(self):
        data = load_csv(ROOT / 'input' / 'client_data.csv')
        user_cfg = parse_client(copy.deepcopy(data), '')
        opt_data = copy.deepcopy(data)
        opt_data.setdefault('Asset Allocation Policy', {}).setdefault('Global', {})['allocation_selection_mode'] = ap.ALLOCATION_MODE_OPTIMIZER
        opt_cfg = parse_client(opt_data, '')

        self.assertEqual(user_cfg['allocation_projection_mode'], ap.ALLOCATION_MODE_USER)
        self.assertEqual(opt_cfg['allocation_projection_mode'], ap.ALLOCATION_MODE_OPTIMIZER)
        # User-defined mode remains calibrated to the configured economic return;
        # optimizer mode applies only the relative optimizer-vs-user allocation delta.
        self.assertAlmostEqual(user_cfg['ret'], user_cfg['configured_portfolio_nominal_return'], places=8)
        self.assertNotAlmostEqual(user_cfg['ret'], opt_cfg['ret'], places=6)
        self.assertNotAlmostEqual(user_cfg['mc_sigma'], opt_cfg['mc_sigma'], places=6)

        user_rows = project(user_cfg)
        opt_rows = project(opt_cfg)
        user_terminal = user_rows[-1]['total_nw']
        path_delta = max(abs(u['total_nw'] - o['total_nw']) for u, o in zip(user_rows, opt_rows))
        self.assertLess(user_terminal, 15_000_000.0)
        self.assertGreater(path_delta, 1000.0)


if __name__ == '__main__':
    unittest.main()
