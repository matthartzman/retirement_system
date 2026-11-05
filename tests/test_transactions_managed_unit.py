"""Phase 3: managed accounts. The log writes a managed account's holdings; every log write materializes it."""
import pytest

from src import active_plan, sales_confirm, transactions
from src.sales_ledger import ValidationError

IRA, HSA = "Member_1_IRA", "Member_1_HSA"
HOLDINGS = [
    {"account": IRA, "symbol": "VTI", "purchase_date": "2023-01-10", "shares": "10", "purchase_price": "100", "lot_type": "buy", "note": ""},
    {"account": IRA, "symbol": "VTI", "purchase_date": "2025-12-02", "shares": "5", "purchase_price": "200", "lot_type": "buy", "note": ""},
    {"account": HSA, "symbol": "BND", "purchase_date": "2024-01-02", "shares": "7", "purchase_price": "50", "lot_type": "buy", "note": ""},
    {"account": IRA, "symbol": "CASH", "purchase_date": "", "shares": "100", "purchase_price": "1", "lot_type": "cash", "note": ""},
]
MSG = "managed by the transaction log"


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("holdings").replace_all(HOLDINGS)
    with active_plan.workspace_store(tmp_path, write=True) as store, store.transaction():
        transactions.backfill(store)
    return tmp_path


def holdings(ws, account=None):
    with active_plan.workspace_store(ws) as store:
        return [r for r in store.dataset("holdings").rows() if account in (None, r["account"])]


def shares(ws, account, symbol="VTI"):
    return sorted(float(r["shares"]) for r in holdings(ws, account) if r["symbol"] == symbol)


def cand(ws, **over):
    f = dict(source="broker", sale_date="2026-07-06", account=IRA, symbol="VTI", shares=12.0, price=250.0, amount=3000.0)
    f.update(over)
    with active_plan.workspace_store(ws, write=True) as store:
        return store.sales.add_candidate(**f)[0]


def lots(ws, account=IRA):
    with active_plan.workspace_store(ws) as store:
        return transactions.open_lots(store, account=account, symbol="VTI")


def confirm(ws, cid, alloc):
    return sales_confirm.confirm(ws / "input", cid, allocation=alloc, tax_class="pre_tax", trade_date="2026-07-06")


def test_default_is_unmanaged_and_set_managed_validates(ws):
    assert transactions.managed_view(ws / "input") == {"managed": []}
    with pytest.raises(ValidationError):
        transactions.set_managed(ws / "input", "Nobody_Else", True)
    out = transactions.set_managed(ws / "input", IRA, True)
    assert out["managed"] and transactions.managed_view(ws / "input") == {"managed": [IRA]}


def test_set_managed_refused_while_log_differs_from_holdings(ws):
    with active_plan.workspace_store(ws, write=True) as store:
        rows = store.dataset("holdings").rows()
        rows[0]["shares"] = "11"
        store.dataset("holdings").replace_all(rows)
    with pytest.raises(ValidationError, match="differ"):
        transactions.set_managed(ws / "input", IRA, True)


