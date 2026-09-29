"""WI-303 / FIN-013: RMD_DIVISORS must match IRS Publication 590-B, Appendix B,
Table III (Uniform Lifetime Table, 2022+) row by row through age 120 ("120 and
over"), and ages past the table use the final row rather than an extrapolation.

VERIFIED 2026-09-29: all 49 rows (ages 72-120) were compared programmatically with
Table III in IRS Publication 590-B (2025), Appendix B, page 67 of the PDF supplied
by the owner; none differ. Re-verify against the IRS PDF whenever Pub. 590-B is
refreshed.
"""
from __future__ import annotations

import pytest

from src.core import RMD_DIVISORS
from src.tax_kernel import rmd_divisor

PUB_590B_TABLE_III = {
    72: 27.4, 73: 26.5, 74: 25.5, 75: 24.6, 76: 23.7, 77: 22.9, 78: 22.0, 79: 21.1,
    80: 20.2, 81: 19.4, 82: 18.5, 83: 17.7, 84: 16.8, 85: 16.0, 86: 15.2, 87: 14.4,
    88: 13.7, 89: 12.9, 90: 12.2, 91: 11.5, 92: 10.8, 93: 10.1, 94: 9.5, 95: 8.9,
    96: 8.4, 97: 7.8, 98: 7.3, 99: 6.8, 100: 6.4, 101: 6.0, 102: 5.6, 103: 5.2,
    104: 4.9, 105: 4.6, 106: 4.3, 107: 4.1, 108: 3.9, 109: 3.7, 110: 3.5,
    111: 3.4, 112: 3.3, 113: 3.1, 114: 3.0, 115: 2.9, 116: 2.8, 117: 2.7,
    118: 2.5, 119: 2.3, 120: 2.0,
}


def test_rmd_divisors_match_pub_590b_table_iii_row_by_row():
    assert RMD_DIVISORS == PUB_590B_TABLE_III


def test_age_83_divisor_is_17_7():
    assert rmd_divisor(83) == 17.7


@pytest.mark.parametrize("age,expected", [(116, 2.8), (117, 2.7), (118, 2.5), (119, 2.3), (120, 2.0)])
def test_post_115_rows_come_from_the_table(age, expected):
    assert rmd_divisor(age) == expected


@pytest.mark.parametrize("age", [121, 125, 130])
def test_ages_past_120_use_the_120_and_over_row(age):
    assert rmd_divisor(age) == 2.0


def test_table_is_strictly_decreasing():
    ages = sorted(RMD_DIVISORS)
    for a, b in zip(ages, ages[1:]):
        assert RMD_DIVISORS[a] > RMD_DIVISORS[b], (a, b)
