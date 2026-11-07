"""A note stops counting toward net worth once its last payment is received.

The engine reduced each note's balance by the principal paid but never zeroed it after the last payment, so a note
whose face value exceeds its scheduled principal (face $512,848, principal paid $474,253) kept the $38.5K difference
in net worth for every later year."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

FIRST, LAST = 2027, 2031
PRINCIPAL, FINAL = 50_000.0, 52_000.0
SCHEDULED = PRINCIPAL * (LAST - FIRST) + FINAL  # 252,000


def _run(face):
    from src.planning_engines import project
    from tests import synthetic_plans as sp
    from tests.test_synthetic_golden_master import empty_workspace

    note = {"section": "Note 1", "name": "Test Note", "face_value": face, "first_payment_year": FIRST,
            "last_payment_year": LAST, "annual_principal": PRINCIPAL, "final_principal": FINAL,
            "interest_by_year": {}, "st_gain_per_principal": 0.0, "lt_gain_per_principal": 0.0}
    with empty_workspace():
        c = sp.SCENARIOS["baseline_balanced_couple"].build(optimize=False)
        c["note_items"] = [note]
        c["note_face"] = face
        return {r["year"]: r for r in project(c)}


@pytest.fixture(scope="module")
def runs():
    return {"short_schedule": _run(SCHEDULED + 40_000.0), "exact": _run(SCHEDULED)}


def test_balance_is_zero_from_the_last_payment_year_on(runs):
    for year in (LAST, LAST + 1, LAST + 5):
        assert runs["short_schedule"][year]["note_bal"] == pytest.approx(0.0), year


def test_balance_before_the_last_payment_is_the_unpaid_principal(runs):
    rows = runs["short_schedule"]
    assert rows[FIRST]["note_bal"] == pytest.approx(SCHEDULED + 40_000.0 - PRINCIPAL)
    assert rows[LAST - 1]["note_bal"] == pytest.approx(SCHEDULED + 40_000.0 - PRINCIPAL * (LAST - 1 - FIRST + 1))


def test_cash_received_does_not_change(runs):
    for year in range(FIRST, LAST + 2):
        assert runs["short_schedule"][year]["note_princ"] == pytest.approx(runs["exact"][year]["note_princ"])


def test_a_note_that_pays_exactly_its_face_is_unchanged(runs):
    assert runs["exact"][LAST]["note_bal"] == pytest.approx(0.0)
    assert runs["exact"][LAST - 1]["note_bal"] == pytest.approx(FINAL)
