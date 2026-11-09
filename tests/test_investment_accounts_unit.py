"""Which holdings accounts count as investment accounts (never a bank account), and that backfill honours it."""
from __future__ import annotations

import pytest

from src import active_plan, broker_import, transactions

SETUP = [
    {"Account": "Trust - Matt", "Role": "Investment", "Mapped Investment Account": "Matt_Trust"},
    {"Account": "Business Checking", "Role": "Cash / spending", "Mapped Investment Account": "Business_Checking"},
    {"Account": "Family Checking", "Role": "Cash / spending", "Mapped Investment Account": ""},
    {"Account": "Savings Pocket", "Role": "", "Mapped Investment Account": "Savings_Pocket"},
]
HOLDINGS = [
    {"account": "Matt_Trust", "symbol": "ITOT", "purchase_date": "2025-01-02", "shares": "10", "purchase_price": "90", "lot_type": "buy", "note": ""},
    {"account": "Business_Checking", "symbol": "CASH", "purchase_date": "2025-12-31", "shares": "5000", "purchase_price": "1", "lot_type": "buy", "note": ""},
    {"account": "Family_Checking", "symbol": "CASH", "purchase_date": "2025-12-31", "shares": "900", "purchase_price": "1", "lot_type": "buy", "note": ""},
    {"account": "Savings_Pocket", "symbol": "CASH", "purchase_date": "2025-12-31", "shares": "100", "purchase_price": "1", "lot_type": "buy", "note": ""},
]


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("ytd_account_setup").replace_all(SETUP)
        store.dataset("holdings").replace_all(HOLDINGS)
    return tmp_path


def test_checking_accounts_are_not_investment_accounts(ws):
    names = broker_import.investment_accounts(ws / "input")
    assert names == ["Matt_Trust"]
    with active_plan.workspace_store(ws) as store:
        assert broker_import.plan_accounts(store) == ["Matt_Trust"]


def test_missing_role_is_cash(ws):
    assert "Savings_Pocket" not in broker_import.investment_accounts(ws / "input")


def test_backfill_skips_non_investment_accounts(ws):
    with active_plan.workspace_store(ws, write=True) as store, store.transaction():
        transactions.backfill(store)
    with active_plan.workspace_store(ws) as store:
        rows = store.transactions.list(include_voided=True)
    assert {r["account"] for r in rows} == {"Matt_Trust"}
