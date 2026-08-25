"""Optimization-refactor Phase 2: genuine per-path Monte Carlo "cut
statistics" -- probability of any cut, worst annual cut depth, longest
consecutive run of cut years, and cumulative real-dollar shortfall.

This extends the same reporting-only attribution already built for
"probability essential spending is fully funded"
(test_essential_fully_funded_probability_regression.py): both engines
already finalize a per-path/year unfunded-gap figure (out['unfunded'] in the
vectorized engine, row['unfunded_gap'] in the scalar engine's per-path
deterministic rerun) before any of this runs. "Cut" means that a given
path/year's unfunded amount exceeds $1 (nominal), regardless of which
spend tier it would ultimately spill into -- unlike
spending_priority_cut_check (a single hypothetical solved cut_frac
scenario), this reads each path's OWN realized shortfall.

Reporting-only: reads already-finalized unfunded/unfunded_gap tracking and
never feeds back into unfunded/liquid/total/path_success/success_rate.
"""
from __future__ import annotations

import numpy as np

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import (
    _mc_vectorized_batch,
    _mc_vectorized_projection,
    monte_carlo,
    monte_carlo_exact_scalar,
    project,
)


def _base_config():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["plan_end"] = min(int(c["plan_end"]), int(c["plan_start"]) + 8)
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    return c


def _synthetic_zero_income_setup(total_spends: list, tiers: dict):
    """A fully synthetic, zero-balance, zero-income household: one taxable
    account with balance 0 and no deposits of any kind, so the withdrawal
    cascade cannot fund ANY of the requested spend -- unfunded == the full
    requested withdrawal, deterministically, in every year. ``total_spends``
    gives one requested-spend dollar amount per plan year (its length sets
    n_years). A $0 year is exactly $0 regardless of the pre-existing
    falsy-zero inflation-scaling quirk in _mc_row_bucket_flows (c['inf']=0.0
    silently becomes 0.025 there -- see this module's sibling test file for
    the full explanation), since scaling a zero by a positive factor is
    still zero -- so the any_cut/cut_years_count/max_consecutive_cut_years
    threshold checks below are robust to it even across multiple years.
    """
    plan_start = 2030
    n_years = len(total_spends)
    years = list(range(plan_start, plan_start + n_years))
    c = {
        "plan_start": plan_start,
        "inf": 0.0,
        "account_registry": [{"id": "acct1", "tax": "taxable", "balance": 0.0}],
        "balances": {"acct1": 0.0},
    }
    base_rows = [
        {
            "year": y,
            "_account_withdrawals": {"acct1": spend},
            "total_spend": spend,
            "total_tax": 0.0,
            "gross_income": 0.0,
            "spend_by_tier": dict(tiers),
            "total_nw": 0.0, "pretax_nw": 0.0, "roth_nw": 0.0, "trust_nw": 0.0, "hsa_nw": 0.0,
        }
        for y, spend in zip(years, total_spends)
    ]
    n_sims = 3
    returns = np.zeros((n_sims, n_years))
    inflation_paths = {
        "inflation_index_matrix": np.ones((n_sims, n_years)),
        "medical_index_matrix": np.ones((n_sims, n_years)),
        "wellness_shock_matrix": np.zeros((n_sims, n_years)),
        "inflation_by_year_matrix": np.zeros((n_sims, n_years)),
    }
    max_death_years = np.full(n_sims, years[-1] + 100, dtype=int)  # every year active
    return c, base_rows, returns, inflation_paths, max_death_years


def test_no_shortfall_year_has_no_cut():
    tiers = {"essential": 40000.0, "important": 20000.0, "discretionary": 10000.0}
    # Single year, all spend fundable (spend request is 0) -- see comment in
    # test_essential_fully_funded_probability_regression.py about why a
    # single-year fixture sidesteps the inflation-index exponent entirely
    # for exact-dollar assertions.
    c, base_rows, returns, inflation_paths, max_death_years = _synthetic_zero_income_setup([0.0], tiers)
    proj = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death_years)
    assert bool(np.all(~proj["any_cut"]))
    assert bool(np.all(proj["cut_years_count"] == 0))
    assert bool(np.all(proj["max_annual_shortfall_real"] == 0.0))
    assert bool(np.all(proj["cumulative_shortfall_real"] == 0.0))
    assert bool(np.all(proj["max_consecutive_cut_years"] == 0))


