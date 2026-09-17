"""Survivor-bucket memoization must never serve buckets across different configs.

The three call sites do not all pass the same config: the Roth optimizer uses
the PRE-optimization base, while monte_carlo and the Sheet 10 sweep use the
post-optimization config. Bucket flows come from a full projection off that
config, so a key that ignores Roth policy would serve wrong trajectories.
"""
from __future__ import annotations

import unittest

from src.planning_engines import _survivor_bucket_cache_key


class SurvivorBucketCacheKey(unittest.TestCase):
    def _cfg(self, **over):
        base = {
            'members': [{'name': 'H'}, {'name': 'W'}],
            'plan_start': 2026, 'plan_end': 2060,
            'h_death_yr': 2055, 'w_death_yr': 2060,
            'roth_policy': 'fill_to_bracket', 'spend_base': 120000.0,
        }
        base.update(over)
        return base

    def _rows(self):
        return [{'year': y} for y in range(2026, 2061)]

    def test_same_config_produces_the_same_key(self):
        self.assertEqual(
            _survivor_bucket_cache_key(self._cfg(), self._rows()),
            _survivor_bucket_cache_key(self._cfg(), self._rows()),
        )

    def test_roth_policy_change_produces_a_different_key(self):
        a = _survivor_bucket_cache_key(self._cfg(), self._rows())
        b = _survivor_bucket_cache_key(self._cfg(roth_policy='none'), self._rows())
        self.assertNotEqual(a, b, "Roth policy changes bucket flows and must be in the key")

    def test_spending_change_produces_a_different_key(self):
        a = _survivor_bucket_cache_key(self._cfg(), self._rows())
        b = _survivor_bucket_cache_key(self._cfg(spend_base=200000.0), self._rows())
        self.assertNotEqual(a, b)

    def test_death_year_change_produces_a_different_key(self):
        a = _survivor_bucket_cache_key(self._cfg(), self._rows())
        b = _survivor_bucket_cache_key(self._cfg(h_death_yr=2040), self._rows())
        self.assertNotEqual(a, b)


if __name__ == '__main__':
    unittest.main()
