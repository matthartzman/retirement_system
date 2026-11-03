"""materialize: the holdings of one account rewritten from the log's open lots."""
import pytest

from src import active_plan, broker_import, transactions
from tests.broker_activity_fixtures import ETRADE_FILE_NAME, FILE_NAME, etrade_csv, history_csv

HSA, IRA = "Member_1_HSA", "Member_1_IRA"
HOLDINGS = [
    {"account": HSA, "symbol": "TOTL", "purchase_date": "2025-12-30", "shares": "5", "purchase_price": "90", "lot_type": "buy", "note": ""},
    {"account": IRA, "symbol": "TOTL", "purchase_date": "2025-01-02", "shares": "20", "purchase_price": "90", "lot_type": "buy", "note": ""},
    {"account": IRA, "symbol": "91733P115", "purchase_date": "2025-02-01", "shares": "1500", "purchase_price": "0.5", "lot_type": "buy", "note": ""},
    {"account": IRA, "symbol": "ZZZ", "purchase_date": "2024-06-01", "shares": "7", "purchase_price": "3", "lot_type": "buy", "note": "hand entered"},
    {"account": IRA, "symbol": "CASH", "purchase_date": "", "shares": "1234.5", "purchase_price": "1", "lot_type": "cash", "note": ""},
]


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("holdings").replace_all(HOLDINGS)
    broker_import.commit(tmp_path / "input", text=history_csv(), file_name=FILE_NAME, account=HSA, confirm_method="fifo")
    broker_import.commit(tmp_path / "input", text=etrade_csv(), file_name=ETRADE_FILE_NAME, account=IRA, confirm_method="fifo")
    with active_plan.workspace_store(tmp_path, write=True) as store, store.transaction():
        transactions.backfill(store)
    return tmp_path


def rows(ws, account=None):
    with active_plan.workspace_store(ws) as store:
        return [r for r in store.dataset("holdings").rows() if account is None or r["account"] == account]


def mat(ws, account):
    with active_plan.workspace_store(ws, write=True) as store, store.transaction():
        return transactions.materialize(store, account)


def shape(rs):
    return sorted((r["account"], r["symbol"], r["purchase_date"], float(r["purchase_price"]), r["lot_type"], r["note"], round(float(r["shares"]), 6)) for r in rs)


def test_materialized_rows_match_pre_switch_holdings(ws):
    before = rows(ws)
    mat(ws, IRA)
    mat(ws, HSA)
    assert shape(rows(ws)) == shape(before)


def test_materialize_leaves_other_accounts_and_cash_lot_untouched(ws):
    hsa_before = rows(ws, HSA)
    cash_before = [r for r in rows(ws) if r["symbol"] == "CASH"]
    n = mat(ws, IRA)
    assert n >= 3 and rows(ws, HSA) == hsa_before
    assert [r for r in rows(ws) if r["symbol"] == "CASH"] == cash_before


def test_materialize_is_idempotent_and_keeps_order(ws):
    mat(ws, IRA)
    once = rows(ws)
    mat(ws, IRA)
    assert rows(ws) == once
    ira_symbols = [r["symbol"] for r in once if r["account"] == IRA and r["symbol"] != "CASH"]
    assert ira_symbols == sorted(ira_symbols)


def test_materialize_follows_a_log_edit(ws):
    with active_plan.workspace_store(ws) as store:
        lot = next(l for l in transactions.open_lots(store, account=IRA, symbol="ZZZ"))
    transactions.revise(ws / "input", lot["lot_txn_id"], shares=9)
    mat(ws, IRA)
    assert [float(r["shares"]) for r in rows(ws, IRA) if r["symbol"] == "ZZZ"] == [9.0]
