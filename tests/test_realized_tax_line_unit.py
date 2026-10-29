"""Sales ledger 4.5: tax on gains realized this year, as a line beside the unrealized estimate."""
from __future__ import annotations

from datetime import date

import pytest

from financial_trends_reporter import live_snapshot as ls, realized_tax_line as rtl
from src.realized_tax import net_realized_by_year, realized_gain_tax
from tests.test_live_snapshot_compute_unit import BASELINE, MONARCH, SECURITY_MASTER, TAX
from tests.test_realized_tax_unit import _C

TODAY = date(2026, 10, 27)


def _sale(gain, term, **over):
    return {"sale_id": 1, "sale_date": "2026-06-05", "tax_class": "taxable", "status": "confirmed", "holding_period": term, "gain": gain, **over}


def test_flat_rates_net_short_against_long_then_price_the_rest():
    # +1000 ST, +2000 LT: ordinary 1000 x 25% + LTCG 2000 x 15% = 550.
    out = rtl.line(None, [_sale(1000.0, "short"), _sale(2000.0, "long")], [], TODAY)
    assert (out["method"], out["st_gain"], out["lt_gain"], out["total"]) == ("flat", 1000.0, 2000.0, 550.0)
    # A short-term loss cancels long-term gain and the rest keeps long-term character: (2000 - 500) x 15%.
    assert rtl.line(None, [_sale(-500.0, "short"), _sale(2000.0, "long")], [], TODAY)["total"] == 225.0


def test_carryforward_from_last_year_applies_to_this_year():
    out = rtl.line(None, [_sale(2000.0, "long")], [{"tax_year": 2026, "carryforward_short": 0.0, "carryforward_long": 500.0}], TODAY)
    assert out["total"] == 225.0                      # (2000 - 500) x 15%
    loss = rtl.line(None, [_sale(-5000.0, "long")], [], TODAY)
    assert (loss["ordinary_offset"], loss["carryforward_lt"], loss["total"]) == (3000.0, 2000.0, -750.0)   # $3,000 against ordinary income


def test_only_confirmed_taxable_sales_with_a_term_count():
    sales = [_sale(1000.0, "long"), _sale(9999.0, "long", status="voided"), _sale(9999.0, "long", tax_class="pre_tax"),
             _sale(500.0, "unknown"), _sale(None, "long"), _sale(800.0, "long", sale_date="2025-03-01")]
    out = rtl.line(None, sales, [], TODAY)
    assert (out["lt_gain"], out["total"], out["unknown_term"]) == (1000.0, 150.0, {"count": 1})


def test_planner_method_calls_the_engine_with_the_netting():
    sales = [_sale(4000.0, "short"), _sale(10000.0, "long")]
    out = rtl.line(_C, sales, [], TODAY, ordinary_income=60000.0)
    rows, _ = rtl.ledger_rows(sales)
    want = realized_gain_tax(_C, net_realized_by_year(rows, {}, "MFJ")[2026], year=2026, ordinary_income=60000.0, magi=60000.0)
    assert out["method"] == "planner" and out["total"] == round(want["total"], 2)
    assert out["ordinary_tax"] == round(want["ordinary_tax"], 2) and out["ltcg_tax"] == round(want["ltcg_tax"], 2)
    assert rtl.line(_C, sales, [], TODAY, ordinary_income=400000.0)["total"] > out["total"]   # a higher bracket costs more


def test_a_partial_plan_falls_back_to_flat_rates():
    out = rtl.line({"filing_status": "MFJ", "brk_inf": "not a number"}, [_sale(2000.0, "long")], [], TODAY)
    assert out["method"] == "flat" and out["total"] == 300.0


# ---- in the Live Snapshot ----
QUOTES = {"ITOT": {"price": 130.0, "previous_close": 129.0, "stale": False}}
BASE = {"baseline_date": "2025-12-31", "prices": {"ITOT": {"price": 120.0}}, "missing": []}


def _lots(*, sold: bool):
    lots = [{"account": "Member_1_Trust", "symbol": "CASH", "purchase_date": "2025-06-01", "shares": "14000" if sold else "1000", "purchase_price": "1"}]
    if not sold:
        lots.append({"account": "Member_1_Trust", "symbol": "ITOT", "purchase_date": "2025-06-01", "shares": "100", "purchase_price": "100"})
    return lots


def _compute(lots, sales=None, **kw):
    return ls.compute(lots=lots, quotes=QUOTES, baseline=BASE, security_master=SECURITY_MASTER, accounts=[], flows_daily={},
                      monarch=MONARCH, tax_rates=TAX, today=TODAY, sales=sales, **kw)


def _sold(proceeds):
    return {"sale_id": 1, "sale_date": "2026-09-01", "account": "Member_1_Trust", "tax_class": "taxable", "symbol": "ITOT", "shares": 100.0,
            "proceeds": proceeds, "basis": 10000.0, "gain": proceeds - 10000.0, "holding_period": "long", "purchase_date": "2025-06-01",
            "status": "confirmed"}


def test_selling_a_lot_moves_tax_between_the_two_lines_and_changes_the_sum_only_by_the_true_difference():
    held = _compute(_lots(sold=False))["tax"]
    assert "realized_tax" not in held and held["unrealized_gain"] == 3000.0     # 100 sh: 13000 now, 10000 basis
    # Sold at today's price (13000): the lot leaves holdings, the gain is realized instead of unrealized.
    at_market = _compute(_lots(sold=True), [_sold(13000.0)])["tax"]
    assert at_market["unrealized_gain"] == 0.0 and at_market["ltcg_tax"] == 0.0
    assert at_market["realized_tax"]["total"] == 450.0 and at_market["realized_tax"]["lt_gain"] == 3000.0
    assert at_market["total_with_realized"] == pytest.approx(held["total"])        # the two lines, summed, do not move
    # Sold 1000 above today's price: the sum rises by exactly the tax on that 1000 (15%).
    higher = _compute(_lots(sold=True), [_sold(14000.0)])["tax"]
    assert higher["total_with_realized"] - held["total"] == pytest.approx(150.0)


def test_the_unrealized_total_and_after_tax_net_worth_are_left_as_they_were():
    plain = _compute(_lots(sold=True))
    sold = _compute(_lots(sold=True), [_sold(13000.0)])
    assert sold["tax"]["total"] == plain["tax"]["total"] and sold["totals"]["after_tax_net_worth"] == plain["totals"]["after_tax_net_worth"]


def test_the_line_needs_a_sale_or_an_entered_adjustment():
    assert "realized_tax" not in _compute(_lots(sold=True))["tax"]
    assert _compute(_lots(sold=True), [], adjustments=[{"tax_year": 2026, "carryforward_short": 0.0, "carryforward_long": 0.0}])["tax"]["realized_tax"]["total"] == 0.0
