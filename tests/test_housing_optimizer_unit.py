"""Pure-function unit coverage for the housing optimizer's ORCHESTRATION
layer: engine-config translation (``plan_variant``), scoring/ranking
(``scoring``), move-2 anchoring and the pre-engine safety cap
(``candidates``), and ``optimize_housing``'s own argument validation and
rejection tally. No engine projection is run here -- see
test_housing_optimizer_integration.py for engine-backed coverage.

Candidate GENERATION, the family-presence radius, the coordinate descent and
the v2 payload shape each have their own module now
(test_housing_candidates_decoupled / test_housing_family_presence_radius /
test_housing_coordinate_descent_unit / test_housing_results_v2); this file no
longer duplicates them.
"""
from __future__ import annotations

import pytest

from src.housing_optimizer import (
    MOVE2_CROSS_PRODUCT_CAP,
    HousingCandidate,
    Location,
    Move,
    MoveWindow,
    OriginalHome,
    SaleWindow,
    ScoredCandidate,
    estimate_move2_candidate_count,
    extend_with_move2,
    optimize_housing,
    rank_candidates,
    score_candidate,
    sec121_exclusion_flag,
    select_all_eligible,
    select_anchors,
)
from src.housing.models import NARROWED_MAX_EVALS_PER_AXIS, NARROWED_MOVE2_AXES
from src.housing.plan_variant import (
    _DEFAULT_MORTGAGE_RATE,
    _apply_candidate,
    _effective_mortgage_rate,
    _purchase_price_for_location,
    estimate_monthly_pi_payment,
)

pytestmark = pytest.mark.unit

TX = Location(state="Texas", city_type="suburban", population_size=150000)
FL = Location(state="Florida", city_type="urban", population_size=300000)


def _minimal_config() -> dict:
    """Enough config for ``_apply_candidate`` and for the argument-validation
    and all-rejected paths of ``optimize_housing``, which never reach the
    engine."""
    return {"state": "Illinois", "home_sale_yr": 0}


def _cand(*moves, disposition="sell", sale_year=2030) -> HousingCandidate:
    return HousingCandidate(
        original_home=OriginalHome(disposition=disposition, sale_year=sale_year),
        moves=tuple(moves),
    )


def _move(index=1, year=2031, action="buy", loc=TX, mode="sequential") -> Move:
    return Move(index=index, acquisition_year=year, action=action, location=loc, mode=mode)


# ---------------------------------------------------------------------------
# plan_variant: candidate -> engine config
# ---------------------------------------------------------------------------

def test_apply_candidate_mutates_in_place_and_returns_none():
    """It is ``run_scenario``'s ``mutate`` callback, so it writes to the
    config it is handed rather than returning a new one."""
    c = _minimal_config()
    assert _apply_candidate(c, _cand(_move()), down_payment_pct=0.20,
                            mortgage_rate_pct=0.065) is None
    assert c["next_housing_steps"]


def test_keep_leaves_home_sale_yr_at_zero():
    c = _minimal_config()
    cand = _cand(_move(action="rent", year=2033, loc=FL),
                 disposition="keep", sale_year=None)
    _apply_candidate(c, cand, down_payment_pct=0.20, mortgage_rate_pct=0.065)
    assert c["home_sale_yr"] == 0


def test_sell_writes_the_searched_sale_year_to_home_sale_yr():
    c = _minimal_config()
    _apply_candidate(c, _cand(_move(year=2032), sale_year=2032),
                     down_payment_pct=0.20, mortgage_rate_pct=0.065)
    assert c["home_sale_yr"] == 2032


def test_down_payment_and_rate_come_from_the_request_not_a_constant():
    c = _minimal_config()
    cand = _cand(_move(year=2033, action="buy", loc=FL), sale_year=2032)
    _apply_candidate(c, cand, down_payment_pct=0.35, mortgage_rate_pct=0.055)
    step = c["next_housing_steps"][0]
    # The wire key is down_payment_pct -- unchanged; only its SOURCE moved.
    assert step["down_payment_pct"] == 0.35
    assert step["mortgage_rate_pct"] == 0.055


