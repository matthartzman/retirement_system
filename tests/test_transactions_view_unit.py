"""Read-only Transactions view (phase 1 of the transaction log plan) and GET /api/transactions."""
from __future__ import annotations

import pytest

from src import active_plan, broker_import
from src.server import app, plan_routes
from tests.broker_activity_fixtures import ETRADE_FILE_NAME, FILE_NAME, etrade_csv, history_csv

ACCT = "Member_1_HSA"
IRA = "Member_1_IRA"
HOLDINGS = [
    {"account": ACCT, "symbol": "TOTL", "purchase_date": "2025-12-30", "shares": "5", "purchase_price": "90", "lot_type": "buy", "note": ""},
    {"account": IRA, "symbol": "TOTL", "purchase_date": "2025-01-02", "shares": "20", "purchase_price": "90", "lot_type": "buy", "note": ""},
    {"account": IRA, "symbol": "91733P115", "purchase_date": "2025-02-01", "shares": "1500", "purchase_price": "0.5", "lot_type": "buy", "note": ""},
]


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("holdings").replace_all(HOLDINGS)
    broker_import.commit(tmp_path / "input", text=history_csv(), file_name=FILE_NAME, account=ACCT, confirm_method="fifo")
    broker_import.commit(tmp_path / "input", text=etrade_csv(), file_name=ETRADE_FILE_NAME, account=IRA, confirm_method="fifo")
    return tmp_path


def _view(ws, **kw):
    from src import transactions_view
    return transactions_view.view(ws / "input", **kw)


def test_rows_cover_buys_reinvests_and_sells_never_monarch_or_sweep(ws):
    v = _view(ws)
    assert {r["type"] for r in v["rows"]} <= {"buy", "reinvest", "sell"} and {"buy", "sell"} <= {r["type"] for r in v["rows"]}
    assert all(r["source"] in ("broker", "manual") for r in v["rows"])
    assert [r["date"] for r in v["rows"]] == sorted(r["date"] for r in v["rows"])


def test_redemption_listed_as_a_sale_and_its_lot_is_relieved(ws):
    red = [r for r in _view(ws, account=IRA, symbol="91733P115")["rows"]]
    assert [(r["type"], r["shares"]) for r in red] == [("sell", 1000.0)] and red[0]["linked"] == "confirmed"
    held = _view(ws, account=IRA, symbol="91733P115")["held"]
    assert [h["shares"] for h in held] == [500.0]


def test_unsold_buy_listed_as_held_with_remaining(ws):
    v = _view(ws, account=IRA, types=["buy"], held_only=True)
    assert v["rows"] and all(r["remaining"] and r["remaining"] > 0 for r in v["rows"])
    assert all(r["type"] != "sell" for r in v["rows"])


def test_filters_by_account_symbol_year(ws):
    assert {r["account"] for r in _view(ws, account=IRA)["rows"]} == {IRA}
    assert {r["symbol"] for r in _view(ws, symbol="totl")["rows"]} == {"TOTL"}
    assert _view(ws, year=1999)["rows"] == []


def test_route_returns_rows_and_unknown_filter_is_empty(ws, monkeypatch):
    monkeypatch.setattr(plan_routes, "_ytd_input_root", lambda: ws / "input")
    c = app.test_client()
    body = c.get(f"/api/transactions?account={IRA}&type=sell").get_json()
    assert body["success"] and body["rows"] and {r["type"] for r in body["rows"]} == {"sell"}
    assert c.get("/api/transactions?account=nobody").get_json()["rows"] == []
    assert c.get("/api/transactions?year=abc").status_code == 400
