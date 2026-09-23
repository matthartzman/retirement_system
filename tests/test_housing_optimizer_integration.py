"""Engine-backed functional coverage for the housing optimizer: candidates
actually run through the real deterministic engine and Monte Carlo runner
(no new tax logic -- see src/housing's module docstring), on the frozen
sample plan fixture. Pure-logic coverage (config translation, filters,
ranking, the safety cap) lives in test_housing_optimizer_unit.py, which needs
no engine run and stays fast.
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


TX = ho.Location(state="Texas", population_size=150000, zip_code="78701")
FL = ho.Location(state="Florida", population_size=300000, zip_code="33101")
# Austin TX and Miami FL, far enough apart that a 25-mile family radius can
# only ever be satisfied by one of them.
COORDS = {"78701": (30.27, -97.74), "33101": (25.77, -80.19)}


def _kwargs(**overrides):
    base = dict(
        locations1=[TX, FL],
        locations2=[],
        sale_window=ho.SaleWindow(2027, 2027),
        move1_window=ho.MoveWindow(2027, 2028),
        move2_window=None,
        dispositions=("sell",),
        move1_action="auto",
        move2_action="auto",
        move2_concurrent=False,
        no_dual_ownership=True,
        family_presence=None,
        family_coords=COORDS,
        anchor_count=5,
        objective="net_worth",
        search_mode="full",
        move2_strategy="anchored",
        zip_screens={},
        down_payment_pct=0.20,
        mortgage_rate_pct=0.065,
    )
    base.update(overrides)
    return base


def _run(**overrides):
    c0 = _base_config()
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        return ho.optimize_housing(c0, **_kwargs(**overrides))


# @pytest.mark.nightly: engine-internals-only equivalence/sweep-breadth
# check identified in the 2026-09-15 CI-time profiling (see
# documentation/reference/TESTING_REFACTOR_RECOMMENDATIONS.md); cannot be
# triggered by an ordinary UI/config change, so it moved off the PR fast
# tier and runs in the nightly full-suite workflow instead.
@pytest.mark.nightly
def test_move1_only_optimization_returns_one_ranked_candidates_list():
    """v2 returns a single ``candidates`` list with ``recommendation`` as an
    alias of its head -- not a recommendation plus a disjoint
    ``alternatives`` list that duplicated the rank-1 row (§7.2)."""
    result = _run()
    assert result["objective"] == "net_worth"
    assert result["schema"] == "housing_optimize_v2"
    assert result["recommendation"] == result["candidates"][0]
    assert len(result["recommendation"]["moves"]) == 1
    assert result["candidates_evaluated"] > 0
    values = [c["net_worth"] for c in result["candidates"]]
    assert values == sorted(values, reverse=True)


@pytest.mark.nightly
def test_lifetime_cost_objective_ranks_ascending():
    result = _run(objective="lifetime_cost")
    values = [c["lifetime_cost"] for c in result["candidates"]]
    assert values == sorted(values)


@pytest.mark.nightly
def test_no_dual_ownership_excludes_buying_before_the_sale_and_tallies_it():
    result = _run(
        sale_window=ho.SaleWindow(2030, 2030),
        move1_window=ho.MoveWindow(2027, 2031),
        no_dual_ownership=True,
    )
    for row in result["candidates"]:
        move = row["moves"][0]
        if move["action"] == "buy":
            assert move["acquisition_year"] >= row["original_home"]["sale_year"]
    # The rows that were dropped are counted, not silently discarded.
    assert result["rejections"]["dual_ownership"] > 0


@pytest.mark.nightly
def test_renting_before_the_sale_is_allowed_and_is_the_intended_bridge():
    """``no_dual_ownership`` constrains OWNERSHIP only (§5.3): renting at the
    destination while still owning the old home is always permitted."""
    result = _run(
        sale_window=ho.SaleWindow(2030, 2030),
        move1_window=ho.MoveWindow(2027, 2028),
        move1_action="rent",
        no_dual_ownership=True,
    )
    assert result["candidates"]
    assert all(r["moves"][0]["action"] == "rent" for r in result["candidates"])
    assert any(r["moves"][0]["acquisition_year"] < 2030 for r in result["candidates"])
    assert result["rejections"]["dual_ownership"] == 0


@pytest.mark.nightly
def test_family_presence_is_a_radius_not_a_state_and_empty_runs_say_so():
    unfiltered = _run()
    filtered = _run(family_presence=ho.FamilyPresence(
        zip_code="60614", radius_miles=25, from_year=2029, through_year=2040))
    assert unfiltered["candidates_evaluated"] > 0
    # The family ZIP is not in COORDS, so presence fails closed for every
    # candidate -- and the payload names the constraint that emptied it.
    assert filtered["candidates_evaluated"] == 0
    assert filtered["recommendation"] is None
    assert filtered["rejections"]["family_presence"] > 0


def test_a_keep_disposition_runs_the_engine_with_home_sale_yr_at_zero():
    """A kept home has no sale year at all -- previously unrepresentable,
    because the sale year was the grid's outer loop."""
    result = _run(dispositions=("keep",), move1_action="rent",
                  move1_window=ho.MoveWindow(2027, 2027))
    assert result["candidates"]
    for row in result["candidates"]:
        assert row["original_home"]["disposition"] == "keep"
        assert row["original_home"]["sale_year"] is None


