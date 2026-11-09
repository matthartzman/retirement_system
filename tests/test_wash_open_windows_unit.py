"""Open wash windows: loss sales less than 31 days old and the household accounts that have reinvested (or just hold) the fund."""
from __future__ import annotations

from datetime import date

import pytest

from src import active_plan, sales_service, transactions
from src.wash_sales import open_windows

A, B, C = "Matt_Trust", "Spouse_IRA", "Spouse_401k"
SETUP = [{"Account": "Trust", "Role": "Investment", "Mapped Investment Account": A}, {"Account": "IRA", "Role": "Investment", "Mapped Investment Account": B},
         {"Account": "401k", "Role": "Investment", "Mapped Investment Account": C}]
HOLDINGS = [{"account": a, "symbol": "VTI", "purchase_date": "2025-01-02", "shares": "20", "purchase_price": "100", "lot_type": "buy", "note": ""} for a in (A, B, C)]


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("ytd_account_setup").replace_all(SETUP)
        store.dataset("holdings").replace_all(HOLDINGS)
    with active_plan.workspace_store(tmp_path, write=True) as store, store.transaction():
        transactions.backfill(store)
    return tmp_path


def _loss(ws, day="2026-11-10"):
    sales_service.add_sale(ws / "input", dict(sale_date=day, account=A, tax_class="taxable", symbol="VTI", shares=5, proceeds=400.0, fees=0.0, basis=500.0,
                                              purchase_date="2025-01-02"))


def _windows(ws, today, **kw):
    with active_plan.workspace_store(ws) as store:
        return open_windows(store, today, **kw)


def _reinvest(ws, account, day):
    with active_plan.workspace_store(ws, write=True) as store, store.transaction():
        store.transactions.insert(txn_date=day, account=account, type="reinvest", symbol="VTI", shares=0.1, price=100.0, amount=-10.0, source="manual")


def test_window_open_for_sale_29_days_ago(ws):
    _loss(ws, "2026-10-11")
    (w,) = _windows(ws, date(2026, 11, 9))
    assert w["closes_on"] == "2026-11-10" and w["symbol"] == "VTI" and w["sale_key"] == f"{A}|VTI|2026-10-11"


def test_window_closed_after_30_days(ws):
    _loss(ws, "2026-10-09")
    assert _windows(ws, date(2026, 11, 9)) == []                         # day 31
    assert len(_windows(ws, date(2026, 11, 8))) == 1                    # day 30: still open


def test_reinvesting_uses_last_12_months(ws):
    _loss(ws)
    _reinvest(ws, B, "2026-03-01")
    _reinvest(ws, C, "2025-09-01")                                       # more than 12 months before 2026-11-10
    (w,) = _windows(ws, date(2026, 11, 12), label=lambda a: f"<{a}>")
    assert w["reinvesting"] == ["<Spouse_IRA>"]


def test_account_holding_fund_without_reinvest_listed_as_also_holds(ws):
    _loss(ws)
    _reinvest(ws, B, "2026-03-01")
    (w,) = _windows(ws, date(2026, 11, 12))
    assert w["reinvesting"] == [B] and w["also_holds"] == sorted([A, C])


def test_no_loss_sales_means_no_windows(ws):
    sales_service.add_sale(ws / "input", dict(sale_date="2026-11-10", account=A, tax_class="taxable", symbol="VTI", shares=5, proceeds=600.0, fees=0.0,
                                              basis=500.0, purchase_date="2025-01-02"))
    assert _windows(ws, date(2026, 11, 12)) == []
