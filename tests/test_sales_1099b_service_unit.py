"""Plan step 5.2: preview and apply of a broker 1099-B against the ledger (scratch workspace, synthetic statement)."""
from __future__ import annotations

import pytest

import broker_1099b_synthetic as syn
from src import active_plan, sales_1099b
from src.sales_ledger import ValidationError

SYMBOLS = {"ABCD", "WXYZ", "QRST", "LMNO", "PQRS"}
BASE = dict(symbol="ABCD", account="Trust", tax_class="taxable", shares=10.0, fees=0.0, source="manual",
            sale_date="2025-09-10", purchase_date="2025-03-04", holding_period="short", proceeds=1490.0, basis=1400.0, gain=90.0)


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.sales.insert_sale(**BASE)                                                    # 1: matches lot 1 exactly (numbers differ)
        store.sales.insert_sale(**{**BASE, "shares": 5.5, "purchase_date": "2025-05-20", "proceeds": 780.5,
                                   "basis": 900.25, "gain": -119.75})                    # 2: identical to the statement line
        store.sales.insert_sale(**{**BASE, "symbol": "ZZZ", "sale_date": "2025-04-01", "purchase_date": "2025-01-01"})  # 3: no line
        store.sales.insert_sale(**{**BASE, "account": "Other"})                           # 4: another account
    return tmp_path


def kw(**over):
    return {"broker": "etrade", "account": "Trust", "text": syn.build_statement(), "known_symbols": SYMBOLS, **over}


def row(ws, sale_id):
    return next(r for r in rows(ws) if r["sale_id"] == sale_id)


def rows(ws, **q):
    with active_plan.workspace_store(ws) as store:
        return store.sales.list_sales(include_voided=True, **q)


def test_preview_reports_matches_differences_and_unmatched(ws):
    pv = sales_1099b.preview(ws / "input", **kw())
    assert pv["schema"] == "import_preview_v1" and pv["can_apply"] is True and pv["tax_year"] == 2025
    t = pv["report"]["totals"]
    assert (t["changed"], t["unchanged"], t["not_previously_entered"], t["no_1099b_line"]) == (1, 1, 5, 1)
    assert pv["supersedes"] is None and pv["report_csv"].startswith("status,symbol,")
    assert pv["received"] == 7


def test_preview_writes_nothing(ws):
    before = rows(ws)
    sales_1099b.preview(ws / "input", **kw())
    assert rows(ws) == before
    with active_plan.workspace_store(ws) as store:
        assert store.sales.list_statements() == []


def test_preview_with_a_control_total_gap_cannot_apply(ws):
    bad = syn.totals()
    bad[("short", True)] = (1.0,) + bad[("short", True)][1:]
    pv = sales_1099b.preview(ws / "input", **kw(text=syn.build_statement(summary=bad)))
    assert pv["can_apply"] is False and pv["report"]["rows"]            # the report is still shown
    with pytest.raises(ValidationError, match="control"):
        sales_1099b.apply(ws / "input", **kw(text=syn.build_statement(summary=bad)))


def test_account_is_required(ws):
    with pytest.raises(ValidationError, match="account"):
        sales_1099b.preview(ws / "input", **kw(account=""))


def test_apply_replaces_numbers_keeps_pre_values_in_audit_and_adds_unreported_lines(ws):
    res = sales_1099b.apply(ws / "input", **kw())
    assert res["corrected"] == 2 and res["added"] == 5
    one = row(ws, 1)
    assert (one["proceeds"], one["basis"], one["gain"], one["holding_period"]) == (1500.0, 1400.0, 100.0, "short")
    assert (one["official_proceeds"], one["official_basis"], one["official_gain"]) == (1500.0, 1400.0, 100.0)
    assert one["statement_id"] is None
    with active_plan.workspace_store(ws) as store:
        a = [x for x in store.sales.audit(sale_id=1) if x["action"] == "correct"][0]
        assert a["before"]["proceeds"] == 1490.0 and a["after"]["proceeds"] == 1500.0
        added = [r for r in store.sales.list_sales() if r["source"] == "1099b"]
        assert len(added) == 5 and all(r["statement_id"] == res["statement_id"] for r in added)
        assert sorted(r["symbol"] for r in added) == ["LMNO", "LMNO", "PQRS", "QRST", "WXYZ"]
        assert store.sales.get_statement(res["statement_id"])["control"]["status"] == "ok"
        assert len(store.sales.statement_lines(res["statement_id"])) == 7
    assert row(ws, 3)["proceeds"] == 1490.0          # the ledger row with no 1099-B line is left alone
    assert [r for r in rows(ws) if r["account"] == "Other"][0]["official_proceeds"] is None


def test_applied_rows_cannot_be_undone_through_the_queue(ws):
    sales_1099b.apply(ws / "input", **kw())
    r = row(ws, 1)
    assert r["official_proceeds"] is not None             # sales_confirm.undo refuses rows with official_* numbers


def test_apply_is_all_or_nothing(ws, monkeypatch):
    from src.stores import sales_repo
    real = sales_repo.SalesRepo.add_line
    calls = []

    def boom(self, *a, **k):
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError("disk full")
        return real(self, *a, **k)

    monkeypatch.setattr(sales_repo.SalesRepo, "add_line", boom)
    before = rows(ws)
    with pytest.raises(RuntimeError):
        sales_1099b.apply(ws / "input", **kw())
    assert rows(ws) == before
    with active_plan.workspace_store(ws) as store:
        assert store.sales.list_statements() == [] and store.sales.audit() == []