def test_two_move_candidate_sale_produces_a_real_engine_deposit():
    """Move 2's sale must be a real, cascade-visible deposit -- not merely
    reflected in the final score. Run the engine directly (bypassing the
    optimizer's own scoring) and check the second sale's row fields land
    where home_sale.py's apply_next_housing_sale writes them."""
    c0 = _base_config()
    cand = ho.HousingCandidate(
        original_home=ho.OriginalHome(disposition="sell", sale_year=2027),
        moves=(ho.Move(index=1, acquisition_year=2027, action="buy", location=TX),
               ho.Move(index=2, acquisition_year=2032, action="rent", location=FL)),
    )
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c2, rows = ho._run_engine(c0, cand, down_payment_pct=0.20, mortgage_rate_pct=0.065)
    by_year = {int(r["year"]): r for r in rows}
    sale_row = by_year[2032]
    assert sale_row["next_housing_sale_gross"] > 0
    assert sale_row["next_housing_sale_net"] > 0
    # The deposit is visible on the account-flow ledger the engine's own
    # cascade reads from, not just folded into a post-hoc adjustment.
    assert sum(sale_row["_account_deposits"].values()) >= sale_row["next_housing_sale_net"] - 1.0


def test_run_engine_returns_the_mutated_config_the_run_actually_used():
    """``_run_engine`` returns a ``(config, rows)`` PAIR, and the config is
    the deep copy ``_apply_candidate`` wrote to -- ``score_candidate`` and
    ``monte_carlo`` must be handed that, not the caller's base config."""
    c0 = _base_config()
    cand = ho.HousingCandidate(
        original_home=ho.OriginalHome(disposition="sell", sale_year=2027),
        moves=(ho.Move(index=1, acquisition_year=2028, action="buy", location=TX),),
    )
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c2, rows = ho._run_engine(c0, cand, down_payment_pct=0.31, mortgage_rate_pct=0.055)
    assert rows
    assert c2 is not c0
    assert c2["home_sale_yr"] == 2027
    assert c2["next_housing_steps"][0]["down_payment_pct"] == 0.31
    assert c2["next_housing_steps"][0]["mortgage_rate_pct"] == 0.055
    assert c0.get("next_housing_steps") != c2["next_housing_steps"]


@pytest.mark.nightly
def test_monte_carlo_success_rate_is_only_populated_for_the_shortlist():
    result = _run(
        sale_window=ho.SaleWindow(2027, 2029),
        move1_window=ho.MoveWindow(2027, 2029),
        shortlist_size=3,
    )
    rows = result["candidates"]
    assert len(rows) > 3, "grid should produce more candidates than the MC shortlist"
    with_mc = [r for r in rows if r["mc_success_rate"] is not None]
    without_mc = [r for r in rows if r["mc_success_rate"] is None]
    assert 0 < len(with_mc) <= 3
    assert without_mc


@pytest.mark.nightly
def test_search_mode_full_is_the_default():
    omitted = _run()
    explicit = _run(search_mode="full")
    assert explicit["search_mode"] == "full"
    assert omitted["candidates_evaluated"] == explicit["candidates_evaluated"]
    assert omitted["recommendation"] == explicit["recommendation"]


