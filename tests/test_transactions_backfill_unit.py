"""Backfill the transaction log from broker imports and holdings; reconcile against the holdings."""
import pytest

from src import active_plan, broker_import, transactions
from tests.broker_activity_fixtures import ETRADE_FILE_NAME, FILE_NAME, etrade_csv, history_csv

HSA, IRA = "Member_1_HSA", "Member_1_IRA"
HOLDINGS = [
    {"account": HSA, "symbol": "TOTL", "purchase_date": "2025-12-30", "shares": "5", "purchase_price": "90", "lot_type": "buy", "note": ""},
    {"account": IRA, "symbol": "TOTL", "purchase_date": "2025-01-02", "shares": "20", "purchase_price": "90", "lot_type": "buy", "note": ""},
    {"account": IRA, "symbol": "91733P115", "purchase_date": "2025-02-01", "shares": "1500", "purchase_price": "0.5", "lot_type": "buy", "note": ""},
    {"account": IRA, "symbol": "ZZZ", "purchase_date": "2024-06-01", "shares": "7", "purchase_price": "3", "lot_type": "buy", "note": "hand entered"},
]


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("holdings").replace_all(HOLDINGS)
    broker_import.commit(tmp_path / "input", text=history_csv(), file_name=FILE_NAME, account=HSA, confirm_method="fifo")
    broker_import.commit(tmp_path / "input", text=etrade_csv(), file_name=ETRADE_FILE_NAME, account=IRA, confirm_method="fifo")
    return tmp_path


def run(ws):
    with active_plan.workspace_store(ws, write=True) as store, store.transaction():
        return transactions.backfill(store)


def test_open_lots_equal_holdings_after_backfill(ws):
    out = run(ws)
    assert out["added"]["sell"] >= 2 and out["added"]["opening"] >= 1 and not out["warnings"]
    with active_plan.workspace_store(ws) as store:
        assert transactions.reconcile(store) == []


def test_backfill_idempotent(ws):
    run(ws)
    with active_plan.workspace_store(ws) as store:
        first = len(store.transactions.list(include_voided=True))
    again = run(ws)
    assert sum(again["added"].values()) == 0
    with active_plan.workspace_store(ws) as store:
        assert len(store.transactions.list(include_voided=True)) == first


def test_lot_sold_by_broker_confirm_is_opened_with_its_original_shares(ws):
    run(ws)
    with active_plan.workspace_store(ws) as store:
        opening = [r for r in store.transactions.list(types=["opening"]) if r["symbol"] == "91733P115"]
        assert [r["shares"] for r in opening] == [1500.0]      # 500 still held plus the 1000 the redemption took
        sells = [r for r in store.transactions.list(types=["sell"]) if r["symbol"] == "91733P115"]
        assert [r["shares"] for r in sells] == [1000.0]
        assert [l["shares"] for l in transactions.open_lots(store, symbol="91733P115")] == [500.0]


def test_hand_entered_lot_becomes_opening_row(ws):
    run(ws)
    with active_plan.workspace_store(ws) as store:
        zzz = [r for r in store.transactions.list(types=["opening"]) if r["symbol"] == "ZZZ"]
        assert len(zzz) == 1 and zzz[0]["source"] == "backfill" and zzz[0]["txn_date"] == "2024-06-01"


def test_reconcile_reports_hand_edited_lot(ws):
    run(ws)
    with active_plan.workspace_store(ws, write=True) as store:
        rows = store.dataset("holdings").rows()
        for r in rows:
            if r["symbol"] == "ZZZ":
                r["shares"] = "9"
        rows.append({"account": HSA, "symbol": "NEW", "purchase_date": "2026-01-01", "shares": "1", "purchase_price": "5",
                     "lot_type": "buy", "note": ""})
        store.dataset("holdings").replace_all(rows)
    with active_plan.workspace_store(ws) as store:
        drift = transactions.reconcile(store)
        assert {d["symbol"] for d in drift} == {"ZZZ", "NEW"}
        assert all(d["reason"] for d in drift)
        assert [d["symbol"] for d in transactions.reconcile(store, account=HSA)] == ["NEW"]
