"""W3-05 / FIN-002: senior-deduction phase-out, settled by the CPA (2026-11): joint threshold, not split per person."""
from __future__ import annotations

import pytest

from src.core import senior_bonus_deduction


@pytest.mark.parametrize("magi, expected", [(150_000, 12_000), (200_000, 9_000), (250_000, 6_000), (300_000, 3_000), (350_000, 0)])
def test_two_qualifiers_mfj_reduce_the_combined_amount_once(magi, expected):
    assert senior_bonus_deduction(2026, "MFJ", magi, n_over_65=2) == pytest.approx(expected)


def test_one_qualifier_and_single_threshold():
    assert senior_bonus_deduction(2026, "MFJ", 200_000, n_over_65=1) == pytest.approx(3_000)
    assert senior_bonus_deduction(2026, "Single", 125_000, n_over_65=1) == pytest.approx(3_000)


def test_qualifying_surviving_spouse_uses_the_joint_threshold():
    assert senior_bonus_deduction(2026, "QSS", 200_000, n_over_65=1) == senior_bonus_deduction(2026, "MFJ", 200_000, n_over_65=1)
    assert senior_bonus_deduction(2026, "QSS", 200_000, n_over_65=1) == pytest.approx(3_000)
