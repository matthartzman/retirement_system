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


def test_withdrawals_by_pair_status_are_reported_not_applied():
    led = [{"date": "2026-03-01", "class": "distribution", "amount": -300.0, "counts": True, "in_kind": False, "pair_status": "external_withdrawal"},
           {"date": "2026-03-02", "class": "transfer_out", "amount": -200.0, "counts": True, "in_kind": False, "pair_status": "internal"},
           {"date": "2026-03-03", "class": "transfer_out", "amount": -50.0, "counts": True, "in_kind": False, "pair_status": "unmatched"},
           {"date": "2025-03-03", "class": "distribution", "amount": -999.0, "counts": True, "in_kind": False, "pair_status": "external_withdrawal"},
           {"date": "2026-03-04", "class": "excess_return", "amount": -100.0, "counts": True, "in_kind": False, "pair_status": "unpaired"},
           {"date": "2026-03-05", "class": "income", "amount": 5.0, "counts": True, "in_kind": False, "pair_status": "unpaired"}]
    assert cash_view.withdrawals_by_status(led, 2026) == {"external_withdrawal": 300.0, "internal": 200.0, "unmatched": 50.0}
    assert cash_view.excess_return(led, 2026) == {"count": 1, "amount": 100.0}   # untaxed; its earnings are the user's to enter


def test_view_rows_carry_tax_class_withdrawals_and_excess_return(tmp_path):
    ws = make(tmp_path)
    with active_plan.workspace_store(ws) as store:
        a = cash_view.build_view(store, year=2026)["accounts"][0]
    assert a["tax_class"] == "hsa"
    assert a["excess_return"] == {"count": 1, "amount": 100.0}
    assert set(a["withdrawals"]) == {"external_withdrawal", "internal", "unmatched"}
