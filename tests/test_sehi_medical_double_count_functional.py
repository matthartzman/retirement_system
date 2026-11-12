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


from src.projection_stages.roth_conversion_and_agi_tax import sehi_net_of_credit


def test_sehi_is_capped_at_premiums_net_of_the_credit():
    # 20,000 of premiums; a smaller deduction raises MAGI and lowers the credit (6,000 minus 10% of the shift)
    ptc = lambda s: max(0.0, 6_000 - 0.1 * (20_000 - s))
    got = sehi_net_of_credit(20_000, 20_000, ptc)
    assert got == pytest.approx(14_545.45, abs=100)      # exact fixed point 14,545.45; two passes land within 100
    assert got < 20_000 - 5_000                            # always at least the credit's worth of the premium is not deducted


def test_sehi_is_untouched_without_a_credit_and_floors_at_zero():
    assert sehi_net_of_credit(12_000, 12_000, lambda s: 0.0) == pytest.approx(12_000)
    assert sehi_net_of_credit(5_000, 5_000, lambda s: 9_000.0) == 0.0
