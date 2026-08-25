"""Optimization-refactor Phase 2: liquidity coverage distribution.

Both Monte Carlo engines already compute a per-path/year liquid retirement
asset figure (_liquid_value / out['liquid']) and already compare it against
a flat, nominal-dollar reserve floor (success_threshold) to determine
path_success (see _funding_success's min_liquid > threshold check). This
feature re-labels that SAME liquid/threshold relationship as a ratio --
"how many times over is the floor covered" -- rather than inventing a new
floor concept, and reports its distribution across paths: per-year
percentiles, plus each path's own worst-year (minimum) coverage ratio,
percentile-ized across paths.

Reporting-only: reads each engine's already-computed liquid/success_threshold
figures and never feeds back into path_success/success_rate/unfunded/liquid/
total.
"""
from __future__ import annotations

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import (
    _mc_vectorized_batch,
    monte_carlo,
    monte_carlo_exact_scalar,
    project,
)


def _base_config(**overrides):
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["plan_end"] = min(int(c["plan_end"]), int(c["plan_start"]) + 8)
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    c.update(overrides)
    return c


def test_vectorized_batch_surfaces_liquidity_coverage_with_valid_shape():
    c = _base_config(mc_success_liquid_floor=50000.0)
    base_rows = project(c)
    batch = _mc_vectorized_batch(c, base_rows, 20, 7, 0.06, 0.12, 50000.0, use_asset_classes=False)
    by_year = batch["liquidity_coverage_pct_by_year"]
    assert by_year is not None
    assert set(by_year.keys()) == set(batch["years"])
    for pct in by_year.values():
        for p in (5, 50, 95):
            assert p in pct
    worst = batch["worst_liquidity_coverage_ratio_pct"]
    assert worst is not None
    assert 5 in worst and 50 in worst and 95 in worst


def test_worst_coverage_ratio_is_never_larger_than_any_per_year_percentile_median():
    # Sanity/monotonicity: a path's own worst-year ratio is a minimum across
    # years, so the population's median worst-case ratio should never exceed
    # the median ratio in the single best year of the same population.
    c = _base_config(mc_success_liquid_floor=50000.0)
    base_rows = project(c)
    batch = _mc_vectorized_batch(c, base_rows, 40, 11, 0.06, 0.12, 50000.0, use_asset_classes=False)
    by_year = batch["liquidity_coverage_pct_by_year"]
    best_year_median = max(pct[50] for pct in by_year.values())
    assert batch["worst_liquidity_coverage_ratio_pct"][50] <= best_year_median


def test_no_floor_configured_means_coverage_is_undefined():
    c = _base_config(mc_success_liquid_floor=0.0, near_term_buffer_years=0.0)
    base_rows = project(c)
    batch = _mc_vectorized_batch(c, base_rows, 20, 7, 0.06, 0.12, 0.0, use_asset_classes=False)
    assert batch["liquidity_coverage_pct_by_year"] is None
    assert batch["worst_liquidity_coverage_ratio_pct"] is None


def test_monte_carlo_output_carries_liquidity_coverage_vectorized():
    c = _base_config(mc_success_liquid_floor=50000.0)
    base_rows = project(c)
    mc = monte_carlo(c, n_sims=20, seed=3, base_rows=base_rows)
    assert mc["liquidity_coverage_pct_by_year"] is not None
    assert mc["worst_liquidity_coverage_ratio_pct"] is not None


def test_scalar_engine_reports_the_same_liquidity_coverage_metric():
    c = _base_config(mc_success_liquid_floor=50000.0)
    base_rows = project(c)
    result = monte_carlo_exact_scalar(c, n_sims=15, seed=2, base_rows=base_rows)
    assert result["liquidity_coverage_pct_by_year"] is not None
    assert result["worst_liquidity_coverage_ratio_pct"] is not None
    for pct in result["liquidity_coverage_pct_by_year"].values():
        for p in (5, 50, 95):
            assert p in pct


def test_scalar_engine_no_floor_configured_means_coverage_is_undefined():
    c = _base_config(mc_success_liquid_floor=0.0, near_term_buffer_years=0.0)
    base_rows = project(c)
    result = monte_carlo_exact_scalar(c, n_sims=15, seed=2, base_rows=base_rows)
    assert result["liquidity_coverage_pct_by_year"] is None
    assert result["worst_liquidity_coverage_ratio_pct"] is None
