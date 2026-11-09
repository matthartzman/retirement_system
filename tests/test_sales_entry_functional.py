"""Record sales grid: the open-lots read for the chooser and the atomic batch save."""
from __future__ import annotations

import json

import pytest

from src import active_plan, sales_service, transactions
from src.sales_ledger import ValidationError
from src.server import app, plan_routes

ACCT = "Matt_Trust"
HOLDINGS = [
    {"account": ACCT, "symbol": "ITOT", "purchase_date": "2024-01-10", "shares": "100", "purchase_price": "90", "lot_type": "buy", "note": ""},
    {"account": ACCT, "symbol": "ITOT", "purchase_date": "2026-03-04", "shares": "50", "purchase_price": "110", "lot_type": "buy", "note": ""},
    {"account": "Matt_IRA", "symbol": "VTI", "purchase_date": "2020-01-10", "shares": "10", "purchase_price": "100", "lot_type": "buy", "note": ""},
]
SETUP = [{"Account": "Trust - Matt", "Role": "Investment", "Mapped Investment Account": ACCT},
         {"Account": "IRA - Matt", "Role": "Investment", "Mapped Investment Account": "Matt_IRA"}]


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("ytd_account_setup").replace_all(SETUP)
        store.dataset("holdings").replace_all(HOLDINGS)
    with active_plan.workspace_store(tmp_path, write=True) as store, store.transaction():
        transactions.backfill(store)
    transactions.set_managed(tmp_path / "input", ACCT, True)            # the log writes this account's holdings
    return tmp_path


def _lots(ws, **kw):
    return sales_service.open_lots(ws / "input", ACCT, "ITOT", kw.get("as_of", "2026-09-01"))


def _row(lot, shares, **over):
    row = dict(sale_date="2026-09-01", account=ACCT, symbol="ITOT", shares=shares, proceeds=shares * 120.0, fees=0.0,
               basis=shares * lot["unit_cost"], purchase_date=lot["purchase_date"], txn_lot=lot["txn_id"])
    row.update(over)
    return row


def test_open_lots_as_of_sale_date(ws):
    out = _lots(ws)
    assert out["log_started"] is True
    lots = out["lots"]
    assert [(l["purchase_date"], l["open_shares"], l["unit_cost"], l["term"]) for l in lots] == [
        ("2024-01-10", 100.0, 90.0, "long"), ("2026-03-04", 50.0, 110.0, "short")]
    assert all(l["txn_id"] and l["source"] for l in lots)
    assert [b["txn_date"] for b in out["nearby_buys"]] == []                # no buy within 30 days of 2026-09-01
    before = _lots(ws, as_of="2026-01-01")["lots"]                      # the March lot did not exist yet
    assert [l["purchase_date"] for l in before] == ["2024-01-10"]


def test_account_without_log_reports_it(ws):
    out = sales_service.open_lots(ws / "input", "Nobody_Brokerage", "ITOT", "2026-09-01")
    assert out == {"lots": [], "log_started": False, "nearby_buys": []}


def test_batch_links_txn_lot(ws):
    a, b = _lots(ws)["lots"]
    out = sales_service.add_sales(ws / "input", [_row(a, 60), _row(b, 10, proceeds=1300.0)])
    assert len(out["ids"]) == 2
    with active_plan.workspace_store(ws) as store:
        rows = [store.sales.get_sale(i) for i in out["ids"]]
        assert [json.loads(r["lot_key"])["txn_lot"] for r in rows] == [a["txn_id"], b["txn_id"]]
        assert {r["tax_class"] for r in rows} == {"taxable"}            # the account sets it; the form no longer asks
        assert [round(l["shares"], 4) for l in transactions.open_lots(store, account=ACCT, symbol="ITOT")] == [40.0, 40.0]
        assert [float(h["shares"]) for h in store.dataset("holdings").rows() if h["symbol"] == "ITOT"] == [40.0, 40.0]


def test_batch_is_atomic(ws):
    a, b = _lots(ws)["lots"]
    good = _row(a, 10)
    bad = {**_row(b, 10), "shares": 0}                                          # shares must be > 0
    with pytest.raises(ValidationError):
        sales_service.add_sales(ws / "input", [good, bad])
    with active_plan.workspace_store(ws) as store:
        assert store.sales.list_sales() == []
        assert sum(l["shares"] for l in transactions.open_lots(store, account=ACCT, symbol="ITOT")) == 150.0


def test_selling_more_than_a_lot_holds_writes_nothing(ws):
    a, _ = _lots(ws)["lots"]
    with pytest.raises(ValidationError):
        sales_service.add_sales(ws / "input", [_row(a, 150)])
    with active_plan.workspace_store(ws) as store:
        assert store.sales.list_sales() == []


def test_unlinked_rows_need_a_purchase_date_when_taxable(ws):
    row = dict(sale_date="2026-09-01", account="Elsewhere_Brokerage", symbol="QQQ", shares=5, proceeds=500.0, fees=0.0, basis=400.0)
    with pytest.raises(ValidationError):
        sales_service.add_sales(ws / "input", [row])
    out = sales_service.add_sales(ws / "input", [{**row, "purchase_date": "2025-01-02"}])
    assert len(out["ids"]) == 1


def test_voiding_the_last_linked_lot_returns_the_shares(ws):
    a, b = _lots(ws)["lots"]
    ids = sales_service.add_sales(ws / "input", [_row(a, 60), _row(b, 10)])["ids"]
    sales_service.void_sale(ws / "input", ids[0])
    with active_plan.workspace_store(ws) as store:
        assert sum(l["shares"] for l in transactions.open_lots(store, account=ACCT, symbol="ITOT")) == 140.0   # only the 10-share lot is still sold
    sales_service.void_sale(ws / "input", ids[1])
    with active_plan.workspace_store(ws) as store:
        assert sum(l["shares"] for l in transactions.open_lots(store, account=ACCT, symbol="ITOT")) == 150.0
    with pytest.raises(ValidationError):
        sales_service.unvoid_sale(ws / "input", ids[0])                  # the log sale is gone; record it again


@pytest.fixture()
def client(ws, monkeypatch):
    monkeypatch.setattr(plan_routes, "_ytd_input_root", lambda: ws / "input")
    return app.test_client()


def test_routes(client, ws):
    r = client.get(f"/api/sales/open-lots?account={ACCT}&symbol=ITOT&as_of=2026-09-01").get_json()
    assert r["success"] and len(r["lots"]) == 2
    a = r["lots"][0]
    row = _row(a, 5)
    ok = client.post("/api/sales/batch", json={"rows": [row]})
    assert ok.status_code == 200 and len(ok.get_json()["ids"]) == 1
    bad = client.post("/api/sales/batch", json={"rows": [{**row, "shares": -1}]})
    assert bad.status_code == 400 and not bad.get_json()["success"]
    assert client.post("/api/sales/batch", json={"rows": []}).status_code == 400


def test_years_route_names_accounts_and_classes(client):
    r = client.get("/api/sales/years").get_json()
    assert r["account_classes"] == {"Matt_IRA": "pre_tax", ACCT: "taxable"}
    assert r["taxable_accounts"] == [ACCT]
