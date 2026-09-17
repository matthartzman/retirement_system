"""Bounded coordinate descent over (sale year, move-1 year, move-2 year).

Replaces the pre-2026-09-16 2D/1D version, whose axes were (sale, purchase)
with a separate 1D rent branch. Rent is now an action rather than a missing
year, so the rent branch is gone and the axes are the three year variables.
"""
import pytest

from src.housing.models import (
    HousingCandidate,
    Location,
    MoveWindow,
    SaleWindow,
    ScoredCandidate,
)
from src.housing.search import (
    generate_move1_candidates_narrowed,
    generate_move2_candidates_narrowed,
)

pytestmark = pytest.mark.unit

LOCS = [Location(state='CO')]


def _scorer(counter, peak_sale=2033, peak_acq=2036):
    """Single-peaked score so hill-climbing has a findable optimum."""
    def score(cand: HousingCandidate) -> ScoredCandidate | None:
        counter.append(cand)
        sale = cand.original_home.sale_year or peak_sale
        value = -abs(sale - peak_sale) - abs(cand.move1.acquisition_year - peak_acq)
        return ScoredCandidate(candidate=cand, net_worth=float(value),
                               lifetime_cost=-float(value), mc_success_rate=None,
                               sec121_exclusion_lost=[False])
    return score


def test_narrowed_search_finds_the_peak_without_evaluating_the_whole_grid():
    calls = []
    out = generate_move1_candidates_narrowed(
        locations1=LOCS, move1_window=MoveWindow(2030, 2050),
        sale_window=SaleWindow(2030, 2050), dispositions=('sell',),
        move1_action='buy', no_dual_ownership=False, score_fn=_scorer(calls),
    )
    best = max(out, key=lambda s: s.net_worth)
    assert best.candidate.original_home.sale_year == 2033
    assert best.candidate.move1.acquisition_year == 2036
    # A full grid over two 21-year windows is 441 points.
    assert len(calls) < 441


def test_keep_collapses_the_sale_axis():
    calls = []
    generate_move1_candidates_narrowed(
        locations1=LOCS, move1_window=MoveWindow(2030, 2050),
        sale_window=SaleWindow(2030, 2050), dispositions=('keep',),
        move1_action='rent', no_dual_ownership=False, score_fn=_scorer(calls),
    )
    assert calls
    assert all(c.original_home.sale_year is None for c in calls)


def test_infeasible_points_are_skipped_not_scored_as_zero():
    """A constraint rejection must not read as a very bad score, or the search
    will hill-climb away from a feasible region it has not explored yet."""
    def score(cand):
        if cand.move1.acquisition_year < 2040:
            return None
        return ScoredCandidate(candidate=cand, net_worth=1.0, lifetime_cost=1.0,
                               mc_success_rate=None, sec121_exclusion_lost=[False])

    out = generate_move1_candidates_narrowed(
        locations1=LOCS, move1_window=MoveWindow(2030, 2050),
        sale_window=SaleWindow(2030, 2050), dispositions=('sell',),
        move1_action='buy', no_dual_ownership=False, score_fn=score,
    )
    assert out
    assert all(s.candidate.move1.acquisition_year >= 2040 for s in out)


def test_move2_narrowed_respects_its_own_window_and_the_ordering_rule():
    calls = []
    anchors = generate_move1_candidates_narrowed(
        locations1=LOCS, move1_window=MoveWindow(2035, 2035),
        sale_window=SaleWindow(2033, 2033), dispositions=('sell',),
        move1_action='buy', no_dual_ownership=False, score_fn=_scorer(calls),
    )
    out = generate_move2_candidates_narrowed(
        [s.candidate for s in anchors], locations2=LOCS,
        move2_window=MoveWindow(2030, 2045), move2_action='buy',
        concurrent=False, no_dual_ownership=False, score_fn=_scorer([]),
    )
    assert out
    assert all(s.candidate.move2.acquisition_year > 2035 for s in out)


def test_apartment_locations_never_produce_a_buy_candidate_under_auto():
    apt_locs = [Location(state='CO', property_type='apartment')]
    calls = []
    out = generate_move1_candidates_narrowed(
        locations1=apt_locs, move1_window=MoveWindow(2030, 2032),
        sale_window=SaleWindow(2030, 2032), dispositions=('sell',),
        move1_action='auto', no_dual_ownership=False, score_fn=_scorer(calls),
    )
    assert calls
    assert all(c.move1.action == 'rent' for c in calls)


def test_move2_narrowed_also_excludes_buy_for_an_apartment_location():
    apt_locs = [Location(state='CO', property_type='apartment')]
    anchors = generate_move1_candidates_narrowed(
        locations1=LOCS, move1_window=MoveWindow(2035, 2035),
        sale_window=SaleWindow(2033, 2033), dispositions=('sell',),
        move1_action='buy', no_dual_ownership=False, score_fn=_scorer([]),
    )
    calls = []
    generate_move2_candidates_narrowed(
        [s.candidate for s in anchors], locations2=apt_locs,
        move2_window=MoveWindow(2036, 2038), move2_action='auto',
        concurrent=False, no_dual_ownership=False, score_fn=_scorer(calls),
    )
    assert calls
    assert all(c.move2.action == 'rent' for c in calls)


def test_an_all_infeasible_search_returns_empty_rather_than_looping():
    out = generate_move1_candidates_narrowed(
        locations1=LOCS, move1_window=MoveWindow(2030, 2040),
        sale_window=SaleWindow(2030, 2040), dispositions=('sell',),
        move1_action='buy', no_dual_ownership=False, score_fn=lambda c: None,
    )
    assert out == []


def test_lifetime_cost_objective_minimises_instead_of_climbing_net_worth():
    """A lifetime_cost search must descend towards the cost minimum.

    The surface here is rigged so ``net_worth`` is ANTI-correlated with
    ``lifetime_cost``: net worth peaks at the far corners of the window, cost
    at (2033, 2036). An incumbent chosen on raw ``net_worth`` therefore climbs
    to a corner and never visits the cost minimum at all, which is exactly the
    silent failure this pins -- the returned list still looks plausible.
    """
    peak_sale, peak_acq = 2033, 2036
    visited = []

    def score(cand):
        visited.append(cand)
        distance = float(abs(cand.original_home.sale_year - peak_sale)
                         + abs(cand.move1.acquisition_year - peak_acq))
        # Cost is minimised at the peak; net worth is maximised away from it.
        return ScoredCandidate(candidate=cand, net_worth=distance,
                               lifetime_cost=distance, mc_success_rate=None,
                               sec121_exclusion_lost=[False])

    out = generate_move1_candidates_narrowed(
        locations1=LOCS, move1_window=MoveWindow(2030, 2050),
        sale_window=SaleWindow(2030, 2050), dispositions=('sell',),
        move1_action='buy', no_dual_ownership=False, score_fn=score,
        objective='lifetime_cost',
    )

    best = min(out, key=lambda s: s.lifetime_cost)
    assert best.candidate.original_home.sale_year == peak_sale
    assert best.candidate.move1.acquisition_year == peak_acq
    assert best.lifetime_cost == 0.0
    # And it got there by searching, not by enumerating the 441-point grid.
    assert len(visited) < 441
