"""F1.2 Acceptance test: MC per-account returns diverge across sleeves (Wave 3.5 completion).

Validates that Monte Carlo projections respect per-account return adjustments based on
asset location (holdings mix). This test verifies the code path and logic without
requiring a full engine configuration; detailed integration testing occurs in the
frozen-master gate and regression test suite.

Reference: planning_engines._account_return, data_io.account_returns (Wave 3.5),
REMAINING_WORK_PLAN_2026-08-12.md §F1.1-F1.2.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from src.planning_engines import (
    _account_return,
    _apply_account_return_adjustments,
    _mc_bucket_return_tilts,
)

ROOT = Path(__file__).resolve().parents[1]


class MonteCarloPerAccountReturnsTests(unittest.TestCase):
    """F1.2: Acceptance test for per-account MC returns (Wave 3.5 completion)."""

    def test_account_return_prefers_per_account_per_year_path(self):
        """Verify _account_return uses return_by_account_by_year when available.

        The _account_return function should check per-account per-year returns first,
        falling back to the single return_by_year only when per-account is unavailable.
        This enables asset-location-aware MC paths.
        """
        c = {
            'account_returns': {
                'cash_reserve': 0.03,
                'growth_roth': 0.08,
            },
            'return_by_account_by_year': {
                'cash_reserve': {2026: 0.025, 2027: 0.032},
                'growth_roth': {2026: 0.085, 2027: 0.075},
            },
            'return_by_year': {2026: 0.06, 2027: 0.062},  # Fallback (old path)
        }

        # Test: per-account path is preferred over return_by_year
        self.assertAlmostEqual(
            _account_return(c, 'cash_reserve', 0.0, year=2026),
            0.025,
            places=5,
            msg='Should use return_by_account_by_year[account_id][year]'
        )
        self.assertAlmostEqual(
            _account_return(c, 'growth_roth', 0.0, year=2027),
            0.075,
            places=5,
            msg='Should use return_by_account_by_year for growth_roth in 2027'
        )

    def test_account_return_falls_back_to_uniform_when_no_per_account_path(self):
        """Verify _account_return falls back to return_by_year when per-account unavailable.

        Old behavior: all accounts use the same return_by_year value.
        New behavior: prefer per-account returns when available.
        """
        c = {
            'account_returns': {'cash_reserve': 0.03},
            'return_by_year': {2026: 0.06},  # Fallback for accounts without per-year path
        }

        # cash_reserve is not in return_by_account_by_year, so falls back to return_by_year
        result = _account_return(c, 'cash_reserve', 0.0, year=2026)
        self.assertAlmostEqual(result, 0.06, places=5)

    def test_apply_account_return_adjustments_creates_per_year_paths(self):
        """Verify _apply_account_return_adjustments builds per-account per-year dict.

        ``c['account_returns']`` holds ABSOLUTE expected rates, not deltas --
        data_io writes ``_base_ret + (acct_ret - portfolio_ret)`` (data_io.py
        ~2425), i.e. the plan return plus that account's tilt. So the amount to
        carry onto a simulated path is the account's tilt *relative to* the
        plan-wide return, which is ``account_returns[acct] - c['ret']``.

        An earlier version added the absolute rate to the simulated return,
        which roughly doubled every account's growth: with c['ret']=0.05 and a
        5.5% simulated year, a 4.98% IRA came out at 10.48%.
        """
        c = {
            'ret': 0.05,
            'invest_ids': ['cash_reserve', 'growth_roth'],
            'account_returns': {
                'cash_reserve': 0.02,    # absolute 2%  -> tilt -3% vs the 5% plan return
                'growth_roth': 0.07,     # absolute 7%  -> tilt +2%
            },
        }
        base_returns = {2026: 0.06, 2027: 0.065}
        years = [2026, 2027]

        result = _apply_account_return_adjustments(c, base_returns, years)

        # cash_reserve tilt -3%: 6% - 3% = 3%, 6.5% - 3% = 3.5%
        self.assertAlmostEqual(result['cash_reserve'][2026], 0.03, places=10)
        self.assertAlmostEqual(result['cash_reserve'][2027], 0.035, places=10)

        # growth_roth tilt +2%: 6% + 2% = 8%, 6.5% + 2% = 8.5%
        self.assertAlmostEqual(result['growth_roth'][2026], 0.08, places=10)
        self.assertAlmostEqual(result['growth_roth'][2027], 0.085, places=10)

    def test_real_account_returns_do_not_double_the_simulated_return(self):
        """Regression: the units bug, stated against REAL fixture data.

        The unit tests above can be satisfied by any consistent convention.
        This one pins the convention against what data_io actually writes, so
        a future change that reinterprets account_returns fails here rather
        than silently doubling every simulated return.
        """
        from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config
        from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

        with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
            c = _frozen_config()

        simulated = 0.0550
        adj = _apply_account_return_adjustments(c, {2030: simulated}, [2030])
        self.assertTrue(adj, "frozen fixture should populate account_returns")

        for acct, by_year in adj.items():
            rate = by_year[2030]
            # Every account must land within a plausible tilt of the simulated
            # return. Doubling (~0.105) is the failure this catches.
            self.assertLess(
                abs(rate - simulated), 0.03,
                f"{acct} returned {rate:.4f} against a simulated {simulated:.4f} -- "
                "account_returns is being treated as a delta when it holds an "
                "absolute rate.",
            )

    def test_bucket_return_tilts_are_dollar_weighted(self):
        """The vectorized MC grows tax BUCKETS, not accounts, so per-account
        tilts must be dollar-weighted into per-bucket tilts.

        Weighting matters: a $10k bond-heavy IRA and a $1M one cannot move the
        pretax bucket equally. Averaging the rates instead of weighting them is
        the obvious wrong implementation, so this fixture makes the two answers
        differ (simple mean = +0.02, dollar-weighted = ~+0.0373).

        Scope: dollar weighting ONLY. This test was previously named
        "..._and_market_neutral", but nothing in the body ever asserted market
        neutrality -- the claim existed only in the identifier, which is how the
        tilt-drift defect went unnoticed (finding S3). Neutrality is covered by
        tests/test_mc_bucket_tilt_neutrality_regression.py; do not re-add the
        claim to this name without assertions behind it.
        """
        c = {
            'ret': 0.05,
            'invest_ids': ['ira_small', 'ira_big', 'roth1'],
            'balances': {'ira_small': 10_000.0, 'ira_big': 1_000_000.0, 'roth1': 500_000.0},
            'account_registry': [
                {'id': 'ira_small', 'tax': 'pre_tax'},
                {'id': 'ira_big', 'tax': 'pre_tax'},
                {'id': 'roth1', 'tax': 'roth'},
            ],
            'account_returns': {
                'ira_small': 0.01,   # tilt -0.04, tiny balance
                'ira_big': 0.0875,   # tilt +0.0375, dominant balance
                'roth1': 0.07,       # tilt +0.02
            },
        }
        tilts = _mc_bucket_return_tilts(c)

        self.assertAlmostEqual(tilts['roth'], 0.02, places=10)
        # Dollar-weighted: (10k*-0.04 + 1M*0.0375) / 1.01M
        expected = (10_000.0 * -0.04 + 1_000_000.0 * 0.0375) / 1_010_000.0
        self.assertAlmostEqual(tilts['pretax'], expected, places=10)
        self.assertNotAlmostEqual(tilts['pretax'], (-0.04 + 0.0375) / 2, places=4)

    def test_vectorized_mc_actually_applies_the_bucket_tilts(self):
        """The defect this whole item exists to fix, one level up.

        Wave 3.5 wired per-account returns into the deterministic path only;
        the follow-up wired the SCALAR Monte Carlo path. Neither touched the
        VECTORIZED path -- the one that produces the headline success rate --
        so the number users actually see was unchanged by both. Asserting on
        the helper alone would pass in exactly that state, so this asserts
        that the vectorized projection itself responds.
        """
        import numpy as _np
        from src.planning_engines import _mc_apply_bucket_growth

        balances = {
            'pretax': _np.array([100_000.0]),
            'roth': _np.array([100_000.0]),
            'taxable': _np.array([100_000.0]),
            'hsa': _np.array([100_000.0]),
        }
        growth = _np.array([0.05])

        flat = _mc_apply_bucket_growth(dict(balances), growth, {})
        tilted = _mc_apply_bucket_growth(
            dict(balances), growth, {'pretax': -0.02, 'roth': +0.02},
        )

        self.assertAlmostEqual(float(flat['pretax'][0]), 105_000.0, places=6)
        self.assertAlmostEqual(float(flat['roth'][0]), 105_000.0, places=6)
        # A bond-heavy IRA must grow slower and a growth Roth faster.
        self.assertAlmostEqual(float(tilted['pretax'][0]), 103_000.0, places=6)
        self.assertAlmostEqual(float(tilted['roth'][0]), 107_000.0, places=6)
        # Untilted buckets are untouched.
        self.assertAlmostEqual(float(tilted['taxable'][0]), 105_000.0, places=6)

    def test_mc_per_account_returns_criterion(self):
        """Document the criterion for Wave 3.5 completion (F1.2 acceptance).

        Per-account MC returns are complete when:
        1. _apply_account_return_adjustments builds return_by_account_by_year
        2. _account_return prefers return_by_account_by_year[acct][year]
        3. _run_one_mc_path populates return_by_account_by_year before projecting
        4. Full-suite testing (golden master, frozen build) shows success-rate convergence

        This unit test validates (1) and (2); integration tests validate (3) and (4).
        """
        # Criterion (1): function exists and creates correct structure
        c = {'invest_ids': ['a', 'b'], 'account_returns': {'a': 0.01, 'b': -0.01}}
        adj = _apply_account_return_adjustments(c, {2026: 0.06}, [2026])
        self.assertIn('a', adj)
        self.assertIn(2026, adj['a'])

        # Criterion (2): _account_return routes correctly
        c['return_by_account_by_year'] = adj
        rate_a = _account_return(c, 'a', 0.0, year=2026)
        self.assertAlmostEqual(rate_a, 0.07, places=5)  # 0.06 + 0.01


if __name__ == '__main__':
    unittest.main()
