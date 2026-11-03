"""Checking & Savings accounts: add, list, delete, and the account import updating the balance and its date."""
from __future__ import annotations

import csv
from datetime import date, datetime, timezone

import pytest

from src import active_plan, reconcile
from src import monarch_balances_import as mbi
from src import ytd_tracking as ytd
from src.server import app, plan_routes

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 4, 0, tzinfo=timezone.utc)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    base = tmp_path / "ws"
    (base / "input").mkdir(parents=True)
    ytd.write_account_setup(base / "input", [])
    with active_plan.workspace_store(base, write=True) as store:
        store.set_value("Other Assets", "Home", "value_as_of_plan_start", "1313000")
    path = base / "Monarch Extractor" / "output" / "balances.csv"
    path.parent.mkdir(parents=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(mbi.EXPECTED_HEADER)
        w.writerow(["2026-10-14", "family checking", "Family Checking", 13894.27])
        w.writerow(["2026-10-14", "high yield savings", "High Yield Savings", 5000.0])
    assert mbi.import_balances(base, today=TODAY, now=NOW)["success"]
    monkeypatch.setattr(plan_routes, "_ytd_input_root", lambda: base / "input")
    c = app.test_client()
    c.base = base
    return c


def _add(client, **body):
    return client.post("/api/cash-accounts", json=body)


def test_add_lists_a_lot_free_account_linked_to_the_import(client):
    r = _add(client, name="Family Checking", balance="13,000", as_of="2026-10-01", import_account_key="family checking")
    assert r.status_code == 200 and r.get_json()["account"] == "Family_Checking"
    rows = client.get("/api/cash-accounts").get_json()
    assert rows["has_import"] and len(rows["import_accounts"]) == 2
    (acct,) = rows["accounts"]
    assert acct == {"account": "Family_Checking", "name": "Family Checking", "balance": "13000.00", "as_of": "2026-10-01",
                    "import_account": "Family Checking"}
    with active_plan.workspace_store(client.base) as store:
        lots = [r for r in store.holdings.rows() if r["account"] == "Family_Checking"]
    assert [(l["symbol"], l["shares"]) for l in lots] == [("CASH", "13000.00")]


def test_import_updates_balance_and_last_updated_date(client):
    _add(client, name="Family Checking", balance=13000, as_of="2026-10-01", import_account_key="family checking")
    out = reconcile.auto_apply(client.base / "input", today=TODAY)
    assert out["applied"], out
    (acct,) = client.get("/api/cash-accounts").get_json()["accounts"]
    assert float(acct["balance"]) == 13894.27 and acct["as_of"] == "2026-10-14"


def test_refuses_blank_bad_and_duplicate(client):
    assert _add(client, name="  ", balance=1).status_code == 400
    assert _add(client, name="X", balance="abc").status_code == 400
    assert _add(client, name="X", balance=1, as_of="10/01/2026").status_code == 400
    assert _add(client, name="X", balance=1, import_account_key="ghost").status_code == 400
    assert _add(client, name="Savings", balance=1).status_code == 200
    assert _add(client, name="savings", balance=1).status_code == 400


def test_delete_removes_lot_setup_row_and_mapping(client):
    _add(client, name="High Yield Savings", balance=5000, import_account_key="high yield savings")
    assert client.post("/api/cash-accounts/delete", json={"account": "Nope"}).status_code == 400
    assert client.post("/api/cash-accounts/delete", json={"account": "High_Yield_Savings"}).status_code == 200
    assert client.get("/api/cash-accounts").get_json()["accounts"] == []
    with active_plan.workspace_store(client.base) as store:
        assert store.holdings.rows() == []
        assert store.dataset("ytd_account_setup").rows() == []
        assert store.monarch.mapping() == {}


def test_brokerage_account_is_not_a_cash_account(client):
    with active_plan.workspace_store(client.base, write=True) as store:
        ds = store.holdings
        ds.replace_all([{"account": "Brokerage", "symbol": "CASH", "purchase_date": "2026-01-01", "shares": "5", "purchase_price": "1", "lot_type": "buy"},
                        {"account": "Brokerage", "symbol": "VTI", "purchase_date": "2026-01-01", "shares": "5", "purchase_price": "200", "lot_type": "buy"}],
                       header=ds.extra_columns())
    assert client.get("/api/cash-accounts").get_json()["accounts"] == []
    assert client.post("/api/cash-accounts/delete", json={"account": "Brokerage"}).status_code == 400
