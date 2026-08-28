"""Optimization-refactor Phase 4: LCV (Lifetime Consumption-and-Transfer
Value) scoring and feasibility gate, per docs/superpowers/plans/2026-08-27-
phase4-lcv-feasibility-gate-spec.md's Option C (full sign-off: LCV replaces
the Roth optimizer's and SS claim-age sweep's terminal-wealth basis
entirely, both optimizers together, hard-exclude gate, essential tier only
at a 95% probability floor).

LCV = PV(lifetime consumption) + PV(after-tax terminal transfer), same
discount convention _roth_strategy_metrics already used for lifetime_tax.
The feasibility gate reuses essential_fully_funded_probability (Phase 2)
via a small Monte Carlo run per candidate -- for the Roth optimizer this is
a NEW per-candidate MC run (survivor buckets built once from the base
config and reused, mirroring the SS sweep's own established, CI-timeout-
motivated safe pattern); for the SS claim-age sweep this reuses the MC run
that already existed there, purely informationally, before this change.
"""
from __future__ import annotations

import pytest

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
import src.planning_engines as planning_engines
from src.planning_engines import (
    LCV_FEASIBILITY_GATE_THRESHOLD,
    _roth_discount_rate,
    _roth_strategy_metrics,
    optimize_roth_conversion_strategy,
    project,
)


def _base_config():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["plan_end"] = min(int(c["plan_end"]), int(c["plan_start"]) + 10)
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    return c


def test_lcv_score_equals_consumption_pv_plus_terminal_pv():
    c = _base_config()
    rows = project(c)
    result = _roth_strategy_metrics(c, rows)

    discount = _roth_discount_rate(c)
    plan_start = int(c["plan_start"])
    expected_consumption_pv = sum(
        float(r.get("total_spend", 0.0) or 0.0) / ((1.0 + discount) ** max(0, int(r["year"]) - plan_start))
        for r in rows
    )
    terminal_year = int(rows[-1]["year"])
    expected_terminal_pv = result["after_tax_terminal_nw"] / ((1.0 + discount) ** (terminal_year - plan_start))

    assert result["consumption_pv"] == pytest.approx(expected_consumption_pv, rel=1e-9)
    assert result["lcv_score"] == pytest.approx(expected_consumption_pv + expected_terminal_pv, rel=1e-9)
    assert result["consumption_pv"] > 0


def test_lcv_score_used_across_objective_modes_not_just_default():
    # MINIMIZE_LIFETIME_TAX uses a 0.10 terminal weight (vs BALANCED_
    # RETIREMENT's default terminal_weight config, typically 1.0) -- confirm
    # the LCV substitution applies inside every mode branch, not just the
    # pre-branch default that a single-mode test could miss.
    c = _base_config()
    rows = project(c)
    c["roth_objective_mode"] = "MINIMIZE_LIFETIME_TAX"
    result = _roth_strategy_metrics(c, rows)
    assert result["terminal_wealth_score"] == pytest.approx(0.10 * result["lcv_score"], rel=1e-9)

    c["roth_objective_mode"] = "MAXIMIZE_TERMINAL_NET_WORTH"
    result2 = _roth_strategy_metrics(c, rows)
    assert result2["terminal_wealth_score"] == pytest.approx(1.25 * result2["lcv_score"], rel=1e-9)


def test_empty_rows_returns_zero_lcv_fields_not_a_crash():
    result = _roth_strategy_metrics({}, [])
    assert result["consumption_pv"] == 0.0
    assert result["lcv_score"] == 0.0


def test_roth_candidates_carry_feasibility_fields_in_valid_range():
    c = _base_config()
    c["roth_bracket_strategy"] = "FILL_TARGET_BRACKET"  # small candidate set (4), keeps the test fast
    c = optimize_roth_conversion_strategy(c)
    candidates = c["roth_optimization"]["candidates"]
    assert len(candidates) >= 2
    for cand in candidates:
        assert "feasibility_probability" in cand
        assert "feasibility_gate_met" in cand
        assert 0.0 <= cand["feasibility_probability"] <= 1.0
        assert cand["feasibility_gate_met"] == (cand["feasibility_probability"] >= LCV_FEASIBILITY_GATE_THRESHOLD)
        assert "lcv_score" in cand and "consumption_pv" in cand


def test_selection_never_picks_a_candidate_that_fails_the_feasibility_gate(monkeypatch):
    # Force an impossible threshold so every candidate fails the gate, then
    # confirm the fallback (rank the full set, flag all_candidates_infeasible)
    # engages instead of crashing or silently picking an infeasible winner
    # with no flag raised.
    monkeypatch.setattr(planning_engines, "LCV_FEASIBILITY_GATE_THRESHOLD", 1.01)
    c = _base_config()
    c["roth_bracket_strategy"] = "FILL_TARGET_BRACKET"
    c = optimize_roth_conversion_strategy(c)
    opt = c["roth_optimization"]
    assert opt["all_candidates_infeasible"] is True
    assert all(not cand["feasibility_gate_met"] for cand in opt["candidates"])
    # A recommendation must still be produced (the best-scoring candidate by
    # LCV/tax/etc., same as pre-Phase-4 behavior) rather than nothing at all.
    assert opt["selected_policy"]


def test_trivial_threshold_never_flags_all_candidates_infeasible(monkeypatch):
    monkeypatch.setattr(planning_engines, "LCV_FEASIBILITY_GATE_THRESHOLD", 0.0)
    c = _base_config()
    c["roth_bracket_strategy"] = "FILL_TARGET_BRACKET"
    c = optimize_roth_conversion_strategy(c)
    opt = c["roth_optimization"]
    assert opt["all_candidates_infeasible"] is False
    assert all(cand["feasibility_gate_met"] for cand in opt["candidates"])


def test_feasibility_gate_threshold_reported_on_roth_optimization():
    c = _base_config()
    c["roth_bracket_strategy"] = "FILL_TARGET_BRACKET"
    c = optimize_roth_conversion_strategy(c)
    assert c["roth_optimization"]["feasibility_gate_threshold"] == LCV_FEASIBILITY_GATE_THRESHOLD
