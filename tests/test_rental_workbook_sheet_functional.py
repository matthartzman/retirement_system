"""The Rental Properties sheet (WP12.7; design 2026-10-05 section 7): sections A-G.

Sheet '40. Rental Properties' exists only while ``rental_property_income`` is on. Cases come from
``tests/rental_fixtures.py``; the sheet is built in process from the projection rows, and one slow
test checks a real build with the feature on and off.
"""
from __future__ import annotations

import json

import pytest
from openpyxl import Workbook, load_workbook

import src.module_catalog as mc
from src.reporting import rental_report_data as rrd
from src.reporting import workbook_common as wc
from src.reporting.sheets_rental import SHEET, assumption_lines, build_sheet_rental
from tests.rental_fixtures import project, rental_config
from tests.rental_sheet_helpers import ALL_CASES, ROOT, built_workbooks, case, rental_sheet, row_labeled, texts

# ── registry and gating ─────────────────────────────────────────────────────────
def test_sheet_is_registered_after_the_balance_sheet_and_gated_by_the_feature():
    spec = wc._SHEET_REGISTRY[SHEET]
    assert spec.module_key == "rental_property_income" and spec.slug == "rental_properties"
    assert SHEET == "40. Rental Properties"
    reports = next(a["sheets"] for a in wc.WORKBOOK_SECTION_LAYOUT if a["code"] == "1")
    assert reports.index("3. Balance Sheet") < reports.index(SHEET) < reports.index("7. Lifetime Tax")
    assert mc.OPTIONAL_MODULE_SHEETS["rental_property_income"] == [SHEET]
    c_off, c_on = rental_config("profitable", on=False), rental_config("profitable", on=True)
    assert not mc.module_enabled(c_off, "rental_property_income")
    assert mc.module_enabled(c_on, "rental_property_income")


# ── the sheet itself ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("name", ALL_CASES)
def test_sheet_has_every_section_and_every_limitation(name):
    ws, rep, _c, _rows = rental_sheet(name)
    assert rep is not None
    body = texts(ws)
    for heading in ("A. SUMMARY BY YEAR", "B. BY PROPERTY AND YEAR", "C. DEPRECIATION SCHEDULE", "D. PASSIVE-LOSS LEDGER",
                    "E. SALE ANALYSIS", "F. METRICS", "G. ASSUMPTIONS AND WARNINGS"):
        assert any(t.startswith(heading) for t in body), heading
    joined = "\n".join(body)
    # The verification note, the defaults and every exclusion are stated in plain words.
    for phrase in ("Verified by the household's tax preparer on 2026-10-13, against tax year 2025 rules (not 2026)",
                   "placed in July (mid-year)", "assumed to have lived together all year",
                   "Like-kind (section 1031) exchanges", "qualified business income (QBI)", "real-estate-professional status",
                   "short-term rentals", "personal use of a dwelling unit (section 280A)", "Refinancing events",
                   "entity (LLC or partnership) ownership", "state-specific passive-loss rules", "tenant-level detail",
                   "Partial, installment and related-party sales", "once-in-two-years rule",
                   "first-pass AGI before the withdrawal cascade", "one land share", "step-up"):
        assert phrase in joined, phrase
    # Constants quoted in section G come from the reference data in force, not from the sheet.
    k = rep.constants
    assert f"${k.special_allowance:,.0f}" in joined and f"${k.phaseout_start:,.0f}" in joined
    assert f"{k.recovery_years:g} years" in joined


def test_sheet_without_properties_says_so_and_builds_nothing_else():
    c, rows = case("off")
    ws = Workbook().active
    assert build_sheet_rental(ws, c, rows) is None
    assert any("nothing to report" in t for t in texts(ws))


@pytest.mark.parametrize("name", ["standalone_loss", "profitable", "converted_passes", "sale_with_recapture"])
def test_totals_tie_to_the_engine_rows_and_to_the_properties(name):
    _ws, rep, _c, rows = rental_sheet(name)
    rr = [r for r in rows if "rental_net_cash_flow" in r]
    assert [y.year for y in rep.totals] == [r["year"] for r in rr]
    for y, r in zip(rep.totals, rr):
        assert y.gross_rent == pytest.approx(r["rental_gross_rent"])
        assert y.net_cash == pytest.approx(r["rental_net_cash_flow"])
        assert y.schedule_e == pytest.approx(r["rental_schedule_e_net"])
        assert y.schedule_e_to_agi == pytest.approx(r["rental_schedule_e_to_agi"])
        assert y.suspended == pytest.approx(r["rental_suspended_loss_carryforward"])
        assert y.depreciation == pytest.approx(r["rental_depreciation"])
        # rent collected - operating expenses - debt service - improvements and purchase cash = net cash flow
        # (a sale year may add an underwater-sale shortfall to the cash need, so it is left out here)
        if not any(p.get("sold") for p in r["rental_by_property"]):
            assert (y.collected - y.operating_expenses - y.debt_service - y.improvements_purchase) == pytest.approx(y.net_cash, abs=1.0)
    # per-property figures add up to the plan, including the Schedule E amount after the passive limit
    for attr in ("net_cash", "schedule_e", "schedule_e_to_agi", "depreciation", "gross_rent"):
        for i, y in enumerate(rep.totals):
            assert sum(getattr(lines[i], attr) for lines in rep.by_property.values()) == pytest.approx(getattr(y, attr), abs=0.01), (attr, y.year)


