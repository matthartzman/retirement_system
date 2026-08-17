"""A Liquidity Buffer's reserve_account must preserve the bucket it names.

Finding P8 (documentation/reports/PLANNER_SIGNOFF_2026-08-17.md): the field is a
live UI control, persisted to client_assets.csv and validated against
reference_data/schema.csv, and it was read by no engine code. `withdraw_taxable_trust`
applied the reserve floor to the taxable bucket unconditionally, so a user who
selected "Roth" or "HSA" silently got taxable treatment -- the opposite of what
they configured, since the bucket they asked to protect was left fully drainable
while a bucket they did not name was held back.

These tests assert on the observable that separates the two implementations: the
END BALANCE of the named bucket, projected through a year where the cascade is
forced to draw. Asserting only that the floor helper returns a number would pass
in exactly the broken state, because the helper was never the problem -- its
caller was.
"""

from __future__ import annotations

import unittest

from src.planning_engines import (
    liquidity_buffer_for_year,
    liquidity_reserve_floor,
    withdraw_hsa_gap,
    withdraw_pretax_elective,
    withdraw_roth,
    withdraw_taxable_trust,
)

SPEND = 100_000.0
YEARS = 2.0
FLOOR = SPEND * YEARS  # 200,000


def _plan(reserve_account: str) -> dict:
    """One account per bucket, each funded well above the reserve floor."""
    return {
        'plan_start': 2026,
        'liquidity_buffer_schedule': [{
            'start_year': 2026,
            'end_year': 2030,
            'years_of_expenses': YEARS,
            'reserve_account': reserve_account,
        }],
        'account_registry': [
            {'id': 'tax1', 'owner_idx': 0, 'tax': 'taxable'},
            {'id': 'ira1', 'owner_idx': 0, 'tax': 'pre_tax'},
            {'id': 'roth1', 'owner_idx': 0, 'tax': 'roth'},
            {'id': 'hsa1', 'owner_idx': 0, 'tax': 'hsa'},
            {'id': 'cash1', 'owner_idx': 0, 'tax': 'cash'},
        ],
        'hsa_ids': ['hsa1'],
        'pre_tax_ids': ['ira1'],
        'hsa_withdrawal_mode': 'spend_as_needed',
    }


def _balances() -> dict:
    return {'tax1': 500_000.0, 'ira1': 500_000.0, 'roth1': 500_000.0,
            'hsa1': 500_000.0, 'cash1': 500_000.0}


