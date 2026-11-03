"""Cash ledger builder (cash tracking Phase 2): classes, sweep exclusion, source precedence, journals, in-kind rows."""
from __future__ import annotations

from src.broker_activity import etrade, fidelity, vanguard
from src.cash_ledger import build_ledger
from tests.broker_activity_fixtures import etrade_csv, history_csv, vanguard_csv

ACCT = "fidelity:5678"


def _rows(parsed, import_id=1, account=ACCT):
    return [{**r, "import_id": import_id, "account": account, "row_key": f"k{import_id}-{i}", "activity_id": i}
            for i, r in enumerate(parsed.rows)]


def _acct_rows(parsed, hint):
    return [{**r, "import_id": 1, "account": hint, "row_key": f"v{hint}{i}"}
            for i, r in enumerate(x for x in parsed.rows if x.get("account_hint") == hint)]


def _imp(import_id=1, date_from="2026-01-01", date_to="2026-12-31", status="applied", account=ACCT):
    return {"import_id": import_id, "account": account, "date_from": date_from, "date_to": date_to, "status": status}


def _b(**kw):
    base = {"import_id": 1, "row_key": "x", "run_date": "2026-03-01", "kind": "other", "sweep": False, "action": "",
            "symbol": "", "description": "", "quantity": None, "amount": 0.0, "cash_balance": None}
    return {**base, **kw}


def _m(date, amount, category, merchant="m"):
    return {"Date": date, "Amount": str(amount), "Category": category, "Merchant": merchant, "Account": "Mon IRA"}


def _by_class(rows, cls):
    return [r for r in rows if r["class"] == cls]


def test_fidelity_sweep_pair_nets_to_the_dividend_only():
    parsed = fidelity.parse(history_csv(), file_name="History_for_Account_X12345678.csv")
    rows = build_ledger(ACCT, _rows(parsed), [_imp()], [])
    fd = [r for r in rows if r["date"] == "2026-09-30"]
    assert len(fd) == 1
    assert fd[0]["class"] == "income" and fd[0]["amount"] == 0.12
    assert not any(r["symbol"] == "FDRXX" and r["amount"] < 0 for r in rows)


def test_fidelity_non_sweep_reinvestment_is_a_settlement_and_cash_balance_is_carried():
    parsed = fidelity.parse(history_csv(), file_name="History_for_Account_X12345678.csv")
    rows = build_ledger(ACCT, _rows(parsed), [_imp()], [])
    d = [r for r in rows if r["date"] == "2026-09-18"]
    assert sorted(r["class"] for r in d) == ["income", "trade"]
    assert round(sum(r["amount"] for r in d), 2) == 0.0
    assert any(r["cash_balance"] == 250.88 for r in d)
    contrib = [r for r in rows if r["date"] == "2026-01-16"][0]
    assert contrib["class"] == "contribution" and contrib["amount"] == 1000 and contrib["cash_balance"] == 1000
    excess = [r for r in rows if r["date"] == "2026-09-17"][0]
    assert excess["class"] == "excess_return" and excess["amount"] == -100


def test_all_rows_start_unpaired_and_carry_source():
    parsed = fidelity.parse(history_csv(), file_name="History_for_Account_X12345678.csv")
    rows = build_ledger(ACCT, _rows(parsed), [_imp()], [_m("2027-02-01", 10, "Other Income")])
    assert {r["pair_status"] for r in rows} == {"unpaired"}
    assert {r["source"] for r in rows} == {"broker", "monarch"}


def test_vanguard_sweep_in_out_and_vmfxx_reinvest_are_internal():
    parsed = vanguard.parse(vanguard_csv())
    rows2 = build_ledger("vanguard:2222", _acct_rows(parsed, "vanguard:2222"), [_imp(account="vanguard:2222")], [])
    assert round(sum(r["amount"] for r in rows2 if r["date"] == "2026-09-30"), 2) == 2.5
    rows1 = build_ledger("vanguard:1111", _acct_rows(parsed, "vanguard:1111"), [_imp(account="vanguard:1111")], [])
    assert not any("sweep" in (r["action"] or "").lower() for r in rows1)
    sell = [r for r in rows1 if r["class"] == "trade" and r["date"] == "2026-09-15"]
    assert [r["amount"] for r in sell] == [999.5]


