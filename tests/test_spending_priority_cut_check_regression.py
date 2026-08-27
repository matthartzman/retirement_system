"""Optimization-refactor Phase 2 (tiered cuts): spending_priority_cut_check
extends essential_discretionary_floor_check's 2-tier check (discretionary ==
travel only, vs. everything else) into the full SPENDING_TIERS cut-priority
cascade -- discretionary first, then important, essential protected as a
last resort -- using Phase 0's row['spend_by_tier'] classification.
contingent_liability is never counted as available to absorb a cut.

Like essential_discretionary_floor_check, this is a reporting-layer
computation: it re-labels an already-computed uniform dollar cut by
spending-tier priority and never changes which accounts fund withdrawals,
the MC success/failure computation, or any dollar total the engine already
produces.
"""
from __future__ import annotations

from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
from src.planning_engines import (
    monte_carlo,
    project,
    spending_priority_cut_check,
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


def _synthetic_rows(*tier_dicts):
    return [
        {"year": 2030 + i, "spend_by_tier": tiers}
        for i, tiers in enumerate(tier_dicts)
    ]


def test_none_cut_returns_none_protected():
    result = spending_priority_cut_check(_synthetic_rows({"essential": 40000, "important": 20000, "discretionary": 10000}), None)
    assert result["essential_protected"] is None
    assert result["cut_years"] == 0


def test_small_cut_comes_entirely_from_discretionary():
    rows = _synthetic_rows({"essential": 40000.0, "important": 20000.0, "discretionary": 10000.0, "contingent_liability": 5000.0})
    total_cuttable = 40000.0 + 20000.0 + 10000.0
    # A cut fraction whose dollar amount is smaller than the discretionary
    # tier alone must come entirely from discretionary.
    cut_frac = 5000.0 / total_cuttable
    result = spending_priority_cut_check(rows, cut_frac)
    year_cut = result["tier_cut_by_year"][2030]
    assert set(year_cut.keys()) == {"discretionary"}
    assert year_cut["discretionary"] == 5000.0
    assert result["essential_protected"] is True
    assert result["worst_year_essential_shortfall"] == 0.0


def test_cut_spills_into_important_once_discretionary_is_exhausted():
    rows = _synthetic_rows({"essential": 40000.0, "important": 20000.0, "discretionary": 10000.0})
    total_cuttable = 40000.0 + 20000.0 + 10000.0
    # Discretionary (10000) fully exhausted, 5000 more needed from important.
    cut_frac = 15000.0 / total_cuttable
    result = spending_priority_cut_check(rows, cut_frac)
    year_cut = result["tier_cut_by_year"][2030]
    assert year_cut["discretionary"] == 10000.0
    assert year_cut["important"] == 5000.0
    assert "essential" not in year_cut
    assert result["essential_protected"] is True


def test_cut_spills_into_essential_only_as_last_resort():
    rows = _synthetic_rows({"essential": 40000.0, "important": 20000.0, "discretionary": 10000.0})
    total_cuttable = 40000.0 + 20000.0 + 10000.0
    # Discretionary + important (30000) fully exhausted, 2000 more into essential.
    cut_frac = 32000.0 / total_cuttable
    result = spending_priority_cut_check(rows, cut_frac)
    year_cut = result["tier_cut_by_year"][2030]
    assert year_cut["discretionary"] == 10000.0
    assert year_cut["important"] == 20000.0
    assert round(year_cut["essential"], 2) == 2000.0
    assert result["essential_protected"] is False
    assert round(result["worst_year_essential_shortfall"], 2) == 2000.0
    assert result["worst_year"] == 2030


def test_contingent_liability_dollars_are_never_available_to_absorb_a_cut():
    # A household whose ONLY tier is contingent_liability has nothing
    # cuttable at all, however large the requested cut fraction.
    rows = _synthetic_rows({"contingent_liability": 50000.0})
    result = spending_priority_cut_check(rows, 1.0)
    assert result["tier_cut_by_year"] == {}
    assert result["cut_years"] == 0
    assert result["essential_protected"] is True  # nothing to protect, nothing shortfell


def test_cumulative_and_consecutive_cut_year_bookkeeping():
    # Years 0-1 need a cut (spills into essential), year 2 needs none, year 3
    # needs a cut again -- exercises cut_years, cumulative_cut_dollars,
    # max_annual_cut_dollars, and max_consecutive_cut_years independently.
    big_tiers = {"essential": 40000.0, "important": 10000.0, "discretionary": 5000.0}
    small_tiers = {"essential": 40000.0, "important": 10000.0, "discretionary": 5000.0}
    rows = _synthetic_rows(big_tiers, big_tiers, small_tiers, big_tiers)
    total_cuttable = 55000.0
    cut_frac = 20000.0 / total_cuttable  # exceeds discretionary+important (15000) every year but zero
    result = spending_priority_cut_check(rows, cut_frac)
    assert result["cut_years"] == 4
    assert result["max_consecutive_cut_years"] == 4
    assert round(result["cumulative_cut_dollars"], 2) == 80000.0
    assert round(result["max_annual_cut_dollars"], 2) == 20000.0


# Mirrors test_essential_discretionary_floor_regression.py's coverage
# against the real frozen two-spouse fixture, one level finer-grained.

def test_real_fixture_zero_cut_is_always_essential_protected():
    c, rows = sample_config_and_rows()
    result = spending_priority_cut_check(rows, 0.0)
    assert result["essential_protected"] is True
    assert result["worst_year_essential_shortfall"] == 0.0


def test_real_fixture_full_cut_cannot_be_discretionary_and_important_only():
    c, rows = sample_config_and_rows()
    result = spending_priority_cut_check(rows, 1.0)
    assert result["essential_protected"] is False
    assert result["worst_year_essential_shortfall"] > 0.0
    assert result["worst_year"] is not None


def test_real_fixture_larger_cut_never_produces_a_smaller_essential_shortfall():
    c, rows = sample_config_and_rows()
    small = spending_priority_cut_check(rows, 0.05)
    large = spending_priority_cut_check(rows, 0.50)
    assert large["worst_year_essential_shortfall"] >= small["worst_year_essential_shortfall"]


def test_real_fixture_sustainable_spending_solve_carries_tiered_cut_fields():
    c, rows = sample_config_and_rows(mc_sims=150, mc_sensitivity_sims=2)
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        mc = monte_carlo(c, base_rows=rows)
    solve = mc["sustainable_spending_solve"]
    assert len(solve) == 3
    for entry in solve:
        assert "tiered_essential_protected" in entry
        assert "tiered_cut_years" in entry
        assert "tiered_cumulative_cut_dollars" in entry
        assert "tiered_max_annual_cut_dollars" in entry
        assert "tiered_max_consecutive_cut_years" in entry
