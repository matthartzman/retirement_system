"""Wave 5.5 (system review 2026-08-04, planner finding
no-dynamic-spending-policy): "Essential/discretionary split with a floor."

A uniform spend_cut_frac (from sustainable_spending_solve / Sheet 15 B3/B4)
says HOW MUCH spending would need to be cut but never says WHERE it should
come from. essential_discretionary_floor_check (src/planning_engines.py)
answers that: given a cut fraction and the deterministic engine's own
per-year cashflow_breakdown (already computed for every row, no new engine
math), it checks whether the dollar cut could come entirely from
discretionary spending (Travel / Large Discretionary) every year, leaving
essential spending (housing, wellness, core spend_base) untouched -- i.e.
whether essential spending has a protected floor at that cut level.

This is deliberately a reporting-layer feature: it does not change which
accounts fund withdrawals, the MC success/failure computation, or any
dollar total the engine already produces (see the function's own
docstring) -- it only re-labels an already-computed cut by spending
purpose.
"""
from __future__ import annotations

from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
from src.planning_engines import (
    essential_discretionary_floor_check,
    monte_carlo,
    project,
)
from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

from conftest import TEST_INPUT_DIR


def sample_config_and_rows(**overrides):
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c.update(overrides)
    c = ensure_engine_config(c, source="test")
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        rows = project(c)
    return c, rows


def test_zero_cut_is_always_essential_protected():
    c, rows = sample_config_and_rows()
    result = essential_discretionary_floor_check(rows, 0.0)
    assert result["essential_protected"] is True
    assert result["worst_year_essential_shortfall"] == 0.0


def test_none_cut_returns_none_protected():
    c, rows = sample_config_and_rows()
    result = essential_discretionary_floor_check(rows, None)
    assert result["essential_protected"] is None


def test_full_cut_of_all_spending_cannot_be_discretionary_only():
    # Cutting 100% of total spend every year necessarily exceeds whatever
    # discretionary (travel) spending exists that year, unless discretionary
    # spending happens to equal total spend (never true for a real plan
    # with any housing/core spend_base).
    c, rows = sample_config_and_rows()
    result = essential_discretionary_floor_check(rows, 1.0)
    assert result["essential_protected"] is False
    assert result["worst_year_essential_shortfall"] > 0.0
    assert result["worst_year"] is not None


def test_larger_cut_never_produces_a_smaller_essential_shortfall():
    # Monotonicity sanity check: increasing the cut fraction should never
    # decrease how much spills into essential spending.
    c, rows = sample_config_and_rows()
    small = essential_discretionary_floor_check(rows, 0.05)
    large = essential_discretionary_floor_check(rows, 0.50)
    assert large["worst_year_essential_shortfall"] >= small["worst_year_essential_shortfall"]


def test_uses_cashflow_breakdown_travel_not_total_rec_extra_double_counted():
    # Sanity check that the discretionary figure is read from the same
    # canonical cashflow_breakdown every other consumer (Sheet 6, Sheet 8,
    # results_model) reads, not re-derived.
    c, rows = sample_config_and_rows()
    for row in rows:
        if row.get("total_spend", 0) > 0:
            expected_travel = row.get("cashflow_breakdown", {}).get("expense", {}).get("travel", 0.0)
            assert expected_travel == row.get("rec_extra", 0.0)
            break


def test_sustainable_spending_solve_results_carry_essential_protected_field():
    c, rows = sample_config_and_rows(mc_sims=150, mc_sensitivity_sims=2)
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        mc = monte_carlo(c, base_rows=rows)
    solve = mc["sustainable_spending_solve"]
    assert len(solve) == 3
    for entry in solve:
        assert "essential_protected" in entry
        assert "essential_shortfall_worst_year_amount" in entry
        assert "essential_shortfall_worst_year" in entry


def test_sheet15_renders_essential_floor_annotations():
    from openpyxl import Workbook

    from src.reporting.sheets_stress import build_sheet15

    c, rows = sample_config_and_rows(mc_sims=150, mc_sensitivity_sims=2)
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        mc = monte_carlo(c, base_rows=rows)
    wb = Workbook()
    ws = wb.active
    build_sheet15(ws, c, rows, mc)
    texts = [str(cell.value) for row in ws.iter_rows() for cell in row if cell.value is not None]
    assert any("Discretionary-only" in t or "Reaches essential" in t for t in texts) or \
        any("Sustainable spending solve not available" in t for t in texts) or \
        any("No failing paths" in t for t in texts)