def test_vanguard_withdrawal_is_a_distribution():
    parsed = vanguard.parse(vanguard_csv())
    rows = build_ledger("vanguard:2222", _acct_rows(parsed, "vanguard:2222"), [_imp(account="vanguard:2222")], [])
    assert [r["amount"] for r in _by_class(rows, "distribution")] == [-500.0]


def test_etrade_classes():
    parsed = etrade.parse(etrade_csv())
    rows = build_ledger("etrade:9876", _rows(parsed, account="etrade:9876"), [_imp(account="etrade:9876")], [])
    assert [r["amount"] for r in _by_class(rows, "contribution")] == [500.0]
    assert [r["amount"] for r in _by_class(rows, "fee")] == [-25.0]
    # bank deposit program interest is a sweep-flagged income row: still income
    assert 0.07 in [r["amount"] for r in _by_class(rows, "income")]


def test_adjustment_journals_net_to_zero_and_are_not_flows():
    rows_in = [
        _b(run_date="2026-03-01", action="Transfer", description="TRNSFR CASH TO MARGIN", amount=-300.0),
        _b(run_date="2026-03-01", action="Transfer", description="TRNSFR MARGIN TO CASH", amount=300.0),
        _b(run_date="2026-03-02", action="Adjustment", description="ADJ", amount=12.5),
        _b(run_date="2026-03-02", action="Adjustment", description="ADJ", amount=-12.5),
    ]
    rows = build_ledger("etrade:9876", rows_in, [_imp(account="etrade:9876")], [])
    adj = _by_class(rows, "adjustment")
    assert len(adj) == 4 and round(sum(r["amount"] for r in adj), 2) == 0.0
    assert not any(r["counts"] for r in adj)
    assert not _by_class(rows, "transfer_in") and not _by_class(rows, "transfer_out")


def test_in_kind_transfer_has_zero_cash_and_is_not_a_flow():
    rows = build_ledger("etrade:9876", [_b(action="Transfer", description="TFR FROM ACCT", symbol="TOTL", quantity=10.0, amount=None)],
                        [_imp(account="etrade:9876")], [])
    assert len(rows) == 1
    r = rows[0]
    assert r["amount"] == 0.0 and r["in_kind"] is True and r["counts"] is False and r["class"] == "transfer_in"


def test_in_kind_with_an_amount_still_zero_cash():
    rows = build_ledger("vanguard:1111", [_b(action="Transfer (incoming)", symbol="EXMK", quantity=5.0, amount=1000.0)],
                        [_imp(account="vanguard:1111")], [])
    assert rows[0]["amount"] == 0.0 and rows[0]["in_kind"]


def test_cash_transfers_and_rollover_have_direction_from_sign():
    rows = build_ledger("vanguard:1111", [
        _b(run_date="2026-02-01", action="Rollover (incoming)", symbol="CASH", amount=5000.0),
        _b(run_date="2026-02-02", action="Transfer (Outgoing)", amount=-200.0),
    ], [_imp(account="vanguard:1111")], [])
    assert [(r["class"], r["amount"], r["counts"]) for r in rows] == [("transfer_in", 5000.0, True), ("transfer_out", -200.0, True)]


def test_overlap_broker_file_wins_over_monarch_no_double_count():
    broker = [_b(run_date="2026-06-01", action="Contribution", description="EMPLOYER", amount=500.0)]
    monarch = [_m("2026-06-01", 500, "401k Contribution"),      # inside coverage: dropped
               _m("2026-02-01", 400, "401k Contribution"),      # before the file: kept
               _m("2026-09-30", 25, "401K Match")]              # after: kept
    rows = build_ledger("a", broker, [_imp(account="a", date_from="2026-05-01", date_to="2026-07-01")], monarch)
    assert sum(r["amount"] for r in _by_class(rows, "contribution")) == 925.0
    assert [r["source"] for r in rows] == ["monarch", "broker", "monarch"]


