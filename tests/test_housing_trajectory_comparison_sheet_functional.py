"""Housing Comparison sheet (Slice 4, H11) --
docs/superpowers/plans/2026-09-09-housing-estimate-realism-and-dollar-
convention-design.md, §4.5.

Covers registration/gating (same pattern as
tests/test_advanced_planning_modules.py's
test_module_is_registered_for_gating_and_rename -- fast, no subprocess
workbook build) and the sheet builder itself against the frozen sample plan
fixture, which has a real Housing Step 1 purchase configured (see
test_cashflow_chart_home_purchase_down_payment.py's docstring).

Slice 3's two-row "Configured vs. Alternative" assertions are superseded here:
the same registry entry, same builder function and same signature now render
the recommended-trajectory block, the refine-pass table with §4.5's exact
column shape, the three per-axis sensitivity mini-tables, and the
methodology/real-vs-modeled disclosure. Full-workbook subprocess builds with
this module on and off are covered by the module matrix in
tests/test_all_modules_off_build_functional.py, which enumerates
module_catalog.optional_keys() rather than a hand-maintained list, so this
module is swept there automatically; one direct on/off build is repeated here
because this sheet is the workbook's most expensive and its cost has to be
proven survivable inside a real build, not only in-process.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
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

REFINE_TABLE_HEADERS = [
    'Rank', 'Sale Year', 'Step 1 (Type / Year)', 'Step 2 (Type / Year)', 'Score (0-100)',
    'Objective Value', 'After-Tax Terminal NW', 'LCV', 'Δ LCV', 'NPV of Future Taxes',
    'Equity at Plan End', 'Feasibility Gate Met', 'Worst-Case Ending Wealth (5th %ile)',
]


@pytest.fixture(scope="module")
def built_sheet():
    c = ensure_engine_config(parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), ""), source="test")
    c['mc_sims'] = _FAST_MC_SIMS
    c['mc_sensitivity_sims'] = 1
    c['housing_sweep_mc_sims'] = _FAST_MC_SIMS
    ws = Workbook().create_sheet("t")
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        rows = project(c)
        result = build_sheet_housing_comparison(ws, c, rows)
    return ws, result


def _cell_text(ws) -> str:
    return " ".join(
        str(cell.value) for row in ws.iter_rows() for cell in row if cell.value is not None
    )


def _row_values(ws, wanted: list[str]):
    """The row whose leading cells are exactly `wanted`, as a list of values."""
    for row in ws.iter_rows():
        values = [cell.value for cell in row]
        if values[:len(wanted)] == wanted:
            return values
    return None


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


# @pytest.mark.nightly: engine-internals-only equivalence/sweep-breadth
# check identified in the 2026-09-15 CI-time profiling (see
# documentation/reference/TESTING_REFACTOR_RECOMMENDATIONS.md); cannot be
# triggered by an ordinary UI/config change, so it moved off the PR fast
# tier and runs in the nightly full-suite workflow instead.
@pytest.mark.nightly
def test_refine_table_uses_the_designs_exact_column_shape(built_sheet):
    ws, _result = built_sheet
    assert _row_values(ws, REFINE_TABLE_HEADERS) is not None, \
        f"§4.5's refine-pass column shape not found; sheet text was: {_cell_text(ws)[:2000]}"


def test_recommended_trajectory_block_names_all_three_axes(built_sheet):
    ws, result = built_sheet
    text = _cell_text(ws)
    assert 'Recommended housing trajectory' in text
    for label in ('Recommended Current-Home Sale Year', 'Recommended Housing Step 1',
                  'Recommended Housing Step 2', 'Currently Configured Trajectory'):
        assert label in text
    # The recommendation rendered is the refine pass's own winner.
    assert result['recommended'] in result['refine_candidates']


def test_every_refine_candidate_is_rendered_as_a_ranked_row(built_sheet):
    ws, result = built_sheet
    header_row = None
    for row in ws.iter_rows():
        if [cell.value for cell in row][:len(REFINE_TABLE_HEADERS)] == REFINE_TABLE_HEADERS:
            header_row = row[0].row
            break
    ranks = []
    for offset in range(1, len(result['refine_candidates']) + 1):
        ranks.append(ws.cell(row=header_row + offset, column=1).value)
    assert ranks == list(range(1, len(result['refine_candidates']) + 1))


def test_three_per_axis_sensitivity_tables_are_rendered(built_sheet):
    ws, result = built_sheet
    text = _cell_text(ws)
    assert 'Per-axis sensitivity of the coarse pass' in text
    for label in ('Current-home sale year', 'Housing Step 1 (type / year)',
                  'Housing Step 2 (type / year)'):
        assert label in text, f"missing sensitivity mini-table for {label}"
    # Sourced from the winning ordering's coarse pass, with every axis point on
    # display (§4.5 item 3) -- and nothing extra run to produce them.
    for axis, values in result['axes'].items():
        assert len(result['winning_order']['axis_candidates'][axis]) == len(values)


def test_disclosure_states_two_orderings_and_the_real_vs_modeled_split(built_sheet):
    ws, _result = built_sheet
    text = _cell_text(ws)
    lowered = text.lower()
    # §4.2 point 4: say plainly that two axis orderings were tried and the
    # better kept -- not just "coarse then refine".
    assert 'coordinate-descent' in lowered
    assert 'twice' in lowered and 'two different axis orderings' in lowered
    # §4.3: the per-cell real-vs-modeled distinction, including the points the
    # coarse pass visited and discarded.
    assert 'synthesized' in lowered
    assert 'visited and discarded' in lowered
    assert 'not swept in this version' in lowered


def test_builder_handles_no_configured_step1_gracefully():
    c = {"plan_start": 2026, "next_housing_steps": []}
    ws = Workbook().create_sheet("e")
    assert build_sheet_housing_comparison(ws, c, []) is None
    assert ws.max_row >= 1
    assert "nothing to compare" in _cell_text(ws).lower()


def _build_workbook(tmp_path_factory, *, enabled: bool):
    out_dir = tmp_path_factory.mktemp(f"housing_sweep_{'on' if enabled else 'off'}")
    env = os.environ.copy()
    env["RETIREMENT_SYSTEM_OUTPUT_DIR"] = str(out_dir)
    env["RETIREMENT_SYSTEM_APP_MODE"] = "LOCAL"
    env["RETIREMENT_SYSTEM_WORKSPACE_ID"] = "local"
    env["RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS"] = "1"
    env["RETIREMENT_MC_SIMS"] = "16"
    env["RETIREMENT_MC_SENSITIVITY_SIMS"] = "3"
    for key in ("RETIREMENT_SYSTEM_FORCE_ALL_MODULES",
                "RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES",
                "RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES"):
        env.pop(key, None)
    env["RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES" if enabled
        else "RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES"] = TOGGLE
    result = subprocess.run(
        [sys.executable, "tools/build_workbook.py"],
        cwd=ROOT, env=env, text=True, capture_output=True, timeout=600,
    )
    return out_dir, result


@pytest.mark.slow
@pytest.mark.parametrize("enabled", [True, False])
def test_full_workbook_build_succeeds_with_the_module_on_and_off(tmp_path_factory, enabled):
    out_dir, result = _build_workbook(tmp_path_factory, enabled=enabled)
    tail = (result.stdout + result.stderr)[-4000:]
    assert result.returncode == 0, f"build with {TOGGLE}={enabled} failed:\n{tail}"
    assert (out_dir / "retirement_plan.xlsx").exists()
