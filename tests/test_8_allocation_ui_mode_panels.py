from __future__ import annotations
import csv
import copy
import unittest
from pathlib import Path

from src import allocation_policy as ap
from src.data_io import load_csv, parse_client
from src.optimization import compute_optimal_allocation

ROOT = Path(__file__).resolve().parents[1]


class AllocationUIModePanelsTests(unittest.TestCase):
    def test_optimizer_controls_csv_has_override_rows_for_every_class(self):
        p = ROOT / 'input' / 'asset_class_optimizer_controls.csv'
        seen_action = set()
        seen_override = set()
        with p.open(newline='', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                if row['label'] == 'selection_action':
                    seen_action.add(ap.canonical_asset_class(row['subsection']))
                if row['label'] == 'optimizer_override_pct':
                    seen_override.add(ap.canonical_asset_class(row['subsection']))
        expected = set(ap.DEFAULT_ALLOCATION_TARGETS)
        self.assertEqual(seen_action, expected)
        self.assertEqual(seen_override, expected)

    def test_parser_loads_blank_optimizer_overrides_without_activating_them(self):
        data = load_csv(ROOT / 'input' / 'client_data.csv')
        c = parse_client(data, '')
        self.assertEqual(set(c['allocation_optimizer_override_pct']), set(ap.DEFAULT_ALLOCATION_TARGETS))
        self.assertAlmostEqual(c['allocation_optimizer_override_sum'], 0.0)
        out = compute_optimal_allocation({**c, 'allocation_selection_mode': ap.ALLOCATION_MODE_OPTIMIZER})
        self.assertEqual(out['diagnostics']['allocation_policy_mode'], 'optimizer_recommendation')

    def test_optimizer_override_replaces_computed_optimizer_when_entered(self):
        data = load_csv(ROOT / 'input' / 'client_data.csv')
        c = parse_client(data, '')
        c = copy.deepcopy(c)
        c['allocation_selection_mode'] = ap.ALLOCATION_MODE_OPTIMIZER
        c['allocation_optimizer_override_pct'] = {cls: 0.0 for cls in ap.DEFAULT_ALLOCATION_TARGETS}
        c['allocation_optimizer_override_pct']['US Large Cap'] = 0.60
        c['allocation_optimizer_override_pct']['Bonds'] = 0.35
        c['allocation_optimizer_override_pct']['Cash'] = 0.05
        out = compute_optimal_allocation(c)
        self.assertEqual(out['diagnostics']['allocation_policy_mode'], 'optimizer_override_pct')
        self.assertAlmostEqual(sum(out['liquid_targets'].values()), 1.0, places=8)
        # Override targets are retained as total-target context, but covered
        # fixed-income sleeves are removed from the active liquid target before
        # the remaining liquid allocation is normalized.
        self.assertAlmostEqual(out['total_targets']['US Large Cap'], 0.60, places=8)
        self.assertAlmostEqual(out['total_targets']['Bonds/Fixed Income'], 0.35, places=8)
        self.assertLess(out['liquid_targets']['Bonds'], 0.35)
        self.assertGreater(out['liquid_targets']['US Large Cap'], 0.60)
        self.assertGreater(out['liquid_targets']['Cash'], 0.05)

    def test_ui_has_mode_specific_panels_and_copy_button(self):
        html = (ROOT / 'src' / 'dashboard_ui' / 'template.py').read_text(encoding='utf-8')
        self.assertIn('renderAllocationRecommendation', html)
        self.assertIn('renderUserAllocationPanel', html)
        self.assertIn('renderOptimizerAllocationPanel', html)
        self.assertIn('Copy optimizer override to user-defined', html)
        self.assertIn('optimizer_override_pct', html)
        self.assertIn('Optional override percentages below replace the computed optimizer result', html)

    def test_canonical_frontend_contains_visible_allocation_mode_panel(self):
        html = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('renderAllocationRecommendation', html)
        self.assertIn('renderAllocationPolicy', html)
        self.assertIn('Use allocation optimizer recommendation', html)
        self.assertIn('Use user-specified allocation', html)
        self.assertIn('allocation_selection_mode', html)
        self.assertIn('Optional override percentages below replace the computed optimizer result', html)
        self.assertIn('Copy optimizer override to user-defined', html)
        self.assertIn("else if(activeStep==='allocation_policy')content+=renderAllocationPolicy();else if(activeStep==='allocation_assets')content+=renderAllocationRecommendation()", html)

    def test_no_duplicate_src_frontend_artifact_exists(self):
        self.assertFalse((ROOT / 'src' / 'frontend').exists())


if __name__ == '__main__':
    unittest.main()
