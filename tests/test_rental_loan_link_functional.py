"""H2: a rental property uses an existing Liabilities row as its loan (RENTAL_TAX_RULES.md section 9)."""
from __future__ import annotations

import copy

import pytest

from src.projection_stages import rental_property as rp
from tests import rental_fixtures as rf

PROP = dict(rf.PROFITABLE)
MTG = {"liability_id": "mtg-a", "type": "other", "label": "Duplex", "balance": 200000.0, "interest_rate": 0.04,
       "monthly_payment": 1140.36, "start_year": 0, "payoff_year": 0, "notes": ""}
HELOC = {"liability_id": "heloc1", "type": "heloc", "label": "HELOC", "balance": 100000.0, "interest_rate": 0.07,
         "monthly_payment": 583.33, "start_year": 0, "payoff_year": 0, "notes": ""}


def _config(rows, liabs, plan=None, on=True):
    c = rf.rental_config(rf.RentalCase(rows, plan=plan or {}), on=on)
    c["liabilities"] = copy.deepcopy(liabs)
    return c


def _run(rows, liabs, plan=None, on=True):
    return rf.by_year(rf.project(_config(rows, liabs, plan, on)))


@pytest.fixture(scope="module")
def runs():
    own = dict(PROP, loan_balance=200000, loan_rate=0.04, loan_term_years=22)
    return {
        "own": _run([own], []),
        "double": _run([own], [MTG]),
        "linked": _run([dict(PROP, loan_liability_id="mtg-a")], [MTG]),
    }


def test_linked_loan_equals_the_loan_entered_on_the_property(runs):
    own, linked = runs["own"], runs["linked"]
    for y in (2026, 2027, 2030):
        for k in ("rental_mortgage_interest", "rental_mortgage_principal", "rental_mortgage_balance"):
            assert linked[y][k] == pytest.approx(own[y][k], abs=1.0)
        assert linked[y]["total_nw"] == pytest.approx(own[y]["total_nw"], abs=1.0)
    assert linked[2026]["rental_mortgage_interest"] == pytest.approx(7894.62, abs=0.05)
    assert linked[2026]["rental_mortgage_principal"] == pytest.approx(5789.72, abs=0.05)


def test_entering_the_loan_twice_double_counts_without_the_link(runs):
    assert runs["double"][2026]["total_nw"] < runs["own"][2026]["total_nw"] - 150000


def test_converted_home_linked_interest_moves_to_schedule_e_only():
    plan = {"home_sale_yr": 2040}
    conv = dict(rf.CONVERTED_HOME)
    base = _run([conv], [HELOC], plan)
    link = _run([dict(conv, loan_liability_id="heloc1")], [HELOC], plan)
    # July 2027 conversion: share 0.5; 2028 on: 1.0. Interest-only 7% of 100,000.
    assert link[2027]["rental_mortgage_interest"] - base[2027]["rental_mortgage_interest"] == pytest.approx(3500, abs=1)
    assert link[2028]["rental_mortgage_interest"] - base[2028]["rental_mortgage_interest"] == pytest.approx(7000, abs=1)
    assert link[2028]["rental_schedule_e_net"] == pytest.approx(base[2028]["rental_schedule_e_net"] - 7000, abs=1)
    # cash need and liability balance unchanged: the payment stays in the liability loop
    assert link[2028]["rental_net_cash_flow"] == pytest.approx(base[2028]["rental_net_cash_flow"], abs=1)


def test_bad_links_warn_and_fall_back():
    typo = _run([dict(PROP, loan_balance=200000, loan_rate=0.04, loan_term_years=22, loan_liability_id="typo")], [MTG])
    assert "not found" in typo[2026]["rental_loan_link_warnings"][0]
    student = dict(MTG, type="student_loan")
    s = _run([dict(PROP, loan_liability_id="mtg-a")], [student])
    assert "student loan" in s[2026]["rental_loan_link_warnings"][0]
    two = _run([dict(PROP, name="A", loan_liability_id="mtg-a"),
                dict(PROP, name="B", loan_liability_id="mtg-a")], [MTG])
    assert "already used" in two[2026]["rental_loan_link_warnings"][0]


def test_feature_off_ignores_the_link():
    off_linked = _run([dict(PROP, loan_liability_id="mtg-a")], [MTG], on=False)
    off_plain = _run([PROP], [MTG], on=False)
    assert off_linked == off_plain
    assert rp.linked_liability_ids(_config([dict(PROP, loan_liability_id="mtg-a")], [MTG], on=False)) == frozenset()