class ReserveAccountIsHonoredTests(unittest.TestCase):

    def test_taxable_reserve_still_floors_the_taxable_draw(self):
        """The pre-P8 behavior, pinned: a fix must not lose the working case."""
        bal = _balances()
        res = withdraw_taxable_trust(_plan('Taxable/Trust'), bal, 2027, 1_000_000.0, SPEND)
        self.assertAlmostEqual(res['amount'], 500_000.0 - FLOOR, places=6)

    def test_roth_reserve_floors_the_roth_draw(self):
        bal = _balances()
        res = withdraw_roth(_plan('Roth'), bal, 1_000_000.0, year=2027, spend_floor_base=SPEND)
        self.assertAlmostEqual(
            res['amount'], 500_000.0 - FLOOR, places=6,
            msg="a reserve configured against Roth did not hold Roth dollars back; "
                "before P8 this drew the full balance because the floor was "
                "hardwired to the taxable bucket",
        )

    def test_hsa_reserve_floors_the_hsa_gap_draw(self):
        bal = _balances()
        res = withdraw_hsa_gap(_plan('HSA'), bal, 1_000_000.0, year=2027, spend_floor_base=SPEND)
        self.assertAlmostEqual(res['amount'], 500_000.0 - FLOOR, places=6)

    def test_ira_reserve_floors_the_pretax_draw(self):
        bal = _balances()
        res = withdraw_pretax_elective(
            _plan('IRA'), bal, 1_000_000.0, 0.0, 0.0, 2027, 'MFJ',
            400_000.0, 400_000.0, 0.24,
            respect_tax_caps=False, spend_floor_base=SPEND,
        )
        self.assertAlmostEqual(res['amount'], 500_000.0 - FLOOR, places=6)

    def test_a_reserve_only_constrains_the_bucket_it_names(self):
        """The other half of honoring the field, and the actual pre-P8 bug.

        A Roth reserve must leave taxable fully drawable. Before P8 every
        reserve floored taxable regardless, so selecting Roth protected the
        wrong bucket AND restricted one the user never named.
        """
        bal = _balances()
        res = withdraw_taxable_trust(_plan('Roth'), bal, 2027, 1_000_000.0, SPEND)
        self.assertAlmostEqual(
            res['amount'], 500_000.0, places=6,
            msg="a Roth reserve restricted the TAXABLE draw -- the pre-P8 behavior, "
                "where reserve_account was ignored and every reserve was a taxable one",
        )

    def test_reserve_outside_its_configured_year_range_does_not_apply(self):
        bal = _balances()
        res = withdraw_taxable_trust(_plan('Taxable/Trust'), bal, 2035, 1_000_000.0, SPEND)
        self.assertAlmostEqual(res['amount'], 500_000.0, places=6)

    def test_unrecognized_reserve_account_falls_back_to_taxable(self):
        """Schema default and pre-P8 behavior, so old plans cannot shift."""
        years, bucket = liquidity_buffer_for_year(_plan('something else'), 2027)
        self.assertEqual(years, YEARS)
        self.assertEqual(bucket, 'taxable')

    def test_blank_reserve_account_falls_back_to_taxable(self):
        years, bucket = liquidity_buffer_for_year(_plan(''), 2027)
        self.assertEqual(bucket, 'taxable')

    def test_floor_is_zero_for_buckets_the_reserve_does_not_name(self):
        c = _plan('HSA')
        self.assertAlmostEqual(liquidity_reserve_floor(c, 2027, 'hsa', SPEND), FLOOR, places=6)
        for other in ('taxable', 'pretax', 'roth', 'cash'):
            self.assertAlmostEqual(liquidity_reserve_floor(c, 2027, other, SPEND), 0.0, places=6)


class CashReserveTests(unittest.TestCase):
    """Cash is the one bucket the deterministic cascade never draws from.

    Priorities are RMD, HSA, pre-tax elective, taxable/trust, Roth, home equity
    -- cash-tax accounts appear in none of them. So a cash reserve is preserved
    by construction rather than by a floor, and there is no draw to constrain.
    This is pinned rather than left implicit: if a cash draw is ever added to
    the cascade, this test is the reminder that it needs the floor applied, and
    `liquidity_reserve_floor(..., 'cash', ...)` already returns the right number
    for it to use.
    """

    def test_cash_reserve_resolves_to_the_cash_bucket(self):
        years, bucket = liquidity_buffer_for_year(_plan('Cash'), 2027)
        self.assertEqual((years, bucket), (YEARS, 'cash'))

    def test_cash_floor_is_available_for_a_future_cash_draw(self):
        self.assertAlmostEqual(
            liquidity_reserve_floor(_plan('Cash'), 2027, 'cash', SPEND), FLOOR, places=6)

    def test_a_cash_reserve_does_not_restrict_any_drawn_bucket(self):
        c = _plan('Cash')
        bal = _balances()
        self.assertAlmostEqual(
            withdraw_taxable_trust(c, bal, 2027, 1_000_000.0, SPEND)['amount'], 500_000.0, places=6)
        bal = _balances()
        self.assertAlmostEqual(
            withdraw_roth(c, bal, 1_000_000.0, year=2027, spend_floor_base=SPEND)['amount'],
            500_000.0, places=6)


if __name__ == '__main__':
    unittest.main()
