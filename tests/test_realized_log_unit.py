"""Sales ledger 4.4: year-to-date realized figures in the daily log, and "no data" for entries without them."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date

from financial_trends_reporter import percent_view, realized_log
from financial_trends_reporter.trends_log import append_or_replace_entry, read_history, realized_ytd_of
from financial_trends_reporter.trends_metrics import compute_snapshot
from tests.test_realized_view_unit import SALES
from tests.test_trends_daily_flows_unit import TODAY as FLOWS_TODAY, _workspace

TODAY = date(2026, 10, 27)
CANDIDATES = [
    {"candidate_id": 1, "source": "monarch", "sale_date": "2026-09-30", "account": "Member_1_Trust", "symbol": "ITOT", "shares": 10.0, "price": None, "amount": 1300.0},
    {"candidate_id": 2, "source": "holdings_diff", "sale_date": "2026-09-01", "account": "Member_1_Trust", "symbol": "ITOT", "shares": 1.0, "price": None, "amount": None},
    {"candidate_id": 3, "source": "monarch", "sale_date": "2025-11-01", "account": "Member_1_Trust", "symbol": "ITOT", "shares": 1.0, "price": None, "amount": -100.0},
]


def test_block_is_taxable_confirmed_sales_this_year():
    b = realized_log.from_rows(SALES, CANDIDATES, TODAY)
    # Taxable, confirmed, 2026: ITOT +1500 (long) and AVUV -600 (short, wash-flagged). The IRA sale, last year's sale
    # and the voided sale are out.
    assert (b["year"], b["st_gain"], b["lt_gain"], b["net"], b["wash_flagged"]) == (2026, -600.0, 1500.0, 900.0, -600.0)
    assert b["unconfirmed"] == {"count": 2, "amount": 1300.0}      # last year's candidate is out; a count needs no amount
    assert b["tax_estimate"] is None                               # the realized-tax line is step 4.5


def test_an_empty_ledger_is_real_zeros_and_the_estimate_is_never_logged():
    b = realized_log.from_rows([], [], TODAY)
    assert (b["net"], b["unconfirmed"]) == (0.0, {"count": 0, "amount": 0.0})
    assert set(b) == {"year", "st_gain", "lt_gain", "net", "tax_estimate", "wash_flagged", "unconfirmed"}   # no estimate block


@contextmanager
def _store(sales, candidates):
    class Sales:
        list_sales = staticmethod(lambda: sales)
        list_candidates = staticmethod(lambda state=None: candidates)

    yield type("S", (), {"sales": Sales()})()


def test_reads_the_plan_and_an_unreadable_one_is_no_data(tmp_path, monkeypatch):
    from src import active_plan

    monkeypatch.setattr(active_plan, "workspace_store", lambda root, **k: _store(SALES, CANDIDATES))
    assert realized_log.realized_ytd(tmp_path, TODAY)["net"] == 900.0

    def broken(root, **k):
        raise OSError("locked")

    monkeypatch.setattr(active_plan, "workspace_store", broken)
    assert realized_log.realized_ytd(tmp_path, TODAY) is None


def test_snapshot_carries_the_block_or_leaves_the_key_out(tmp_path, monkeypatch):
    base = _workspace(tmp_path)
    monkeypatch.setattr(realized_log, "realized_ytd", lambda b, t: None)
    assert "realized_ytd" not in compute_snapshot(base, today=FLOWS_TODAY)
    block = {"year": 2026, "net": 1.0}
    monkeypatch.setattr(realized_log, "realized_ytd", lambda b, t: block)
    assert compute_snapshot(base, today=FLOWS_TODAY)["realized_ytd"] == block


def test_old_entries_read_as_no_data_not_zero(tmp_path):
    log = tmp_path / "log.jsonl"
    append_or_replace_entry(log, {"as_of_date": "2026-01-05", "net_worth": {"total": 1.0}})
    append_or_replace_entry(log, {"as_of_date": "2026-10-27", "realized_ytd": realized_log.from_rows(SALES, CANDIDATES, TODAY)})
    old, new = read_history(log)
    assert realized_ytd_of(old) is None and realized_ytd_of(None) is None and realized_ytd_of({"realized_ytd": "x"}) is None
    assert realized_ytd_of(new)["net"] == 900.0


def test_percent_view_scales_the_dollars_and_leaves_the_count():
    entry = {"as_of_date": "2026-10-27", "realized_ytd": realized_log.from_rows(SALES, CANDIDATES, TODAY)}
    out = percent_view.scale_payload(percent_view.strip_detail("/api/history", [entry]), 100000.0)[0]["realized_ytd"]
    assert out["unconfirmed"]["count"] == 2 and out["year"] == 2026
    assert out["net"] == 900.0 / 100000.0 and out["unconfirmed"]["amount"] == 1300.0 / 100000.0
    assert percent_view.find_money_leaks(out) == []
