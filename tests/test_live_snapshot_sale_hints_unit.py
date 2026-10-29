"""Sales ledger 4.5: the unmatched_sale and sale_not_in_holdings hints on the Trends reconcile card (plan 11)."""
from __future__ import annotations

from datetime import date

from financial_trends_reporter import live_snapshot as ls
from tests.test_live_snapshot_compute_unit import BASELINE, SECURITY_MASTER, TAX

TODAY = date(2026, 10, 27)
QUOTES = {"ITOT": {"price": 130.0, "previous_close": 129.0, "stale": False}}
BASE = {"baseline_date": "2025-12-31", "prices": {"ITOT": {"price": 120.0}}, "missing": []}
LOTS = [{"account": "Member_1_Trust", "symbol": "ITOT", "purchase_date": "2025-06-01", "shares": "100", "purchase_price": "100"},
        {"account": "Member_1_Trust", "symbol": "CASH", "purchase_date": "2025-06-01", "shares": "1000", "purchase_price": "1"}]
ACCOUNTS = [{"account": "Trust - Matt", "role": "Investment", "mapped_investment_account": "Member_1_Trust"}]
# Holdings at the prior close are 13000 - 100 (ITOT's day move) + 1000 = 13900; the imported balance is 8400: a 5500 gap.
MONARCH = {"latest_date": "2026-10-26", "by_account": [{"account": "Trust - Matt", "type": "Investment", "value": 8400.0, "as_of": "2026-10-26"}]}
WAITING = {"candidate_id": 1, "source": "monarch", "sale_date": "2026-10-27", "account": "Trust - Matt", "symbol": "ITOT", "shares": 40.0,
           "price": None, "amount": 5500.0}


def _hints(**kw):
    out = ls.compute(lots=LOTS, quotes=QUOTES, baseline=BASE, security_master=SECURITY_MASTER, accounts=ACCOUNTS, flows_daily={},
                     monarch=MONARCH, tax_rates=TAX, today=TODAY, **kw)
    (row,) = out["reconciliation"]["accounts"]
    assert row["flag"] and row["delta"] == 5500.0
    return [h for h in row["hints"]]


def _kinds(hints):
    return [h["kind"] for h in hints]


def test_a_waiting_sale_near_the_gap_is_named_ahead_of_the_direction_hint():
    hints = _hints(unconfirmed=[WAITING])
    assert _kinds(hints)[-2:] == ["unmatched_sale", "direction"]
    sale = next(h for h in hints if h["kind"] == "unmatched_sale")
    assert (sale["symbol"], sale["sale_date"], sale["shares"], sale["confirmed"]) == ("ITOT", "2026-10-27", 40.0, False)


def test_no_hint_when_the_sale_is_the_wrong_size_or_not_after_the_balance_date_or_another_account():
    assert "unmatched_sale" not in _kinds(_hints())
    assert "unmatched_sale" not in _kinds(_hints(unconfirmed=[{**WAITING, "amount": 3000.0}]))
    assert "unmatched_sale" not in _kinds(_hints(unconfirmed=[{**WAITING, "sale_date": "2026-10-26"}]))    # on the balance date, not after it
    assert "unmatched_sale" not in _kinds(_hints(unconfirmed=[{**WAITING, "account": "IRA - Matt"}]))


def test_a_candidate_may_name_the_holdings_account_or_a_price_instead_of_an_amount():
    by_holdings = {**WAITING, "account": "Member_1_Trust"}
    assert "unmatched_sale" in _kinds(_hints(unconfirmed=[by_holdings]))
    by_price = {**WAITING, "amount": None, "shares": 55.0, "price": 100.0}
    assert "unmatched_sale" in _kinds(_hints(unconfirmed=[by_price]))


def test_a_confirmed_sale_is_named_as_in_the_ledger():
    ledger = {"sale_id": 1, "sale_date": "2026-10-27", "account": "Member_1_Trust", "symbol": "AVUV", "shares": 10.0, "proceeds": 5400.0,
              "basis": 4000.0, "purchase_date": "2024-01-02", "status": "confirmed"}
    sale = next(h for h in _hints(sales=[ledger]) if h["kind"] == "unmatched_sale")
    assert sale["confirmed"] is True and sale["symbol"] == "AVUV"


def test_a_confirmed_whole_lot_sale_whose_lot_is_still_in_holdings_is_a_stale_file():
    still_there = {"sale_id": 1, "sale_date": "2026-10-01", "account": "Member_1_Trust", "symbol": "ITOT", "shares": 100.0, "proceeds": 100.0,
                   "basis": 10000.0, "purchase_date": "2025-06-01", "status": "confirmed"}
    hints = _hints(sales=[still_there])
    stale = next(h for h in hints if h["kind"] == "sale_not_in_holdings")
    assert (stale["symbol"], stale["sale_date"]) == ("ITOT", "2026-10-01")
    assert "sale_not_in_holdings" not in _kinds(_hints(sales=[{**still_there, "shares": 40.0}]))   # a part sale leaves a smaller lot: no claim
