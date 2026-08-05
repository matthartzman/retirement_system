"""Wave 5.1 (system review 2026-08-04, planner finding
no-sustainable-spending-solve): "What's the most I can sustainably spend?"
is the planner's most common client question, and the machinery to answer
it already existed as a per-path diagnostic (_mc_required_cut_distribution,
P13 phase 1) -- this reuses the same binary-search primitive
(_mc_vectorized_projection's spend_cut_frac) at the whole-batch level,
bisecting toward a target OVERALL success rate instead of a per-path rescue
cut, for three confidence levels (95%/85%/75% by default).
"""
from __future__ import annotations

from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
from src.planning_engines import (
    _mc_vectorized_batch,
    monte_carlo,
    project,
    sustainable_spending_solve,
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


def test_monte_carlo_populates_sustainable_spending_solve():
    c, rows = sample_config_and_rows(mc_sims=150, mc_sensitivity_sims=2)
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        mc = monte_carlo(c, base_rows=rows)
    solve = mc["sustainable_spending_solve"]
    assert len(solve) == 3
    assert [round(r["target_success_rate"], 2) for r in solve] == [0.95, 0.85, 0.75]


def test_higher_target_never_implies_more_spending():
    # Monotonicity: a stricter (higher) success-rate target must never imply
    # a HIGHER sustainable spend than a looser target.
    c, rows = sample_config_and_rows(mc_sims=150, mc_sensitivity_sims=2)
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        mc = monte_carlo(c, base_rows=rows)
    solve = sorted(mc["sustainable_spending_solve"], key=lambda r: r["target_success_rate"])
    spends = [r["sustainable_spend_base"] for r in solve]
    assert spends == sorted(spends, reverse=True), "higher success target should never allow more spending"


def test_achieved_success_rate_matches_target_within_tolerance():
    c, rows = sample_config_and_rows(mc_sims=150, mc_sensitivity_sims=2)
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        mc = monte_carlo(c, base_rows=rows)
    for r in mc["sustainable_spending_solve"]:
        if r["feasible"]:
            assert r["achieved_success_rate"] >= r["target_success_rate"] - 0.02


def test_zero_cut_when_current_spending_already_clears_a_low_target():
    c, rows = sample_config_and_rows()
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        batch = _mc_vectorized_batch(c, rows, 150, 42, c.get("ret", 0.06), c.get("mc_sigma", 0.12), 0.0, use_asset_classes=True)
        result = sustainable_spending_solve(c, rows, batch, 0.0, targets=(0.01,))
    assert result[0]["required_cut"] == 0.0
    assert result[0]["sustainable_spend_base"] == c["spend_base"]


def test_infeasible_target_reports_best_achievable_not_a_false_answer():
    c, rows = sample_config_and_rows()
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        batch = _mc_vectorized_batch(c, rows, 150, 42, c.get("ret", 0.06), c.get("mc_sigma", 0.12), 0.0, use_asset_classes=True)
        # A wildly high liquid floor makes even a near-total spending cut
        # infeasible for a 99.9% success target.
        result = sustainable_spending_solve(c, rows, batch, 1e12, targets=(0.999,), cut_cap=0.90)
    assert result[0]["feasible"] is False
    assert result[0]["required_cut"] == 0.90


def test_sheet15_renders_sustainable_spending_section():
    from openpyxl import Workbook
    from src.reporting.sheets_stress import build_sheet15

    c, rows = sample_config_and_rows(mc_sims=150, mc_sensitivity_sims=2)
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        mc = monte_carlo(c, base_rows=rows)
        wb = Workbook()
        ws = wb.active
        build_sheet15(ws, c, rows, mc)
    text = [str(cell.value) for row in ws.iter_rows() for cell in row if cell.value is not None]
    assert any("Sustainable Spending" in t for t in text)