def test_purchase_price_prefers_target_range_midpoint():
    loc = Location(state="Texas", target_purchase_price_range=(400000.0, 500000.0), est_price=999999.0)
    assert _purchase_price_for_location(loc) == 450000.0


def test_purchase_price_falls_back_to_the_zip_scaled_estimate():
    """No price range set: use the ZIP screen's own scaled estimate, not a
    flatter state-wide number."""
    loc = Location(state="Texas", est_price=612345.0)
    assert _purchase_price_for_location(loc) == 612345.0


def test_purchase_price_honors_an_explicit_zero_est_price():
    """est_price=0.0 (never legitimately produced today) must not be treated
    as falsy and fall through to the state-level estimate -- an explicit
    None is the only thing that should fall through."""
    loc = Location(state="Texas", est_price=0.0)
    assert _purchase_price_for_location(loc) == 0.0


def test_purchase_price_falls_back_to_state_estimate_when_no_est_price():
    """A hand-built Location with neither a price range nor an est_price
    (never happens for an optimizer-generated candidate, since
    _splice_screen_detail always sets est_price) still returns something
    sane rather than raising."""
    loc = Location(state="Texas", city_type="suburban", population_size=150000)
    price = _purchase_price_for_location(loc)
    assert price > 0


def test_effective_mortgage_rate_prefers_the_explicit_value():
    assert _effective_mortgage_rate(TX, 0.05) == 0.05


def test_effective_mortgage_rate_falls_back_to_the_location_estimate():
    rate = _effective_mortgage_rate(TX, None)
    assert rate > 0


def test_monthly_pi_payment_matches_a_hand_computed_amortization():
    # $400,000 price, 20% down -> $320,000 principal, 6% annual rate, 30yr.
    # Standard level-payment formula: 320000 * 0.005 / (1 - 1.005**-360)
    payment = estimate_monthly_pi_payment(400000.0, 0.20, 0.06)
    assert round(payment, 2) == 1918.56


def test_monthly_pi_payment_is_zero_rate_safe():
    # 0% rate: straight-line principal / n_payments, no division by zero.
    payment = estimate_monthly_pi_payment(360000.0, 0.20, 0.0)
    assert round(payment, 2) == round(288000.0 / 360, 2)


def test_monthly_pi_payment_is_zero_when_fully_down():
    assert estimate_monthly_pi_payment(400000.0, 1.0, 0.06) == 0.0


def test_a_rental_move_is_a_rent_step_because_the_action_says_so():
    c = _minimal_config()
    _apply_candidate(c, _cand(_move(year=2031, action="rent")),
                     down_payment_pct=0.20, mortgage_rate_pct=0.065)
    step = c["next_housing_steps"][0]
    assert step["type"] == "rent"
    assert step["start_year"] == 2031
    assert step["monthly_rent"] > 0


def test_a_sequential_move2_ends_move1_and_points_the_engines_second_sale_at_it():
    c = _minimal_config()
    cand = _cand(_move(index=1, year=2031, action="buy", loc=TX),
                 _move(index=2, year=2036, action="buy", loc=FL))
    _apply_candidate(c, cand, down_payment_pct=0.20, mortgage_rate_pct=0.065)
    move1, move2 = c["next_housing_steps"]
    assert move1["end_year"] == 2035
    assert move1["sale_year"] == 2036   # apply_next_housing_sale's trigger
    assert move2["start_year"] == 2036
    assert move2["end_year"] == 0       # open-ended


def test_a_concurrent_move2_keeps_move1_open_and_is_never_sold():
    c = _minimal_config()
    cand = _cand(_move(index=1, year=2031, action="buy", loc=TX),
                 _move(index=2, year=2033, action="rent", loc=FL, mode="concurrent"))
    _apply_candidate(c, cand, down_payment_pct=0.20, mortgage_rate_pct=0.065)
    move1, move2 = c["next_housing_steps"]
    assert move1["end_year"] == 0
    assert "sale_year" not in move1
    assert move2["type"] == "rent"
    # A second home is not a relocation: tax residency stays with move 1.
    assert [s["state"] for s in c["residency_schedule"]] == ["Illinois", "Texas"]


