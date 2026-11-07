"""Standard checking and credit-card balances for the forecast years.

The forecast used to hold today's checking balance and today's credit-card liabilities flat for every year. The plan
now takes a standard balance for all checking accounts together and for all credit cards together, used from the
year after the current one, each with its own annual percent change; the current year keeps today's balances.

Design: documentation/future/superpowers/plans/2026-11-07-cash-balances-and-art-split-design-and-plan.md 3.1-3.3."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

from src import plan_data_backfill as bf
from src import working_balances as wb


# ---- the balance in each year ----

def test_current_year_is_todays_balance():
    assert wb.target_total(2026, 2026, 86_849.0, 10_000.0, 0.05) == 86_849.0


def test_standard_balance_from_the_next_year_and_its_own_percent_after():
    t = lambda y: wb.target_total(y, 2026, 86_849.0, 10_000.0, 0.05)
    assert (t(2027), t(2028), t(2029)) == (pytest.approx(10_000.0), pytest.approx(10_500.0), pytest.approx(11_025.0))
    flat = lambda y: wb.target_total(y, 2026, 86_849.0, 10_000.0, 0.0)
    assert [flat(y) for y in (2027, 2030, 2060)] == [10_000.0] * 3


def test_negative_percent_shrinks_the_balance():
    assert wb.target_total(2028, 2026, 5_000.0, 10_000.0, -0.10) == pytest.approx(9_000.0)


def test_blank_standard_holds_todays_balance_and_the_percent_applies_from_the_next_year():
    assert wb.target_total(2027, 2026, 6_571.0, None, 0.0) == 6_571.0
    assert wb.target_total(2060, 2026, 6_571.0, None, 0.0) == 6_571.0
    assert wb.target_total(2027, 2026, 100.0, None, 0.03) == pytest.approx(103.0)
    assert wb.target_total(2028, 2026, 100.0, None, 0.03) == pytest.approx(106.09)


# ---- the four plan rows ----

def test_rows_and_parse():
    labels = [r[2] for r in wb.UI_PLAN_DATA_ROWS]
    assert labels == ["checking_standard_balance", "checking_annual_change_pct",
                      "credit_card_standard_balance", "credit_card_annual_change_pct"]
    assert all(r[0] == "Other Assets" and r[1] == "Cash" and r[3] == "" for r in wb.UI_PLAN_DATA_ROWS)
    assert [r[4] for r in wb.UI_PLAN_DATA_ROWS] == ["USD", "pct", "USD", "pct"]

    full = {"Other Assets": {"Cash": {"checking_standard_balance": "$10,000", "checking_annual_change_pct": "0%",
                                      "credit_card_standard_balance": "$10,000", "credit_card_annual_change_pct": "2.5%"}}}
    assert wb.parse(full) == {"checking_std_balance": 10_000.0, "checking_change_pct": 0.0,
                              "cc_std_balance": 10_000.0, "cc_change_pct": 0.025}
    blank = {"Other Assets": {"Cash": {"checking_standard_balance": "", "credit_card_annual_change_pct": ""}}}
    assert wb.parse(blank) == {"checking_std_balance": None, "checking_change_pct": 0.0,
                               "cc_std_balance": None, "cc_change_pct": 0.0}
    assert wb.parse({}) == wb.parse(blank)


def test_backfill_entry_is_registered_and_adds_blank_rows():
    from src.server import app_core

    assert any(e.rows is wb.UI_PLAN_DATA_ROWS for e in app_core.PLAN_DATA_BACKFILL_ENTRIES)

    class _Store:
        def rows(self, section):
            return []

        def all_rows(self):
            return []

    [(_entry, missing)] = bf.pending_rows(_Store(), [bf.BackfillEntry(wb.UI_PLAN_DATA_ROWS)], None)
    assert [r[2] for r in missing] == [r[2] for r in wb.UI_PLAN_DATA_ROWS]


# ---- through the engine ----

CARDS = [{"liability_id": "amex", "type": "credit_card", "label": "Amex", "balance": 6_000.0, "interest_rate": 0.0,
          "monthly_payment": 0.0, "start_year": 0, "payoff_year": 0, "payoff_month": 0, "carry_zero": True, "notes": ""},
         {"liability_id": "visa", "type": "credit_card", "label": "Visa", "balance": 2_000.0, "interest_rate": 0.0,
          "monthly_payment": 0.0, "start_year": 0, "payoff_year": 0, "payoff_month": 0, "carry_zero": True, "notes": ""}]
TODAY_CHECKING, TODAY_CARDS = 120_000.0, 8_000.0


def _run(**inputs):
    from src.planning_engines import project
    from tests import synthetic_plans as sp
    from tests.test_synthetic_golden_master import empty_workspace

    with empty_workspace():
        c = sp.SCENARIOS["baseline_balanced_couple"].build(optimize=False)
        c["liabilities"] = [dict(x) for x in CARDS]
        c.update(inputs)
        return c, {r["year"]: r for r in project(c)}


@pytest.fixture(scope="module")
def runs():
    return {
        "base": _run(),
        "std": _run(checking_std_balance=10_000.0, checking_change_pct=0.0, cc_std_balance=10_000.0, cc_change_pct=0.0),
        "up": _run(checking_std_balance=150_000.0, checking_change_pct=0.10, cc_std_balance=5_000.0, cc_change_pct=0.0),
    }


def test_blank_inputs_change_nothing(runs):
    _c, base = runs["base"]
    blank = _run(checking_std_balance=None, checking_change_pct=0.0, cc_std_balance=None, cc_change_pct=0.0)[1]
    for year, row in base.items():
        assert blank[year]["total_nw"] == row["total_nw"]
        assert blank[year]["cash_nw"] == row["cash_nw"]
        assert blank[year]["additional_liabilities"] == row["additional_liabilities"]
        assert "working_balance_cash_need" not in blank[year]


def test_current_year_keeps_todays_balances_then_the_standard(runs):
    c, rows = runs["std"]
    ps = c["plan_start"]
    assert rows[ps]["cash_nw"] == pytest.approx(TODAY_CHECKING)
    assert rows[ps]["additional_liabilities"] == pytest.approx(TODAY_CARDS)
    for year in (ps + 1, ps + 2, ps + 10):
        assert rows[year]["cash_nw"] == pytest.approx(10_000.0)
        assert rows[year]["additional_liabilities"] == pytest.approx(10_000.0)


def test_each_account_or_card_keeps_its_share_of_the_total():
    assert wb.scale_to({"amex": 6_000.0, "visa": 2_000.0}, 10_000.0) == {"amex": pytest.approx(7_500.0),
                                                                           "visa": pytest.approx(2_500.0)}
    assert wb.scale_to({"a": 3.0, "b": 1.0}, 0.0) == {"a": 0.0, "b": 0.0}
    # nothing to take the shares from: split evenly
    assert wb.scale_to({"a": 0.0, "b": 0.0}, 10.0) == {"a": 5.0, "b": 5.0}
    assert wb.scale_to({}, 10.0) == {}


def test_each_item_compounds_at_its_own_percent(runs):
    c, rows = runs["up"]
    ps = c["plan_start"]
    assert rows[ps + 1]["cash_nw"] == pytest.approx(150_000.0)
    assert rows[ps + 2]["cash_nw"] == pytest.approx(165_000.0)
    assert rows[ps + 3]["cash_nw"] == pytest.approx(181_500.0)
    assert rows[ps + 3]["additional_liabilities"] == pytest.approx(5_000.0)  # cards: 0%


def test_lower_checking_goes_to_the_taxable_account_and_cards_borrow_into_it(runs):
    c, rows = runs["std"]
    ps = c["plan_start"]
    row = rows[ps + 1]
    # checking 120,000 -> 10,000 frees 110,000; cards 8,000 -> 10,000 borrows 2,000: both land in Joint_Trust
    assert row["_account_withdrawals"]["Family_Checking"] == pytest.approx(110_000.0)
    moved = sum(s["amount"] for s in row["_account_deposit_sources"]["Joint_Trust"]
                if s["source"] == "Working Balance Transfer")
    assert moved == pytest.approx(112_000.0)
    assert row["working_balance_cash_need"] == pytest.approx(0.0)
    assert rows[ps + 2].get("working_balance_cash_need", 0.0) == pytest.approx(0.0)  # no change after the first year


def test_higher_checking_and_a_card_paydown_are_funded_by_the_withdrawal_order(runs):
    c, rows = runs["up"]
    ps = c["plan_start"]
    row = rows[ps + 1]
    # checking 120,000 -> 150,000 needs 30,000; cards 8,000 -> 5,000 pays 3,000 down
    assert row["working_balance_cash_need"] == pytest.approx(33_000.0)
    assert row["other_cash_need_yr"] >= 33_000.0 - 1
    assert row["_account_deposits"]["Family_Checking"] == pytest.approx(30_000.0)
    assert row["cashflow_breakdown"]["tax"] and sum(row["cashflow_breakdown"]["tax"].values()) == pytest.approx(
        row["total_tax"], abs=0.01)
