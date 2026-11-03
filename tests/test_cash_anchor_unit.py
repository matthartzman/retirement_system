"""Anchored cash balance (cash Phase 4, task C.2): an import with the broker's running balance writes the CASH lot."""
import pytest

from src import active_plan, broker_import, cash_anchor, transactions
from src.sales_ledger import ValidationError
from tests.broker_activity_fixtures import ETRADE_ACCOUNT, FILE_NAME, etrade_csv, history_csv

ACCT = "Member_1_HSA"
TOTL = {"account": ACCT, "symbol": "TOTL", "purchase_date": "2025-12-30", "shares": "5", "purchase_price": "90",
        "lot_type": "buy", "note": ""}


def cash_lot(shares="10", date="2026-01-01"):
    return {"account": ACCT, "symbol": "CASH", "purchase_date": date, "shares": shares, "purchase_price": "1",
            "lot_type": "buy", "note": ""}


def make_ws(tmp_path, holdings):
    (tmp_path / "input").mkdir(parents=True)
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("holdings").replace_all(holdings)
    return tmp_path


def lots(ws):
    with active_plan.workspace_store(ws) as store:
        return [(r["symbol"], r["purchase_date"], r["shares"]) for r in store.dataset("holdings").rows()]


def do_import(ws, **kw):
    return broker_import.commit(ws / "input", text=history_csv(), file_name=FILE_NAME, account=ACCT, **kw)


def summary(ws, import_id):
    with active_plan.workspace_store(ws) as store:
        return store.broker.get_import(import_id)["summary"]


def test_anchored_import_writes_balance_with_old_and_new_and_revert_restores(tmp_path):
    ws = make_ws(tmp_path, [TOTL, cash_lot()])
    out = do_import(ws, confirm_method=None, history_only=[ACCT])
    assert ("CASH", "2026-09-30", "50") in lots(ws)       # the file's latest running balance (09/30: 50.00)
    cw = summary(ws, out["import_id"])["cash_write"]
    assert (cw["old"], cw["old_date"], cw["new"], cw["new_date"]) == ("10", "2026-01-01", "50", "2026-09-30")
    broker_import.revert(ws / "input", out["import_id"])
    assert ("CASH", "2026-01-01", "10") in lots(ws)


def test_revert_refuses_when_the_cash_lot_was_edited_since(tmp_path):
    ws = make_ws(tmp_path, [TOTL, cash_lot()])
    out = do_import(ws, history_only=[ACCT])
    with active_plan.workspace_store(ws, write=True) as store:
        rows = store.dataset("holdings").rows()
        next(r for r in rows if r["symbol"] == "CASH")["shares"] = "77"
        store.dataset("holdings").replace_all(rows)
    with pytest.raises(ValidationError):
        broker_import.revert(ws / "input", out["import_id"])
    assert ("CASH", "2026-09-30", "77") in lots(ws)


def test_unanchored_import_writes_nothing(tmp_path):
    ws = make_ws(tmp_path, [{**cash_lot(), "account": "Member_1_Rollover_IRA"}])
    before = lots(ws)
    broker_import.commit(ws / "input", broker="etrade", text=etrade_csv(), file_name="etrade.csv",
                         account="Member_1_Rollover_IRA", history_only=["Member_1_Rollover_IRA"])
    assert lots(ws) == before
    rep = broker_import.preview(ws / "input", broker="etrade", text=etrade_csv(), file_name="etrade.csv",
                                account="Member_1_Rollover_IRA")
    assert rep["parts"][0]["cash"]["anchored"] is False and rep["parts"][0]["cash"]["write"] is False


def test_large_change_warns_in_preview_and_small_change_does_not(tmp_path):
    ws = make_ws(tmp_path, [TOTL, cash_lot("5000")])
    rep = broker_import.preview(ws / "input", text=history_csv(), file_name=FILE_NAME, account=ACCT)
    assert "check it" in rep["parts"][0]["cash"]["warning"] and any("check it" in w for w in rep["warnings"])
    assert not cash_anchor.large_change(100, 600) and cash_anchor.large_change(100, 5000)
    assert not cash_anchor.large_change(10000, 10500)


def test_no_cash_lot_or_older_file_writes_nothing(tmp_path):
    ws = make_ws(tmp_path, [TOTL])
    do_import(ws, history_only=[ACCT])
    assert all(s != "CASH" for s, _, _ in lots(ws))
    ws2 = make_ws(tmp_path / "b", [TOTL, cash_lot("123", "2026-10-27")])
    do_import(ws2, history_only=[ACCT])
    assert ("CASH", "2026-10-27", "123") in lots(ws2)


def test_managed_accounts_import_writes_cash_and_no_other_lot(tmp_path):
    ws = make_ws(tmp_path, [TOTL, cash_lot()])
    with active_plan.workspace_store(ws, write=True) as store, store.transaction():
        transactions.backfill(store)
    others = [l for l in lots(ws) if l[0] != "CASH"]
    do_import(ws, history_only=[ACCT])
    assert ("CASH", "2026-09-30", "50") in lots(ws)
    assert [l for l in lots(ws) if l[0] != "CASH"] == others
    with active_plan.workspace_store(ws) as store:
        assert [d for d in transactions.reconcile(store) if str(d["symbol"]).upper() != "CASH"] == []


