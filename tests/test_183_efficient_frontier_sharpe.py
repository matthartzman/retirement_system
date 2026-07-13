"""Tests for the efficient-frontier and Sharpe-ratio portfolio-analytics
additions to src/optimization.py:

    - efficient_frontier(c, n_points=20, force_mode=None)
    - risk_free_rate(c)
    - sharpe_ratio(expected_return, volatility, rf)
    - allocation_portfolio_stats(c, force_mode=None)['sharpe']

Uses the repo's sample client_data.csv fixture the same way
tests/test_optimization_module.py and
tests/test_13_allocation_table_and_load_path.py build their config, so
eligibility/inclusion logic (allocation_class_enabled, disabled classes,
covered-by-existing-asset exclusions, etc.) reflects a realistic household
rather than a hand-built stub.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import src.optimization as opt
from src.data_io import load_csv, parse_client

ROOT = Path(__file__).resolve().parents[1]


def sample_config():
    data = load_csv(ROOT / "input" / "client_data.csv")
    return parse_client(data, "")


# ---------------------------------------------------------------------------
# sharpe_ratio
# ---------------------------------------------------------------------------


def test_sharpe_ratio_matches_manual_formula():
    assert opt.sharpe_ratio(0.08, 0.10, 0.02) == pytest.approx(0.6, abs=1e-9)


def test_sharpe_ratio_zero_volatility_returns_zero():
    assert opt.sharpe_ratio(0.08, 0.0, 0.02) == 0.0


def test_sharpe_ratio_negative_volatility_returns_zero():
    assert opt.sharpe_ratio(0.08, -0.05, 0.02) == 0.0


def test_sharpe_ratio_handles_negative_excess_return():
    # Below the risk-free rate should produce a negative Sharpe, not an error.
    assert opt.sharpe_ratio(0.01, 0.10, 0.02) == pytest.approx(-0.1, abs=1e-9)


# ---------------------------------------------------------------------------
# risk_free_rate
# ---------------------------------------------------------------------------


def test_risk_free_rate_defaults_near_cash_return_when_unset():
    c = sample_config()
    c.pop("capital_market_config", None)
    rf = opt.risk_free_rate(c)
    # Should resolve to something in the sane neighborhood of the shipped
    # Cash asset-class return (~0.02), not raise and not be negative.
    assert 0.0 <= rf <= 0.10


def test_risk_free_rate_honors_explicit_override():
    c = sample_config()
    c["capital_market_config"] = dict(c.get("capital_market_config") or {})
    c["capital_market_config"]["risk_free_rate"] = 0.033
    assert opt.risk_free_rate(c) == pytest.approx(0.033, abs=1e-9)


# ---------------------------------------------------------------------------
# allocation_portfolio_stats — sharpe key
# ---------------------------------------------------------------------------


def test_allocation_portfolio_stats_includes_finite_sharpe():
    c = sample_config()
    stats = opt.allocation_portfolio_stats(c)
    assert "sharpe" in stats
    assert stats["sharpe"] == stats["sharpe"]  # not NaN
    assert abs(stats["sharpe"]) < float("inf")


def test_allocation_portfolio_stats_sharpe_matches_expected_return_vol_formula():
    c = sample_config()
    stats = opt.allocation_portfolio_stats(c)
    rf = opt.risk_free_rate(c)
    expected = opt.sharpe_ratio(stats["expected_return"], stats["volatility"], rf)
    assert stats["sharpe"] == pytest.approx(expected, abs=1e-9)


def test_allocation_portfolio_stats_sharpe_present_for_optimizer_mode_too():
    c = sample_config()
    stats = opt.allocation_portfolio_stats(c, force_mode="optimizer_recommendation")
    rf = opt.risk_free_rate(c)
    expected = opt.sharpe_ratio(stats["expected_return"], stats["volatility"], rf)
    assert stats["sharpe"] == pytest.approx(expected, abs=1e-9)


def test_allocation_portfolio_stats_existing_keys_unchanged():
    # Additive-only guard: the pre-existing keys/values must be untouched by
    # the sharpe addition.
    c = sample_config()
    stats = opt.allocation_portfolio_stats(c)
    for key in ("mode", "label", "targets", "expected_return", "volatility",
                "geometric_return", "diagnostics"):
        assert key in stats


# ---------------------------------------------------------------------------
# efficient_frontier
# ---------------------------------------------------------------------------


def test_efficient_frontier_returns_multiple_points_for_sample_household():
    c = sample_config()
    points = opt.efficient_frontier(c)
    assert len(points) >= 2


def test_efficient_frontier_points_have_expected_keys():
    c = sample_config()
    points = opt.efficient_frontier(c)
    for p in points:
        assert set(("target_return", "volatility", "return", "sharpe", "weights")).issubset(p.keys())


def test_efficient_frontier_volatility_non_decreasing_when_sorted():
    c = sample_config()
    points = opt.efficient_frontier(c)
    vols = [p["volatility"] for p in points]
    assert vols == sorted(vols)


def test_efficient_frontier_return_non_decreasing_along_sorted_frontier():
    c = sample_config()
    points = opt.efficient_frontier(c)
    rets = [p["return"] for p in points]
    for i in range(len(rets) - 1):
        assert rets[i] <= rets[i + 1] + 1e-6, (
            f"return decreased along the volatility-sorted frontier at index {i}: "
            f"{rets[i]} -> {rets[i + 1]}"
        )


def test_efficient_frontier_weights_are_long_only_and_sum_to_one():
    c = sample_config()
    points = opt.efficient_frontier(c)
    for p in points:
        weights = p["weights"]
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)
        for w in weights.values():
            assert w >= -1e-9


def test_efficient_frontier_respects_n_points_upper_bound():
    c = sample_config()
    points = opt.efficient_frontier(c, n_points=8)
    assert len(points) <= 8


def test_efficient_frontier_does_not_raise_for_optimizer_force_mode():
    c = sample_config()
    points = opt.efficient_frontier(c, force_mode="optimizer_recommendation")
    assert isinstance(points, list)
    assert len(points) >= 1


def test_efficient_frontier_degenerate_single_class_falls_back_gracefully():
    # Disable every class except one to force the degenerate n==1 branch and
    # confirm it returns a single well-formed point instead of raising.
    c = sample_config()
    enabled = {cls: False for cls in opt.ASSET_CLASSES}
    enabled["US Large Cap"] = True
    c["asset_class_enabled"] = enabled
    points = opt.efficient_frontier(c)
    assert len(points) >= 1
    for p in points:
        assert p["volatility"] >= 0.0
        assert sum(p["weights"].values()) == pytest.approx(1.0, abs=1e-6)
