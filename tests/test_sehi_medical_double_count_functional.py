"""W3-04 / FIN-006: premiums deducted as self-employed health insurance are not also itemized medical expense."""
from __future__ import annotations

import pytest

from src.projection_stages.roth_conversion_and_agi_tax import medical_expense_after_sehi


def test_premiums_already_deducted_as_sehi_leave_the_medical_total():
    # 20,000 of premiums, 12,000 deducted as SEHI, 3,000 other medical -> 8,000 + 3,000
    assert medical_expense_after_sehi(20_000, 12_000, 3_000) == pytest.approx(11_000)


def test_without_sehi_the_premiums_count_in_full():
    assert medical_expense_after_sehi(20_000, 0.0, 3_000) == pytest.approx(23_000)


def test_sehi_above_the_premiums_never_goes_negative():
    assert medical_expense_after_sehi(5_000, 12_000, 1_000) == pytest.approx(1_000)


def test_itemizing_household_medical_deduction_falls_by_the_sehi_amount():
    agi = 100_000.0
    floor = 0.075 * agi
    before = max(0.0, medical_expense_after_sehi(20_000, 0.0, 3_000) - floor)
    after = max(0.0, medical_expense_after_sehi(20_000, 12_000, 3_000) - floor)
    assert before - after == pytest.approx(12_000)
