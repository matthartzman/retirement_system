"""Year-end page (year-end transition Phase 2): ordered checklist whose state is derived from the data wherever possible."""
import json
from datetime import date

import pytest

from src import cash_view, cash_year_close as cyc, year_end


class Meta:
    def __init__(self):
        self.d = {}

    def get_meta(self, key, default=None):
        return self.d.get(key, default)

    def set_meta(self, key, value):
        self.d[key] = value

    def delete_meta(self, key):
        self.d.pop(key, None)


def row(d, typ, amt, status="external_withdrawal"):
    return {"date": d, "class": typ, "amount": amt, "counts": True, "in_kind": False, "pair_status": status, "pair_id": None, "partner_account": None}


def snap(first_year):
    return {"created_at": "2026-12-20T09:00:00Z", "plan_id": "p", "result": {"projection_rows": [{"year": first_year, "_account_withdrawals": {"A_IRA": 1.0}}]}}


@pytest.fixture
def jan_2027(monkeypatch):
    for mod in (year_end, cyc, cash_view):
        monkeypatch.setattr(mod, "today", lambda: date(2027, 1, 8))


def steps(**kw):
    kw.setdefault("store", Meta())
    kw.setdefault("ledgers", {"A_IRA": [row("2026-03-01", "distribution", -300.0)]})
    kw.setdefault("snapshots", [])
    kw.setdefault("imports", [{"account": "A_IRA", "date_to": "2027-01-05"}])
    kw.setdefault("setup_rows", [])
    kw.setdefault("cash_differences", [])
    kw.setdefault("reference_stale", 0)
    out = year_end.build(2026, **kw)
    return out, {s["id"]: s for s in out["steps"]}


TAX_STEPS = ["clear_sales_queue", "resolve_log_drift", "run_wash_check", "tie_1099b", "confirm_carryforward"]
CLEAN = {"queue_waiting": 0, "drift_accounts": 0, "wash_state": "clean", "untied_1099b": 0, "carryforward_saved": True}


def test_steps_come_in_the_designed_order_with_links(jan_2027):
    # Task 14 (2026-11-03 sales-ledger redesign): the five tax-filing steps sit after final_broker_files.
    out, by = steps()
    assert [s["id"] for s in out["steps"]] == ["capture_plan_year", "final_broker_files", *TAX_STEPS, "resolve_cash_rows",
                                              "confirm_year_end_cash", "close_cash_year", "start_tracking", "personal_numbers",
                                              "reference_data"]
    assert all(s["link"] and s["title"] and s["state"] in ("done", "open", "na") for s in out["steps"])
    assert out["year"] == 2026


def test_tax_filing_steps_are_na_without_data_and_leave_the_old_steps_unchanged(jan_2027):
    out, by = steps()
    assert [by[k]["state"] for k in TAX_STEPS] == ["na"] * 5
    old = [s for s in out["steps"] if s["id"] not in TAX_STEPS]
    assert all(set(s) == {"id", "title", "link", "state", "detail"} for s in old)
    with_data = [s for s in steps(tax_filing=CLEAN)[0]["steps"] if s["id"] not in TAX_STEPS]
    assert with_data == old


def test_tax_filing_steps_titles_links_and_deep_link_hashes(jan_2027):
    by = steps(tax_filing=CLEAN)[1]
    assert [by[k]["title"] for k in TAX_STEPS] == [
        "Clear the sales waiting for lots", "Resolve log drift", "Run the wash-sale check",
        "Apply and tie the broker 1099-B", "Confirm the capital-loss carryforward"]
    assert all(by[k]["link"] == "sales_ledger" for k in TAX_STEPS)
    assert [by[k]["hash"] for k in TAX_STEPS] == [
        "#sales_ledger?tab=fix&sec=queue", "#sales_ledger?tab=fix&sec=health", "#sales_ledger?tab=fix&sec=wash",
        "#sales_ledger?tab=tax&sec=b1099", "#sales_ledger?tab=tax&sec=cf"]
    assert [by[k]["state"] for k in TAX_STEPS] == ["done"] * 5


def test_clear_sales_queue_open_while_sales_wait_for_lots(jan_2027):
    s = steps(tax_filing={**CLEAN, "queue_waiting": 3})[1]["clear_sales_queue"]
    assert s["state"] == "open" and "3" in s["detail"]


def test_resolve_log_drift_open_while_accounts_drift(jan_2027):
    s = steps(tax_filing={**CLEAN, "drift_accounts": 2})[1]["resolve_log_drift"]
    assert s["state"] == "open" and "2" in s["detail"]