def test_a_sequential_move2_adds_a_residency_transition():
    c = _minimal_config()
    cand = _cand(_move(index=1, year=2031, loc=TX),
                 _move(index=2, year=2036, loc=FL))
    _apply_candidate(c, cand, down_payment_pct=0.20, mortgage_rate_pct=0.065)
    assert [s["state"] for s in c["residency_schedule"]] == ["Illinois", "Texas", "Florida"]


# ---------------------------------------------------------------------------
# scoring: notes replace the family_presence_via_rental boolean
# ---------------------------------------------------------------------------

def test_via_rental_is_a_note_not_a_boolean_field():
    sc = score_candidate({}, _cand(_move(action="rent")), [{"total_nw": 1.0}],
                         via_rental=True)
    assert "family presence via rental" in sc.notes
    assert not hasattr(sc, "family_presence_via_rental")


def test_a_short_ownership_span_is_flagged_and_noted():
    cand = _cand(_move(index=1, year=2031, action="buy"),
                 _move(index=2, year=2032, action="buy", loc=FL))
    sc = score_candidate({}, cand, [{"total_nw": 1.0}])
    assert sc.sec121_exclusion_lost == [False, True]
    assert any("121" in n for n in sc.notes)


def test_concurrent_mode_never_flags_sec121_for_move_2():
    cand = _cand(_move(index=1, year=2031, action="buy"),
                 _move(index=2, year=2032, action="buy", loc=FL, mode="concurrent"))
    sc = score_candidate({}, cand, [{"total_nw": 1.0}])
    assert sc.sec121_exclusion_lost == [False, False]


def test_an_overlapping_buy_carries_a_dual_ownership_note():
    """With the checkbox off the overlap is generated and scored, so the row
    has to SAY it overlaps (§5.3)."""
    cand = _cand(_move(year=2028, action="buy"), sale_year=2031)
    sc = score_candidate({}, cand, [{"total_nw": 1.0}])
    assert any(n.startswith("dual_ownership_years") for n in sc.notes)


@pytest.mark.parametrize("acquisition_year,sale_year,expected", [
    (2027, 2028, True),   # < 2 years owned
    (2027, 2029, False),  # exactly 2 years
    (2020, 2030, False),
    (None, 2030, False),  # nothing bought under this leg
    (2027, None, False),  # kept, never sold
])
def test_sec121_exclusion_flag_is_purely_informational(acquisition_year, sale_year, expected):
    assert sec121_exclusion_flag(acquisition_year, sale_year) is expected


def _scored(net_worth, lifetime_cost, mc_success_rate=None):
    return ScoredCandidate(candidate=_cand(_move()), net_worth=net_worth,
                           lifetime_cost=lifetime_cost, mc_success_rate=mc_success_rate,
                           sec121_exclusion_lost=[False])


def test_rank_candidates_net_worth_is_descending():
    ranked = rank_candidates([_scored(100, 5), _scored(300, 5), _scored(200, 5)], "net_worth")
    assert [s.net_worth for s in ranked] == [300, 200, 100]


def test_rank_candidates_lifetime_cost_is_ascending_lower_is_better():
    ranked = rank_candidates([_scored(100, 30), _scored(100, 10), _scored(100, 20)],
                             "lifetime_cost")
    assert [s.lifetime_cost for s in ranked] == [10, 20, 30]


def test_rank_candidates_mc_success_rate_falls_back_to_net_worth_when_unset():
    ranked = rank_candidates([_scored(100, 5), _scored(300, 5)], "mc_success_rate")
    assert [s.net_worth for s in ranked] == [300, 100]


def test_rank_candidates_mc_success_rate_uses_the_computed_rate_when_present():
    ranked = rank_candidates([_scored(300, 5, 0.70), _scored(100, 5, 0.95)], "mc_success_rate")
    assert [s.mc_success_rate for s in ranked] == [0.95, 0.70]