def test_second_import_needs_confirmation_and_identical_file_is_refused(ws):
    sales_1099b.apply(ws / "input", **kw())
    with pytest.raises(ValidationError, match="already imported"):
        sales_1099b.apply(ws / "input", **kw())
    with pytest.raises(ValidationError, match="identical"):
        sales_1099b.apply(ws / "input", **kw(), replace=True)


CORRECTED = {**syn.DEFAULT_SECTIONS,
             ("short", True): [(c, s, d, [(l if (s, l[8]) != ("ABCD", 10.0) else (l[0], l[1], 1510.0, l[3], l[4], l[5], 110.0, l[7], l[8])) for l in lots])
                               for c, s, d, lots in syn.DEFAULT_SECTIONS[("short", True)]]}


def test_corrected_statement_preview_shows_the_supersede_and_what_changed(ws):
    sales_1099b.apply(ws / "input", **kw())
    pv = sales_1099b.preview(ws / "input", **kw(text=syn.build_statement(CORRECTED)))
    assert pv["supersedes"]["line_count"] == 7
    ch = pv["changes_since_previous"]
    assert len(ch) == 1 and ch[0]["symbol"] == "ABCD" and ch[0]["fields"]["proceeds"]["delta"] == 10.0
    # compared with the ledger as it stood before the earlier import, not with the rows that import already rewrote
    t = pv["report"]["totals"]
    assert t["changed"] == 1 and t["unchanged"] == 1 and t["not_previously_entered"] == 5


def test_replace_reverts_the_earlier_import_then_applies_the_corrected_one(ws):
    first = sales_1099b.apply(ws / "input", **kw())
    res = sales_1099b.apply(ws / "input", **kw(text=syn.build_statement(CORRECTED)), replace=True)
    assert res["superseded"] == first["statement_id"]
    one = row(ws, 1)
    assert (one["proceeds"], one["gain"], one["official_proceeds"]) == (1510.0, 110.0, 1510.0)
    live = [r for r in rows(ws) if r["source"] == "1099b" and r["status"] == "confirmed"]
    assert len(live) == 5 and all(r["statement_id"] == res["statement_id"] for r in live)
    assert len([r for r in rows(ws) if r["source"] == "1099b"]) == 10          # the first import's rows are voided, kept
    with active_plan.workspace_store(ws) as store:
        assert store.sales.get_statement(first["statement_id"])["status"] == "superseded"
        assert store.sales.active_statement("etrade", "Trust", 2025)["statement_id"] == res["statement_id"]


def test_a_lot_line_never_aggregates_ledger_rows(ws):
    agg = {("short", True): [("111111111", "ABCD", "Alpha", [("03/04/25", "09/10/25", 3000.0, 2800.0, 0.0, 0.0, 200.0, 0.0, 15.5)])]}
    res = sales_1099b.apply(ws / "input", **kw(text=syn.build_statement(agg)))
    assert res["corrected"] == 0 and res["added"] == 1


def test_apply_apportions_an_aggregate_line_across_the_matched_rows(ws):
    from src import broker_1099b
    from src.broker_1099b import normalized

    def fake(text, *, known_symbols=None, account=None):
        ln = {"broker": "fake", "account": account, "symbol": "ABCD", "cusip": "1", "description": "", "date_acquired": None,
              "date_sold": "2025-09-10", "proceeds": 2400.0, "basis": 2200.0, "market_discount": 0.0, "wash_disallowed": 0.0,
              "gain": 200.0, "term": "short", "covered": True, "quantity": 15.5, "fed_withheld": 0.0}
        st = normalized.ParsedStatement(broker="fake", rows=[ln], summary={("short", True): {
            "proceeds": 2400.0, "basis": 2200.0, "market_discount": 0.0, "wash_disallowed": 0.0, "gain": 200.0}})
        st.control = normalized.check_control_totals(st.rows, st.summary)
        st.meta["tax_year"] = 2025
        return st

    broker_1099b.register("fake", fake)
    try:
        res = sales_1099b.apply(ws / "input", broker="fake", account="Trust", text="x", known_symbols=SYMBOLS)
    finally:
        broker_1099b.REGISTRY.pop("fake", None)
    assert res["corrected"] == 2 and res["added"] == 0
    a, b = row(ws, 1), row(ws, 2)
    assert round(a["proceeds"] + b["proceeds"], 2) == 2400.0 and round(a["gain"] + b["gain"], 2) == 200.0
    assert a["purchase_date"] == "2025-03-04" and b["purchase_date"] == "2025-05-20"     # dates untouched


def test_noncovered_line_keeps_the_ledger_basis(ws):
    sections = {("short", False): [("111111111", "ABCD", "Alpha", [("03/04/25", "09/10/25", 1500.0, 0.0, 0.0, 0.0, 1500.0, 0.0, 10.0)])]}
    sales_1099b.apply(ws / "input", **kw(text=syn.build_statement(sections)))
    one = row(ws, 1)
    assert (one["proceeds"], one["basis"], one["gain"]) == (1500.0, 1400.0, 100.0)
    assert one["official_basis"] is None and one["official_gain"] is None and one["official_proceeds"] == 1500.0


def test_unsupported_broker_and_year_mismatch(ws):
    with pytest.raises(ValidationError, match="Unknown broker"):
        sales_1099b.preview(ws / "input", **kw(broker="nosuch"))
    with pytest.raises(ValidationError, match="tax year"):
        sales_1099b.preview(ws / "input", **kw(tax_year=2024))
