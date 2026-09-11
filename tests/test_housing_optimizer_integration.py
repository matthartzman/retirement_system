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


def test_two_move_candidate_has_no_mc_approximate_flag():
    """Move 2's sale now runs through the engine's own second-sale pathway
    (design doc §8.2 P0) -- there is no more out-of-loop estimate, so the
    API response no longer carries an mc_approximate flag at all."""
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
    for row in [result["recommendation"], *result["alternatives"]]:
        if row is None:
            continue
        assert "mc_approximate" not in row


def test_two_move_candidate_sale_produces_a_real_engine_deposit():
    """Move 2's sale must be a real, cascade-visible deposit -- not merely
    reflected in the final score. Run the engine directly (bypassing the
    optimizer's own scoring) and check the second sale's row fields land
    where home_sale.py's apply_next_housing_sale writes them."""
    c0 = _base_config()
    cand = ho.HousingCandidate(
        location_1=ho.Location(state="Texas"), sale_year=2027, purchase_year=2027,
        location_2=ho.Location(state="Florida"), sale_year_2=2032, purchase_year_2=None,
    )
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c2, rows = ho._run_engine(c0, cand)
    by_year = {int(r["year"]): r for r in rows}
    sale_row = by_year[2032]
    assert sale_row["next_housing_sale_gross"] > 0
    assert sale_row["next_housing_sale_net"] > 0
    # The deposit is visible on the account-flow ledger the engine's own
    # cascade reads from, not just folded into a post-hoc adjustment.
    assert sum(sale_row["_account_deposits"].values()) >= sale_row["next_housing_sale_net"] - 1.0


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


def test_search_mode_full_is_unchanged_by_default():
    """search_mode defaults to 'full' and must behave exactly as before
    (§8.2 P2 module docstring): identical candidates_evaluated and ranking
    whether or not search_mode is passed explicitly."""
    c0 = _base_config()
    window = ho.SearchWindow(earliest_sale_year=2027, latest_sale_year=2028,
                              earliest_purchase_year=2027, latest_purchase_year=2028)
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        omitted = ho.optimize_housing(
            c0, locations=[ho.Location(state="Texas"), ho.Location(state="Florida")],
            move1_window=window, objective="net_worth",
        )
        explicit_full = ho.optimize_housing(
            c0, locations=[ho.Location(state="Texas"), ho.Location(state="Florida")],
            move1_window=window, objective="net_worth", search_mode="full",
        )
    assert explicit_full["search_mode"] == "full"
    assert omitted["candidates_evaluated"] == explicit_full["candidates_evaluated"]
    assert omitted["recommendation"] == explicit_full["recommendation"]


def test_search_mode_narrowed_runs_end_to_end_with_fewer_evaluations_than_full_grid():
    c0 = _base_config()
    # A wide window: full grid is 5 sale years x (6 purchase years + 1 rent)
    # per location x 2 locations = 70 candidates; narrowed should use far
    # fewer engine runs per the module docstring's ~33/location bound.
    window = ho.SearchWindow(earliest_sale_year=2027, latest_sale_year=2031,
                              earliest_purchase_year=2027, latest_purchase_year=2032)
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        full = ho.optimize_housing(
            c0, locations=[ho.Location(state="Texas"), ho.Location(state="Florida")],
            move1_window=window, objective="net_worth", search_mode="full",
        )
        narrowed = ho.optimize_housing(
            c0, locations=[ho.Location(state="Texas"), ho.Location(state="Florida")],
            move1_window=window, objective="net_worth", search_mode="narrowed",
        )
    assert narrowed["search_mode"] == "narrowed"
    assert narrowed["recommendation"] is not None
    assert narrowed["candidates_evaluated"] > 0
    assert narrowed["candidates_evaluated"] < full["candidates_evaluated"]
    values = [c["net_worth"] for c in [narrowed["recommendation"], *narrowed["alternatives"]]]
    assert values == sorted(values, reverse=True)


def test_search_mode_narrowed_rejects_unknown_value():
    c0 = _base_config()
    with pytest.raises(ValueError, match="search_mode"):
        ho.optimize_housing(
            c0, locations=[ho.Location(state="Texas"), ho.Location(state="Florida")],
            move1_window=ho.SearchWindow(2027, 2027, 2027, 2027), search_mode="bogus",
        )


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
