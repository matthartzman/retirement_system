"""Unit tests for src/housing_comparison.py -- Slice 4 (H9/H10) of
docs/superpowers/plans/2026-09-09-housing-estimate-realism-and-dollar-
convention-design.md, §4.

Supersedes Slice 3's 2-candidate (H9a) coverage: the module no longer
compares one configured step against its opposite type, it sweeps three axes
by coordinate descent from two orderings. What is KEPT from Slice 3 is the
coverage that still matters -- that a synthesized candidate is priced through
``estimate_housing_cost`` (H8's pure extraction) rather than reusing the
household's parsed dollars, and that nothing mutates the caller's config.

Uses the frozen sample plan fixture (tests/fixtures/sample_plan_frozen/,
TEST_INPUT_DIR), which -- per test_cashflow_chart_home_purchase_down_payment.py's
own docstring -- has a real Housing Step 1 purchase configured (Texas,
$400,000 @ 27% down, 2036) and no configured home sale year, so it exercises
§4.1(a)'s "unset home_sale_yr centres the window on Step 1's start_year"
fallback and §4.1(c)'s "no second move" collapse at the same time.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from src.data_io import load_csv, parse_client
from src.housing_comparison import (
    AXIS_WINDOW,
    NEVER_SELL,
    Trajectory,
    build_axes,
    configured_trajectory,
    priced_step,
    sweep_housing_trajectories,
)
from src.plan_config import ensure_engine_config
from src.planning_engines import project

from conftest import TEST_INPUT_DIR
from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

ROOT = Path(__file__).resolve().parents[1]

# The sweep is the most expensive sheet in the workbook (tens of deterministic
# projections plus a handful of real Monte Carlo runs), so the suite runs it
# ONCE at a deliberately tiny path count and shares the result.
_FAST_MC_SIMS = 8


def _config():
    c = ensure_engine_config(parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), ""), source="test")
    c['mc_sims'] = _FAST_MC_SIMS
    c['mc_sensitivity_sims'] = 1
    c['housing_sweep_mc_sims'] = _FAST_MC_SIMS
    return c


@pytest.fixture(scope="module")
def swept():
    c = _config()
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        rows = project(c)
        result = sweep_housing_trajectories(c, rows)
    return c, result


def test_configured_trajectory_reads_all_three_axes():
    c = _config()
    traj = configured_trajectory(c)
    assert traj == Trajectory(sale_year=0, step1=('purchase', 2036), step2=None)


def test_sale_year_axis_falls_back_to_step1_year_when_home_sale_year_is_unset():
    c = _config()
    assert int(c['home_sale_yr']) == 0, "fixture is expected to leave home_sale_yr unset"
    axis = build_axes(c)['sale_year']
    assert axis[0] == NEVER_SELL
    # §4.1(a): centred on Step 1's start_year (2036), +/- 3, clamped to plan.
    assert axis[1:] == list(range(2036 - AXIS_WINDOW, 2036 + AXIS_WINDOW + 1))
    assert len(axis) <= 8


def test_step1_axis_is_both_types_across_the_year_window():
    axis = build_axes(_config())['step1']
    assert len(axis) <= 14
    assert {t for t, _y in axis} == {'purchase', 'rent'}
    assert ('purchase', 2036) in axis and ('rent', 2036) in axis


def test_step2_axis_collapses_to_a_single_no_second_move_candidate():
    # §4.1(c): an unconfigured Step 2 collapses to one candidate rather than
    # dropping the axis, so the sweep still runs for the single-move household.
    assert build_axes(_config())['step2'] == [None]


def test_priced_step_keeps_real_entered_dollars_at_the_as_configured_point():
    # §4.3's per-cell "real vs. modeled" rule: the exact configured (type,
    # year) is the ONLY point that uses the household's entered dollars.
    c = _config()
    step = c['next_housing_steps'][0]
    same = priced_step(c, step, 'purchase', 2036)
    assert same['purchase_price'] == step['purchase_price']
    assert same['real_estate_tax_pct'] == step['real_estate_tax_pct']


def test_priced_step_rederives_the_price_when_only_the_year_moves():
    # §4.3's trap: next_housing_steps[i]['purchase_price'] is a flat number
    # fixed at CSV-parse time for its own configured year. A candidate that
    # moves the year MUST re-derive it through estimate_housing_cost or the
    # sweep reintroduces the stale-year-price bug inside the fix for it.
    c = _config()
    step = c['next_housing_steps'][0]
    later = priced_step(c, step, 'purchase', 2039)
    assert later['start_year'] == 2039
    assert later['purchase_price'] != step['purchase_price']
    earlier = priced_step(c, step, 'purchase', 2033)
    assert earlier['purchase_price'] < later['purchase_price'], \
        "a later candidate year must carry more inflated dollars than an earlier one"


def test_priced_step_flips_type_and_clears_the_other_side_dollar_fields():
    c = _config()
    step = c['next_housing_steps'][0]
    rented = priced_step(c, step, 'rent', 2036)
    assert rented['type'] == 'rent'
    assert rented['monthly_rent'] > 0.0
    for field in ('purchase_price', 'maintenance_annual', 'real_estate_tax_pct',
                  'hoa_pct', 'mortgage_rate_pct', 'down_payment_pct'):
        assert rented[field] == 0.0
    bought = priced_step(c, dict(step, type='rent'), 'purchase', 2036)
    assert bought['purchase_price'] > 0.0
    assert bought['monthly_rent'] == 0.0


def test_priced_step_does_not_mutate_its_input():
    c = _config()
    step = c['next_housing_steps'][0]
    before = copy.deepcopy(step)
    priced_step(c, step, 'rent', 2039)
    assert step == before


def test_sweep_returns_none_when_no_step1_is_configured():
    c = dict(_config())
    c['next_housing_steps'] = []
    assert sweep_housing_trajectories(c, []) is None


def test_sweep_stays_within_the_designs_call_budget(swept):
    _c, result = swept
    # §4.2: <=36 deterministic project() calls per ordering, <=72 for both.
    # Distinct trajectories are scored once and cached across orderings, so
    # the real figure is below the ceiling, never above it.
    assert 0 < result['deterministic_calls'] <= 72
    # §4.2 step 2: "on the order of 5-10 real MC runs, not hundreds."
    assert 5 <= result['mc_calls'] <= 10
    assert result['mc_calls'] == len(result['refine_candidates'])


def test_sweep_runs_both_axis_orderings_and_keeps_the_better_one(swept):
    _c, result = swept
    assert len(result['orderings']) == 2
    assert {o['order'] for o in result['orderings']} == {
        ('sale_year', 'step1', 'step2'), ('step1', 'step2', 'sale_year')}
    assert result['winning_order']['objective_value'] == max(
        o['objective_value'] for o in result['orderings'])


def test_refine_candidates_are_ranked_scored_and_gated(swept):
    _c, result = swept
    candidates = result['refine_candidates']
    objectives = [x['objective_value'] for x in candidates]
    assert objectives == sorted(objectives, reverse=True)
    assert max(x['rank_score'] for x in candidates) == 100
    for cand in candidates:
        assert isinstance(cand['trajectory'], Trajectory)
        assert cand['scored_with_monte_carlo'] is True
        assert 0.0 <= cand['feasibility_probability'] <= 1.0
        assert isinstance(cand['feasibility_gate_met'], bool)
        assert isinstance(cand['equity_at_plan_end'], float)
    assert result['recommended'] in candidates


def test_sweep_visits_the_as_configured_trajectory(swept):
    # The configured point is the sweep's own starting trajectory, so it is
    # always among the scored coarse-pass candidates -- otherwise the sheet
    # would recommend a change without ever having priced the status quo.
    _c, result = swept
    visited = {
        cand['trajectory']
        for ordering in result['orderings']
        for candidates in ordering['axis_candidates'].values()
        for cand in candidates
    }
    assert result['configured'] in visited


def test_sweep_does_not_mutate_the_callers_config(swept):
    # The module-scoped fixture already ran a full sweep against this config;
    # it must have come back out the far side untouched (run_scenario's
    # deep-copy contract), checked against a freshly parsed one rather than by
    # paying for a second sweep.
    c, _result = swept
    fresh = _config()
    assert c['next_housing_steps'] == fresh['next_housing_steps']
    assert c['home_sale_yr'] == fresh['home_sale_yr']
