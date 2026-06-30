from __future__ import annotations
import csv
import itertools
import unittest
from pathlib import Path

from src import allocation_policy as ap
from src import optimization as opt
from src.data_io import load_csv, parse_client

ROOT = Path(__file__).resolve().parents[1]

class TestAssetClassOptimizerControls(unittest.TestCase):
    def test_requested_asset_classes_are_canonical_and_have_assumptions(self):
        expected = [
            'US Large Cap','US Mid Cap','US Small Cap','International','Emerging Markets','Commodities',
            'Bonds','Short-Term Bonds','TIPS','Municipal Bonds','Managed Futures','Private Credit','REITs','Cash'
        ]
        self.assertEqual(list(ap.DEFAULT_ALLOCATION_TARGETS.keys()), expected)
        for cls in expected:
            self.assertIn(cls, opt.ASSET_CLASSES)
            self.assertIn('ret', opt.ASSET_CLASSES[cls])
            self.assertIn('vol', opt.ASSET_CLASSES[cls])

    def test_all_pairs_have_correlations(self):
        classes = list(opt.ASSET_CLASSES.keys())
        missing = [(a,b) for a,b in itertools.combinations(classes,2) if (a,b) not in opt._CORR and (b,a) not in opt._CORR]
        self.assertEqual(missing, [])

    def test_separate_optimizer_controls_csv_loads(self):
        data = load_csv(ROOT / 'input' / 'client_data.csv')
        self.assertIn('Asset Class Optimizer Controls', data)
        cfg = parse_client(data, '')
        self.assertTrue(cfg['asset_class_enabled']['US Mid Cap'])
        self.assertTrue(cfg['asset_class_enabled']['Municipal Bonds'])

    def test_excluding_class_removes_it_from_optimizer_targets(self):
        data = load_csv(ROOT / 'input' / 'client_data.csv')
        data['Asset Class Optimizer Controls']['US Mid Cap']['selection_action'] = 'exclude'
        cfg = parse_client(data, '')
        out = opt.compute_optimal_allocation(cfg, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)
        self.assertNotIn('US Mid Cap', out.get('liquid_targets', {}))

    def test_reference_correlation_csv_contains_all_pairs(self):
        p = ROOT / 'reference_data' / 'asset_correlations.csv'
        seen = set()
        with p.open(newline='', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                seen.add((row['asset_class_a'], row['asset_class_b']))
        for pair in itertools.combinations(opt.ASSET_CLASSES.keys(), 2):
            self.assertIn(pair, seen)

if __name__ == '__main__':
    unittest.main()