def test_single_shortfall_year_exact_dollars():
    tiers = {"essential": 40000.0, "important": 20000.0, "discretionary": 10000.0}
    c, base_rows, returns, inflation_paths, max_death_years = _synthetic_zero_income_setup([50000.0], tiers)
    proj = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death_years)
    assert bool(np.all(proj["any_cut"]))
    assert bool(np.all(proj["cut_years_count"] == 1))
    assert bool(np.all(proj["max_annual_shortfall_real"] == 50000.0))
    assert bool(np.all(proj["cumulative_shortfall_real"] == 50000.0))
    assert bool(np.all(proj["max_consecutive_cut_years"] == 1))


def test_multi_year_cut_pattern_counts_and_longest_run():
    # Years: cut, cut, no-cut, cut -- exercises cut_years_count (3),
    # max_consecutive_cut_years (2, the first two years), and any_cut (True)
    # using only threshold-crossing checks (>$1), which are robust to the
    # per-year inflation-scaling quirk noted above regardless of how it
    # scales the nonzero years, since a $0 request is always exactly $0.
    tiers = {"essential": 40000.0, "important": 20000.0, "discretionary": 10000.0}
    total_spends = [30000.0, 30000.0, 0.0, 30000.0]
    c, base_rows, returns, inflation_paths, max_death_years = _synthetic_zero_income_setup(total_spends, tiers)
    proj = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death_years)
    assert bool(np.all(proj["any_cut"]))
    assert bool(np.all(proj["cut_years_count"] == 3))
    assert bool(np.all(proj["max_consecutive_cut_years"] == 2))
    assert bool(np.all(proj["cumulative_shortfall_real"] > 0.0))
    assert bool(np.all(proj["max_annual_shortfall_real"] > 0.0))


def test_larger_shortfall_never_produces_a_smaller_cumulative_shortfall():
    tiers = {"essential": 40000.0, "important": 20000.0, "discretionary": 10000.0}
    c_small, rows_small, ret_small, infl_small, md_small = _synthetic_zero_income_setup([10000.0], tiers)
    c_large, rows_large, ret_large, infl_large, md_large = _synthetic_zero_income_setup([50000.0], tiers)
    proj_small = _mc_vectorized_projection(c_small, rows_small, ret_small, infl_small, md_small)
    proj_large = _mc_vectorized_projection(c_large, rows_large, ret_large, infl_large, md_large)
    assert bool(np.all(proj_large["cumulative_shortfall_real"] >= proj_small["cumulative_shortfall_real"]))
    assert bool(np.all(proj_large["max_annual_shortfall_real"] >= proj_small["max_annual_shortfall_real"]))


def test_vectorized_batch_surfaces_cut_statistics_with_valid_ranges():
    c = _base_config()
    base_rows = project(c)
    batch = _mc_vectorized_batch(c, base_rows, 20, 7, 0.06, 0.12, 0.0, use_asset_classes=False)
    assert batch["probability_any_cut"] is not None
    assert 0.0 <= batch["probability_any_cut"] <= 1.0
    for key in ("cut_years_pct", "max_annual_shortfall_real_pct", "max_consecutive_cut_years_pct", "cumulative_shortfall_real_pct"):
        pct = batch[key]
        assert pct is not None
        for p in (5, 50, 95):
            assert p in pct
            assert pct[p] >= 0.0


def test_comfortably_funded_fixture_has_zero_probability_of_any_cut():
    # Same short-horizon, comfortably-funded fixture used by the sibling
    # essential-fully-funded test to assert 1.0 fully-funded probability --
    # here that must mean zero probability of any cut at all.
    c = _base_config()
    base_rows = project(c)
    batch = _mc_vectorized_batch(c, base_rows, 20, 7, 0.06, 0.12, 0.0, use_asset_classes=False)
    assert batch["probability_any_cut"] == 0.0


def test_monte_carlo_output_carries_cut_statistics_vectorized():
    c = _base_config()
    base_rows = project(c)
    mc = monte_carlo(c, n_sims=20, seed=3, base_rows=base_rows)
    assert "probability_any_cut" in mc
    assert 0.0 <= mc["probability_any_cut"] <= 1.0
    for key in ("cut_years_pct", "max_annual_shortfall_real_pct", "max_consecutive_cut_years_pct", "cumulative_shortfall_real_pct"):
        assert key in mc


def test_scalar_engine_reports_the_same_cut_statistics():
    c = _base_config()
    base_rows = project(c)
    result = monte_carlo_exact_scalar(c, n_sims=15, seed=2, base_rows=base_rows)
    assert "probability_any_cut" in result
    assert 0.0 <= result["probability_any_cut"] <= 1.0
    for key in ("cut_years_pct", "max_annual_shortfall_real_pct", "max_consecutive_cut_years_pct", "cumulative_shortfall_real_pct"):
        pct = result[key]
        assert key in result
        for p in (5, 50, 95):
            assert p in pct
            assert pct[p] >= 0.0
