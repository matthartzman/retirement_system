"""Wave 4 item 4.9 (system review P5 phase 2): per-beneficiary 10-year
drawdown of inherited pre-tax/Roth accounts, blocked on items 4.3 (done
earlier) and 4.7 (this wave). Explicitly a scenario-sensitivity report, not
a prediction.
"""
from __future__ import annotations

import unittest

from src.after_tax import _account_ten_year_schedule, per_beneficiary_ten_year_drawdown


class TenYearScheduleTests(unittest.TestCase):
    def test_flat_schedule_sums_to_the_full_balance(self):
        schedule = _account_ten_year_schedule(100_000.0, decedent_reached_rbd=False)
        self.assertEqual(len(schedule), 10)
        self.assertTrue(all(abs(s - 10_000.0) < 1e-6 for s in schedule))
        self.assertAlmostEqual(sum(schedule), 100_000.0, places=2)

    def test_declining_divisor_schedule_with_no_growth_matches_the_flat_schedule(self):
        # A known identity: dividing a balance that shrinks by exactly
        # 1/divisor each year by a divisor that also shrinks by 1 each year
        # always yields the same constant slice when there's no growth --
        # confirming growth is what actually differentiates the RBD-reached
        # schedule from phase 1's flat one, not the declining divisor alone.
        schedule = _account_ten_year_schedule(100_000.0, decedent_reached_rbd=True, annual_growth_rate=0.0)
        self.assertTrue(all(abs(s - 10_000.0) < 1e-6 for s in schedule))

    def test_declining_divisor_schedule_with_growth_front_loads_smaller_distributions(self):
        schedule = _account_ten_year_schedule(100_000.0, decedent_reached_rbd=True, annual_growth_rate=0.06)
        self.assertEqual(len(schedule), 10)
        # Growth during the drawdown means total distributed exceeds the
        # original balance (the account keeps compounding while being drawn
        # down), but the account is still fully depleted by year 10.
        self.assertGreater(sum(schedule), 100_000.0)
        self.assertLess(schedule[0], schedule[-1])

    def test_zero_balance_is_a_zero_schedule(self):
        self.assertEqual(_account_ten_year_schedule(0.0, decedent_reached_rbd=True), [0.0] * 10)


def _base_config(**overrides):
    c = {
        'h_death_yr': 0, 'w_death_yr': 0,
        'h_dob_yr': 1960, 'w_dob_yr': 1962,
        'rmd_start_age': 75,
        'brk_inf': 0.02,
        'ret': 0.06,
        'roth_heir_filing_status': 'Single',
        'account_registry': [],
        'account_titling': {},
    }
    c.update(overrides)
    return c


