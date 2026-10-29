"""Plan step 5.2, pure part: match normalized 1099-B lines to ledger rows (lot-level, then many-to-one)."""
from __future__ import annotations

from src.broker_1099b import matching


def line(symbol="ABCD", sold="2025-09-10", acquired="2025-03-04", qty=10.0, proceeds=1500.0, basis=1400.0, gain=100.0,
         covered=True, term="short", wash=0.0, **kw):
    return {"symbol": symbol, "date_sold": sold, "date_acquired": acquired, "quantity": qty, "proceeds": proceeds,
            "basis": basis, "gain": gain, "covered": covered, "term": term, "wash_disallowed": wash,
            "market_discount": 0.0, "account": "x", "cusip": "1", "description": "", **kw}


def sale(sale_id, symbol="ABCD", sold="2025-09-10", purchase="2025-03-04", shares=10.0, account="Trust", **kw):
    return {"sale_id": sale_id, "sale_date": sold, "purchase_date": purchase, "shares": shares, "symbol": symbol,
            "account": account, "tax_class": "taxable", "status": "confirmed", "proceeds": 1490.0, "basis": 1400.0,
            "fees": 0.0, "gain": 90.0, "holding_period": "short", **kw}


def run(lines, ledger, **kw):
    return matching.match_lines(lines, ledger, account="Trust", **kw)


def test_exact_lot_match():
    r = run([line()], [sale(1)])
    assert r["matches"] == [{"line_index": 0, "kind": "lot", "how": "exact", "sale_ids": [1]}]
    assert r["unmatched_lines"] == [] and r["unmatched_ledger"] == []


def test_match_ignores_other_accounts_voided_and_non_taxable_rows():
    ledger = [sale(1, account="Other"), sale(2, status="voided"), sale(3, tax_class="roth")]
    r = run([line()], ledger)
    assert r["matches"] == [] and r["unmatched_lines"] == [0] and r["unmatched_ledger"] == []


def test_symbol_comparison_is_case_insensitive():
    assert run([line(symbol="abcd")], [sale(1)])["matches"][0]["sale_ids"] == [1]


def test_purchase_date_difference_still_matches_on_shares():
    r = run([line()], [sale(1, purchase="2025-03-06")])
    assert r["matches"][0]["how"] == "shares"


def test_exact_purchase_date_wins_over_a_same_size_lot_with_another_date():
    ledger = [sale(1, purchase="2025-01-01"), sale(2, purchase="2025-03-04")]
    r = run([line()], ledger)
    assert r["matches"][0]["sale_ids"] == [2] and r["unmatched_ledger"] == [1]


def test_trade_date_within_tolerance_matches_and_is_labelled():
    r = run([line()], [sale(1, sold="2025-09-09")])
    assert r["matches"][0]["how"] == "date"
    assert run([line()], [sale(1, sold="2025-09-01")])["matches"] == []


def test_exact_date_claims_a_row_before_a_tolerance_match():
    ledger = [sale(1, sold="2025-09-09"), sale(2, sold="2025-09-10")]
    r = run([line()], ledger)
    assert r["matches"][0]["sale_ids"] == [2]


def test_two_lines_claim_two_rows_once_each():
    lines = [line(qty=10.0), line(qty=5.5, acquired="2025-05-20")]
    ledger = [sale(1), sale(2, shares=5.5, purchase="2025-05-20")]
    r = run(lines, ledger)
    assert [m["sale_ids"] for m in r["matches"]] == [[1], [2]]


def test_aggregate_line_matches_rows_that_sum_to_its_quantity():
    agg = line(acquired=None, qty=15.0, proceeds=3000.0)
    ledger = [sale(1, shares=10.0), sale(2, shares=5.0, purchase="2025-04-01"), sale(3, shares=2.0)]
    r = run([agg], ledger)
    assert r["matches"] == [{"line_index": 0, "kind": "aggregate", "how": "aggregate", "sale_ids": [1, 2]}]
    assert r["unmatched_ledger"] == [3]


def test_aggregate_shares_that_do_not_sum_leave_the_line_unmatched():
    r = run([line(acquired=None, qty=15.0)], [sale(1, shares=10.0), sale(2, shares=4.0)])
    assert r["matches"] == [] and r["unmatched_lines"] == [0] and r["unmatched_ledger"] == [1, 2]


def test_lot_line_does_not_aggregate_when_it_has_an_acquired_date():
    r = run([line(qty=15.0)], [sale(1, shares=10.0), sale(2, shares=5.0)])
    assert r["matches"] == []


def test_fractional_share_tolerance():
    assert run([line(qty=31.25)], [sale(1, shares=31.2500004, purchase="2025-03-04")])["matches"]


def test_unmatched_ledger_rows_are_listed_by_id():
    r = run([line()], [sale(1), sale(2, symbol="ZZZ")])
    assert r["unmatched_ledger"] == [2]