def test_set_managed_refused_before_log_is_started(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("holdings").replace_all(HOLDINGS)
    with pytest.raises(ValidationError, match="start the transaction log"):
        transactions.set_managed(tmp_path / "input", IRA, True)


def test_log_write_materializes_round_trip(ws):
    transactions.set_managed(ws / "input", IRA, True)
    new = transactions.add(ws / "input", txn_date="2026-03-01", account=IRA, type="buy", symbol="VTI", shares=3, price=210)
    assert shares(ws, IRA) == [3.0, 5.0, 10.0]
    sale = transactions.add(ws / "input", txn_date="2026-04-01", account=IRA, type="sell", symbol="VTI", shares=4, price=220)
    assert sum(shares(ws, IRA)) == 14
    revised = transactions.revise(ws / "input", new, shares=2)
    assert sum(shares(ws, IRA)) == 13
    transactions.void(ws / "input", sale)
    assert sum(shares(ws, IRA)) == 17
    assert shares(ws, HSA, "BND") == [7.0]
    assert [r["shares"] for r in holdings(ws, IRA) if r["symbol"] == "CASH"] == ["100"]
    assert revised != new


def test_unmanaged_account_holdings_are_not_rewritten(ws):
    transactions.add(ws / "input", txn_date="2026-03-01", account=IRA, type="buy", symbol="VTI", shares=3, price=210)
    assert shares(ws, IRA) == [5.0, 10.0]


def test_transfer_materializes_the_managed_source_only(ws):
    transactions.set_managed(ws / "input", IRA, True)
    lot = lots(ws)[0]["lot_txn_id"]
    transactions.transfer(ws / "input", from_account=IRA, to_account=HSA, symbol="VTI", allocation={lot: 4}, txn_date="2026-05-01")
    assert sum(shares(ws, IRA)) == 11
    assert shares(ws, HSA) == []   # HSA is not managed: the move shows in the log only (and as drift until it is)
    assert shares(ws, HSA, "BND") == [7.0]


def test_unmanage_keeps_last_rows(ws):
    transactions.set_managed(ws / "input", IRA, True)
    transactions.add(ws / "input", txn_date="2026-03-01", account=IRA, type="buy", symbol="VTI", shares=3, price=210)
    before = holdings(ws, IRA)
    assert transactions.set_managed(ws / "input", IRA, False)["managed"] is False
    assert holdings(ws, IRA) == before
    transactions.add(ws / "input", txn_date="2026-03-02", account=IRA, type="buy", symbol="VTI", shares=1, price=210)
    assert holdings(ws, IRA) == before   # no longer materialized


def test_managed_account_confirm_materializes_holdings(ws):
    transactions.set_managed(ws / "input", IRA, True)
    cid = cand(ws)
    panel = sales_confirm.panel(ws / "input", cid)
    assert panel["managed"] and panel["confirmable"]
    old = next(l for l in panel["lots"] if l["purchase_date"] == "2023-01-10")
    assert old["lot_id"] == str(lots(ws)[0]["lot_txn_id"])
    out = confirm(ws, cid, {old["lot_id"]: 10, [l for l in panel["lots"] if l is not old][0]["lot_id"]: 2})
    assert out["sale_ids"] and shares(ws, IRA) == [3.0]
    with active_plan.workspace_store(ws) as store:
        sells = [r for r in store.transactions.list() if r["type"] == "sell"]
        assert len(sells) == 1 and sells[0]["candidate_id"] == cid and transactions.reconcile(store, IRA) == []
    cash = [r for r in holdings(ws, IRA) if r["symbol"] == "CASH"]
    assert [r["shares"] for r in cash] == ["100"]   # confirm never credits CASH
    sales_confirm.undo(ws / "input", cid)
    assert shares(ws, IRA) == [5.0, 10.0]
    with active_plan.workspace_store(ws) as store:
        assert not [r for r in store.transactions.list() if r["type"] == "sell"]


def test_undo_after_unmanaging_restores_holdings(ws):
    transactions.set_managed(ws / "input", IRA, True)
    cid = cand(ws, shares=3.0, amount=750.0)
    panel = sales_confirm.panel(ws / "input", cid)
    confirm(ws, cid, {panel["lots"][0]["lot_id"]: 3})
    transactions.set_managed(ws / "input", IRA, False)
    sales_confirm.undo(ws / "input", cid)
    assert sum(shares(ws, IRA)) == 15


def test_monarch_confirm_refused_for_managed_account(ws):
    transactions.set_managed(ws / "input", IRA, True)
    cid = cand(ws, source="monarch", monarch_id="m-1")
    panel = sales_confirm.panel(ws / "input", cid)
    assert not panel["confirmable"] and MSG in panel["refusal"] and "dismiss this one" in panel["refusal"]
    with pytest.raises(ValidationError, match=MSG):
        confirm(ws, cid, {panel["lots"][0]["lot_id"]: 12}) if panel["lots"] else sales_confirm.confirm(
            ws / "input", cid, allocation={}, tax_class="pre_tax", trade_date="2026-07-06")
    assert shares(ws, IRA) == [5.0, 10.0]
    sales_confirm.dismiss(ws / "input", cid, reason="other")


def test_monarch_confirm_still_works_for_unmanaged_account(ws):
    cid = cand(ws, source="monarch", monarch_id="m-2", shares=2.0, amount=500.0)
    confirm(ws, cid, {"0": 2})
    assert sum(shares(ws, IRA)) == 13


def test_import_into_managed_account_queues_sales_and_materializes(tmp_path):
    from src import broker_import
    from tests.broker_activity_fixtures import FILE_NAME, history_csv
    (tmp_path / "input").mkdir()
    hold = [{"account": HSA, "symbol": "TOTL", "purchase_date": "2025-12-30", "shares": "5", "purchase_price": "90", "lot_type": "buy", "note": ""}]
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("holdings").replace_all(hold)
    with active_plan.workspace_store(tmp_path, write=True) as store, store.transaction():
        transactions.backfill(store)
    transactions.set_managed(tmp_path / "input", HSA, True)
    out = broker_import.commit(tmp_path / "input", text=history_csv(), file_name=FILE_NAME, account=HSA, confirm_method="fifo")
    assert out["confirmed"] == []   # a managed account's sales are confirmed in the queue, through the log
    with active_plan.workspace_store(tmp_path) as store:
        assert transactions.reconcile(store, HSA) == []
        assert {r["symbol"] for r in store.dataset("holdings").rows()} >= {"TOTL"}


def test_managed_routes(ws, monkeypatch):
    from src.server import app, plan_routes
    monkeypatch.setattr(plan_routes, "_ytd_input_root", lambda: ws / "input")
    c = app.test_client()
    assert c.get("/api/transactions/accounts").get_json()["managed"] == []
    assert c.post(f"/api/transactions/accounts/{IRA}/managed", json={"managed": "yes"}).status_code == 400
    r = c.post(f"/api/transactions/accounts/{IRA}/managed", json={"managed": True})
    assert r.status_code == 200 and r.get_json()["result"]["managed"] is True
    assert c.get("/api/transactions/log").get_json()["managed"] == [IRA]
    assert c.post("/api/transactions/accounts/Nobody_Else/managed", json={"managed": True}).status_code == 400
    assert c.post(f"/api/transactions/accounts/{IRA}/managed", json={"managed": False}).get_json()["result"]["managed"] is False


def test_reconcile_ignores_cash_lots_the_log_does_not_own(ws):
    with active_plan.workspace_store(ws, write=True) as store:           # an import replaces the CASH lot: new date and balance
        rows = [r for r in store.dataset("holdings").rows() if r["symbol"] != "CASH"]
        store.dataset("holdings").replace_all(rows + [{"account": IRA, "symbol": "CASH", "purchase_date": "2026-11-03",
                                                       "shares": "55", "purchase_price": "1", "lot_type": "buy", "note": ""}])
    with active_plan.workspace_store(ws) as store:
        assert transactions.reconcile(store) == []
        assert transactions.reconcile(store, IRA) == []