def test_loss_making_case_suspends_losses_and_releases_them_at_sale():
    ws, rep, _c, rows = rental_sheet("standalone_loss")
    assert rep.totals[0].schedule_e < 0 and rep.totals[0].schedule_e_to_agi == 0  # MAGI above the phase-out: nothing allowed
    assert rep.totals[0].suspended == pytest.approx(-rep.totals[0].schedule_e)
    peak = max(y.suspended for y in rep.totals)
    ledger = rep.ledger["Condo"]
    assert ledger[0].opening == 0 and ledger[0].closing == pytest.approx(rep.totals[0].suspended)
    for prev, cur in zip(ledger, ledger[1:]):  # closing carries to the next opening
        assert cur.opening == pytest.approx(prev.closing)
    sale = next(x for x in ledger if x.year == 2040)  # the fixture sells in 2040
    assert sale.closing == 0 and sale.released == pytest.approx(sale.opening + sale.current_loss)
    assert sale.released >= peak
    assert next(y for y in rep.totals if y.year == 2040).schedule_e_to_agi == pytest.approx(-(sale.opening + sale.current_loss))
    assert all(x.opening == x.closing == 0 for x in ledger if x.year > 2040)
    assert any("suspends rental losses" in w for w in rep.warnings)
    # section A stops at the last year with rental activity (the 2040 sale) and says so
    total_row = row_labeled(ws, "Plan total")
    years_listed = [ws.cell(row=r, column=1).value for r in range(max(1, total_row - 40), total_row)
                    if isinstance(ws.cell(row=r, column=1).value, int)]
    assert years_listed[-1] == 2040 and years_listed[0] == rep.totals[0].year
    assert "No rental activity after 2040; later years are not listed." in texts(ws)
    # Section D shows the MAGI the limit used and the allowance
    assert "MAGI used for the limit" in texts(ws) and "Special allowance available" in texts(ws)
    assert [p["magi"] for p in rep.passive_by_year] == [pytest.approx(r["rental_passive_magi"]) for r in rows if "rental_passive_magi" in r]


def test_profitable_case_has_taxable_income_and_sensible_metrics():
    _ws, rep, _c, _rows = rental_sheet("profitable")
    assert all(y.suspended == 0 and y.loss_allowed == 0 for y in rep.totals)
    assert all(y.schedule_e_to_agi == pytest.approx(y.schedule_e) for y in rep.totals)
    assert rep.totals[0].tax_effect > 0  # income adds tax
    (m,) = rep.metrics
    assert 0 < m.cap_rate < 0.15 and m.net_yield < m.cap_rate and m.value > 0
    assert m.reference_year == rep.totals[0].year == 2026
    assert m.noi == pytest.approx(rep.totals[0].collected - rep.totals[0].operating_expenses)
    assert m.cap_rate == pytest.approx(m.noi / m.value)
    assert m.after_tax_return is not None and 0 < m.after_tax_return < 0.5
    assert m.held_to.startswith("plan end")
    assert rep.sales == ()
    dep = rep.depreciation["Duplex"]
    assert dep[0].depreciable_basis == pytest.approx(288000.0)  # (350,000 + 10,000) x (1 - 20%)
    assert dep[-1].depreciable_basis == pytest.approx(288000.0 + 27500.0)  # the 2028 improvement joins
    assert dep[-1].accumulated <= dep[-1].depreciable_basis + 1e-6
    for d in dep:  # adjusted basis = cost 360,000 + the improvement once placed - accumulated depreciation
        assert d.adjusted_basis == pytest.approx(360000.0 + (27500.0 if d.year >= 2028 else 0.0) - d.accumulated)


def test_sale_with_recapture_splits_the_gain_into_1250_and_long_term():
    ws, rep, _c, rows = rental_sheet("sale_with_recapture")
    (sale,) = rep.sales
    assert sale.year == 2035 and not sale.converted
    assert sale.gain == pytest.approx(sale.price - sale.selling_costs - sale.adjusted_basis)
    assert sale.recapture_1250 == pytest.approx(min(sale.gain, sale.accumulated_depreciation))
    assert sale.long_term_gain == pytest.approx(sale.gain - sale.recapture_1250)
    assert sale.tax_at_sale > 0 and sale.after_tax_proceeds == pytest.approx(sale.net_proceeds - sale.tax_at_sale)
    row = next(r for r in rows if r["year"] == 2035)
    assert row["rental_sale_unrecaptured_1250_gain"] == pytest.approx(sale.recapture_1250)
    assert sale.net_proceeds == pytest.approx(row["rental_sale_net_proceeds"])
    labels = texts(ws)
    for label in ("Unrecaptured section 1250 gain (taxed at ordinary rates, 25% cap)", "Estimated tax at sale",
                  "Net proceeds after estimated tax"):
        assert label in labels
    # the property stops depreciating after the sale year
    assert rep.by_property["Duplex for sale"][-1].owned is False
    assert rep.totals[-1].depreciation == 0


