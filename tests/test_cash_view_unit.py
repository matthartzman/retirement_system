"""Cash panel view model (cash Phase 5): balance, anchor, difference against the CASH lot, income by tax class, ledger."""
from src import active_plan, broker_import, cash_view
from tests.broker_activity_fixtures import FILE_NAME, history_csv

ACCT = "Member_1_HSA"


def make(tmp_path, lot=True):
    (tmp_path / "input").mkdir(parents=True)
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("holdings").replace_all(
            [{"account": ACCT, "symbol": "CASH", "purchase_date": "2026-01-01", "shares": "10", "purchase_price": "1",
              "lot_type": "buy", "note": ""}] if lot else [])
    broker_import.commit(tmp_path / "input", text=history_csv(), file_name=FILE_NAME, account=ACCT, history_only=[ACCT])
    return tmp_path


def test_view_anchors_on_the_file_balance_and_shows_the_difference(tmp_path):
    ws = make(tmp_path, lot=False)             # no lot: the import wrote nothing, the lot stays unset
    with active_plan.workspace_store(ws, write=True) as store:
        store.dataset("holdings").replace_all([{"account": ACCT, "symbol": "CASH", "purchase_date": "2026-01-01",
                                                "shares": "10", "purchase_price": "1", "lot_type": "buy", "note": ""}])
        v = cash_view.build_view(store, year=2026)
    a = v["accounts"][0]
    assert (a["account"], a["anchor"], a["balance"], a["as_of"]) == (ACCT, "broker balance", 50.0, "2026-09-30")
    assert (a["cash_lot"], a["difference"]) == (10.0, 40.0)
    assert v["income_by_tax_class"].get("hsa", 0) > 0          # dividends of 2026 in an _hsa account


def test_ledger_rows_carry_pairing_status(tmp_path):
    ws = make(tmp_path)
    with active_plan.workspace_store(ws) as store:
        rows = cash_view.ledger_view(store, ACCT)["rows"]
        assert rows and {"date", "class", "amount", "pair_status"} <= set(rows[0])
        assert cash_view.ledger_view(store, "Nobody_Else")["rows"] == []


def test_unanchored_without_balance_or_lot():
    assert cash_view.anchor([], None)["type"] == "unanchored"
    a = cash_view.anchor([], {"shares": "7", "purchase_date": "2026-02-01"})
    assert (a["type"], a["balance"]) == ("confirmed CASH lot", 7.0)
