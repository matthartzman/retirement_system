"""WI-040 (FIN-007): Social Security earnings test, with hand-computed expected values.

2026 limits (dated rows, SSA-verified): 24,480 below FRA, 65,160 in the FRA year (2027: 25,560 and 67,920);
$1 withheld per $2 / $1 per $3 over the limit (42 USC 403(b)).
"""
from __future__ import annotations

import pytest

import src.data_io  # noqa: F401  (import order: avoids a parsing/data_io cycle)
from src.ss_earnings_test import earnings_test_withholding as withhold, fra_year_and_month
from src.tax_law import default_tax_law_dataset

DS = default_tax_law_dataset()


def _w(year, earnings, benefit, dob=(1962, 8), fra=67.0, inf=0.0):
    return withhold(DS, year=year, brk_inf=inf, dob_year=dob[0], dob_month=dob[1], fra_years=fra,
                    earnings=earnings, annual_benefit=benefit)


def test_fra_month():
    assert fra_year_and_month(1962, 8, 67.0) == (2029, 7)
    assert fra_year_and_month(1960, 1, 67.0) == (2027, 0)


def test_below_fra_all_year_example():
    # Wages 40,000 vs 24,480: excess 15,520, withheld 7,760.
    assert _w(2026, 40_000, 30_000) == pytest.approx(7_760.0)
    # Never more than the benefit payable.
    assert _w(2026, 200_000, 30_000) == 30_000
    assert _w(2026, 24_480, 30_000) == 0.0


def test_fra_year_example():
    # FRA in August 2029 -> 7 months tested. Earnings before FRA: 80,000 * 7/12 = 46,666.67 < 67,920.
    assert _w(2029, 80_000, 36_000) == 0.0
    # December FRA: 11 tested months, so 11/12 of 140,000 = 128,333.33 counts.
    dec = _w(2029, 140_000, 36_000, dob=(1962, 12))
    assert dec == pytest.approx((140_000 * 11 / 12 - 67_920) / 3)   # 2029 uses the 2027 row (no inflation here)
    # January FRA: no tested months.
    assert _w(2029, 400_000, 36_000, dob=(1962, 1)) == 0.0


def test_no_test_from_the_fra_year_end_or_after():
    assert _w(2030, 400_000, 36_000) == 0.0


def test_limits_use_the_published_2027_amount_then_index():
    # SSA publishes 25,560 (below FRA) and 67,920 (FRA year) for 2027; later years compound that row.
    assert _w(2027, 40_000, 30_000, inf=0.03) == pytest.approx((40_000 - 25_560) / 2)
    assert _w(2028, 40_000, 30_000, inf=0.03) == pytest.approx((40_000 - 25_560 * 1.03) / 2)


def test_earnings_test_rows_are_verified_and_cited():
    ds = DS
    for name in ("ss_earnings_test_annual_limit", "ss_earnings_test_fra_year_limit"):
        for year in (2026, 2027):
            row = ds.lookup(name, year)
            assert row.status == "verified" and "ssa.gov" in row.source
    assert ds.lookup("ss_earnings_test_annual_limit", 2026).value == 24_480
    assert ds.lookup("ss_earnings_test_fra_year_limit", 2026).value == 65_160


# ── Through the projection ─────────────────────────────────────────────────

def _scenario(earnings_end):
    from tests.rental_fixtures import base_config, project
    c = base_config()
    c.update(h_ss_claim_age=64, h_ss_claim_age_precise=64.0, h_ss_claim_year=2026, entity='sole_prop',
             earned=40_000.0, earn_inc=0.0, earn_start=2026, earn_end=earnings_end, biz_exp=0.0, home_off=0.0)
    c.pop('h_ss_claim_month', None)
    return {r['year']: r for r in project(c)}


def test_projection_withholds_then_credits_at_fra():
    working, retired = _scenario(2029), _scenario(2025)
    inf = base_inf()
    for year in (2027, 2028):   # full years under FRA; 2027 is the published amount, 2028 indexes it
        limit = 25_560 * (1 + inf) ** (year - 2027)
        expect = (40_000 - limit) / 2
        assert working[year]['h_ss_withheld_earnings_test'] == pytest.approx(expect)
        assert working[year]['h_ss'] == pytest.approx(retired[year]['h_ss'] - expect)
    assert 'h_ss_withheld_earnings_test' not in retired[2027]
    # After the FRA year the withheld months shrink the early-claim reduction: benefit is higher
    # than the no-earnings case, but never above the at-FRA amount.
    assert working[2031]['h_ss'] > retired[2031]['h_ss']


def base_inf():
    from tests.rental_fixtures import base_config
    return base_config()['brk_inf']