# ---------------------------------------------------------------------------
# Anchoring and the pre-engine safety cap
# ---------------------------------------------------------------------------

def test_a_rental_move1_is_now_a_legitimate_anchor():
    """The old rule required move 1 to end in ownership. With sale decoupled
    from acquisition, renting first and buying at move 2 is an ordinary plan
    (§5.1), so anchor selection no longer filters on ownership at all."""
    rented = ScoredCandidate(candidate=_cand(_move(action="rent")), net_worth=10.0,
                             lifetime_cost=1.0, mc_success_rate=None,
                             sec121_exclusion_lost=[False])
    owned = ScoredCandidate(candidate=_cand(_move(action="buy")), net_worth=9.0,
                            lifetime_cost=1.0, mc_success_rate=None,
                            sec121_exclusion_lost=[False])
    assert select_anchors([rented, owned], anchor_count=5) == [rented.candidate, owned.candidate]
    assert select_all_eligible([rented, owned]) == [rented.candidate, owned.candidate]


def test_anchors_respect_anchor_count_but_all_eligible_does_not():
    scored = [
        ScoredCandidate(candidate=_cand(_move(year=2031 + i)), net_worth=100.0 - i,
                        lifetime_cost=1.0, mc_success_rate=None, sec121_exclusion_lost=[False])
        for i in range(10)
    ]
    anchors = select_anchors(scored, anchor_count=3)
    assert [a.move1.acquisition_year for a in anchors] == [2031, 2032, 2033]
    assert len(select_all_eligible(scored)) == 10


def test_estimate_move2_candidate_count_matches_full_grid_generation_exactly():
    eligible = [_cand(_move(year=2031 + i)) for i in range(3)]
    window = MoveWindow(2035, 2038)
    exact = len(extend_with_move2(
        eligible, locations2=[FL], move2_window=window, move2_action="auto",
        concurrent=False, no_dual_ownership=True,
    ))
    estimated = estimate_move2_candidate_count(
        eligible, locations2=[FL], move2_window=window, move2_action="auto",
        concurrent=False, no_dual_ownership=True, narrowed=False,
    )
    assert estimated == exact > 0


@pytest.mark.parametrize("move2_action,actions", [("auto", 2), ("buy", 1), ("rent", 1)])
def test_narrowed_projection_is_axes_times_actions(move2_action, actions):
    """The projection used a standalone ``NARROWED_MAX_EVALS_PER_AXIS * 2``
    constant while the move-2 descent searches ONE axis and loops over
    actions -- 2x high except under 'auto', where ignoring the actions loop
    cancelled it. It is now derived from the constants the search itself
    uses."""
    eligible = [_cand(_move(year=2031)) for _ in range(4)]
    estimated = estimate_move2_candidate_count(
        eligible, locations2=[TX, FL], move2_window=MoveWindow(2035, 2038),
        move2_action=move2_action, concurrent=False, no_dual_ownership=True, narrowed=True,
    )
    assert estimated == 4 * 2 * NARROWED_MAX_EVALS_PER_AXIS * NARROWED_MOVE2_AXES * actions


def test_estimate_move2_candidate_count_is_keyword_only_past_eligible():
    """It gained ``move2_action``/``concurrent`` in the MIDDLE of the old
    positional order, so a stale positional call would silently bind
    ``no_dual_ownership`` to ``move2_action`` and return a wrong count. The
    keyword-only marker turns that into a TypeError."""
    with pytest.raises(TypeError):
        estimate_move2_candidate_count(
            [_cand(_move())], [FL], MoveWindow(2035, 2038), True, False,
        )


def test_cross_product_cap_guard_number_exceeds_cap_for_a_wide_window():
    eligible = [_cand(_move(year=2031 + i)) for i in range(50)]
    estimated = estimate_move2_candidate_count(
        eligible, locations2=[TX, FL], move2_window=MoveWindow(2036, 2100),
        move2_action="auto", concurrent=False, no_dual_ownership=True, narrowed=False,
    )
    assert estimated > MOVE2_CROSS_PRODUCT_CAP


