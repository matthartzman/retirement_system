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

from src.planning_engines import _account_return, _apply_account_return_adjustments

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

        Given account_returns (scalar deltas) and a base return_by_year dict,
        create per-account adjusted returns for each year.
        """
        c = {
            'invest_ids': ['cash_reserve', 'growth_roth'],
            'account_returns': {
                'cash_reserve': -0.03,    # underperform portfolio by 3%
                'growth_roth': 0.02,     # outperform portfolio by 2%
            },
        }
        base_returns = {2026: 0.06, 2027: 0.065}
        years = [2026, 2027]

        result = _apply_account_return_adjustments(c, base_returns, years)

        # cash_reserve: 6% - 3% = 3%, 6.5% - 3% = 3.5%
        self.assertEqual(result['cash_reserve'][2026], 0.03)
        self.assertEqual(result['cash_reserve'][2027], 0.035)

        # growth_roth: 6% + 2% = 8%, 6.5% + 2% = 8.5%
        self.assertEqual(result['growth_roth'][2026], 0.08)
        self.assertEqual(result['growth_roth'][2027], 0.085)

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
