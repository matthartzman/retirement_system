"""The annuity payment memo must be per-projection, never per-stream.

A memo attached to a stream dict would survive run_scenario's deepcopy and
serve pre-override values to a scenario that changed that stream -- silently
wrong numbers in every stress sheet. This pins the memo's scope.
"""
from __future__ import annotations

import unittest

from src.projection_stages.portfolio_growth_and_net_worth import _annuity_pmt


class AnnuityPmtMemoScope(unittest.TestCase):
    def _stream(self, init_pmt: float) -> dict:
        return {
            'first_yr': 2030, 'base': 0.0, 'div_rate': 0.0,
            'add_pct': 0.0, 'init_pmt': init_pmt,
        }

    def test_memo_is_keyed_per_config_not_shared_across_configs(self):
        stream_a = self._stream(100.0)
        c_a = {'wife_single': stream_a}
        first = _annuity_pmt(c_a, 'wife_single', stream_a, 2031)

        # A different scenario mutated the stream's payment. A correctly
        # scoped memo lives on the new config, so it must NOT return c_a's value.
        stream_b = self._stream(500.0)
        c_b = {'wife_single': stream_b}
        second = _annuity_pmt(c_b, 'wife_single', stream_b, 2031)

        self.assertAlmostEqual(first, 100.0 * 12)
        self.assertAlmostEqual(second, 500.0 * 12)

    def test_memo_does_not_write_to_the_stream_dict(self):
        stream = self._stream(100.0)
        c = {'wife_single': stream}
        before = set(stream)
        _annuity_pmt(c, 'wife_single', stream, 2031)
        self.assertEqual(
            set(stream) - before, set(),
            "memo must live on the config, not the stream",
        )

    def test_repeated_lookups_return_identical_values(self):
        stream = self._stream(100.0)
        c = {'wife_single': stream}
        vals = [_annuity_pmt(c, 'wife_single', stream, 2035) for _ in range(3)]
        self.assertEqual(len(set(vals)), 1)


if __name__ == '__main__':
    unittest.main()