def test_confirming_a_sale_does_not_credit_cash(tmp_path):
    acct = "Member_1_Rollover_IRA"
    ws = make_ws(tmp_path, [{**TOTL, "account": acct, "shares": "50", "purchase_date": "2020-01-01"},
                            {**cash_lot("10"), "account": acct}])
    out = broker_import.commit(ws / "input", broker="etrade", text=etrade_csv(), file_name="etrade.csv", account=acct,
                               confirm_method="fifo")
    assert out["confirmed"]                              # the sale was confirmed ...
    assert ("CASH", "2026-01-01", "10") in lots(ws)      # ... and CASH is untouched (the broker balance is the writer)


# ---- anchor 2: the confirmed CASH lot plus the file's flows (cash design 4.5) ----------------------------------------
def frow(day, kind, amount, **kw):
    return {"run_date": day, "kind": kind, "amount": amount, "row_key": f"{day}{kind}{amount}", **kw}


def test_anchor2_rolls_the_confirmed_lot_forward_by_the_files_flows():
    rows = [frow("2026-03-02", "dividend", 5.0), frow("2026-03-03", "other", 500.0, action="Contribution"),
            frow("2026-03-04", "other", -25.0, action="Service Fee"), frow("2026-03-05", "buy", -100.0)]
    plan = cash_anchor.plan_write(rows, [cash_lot("1000", "2026-03-01")], ACCT)
    assert plan["write"] and plan["anchored"] and plan["anchor"] == "confirmed CASH lot plus flows"
    assert (plan["old"], plan["new"], plan["new_date"], plan["flows"]) == ("1000", "1380", "2026-03-05", "380")


def test_anchor2_skips_rows_on_or_before_the_lot_date_and_rows_already_imported():
    rows = [frow("2026-03-01", "dividend", 50.0), frow("2026-03-02", "dividend", 5.0), frow("2026-03-03", "dividend", 7.0)]
    plan = cash_anchor.plan_write(rows, [cash_lot("1000", "2026-03-01")], ACCT, new_rows=rows[:2])
    assert plan["new"] == "1005"          # 03-01 is inside the confirmed balance; 03-03 was imported before


def test_anchor2_needs_a_dated_lot_and_a_contiguous_newer_file_and_never_writes_otherwise():
    rows = [frow("2026-03-10", "dividend", 5.0)]
    for lot, why in [(cash_lot("10", ""), "no date"), (cash_lot("10", "2026-03-01"), "missing"),
                     (cash_lot("10", "2026-03-10"), "not after")]:
        plan = cash_anchor.plan_write(rows, [lot], ACCT)
        assert not plan["write"] and not plan["anchored"] and why in plan["reason"], plan
    assert not cash_anchor.plan_write(rows, [], ACCT)["write"]                      # no lot at all
    assert cash_anchor.plan_write(rows, [cash_lot("10", "2026-03-09")], ACCT)["new"] == "15"   # one day after is contiguous


def test_anchor2_ignores_sweep_legs_and_in_kind_transfers_and_the_broker_balance_wins():
    rows = [frow("2026-03-02", "buy", -10.0, sweep=True), frow("2026-03-02", "other", 0.0, action="Transfer",
                                                              symbol="TOTL", quantity=5.0)]
    assert cash_anchor.plan_write(rows, [cash_lot("10", "2026-03-01")], ACCT)["new"] == "10"
    both = [frow("2026-03-02", "dividend", 5.0, cash_balance=777.0)]
    plan = cash_anchor.plan_write(both, [cash_lot("10", "2026-03-01")], ACCT)
    assert plan["anchor"] == "broker balance" and plan["new"] == "777"


def test_anchor2_import_writes_with_old_new_and_revert_restores(tmp_path):
    acct = "Member_1_Rollover_IRA"
    lot = {**cash_lot("100", "2026-04-30"), "account": acct}      # the E*Trade file's first day is 2026-05-01
    ws = make_ws(tmp_path, [lot])
    out = broker_import.commit(ws / "input", broker="etrade", text=etrade_csv(), file_name="etrade.csv", account=acct,
                               history_only=[acct])
    cw = summary(ws, out["import_id"])["cash_write"]
    assert cw and cw["anchor"] == "confirmed CASH lot plus flows" and cw["old"] == "100"
    assert ("CASH", cw["new_date"], cw["new"]) in lots(ws) and cw["new"] != "100"
    again = broker_import.preview(ws / "input", broker="etrade", text=etrade_csv(), file_name="etrade.csv", account=acct)
    assert again["parts"][0]["cash"]["write"] is False         # re-importing the same file cannot add the flows twice
    broker_import.revert(ws / "input", out["import_id"])
    assert ("CASH", "2026-04-30", "100") in lots(ws)
