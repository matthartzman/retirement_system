"""Sales ledger plan 7.2 / 9.4 / 10 (3a.3 gap a): the dollar "Tax on gains realized this year" line in the Planner's
tax-year panel payload and in Trends, with the percent-view leak guard."""
from __future__ import annotations

from datetime import date

import pytest

from financial_trends_reporter import percent_view as pv, realized_tax_line as rtl
from src import active_plan, sales_service, sales_tax_year
from src.realized_tax import realized_gain_tax
from tests.test_realized_percent_view_unit import K, _sold, _transform
from tests.test_realized_tax_unit import _C


@pytest.fixture()
def input_dir(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True):
        pass
    return tmp_path / "input"


def _add(input_dir, **over):
    row = dict(sale_date="2026-06-10", account="Trust_taxable", tax_class="taxable", symbol="VTI", shares=10,
               proceeds=22000.0, fees=0.0, basis=2000.0, purchase_date="2025-01-02")
    row.update(over)
    return sales_service.add_sale(input_dir, row)


def test_empty_ledger_has_no_realized_tax_line(input_dir):
    assert "realized_tax" not in sales_tax_year.tax_year_summary(input_dir, 2026)


def test_planner_payload_prices_the_netting_with_the_engine(input_dir, monkeypatch):
    cfg = {**_C, "earned": 150000, "earned_end": 2030}
    monkeypatch.setattr(sales_tax_year, "_plan_config", lambda _d: cfg)
    _add(input_dir)   # +20,000 long
    out = sales_tax_year.tax_year_summary(input_dir, 2026)
    t = out["realized_tax"]
    want = realized_gain_tax(cfg, out["netting"], year=2026, ordinary_income=150000.0, magi=150000.0)
    assert t["available"] and t["total"] == round(want["total"], 2) > 0 and t["ordinary_income"] == 150000.0
    assert t["ltcg_tax"] == round(want["ltcg_tax"], 2) and t["niit"] == round(want["niit"], 2)


def test_planner_payload_unavailable_without_a_buildable_plan(input_dir, monkeypatch):
    monkeypatch.setattr(sales_tax_year, "_plan_config", lambda _d: None)
    _add(input_dir)
    t = sales_tax_year.tax_year_summary(input_dir, 2026)["realized_tax"]
    assert t["available"] is False and "total" not in t


def test_trends_line_uses_the_plan_income_when_larger_than_the_recorded_floor():
    cfg = {**_C, "earned": 250000, "earned_end": 2030}
    today = date(2026, 10, 27)
    low = rtl.line(cfg, [_sold(60000.0)], [], today, ordinary_income=10000.0)
    assert low["method"] == "planner" and low["ordinary_income"] == 250000.0
    assert low["label"] == "Tax on gains realized in 2026"
    retired = rtl.line({**cfg, "earned_end": 2025}, [_sold(60000.0)], [], today, ordinary_income=10000.0)
    assert retired["ordinary_income"] == 10000.0 and retired["total"] < low["total"]


def test_empty_trends_line_is_unchanged_in_flat_form():
    out = rtl.line(None, [], [], date(2026, 10, 27))
    assert out["total"] == 0.0 and out["ordinary_income"] is None


def test_percent_view_scales_the_new_dollar_fields_and_leaks_nothing():
    cfg = {**_C, "earned": 250000, "earned_end": 2030}
    body = {"tax": {"realized_tax": rtl.line(cfg, [_sold(60000.0)], [], date(2026, 10, 27), ordinary_income=10000.0)}}
    line = body["tax"]["realized_tax"]
    out = _transform(body, "/api/live-snapshot")
    assert pv.find_money_leaks(out) == []
    assert out["tax"]["realized_tax"]["ordinary_income"] == pytest.approx(250000.0 / K)
    assert out["tax"]["realized_tax"]["total"] == pytest.approx(line["total"] / K)
    assert pv.find_money_leaks(body) != []   # the guard does flag the unscaled payload


def test_planner_panel_fields_are_scaled_fail_closed():
    out = pv.scale_payload({"realized_tax": {"magi": 250000.0, "ordinary_income": 250000.0, "mystery": 9999.0}}, K)
    assert out["realized_tax"] == {"magi": 2.5, "ordinary_income": 2.5, "mystery": 0.09999}