@pytest.mark.parametrize("state,words", [("flagged", "flagged"), ("stale", "since the ledger changed"), ("never", "never run")])
def test_run_wash_check_open_unless_clean(jan_2027, state, words):
    s = steps(tax_filing={**CLEAN, "wash_state": state})[1]["run_wash_check"]
    assert s["state"] == "open" and words in s["detail"] and "This app's accounts only." in s["detail"]
    assert "This app's accounts only." in steps(tax_filing=CLEAN)[1]["run_wash_check"]["detail"]


def test_tie_1099b_open_while_accounts_are_untied(jan_2027):
    s = steps(tax_filing={**CLEAN, "untied_1099b": 1})[1]["tie_1099b"]
    assert s["state"] == "open" and "1" in s["detail"]


def test_tie_1099b_reports_whether_the_untied_count_is_known(jan_2027):
    """The page shows 'Undo confirmation' only while the count is unknown (a known count wins over the stored attestation)."""
    assert steps(tax_filing=CLEAN)[1]["tie_1099b"]["count_known"] is True
    assert steps(tax_filing={**CLEAN, "untied_1099b": None})[1]["tie_1099b"]["count_known"] is False


@pytest.mark.parametrize("key,sid,words", [
    ("queue_waiting", "clear_sales_queue", "Could not check"), ("drift_accounts", "resolve_log_drift", "Could not check"),
    ("untied_1099b", "tie_1099b", "Not verified automatically")])
def test_an_unknown_count_is_open_never_done(jan_2027, key, sid, words):
    s = steps(tax_filing={**CLEAN, key: None})[1][sid]
    assert s["state"] == "open" and s["detail"].startswith(words)
    assert steps(tax_filing={**CLEAN, key: 0})[1][sid]["state"] == "done"


def test_drift_is_not_applicable_when_the_log_is_not_in_use(jan_2027):
    s = steps(tax_filing={**CLEAN, "log_in_use": False})[1]["resolve_log_drift"]
    assert (s["state"], s["detail"]) == ("na", "The transaction log is not in use.")
    assert steps(tax_filing={**CLEAN, "log_in_use": True})[1]["resolve_log_drift"]["state"] == "done"


def test_confirm_carryforward_done_once_saved(jan_2027):
    assert steps(tax_filing={**CLEAN, "carryforward_saved": False})[1]["confirm_carryforward"]["state"] == "open"


def test_capture_plan_year_is_done_only_when_a_snapshot_projected_that_year(jan_2027):
    assert steps(snapshots=[snap(2026)])[1]["capture_plan_year"]["state"] == "done"
    s = steps(snapshots=[snap(2027)])[1]["capture_plan_year"]
    assert s["state"] == "open" and "no saved plan run" in s["detail"].lower()


def test_broker_files_flag_accounts_without_a_file_after_year_end(jan_2027):
    s = steps(imports=[{"account": "A_IRA", "date_to": "2026-12-31"}, {"account": "B_Roth", "date_to": "2027-01-03"}])[1]["final_broker_files"]
    assert s["state"] == "open" and "A_IRA" in s["detail"] and "B_Roth" not in s["detail"]
    assert steps(imports=[])[1]["final_broker_files"]["state"] == "na"
    assert steps()[1]["final_broker_files"]["state"] == "done"


def test_resolve_cash_rows_open_while_unmatched_rows_exist(jan_2027):
    s = steps(ledgers={"A_IRA": [row("2026-03-01", "transfer_out", -5.0, "unmatched")]})[1]["resolve_cash_rows"]
    assert s["state"] == "open" and "1 unmatched" in s["detail"]
    assert steps()[1]["resolve_cash_rows"]["state"] == "done"


def test_year_end_cash_open_until_every_difference_is_zero(jan_2027):
    assert steps(cash_differences=[("A_IRA", 0.0), ("B_Roth", None)])[1]["confirm_year_end_cash"]["state"] == "done"
    s = steps(cash_differences=[("A_IRA", 12.5)])[1]["confirm_year_end_cash"]
    assert s["state"] == "open" and "A_IRA" in s["detail"]
    assert steps(cash_differences=[])[1]["confirm_year_end_cash"]["state"] == "na"


def test_close_step_follows_the_close_itself(jan_2027):
    meta = Meta()
    assert steps(store=meta)[1]["close_cash_year"]["state"] == "open"
    cyc.close_year(meta, 2026, ledgers={"A_IRA": [row("2026-03-01", "distribution", -300.0)]})
    assert steps(store=meta)[1]["close_cash_year"]["state"] == "done"


