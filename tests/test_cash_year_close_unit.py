"""Cash-year close (year-end transition Phase 1): manual close of a calendar year's cash reconciliation, frozen in plan_meta."""
import json
from datetime import date

import pytest

from src import active_plan, cash_view, cash_year_close as cyc
from tests.test_cash_view_unit import ACCT, make


class FakeMeta:
    def __init__(self):
        self.d = {}

    def get_meta(self, key, default=None):
        return self.d.get(key, default)

    def set_meta(self, key, value):
        self.d[key] = value

    def delete_meta(self, key):
        self.d.pop(key, None)


def row(d, typ, amt, status="external_withdrawal", pid=None, partner=None):
    return {"date": d, "class": typ, "amount": amt, "counts": True, "in_kind": False, "pair_status": status,
            "pair_id": pid, "partner_account": partner}


def snap(first_year, built="2026-12-20T09:00:00Z", pid="plan_a", wd=1000.0):
    return {"created_at": built, "plan_id": pid, "result": {"projection_rows": [
        {"year": first_year, "_account_withdrawals": {"A_IRA": wd}}, {"year": first_year + 1, "_account_withdrawals": {"A_IRA": 1.0}}]}}


@pytest.fixture
def jan_2027(monkeypatch):
    monkeypatch.setattr(cyc, "today", lambda: date(2027, 1, 8))
    monkeypatch.setattr(cash_view, "today", lambda: date(2027, 1, 8))


LED = {"A_IRA": [row("2026-03-01", "distribution", -300.0)]}


def test_close_blocked_before_the_year_has_ended(monkeypatch):
    monkeypatch.setattr(cyc, "today", lambda: date(2026, 12, 31))
    st = cyc.close_status(FakeMeta(), 2026, ledgers=LED)
    assert st["allowed"] is False and any("ended" in b for b in st["blockers"])
    with pytest.raises(cyc.CloseError):
        cyc.close_year(FakeMeta(), 2026, ledgers=LED)


def test_close_blocked_by_an_unmatched_row_of_that_year(jan_2027):
    led = {"A_IRA": [row("2026-03-01", "transfer_out", -50.0, status="unmatched")]}
    st = cyc.close_status(FakeMeta(), 2026, ledgers=led)
    assert st["allowed"] is False and any("unmatched" in b for b in st["blockers"])
    # an unmatched row of another year does not block
    assert cyc.close_status(FakeMeta(), 2026, ledgers={"A_IRA": [row("2025-03-01", "transfer_out", -50.0, status="unmatched")]})["allowed"]


def test_straddling_rows_are_listed_and_must_be_seen(jan_2027):
    led = {"A_IRA": [row("2026-12-30", "transfer_out", -100.0, "internal", "p1", "B_Roth")],
           "B_Roth": [row("2027-01-02", "transfer_in", 100.0, "internal", "p1", "A_IRA")]}
    meta = FakeMeta()
    st = cyc.close_status(meta, 2026, ledgers=led)
    assert st["allowed"] and len(st["straddles"]) == 1
    with pytest.raises(cyc.CloseError, match="straddl"):
        cyc.close_year(meta, 2026, ledgers=led)
    cyc.close_year(meta, 2026, ledgers=led, straddles_seen=True)
    assert cyc.is_year_closed(meta, 2026)


def test_close_writes_reported_totals_plan_figure_and_digest(jan_2027):
    meta = FakeMeta()
    rec = cyc.close_year(meta, 2026, "final", ledgers=LED, snapshots=[snap(2026)])
    stored = json.loads(meta.d["cash.year_close.2026"])
    assert stored == rec and rec["year"] == 2026 and rec["note"] == "final" and rec["closed_at"].startswith("2027-01-08")
    assert rec["reported"]["A_IRA"] == {"external_withdrawal": 300.0, "internal": 0.0, "unmatched": 0.0, "excess_return": 0.0}
    assert rec["plan"]["source"] == "snapshot" and rec["plan"]["built_at"] == "2026-12-20T09:00:00Z"
    assert rec["plan"]["by_account"] == {"A_IRA": 1000.0} and len(rec["ledger_digest"]) == 64


