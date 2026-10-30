"""Broker activity bulk import: planning (pure), preview, commit with bulk confirm, idempotency, revert."""
import pytest

from src import active_plan, broker_import
from src.broker_activity import parse_file
from src.sales_ledger import ValidationError
from tests.broker_activity_fixtures import FILE_NAME, ROWS, history_csv

ACCT = "Member_1_HSA"
HOLDINGS = [
    {"account": ACCT, "symbol": "TOTL", "purchase_date": "2025-12-30", "shares": "5", "purchase_price": "90", "lot_type": "buy", "note": ""},
    {"account": ACCT, "symbol": "TOTL", "purchase_date": "2026-09-17", "shares": "2", "purchase_price": "100.4", "lot_type": "reinvestment", "note": ""},
    {"account": ACCT, "symbol": "CASH", "purchase_date": "2026-10-27", "shares": "50", "purchase_price": "1", "lot_type": "buy", "note": ""},
    {"account": "Member_1_Trust", "symbol": "TOTL", "purchase_date": "2020-01-01", "shares": "100", "purchase_price": "50", "lot_type": "buy", "note": ""},
]


@pytest.fixture
def ws(tmp_path):
    base = tmp_path / "ws"
    (base / "input").mkdir(parents=True)
    with active_plan.workspace_store(base, write=True) as store:
        store.dataset("holdings").replace_all(HOLDINGS)
    return base / "input"


def _rows():
    return parse_file("fidelity", history_csv(), account=ACCT, file_name=FILE_NAME).rows


def _holdings(ws):
    with active_plan.workspace_store(ws.parent) as store:
        return store.dataset("holdings").rows()


def test_plan_lots_add_and_present():
    plan = broker_import.plan_import(_rows(), HOLDINGS, account=ACCT)
    acts = {(l["kind"], l["run_date"]): l["action"] for l in plan["lots"]}
    assert acts == {("buy", "2026-05-12"): "add", ("reinvest", "2026-09-18"): "present"}
    present = next(l for l in plan["lots"] if l["action"] == "present")
    assert present["lot_date"] == "2026-09-17" and present["price_diff"] == 0.1


def test_plan_orders_replay_fifo_with_in_file_buy():
    orders = broker_import.plan_import(_rows(), HOLDINGS, account=ACCT)["orders"]
    by = {(o["symbol"], o["trade_date"]): o for o in orders}
    assert by[("SHRT", "2026-05-11")]["status"] == "no_lots"
    aug = by[("TOTL", "2026-08-12")]
    assert aug["status"] == "ready" and aug["allocation"] == {"0": 5.0, "new:0": 1.5}
    sep = by[("TOTL", "2026-09-15")]
    assert sep["status"] == "ready" and sep["allocation"] == {"new:0": 1.0}


def test_plan_sale_cannot_use_lot_bought_later():
    rows = [r for r in _rows() if not (r["kind"] == "buy")]
    hold = [h for h in HOLDINGS if h["purchase_date"] != "2025-12-30"]
    orders = broker_import.plan_import(rows, hold, account=ACCT)["orders"]
    aug = next(o for o in orders if o["trade_date"] == "2026-08-12")
    assert aug["status"] == "short" and aug["lots_short"] == 6.5   # the 09-17 lot is after the sale


def test_plan_position_check_flags_negative():
    hold = [h for h in HOLDINGS if h["purchase_date"] != "2025-12-30"]
    pos = {p["symbol"]: p for p in broker_import.plan_import(_rows(), hold, account=ACCT)["position"]}
    assert pos["TOTL"] == {"symbol": "TOTL", "holdings_now": 2.0, "bought": 10.0, "sold": 7.5, "after": 4.5, "negative": False}
    assert pos["SHRT"]["negative"] is True


def test_plan_income_totals_and_ignored():
    plan = broker_import.plan_import(_rows(), HOLDINGS, account=ACCT)
    assert plan["income_totals"] == {"dividend": 205.62}
    assert {i["action"][:12] for i in plan["ignored"]} >= {"RETURN EXCES", "PARTIC CONTR", "REINVESTMENT"}


def test_preview_needs_account_without_hint(ws):
    rep = broker_import.preview(ws, broker="fidelity", text=history_csv(), file_name="x.csv")
    assert rep["needs_account"] is True and ACCT in rep["accounts"]