@pytest.mark.nightly
def test_search_mode_narrowed_runs_end_to_end_with_fewer_evaluations():
    window = ho.MoveWindow(2027, 2032)
    sale = ho.SaleWindow(2027, 2031)
    full = _run(search_mode="full", sale_window=sale, move1_window=window)
    narrowed = _run(search_mode="narrowed", sale_window=sale, move1_window=window)
    assert narrowed["search_mode"] == "narrowed"
    assert narrowed["recommendation"] is not None
    assert 0 < narrowed["candidates_evaluated"] < full["candidates_evaluated"]
    values = [c["net_worth"] for c in narrowed["candidates"]]
    assert values == sorted(values, reverse=True)


def test_search_mode_narrowed_rejects_unknown_value():
    with pytest.raises(ValueError, match="search_mode"):
        _run(search_mode="bogus")


@pytest.mark.nightly
def test_move2_uses_its_own_declared_window():
    """The old implementation derived move 2's lower bound from move 1's
    purchase year, silently overriding the declared window."""
    result = _run(
        locations2=[FL],
        move1_window=ho.MoveWindow(2027, 2027),
        move2_window=ho.MoveWindow(2033, 2034),
        anchor_count=2,
    )
    two_move = [r for r in result["candidates"] if len(r["moves"]) == 2]
    assert two_move
    for row in two_move:
        assert 2033 <= row["moves"][1]["acquisition_year"] <= 2034


@pytest.mark.nightly
def test_move2_strategy_anchored_is_the_default():
    kwargs = dict(locations2=[FL], move1_window=ho.MoveWindow(2027, 2027),
                  move2_window=ho.MoveWindow(2032, 2032), anchor_count=2)
    omitted = _run(**kwargs)
    explicit = _run(move2_strategy="anchored", **kwargs)
    assert explicit["move2_strategy"] == "anchored"
    assert omitted["candidates_evaluated"] == explicit["candidates_evaluated"]
    assert omitted["recommendation"] == explicit["recommendation"]


@pytest.mark.nightly
def test_move2_strategy_cross_product_uses_more_anchors_than_anchor_count():
    kwargs = dict(locations2=[FL], move1_window=ho.MoveWindow(2027, 2028),
                  move2_window=ho.MoveWindow(2030, 2031), anchor_count=1)
    anchored = _run(move2_strategy="anchored", **kwargs)
    cross = _run(move2_strategy="cross_product", **kwargs)
    assert cross["move2_strategy"] == "cross_product"
    assert cross["recommendation"] is not None
    assert [r for r in cross["candidates"] if len(r["moves"]) == 2]
    assert cross["candidates_evaluated"] > anchored["candidates_evaluated"]


@pytest.mark.nightly
def test_move2_strategy_cross_product_composes_with_narrowed_search_mode():
    result = _run(search_mode="narrowed", move2_strategy="cross_product",
                  locations2=[FL], move1_window=ho.MoveWindow(2027, 2028),
                  move2_window=ho.MoveWindow(2030, 2031), anchor_count=1)
    assert result["search_mode"] == "narrowed"
    assert result["move2_strategy"] == "cross_product"
    assert result["candidates_evaluated"] > 0


CA = ho.Location(state="California", population_size=200000, zip_code="90001")


def test_move2_strategy_cross_product_rejects_a_too_large_search_before_the_engine():
    # move1_window stays small (cheap real-engine Pass 1a) but move2_window is
    # huge -- the estimate is computed, and this raised, before any move-2
    # engine call.
    #
    # Sizing, since the anchor rule changed: this move1_window/sale_window
    # gives 8 move-1 candidates (1 sale year x 2 acquisition years x 2
    # locations x buy/rent), all of which are anchors now that a rental move 1
    # is eligible (§5.1) -- 4 under the old ownership-filtered rule. Against
    # THREE move-2 locations that is 8 x 3 x 72 window-years x 2 actions =
    # 3456, over MOVE2_CROSS_PRODUCT_CAP=3000; two locations would be 2304 and
    # would not trip it.
    with pytest.raises(ValueError, match="cross_product"):
        _run(move2_strategy="cross_product", locations2=[TX, FL, CA],
             move1_window=ho.MoveWindow(2027, 2028),
             move2_window=ho.MoveWindow(2029, 2100))


