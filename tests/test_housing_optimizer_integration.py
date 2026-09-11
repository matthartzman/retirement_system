"""Engine-backed functional coverage for src/housing_optimizer.py: candidates
actually run through the real deterministic engine and Monte Carlo runner
(no new tax logic -- see module docstring), on the frozen sample plan fixture.
Pure-logic coverage (grid bounds, filters, ranking) lives in
test_housing_optimizer_unit.py, which needs no engine run and stays fast.
"""
from __future__ import annotations

import pytest

from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
import src.housing_optimizer as ho
from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

from conftest import TEST_INPUT_DIR

pytestmark = pytest.mark.integration


def _base_config():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        return ensure_engine_config(dict(c), source="test")


def test_move1_only_optimization_returns_a_headline_and_ranked_alternatives():
    c0 = _base_config()
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        result = ho.optimize_housing(
            c0,
            locations=[ho.Location(state="Texas", population_size=150000),
                       ho.Location(state="Florida", population_size=300000)],
            move1_window=ho.SearchWindow(2027, 2028, 2027, 2028),
            objective="net_worth",
        )
    assert result["objective"] == "net_worth"
    assert result["recommendation"] is not None
    assert len(result["recommendation"]["moves"]) == 1
    assert result["candidates_evaluated"] > 0
    # Ranked descending by net worth for the net_worth objective.
    values = [c["net_worth"] for c in [result["recommendation"], *result["alternatives"]]]
    assert values == sorted(values, reverse=True)


def test_lifetime_cost_objective_ranks_ascending():
    c0 = _base_config()
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        result = ho.optimize_housing(
            c0,
            locations=[ho.Location(state="Texas"), ho.Location(state="Florida")],
            move1_window=ho.SearchWindow(2027, 2027, 2027, 2028),
            objective="lifetime_cost",
        )
    values = [c["lifetime_cost"] for c in [result["recommendation"], *result["alternatives"]]]
    assert values == sorted(values)


def test_no_dual_ownership_excludes_purchase_before_sale_from_results():
    c0 = _base_config()
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        result = ho.optimize_housing(
            c0,
            locations=[ho.Location(state="Texas"), ho.Location(state="Florida")],
            move1_window=ho.SearchWindow(earliest_sale_year=2030, latest_sale_year=2030,
                                          earliest_purchase_year=2027, latest_purchase_year=2032),
            no_dual_ownership=True,
            objective="net_worth",
        )
    for row in [result["recommendation"], *result["alternatives"]]:
        move = row["moves"][0]
        if not move["rent_indefinitely"]:
            assert move["purchase_year"] >= move["sale_year"]


def test_family_presence_hard_filter_drops_disqualifying_candidates():
    c0 = _base_config()
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        unfiltered = ho.optimize_housing(
            c0,
            locations=[ho.Location(state="Texas"), ho.Location(state="Florida")],
            move1_window=ho.SearchWindow(2027, 2027, 2027, 2027),
            objective="net_worth",
        )
        filtered = ho.optimize_housing(
            c0,
            locations=[ho.Location(state="Texas"), ho.Location(state="Florida")],
            move1_window=ho.SearchWindow(2027, 2027, 2027, 2027),
            family_presence=ho.FamilyPresence(region="Illinois", start_year=2026, end_year=2040),
            objective="net_worth",
        )
    # Neither candidate location keeps the household in Illinois past 2027,
    # so every candidate must be dropped by the hard filter.
    assert unfiltered["candidates_evaluated"] > 0
    assert filtered["candidates_evaluated"] == 0
    assert filtered["recommendation"] is None


def test_two_move_candidate_is_flagged_as_mc_approximate():
    c0 = _base_config()
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        result = ho.optimize_housing(
            c0,
            locations=[ho.Location(state="Texas"), ho.Location(state="Florida")],
            move1_window=ho.SearchWindow(2027, 2027, 2027, 2027),
            move2_window=ho.Move2Window(latest_sale_year_2=2035, latest_purchase_year_2=2035),
            anchor_count=2,
            objective="net_worth",
        )
    two_move_rows = [row for row in [result["recommendation"], *result["alternatives"]]
                      if row and len(row["moves"]) == 2]
    assert two_move_rows, "expected at least one two-move candidate in the ranked results"
    for row in two_move_rows:
        assert row["mc_approximate"] is True
    one_move_rows = [row for row in [result["recommendation"], *result["alternatives"]]
                      if row and len(row["moves"]) == 1]
    for row in one_move_rows:
        assert row["mc_approximate"] is False


def test_monte_carlo_success_rate_is_only_populated_for_the_shortlist():
    c0 = _base_config()
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        result = ho.optimize_housing(
            c0,
            locations=[ho.Location(state="Texas"), ho.Location(state="Florida")],
            move1_window=ho.SearchWindow(earliest_sale_year=2027, latest_sale_year=2029,
                                          earliest_purchase_year=2027, latest_purchase_year=2029),
            objective="net_worth",
            shortlist_size=3,
        )
    all_rows = [result["recommendation"], *result["alternatives"]]
    assert len(all_rows) > 3, "grid should produce more candidates than the MC shortlist"
    with_mc = [r for r in all_rows if r["mc_success_rate"] is not None]
    without_mc = [r for r in all_rows if r["mc_success_rate"] is None]
    assert 0 < len(with_mc) <= 3
    assert without_mc


def test_request_adapter_runs_end_to_end_through_the_http_shaped_entry_point():
    c0 = _base_config()
    body = {
        "locations": [{"state": "Texas", "city_type": "suburban", "population_size": 150000},
                      {"state": "Florida", "city_type": "urban", "population_size": 300000}],
        "move1_window": {"earliest_sale_year": 2027, "latest_sale_year": 2027,
                          "earliest_purchase_year": 2027, "latest_purchase_year": 2027},
        "objective": "net_worth",
        "no_dual_ownership": True,
    }
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        payload, status = ho.optimize_housing_from_request(c0, body)
    assert status == 200
    assert payload["success"] is True
    assert payload["schema"] == "housing_optimize_v1"
    assert payload["recommendation"] is not None


def test_optimizer_never_mutates_the_base_plan_config():
    c0 = _base_config()
    before_next_steps = c0.get("next_housing_steps")
    before_residency = c0.get("residency_schedule")
    before_sale_yr = c0.get("home_sale_yr")
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        ho.optimize_housing(
            c0,
            locations=[ho.Location(state="Texas"), ho.Location(state="Florida")],
            move1_window=ho.SearchWindow(2027, 2027, 2027, 2027),
            objective="net_worth",
        )
    assert c0.get("next_housing_steps") == before_next_steps
    assert c0.get("residency_schedule") == before_residency
    assert c0.get("home_sale_yr") == before_sale_yr
