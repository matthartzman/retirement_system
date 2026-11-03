"""Sales ledger plan 7.1 / 7.2, 3a.3 gap (a): the income stack the "Tax on gains realized this year" line prices on now holds
pension, annuity income, taxable Social Security and rental income from the built plan, not just earned income."""
from __future__ import annotations

from datetime import date

import pytest

from financial_trends_reporter import percent_view as pv, realized_tax_line as rtl
from src import active_plan, sales_service, sales_tax_year
from src.projection_stages import rental_property as rp
from src.realized_income_stack import plan_income_stack
from tests import rental_fixtures as rf
from tests.test_realized_percent_view_unit import K, _sold, _transform
from tests.test_realized_tax_unit import _C

# A retired 2026 couple: earned income ended 2020; the wife's pension pays $5,000 a month; the husband (born 1955) claimed
# Social Security at 67 (2022) at $3,000 a month, no COLA so the 2026 figure stays $36,000. Federal bands at the plan's
# values (2026): MFJ 12% bracket tops at $100,800, the 0% long-term band at $98,900.
RETIRED = {**_C, "earned": 250000, "earned_end": 2020, "h_dob_yr": 1955, "ss_cola": 0.0, "ss_claim_age": 67,
           "h_ss_benefit_table": {67: 3000}, "ltcg_0_top": 98900, "ltcg_15_top": 613700,
           "wife_pension": {"first_yr": 2020, "init_pmt": 5000, "base": 0, "div_rate": 0.0575, "add_pct": 0.5}}


@pytest.fixture()
def input_dir(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True):
        pass
    return tmp_path / "input"


def test_retired_stack_has_pension_and_taxable_social_security():
    s = plan_income_stack(RETIRED, 2026)
    # pension 5,000 x 12 = 60,000. Provisional income = 60,000 + half of 36,000 = 78,000, above the MFJ $44,000 line, so
    # taxable SS = min(85% x 36,000 = 30,600, 0.85 x (78,000 - 44,000) + 6,000 = 34,900) = 30,600. Stack = 90,600.
    assert (s["earned"], s["pension"], s["annuity"], s["rental"]) == (0.0, 60000.0, 0.0, 0.0)
    assert (s["social_security"], s["social_security_taxable"], s["ordinary_income"]) == (36000.0, 30600.0, 90600.0)
    assert s["included"] == ["pension", "taxable Social Security"]
    assert "pension, taxable Social Security" in s["label"] and "Estimate" in s["label"] and "withdrawals" in s["label"]


def test_stack_before_claiming_and_while_working_is_unchanged():
    assert plan_income_stack(RETIRED, 2021)["social_security"] == 0.0
    working = {**_C, "earned": 150000, "earned_end": 2030}
    s = plan_income_stack(working, 2026)
    assert s["ordinary_income"] == 150000.0 and s["included"] == ["earned income"]
    assert plan_income_stack(_C, 2026)["ordinary_income"] == 0.0


def test_the_pension_stream_is_not_mutated_and_a_death_stops_it():
    before = dict(RETIRED["wife_pension"])
    plan_income_stack(RETIRED, 2026)
    assert RETIRED["wife_pension"] == before   # annuity_cash_income caches on the stream; the stack works on a copy
    assert plan_income_stack({**RETIRED, "w_death_yr": 2025}, 2026)["pension"] == 0.0


def test_rental_ordinary_income_is_added_from_the_rental_book():
    c = {**rf.rental_config("profitable"), "earned": 0, "earned_end": 2020}
    book = rp.rental_book_for(c)
    ry = None
    for y in range(book.plan_start, 2027):
        ry = book.year_flows(y)
    want = rp.ordinary_income(ry, book.passive_result(ry, 0.0, "MFJ"))
    s = plan_income_stack(c, 2026)
    assert want != 0.0 and s["rental"] == round(want, 2) and "rental income" in s["included"]
    parts = s["earned"] + s["pension"] + s["annuity"] + s["rental"] + s["social_security_taxable"]
    assert s["ordinary_income"] == pytest.approx(parts, abs=0.02)   # the fixture config also carries its own SS


def test_a_piece_that_cannot_be_read_falls_to_zero_not_an_error():
    bad = {**RETIRED, "wife_pension": {"first_yr": "x"}, "h_ss_benefit_table": {67: "n/a"}}
    s = plan_income_stack(bad, 2026)
    assert s["pension"] == 0.0 and s["ordinary_income"] >= 0.0


