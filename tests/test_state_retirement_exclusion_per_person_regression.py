"""WI-305 / FIN-006: New York and Colorado retirement-income exclusions apply
once per qualifying, LIVING person -- not once per household -- and each
member's own alive/age status gates their own exclusion.

NY exclusion = $20,000 and CO = $24,000 per state_tax.csv. The engine keeps
the existing age-65 eligibility gate (NY's age-59 1/2 rule is flagged for
professional review, not changed here).
"""
from __future__ import annotations

import pytest

from src.core import state_income_tax, state_retirement_exclusion_count


def _ny(retirement_dist, qualifying, year=2026):
    return state_income_tax('New York', 0.0, retirement_dist, 0.0, 0.0, 0.0, 0.0,
                            year, qualifying, filing='MFJ', brk_inf=0.0)


def test_ny_mfj_couple_both_66_excludes_40k_of_60k_ira_distributions():
    # Both spouses qualify: $40k excluded, $20k taxable.
    assert _ny(60_000.0, 2) == pytest.approx(_ny(20_000.0, 0))
    # Previously only one $20k exclusion applied ($40k taxable).
    assert _ny(60_000.0, 2) < _ny(60_000.0, 1)
    assert _ny(60_000.0, 1) == pytest.approx(_ny(40_000.0, 0))


def test_boolean_gate_is_backward_compatible_single_exclusion():
    assert _ny(60_000.0, True) == pytest.approx(_ny(60_000.0, 1))
    assert _ny(60_000.0, False) == pytest.approx(_ny(60_000.0, 0))


def test_exclusion_never_exceeds_retirement_income():
    assert _ny(15_000.0, 2) == 0.0


def test_colorado_per_person_exclusion():
    def co(dist, n):
        return state_income_tax('Colorado', 0.0, dist, 0.0, 0.0, 0.0, 0.0, 2026, n, filing='MFJ')
    assert co(60_000.0, 2) == pytest.approx(co(12_000.0, 0))
    assert co(60_000.0, 1) == pytest.approx(co(36_000.0, 0))


@pytest.mark.parametrize("h_age,w_age,h_alive,w_alive,expected", [
    (66, 66, True, True, 2),
    (66, 60, True, True, 1),
    (60, 60, True, True, 0),
    (70, 68, False, True, 1),   # deceased spouse's age no longer opens the gate
    (70, 60, False, True, 0),   # survivor under 65: no exclusion at all
])
def test_qualifying_count_uses_each_members_own_age_and_alive_flag(h_age, w_age, h_alive, w_alive, expected):
    assert state_retirement_exclusion_count(h_age, w_age, h_alive, w_alive) == expected
