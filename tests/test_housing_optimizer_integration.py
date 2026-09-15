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


def test_move2_strategy_anchored_default_is_unchanged():
    """move2_strategy defaults to 'anchored' and must behave exactly as
    before (§8.2 P3 module docstring): identical results whether or not
    move2_strategy is passed explicitly."""
    c0 = _base_config()
    kwargs = dict(
        locations=[ho.Location(state="Texas"), ho.Location(state="Florida")],
        move1_window=ho.SearchWindow(2027, 2027, 2027, 2027),
        move2_window=ho.Move2Window(latest_sale_year_2=2032, latest_purchase_year_2=2032),
        anchor_count=2,
        objective="net_worth",
    )
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        omitted = ho.optimize_housing(c0, **kwargs)
        explicit_anchored = ho.optimize_housing(c0, move2_strategy="anchored", **kwargs)
    assert explicit_anchored["move2_strategy"] == "anchored"
    assert omitted["candidates_evaluated"] == explicit_anchored["candidates_evaluated"]
    assert omitted["recommendation"] == explicit_anchored["recommendation"]


def test_move2_strategy_cross_product_runs_end_to_end_against_more_than_anchor_count_anchors():
    """A small search window (2 years each, 2 locations) with anchor_count=1
    should still let cross_product build move-2 candidates against every
    eligible move-1 candidate, not just the single anchor 'anchored' would
    use -- confirmed by cross_product evaluating strictly more move-2
    candidates than the equivalent anchored run with the same anchor_count.
    """
    c0 = _base_config()
    move1_window = ho.SearchWindow(earliest_sale_year=2027, latest_sale_year=2028,
                                    earliest_purchase_year=2027, latest_purchase_year=2028)
    move2_window = ho.Move2Window(latest_sale_year_2=2030, latest_purchase_year_2=2031)
    locations = [ho.Location(state="Texas"), ho.Location(state="Florida")]
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        anchored = ho.optimize_housing(
            c0, locations=locations, move1_window=move1_window, move2_window=move2_window,
            anchor_count=1, objective="net_worth", move2_strategy="anchored",
        )
        cross = ho.optimize_housing(
            c0, locations=locations, move1_window=move1_window, move2_window=move2_window,
            anchor_count=1, objective="net_worth", move2_strategy="cross_product",
        )
    assert cross["move2_strategy"] == "cross_product"
    assert cross["recommendation"] is not None
    two_move_cross = [r for r in [cross["recommendation"], *cross["alternatives"]] if r and len(r["moves"]) == 2]
    two_move_anchored = [r for r in [anchored["recommendation"], *anchored["alternatives"]]
                          if r and len(r["moves"]) == 2]
    assert two_move_cross, "expected two-move candidates in the cross_product results"
    # cross_product ignores anchor_count and searches every eligible move-1
    # candidate, so its total candidate pool must be strictly larger than
    # the anchor_count=1 anchored run's (same windows/locations otherwise).
    assert cross["candidates_evaluated"] > anchored["candidates_evaluated"]


def test_move2_strategy_cross_product_composes_with_narrowed_search_mode():
    c0 = _base_config()
    move1_window = ho.SearchWindow(earliest_sale_year=2027, latest_sale_year=2028,
                                    earliest_purchase_year=2027, latest_purchase_year=2028)
    move2_window = ho.Move2Window(latest_sale_year_2=2030, latest_purchase_year_2=2031)
    locations = [ho.Location(state="Texas"), ho.Location(state="Florida")]
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        result = ho.optimize_housing(
            c0, locations=locations, move1_window=move1_window, move2_window=move2_window,
            anchor_count=1, objective="net_worth", search_mode="narrowed", move2_strategy="cross_product",
        )
    assert result["search_mode"] == "narrowed"
    assert result["move2_strategy"] == "cross_product"
    assert result["candidates_evaluated"] > 0


def test_move2_strategy_cross_product_rejects_a_too_large_search_before_running_the_engine():
    c0 = _base_config()
    # Keep move1_window small (cheap real-engine Pass 1a, like the other
    # tests here) but move2_window huge -- estimate_move2_candidate_count is
    # computed (and this raised) before any move-2 engine call, so a wide
    # move2 window alone is enough to trip the cap without this test paying
    # for a wide move1 grid too.
    move1_window = ho.SearchWindow(earliest_sale_year=2027, latest_sale_year=2028,
                                    earliest_purchase_year=2027, latest_purchase_year=2028)
    move2_window = ho.Move2Window(latest_sale_year_2=2100, latest_purchase_year_2=2100)
    locations = [ho.Location(state="Texas"), ho.Location(state="Florida")]
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES), pytest.raises(ValueError, match="cross_product"):
        ho.optimize_housing(
            c0, locations=locations, move1_window=move1_window, move2_window=move2_window,
            objective="net_worth", move2_strategy="cross_product",
        )