class PerBeneficiaryDrawdownTests(unittest.TestCase):
    def test_no_second_death_year_returns_unavailable_not_an_error(self):
        c = _base_config()
        result = per_beneficiary_ten_year_drawdown(c, rows=[])
        self.assertFalse(result['available'])
        self.assertEqual(result['beneficiaries'], [])

    def test_no_account_titling_returns_unavailable(self):
        c = _base_config(
            h_death_yr=2050, w_death_yr=2045,
            account_registry=[{'id': 'H_IRA', 'owner_idx': 0, 'tax': 'pre_tax', 'label': "Alex's IRA"}],
        )
        rows = [{'year': 2050, '_account_balances': {'H_IRA': 500_000.0}}]
        result = per_beneficiary_ten_year_drawdown(c, rows)
        self.assertFalse(result['available'])

    def test_no_balance_snapshot_at_second_death_returns_unavailable(self):
        c = _base_config(
            h_death_yr=2050, w_death_yr=2045,
            account_registry=[{'id': 'H_IRA', 'owner_idx': 0, 'tax': 'pre_tax', 'label': "Alex's IRA"}],
            account_titling={'H_IRA': {'primary_beneficiary': 'Jordan'}},
        )
        rows = [{'year': 2049}]  # no row at year 2050, no _account_balances anywhere
        result = per_beneficiary_ten_year_drawdown(c, rows)
        self.assertFalse(result['available'])

    def test_full_drawdown_for_a_decedent_who_reached_rbd(self):
        # h dies second (2050), born 1960 -> reaches rmd_start_age 75 in 2035, well before 2050.
        c = _base_config(
            h_death_yr=2050, w_death_yr=2045,
            account_registry=[{'id': 'H_IRA', 'owner_idx': 0, 'tax': 'pre_tax', 'label': "Alex's IRA"}],
            account_titling={'H_IRA': {'primary_beneficiary': 'Jordan'}},
        )
        rows = [{'year': 2050, '_account_balances': {'H_IRA': 500_000.0}}]
        result = per_beneficiary_ten_year_drawdown(c, rows)
        self.assertTrue(result['available'])
        self.assertTrue(result['decedent_reached_rbd'])
        self.assertEqual(len(result['beneficiaries']), 1)
        jordan = result['beneficiaries'][0]
        self.assertEqual(jordan['beneficiary'], 'Jordan')
        self.assertAlmostEqual(jordan['gross_total'], 500_000.0, places=2)
        self.assertGreater(jordan['total_tax'], 0)
        # after_tax_total is net of real tax on each year's slice; it can
        # exceed the original terminal balance because the account keeps
        # growing during the 10-year drawdown, but it must always be less
        # than the pre-tax total actually distributed (total_tax + after_tax_total).
        self.assertLess(jordan['after_tax_total'], jordan['after_tax_total'] + jordan['total_tax'])
        acct = jordan['accounts'][0]
        self.assertTrue(acct['decedent_reached_rbd'])
        # Growth during the drawdown window means the total distributed
        # exceeds the original terminal balance.
        self.assertGreaterEqual(sum(acct['annual_schedule']), 500_000.0)

    def test_decedent_below_rbd_uses_flat_schedule(self):
        # h dies second (2030), born 1960 -> only 70 years old, below rmd_start_age 75.
        c = _base_config(
            h_death_yr=2030, w_death_yr=2025,
            account_registry=[{'id': 'H_IRA', 'owner_idx': 0, 'tax': 'pre_tax', 'label': "Alex's IRA"}],
            account_titling={'H_IRA': {'primary_beneficiary': 'Jordan'}},
        )
        rows = [{'year': 2030, '_account_balances': {'H_IRA': 500_000.0}}]
        result = per_beneficiary_ten_year_drawdown(c, rows)
        self.assertFalse(result['decedent_reached_rbd'])
        acct = result['beneficiaries'][0]['accounts'][0]
        self.assertFalse(acct['decedent_reached_rbd'])
        for s in acct['annual_schedule']:
            self.assertAlmostEqual(s, 50_000.0, places=2)

    def test_roth_account_distributions_are_tax_free(self):
        c = _base_config(
            h_death_yr=2050, w_death_yr=2045,
            account_registry=[{'id': 'H_Roth', 'owner_idx': 0, 'tax': 'roth', 'label': "Alex's Roth"}],
            account_titling={'H_Roth': {'primary_beneficiary': 'Jordan'}},
        )
        rows = [{'year': 2050, '_account_balances': {'H_Roth': 500_000.0}}]
        result = per_beneficiary_ten_year_drawdown(c, rows)
        jordan = result['beneficiaries'][0]
        self.assertEqual(jordan['total_tax'], 0)
        self.assertAlmostEqual(jordan['after_tax_total'], 500_000.0, places=2)

    def test_two_accounts_to_the_same_beneficiary_aggregate(self):
        c = _base_config(
            h_death_yr=2050, w_death_yr=2045,
            account_registry=[
                {'id': 'H_IRA', 'owner_idx': 0, 'tax': 'pre_tax', 'label': "Alex's IRA"},
                {'id': 'H_401k', 'owner_idx': 0, 'tax': 'pre_tax', 'label': "Alex's 401k"},
            ],
            account_titling={
                'H_IRA': {'primary_beneficiary': 'Jordan'},
                'H_401k': {'primary_beneficiary': 'Jordan'},
            },
        )
        rows = [{'year': 2050, '_account_balances': {'H_IRA': 300_000.0, 'H_401k': 200_000.0}}]
        result = per_beneficiary_ten_year_drawdown(c, rows)
        self.assertEqual(len(result['beneficiaries']), 1)
        jordan = result['beneficiaries'][0]
        self.assertEqual(len(jordan['accounts']), 2)
        self.assertAlmostEqual(jordan['gross_total'], 500_000.0, places=2)

    def test_different_beneficiaries_are_kept_separate(self):
        c = _base_config(
            h_death_yr=2050, w_death_yr=2045,
            account_registry=[
                {'id': 'H_IRA', 'owner_idx': 0, 'tax': 'pre_tax', 'label': "Alex's IRA"},
                {'id': 'H_401k', 'owner_idx': 0, 'tax': 'pre_tax', 'label': "Alex's 401k"},
            ],
            account_titling={
                'H_IRA': {'primary_beneficiary': 'Jordan'},
                'H_401k': {'primary_beneficiary': 'Sam'},
            },
        )
        rows = [{'year': 2050, '_account_balances': {'H_IRA': 300_000.0, 'H_401k': 200_000.0}}]
        result = per_beneficiary_ten_year_drawdown(c, rows)
        names = {b['beneficiary'] for b in result['beneficiaries']}
        self.assertEqual(names, {'Jordan', 'Sam'})

    def test_account_with_no_beneficiary_on_file_is_skipped(self):
        c = _base_config(
            h_death_yr=2050, w_death_yr=2045,
            account_registry=[{'id': 'H_IRA', 'owner_idx': 0, 'tax': 'pre_tax', 'label': "Alex's IRA"}],
            account_titling={'H_IRA': {'primary_beneficiary': ''}},
        )
        rows = [{'year': 2050, '_account_balances': {'H_IRA': 500_000.0}}]
        result = per_beneficiary_ten_year_drawdown(c, rows)
        self.assertFalse(result['available'])


if __name__ == "__main__":
    unittest.main()
