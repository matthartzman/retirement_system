import copy
import json
import unittest
from pathlib import Path

from src.core import RMD_DIVISORS, validate_projection
from src.data_io import build_plan_from_json, load_csv, parse_client
from src.planning_engines import _percentiles, project

ROOT = Path(__file__).resolve().parents[1]


def sample_config():
    data = load_csv(ROOT / 'input' / 'client_data.csv')
    c = parse_client(data, '')
    c['roth_policy'] = 'none'
    c['mc_paths'] = 5
    c['mc_sensitivity_sims'] = 1
    return c


class RegressionV781Tests(unittest.TestCase):
    def test_rmd_divisors_are_strictly_decreasing(self):
        ages = sorted(RMD_DIVISORS)
        for a, b in zip(ages, ages[1:]):
            self.assertGreater(RMD_DIVISORS[a], RMD_DIVISORS[b], (a, b))
        self.assertEqual(RMD_DIVISORS[85], 16.0)
        self.assertEqual(RMD_DIVISORS[101], 6.0)

    def test_sectioned_client_json_does_not_return_zero_forecast(self):
        plan = json.loads((ROOT / 'input' / 'client_data.json').read_text())
        c = build_plan_from_json(plan)
        self.assertGreater(sum(c['balances'].values()), 0)
        rows = project(c)
        self.assertGreater(rows[-1]['total_nw'], 0)

    def test_agi_components_validation_uses_taxable_annuity_components(self):
        c = sample_config()
        rows = project(c)
        agi_warnings = [v for v in validate_projection(rows, c) if v[2] == 'AGI_COMPONENTS']
        self.assertEqual(agi_warnings, [])

    def test_single_filing_home_sale_uses_250k_sec121_exclusion(self):
        c = sample_config()
        year = c['plan_start']
        c.update({
            'plan_end': year,
            'filing_status': 'Single',
            'survivor_filing': 'Single',
            'home_val': 1_000_000.0,
            'home_sale_yr': year,
            'home_sale_px': 1_000_000.0,
            'home_basis': 100_000.0,
            'home_sell_cost_pct': 0.0,
            'mortgage_bal': 0.0,
            'mort_schedule': {},
            'mort_end': year - 1,
            'sec121': 500_000.0,
        })
        rows = project(c)
        self.assertEqual(rows[0]['home_sale_sec121_exclusion'], 250_000.0)
        self.assertEqual(rows[0]['home_sale_taxable'], 650_000.0)

    def test_legacy_post_sale_rent_setting_is_ignored(self):
        c = sample_config()
        year = c['plan_start']
        c.update({
            'plan_end': year,
            'home_sale_yr': year,
            'home_sale_px': c.get('home_val', 1_000_000.0),
            'post_sale_rent_mo': 3000.0,
            'next_housing_steps': [],
            'mort_pmt': 0.0,
            'mort_end': year - 1,
            'mort_schedule': {},
        })
        row = project(c)[0]
        self.assertEqual(row['rent_yr'], 0.0)

    def test_current_home_operating_costs_drop_after_home_sale_and_next_rent(self):
        c = sample_config()
        year = c['plan_start']
        c.update({
            'plan_end': year,
            'home_sale_yr': year,
            'home_sale_px': c.get('home_val', 1_000_000.0),
            'mort_pmt': 0.0,
            'mort_end': year - 1,
            'mort_schedule': {},
            'real_estate_tax_base': 0.0,
            'spending_rollup_by_year': {
                year: {'Housing': {'Utilities': 2400.0, 'Maintenance': 1200.0, 'Other': 800.0}}
            },
            'next_housing_steps': [{
                'id': 'rent_after_sale',
                'type': 'rent',
                'start_year': year,
                'monthly_rent': 3000.0,
                'utilities_annual': 600.0,
                'insurance_annual': 300.0,
            }],
        })
        row = project(c)[0]
        self.assertGreater(row['rent_yr'], 0.0)
        self.assertEqual(row['housing_utilities_yr'], 600.0)
        self.assertEqual(row['housing_maintenance_yr'], 0.0)
        self.assertEqual(row['housing_other_yr'], 300.0)

    def test_next_housing_rent_does_not_seed_insurance_or_utilities_from_current_home(self):
        c = sample_config()
        year = c['plan_start']
        c.update({
            'plan_end': year,
            'home_sale_yr': year,
            'home_sale_px': c.get('home_val', 1_000_000.0),
            'mort_pmt': 0.0,
            'mort_end': year - 1,
            'mort_schedule': {},
            'current_homeowners_insurance_annual': 2000.0,
            'current_home_utilities_annual': 6000.0,
            'spending_rollup_by_year': {},
            'next_housing_steps': [{
                'id': 'rent_after_sale',
                'type': 'rent',
                'start_year': year,
                'monthly_rent': 3000.0,
                'utilities_annual': 0.0,
                'insurance_annual': 0.0,
            }],
        })
        row = project(c)[0]
        self.assertGreater(row['rent_yr'], 0.0)
        self.assertEqual(row['housing_utilities_yr'], 0.0)
        self.assertEqual(row['housing_other_yr'], 0.0)

    def test_niit_is_added_to_funding_need(self):
        c = sample_config()
        year = c['plan_start']
        c.update({
            'plan_end': year,
            'note_first': year,
            'note_last': year,
            'note_interest': {year: 500_000.0},
            'note_princ': 0.0,
            'note_princ_final': 0.0,
            'note_face': 0.0,
            'spend_base': 900_000.0,
            'rec_extra': 0.0,
            'lump_events': {},
            'mort_pmt': 0.0,
            'mort_schedule': {},
            'hc_base': 0.0,
        })
        c_with = copy.deepcopy(c); c_with['model_niit'] = True
        c_without = copy.deepcopy(c); c_without['model_niit'] = False
        r_with = project(c_with)[0]
        r_without = project(c_without)[0]
        wd_with = sum(r_with.get(k, 0) for k in ['ira_wd', 'trust_wd', 'roth_wd', 'hsa_wd', 'heloc_draw'])
        wd_without = sum(r_without.get(k, 0) for k in ['ira_wd', 'trust_wd', 'roth_wd', 'hsa_wd', 'heloc_draw'])
        self.assertGreater(r_with['niit'], 0)
        self.assertGreater(wd_with, wd_without + r_with['niit'] * 0.95)
        self.assertAlmostEqual(r_with['net_income'], r_with['gross_income'] - r_with['total_tax'], places=6)

    def test_percentiles_are_interpolated(self):
        p = _percentiles([0, 100])
        self.assertEqual(p[50], 50.0)
        self.assertEqual(p[25], 25.0)
        self.assertEqual(p[75], 75.0)


if __name__ == '__main__':
    unittest.main()