def test_move2_concurrent_rejects_a_too_large_search_before_running_the_engine():
    # move2_concurrent generates its own candidate set (independent of
    # move2_strategy) that, before this fix, was never counted against
    # MOVE2_CROSS_PRODUCT_CAP -- so even the default move2_strategy='anchored'
    # (not just 'cross_product') could reach the real engine with an
    # uncapped, runaway number of concurrent candidates for a wide-enough
    # move2_window. move2_strategy is left at its default ('anchored'), so
    # estimated starts at 0 and is entirely the concurrent count -- proving
    # concurrent's contribution alone (not the pre-existing cross_product
    # check) is what trips the cap.
    #
    # With only 2 candidate locations and this move1_window, move1 Pass 1a
    # produces just 6 owned (extendable) candidates -- not enough anchors for
    # the concurrent count (anchors * locations * move2-window-years * 2) to
    # clear MOVE2_CROSS_PRODUCT_CAP=3000 on its own (verified: only ~1760,
    # under the cap, which let the real engine run to completion instead of
    # raising -- silently defeating the point of this test by taking
    # minutes). A third candidate location raises the number of owned move1
    # candidates to 9, which is enough: 9 anchors * 3 locations * 74
    # move2-window-years * 2 (buy/rent variants) = 3996 concurrent
    # candidates, comfortably over the cap, so optimize_housing raises
    # ValueError before ever calling the engine (verified this test now
    # completes in well under a second, unlike before the fix).
    move1_window = ho.SearchWindow(earliest_sale_year=2027, latest_sale_year=2028,
                                    earliest_purchase_year=2027, latest_purchase_year=2028)
    move2_window = ho.Move2Window(latest_sale_year_2=2100, latest_purchase_year_2=2100)
    locations = [ho.Location(state="Texas"), ho.Location(state="Florida"), ho.Location(state="California")]
    c0 = _base_config()
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES), pytest.raises(ValueError, match="cap"):
        ho.optimize_housing(
            c0, locations=locations, move1_window=move1_window, move2_window=move2_window,
            anchor_count=20, objective="net_worth", move2_concurrent=True,
        )


def test_move2_strategy_rejects_unknown_value():
    c0 = _base_config()
    with pytest.raises(ValueError, match="move2_strategy"):
        ho.optimize_housing(
            c0, locations=[ho.Location(state="Texas"), ho.Location(state="Florida")],
            move1_window=ho.SearchWindow(2027, 2027, 2027, 2027), move2_strategy="bogus",
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


def test_estimate_for_location_passes_characteristics_through_to_pricing():
    from src.housing_optimizer import Location, _estimate_for_location

    baseline = _estimate_for_location(Location(state="Texas"), "purchase")
    bigger = _estimate_for_location(
        Location(state="Texas", bedrooms=5, sqft_band="over_3500"), "purchase",
    )
    assert bigger["purchase_price"] > baseline["purchase_price"]


def test_move1_action_rent_only_is_honored_in_both_search_modes():
    c0 = _base_config()
    locations = [ho.Location(state="Texas"), ho.Location(state="Florida")]
    window = ho.SearchWindow(earliest_sale_year=2027, latest_sale_year=2027,
                              earliest_purchase_year=2027, latest_purchase_year=2028)
    for mode in ("full", "narrowed"):
        with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
            result = ho.optimize_housing(
                c0, locations=locations, move1_window=window,
                move1_action="rent", search_mode=mode, shortlist_size=1,
            )
        for cand in [result["recommendation"], *result["alternatives"]]:
            if cand is None:
                continue
            assert cand["moves"][0]["rent_indefinitely"] is True


def test_move2_concurrent_candidate_is_generated_and_scored_by_the_real_engine():
    """Engine-backed proof that move2_concurrent=True actually reaches the
    real engine and produces a genuine two-simultaneous-residence run (not
    just a code path that's never exercised).

    Note: unlike the sequential two-move case, a concurrent candidate can
    never outrank a move1-only candidate that already satisfies
    family_presence on its own -- the anchor a concurrent candidate extends
    must independently pass family_presence_ok before it's even eligible to
    anchor a move 2 (see family_presence_ok's docstring and the existing
    test_family_presence_hard_filter_drops_disqualifying_candidates), so
    concurrent mode only ever adds cost on top of an anchor that already
    satisfies presence by itself; it structurally cannot become the #1
    full-search recommendation on net_worth. This mirrors
    test_two_move_candidate_has_no_mc_approximate_flag's pattern below:
    assert a concurrent-mode candidate is present among the ranked results,
    not that it's ranked first.
    """
    c0 = _base_config()
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        result = ho.optimize_housing(
            c0,
            locations=[ho.Location(state="Texas"), ho.Location(state="Florida")],
            move1_window=ho.SearchWindow(2027, 2027, 2027, 2027),
            move2_window=ho.Move2Window(latest_sale_year_2=2028, latest_purchase_year_2=2028),
            move2_concurrent=True,
            anchor_count=1,
            family_presence=ho.FamilyPresence(region="Florida", start_year=2028, end_year=2028),
            shortlist_size=3,
        )
    assert result["recommendation"] is not None
    rows = [result["recommendation"], *result["alternatives"]]
    concurrent_rows = [
        r for r in rows
        if r and len(r["moves"]) == 2 and r["moves"][1]["mode"] == "concurrent"
    ]
    assert concurrent_rows, "expected at least one concurrent-mode candidate in the ranked results"
    move2 = concurrent_rows[0]["moves"][1]
    assert move2["sale_year"] is None
    assert move2["start_year"] is not None
