from __future__ import annotations

import copy
import unittest
from pathlib import Path

from src import allocation_policy as ap
from src.data_io import load_csv, parse_client
from src.optimization import allocation_portfolio_stats
from src.planning_engines import project

ROOT = Path(__file__).resolve().parents[1]


class AllocationScenarioTests(unittest.TestCase):
    def _config(self):
        data = load_csv(ROOT / 'input' / 'client_data.csv')
        c = parse_client(data, '')
        c['mc_sims'] = 5
        c['mc_sensitivity_sims'] = 1
        return c

    def test_plan_data_includes_two_allocation_scenarios_but_ui_hides_mode_rows(self):
        text = (ROOT / 'input' / 'client_policy.csv').read_text(encoding='utf-8')
        self.assertIn('Scenarios,Allocation User Defined,allocation_selection_mode,user_target', text)
        self.assertIn('Scenarios,Allocation Optimizer Defined,allocation_selection_mode,optimizer_recommendation', text)
        ui = (ROOT / 'src' / 'dashboard_ui' / 'template.py').read_text(encoding='utf-8')
        self.assertIn("title:'Scenarios'", ui)
        self.assertIn("title:'Monte Carlo options'", ui)
        self.assertIn("case 'scenarios':return sec==='Scenarios'&&!rowIsDivorceScenario(r)", ui)
        self.assertIn("case 'monte_carlo_options':return rowIsMonteCarlo(r)", ui)
        self.assertIn("case 'divorce_options':return optionalFunctionEnabled('divorce_qdro')&&rowIsDivorceScenario(r)", ui)
        self.assertNotIn('Allocation — User Defined', ui)
        self.assertNotIn('Allocation — Optimizer Defined', ui)

    def test_allocation_scenario_stats_are_cashflow_ready(self):
        c = self._config()
        user = allocation_portfolio_stats(c, force_mode=ap.ALLOCATION_MODE_USER)
        opt = allocation_portfolio_stats(c, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)
        for stats in (user, opt):
            self.assertGreater(stats['expected_return'], 0)
            self.assertGreater(stats['volatility'], 0)
            self.assertAlmostEqual(sum(stats['targets'].values()), 1.0, places=8)
            self.assertIn('Cash', stats['targets'])
        self.assertNotAlmostEqual(user['expected_return'], opt['expected_return'], places=4)

    def test_allocation_scenarios_change_projection_return(self):
        c = self._config()
        base_rows = project(copy.deepcopy(c))
        opt_stats = allocation_portfolio_stats(c, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)
        c_opt = copy.deepcopy(c)
        c_opt['allocation_selection_mode'] = ap.ALLOCATION_MODE_OPTIMIZER
        c_opt['ret'] = opt_stats['expected_return']
        c_opt['mc_sigma'] = opt_stats['volatility']
        opt_rows = project(c_opt)
        path_delta = max(abs(b['total_nw'] - o['total_nw']) for b, o in zip(base_rows, opt_rows))
        self.assertGreater(path_delta, 1000)


if __name__ == '__main__':
    unittest.main()
