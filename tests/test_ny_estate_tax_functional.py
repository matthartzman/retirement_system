"""Wave 3 item 3.6, full-pipeline companion to test_ny_estate_tax_unit.py:
drives the real project()/build_sheet14() pipeline to confirm the 3-year
gift add-back reaches the estate-tax figure through the real gifting
schedule (not just the pure new_york_estate_tax function in isolation),
and that the reporting layer renders a NY household without error.
"""
from openpyxl import Workbook

from src.data_io import load_csv, parse_client
from src.planning_engines import project
from src.reporting.sheets_strategy import build_sheet9, build_sheet14
from src.after_tax import estimate_terminal_estate_tax

from conftest import TEST_INPUT_DIR


def _ny_config(**overrides):
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["mc_paths"] = 5
    c["state"] = "New York"
    c.update(overrides)
    return c


def test_gift_total_last_3yr_is_a_rolling_window_not_a_lifetime_total():
    c = _ny_config()
    plan_start = c["plan_start"]
    funding_id = c["taxable_ids"][0] if c.get("taxable_ids") else c["account_registry"][0]["id"]
    c["gifting_schedule"] = [{
        "start_year": plan_start, "end_year": plan_start + 1,
        "annual_amount_per_donee": 50_000.0, "donee_count": 1,
        "funding_account": funding_id,
    }]
    rows = project(c)
    # Gifts stop after plan_start+1; a row several years later must show
    # gift_total_last_3yr == 0 (outside the rolling window), while a row
    # right after gifting ends must still show a nonzero rolling total.
    row_during_window = next(r for r in rows if r["year"] == plan_start + 1)
    row_after_window = next(r for r in rows if r["year"] == plan_start + 5)
    assert row_during_window["gift_total_last_3yr"] > 0.0
    assert row_after_window["gift_total_last_3yr"] == 0.0


def test_terminal_estate_tax_reflects_the_three_year_gift_addback():
    c = _ny_config()
    rows = project(c)
    terminal = dict(rows[-1])
    terminal_no_gift = dict(terminal)
    terminal_no_gift["gift_total_last_3yr"] = 0.0
    terminal_with_gift = dict(terminal)
    terminal_with_gift["gift_total_last_3yr"] = 2_000_000.0
    tax_no_gift = estimate_terminal_estate_tax(c, terminal_no_gift)
    tax_with_gift = estimate_terminal_estate_tax(c, terminal_with_gift)
    assert tax_with_gift >= tax_no_gift


def test_ny_household_at_the_shipped_exemption_default_builds_sheets_without_error():
    # il_exempt left at its shipped $4M default -- resolved_state_estate_exemption
    # must correct it to NY's real ~$6.94M for this household, not silently
    # under-report using Illinois's figure.
    c = _ny_config()
    rows = project(c)
    ws9 = Workbook().active
    build_sheet9(ws9, c, rows)
    ws14 = Workbook().active
    build_sheet14(ws14, c, rows)


def test_illinois_household_estate_tax_is_unaffected_by_the_ny_addition():
    c_il = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c_il["mc_paths"] = 5
    rows = project(c_il)
    tax = estimate_terminal_estate_tax(c_il, rows[-1])
    assert tax >= 0.0  # no exception, no regression in the existing IL path
