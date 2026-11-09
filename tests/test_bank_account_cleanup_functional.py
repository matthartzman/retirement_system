"""The one-time cleanup of bank accounts that an earlier backfill gave opening CASH rows."""
from __future__ import annotations

import pytest

from src import active_plan, transactions
from src.sales_ledger import ValidationError

BANK, FAMILY, INVEST = "Business_Checking", "Family_Checking", "Matt_Trust"
SETUP = [
    {"Account": "Trust - Matt", "Role": "Investment", "Mapped Investment Account": INVEST},
    {"Account": "Business Checking", "Role": "Cash / spending", "Mapped Investment Account": BANK},
    {"Account": "Family Checking", "Role": "Cash / spending", "Mapped Investment Account": FAMILY},
]
HOLDINGS = [
    {"account": INVEST, "symbol": "ITOT", "purchase_date": "2025-01-02", "shares": "10", "purchase_price": "90", "lot_type": "buy", "note": ""},
    {"account": BANK, "symbol": "CASH", "purchase_date": "2025-12-31", "shares": "5000", "purchase_price": "1", "lot_type": "cash", "note": ""},
    {"account": FAMILY, "symbol": "CASH", "purchase_date": "2025-12-31", "shares": "900", "purchase_price": "1", "lot_type": "cash", "note": ""},
]


@pytest.fixture()
def ws(tmp_path):
    """A plan where an old backfill (before the investment-account rule) logged the bank accounts too."""
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("holdings").replace_all(HOLDINGS)
    with active_plan.workspace_store(tmp_path, write=True) as store, store.transaction():
        transactions.backfill(store)                      # no setup rows yet, so the legacy "_" rule admits every account
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("ytd_account_setup").replace_all(SETUP)
        store.transactions.set_managed(BANK, True)
    return tmp_path


def _rows(ws, account):
    with active_plan.workspace_store(ws) as store:
        return [r for r in store.transactions.list() if r["account"] == account]


def test_preview_lists_checking_accounts_with_opening_rows(ws):
    out = transactions.bank_account_cleanup_preview(ws / "input")["accounts"]
    assert {a["account"] for a in out} == {BANK, FAMILY}
    by = {a["account"]: a for a in out}
    assert by[BANK]["managed"] is True and by[FAMILY]["managed"] is False
    assert all(a["opening_rows"] for a in out)


def test_apply_unmanages_before_voiding_so_cash_holdings_survive(ws):
    out = transactions.bank_account_cleanup_apply(ws / "input", [BANK, FAMILY])
    assert out["voided"] >= 2 and out["unmanaged"] == [BANK]
    with active_plan.workspace_store(ws) as store:
        cash = {(r["account"], r["symbol"]): r["shares"] for r in store.dataset("holdings").rows() if r["symbol"] == "CASH"}
        assert BANK not in store.transactions.managed_accounts()
    assert cash[(BANK, "CASH")] == "5000" and cash[(FAMILY, "CASH")] == "900"
    assert not _rows(ws, BANK) and not _rows(ws, FAMILY)


def test_apply_requires_explicit_accounts(ws):
    with pytest.raises(ValidationError):
        transactions.bank_account_cleanup_apply(ws / "input", [])
    assert _rows(ws, BANK)


def test_apply_never_touches_investment_accounts(ws):
    before = len(_rows(ws, INVEST))
    out = transactions.bank_account_cleanup_apply(ws / "input", [INVEST])
    assert out["voided"] == 0 and len(_rows(ws, INVEST)) == before > 0