@pytest.mark.parametrize("name,passes", [("converted_passes", True), ("converted_fails", False)])
def test_converted_home_reports_the_section_121_result(name, passes):
    ws, rep, _c, rows = rental_sheet(name)
    (sale,) = rep.sales
    assert sale.converted and sale.sec121_qualifies is passes
    assert ("Passes" if passes else "Fails") in texts(ws)
    row = next(r for r in rows if r["year"] == sale.year)
    assert sale.price == pytest.approx(row["home_sale_gross"]) and sale.gain == pytest.approx(row["home_sale_gain"])
    if passes:
        assert sale.sec121_excluded > 0
        # depreciation is never excluded: it is the 1250 gain, the rest is taxable gain above the exclusion
        assert sale.recapture_1250 == pytest.approx(sale.accumulated_depreciation)
        assert any("passes the two-of-five-year test" in w for w in rep.warnings)
    else:
        assert sale.sec121_excluded == 0
        assert any("fails the two-of-five-year ownership-and-use test" in w for w in rep.warnings)
    assert rep.metrics[0].after_tax_return is None and "converted home" in rep.metrics[0].held_to


def test_mfs_default_and_single_filer_notes():
    _ws, rep, _c, _rows = rental_sheet("single")
    assert rep.filing == "Single" and not any("Married filing separately is assumed" in w for w in rep.warnings)
    c, rows = case("mfs")  # fixture states the spouses lived apart, so the allowance is not zeroed
    assert rrd.build_report(c, rows).mfs_lived_apart
    c2 = rental_config("standalone_loss")
    c2["filing_status"] = "MFS"
    c2.pop("mfs_lived_apart", None)
    rows2 = project(c2)
    rep2 = rrd.build_report(c2, rows2)
    assert not rep2.mfs_lived_apart and any("Married filing separately is assumed" in w for w in rep2.warnings)


def test_outline_rows_are_collapsed_by_property():
    ws, rep, _c, _rows = rental_sheet("standalone_loss")
    hidden = [r for r, d in ws.row_dimensions.items() if d.hidden]
    assert hidden and all(ws.row_dimensions[r].outlineLevel == 1 for r in hidden)
    prop_row = row_labeled(ws, "Condo")
    assert not ws.row_dimensions[prop_row].hidden and ws.row_dimensions[prop_row + 1].hidden
    assert ws.sheet_properties.outlinePr.summaryBelow is False


def test_irr_helper():
    assert rrd.irr([-100.0, 110.0]) == pytest.approx(0.10)
    assert rrd.irr([100.0, 110.0]) is None and rrd.irr([]) is None
    assert rrd.irr([-100.0, 0.0, 121.0]) == pytest.approx(0.10)


def test_assumption_text_follows_the_filing_status_constants():
    _ws, rep, _c, _rows = rental_sheet("mfs")
    text = "\n".join(p for _h, paras in assumption_lines(rep) for p in paras)
    assert f"${rep.constants.special_allowance:,.0f}" in text


@pytest.mark.slow
def test_real_workbook_has_the_rental_sheet_only_when_the_feature_is_on(tmp_path_factory):
    off_path, on_path = built_workbooks(tmp_path_factory)
    off, on = load_workbook(off_path), load_workbook(on_path)
    assert not any("Rental" in n for n in off.sheetnames)
    (name,) = [n for n in on.sheetnames if "Rental Properties" in n]
    letters = [n for n in on.sheetnames if n[:1] == "1"]
    assert letters.index(name) == letters.index(next(n for n in letters if "Balance Sheet" in n)) + 1
    expected = json.loads((ROOT / "tests" / "fixtures" / "rental_workbook_expectations.json").read_text(encoding="utf-8"))
    body = "\n".join(texts(on[name]))
    for phrase in expected["required_phrases"]:
        assert phrase in body, f"{name} missing {phrase!r}"
    qc_ws = on[next(n for n in on.sheetnames if n.endswith("Quality Control"))]
    assert not [t for t in texts(qc_ws) if t == "FAIL"]
    # the off workbook is unchanged in shape: every historic section-1 tab keeps its letter
    assert [n for n in off.sheetnames if n[:1] == "1"] == [
        "1. Reports", "1A. Executive Summary", "1B. Net Worth", "1C. Cash Flow", "1D. Balance Sheet",
        "1E. Lifetime Taxes", "1F. Charts", "1G. Spending Summary"]
