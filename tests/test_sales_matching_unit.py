"""Monarch Sell rows -> sale candidates (ledger plan 5.2): extractor, parser, idempotent loader, suggestions."""
import copy
from datetime import date

import pytest

from src import sales_matching as sm
from src import ytd_tracking
from src.stores import PlanStore

START = date(2026, 1, 1)


def row(mid, day, account, amount, statement="", merchant="", category="Sell"):
    return {"Date": day, "Merchant": merchant, "Category": category, "Account": account, "Original Statement": statement,
            "Notes": "", "Amount": amount, "Tags": "", "Owner": "", "Monarch Id": mid}


FIXTURE = [
    row("m1", "2026-03-10", "Brokerage", "2,500.00", "Sold 10 VTI @ 250.00"),                    # parseable
    row("m2", "2026-03-11", "Brokerage", "1000", "", merchant="Sold 12.5 BRK.B @ $80"),            # parseable via Merchant, odd ticker
    row("m3", "2026-04-01", "Roth IRA", "700.00", "SELL TRANSACTION"),                               # bare
    row("m4", "2026-04-02", "Brokerage", "300", "Sold 3 vanguard total @ 100"),                     # a name, not a ticker -> bare
    row("m5", "2026-05-01", "Brokerage", "900", "Sold 9 FXAIX @ 100"),                               # parseable
    row("m5", "2026-05-01", "Brokerage", "900", "Sold 9 FXAIX @ 100"),                               # duplicate id in the same file
    row("m6", "2025-12-30", "Brokerage", "500", "Sold 5 VTI @ 100"),                                 # before the ledger start
    row("m7", "2026-06-01", "Brokerage", "50", "Coffee", category="Dining"),                        # not a sell
    row("", "2026-06-02", "Brokerage", "400", "Sold 4 VTI @ 100"),                                   # no Monarch Id
    row("m8", "not-a-date", "Brokerage", "400", "Sold 4 VTI @ 100"),                                 # unreadable date
]


@pytest.mark.parametrize("text,expected", [
    ("Sold 10 VTI @ 250.00", ("VTI", 10.0, 250.0)),
    ("sold 12.5 brk.b @ 80", None),
    ("Sold 12.5 BRK.B @ $1,080.50", ("BRK.B", 12.5, 1080.5)),
    ("Sold 3 BRK-B @ 5", ("BRK-B", 3.0, 5.0)),
    ("Sold 1,000 SWPPX @ 0.5", ("SWPPX", 1000.0, 0.5)),
    ("Sold 0 VTI @ 10", None),
    ("Sold 10 Total Market @ 10", None),
    ("Bought 10 VTI @ 10", None),
    ("Sold VTI", None),
    ("", None),
])
def test_parse_sell_text(text, expected):
    got = sm.parse_sell_text(text)
    assert (None if got is None else (got["symbol"], got["shares"], got["price"])) == expected


def test_sell_rows_selects_only_sell_category():
    rows = sm.sell_rows(FIXTURE)
    assert [r["Monarch Id"] for r in rows] == ["m1", "m2", "m3", "m4", "m5", "m5", "m6", "", "m8"]


def test_parse_row_keeps_only_date_account_amount_when_bare():
    bare = sm.parse_sell_row(FIXTURE[2])
    assert bare == {"monarch_id": "m3", "sale_date": "2026-04-01", "account": "Roth IRA", "amount": 700.0,
                    "symbol": None, "shares": None, "price": None}
    full = sm.parse_sell_row(FIXTURE[0])
    assert (full["symbol"], full["shares"], full["price"], full["amount"]) == ("VTI", 10.0, 250.0, 2500.0)
    assert sm.parse_sell_row(FIXTURE[9]) is None


def test_count_parseable_vs_bare():
    counts = sm.count_parseable(sm.sell_rows(FIXTURE))
    assert counts == {"parseable": 6, "bare": 2, "unreadable": 1}


@pytest.fixture
def repo(tmp_path):
    with PlanStore.open(tmp_path / "plan.rpx") as s:
        yield s.sales


def test_load_queues_once_and_honors_start_date(repo):
    result = sm.load_sell_candidates(repo, FIXTURE, ledger_start=START)
    assert result == {"added": 5, "existing": 1, "before_start": 1, "no_monarch_id": 1, "unreadable": 1, "parseable": 3, "bare": 2}
    queued = {c["monarch_id"]: c for c in repo.list_candidates()}
    assert set(queued) == {"m1", "m2", "m3", "m4", "m5"}
    assert all(c["source"] == "monarch" and c["state"] == "unmatched" for c in queued.values())
    assert (queued["m2"]["symbol"], queued["m2"]["shares"], queued["m2"]["price"], queued["m2"]["amount"]) == ("BRK.B", 12.5, 80.0, 1000.0)
    assert queued["m3"]["symbol"] is None and queued["m3"]["shares"] is None and queued["m3"]["amount"] == 700.0


