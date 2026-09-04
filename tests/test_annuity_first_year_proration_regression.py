"""Regression test: annuity/pension income streams paid a full 12 months in
their first calendar year of income regardless of what month `first_payment`
actually fell in, because src/core.py's annuity_cash_income() only ever
worked in whole calendar years -- src/data_io.py's load_stream() discarded
the month/day of `first_payment` and kept only the year (`.split('/')[-1]`).
A stream whose contract said "first payment 6/1/2026" showed 12 months of
cash flow in 2026 instead of 7 (June through December).

Fix: load_stream() now also captures the payment month, and
annuity_cash_income() prorates the CASH ACTUALLY PAID in the first income
year only -- the internal reserve/compounding math (which drives every
LATER year's guaranteed-payment growth) still operates on full-year
increments, matching how these contracts actually work: the carrier's
"guaranteed annual payment" is a full-year figure for crediting purposes;
only the dollars an annuitant collects in a partial stub year are prorated.
"""
from __future__ import annotations

from src.core import annuity_cash_income


def _base_stream(**overrides):
    stream = {
        "first_yr": 2026,
        "first_payment_month": 1,
        "base": 100_000.0,
        "div_rate": 0.05,
        "add_pct": 0.2,
        "init_pmt": 500.0,
        "deferral_years": 0,
        "deferral_dampening": 0.55,
        "reserve_factor": 0.853,
        "annuitant_dob_yr": 1961,
        "recovery_age": 86,
        "annuity_calib": None,
    }
    stream.update(overrides)
    return stream


class TestAnnuityFirstYearProration:
    def test_january_first_payment_pays_a_full_year(self):
        stream = _base_stream(first_payment_month=1)
        full_year = annuity_cash_income(stream, 2026)
        # January start: nothing to prorate away, 12/12 of the year.
        assert full_year == annuity_cash_income(_base_stream(first_payment_month=1), 2026)
        assert full_year > 0

    def test_june_first_payment_pays_roughly_seven_twelfths(self):
        june_stream = _base_stream(first_payment_month=6)
        jan_stream = _base_stream(first_payment_month=1)
        june_amount = annuity_cash_income(june_stream, 2026)
        jan_amount = annuity_cash_income(jan_stream, 2026)
        assert jan_amount > 0
        ratio = june_amount / jan_amount
        # June 1 -> 7 remaining months (Jun-Dec) of a 12-month year.
        assert abs(ratio - 7 / 12) < 1e-9

    def test_december_first_payment_pays_roughly_one_twelfth(self):
        dec_stream = _base_stream(first_payment_month=12)
        jan_stream = _base_stream(first_payment_month=1)
        dec_amount = annuity_cash_income(dec_stream, 2026)
        jan_amount = annuity_cash_income(jan_stream, 2026)
        ratio = dec_amount / jan_amount
        assert abs(ratio - 1 / 12) < 1e-9

    def test_proration_applies_only_to_the_first_income_year(self):
        # The second year of income should NOT be prorated -- only the stub
        # first year is partial; every later year is a full 12 months.
        june_stream = _base_stream(first_payment_month=6)
        jan_stream = _base_stream(first_payment_month=1)
        june_year2 = annuity_cash_income(june_stream, 2027)
        jan_year2 = annuity_cash_income(jan_stream, 2027)
        assert abs(june_year2 - jan_year2) < 1e-6

    def test_pure_guaranteed_payment_stream_base_zero_also_prorates(self):
        # QLAC-style streams collapse to base=0 (see load_qlac in data_io.py)
        # and take the early-return branch in annuity_cash_income -- must be
        # prorated too, not just the general reserve-based branch.
        june_stream = _base_stream(first_payment_month=6, base=0.0)
        jan_stream = _base_stream(first_payment_month=1, base=0.0)
        june_amount = annuity_cash_income(june_stream, 2026)
        jan_amount = annuity_cash_income(jan_stream, 2026)
        assert jan_amount > 0
        assert abs(june_amount / jan_amount - 7 / 12) < 1e-9

    def test_missing_first_payment_month_defaults_to_no_proration(self):
        # Streams without a real M/D/YYYY first_payment (legacy/blank data)
        # must keep paying a full first year, matching pre-fix behavior --
        # this is a backward-compatibility guard, not a new feature.
        stream = _base_stream()
        del stream["first_payment_month"]
        assert annuity_cash_income(stream, 2026) == annuity_cash_income(
            _base_stream(first_payment_month=1), 2026
        )