def test_unapplied_import_does_not_cover_or_contribute():
    broker = [_b(import_id=2, run_date="2026-06-01", action="Contribution", amount=500.0)]
    rows = build_ledger("a", broker, [_imp(import_id=2, status="reverted", date_from="2026-05-01", date_to="2026-07-01")],
                        [_m("2026-06-01", 500, "401k Contribution")])
    assert [r["source"] for r in rows] == ["monarch"]


def test_monarch_categories():
    rows = build_ledger("a", [], [], [
        _m("2026-01-01", 100, "Transfer"), _m("2026-01-02", -50, "Transfer"), _m("2026-01-03", 1000, "401k Contribution"),
        _m("2026-01-04", 200, "401K Match"), _m("2026-01-05", -9, "Financial Fees"), _m("2026-01-06", 3, "Other Income"),
        _m("2026-01-07", -7, "Uncategorized"), _m("2026-01-08", 1, "Groceries")])
    assert [r["class"] for r in rows] == ["transfer_in", "transfer_out", "contribution", "contribution", "fee", "income", "transfer_out"]
    assert rows[-1]["needs_review"] is True


def test_rows_sorted_by_date():
    rows = build_ledger("a", [_b(run_date="2026-05-01", action="Contribution", amount=1.0)], [_imp(account="a", date_from="2026-05-01", date_to="2026-05-01")], [_m("2026-04-01", 2, "Other Income")])
    assert [r["date"] for r in rows] == ["2026-04-01", "2026-05-01"]


def test_etrade_parser_keeps_the_reference_id_and_the_ledger_carries_it():
    rows = ["02/09/2026,02/09/2026,02/09/2026,Online Transfer,ACH DEPOSIT  REFID:123456;,--,--,,,500.0,0.0,--,--",
            "07/03/2025,07/03/2025,07/03/2025,Distribution,TRANSFER TO XXXXX6921  REFID:777,--,--,,,-40.0,0.0,--,--",
            "06/01/2026,06/01/2026,--,Contribution,TY 2026 EMPLOYER CURR YR,--,--,--,--,500.0,0.0,--,--"]
    parsed = etrade.parse(etrade_csv(rows=rows))
    assert sorted(r.get("ref_id") or "" for r in parsed.rows) == ["", "123456", "777"]
    led = build_ledger("etrade:9876", _rows(parsed, account="etrade:9876"), [_imp(account="etrade:9876")], [])
    assert sorted(r["ref_id"] for r in led) == ["", "123456", "777"]
    assert {r["ref"] for r in led if r["ref_id"]} == {"123456", "777"}
    assert "XXXXX6921" in [r for r in led if r["ref_id"] == "777"][0]["description"]


def test_ledger_ref_id_falls_back_to_the_stored_description():
    # the store keeps only ROW_FIELDS, so a stored row has the REFID text in its description and no ref_id key
    rows = build_ledger("a", [_b(action="Online Transfer", description="TRANSFER FROM XXXXX7314  REFID:142071675906", amount=9.0)],
                        [_imp(account="a")], [])
    assert rows[0]["ref_id"] == "142071675906"


def test_return_of_excess_contribution_is_its_own_class():
    rows = build_ledger("a", [_b(action="RETURN EXCESS CONTR HSA CHK PD 000000001 (Cash)", amount=-100.0)], [_imp(account="a")], [])
    assert rows[0]["class"] == "excess_return" and rows[0]["counts"] is True and rows[0]["amount"] == -100.0


def test_rollover_rows_are_marked_and_in_kind_rows_keep_symbol_and_quantity():
    rows = build_ledger("a", [_b(run_date="2026-02-01", action="Rollover (incoming)", symbol="CASH", amount=5000.0),
                              _b(run_date="2026-02-02", action="Transfer", symbol="TOTL", quantity=-10.0, amount=None)],
                        [_imp(account="a")], [])
    assert rows[0]["rollover"] is True and rows[1]["rollover"] is False
    assert rows[1]["quantity"] == -10.0 and rows[1]["in_kind"] is True
