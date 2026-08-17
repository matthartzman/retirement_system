"""The Monte Carlo bucket tilts must redistribute return, never create it.

`_mc_bucket_return_tilts` turns per-account holdings differences into one
constant tilt per tax bucket, and the vectorized MC adds those constants to the
sampled portfolio return. `_account_return_tilt`'s docstring states the property
that makes this legitimate:

    "Tilts are dollar-weighted to approximately zero across the portfolio by
     construction, so applying them preserves the plan's expected return as the
     portfolio-wide average while letting asset location redistribute it."

Preserving the plan's expected return is a **conservation** claim: growing the
buckets at their tilted rates must leave the portfolio total exactly where the
untilted sampled return would have left it. Anything else is a return the engine
invented, applied to every path, every year.

That claim held only at t=0, and only approximately. The tilts are computed once
from the opening balance mix and then applied unchanged for the whole horizon,
while withdrawal sequencing, RMDs and Roth conversions reshape that mix
underneath them -- draining the negatively-tilted pretax bucket and filling the
positively-tilted Roth one. Measured on the frozen fixture before this guard
existed, the effective portfolio-wide tilt drifted monotonically upward:

    2026 +4.3 bps -> 2036 +7.6 -> 2046 +15.0 -> 2056 +24.9 bps

i.e. a tailwind that grows through exactly the late years where Monte Carlo
success or failure is decided, and which every recommended Roth conversion
feeds, because converted dollars inherit the Roth account's holdings tilt.

See documentation/reports/PLANNER_SIGNOFF_2026-08-17.md findings S2/S3 -- S3
being that the pre-existing test named "..._and_market_neutral" checked dollar
weighting and never checked neutrality, which is why this went unnoticed. That
test has since been renamed to test_bucket_return_tilts_are_dollar_weighted
(P3); this file is the only place neutrality is actually asserted.
"""

from __future__ import annotations

import unittest

import numpy as np

from src.planning_engines import _mc_apply_bucket_growth

BUCKETS = ('taxable', 'pretax', 'roth', 'hsa')

# The bucket tilts the frozen sample plan actually produces, to 7 places.
FROZEN_TILTS = {
    'hsa': 0.0030180,
    'pretax': -0.0005381,
    'roth': 0.0024865,
    'taxable': 0.0013327,
}


def _arr(**kw):
    return {b: np.array([float(kw.get(b, 0.0))]) for b in BUCKETS}


def _total(balances):
    return float(sum(balances[b].sum() for b in BUCKETS))


class BucketTiltNeutralityTests(unittest.TestCase):

    def test_tilts_do_not_change_the_portfolio_total_at_the_opening_mix(self):
        """Growth of the whole portfolio must equal the sampled return exactly."""
        balances = _arr(pretax=1_891_638, roth=357_126, taxable=560_390, hsa=74_998)
        before = _total(balances)
        growth = np.array([0.05])

        after = _total(_mc_apply_bucket_growth(balances, growth, dict(FROZEN_TILTS)))

        self.assertAlmostEqual(after, before * 1.05, places=4)

    def test_tilts_do_not_change_the_portfolio_total_at_a_late_horizon_mix(self):
        """The regression this file exists for.

        By the 2050s the frozen plan's portfolio is overwhelmingly Roth, whose
        tilt is +24.9 bps. Applying the opening mix's constants to that mix used
        to hand the portfolio the full +24.9 bps as free return, every path,
        every remaining year.
        """
        balances = _arr(roth=1_200_000, hsa=150_000, pretax=50_000, taxable=58_598)
        before = _total(balances)
        growth = np.array([0.05])

        after = _total(_mc_apply_bucket_growth(balances, growth, dict(FROZEN_TILTS)))

        self.assertAlmostEqual(after, before * 1.05, places=4)

    def test_neutrality_holds_for_a_single_surviving_bucket(self):
        """The degenerate end state: one bucket left, so its tilt IS the
        portfolio's. There is nothing left to redistribute against, so the tilt
        must vanish rather than apply."""
        balances = _arr(roth=1_000_000)
        growth = np.array([0.05])

        after = _mc_apply_bucket_growth(balances, growth, dict(FROZEN_TILTS))

        self.assertAlmostEqual(float(after['roth'][0]), 1_050_000.0, places=4)

    def test_neutrality_holds_independently_on_every_simulated_path(self):
        """Balances are (n_paths,) arrays and paths diverge, so a single
        portfolio-wide correction computed off one path would be wrong for the
        others. Each path must be normalized against its own mix."""
        balances = {
            'pretax': np.array([1_000_000.0, 10_000.0]),
            'roth': np.array([10_000.0, 1_000_000.0]),
            'taxable': np.array([0.0, 0.0]),
            'hsa': np.array([0.0, 0.0]),
        }
        totals_before = sum(balances[b] for b in BUCKETS).copy()
        growth = np.array([0.05, 0.05])

        after = _mc_apply_bucket_growth(balances, growth, dict(FROZEN_TILTS))
        totals_after = sum(after[b] for b in BUCKETS)

        np.testing.assert_allclose(totals_after, totals_before * 1.05, rtol=1e-9)

    def test_tilts_still_redistribute_between_buckets(self):
        """Neutrality must not be achieved by discarding the tilts.

        Zeroing everything would satisfy every assertion above and silently undo
        Wave 3.5. The SPREAD between buckets is the deliverable and must survive
        untouched -- only the portfolio-wide mean is removed.
        """
        balances = _arr(pretax=1_000_000, roth=1_000_000)
        growth = np.array([0.05])

        after = _mc_apply_bucket_growth(balances, growth, dict(FROZEN_TILTS))

        pretax_rate = float(after['pretax'][0]) / 1_000_000.0 - 1.0
        roth_rate = float(after['roth'][0]) / 1_000_000.0 - 1.0

        self.assertGreater(roth_rate, pretax_rate)
        self.assertAlmostEqual(
            roth_rate - pretax_rate,
            FROZEN_TILTS['roth'] - FROZEN_TILTS['pretax'],
            places=10,
            msg='the tilt spread is the Wave 3.5 deliverable and must be preserved exactly',
        )

    def test_no_tilts_is_bit_identical_to_the_untilted_path(self):
        """Plans without holdings detail produce no tilts at all, and must be
        completely unmoved by anything in this file."""
        balances = _arr(pretax=1_000_000, roth=500_000, taxable=250_000, hsa=75_000)
        growth = np.array([0.0523])

        after = _mc_apply_bucket_growth(balances, growth, {})

        for bucket, opening in (
            ('pretax', 1_000_000.0), ('roth', 500_000.0),
            ('taxable', 250_000.0), ('hsa', 75_000.0),
        ):
            self.assertEqual(float(after[bucket][0]), opening * 1.0523)


if __name__ == '__main__':
    unittest.main()