def test_start_tracking_done_once_every_growth_account_is_dated_at_or_after_the_year(jan_2027):
    old = [{"Account": "Brokerage", "Role": "Investment", "Prior Year End Date": "2025-12-31"}, {"Account": "Checking", "Role": "Cash", "Prior Year End Date": ""}]
    s = steps(setup_rows=old)[1]["start_tracking"]
    assert s["state"] == "open" and "Brokerage" in s["detail"]
    assert steps(setup_rows=[{**old[0], "Prior Year End Date": "2026-12-31"}])[1]["start_tracking"]["state"] == "done"
    assert steps(setup_rows=[])[1]["start_tracking"]["state"] == "na"


def test_personal_numbers_is_the_only_stored_confirmation(jan_2027):
    meta = Meta()
    assert steps(store=meta)[1]["personal_numbers"]["state"] == "open"
    year_end.set_confirmation(meta, 2026, "personal_numbers", True)
    assert json.loads(meta.d["year_end.2026.personal_numbers"])["confirmed"] is True
    assert steps(store=meta)[1]["personal_numbers"]["state"] == "done"
    year_end.set_confirmation(meta, 2026, "personal_numbers", False)
    assert "year_end.2026.personal_numbers" not in meta.d
    with pytest.raises(ValueError):
        year_end.set_confirmation(meta, 2026, "close_cash_year", True)        # derived steps cannot be ticked


def test_reference_data_is_informational(jan_2027):
    assert steps(reference_stale=3)[1]["reference_data"]["state"] == "open"
    assert steps()[1]["reference_data"]["state"] == "done"


def test_reference_data_warns_when_the_new_plan_year_has_no_dated_rows(jan_2027):
    """FIN-011: closing 2026 with no dated 2027 federal rows must say so, not carry 2026 forward silently."""
    _, by = steps(reference_missing=["federal tax brackets", "the standard deduction"])
    step = by["reference_data"]
    assert step["state"] == "open"
    assert "No dated 2027 reference rows for: federal tax brackets, the standard deduction" in step["detail"]
    assert "carried forward" in step["detail"]


def test_reference_rows_missing_reads_the_shipped_dataset():
    assert year_end.reference_rows_missing(2026) == []          # dated 2026 rows ship
    missing = year_end.reference_rows_missing(2027)             # until the IRS and CMS 2027 figures are added
    assert "federal tax brackets" in missing or not missing     # becomes [] once W2-10's rows ship


def test_default_year_is_the_year_in_progress_from_july_and_the_previous_year_before(monkeypatch):
    monkeypatch.setattr(year_end, "today", lambda: date(2026, 12, 20))
    assert year_end.default_year() == 2026
    monkeypatch.setattr(year_end, "today", lambda: date(2027, 1, 20))
    assert year_end.default_year() == 2026
    monkeypatch.setattr(year_end, "today", lambda: date(2027, 3, 1))
    assert year_end.default_year() == 2026


def test_banner_window_is_mid_december_through_january(monkeypatch):
    for d, expect in ((date(2026, 12, 14), False), (date(2026, 12, 15), True), (date(2027, 1, 31), True), (date(2027, 2, 1), False)):
        monkeypatch.setattr(year_end, "today", lambda d=d: d)
        assert year_end.in_season() is expect


def test_tie_1099b_is_a_stored_confirmation(jan_2027):
    # Task 15b: no per-account tie data exists yet (untied_1099b unknown), so the user attests the tie.
    meta = Meta()
    unknown = {**CLEAN, "untied_1099b": None}
    s = steps(store=meta, tax_filing=unknown)[1]["tie_1099b"]
    assert s["state"] == "open" and s["detail"].startswith("Not verified automatically")
    year_end.set_confirmation(meta, 2026, "tie_1099b", True)
    assert json.loads(meta.d["year_end.2026.tie_1099b"])["confirmed"] is True
    s = steps(store=meta, tax_filing=unknown)[1]["tie_1099b"]
    assert (s["state"], s["detail"], s["hash"]) == ("done", "You confirmed each 1099-B is tied. Re-check after any new import.", "#sales_ledger?tab=tax&sec=b1099")
    year_end.set_confirmation(meta, 2026, "tie_1099b", False)
    assert "year_end.2026.tie_1099b" not in meta.d
    assert steps(store=meta, tax_filing=unknown)[1]["tie_1099b"]["state"] == "open"
    assert year_end.CONFIRMABLE == ("personal_numbers", "tie_1099b")


def test_a_known_untied_count_beats_the_tie_confirmation(jan_2027):
    meta = Meta()
    year_end.set_confirmation(meta, 2026, "tie_1099b", True)
    s = steps(store=meta, tax_filing={**CLEAN, "untied_1099b": 2})[1]["tie_1099b"]
    assert s["state"] == "open" and "2 account(s)" in s["detail"]
    assert steps(store=meta)[1]["tie_1099b"]["state"] == "na"     # no tax-filing data: still not applicable
