"""Social Security earnings test (WI-040, FIN-007; 42 USC 403(b)).

A pure kernel: a beneficiary under full retirement age (FRA) who still earns
wages or net self-employment income has benefits withheld. In every year before
the FRA year, $1 is withheld for each $2 earned over the annual limit; in the
year FRA is reached, $1 for each $3 earned over a higher limit, counting only
earnings before the month FRA is reached. From the FRA month on there is no test.
Withheld months are credited back at FRA (the early-claim reduction shrinks).

Limits are dated rows in ``tax_law_v10.json`` (owner-accepted 2026 figures,
status ``assumption`` until a source citation is attached); later years compound the
latest row by the plan's bracket inflation (no separate wage-growth assumption exists).
Own retirement benefit only: spousal benefits payable on a working spouse's record are
not withheld here (a documented limitation).
"""
from __future__ import annotations

from typing import Any


def fra_year_and_month(dob_year: int, dob_month: int, fra_years: float) -> tuple[int, int]:
    """Calendar year and 0-based month in which FRA is reached."""
    idx = int(dob_year) * 12 + (int(dob_month or 1) - 1) + int(round(float(fra_years) * 12))
    return idx // 12, idx % 12


def earnings_test_withholding(dataset: Any, *, year: int, brk_inf: float, dob_year: int, dob_month: int,
                              fra_years: float, earnings: float, annual_benefit: float) -> float:
    """Dollars of this year's ``annual_benefit`` withheld because of ``earnings``."""
    benefit = float(annual_benefit or 0.0)
    if benefit <= 0.0 or float(earnings or 0.0) <= 0.0:
        return 0.0
    fra_year, fra_month = fra_year_and_month(dob_year, dob_month, fra_years)
    if year > fra_year:
        return 0.0
    if year < fra_year:
        counted, payable = float(earnings), benefit
        limit = dataset.indexed_value('ss_earnings_test_annual_limit', year, brk_inf)
        rate = dataset.lookup_or_earliest('ss_earnings_test_rate', year).value
    else:
        if fra_month == 0:
            return 0.0
        share = fra_month / 12.0   # only the months before the FRA month are tested
        counted, payable = float(earnings) * share, benefit * share
        limit = dataset.indexed_value('ss_earnings_test_fra_year_limit', year, brk_inf)
        rate = dataset.lookup_or_earliest('ss_earnings_test_fra_year_rate', year).value
    return min(payable, max(0.0, counted - limit) * rate)