def test_concurrent_candidate_count_alone_can_exceed_the_cap():
    anchors = [_cand(_move(year=2031 + i)) for i in range(50)]
    concurrent = estimate_move2_candidate_count(
        anchors, locations2=[TX, FL], move2_window=MoveWindow(2036, 2100),
        move2_action="auto", concurrent=True, no_dual_ownership=True, narrowed=False,
    )
    assert concurrent > MOVE2_CROSS_PRODUCT_CAP


# ---------------------------------------------------------------------------
# optimize_housing: argument validation and the rejection tally. None of
# these reach the engine.
# ---------------------------------------------------------------------------

def _kwargs(**overrides):
    base = dict(
        locations1=[Location(state="Colorado", zip_code="80014")],
        locations2=[],
        sale_window=SaleWindow(2030, 2030),
        move1_window=MoveWindow(2029, 2029),
        move2_window=None,
        dispositions=("sell",), move1_action="buy", move2_action="auto",
        move2_concurrent=False, no_dual_ownership=True,
        family_presence=None, family_coords={}, anchor_count=5,
        objective="net_worth", search_mode="full", move2_strategy="anchored",
        zip_screens={}, down_payment_pct=0.20, mortgage_rate_pct=0.065,
    )
    base.update(overrides)
    return base


def test_rejection_reasons_are_tallied_for_an_empty_run():
    """A zero-candidate run must say WHY. Buying in 2029 while the original
    home sells in 2030 is the only point in this grid, so every candidate is
    refused by no_dual_ownership and nothing reaches the engine."""
    out = optimize_housing(_minimal_config(), **_kwargs())
    assert out["candidates"] == []
    assert out["recommendation"] is None
    assert out["rejections"]["dual_ownership"] > 0
    assert out["rejections"]["family_presence"] == 0


def test_rejections_are_reported_even_when_zero():
    out = optimize_housing(_minimal_config(), **_kwargs())
    assert set(out["rejections"]) == {"dual_ownership", "family_presence", "move_order", "housing_gap"}


def test_family_presence_rejections_are_tallied_separately():
    """An unknown ZIP fails presence closed, so the tally must attribute the
    empty result to family_presence rather than to the ownership rule."""
    from src.housing_optimizer import FamilyPresence

    out = optimize_housing(_minimal_config(), **_kwargs(
        no_dual_ownership=False,
        family_presence=FamilyPresence(zip_code="60614", radius_miles=25,
                                       from_year=2029, through_year=2035),
    ))
    assert out["candidates"] == []
    assert out["rejections"]["family_presence"] > 0
    assert out["rejections"]["dual_ownership"] == 0


@pytest.mark.parametrize("overrides,expected", [
    (dict(objective="not_a_real_objective"), "objective"),
    (dict(search_mode="not_a_real_mode"), "search_mode"),
    (dict(move2_strategy="not_a_real_strategy"), "move2_strategy"),
    (dict(move1_action="maybe"), "move1_action"),
    (dict(move2_action="maybe"), "move2_action"),
    (dict(dispositions=("donate",)), "disposition"),
    (dict(locations1=[]), "location"),
])
def test_optimize_housing_rejects_unknown_arguments(overrides, expected):
    with pytest.raises(ValueError, match=expected):
        optimize_housing(_minimal_config(), **_kwargs(**overrides))


def test_optimize_housing_rejects_concurrent_with_narrowed_search():
    with pytest.raises(ValueError, match="narrowed"):
        optimize_housing(_minimal_config(), **_kwargs(
            move2_concurrent=True, search_mode="narrowed",
            move2_window=MoveWindow(2035, 2036), locations2=[FL],
        ))


# ---------------------------------------------------------------------------
# Location characteristics (still the optimizer's own input type)
# ---------------------------------------------------------------------------

def test_location_defaults_match_todays_implicit_assumption():
    loc = Location(state="Texas")
    assert loc.bedrooms == 3
    assert loc.bathrooms == 2.0
    assert loc.property_type == "single_family"
    assert loc.sqft_band == "1800_2500"
    assert loc.built_within_years is None