def test_reimport_never_requeues_confirmed_or_dismissed(repo):
    sm.load_sell_candidates(repo, FIXTURE, ledger_start=START)
    by_id = {c["monarch_id"]: c["candidate_id"] for c in repo.list_candidates()}
    repo.set_candidate_state(by_id["m1"], "confirmed", confirmed_sale_ids=[7])
    repo.set_candidate_state(by_id["m3"], "dismissed")
    again = sm.load_sell_candidates(repo, FIXTURE, ledger_start=START)
    assert again["added"] == 0 and again["existing"] == 6
    states = {c["monarch_id"]: c["state"] for c in repo.list_candidates()}
    assert states["m1"] == "confirmed" and states["m3"] == "dismissed" and len(states) == 5


def _holdings_event(repo, account, symbol, shares, day="2026-03-11"):
    cid, _ = repo.add_candidate(source="holdings_diff", sale_date=day, account=account, symbol=symbol, shares=shares)
    return cid


def test_single_clean_match_is_a_suggestion_only(repo):
    sm.load_sell_candidates(repo, FIXTURE, ledger_start=START)
    event = _holdings_event(repo, "brokerage", "vti", 10.0000004, "2026-03-12")
    out = sm.suggest_matches(repo)
    assert len(out) == 1
    assert out[0]["monarch_id"] == "m1" and out[0]["holdings_candidate_id"] == event
    assert {c["state"] for c in repo.list_candidates()} == {"unmatched"}  # nothing confirmed


@pytest.mark.parametrize("account,symbol,shares,day", [
    ("Other", "VTI", 10.0, "2026-03-11"),
    ("Brokerage", "VXUS", 10.0, "2026-03-11"),
    ("Brokerage", "VTI", 9.0, "2026-03-11"),
    ("Brokerage", "VTI", 10.0, "2026-03-14"),
])
def test_no_suggestion_when_event_does_not_fit(repo, account, symbol, shares, day):
    sm.load_sell_candidates(repo, FIXTURE, ledger_start=START)
    _holdings_event(repo, account, symbol, shares, day)
    assert sm.suggest_matches(repo) == []


def test_three_day_tolerance_is_inclusive(repo):
    sm.load_sell_candidates(repo, FIXTURE, ledger_start=START)
    _holdings_event(repo, "Brokerage", "VTI", 10.0, "2026-03-13")
    assert len(sm.suggest_matches(repo)) == 1


def test_ambiguous_matches_give_no_suggestion(repo):
    sm.load_sell_candidates(repo, FIXTURE, ledger_start=START)
    _holdings_event(repo, "Brokerage", "VTI", 10.0)
    _holdings_event(repo, "Brokerage", "VTI", 10.0, "2026-03-12")
    assert sm.suggest_matches(repo) == []


def test_event_wanted_by_two_sales_is_not_suggested(repo):
    two = [row("a1", "2026-03-10", "Brokerage", "1", "Sold 10 VTI @ 1"), row("a2", "2026-03-11", "Brokerage", "1", "Sold 10 VTI @ 1")]
    sm.load_sell_candidates(repo, two, ledger_start=START)
    _holdings_event(repo, "Brokerage", "VTI", 10.0)
    assert sm.suggest_matches(repo) == []


def test_bare_rows_and_resolved_candidates_are_never_suggested(repo):
    sm.load_sell_candidates(repo, FIXTURE, ledger_start=START)
    _holdings_event(repo, "Roth IRA", "VTI", 10.0, "2026-04-01")
    assert sm.suggest_matches(repo) == []
    event = _holdings_event(repo, "Brokerage", "VTI", 10.0)
    assert len(sm.suggest_matches(repo)) == 1
    repo.set_candidate_state(event, "dismissed")
    assert sm.suggest_matches(repo) == []


def test_sell_rows_never_change_spending(repo):
    rows = copy.deepcopy(FIXTURE)
    before = [(ytd_tracking.is_ignored_ytd_spending_flow(r), ytd_tracking.classify_cash_transaction(r)) for r in rows]
    sm.sell_rows(rows)
    sm.load_sell_candidates(repo, rows, ledger_start=START)
    assert rows == FIXTURE
    assert [(ytd_tracking.is_ignored_ytd_spending_flow(r), ytd_tracking.classify_cash_transaction(r)) for r in rows] == before
    assert all(ytd_tracking.is_ignored_ytd_spending_flow(r) for r in sm.sell_rows(rows))