def test_worked_example_retired_year_with_pension_social_security_and_gains(input_dir, monkeypatch):
    monkeypatch.setattr(sales_tax_year, "_plan_config", lambda _d: RETIRED)
    sales_service.add_sale(input_dir, dict(sale_date="2026-06-10", account="Trust_taxable", tax_class="taxable", symbol="VTI",
                                           shares=10, proceeds=22000.0, fees=0.0, basis=2000.0, purchase_date="2025-01-02"))
    sales_service.add_sale(input_dir, dict(sale_date="2026-06-12", account="Trust_taxable", tax_class="taxable", symbol="QQQ",
                                           shares=10, proceeds=15000.0, fees=0.0, basis=5000.0, purchase_date="2026-02-01"))
    out = sales_tax_year.tax_year_summary(input_dir, 2026)
    assert (out["netting"]["gain_to_tax_ordinary"], out["netting"]["gain_to_tax_ltcg"]) == (10000.0, 20000.0)
    t = out["realized_tax"]
    # Gains: +10,000 short-term (ordinary) and +20,000 long-term. Stack 90,600 (above).
    # Ordinary: 90,600 -> 100,600 stays inside the 12% bracket (tops at 100,800): 10,000 x 12% = 1,200.
    # Long-term: stacked on 100,600, past the 0% band (98,900), inside the 15% band: 20,000 x 15% = 3,000.
    # NIIT: MAGI before + gains = 90,600 + 30,000 = 120,600, under 250,000: 0. Texas: no state tax. Total 4,200.
    # (On the earned-income-only floor of 0 the same gains cost 10,000 x 10% = 1,000 and the long-term 0%: 1,000.)
    assert t["available"] and t["ordinary_income"] == 90600.0
    assert (t["ordinary_tax"], t["ltcg_tax"], t["niit"], t["state_tax"], t["total"]) == (1200.0, 3000.0, 0.0, 0.0, 4200.0)
    assert t["income_components"]["pension"] == 60000.0 and t["income_components"]["social_security_taxable"] == 30600.0
    assert "pension" in t["note"] and "taxable Social Security" in t["note"] and t["note"].startswith("Estimate")


def test_empty_ledger_still_has_no_line_and_flat_trends_line_has_no_components(input_dir, monkeypatch):
    monkeypatch.setattr(sales_tax_year, "_plan_config", lambda _d: RETIRED)
    assert "realized_tax" not in sales_tax_year.tax_year_summary(input_dir, 2026)
    flat = rtl.line(None, [], [], date(2026, 10, 27))
    assert flat["total"] == 0.0 and flat["income_components"] is None and flat["income_note"] is None


def test_trends_line_uses_the_stack_and_labels_it():
    line = rtl.line(RETIRED, [_sold(60000.0)], [], date(2026, 10, 27), ordinary_income=10000.0)
    assert line["method"] == "planner" and line["ordinary_income"] == 90600.0
    assert line["income_components"]["pension"] == 60000.0 and "pension" in line["income_note"]


def test_percent_view_scales_the_income_components_and_leaks_nothing():
    body = {"tax": {"realized_tax": rtl.line(RETIRED, [_sold(60000.0)], [], date(2026, 10, 27), ordinary_income=10000.0)}}
    line = body["tax"]["realized_tax"]
    out = _transform(body, "/api/live-snapshot")
    assert pv.find_money_leaks(out) == []
    comp = out["tax"]["realized_tax"]["income_components"]
    assert comp["pension"] == pytest.approx(60000.0 / K) and comp["social_security_taxable"] == pytest.approx(30600.0 / K)
    assert out["tax"]["realized_tax"]["ordinary_income"] == pytest.approx(90600.0 / K)
    assert pv.find_money_leaks(body) != []   # the guard flags the unscaled payload
    assert line["income_components"]["pension"] == 60000.0   # the input is never mutated


def test_percent_view_scales_a_new_component_it_has_never_seen():
    out = pv.scale_payload({"realized_tax": {"income_components": {"pension": 60000.0, "mystery_income": 9999.0}}}, K)
    assert out["realized_tax"]["income_components"] == {"pension": 0.6, "mystery_income": 0.09999}