def test_preview_is_read_only(ws):
    before = _holdings(ws)
    rep = broker_import.preview(ws, broker="fidelity", text=history_csv(), file_name=FILE_NAME, account=ACCT)
    assert rep["received"] == len(ROWS) and rep["counts"]["orders_ready"] == 2 and rep["tax_class"] == "hsa"
    assert any("SHRT" in w for w in rep["warnings"])
    assert _holdings(ws) == before
    with active_plan.workspace_store(ws.parent) as store:
        assert store.broker.list_imports() == [] and store.sales.list_candidates() == []


def test_commit_bulk_confirm_then_reimport_adds_nothing(ws):
    out = broker_import.commit(ws, broker="fidelity", text=history_csv(), file_name=FILE_NAME, account=ACCT,
                               confirm_method="fifo")
    assert out["lots_added"] == 1 and out["lots_present"] == 1 and len(out["confirmed"]) == 2 and len(out["queued"]) == 1
    totl = {(h["purchase_date"], h["shares"]) for h in _holdings(ws) if h["account"] == ACCT and h["symbol"] == "TOTL"}
    assert totl == {("2026-09-17", "2"), ("2026-05-12", "7.5")}           # 5 + 1.5 + 1 sold FIFO
    with active_plan.workspace_store(ws.parent) as store:
        sales = store.sales.list_sales()
        assert {(s["sale_date"], s["shares"], s["source"], s["tax_class"]) for s in sales} == {
            ("2026-08-12", 5.0, "broker", "hsa"), ("2026-08-12", 1.5, "broker", "hsa"), ("2026-09-15", 1.0, "broker", "hsa")}
        assert round(sum(s["proceeds"] for s in sales), 2) == 682.47 + 110
        assert all(s["settle_date"] for s in sales)
        assert store.broker.account_for("fidelity:5678") == ACCT
        assert len(store.broker.activity(account=ACCT)) == len(ROWS)
    again = broker_import.preview(ws, broker="fidelity", text=history_csv(), file_name=FILE_NAME)
    assert again["account"] == ACCT and again["will_write"] == [] and again["already_imported"] == len(ROWS)
    out2 = broker_import.commit(ws, broker="fidelity", text=history_csv(), file_name=FILE_NAME, account=ACCT)
    assert out2["rows_new"] == 0 and out2["candidates"] == []


def test_commit_without_confirm_queues_and_revert_restores(ws):
    before = _holdings(ws)
    out = broker_import.commit(ws, broker="fidelity", text=history_csv(), file_name=FILE_NAME, account=ACCT)
    assert out["confirmed"] == [] and len(out["queued"]) == 3
    assert len(_holdings(ws)) == len(before) + 1
    broker_import.revert(ws, out["import_id"])
    assert _holdings(ws) == before
    with active_plan.workspace_store(ws.parent) as store:
        assert store.sales.list_candidates() == [] and store.broker.activity() == []
        assert store.broker.get_import(out["import_id"])["status"] == "reverted"
    again = broker_import.commit(ws, broker="fidelity", text=history_csv(), file_name=FILE_NAME, account=ACCT)
    assert again["rows_new"] == len(ROWS)


def test_revert_refused_after_confirm(ws):
    out = broker_import.commit(ws, broker="fidelity", text=history_csv(), file_name=FILE_NAME, account=ACCT,
                               confirm_method="fifo")
    with pytest.raises(ValidationError, match="confirmed"):
        broker_import.revert(ws, out["import_id"])


def test_commit_supersedes_covered_monarch_sale(ws):
    with active_plan.workspace_store(ws.parent, write=True) as store:
        store.dataset("ytd_account_setup").replace_all([{"Account": "Health Savings Account (HSA)", "Role": "Investment",
                                                         "Mapped Investment Account": ACCT}])
        cid, _ = store.sales.add_candidate(source="monarch", sale_date="2026-08-13", account="Health Savings Account (HSA)",
                                           amount=682.0, monarch_id="m-1")
    out = broker_import.commit(ws, broker="fidelity", text=history_csv(), file_name=FILE_NAME, account=ACCT)
    assert out["superseded_monarch"] == [cid]
    broker_import.revert(ws, out["import_id"])
    with active_plan.workspace_store(ws.parent) as store:
        assert store.sales.list_candidates()[0]["state"] == "unmatched"


def test_commit_refuses_file_with_error_rows(ws):
    bad = '05/12/2026,YOU BOUGHT EXAMPLE (TOTL) (Cash),TOTL,EXAMPLE,Cash,100,"","","","","-1000",0,05/13/2026'
    with pytest.raises(ValidationError, match="quantity"):
        broker_import.commit(ws, broker="fidelity", text=history_csv(ROWS + [bad]), file_name=FILE_NAME, account=ACCT)
    with active_plan.workspace_store(ws.parent) as store:
        assert store.broker.list_imports() == []
