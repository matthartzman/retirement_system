from __future__ import annotations

import copy
import unittest
from pathlib import Path

from src import allocation_policy as ap
from src.data_io import load_csv, parse_client
from src.optimization import compute_optimal_allocation

ROOT = Path(__file__).resolve().parents[1]


class AllocationOptimizerToggleTests(unittest.TestCase):
    def _config(self):
        data = load_csv(ROOT / 'input' / 'client_data.csv')
        return parse_client(data, '')

    def test_allocation_mode_defaults_to_user_target_and_optimizer_available(self):
        c = self._config()
        self.assertEqual(c['allocation_selection_mode'], ap.ALLOCATION_MODE_USER)
        selected = compute_optimal_allocation(c)
        optimizer = compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)
        self.assertEqual(selected['diagnostics']['allocation_policy_mode'], 'user_target_pct')
        self.assertEqual(optimizer['diagnostics']['allocation_policy_mode'], 'optimizer_recommendation')
        self.assertAlmostEqual(sum(selected['liquid_targets'].values()), 1.0, places=8)
        self.assertAlmostEqual(sum(optimizer['liquid_targets'].values()), 1.0, places=8)
        self.assertIn('optimizer_recommendation', selected['diagnostics'])
        self.assertIn('risk tolerance', ap.OPTIMIZER_RECOMMENDATION_COMMENT.lower())

    def test_toggle_to_optimizer_changes_selected_recommendation(self):
        c = self._config()
        manual = compute_optimal_allocation(c)['liquid_targets']
        c2 = copy.deepcopy(c)
        c2['allocation_selection_mode'] = ap.ALLOCATION_MODE_OPTIMIZER
        selected = compute_optimal_allocation(c2)
        forced = compute_optimal_allocation(c2, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)
        self.assertEqual(selected['diagnostics']['allocation_policy_mode'], 'optimizer_recommendation')
        self.assertNotAlmostEqual(selected['liquid_targets'].get('US Large Cap', 0), manual.get('US Large Cap', 0), places=4)
        self.assertAlmostEqual(selected['liquid_targets'].get('US Large Cap', 0), forced['liquid_targets'].get('US Large Cap', 0), places=8)

    def test_ui_exposes_optimizer_toggle_and_explanation(self):
        html = (ROOT / 'src' / 'dashboard_ui' / 'template.py').read_text(encoding='utf-8')
        self.assertIn('Use allocation optimizer recommendation', html)
        self.assertIn('Use user-specified allocation', html)
        self.assertIn('allocationOptimizerRecommendationHtml', html)
        self.assertIn('Current inputs used by the optimizer', html)
        self.assertIn('User-specified allocation total', html)


if __name__ == '__main__':
    unittest.main()
