"""Plan step 5.1a through 5.2: a synthetic Vanguard statement matched many-to-one against the ledger, then applied."""
from __future__ import annotations

import pytest

import broker_1099b_vanguard_synthetic as syn
from src import active_plan, sales_1099b

SYMBOLS = {"ABCD", "LMNO"}
BASE = dict(symbol="ABCD", account="Brokerage", tax_class="taxable", fees=0.0, source="manual", sale_date="2025-09-10",
            purchase_date="2025-01-02", holding_period="short")


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        # Three confirmed lots sold on the Various line's date: 10 + 3 + 2.5 = 15.5 shares.
        for shares, proceeds, basis in ((10.0, 1500.0, 1500.0), (3.0, 450.0, 450.0), (2.5, 375.0, 350.25)):
            store.sales.insert_sale(**BASE, shares=shares, proceeds=proceeds, basis=basis, gain=round(proceeds - basis, 2))
    return tmp_path


def kw(**over):
    return {"broker": "vanguard", "account": "Brokerage", "text": syn.build_statement(), "known_symbols": SYMBOLS, **over}


def test_preview_matches_the_various_line_many_to_one(ws):
    pv = sales_1099b.preview(ws / "input", **kw())
    assert pv["can_apply"] is True and pv["tax_year"] == 2025 and pv["meta"]["corrected"] is True
    agg = [m for m in pv["match"]["matches"] if m["kind"] == "aggregate"]
    assert len(agg) == 1 and len(agg[0]["sale_ids"]) == 3
    # the blank-symbol redemption never matches a holdings symbol, so it is reported as not previously entered
    assert pv["report"]["totals"]["not_previously_entered"] == 4


def test_apply_apportions_official_numbers_and_adds_blank_symbol_rows_by_cusip(ws):
    out = sales_1099b.apply(ws / "input", **kw())
    assert out["corrected"] == 3 and out["added"] == 4
    with active_plan.workspace_store(ws) as store:
        sales = store.sales.list_sales()
        statement = store.sales.list_statements()[0]
    assert statement["corrected"] and statement["status"] == "applied"
    mine = [s for s in sales if s["sale_date"] == "2025-09-10" and s["source"] != "1099b"]
    assert round(sum(s["proceeds"] for s in mine), 2) == 2280.50 and round(sum(s["basis"] for s in mine), 2) == 2300.25
    assert any(s["symbol"] == "CUSIP-555555555" and s["source"] == "1099b" for s in sales)
