"""Plan step 5.2, pure part: the difference report, the apportioned official numbers, the CSV export, and the
comparison of a corrected statement with the one it replaces."""
from __future__ import annotations

from src.broker_1099b import matching, report
from test_broker_1099b_matching_unit import line, sale


def build(lines, ledger, **kw):
    m = matching.match_lines(lines, ledger, account="Trust")
    return report.build_report(lines, ledger, m, tax_year=2025, **kw)


def by_status(rep, status):
    return [r for r in rep["rows"] if r["status"] == status]


def test_identical_numbers_are_unchanged():
    rep = build([line(proceeds=1490.0, gain=90.0)], [sale(1)])
    assert [r["status"] for r in rep["rows"]] == ["unchanged"]
    assert rep["totals"]["changed"] == 0


def test_changed_fields_carry_ledger_official_and_delta():
    rep = build([line()], [sale(1)])
    row = by_status(rep, "changed")[0]
    assert set(row["changed"]) == {"proceeds", "gain"}
    assert row["fields"]["proceeds"] == {"ledger": 1490.0, "official": 1500.0, "delta": 10.0}
    assert row["fields"]["gain"]["delta"] == 10.0
    assert row["fields"]["basis"]["delta"] == 0.0


def test_holding_period_and_date_changes_are_reported():
    rep = build([line(term="long", acquired="2024-01-01", proceeds=1490.0, gain=90.0)], [sale(1, purchase="2025-03-04")])
    row = rep["rows"][0]
    assert {"holding_period", "purchase_date"} <= set(row["changed"])
    assert row["fields"]["holding_period"] == {"ledger": "short", "official": "long"}


def test_noncovered_basis_is_not_taken_and_is_labelled():
    rep = build([line(covered=False, basis=0.0, gain=1500.0)], [sale(1)])
    row = rep["rows"][0]
    assert "basis" not in row["changed"]
    assert row["fields"]["basis"]["official"] is None
    assert row["fields"]["basis"]["note"] == "broker did not report basis; ledger value kept"
    assert row["fields"]["gain"]["official"] == 1500.0 - 1400.0     # proceeds - kept basis + wash(0)


def test_noncovered_gain_uses_kept_basis_plus_wash_disallowed():
    rep = build([line(covered=False, wash=20.0, gain=0.0, proceeds=1500.0)], [sale(1)])
    assert rep["rows"][0]["fields"]["gain"]["official"] == 120.0


def test_unmatched_line_is_not_previously_entered():
    rep = build([line(symbol="NEW")], [])
    row = by_status(rep, "not_previously_entered")[0]
    assert row["symbol"] == "NEW" and row["fields"]["proceeds"]["official"] == 1500.0
    assert rep["totals"]["not_previously_entered"] == 1


def test_ledger_row_of_the_year_without_a_line_is_flagged():
    rep = build([line()], [sale(1), sale(2, symbol="ZZZ"), sale(3, symbol="OLD", sold="2024-05-05", purchase="2023-01-01")])
    flagged = by_status(rep, "no_1099b_line")
    assert [r["sale_ids"] for r in flagged] == [[2]]          # the 2024 row is outside this tax year


def test_aggregate_numbers_are_apportioned_by_shares_with_the_remainder_on_the_last_row():
    agg = line(acquired=None, qty=15.0, proceeds=3000.01, basis=2000.0, gain=1000.01)
    ledger = [sale(1, shares=10.0), sale(2, shares=5.0, purchase="2025-04-01")]
    m = matching.match_lines([agg], ledger, account="Trust")
    parts = report.apportion(agg, [sale_row for sale_row in ledger if sale_row["sale_id"] in m["matches"][0]["sale_ids"]])
    assert [p["sale_id"] for p in parts] == [1, 2]
    assert round(sum(p["proceeds"] for p in parts), 2) == 3000.01
    assert (parts[0]["proceeds"], parts[1]["proceeds"]) == (2000.01, 1000.0)     # 3000.01 x 10/15 rounds up; remainder last
    assert round(sum(p["gain"] for p in parts), 2) == 1000.01
    assert all("purchase_date" not in p for p in parts)


def test_official_values_for_a_lot_line():
    (p,) = report.apportion(line(), [sale(1)])
    assert p == {"sale_id": 1, "sale_date": "2025-09-10", "purchase_date": "2025-03-04", "proceeds": 1500.0,
                 "basis": 1400.0, "gain": 100.0, "holding_period": "short", "official_proceeds": 1500.0,
                 "official_basis": 1400.0, "official_gain": 100.0, "official_holding_period": "short"}


def test_csv_export_has_one_row_per_report_row_and_a_header():
    rep = build([line(), line(symbol="NEW")], [sale(1)])
    text = report.report_csv(rep)
    rows = text.strip().splitlines()
    assert rows[0].startswith("status,symbol,date_sold,quantity,")
    assert len(rows) == 1 + len(rep["rows"])
    assert any(r.startswith("changed,ABCD,2025-09-10,10.0,") for r in rows)


def test_compare_statements_lists_added_removed_and_changed_lines():
    old = [line(), line(symbol="GONE", qty=1.0), line(symbol="CHG", proceeds=100.0, gain=0.0, basis=100.0)]
    new = [line(), line(symbol="NEW", qty=2.0), line(symbol="CHG", proceeds=110.0, gain=10.0, basis=100.0)]
    d = report.compare_statements(old, new)
    assert [x["symbol"] for x in d if x["change"] == "added"] == ["NEW"]
    assert [x["symbol"] for x in d if x["change"] == "removed"] == ["GONE"]
    chg = [x for x in d if x["change"] == "changed"]
    assert len(chg) == 1 and chg[0]["symbol"] == "CHG" and chg[0]["fields"]["proceeds"] == {"old": 100.0, "new": 110.0, "delta": 10.0}


def test_compare_identical_statements_is_empty():
    assert report.compare_statements([line()], [line()]) == []
