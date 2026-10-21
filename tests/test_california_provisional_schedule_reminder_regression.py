"""California income-tax brackets are the FTB 2025 schedule carried forward.

``src/core.py`` tags California's bracket dollars with tax year 2025 and indexes
them by ``brk_inf``; no final 2026 schedule was verified (reviewed 2026-10-20).
This test is the dated reminder: it passes until ``CA_REVIEW_DUE`` and then
fails until the carried-forward schedule is replaced with the FTB final 2026
schedule and ``_STATE_INCOME_BRACKETS_VALUE_YEARS['California']`` is moved to
2026. Do not push the date out without checking ftb.ca.gov for the schedule.
"""
from __future__ import annotations

import datetime

from src import core

CA_PROVISIONAL_VALUE_YEAR = 2025
# FTB normally publishes the prior tax year's indexed schedules by early in the
# following year; leave a margin before this becomes a failure.
CA_REVIEW_DUE = datetime.date(2027, 3, 1)


def test_california_vintage_is_still_the_provisional_2025_carry_forward():
    """If the vintage changes, replace this pin and the reminder together."""
    assert core._STATE_INCOME_BRACKETS_VALUE_YEARS["California"] == CA_PROVISIONAL_VALUE_YEAR


def test_california_final_2026_schedule_has_replaced_the_carry_forward_once_due():
    if datetime.date.today() < CA_REVIEW_DUE:
        return
    assert core._STATE_INCOME_BRACKETS_VALUE_YEARS["California"] >= 2026, (
        "California still uses the FTB 2025 schedule carried forward. Replace the "
        "(California, *) entries in core._STATE_INCOME_BRACKETS with the FTB final "
        "2026 schedule, set the value year to 2026, and update this test."
    )
