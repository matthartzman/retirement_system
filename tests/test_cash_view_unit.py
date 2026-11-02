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


# ---- plan vs reported withdrawals (report only; owner decisions 2026-11-02) ----
def _snap(rows, built="2026-11-01T10:00:00Z"):
    return {"created_at": built, "result": {"projection_rows": rows}}


def _row(d, typ, amt, pid=None, partner=None, status="external_withdrawal"):
    return {"date": d, "class": typ, "amount": amt, "counts": True, "in_kind": False, "pair_status": status,
            "pair_id": pid, "partner_account": partner}


def test_plan_year_withdrawals_reads_only_the_current_year_row():
    snap = _snap([{"year": 2026, "_account_withdrawals": {"A_IRA": 500.0, "B_Roth": 0}}, {"year": 2027, "_account_withdrawals": {"A_IRA": 1.0}}])
    assert cash_view.plan_year_withdrawals(snap, 2026) == {"A_IRA": 500.0, "B_Roth": 0.0}
    assert cash_view.plan_year_withdrawals(snap, 2027) is None          # only the first (current) year is compared          # engine has no past-year rows
    assert cash_view.plan_year_withdrawals(None, 2026) is None


def test_year_closed_seam_is_false_for_every_year(tmp_path):
    assert cash_view.is_year_closed(object(), 2025) is False


def test_comparison_is_pace_without_difference_while_year_is_open():
    c = cash_view.comparison({"A_IRA": [_row("2026-03-01", "distribution", -300.0)]}, 2026,
                             _snap([{"year": 2026, "_account_withdrawals": {"A_IRA": 1000.0, "Zed_IRA": 5.0}}]), closed=False)
    a = c["accounts"][0]
    assert (a["account"], a["reported_ytd"], a["plan"], a["difference"]) == ("A_IRA", 300.0, 1000.0, None)
    assert c["closed"] is False and c["snapshot"]["built_at"] == "2026-11-01T10:00:00Z" and "stale" in c["note"].lower()
    assert c["plan_unmapped"] == {"Zed_IRA": 5.0}


def test_comparison_difference_only_for_a_closed_year_and_no_snapshot_means_no_plan():
    led = {"A_IRA": [_row("2026-03-01", "distribution", -300.0)]}
    snap = _snap([{"year": 2026, "_account_withdrawals": {"a_ira": 1000.0}}])           # id match ignores case
    assert cash_view.comparison(led, 2026, snap, closed=True)["accounts"][0]["difference"] == 700.0
    none = cash_view.comparison(led, 2026, None, closed=False)
    assert none["snapshot"] is None and none["accounts"][0]["plan"] is None and none["accounts"][0]["difference"] is None


def test_past_years_are_report_only_by_status():
    led = {"A_IRA": [_row("2025-03-01", "distribution", -40.0), _row("2024-01-01", "transfer_out", -7.0, status="unmatched"),
                     _row("2026-03-01", "distribution", -300.0)]}
    py = cash_view.past_years(led, 2026)
    assert [(p["account"], p["year"], p["external_withdrawal"], p["unmatched"]) for p in py] == [("A_IRA", 2024, 0.0, 7.0), ("A_IRA", 2025, 40.0, 0.0)]


def test_year_end_straddle_is_flagged_not_reallocated():
    led = {"A_IRA": [_row("2026-12-30", "transfer_out", -100.0, "p1", "B_Roth", "internal"),
                     _row("2026-06-01", "transfer_out", -9.0, "p2", "B_Roth", "internal")],
           "B_Roth": [_row("2027-01-02", "transfer_in", 100.0, "p1", "A_IRA", "internal"),
                      _row("2026-06-02", "transfer_in", 9.0, "p2", "A_IRA", "internal")]}
    s = cash_view.year_straddles(led)
    assert len(s) == 1 and s[0]["out_account"] == "A_IRA" and s[0]["out_date"] == "2026-12-30" and s[0]["in_date"] == "2027-01-02"
    # the outflow still counts in its own year
    assert cash_view.withdrawals_by_status(led["A_IRA"], 2026)["internal"] == 109.0


def test_build_view_carries_comparison_past_years_and_straddles(tmp_path):
    ws = make(tmp_path)
    with active_plan.workspace_store(ws) as store:
        v = cash_view.build_view(store, year=2026, snapshot=_snap([{"year": 2026, "_account_withdrawals": {ACCT: 123.0}}]))
    assert v["comparison"]["accounts"][0]["plan"] == 123.0 and v["comparison"]["accounts"][0]["difference"] is None
    assert isinstance(v["past_years"], list) and isinstance(v["straddles"], list)


def test_latest_result_snapshot_reads_newest_and_never_runs_the_engine(tmp_path):
    from src import local_store
    db = tmp_path / "app.db"
    assert local_store.latest_result_snapshot(db) is None
    local_store.save_result_snapshot({"projection_rows": [{"year": 2026}], "n": 1}, db_path=db)
    got = local_store.latest_result_snapshot(db)
    assert got["result"]["n"] == 1 and got["created_at"]


def test_snapshot_whose_first_row_is_another_year_gives_no_plan_figure():
    old = _snap([{"year": 2025, "_account_withdrawals": {"A_IRA": 9.0}}, {"year": 2026, "_account_withdrawals": {"A_IRA": 500.0}}])
    assert cash_view.plan_year_withdrawals(old, 2026) is None
    c = cash_view.comparison({"A_IRA": []}, 2026, old, closed=False)
    assert c["accounts"][0]["plan"] is None and "No plan figure for 2026" in c["note"]
    assert "identifier" in cash_view.comparison({"A_IRA": []}, 2026, _snap([{"year": 2026, "_account_withdrawals": {}}]), closed=False)["note"]
