"""Fuzzy 1099-B match suggestions and the possible-return-of-capital label (plan 5.4). Advisory only; synthetic data."""
from __future__ import annotations

from src.broker_1099b import matching, report
from test_broker_1099b_matching_unit import line, sale


def sug(lines, ledger, **kw):
    m = matching.match_lines(lines, ledger, account="Trust")
    return m, matching.suggest(lines, ledger, m, account="Trust", **kw)


def test_near_miss_is_suggested_and_not_matched():
    ln = line(qty=10.0, sold="2025-09-10", proceeds=1500.0)
    row = sale(1, sold="2025-09-25", shares=10.4, proceeds=1490.0)  # 15 days and 0.4 shares off: no exact pass takes it
    m, s = sug([ln], [row])
    assert m["matches"] == [] and m["unmatched_lines"] == [0]
    assert [c["sale_id"] for c in s[0]] == [1]
    assert s[0][0]["score"] >= matching.SUGGESTION_MIN_SCORE
    assert "15 days apart" in s[0][0]["reason"] and "same symbol" in s[0][0]["reason"]


def test_ranked_best_first_and_capped_at_three():
    ln = line(qty=10.0)
    ledger = [sale(i, sold=f"2025-09-{10 + d:02d}", shares=10.5, purchase=None) for i, d in ((1, 12), (2, 5), (3, 9), (4, 7), (5, 20))]
    _, s = sug([ln], ledger)
    assert len(s[0]) == 3
    assert [c["sale_id"] for c in s[0]] == [2, 4, 3]
    assert [c["score"] for c in s[0]] == sorted((c["score"] for c in s[0]), reverse=True)


def test_other_symbol_account_voided_and_claimed_rows_are_never_suggested():
    ledger = [sale(1, symbol="WXYZ", shares=10.4), sale(2, account="Other", shares=10.4), sale(3, status="voided", shares=10.4),
              sale(4, tax_class="roth", shares=10.4), sale(5, shares=10.0)]  # 5 is claimed by the exact pass
    m, s = sug([line(), line(qty=11.0)], ledger)
    assert m["matches"][0]["sale_ids"] == [5]
    assert s == {}


def test_weak_candidate_below_threshold_is_dropped_and_cusip_only_lines_use_the_cusip_symbol():
    far = sale(1, sold="2025-01-02", shares=3.0, proceeds=100.0)
    assert sug([line()], [far])[1] == {}
    cus = sale(2, symbol="CUSIP-123456789", shares=10.2)
    _, s = sug([line(symbol=None, cusip="123456789")], [cus])
    assert s[0][0]["sale_id"] == 2 and "same CUSIP" in s[0][0]["reason"]


def test_suggestions_do_not_change_matching_and_ride_on_the_not_previously_entered_row():
    ln, row = line(), sale(1, sold="2025-09-25", shares=10.4)
    ledger = [row]
    before = matching.match_lines([ln], ledger, account="Trust")
    m, s = sug([ln], ledger)
    assert m == before
    plain = report.build_report([ln], ledger, m, tax_year=2025)
    rep = report.build_report([ln], ledger, m, tax_year=2025, suggestions=s)
    assert plain["rows"][0].get("suggestions") is None
    nr = [r for r in rep["rows"] if r["status"] == "not_previously_entered"][0]
    assert nr["suggestions"][0]["sale_id"] == 1
    assert report.report_csv(rep) == report.report_csv(plain)


def roc_row(official_basis, ledger_basis=1400.0, proceeds=1500.0, **kw):
    ln = line(basis=official_basis, proceeds=proceeds, gain=proceeds - official_basis, **kw)
    led = [sale(1, proceeds=1500.0, basis=ledger_basis)]
    m = matching.match_lines([ln], led, account="Trust")
    return report.build_report([ln], led, m, tax_year=2025)["rows"][0]


def test_small_basis_drop_with_same_proceeds_is_labelled():
    r = roc_row(1350.0)
    assert r["possible_return_of_capital"] == {"amount": 50.0, "fraction_of_basis": 0.0357}
    assert "return of capital" in r["note"]


def test_roc_label_is_conservative():
    assert "possible_return_of_capital" not in roc_row(1400.0)            # no difference
    assert "possible_return_of_capital" not in roc_row(1450.0)            # basis higher
    assert "possible_return_of_capital" not in roc_row(1399.5)            # rounding-size drop
    assert "possible_return_of_capital" not in roc_row(900.0)             # 36 percent: not plausible
    assert "possible_return_of_capital" not in roc_row(1350.0, proceeds=1600.0)  # proceeds differ: not the same sale
    assert "possible_return_of_capital" not in roc_row(1350.0, covered=False)    # broker basis not reported
