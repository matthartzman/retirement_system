"""Tests for the two new Sharpe-ratio-driven allocation modes added to
src/optimization.py and src/allocation_policy.py:

    - "max_sharpe": risk-budgeted -- same equity_pct/bond/cash/coverage
      machinery as "optimizer_recommendation", but the equity sleeve is
      chosen to maximize the sleeve's own Sharpe ratio instead of the fixed
      risk-aversion utility.
    - "tangency": pure tangency -- the single long-only, max-Sharpe portfolio
      across all enabled liquid asset classes, with no risk-tolerance
      ceiling, glide path, or guaranteed-income/home-equity coverage
      overlay.

Uses the repo's sample client_data.csv fixture the same way
tests/test_183_efficient_frontier_sharpe.py does, so eligibility/inclusion
logic reflects a realistic household rather than a hand-built stub.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import src.allocation_policy as ap
import src.optimization as opt
from src.data_io import load_csv, parse_client

ROOT = Path(__file__).resolve().parents[1]


def sample_config():
    data = load_csv(ROOT / "input" / "client_data.csv")
    return parse_client(data, "")


# ---------------------------------------------------------------------------
# normalize_allocation_mode / allocation_mode_label
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["max_sharpe", "Max Sharpe", "sharpe", "sharpe_optimal", "max-sharpe-ratio"])
def test_normalize_allocation_mode_recognizes_max_sharpe_aliases(raw):
    assert ap.normalize_allocation_mode(raw) == ap.ALLOCATION_MODE_MAX_SHARPE


@pytest.mark.parametrize("raw", ["tangency", "Tangency", "pure_tangency", "tangency portfolio", "unconstrained-sharpe"])
def test_normalize_allocation_mode_recognizes_tangency_aliases(raw):
    assert ap.normalize_allocation_mode(raw) == ap.ALLOCATION_MODE_TANGENCY


def test_allocation_mode_choices_include_all_four_modes():
    assert set(ap.ALLOCATION_MODE_CHOICES) == {
        ap.ALLOCATION_MODE_USER,
        ap.ALLOCATION_MODE_OPTIMIZER,
        ap.ALLOCATION_MODE_MAX_SHARPE,
        ap.ALLOCATION_MODE_TANGENCY,
    }


def test_allocation_mode_labels_are_distinct_and_non_empty():
    labels = [ap.allocation_mode_label(m) for m in ap.ALLOCATION_MODE_CHOICES]
    assert all(labels)
    assert len(set(labels)) == len(labels)


# ---------------------------------------------------------------------------
# optimize_equity_sleeve(objective_mode='max_sharpe')
# ---------------------------------------------------------------------------


def test_optimize_equity_sleeve_max_sharpe_weights_are_long_only_and_sum_to_one():
    classes = ["US Large Cap", "US Small Cap", "International", "Emerging Markets", "Commodities"]
    weights = opt.optimize_equity_sleeve(
        100_000.0, classes, objective_mode="max_sharpe", rf=0.02,
    )
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)
    for w in weights.values():
        assert w >= -1e-9


def test_optimize_equity_sleeve_max_sharpe_respects_class_caps():
    # Enough classes that the combined caps exceed 100% (no proportional
    # relaxation needed), so EQUITY_SLEEVE_CLASS_CAPS's 20% Emerging Markets
    # cap is actually binding rather than rescaled up for feasibility.
    classes = ["US Large Cap", "US Mid Cap", "US Small Cap", "International", "Emerging Markets"]
    weights = opt.optimize_equity_sleeve(
        100_000.0, classes, objective_mode="max_sharpe", rf=0.02,
    )
    assert weights.get("Emerging Markets", 0.0) <= 0.20 + 1e-6


def test_optimize_equity_sleeve_default_objective_mode_unchanged():
    # Additive-only guard: default (mean_variance) call signature/behavior
    # must be identical to before the objective_mode parameter was added.
    classes = ["US Large Cap", "US Small Cap", "International"]
    weights = opt.optimize_equity_sleeve(100_000.0, classes)
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# compute_optimal_allocation -- max_sharpe (risk-budgeted)
# ---------------------------------------------------------------------------


def test_max_sharpe_liquid_targets_sum_to_one_and_are_long_only():
    c = sample_config()
    res = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_MAX_SHARPE)
    lt = res["liquid_targets"]
    assert sum(lt.values()) == pytest.approx(1.0, abs=1e-6)
    for w in lt.values():
        assert w >= -1e-9


def test_max_sharpe_preserves_optimizer_recommendation_equity_pct():
    c = sample_config()
    optimizer = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)
    max_sharpe = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_MAX_SHARPE)
    # Risk-budgeted: same risk level (equity_pct), different sleeve composition.
    assert max_sharpe["equity_pct"] == pytest.approx(optimizer["equity_pct"], abs=1e-6)


def test_max_sharpe_sleeve_sharpe_at_least_as_good_as_optimizer_recommendation():
    c = sample_config()
    optimizer_stats = opt.allocation_portfolio_stats(c, force_mode=ap.ALLOCATION_MODE_OPTIMIZER)
    max_sharpe_stats = opt.allocation_portfolio_stats(c, force_mode=ap.ALLOCATION_MODE_MAX_SHARPE)
    assert max_sharpe_stats["sharpe"] >= optimizer_stats["sharpe"] - 1e-6


def test_max_sharpe_diagnostics_labeled_distinctly_from_optimizer():
    c = sample_config()
    res = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_MAX_SHARPE)
    assert res["diagnostics"]["allocation_policy_mode"] == "max_sharpe_recommendation"
    assert res["diagnostics"]["allocation_selection_mode"] == ap.ALLOCATION_MODE_MAX_SHARPE


def test_max_sharpe_sleeve_excludes_reits_and_alternatives():
    # Same rationale as tangency: guaranteed income/home equity already
    # cover the fixed-income/real-estate role, so the equity sleeve's own
    # Sharpe objective is scoped to growth + commodities only, unlike the
    # optimizer-recommendation sleeve which also considers REITs/Managed
    # Futures/Private Credit.
    c = sample_config()
    res = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_MAX_SHARPE)
    for cls in ("REITs", "Managed Futures", "Private Credit"):
        assert res["liquid_targets"].get(cls, 0.0) < 1e-6


# ---------------------------------------------------------------------------
# compute_optimal_allocation -- tangency (pure)
# ---------------------------------------------------------------------------


def test_tangency_liquid_targets_sum_to_one_and_are_long_only():
    c = sample_config()
    res = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_TANGENCY)
    lt = res["liquid_targets"]
    assert sum(lt.values()) == pytest.approx(1.0, abs=1e-6)
    for w in lt.values():
        assert w >= -1e-9


def test_tangency_uses_only_equity_and_commodities_classes():
    # Bonds/REITs/cash/alternatives are excluded by design: guaranteed
    # income and home equity already fill that role elsewhere in this
    # household's allocation, so Sharpe optimization is scoped to the
    # liquid growth dollars (see SHARPE_EQUITY_CLASSES).
    c = sample_config()
    res = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_TANGENCY)
    for cls, wt in res["liquid_targets"].items():
        if wt > 1e-6:
            assert cls in opt.SHARPE_EQUITY_CLASSES, f"{cls} should not receive weight in tangency mode"


def test_tangency_sharpe_at_least_as_good_as_any_single_class_in_its_universe():
    # A well-formed max-Sharpe/tangency solve should never be beaten by
    # holding just one asset from its own candidate universe, since a
    # single-asset allocation is itself a feasible (corner) point of the
    # same optimization.
    c = sample_config()
    tangency_stats = opt.allocation_portfolio_stats(c, force_mode=ap.ALLOCATION_MODE_TANGENCY)
    for cls in opt.SHARPE_EQUITY_CLASSES:
        if not opt.allocation_class_enabled(c, cls):
            continue
        single_stats = opt.portfolio_stats_from_weights(c, {cls: 1.0})
        assert tangency_stats["sharpe"] >= single_stats["sharpe"] - 1e-4


def test_tangency_ignores_risk_tolerance_and_glide_path():
    c1 = sample_config()
    c1["risk_tolerance"] = 1
    c2 = sample_config()
    c2["risk_tolerance"] = 10
    res1 = opt.compute_optimal_allocation(c1, force_mode=ap.ALLOCATION_MODE_TANGENCY)
    res2 = opt.compute_optimal_allocation(c2, force_mode=ap.ALLOCATION_MODE_TANGENCY)
    # Pure tangency should not depend on risk_tolerance at all (no risk budget).
    for cls in opt.ASSET_CLASSES:
        assert res1["liquid_targets"].get(cls, 0.0) == pytest.approx(
            res2["liquid_targets"].get(cls, 0.0), abs=1e-6
        )


def test_tangency_respects_user_class_overrides():
    c = sample_config()
    c["asset_class_overrides"] = dict(c.get("asset_class_overrides") or {})
    c["asset_class_overrides"]["US Large Cap"] = {"max_target": 0.10}
    res = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_TANGENCY)
    assert res["liquid_targets"].get("US Large Cap", 0.0) <= 0.10 + 1e-6


def test_tangency_degenerate_single_class_falls_back_gracefully():
    c = sample_config()
    enabled = {cls: False for cls in opt.ASSET_CLASSES}
    enabled["US Large Cap"] = True
    c["asset_class_enabled"] = enabled
    res = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_TANGENCY)
    assert res["liquid_targets"] == {"US Large Cap": 1.0}


def test_tangency_diagnostics_labeled_and_carries_risk_free_rate():
    c = sample_config()
    res = opt.compute_optimal_allocation(c, force_mode=ap.ALLOCATION_MODE_TANGENCY)
    assert res["diagnostics"]["allocation_policy_mode"] == "tangency_portfolio"
    assert res["diagnostics"]["allocation_selection_mode"] == ap.ALLOCATION_MODE_TANGENCY
    assert res["diagnostics"]["risk_free_rate"] == pytest.approx(opt.risk_free_rate(c), abs=1e-9)


# ---------------------------------------------------------------------------
# Additive-only guard: existing modes are untouched
# ---------------------------------------------------------------------------


def test_user_target_and_optimizer_recommendation_still_work_after_new_modes():
    c = sample_config()
    for mode in (ap.ALLOCATION_MODE_USER, ap.ALLOCATION_MODE_OPTIMIZER):
        res = opt.compute_optimal_allocation(c, force_mode=mode)
        assert sum(res["liquid_targets"].values()) == pytest.approx(1.0, abs=1e-6)


def test_allocation_portfolio_stats_works_for_both_new_modes():
    c = sample_config()
    for mode in (ap.ALLOCATION_MODE_MAX_SHARPE, ap.ALLOCATION_MODE_TANGENCY):
        stats = opt.allocation_portfolio_stats(c, force_mode=mode)
        assert "sharpe" in stats
        assert stats["sharpe"] == stats["sharpe"]  # not NaN
        assert abs(stats["sharpe"]) < float("inf")
