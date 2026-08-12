"""Ticket 287: annualized spending extrapolates over the period the DATA covers.

Annualizing observed spending is a run-rate extrapolation, so the denominator
must be the span the transaction log actually covers -- Jan 1 through the last
recorded transaction -- not Jan 1 through today. When the log runs to Jul 31 but
today is Aug 12, dividing by 224 elapsed days instead of 212 understates the run
rate by ~5%, and the gap grows with every day the import lags.

This is the convention ``ytd_tracking.py`` already applies (``ytd_end =
max(current_year_dates)``, ~line 1009), which is why the YTD Tracking page and
Spending Analysis disagreed on the same household. These tests pin
``spending_tracker`` to that same rule.

Deliberately NOT changed, and asserted here so it is not "fixed" by mistake
later: ``ytd_projection_blend._remaining_fraction`` stays anchored to today.
That answers a different question -- how much of the year is left to spend --
and the calendar keeps moving whether or not anyone imported transactions.
Its own comment (ytd_projection_blend.py ~221) records that reasoning.
"""

from __future__ import annotations

import unittest
from datetime import date

from src.spending_tracker import _annualization_period_days


class AnnualizationPeriodTests(unittest.TestCase):

    def _txns(self, *days: tuple[int, int]):
        return [{"date": date(2026, m, d), "amount": -100.0} for m, d in days]

    def test_period_ends_at_the_last_transaction_not_today(self):
        """The reported defect, stated directly."""
        txns = self._txns((1, 15), (7, 31))
        days = _annualization_period_days(txns, 2026, today=date(2026, 8, 12))
        # Jan 1 -> Jul 31 inclusive = 212 days, NOT Jan 1 -> Aug 12 (224).
        self.assertEqual(days, 212)

    def test_understatement_it_removes_is_material(self):
        """Guard the magnitude, so a future refactor that quietly reverts to a
        today-anchored denominator fails on the number a user would notice."""
        txns = self._txns((7, 31))
        spend = 100_000.0
        data_days = _annualization_period_days(txns, 2026, today=date(2026, 8, 12))
        calendar_days = (date(2026, 8, 12) - date(2026, 1, 1)).days + 1

        annualized_now = spend * 365.0 / data_days
        annualized_before = spend * 365.0 / calendar_days
        self.assertGreater(annualized_now, annualized_before)
        self.assertAlmostEqual(annualized_now, 172_169.81, places=2)
        self.assertAlmostEqual(annualized_before, 162_946.43, places=2)

    def test_completed_prior_year_uses_the_whole_year(self):
        """A finished year is complete data, not a partial run rate.

        Without this branch a 2025 log whose last entry is Nov 15 would be
        extrapolated by 365/319, inflating a historical year that needs no
        extrapolation at all. ytd_tracking.py makes the same exception.
        """
        txns = [{"date": date(2025, m, d)} for m, d in ((3, 2), (11, 15))]
        days = _annualization_period_days(txns, 2025, today=date(2026, 8, 12))
        self.assertEqual(days, 365)

    def test_future_dated_transaction_cannot_stretch_the_period(self):
        """A single mis-keyed future date must not collapse the factor to ~1.0.

        Date-entry slips land in the future far more often than legitimately
        (a 2026-12-31 typo), and the failure is silent: the period stretches,
        the factor falls, and annualized spending is understated -- the very
        defect this ticket is about, reintroduced from the other direction.
        """
        txns = self._txns((7, 31), (12, 31))
        days = _annualization_period_days(txns, 2026, today=date(2026, 8, 12))
        self.assertEqual(days, 224)  # clamped at today, not stretched to Dec 31

    def test_no_transactions_falls_back_to_today(self):
        """Actuals are zero here so the factor is academic -- but it must not
        divide by zero or return a nonsense period."""
        self.assertEqual(
            _annualization_period_days([], 2026, today=date(2026, 8, 12)), 224
        )

    def test_single_january_transaction_still_yields_a_sane_period(self):
        txns = self._txns((1, 3))
        self.assertEqual(
            _annualization_period_days(txns, 2026, today=date(2026, 8, 12)), 3
        )

    def test_blend_remaining_fraction_stays_today_anchored(self):
        """The deliberate counterpart -- see this module's docstring."""
        from src.ytd_projection_blend import _remaining_fraction

        # Two-thirds of 2026 gone by Sep 1 regardless of the transaction log.
        frac = _remaining_fraction(date(2026, 9, 1))
        self.assertAlmostEqual(frac, 1.0 - (244 / 365.0), places=6)


if __name__ == "__main__":
    unittest.main()