def test_move2_concurrent_rejects_a_too_large_search_before_the_engine():
    """move2_concurrent generates its own candidate set, independent of
    move2_strategy. move2_strategy is left at its default ('anchored'), so
    ``estimated`` starts at 0 and is entirely the concurrent count -- proving
    concurrent's contribution alone trips the cap. Same 3456 sizing as the
    cross_product test above."""
    with pytest.raises(ValueError, match="cap"):
        _run(move2_concurrent=True, locations2=[TX, FL, CA],
             move1_window=ho.MoveWindow(2027, 2028),
             move2_window=ho.MoveWindow(2029, 2100), anchor_count=20)


def test_move2_strategy_rejects_unknown_value():
    with pytest.raises(ValueError, match="move2_strategy"):
        _run(move2_strategy="bogus")


@pytest.mark.nightly
def test_optimizer_never_mutates_the_base_plan_config():
    c0 = _base_config()
    before = (c0.get("next_housing_steps"), c0.get("residency_schedule"),
              c0.get("home_sale_yr"))
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        ho.optimize_housing(c0, **_kwargs(move1_window=ho.MoveWindow(2027, 2027)))
    assert (c0.get("next_housing_steps"), c0.get("residency_schedule"),
            c0.get("home_sale_yr")) == before


def test_estimate_for_location_passes_characteristics_through_to_pricing():
    from src.housing_optimizer import Location, _estimate_for_location

    no_escalation = dict(start_year=2020, home_appr=0.0, inflation_general=0.0)
    baseline = _estimate_for_location(Location(state="Texas"), "purchase", **no_escalation)
    bigger = _estimate_for_location(
        Location(state="Texas", bedrooms=5, sqft_band="over_3500"), "purchase",
        **no_escalation,
    )
    assert bigger["purchase_price"] > baseline["purchase_price"]


def test_move1_action_rent_only_is_honored_in_both_search_modes():
    for mode in ("full", "narrowed"):
        result = _run(move1_action="rent", search_mode=mode, shortlist_size=1,
                      move1_window=ho.MoveWindow(2027, 2028))
        assert result["candidates"]
        for cand in result["candidates"]:
            assert cand["moves"][0]["action"] == "rent"


@pytest.mark.nightly
def test_move2_concurrent_candidate_is_generated_and_scored_by_the_real_engine():
    """Engine-backed proof that move2_concurrent=True reaches the real engine
    and produces a genuine two-simultaneous-residence run.

    A concurrent candidate can never outrank a move1-only candidate that
    already satisfies family_presence on its own -- the anchor it extends had
    to pass family_presence_ok before it was eligible to anchor a move 2 --
    so assert it is PRESENT among the ranked results, not that it is first.
    """
    result = _run(
        locations1=[TX], locations2=[FL],
        move1_window=ho.MoveWindow(2027, 2027),
        move2_window=ho.MoveWindow(2028, 2028),
        move2_concurrent=True, anchor_count=1, shortlist_size=3,
    )
    assert result["recommendation"] is not None
    concurrent_rows = [
        r for r in result["candidates"]
        if len(r["moves"]) == 2 and r["moves"][1]["mode"] == "concurrent"
    ]
    assert concurrent_rows, "expected at least one concurrent-mode candidate"
    assert concurrent_rows[0]["moves"][1]["acquisition_year"] == 2028


def test_family_distance_is_annotated_onto_the_locations_it_was_handed():
    """An empty result under a tight radius is otherwise undiagnosable: the
    row has to show how close the search actually came."""
    result = _run(
        locations1=[TX, FL],
        move1_window=ho.MoveWindow(2027, 2027),
        family_presence=ho.FamilyPresence(zip_code="78701", radius_miles=25,
                                          from_year=2027, through_year=2040),
        shortlist_size=1,
    )
    assert result["candidates"]
    for row in result["candidates"]:
        loc = row["moves"][0]["location"]
        assert loc["zip_code"] == "78701"
        assert loc["family_distance_miles"] == 0.0
