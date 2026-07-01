from __future__ import annotations

import csv
import copy
import unittest
from pathlib import Path

from src import allocation_policy as ap
from src.data_io import load_csv, parse_client
from src.optimization import compute_optimal_allocation

ROOT = Path(__file__).resolve().parents[1]


class CompactAllocationSelectionTests(unittest.TestCase):
    def test_controls_csv_has_selection_action_and_alternate_rows_for_every_class(self):
        p = ROOT / 'input' / 'asset_class_optimizer_controls.csv'
        actions = set()
        alternates = set()
        valid_actions = {'include', 'exclude', 'consider_alternate_first'}
        with p.open(newline='', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                cls = ap.canonical_asset_class(row['subsection'])
                if row['label'] == 'selection_action':
                    actions.add(cls)
                    self.assertIn(row['value'], valid_actions, f"{cls} has invalid selection_action")
                if row['label'] == 'alternate_asset_class':
                    alternates.add(cls)
        expected = set(ap.DEFAULT_ALLOCATION_TARGETS)
        self.assertEqual(actions, expected)
        self.assertEqual(alternates, expected)

    def test_ui_renders_compact_asset_class_selection_table(self):
        html = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('renderAssetClassSelectionTable', html)
        self.assertIn('Asset-class allocation policy', html)
        self.assertIn('Consider alternate first', html)
        self.assertIn('alternate_asset_class', html)
        self.assertIn('Existing asset/source credited to this class', html)
        self.assertIn('targetPctInput', html)

    def test_parser_selection_action_controls_asset_enabled_status(self):
        data = load_csv(ROOT / 'input' / 'client_data.csv')
        data['Asset Class Optimizer Controls']['US Mid Cap']['selection_action'] = 'exclude'
        cfg = parse_client(data, '')
        self.assertFalse(cfg['asset_class_enabled']['US Mid Cap'])
        self.assertEqual(cfg['asset_class_selection_action']['US Mid Cap'], ap.SELECTION_EXCLUDE)

    def test_alternate_first_redirects_user_defined_target(self):
        data = load_csv(ROOT / 'input' / 'client_data.csv')
        cfg = parse_client(data, '')
        cfg = copy.deepcopy(cfg)
        cfg['allocation_selection_mode'] = ap.ALLOCATION_MODE_USER
        cfg['asset_class_selection_action']['US Mid Cap'] = ap.SELECTION_ALTERNATE_FIRST
        cfg['asset_class_alternate_first']['US Mid Cap'] = 'US Small Cap'
        out = compute_optimal_allocation(cfg)
        self.assertNotIn('US Mid Cap', {k: v for k, v in out['liquid_targets'].items() if v > 1e-10})
        self.assertGreater(out['liquid_targets'].get('US Small Cap', 0.0), cfg['allocation_target_pct']['US Small Cap'])
        self.assertEqual(out['diagnostics']['alternate_first_map'].get('US Mid Cap'), 'US Small Cap')


if __name__ == '__main__':
    unittest.main()