def test_snapshot_chosen_only_when_its_first_row_year_matches(jan_2027):
    new_year_run = snap(2027, built="2027-01-05T08:00:00Z", wd=5.0)           # newest, but projects 2027
    december = snap(2026)
    assert cyc.pick_snapshot([new_year_run, december], 2026) is december
    rec = cyc.close_year(FakeMeta(), 2026, ledgers=LED, snapshots=[new_year_run])
    assert rec["plan"] == {"source": "none", "built_at": None, "by_account": {}}


def test_is_year_closed_true_only_for_a_closed_year(jan_2027):
    meta = FakeMeta()
    cyc.close_year(meta, 2026, ledgers=LED)
    assert cyc.is_year_closed(meta, 2026) is True and cyc.is_year_closed(meta, 2025) is False


def test_cannot_close_twice_and_reopen_removes_the_record(jan_2027):
    meta = FakeMeta()
    cyc.close_year(meta, 2026, ledgers=LED)
    with pytest.raises(cyc.CloseError, match="already"):
        cyc.close_year(meta, 2026, ledgers=LED)
    cyc.reopen_year(meta, 2026)
    assert "cash.year_close.2026" not in meta.d and not cyc.is_year_closed(meta, 2026)
    with pytest.raises(cyc.CloseError):
        cyc.reopen_year(meta, 2026)


def test_drift_after_close_is_detected_with_old_and_new_totals(jan_2027):
    meta = FakeMeta()
    cyc.close_year(meta, 2026, ledgers=LED, snapshots=[snap(2026)])
    same = cyc.close_summary(meta, 2026, LED)
    assert same["changed"] is False and same["difference"] == [{"account": "A_IRA", "reported": 300.0, "plan": 1000.0, "difference": 700.0}]
    late = {"A_IRA": LED["A_IRA"] + [row("2026-12-29", "distribution", -40.0)]}      # a late broker file
    drift = cyc.close_summary(meta, 2026, late)
    assert drift["changed"] is True and (drift["closed_total"], drift["current_total"]) == (300.0, 340.0)


def test_digest_ignores_pair_id_numbering_and_other_years(jan_2027):
    a = {"A_IRA": [row("2026-03-01", "transfer_out", -9.0, "internal", "pair-1", "B")]}
    b = {"A_IRA": [row("2026-03-01", "transfer_out", -9.0, "internal", "pair-7", "B"), row("2025-01-01", "distribution", -1.0)]}
    assert cyc.ledger_digest(a, 2026) == cyc.ledger_digest(b, 2026)


def test_build_view_uses_frozen_plan_figure_for_a_closed_year_and_lists_closes(tmp_path, jan_2027):
    ws = make(tmp_path)
    with active_plan.workspace_store(ws, write=True) as store:
        v = cash_view.build_view(store, year=2026, snapshots=[{"created_at": "x", "plan_id": "p", "result": {"projection_rows": [
            {"year": 2026, "_account_withdrawals": {ACCT: 123.0}}]}}])
        assert v["comparison"]["closed"] is False
        assert [c["year"] for c in v["closes"]] == [2026] and v["closes"][0]["closed"] is False
        cyc.close_year(store, 2026, snapshots=[{"created_at": "x", "plan_id": "p", "result": {"projection_rows": [
            {"year": 2026, "_account_withdrawals": {ACCT: 123.0}}]}}], straddles_seen=True)
        later = cash_view.build_view(store, year=2027, snapshots=[snap(2027)])       # January: the live run projects 2027
        assert later["closes"][0]["closed"] is True and later["closes"][0]["plan_source"] == "snapshot"
        again = cash_view.build_view(store, year=2026, snapshots=[snap(2027)])
        assert again["comparison"]["closed"] is True and again["comparison"]["accounts"][0]["plan"] == 123.0
