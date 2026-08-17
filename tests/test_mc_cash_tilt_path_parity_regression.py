"""The scalar and vectorized Monte Carlo paths must agree about cash.

Finding S5 (documentation/reports/PLANNER_SIGNOFF_2026-08-17.md): the vectorized
path excludes cash-tax accounts from tilting -- it grows cash on a short-rate
proxy tied to inflation, so a tilt measured against the equity draw is
meaningless there -- while the scalar/loop path
(``_apply_account_return_adjustments``) applied a tilt to any account present in
``account_returns``, cash-tax or not.

On the frozen fixture the two paths agree only by accident: its cash accounts
hold nothing that maps to a capital-market-assumption class, so they never
appear in ``account_returns`` and neither path tilts them. The divergence is
therefore invisible to every existing test. A plan holding a money-market fund
that DOES map to a CMA class inside a cash account separates them, so that is
the fixture used below -- per §3 rule 3, assert on the observable that
distinguishes the two implementations rather than on one they share.
"""

from __future__ import annotations

import unittest

from src.planning_engines import (
    _apply_account_return_adjustments,
    _mc_bucket_return_tilts,
)


def _plan_with_money_market_in_a_cash_account() -> dict:
    """A cash account whose holding maps to a CMA class, so it earns a tilt.

    ``mm1`` sits in a cash-tax account and carries an absolute return well away
    from the 5% plan return, which is what makes an erroneous tilt visible
    rather than merely present.
    """
    return {
        'ret': 0.05,
        'invest_ids': ['ira1', 'cash_mm'],
        'balances': {'ira1': 1_000_000.0, 'cash_mm': 250_000.0},
        'account_registry': [
            {'id': 'ira1', 'tax': 'pre_tax'},
            {'id': 'cash_mm', 'tax': 'cash'},
        ],
        'account_returns': {
            'ira1': 0.0600,     # tilt +0.01
            'cash_mm': 0.0250,  # tilt -0.025 -- the one that must NOT be applied
        },
    }


class CashTiltPathParityTests(unittest.TestCase):

    def test_scalar_path_does_not_tilt_a_cash_account(self):
        c = _plan_with_money_market_in_a_cash_account()
        adjusted = _apply_account_return_adjustments(c, {2030: 0.05, 2031: 0.05}, [2030, 2031])

        self.assertNotIn(
            'cash_mm', adjusted,
            "The scalar MC path tilted a cash-tax account against the equity "
            "return. The vectorized path -- which produces the headline success "
            "rate -- grows cash on a short-rate proxy instead, so this makes the "
            "two paths report different outcomes for the same plan (finding S5).",
        )

    def test_non_cash_accounts_still_get_their_tilt(self):
        """The exclusion must be surgical: a fix that simply stopped tilting
        would also pass the test above, so pin the behavior it must preserve."""
        c = _plan_with_money_market_in_a_cash_account()
        adjusted = _apply_account_return_adjustments(c, {2030: 0.05}, [2030])

        self.assertIn('ira1', adjusted)
        self.assertAlmostEqual(adjusted['ira1'][2030], 0.06, places=10)

    def test_both_mc_paths_agree_on_which_accounts_are_tilted(self):
        """The parity claim itself, asserted against both implementations.

        ``_mc_bucket_return_tilts`` must produce no cash bucket, and the scalar
        adjustment map must contain no cash account -- for the same plan. This
        is the assertion that goes red if either side is changed in isolation
        later.
        """
        c = _plan_with_money_market_in_a_cash_account()

        bucket_tilts = _mc_bucket_return_tilts(c)
        scalar_tilted = set(_apply_account_return_adjustments(c, {2030: 0.05}, [2030]))

        self.assertNotIn('cash', bucket_tilts)
        self.assertEqual(scalar_tilted, {'ira1'})
        # The pretax bucket is the only one either path tilts, and the cash
        # account's -0.025 must not have leaked into it via the 'taxable'
        # default bucket mapping.
        self.assertEqual(set(bucket_tilts), {'pretax'})
        self.assertAlmostEqual(bucket_tilts['pretax'], 0.01, places=10)


if __name__ == '__main__':
    unittest.main()
