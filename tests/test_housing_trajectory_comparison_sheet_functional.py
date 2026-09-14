"""Housing Trajectory Comparison sheet (Slice 3, H7/H11a) --
docs/superpowers/plans/2026-09-09-housing-estimate-realism-and-dollar-
convention-design.md, §7.0.

Covers registration/gating (same pattern as
tests/test_advanced_planning_modules.py's
test_module_is_registered_for_gating_and_rename -- fast, no subprocess
workbook build) and the sheet builder itself against the frozen sample plan
fixture, which has a real Housing Step 1 purchase configured (see
test_cashflow_chart_home_purchase_down_payment.py's docstring).
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from src.data_io import load_csv, parse_client
from src.module_catalog import OPTIONAL_MODULE_SHEETS, module_enabled
from src.plan_config import ensure_engine_config
from src.planning_engines import project
from src.reporting.sheets_strategy import build_sheet_housing_comparison
from src.reporting.workbook_common import SHEET_LETTER_ORDER, compute_final_sheet_renames

from conftest import TEST_INPUT_DIR
from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

ROOT = Path(__file__).resolve().parents[1]

TOGGLE = "housing_trajectory_comparison"
LEGACY_SHEET = "38. Housing Comparison"
_FAST_MC_SIMS = 8


def _config_and_rows():
    c = ensure_engine_config(parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), ""), source="test")
    c['mc_sims'] = _FAST_MC_SIMS
    c['mc_sensitivity_sims'] = 1
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        rows = project(c)
    return c, rows


def test_module_is_registered_for_gating_and_rename():
    assert OPTIONAL_MODULE_SHEETS.get(TOGGLE) == [LEGACY_SHEET], \
        f"{TOGGLE} not registered to {LEGACY_SHEET} in OPTIONAL_MODULE_SHEETS"
    wb = Workbook()
    for ordered in SHEET_LETTER_ORDER.values():
        for stable in ordered:
            wb.create_sheet(stable)
    renames = compute_final_sheet_renames(wb)
    assert LEGACY_SHEET in renames, f"{LEGACY_SHEET} not present in the final workbook layout"


def test_module_enabled_toggle_gates_the_sheet():
    # Same {"opt": {...}} shape module_catalog._base_enabled reads off a
    # parsed plan config -- mirrors how client_optional_functions.csv toggles
    # surface on c['opt'] after data_io.parse_client.
    c_on = {"opt": {TOGGLE: True}}
    c_off = {"opt": {TOGGLE: False}}
    assert module_enabled(c_on, TOGGLE) is True
    assert module_enabled(c_off, TOGGLE) is False


def test_builder_runs_without_error_and_shows_both_candidates():
    c, rows = _config_and_rows()
    ws = Workbook().create_sheet("t")
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        build_sheet_housing_comparison(ws, c, rows)
    assert ws.max_row >= 5
    values = [cell.value for row in ws.iter_rows() for cell in row if cell.value is not None]
    text = " ".join(str(v) for v in values)
    assert "Configured" in text
    assert "Alternative" in text
    # The configured Step 1 is a purchase (frozen fixture); the opposite-type
    # row must show the flipped type.
    assert "Purchase" in text
    assert "Rent" in text


def test_builder_handles_no_configured_step1_gracefully():
    c = {"plan_start": 2026, "next_housing_steps": []}
    ws = Workbook().create_sheet("e")
    build_sheet_housing_comparison(ws, c, [])
    assert ws.max_row >= 1
    values = [cell.value for row in ws.iter_rows() for cell in row if cell.value is not None]
    text = " ".join(str(v) for v in values)
    assert "nothing to compare" in text.lower()
