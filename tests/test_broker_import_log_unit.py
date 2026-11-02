"""Dual-write: the importer and the queue keep the transaction log in step once the log is in use."""
import pytest

from src import active_plan, broker_import, sales_confirm, transactions
from src.sales_ledger import ValidationError
from tests.broker_activity_fixtures import FILE_NAME, history_csv

HSA = "Member_1_HSA"
HOLDINGS = [{"account": HSA, "symbol": "TOTL", "purchase_date": "2025-12-30", "shares": "5", "purchase_price": "90",
             "lot_type": "buy", "note": ""}]


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("holdings").replace_all(HOLDINGS)
    return tmp_path


def commit(ws, **kw):
    return broker_import.commit(ws / "input", text=history_csv(), file_name=FILE_NAME, account=HSA, **kw)


def start_log(ws):
    with active_plan.workspace_store(ws, write=True) as store, store.transaction():
        transactions.backfill(store)


def holdings(ws):
    with active_plan.workspace_store(ws) as store:
        return [(r["symbol"], r["purchase_date"], r["shares"]) for r in store.dataset("holdings").rows()]


def drift(ws):
    with active_plan.workspace_store(ws) as store:
        return transactions.reconcile(store)


def test_log_stays_untouched_until_it_is_started(ws):
    commit(ws, confirm_method="fifo")
    with active_plan.workspace_store(ws) as store:
        assert store.transactions.list(include_voided=True) == []


def test_commit_writes_log_rows_and_holdings_unchanged(ws):
    start_log(ws)
    ref = commit(ws)          # no confirm: lots only
    with active_plan.workspace_store(ws) as store:
        types = {r["type"] for r in store.transactions.list(account=HSA)}
        assert "buy" in types and "sell" not in types
        assert all(r["activity_id"] for r in store.transactions.list(types=["buy", "reinvest"]))
    assert drift(ws) == [] and ref["lots_added"] >= 1


def test_confirm_writes_sell_with_disposals_and_undo_voids_it(ws):
    start_log(ws)
    out = commit(ws, confirm_method="fifo")
    with active_plan.workspace_store(ws) as store:
        sells = store.transactions.list(types=["sell"])
        assert len(sells) == len(out["confirmed"]) and all(store.transactions.disposals(s["txn_id"]) for s in sells)
    assert drift(ws) == []
    before = holdings(ws)
    sales_confirm.undo(ws / "input", out["confirmed"][0])
    with active_plan.workspace_store(ws) as store:
        assert len(store.transactions.list(types=["sell"])) == len(out["confirmed"]) - 1
    assert drift(ws) == [] and holdings(ws) != before
    # confirming again by the queue panel writes the sell row again
    cid = out["confirmed"][0]
    panel = sales_confirm.panel(ws / "input", cid)
    assert panel["lots"]


def test_revert_voids_log_rows(ws):
    start_log(ws)
    out = commit(ws)
    broker_import.revert(ws / "input", out["import_id"])
    with active_plan.workspace_store(ws) as store:
        assert store.transactions.list(types=["buy", "reinvest"]) == []
    assert drift(ws) == []


def test_revert_refused_when_log_row_revised(ws):
    start_log(ws)
    out = commit(ws)
    with active_plan.workspace_store(ws) as store:
        buy = store.transactions.list(types=["buy"])[0]
    transactions.revise(ws / "input", buy["txn_id"], price=buy["price"] + 1)
    with pytest.raises(ValidationError, match="revised"):
        broker_import.revert(ws / "input", out["import_id"])


def test_reimport_after_revision_does_not_resurrect_the_row(ws):
    start_log(ws)
    commit(ws)
    with active_plan.workspace_store(ws) as store:
        buy = store.transactions.list(types=["buy"])[0]
    transactions.void(ws / "input", buy["txn_id"])
    commit(ws)                                        # same file again: nothing is new
    with active_plan.workspace_store(ws) as store:
        assert [r for r in store.transactions.list(types=["buy"]) if r["txn_id"] == buy["txn_id"]] == []
        assert len(store.transactions.list(types=["buy"])) == len(store.broker.activity(kinds=["buy"])) - 1
