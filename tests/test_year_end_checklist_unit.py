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


def test_steps_come_in_the_designed_order_with_links(jan_2027):
    out, by = steps()
    assert [s["id"] for s in out["steps"]] == ["capture_plan_year", "final_broker_files", "resolve_cash_rows", "confirm_year_end_cash",
                                              "close_cash_year", "start_tracking", "personal_numbers", "reference_data"]
    assert all(s["link"] and s["title"] and s["state"] in ("done", "open", "na") for s in out["steps"])
    assert out["year"] == 2026


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
