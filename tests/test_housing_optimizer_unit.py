"""Pure-function unit coverage for src/housing_optimizer.py: candidate grid
generation and bounds, no_dual_ownership filtering, the family_presence hard
filter, §121 informational flagging, move-2 anchoring, and objective-specific
ranking. No engine projection is run here -- see
test_housing_optimizer_functional.py for engine-backed coverage.
"""
from __future__ import annotations

import pytest

from src.housing_optimizer import (
    FamilyPresence,
    HousingCandidate,
    Location,
    Move2Window,
    ScoredCandidate,
    SearchWindow,
    family_presence_ok,
    generate_move1_candidates,
    generate_move2_candidates,
    optimize_housing_from_request,
    rank_candidates,
    sec121_exclusion_flag,
    select_anchors,
)

pytestmark = pytest.mark.unit

TX = Location(state="Texas", city_type="suburban", population_size=150000)
FL = Location(state="Florida", city_type="urban", population_size=300000)


# ---------------------------------------------------------------------------
# Candidate generation / grid bounds
# ---------------------------------------------------------------------------

def test_move1_grid_covers_the_full_sale_by_purchase_rectangle_plus_rent():
    window = SearchWindow(earliest_sale_year=2027, latest_sale_year=2028,
                           earliest_purchase_year=2027, latest_purchase_year=2029)
    cands = generate_move1_candidates([TX], window, no_dual_ownership=False)
    # 2 sale years x (3 purchase years + 1 rent-indefinitely) per location.
    assert len(cands) == 2 * (3 + 1)
    assert any(c.purchase_year is None for c in cands)
    assert all(window.earliest_sale_year <= c.sale_year <= window.latest_sale_year for c in cands)


def test_move1_grid_respects_two_locations():
    window = SearchWindow(2027, 2027, 2027, 2027)
    cands = generate_move1_candidates([TX, FL], window, no_dual_ownership=False)
    assert len(cands) == 2 * (1 + 1)
    assert {c.location_1.state for c in cands} == {"Texas", "Florida"}


def test_no_dual_ownership_drops_purchase_before_sale():
    window = SearchWindow(earliest_sale_year=2030, latest_sale_year=2030,
                           earliest_purchase_year=2027, latest_purchase_year=2032)
    with_toggle = generate_move1_candidates([TX], window, no_dual_ownership=True)
    without_toggle = generate_move1_candidates([TX], window, no_dual_ownership=False)
    owned_with = [c for c in with_toggle if c.purchase_year is not None]
    owned_without = [c for c in without_toggle if c.purchase_year is not None]
    assert all(c.purchase_year >= c.sale_year for c in owned_with)
    assert any(c.purchase_year < c.sale_year for c in owned_without)
    assert len(owned_with) < len(owned_without)


def test_no_dual_ownership_applies_to_move2_purchase_as_well():
    anchor = HousingCandidate(location_1=TX, sale_year=2027, purchase_year=2027)
    move2_window = Move2Window(latest_sale_year_2=2035, latest_purchase_year_2=2038)
    strict = generate_move2_candidates([anchor], [FL], move2_window, no_dual_ownership=True)
    relaxed = generate_move2_candidates([anchor], [FL], move2_window, no_dual_ownership=False)
    owned_strict = [c for c in strict if c.purchase_year_2 is not None]
    owned_relaxed = [c for c in relaxed if c.purchase_year_2 is not None]
    assert all(c.purchase_year_2 >= c.sale_year_2 for c in owned_strict)
    assert any(c.purchase_year_2 < c.sale_year_2 for c in owned_relaxed)


def test_move2_sale_cannot_precede_move1_purchase():
    anchor = HousingCandidate(location_1=TX, sale_year=2027, purchase_year=2030)
    move2_window = Move2Window(latest_sale_year_2=2032, latest_purchase_year_2=2033)
    cands = generate_move2_candidates([anchor], [FL], move2_window, no_dual_ownership=True)
    assert cands  # non-empty: sale_year_2 can equal purchase_year (2030)
    assert all(c.sale_year_2 >= anchor.purchase_year for c in cands)


# ---------------------------------------------------------------------------
# Move-2 anchoring (§3.2/§4)
# ---------------------------------------------------------------------------

def test_move2_anchors_exclude_rent_indefinitely_forever_outcomes():
    rent_forever = HousingCandidate(location_1=TX, sale_year=2027, purchase_year=None)
    owned = HousingCandidate(location_1=TX, sale_year=2027, purchase_year=2028)
    ranked = [
        ScoredCandidate(candidate=rent_forever, net_worth=10.0, lifetime_cost=1.0,
                         mc_success_rate=None, sec121_exclusion_lost=[False]),
        ScoredCandidate(candidate=owned, net_worth=9.0, lifetime_cost=1.0,
                         mc_success_rate=None, sec121_exclusion_lost=[False]),
    ]
    anchors = select_anchors(ranked, anchor_count=5)
    assert anchors == [owned]


def test_move2_anchors_respect_anchor_count():
    scored = [
        ScoredCandidate(candidate=HousingCandidate(location_1=TX, sale_year=2027, purchase_year=2027 + i),
                         net_worth=100.0 - i, lifetime_cost=1.0, mc_success_rate=None,
                         sec121_exclusion_lost=[False])
        for i in range(10)
    ]
    anchors = select_anchors(scored, anchor_count=3)
    assert len(anchors) == 3
    assert [a.purchase_year for a in anchors] == [2027, 2028, 2029]


def test_generate_move2_candidates_skips_rent_indefinitely_move1_anchor():
    rent_forever = HousingCandidate(location_1=TX, sale_year=2027, purchase_year=None)
    move2_window = Move2Window(latest_sale_year_2=2035, latest_purchase_year_2=2036)
    cands = generate_move2_candidates([rent_forever], [FL], move2_window, no_dual_ownership=True)
    assert cands == []


# ---------------------------------------------------------------------------
# family_presence hard filter (§3.1.2/§3.2.2)
# ---------------------------------------------------------------------------

def test_family_presence_none_always_passes():
    cand = HousingCandidate(location_1=TX, sale_year=2027, purchase_year=2028)
    ok, via_rental = family_presence_ok("Illinois", cand, None)
    assert ok is True
    assert via_rental is False


def test_family_presence_satisfied_by_current_home_before_the_move():
    cand = HousingCandidate(location_1=TX, sale_year=2030, purchase_year=2030)
    presence = FamilyPresence(region="Illinois", start_year=2026, end_year=2029)
    ok, via_rental = family_presence_ok("Illinois", cand, presence)
    assert ok is True
    assert via_rental is False


def test_family_presence_dropped_when_window_falls_outside_the_region():
    cand = HousingCandidate(location_1=TX, sale_year=2027, purchase_year=2028)
    presence = FamilyPresence(region="Illinois", start_year=2029, end_year=2031)
    ok, _via_rental = family_presence_ok("Illinois", cand, presence)
    assert ok is False


def test_family_presence_satisfied_via_rental_flag():
    cand = HousingCandidate(location_1=TX, sale_year=2027, purchase_year=None)  # rent indefinitely
    presence = FamilyPresence(region="Texas", start_year=2028, end_year=2030)
    ok, via_rental = family_presence_ok("Illinois", cand, presence)
    assert ok is True
    assert via_rental is True


def test_family_presence_satisfied_via_ownership_is_not_flagged_as_rental():
    cand = HousingCandidate(location_1=TX, sale_year=2027, purchase_year=2027)
    presence = FamilyPresence(region="Texas", start_year=2028, end_year=2030)
    ok, via_rental = family_presence_ok("Illinois", cand, presence)
    assert ok is True
    assert via_rental is False


def test_family_presence_checked_across_full_two_move_timeline():
    cand = HousingCandidate(location_1=TX, sale_year=2027, purchase_year=2027,
                             location_2=FL, sale_year_2=2035, purchase_year_2=2035)
    # Presence window spans the move-2 gap year -- must resolve to Florida there.
    presence_ok = FamilyPresence(region="Florida", start_year=2035, end_year=2040)
    presence_bad = FamilyPresence(region="Texas", start_year=2036, end_year=2040)
    ok1, _ = family_presence_ok("Illinois", cand, presence_ok)
    ok2, _ = family_presence_ok("Illinois", cand, presence_bad)
    assert ok1 is True
    assert ok2 is False


# ---------------------------------------------------------------------------
# §121 informational flag (not a tax-computation change -- see module docstring)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("purchase_year,sale_year,expected", [
    (2027, 2028, True),   # < 2 years owned -- test would fail
    (2027, 2029, False),  # exactly 2 years -- test passes
    (2020, 2030, False),  # well past 2 years
    (None, 2030, False),  # nothing purchased under this leg -- nothing to flag
])
def test_sec121_exclusion_flag_is_purely_informational_years_owned_check(purchase_year, sale_year, expected):
    assert sec121_exclusion_flag(purchase_year, sale_year) is expected


# ---------------------------------------------------------------------------
# Scoring / ranking per objective
# ---------------------------------------------------------------------------

def _scored(net_worth, lifetime_cost, mc_success_rate=None):
    cand = HousingCandidate(location_1=TX, sale_year=2027, purchase_year=2028)
    return ScoredCandidate(candidate=cand, net_worth=net_worth, lifetime_cost=lifetime_cost,
                            mc_success_rate=mc_success_rate, sec121_exclusion_lost=[False])


def test_rank_candidates_net_worth_is_descending():
    scored = [_scored(100, 5), _scored(300, 5), _scored(200, 5)]
    ranked = rank_candidates(scored, "net_worth")
    assert [s.net_worth for s in ranked] == [300, 200, 100]


def test_rank_candidates_lifetime_cost_is_ascending_lower_is_better():
    scored = [_scored(100, 30), _scored(100, 10), _scored(100, 20)]
    ranked = rank_candidates(scored, "lifetime_cost")
    assert [s.lifetime_cost for s in ranked] == [10, 20, 30]


def test_rank_candidates_mc_success_rate_falls_back_to_net_worth_when_unset():
    scored = [_scored(100, 5, mc_success_rate=None), _scored(300, 5, mc_success_rate=None)]
    ranked = rank_candidates(scored, "mc_success_rate")
    assert [s.net_worth for s in ranked] == [300, 100]


def test_rank_candidates_mc_success_rate_uses_the_computed_rate_when_present():
    scored = [_scored(300, 5, mc_success_rate=0.70), _scored(100, 5, mc_success_rate=0.95)]
    ranked = rank_candidates(scored, "mc_success_rate")
    assert [s.mc_success_rate for s in ranked] == [0.95, 0.70]


# ---------------------------------------------------------------------------
# Request-adapter validation (no engine call needed for these error paths)
# ---------------------------------------------------------------------------

def test_request_adapter_rejects_fewer_than_two_locations():
    payload, status = optimize_housing_from_request({}, {"locations": [{"state": "Texas"}]})
    assert status == 400
    assert payload["success"] is False


def test_request_adapter_rejects_more_than_four_locations():
    body = {"locations": [{"state": "Texas"}] * 5}
    payload, status = optimize_housing_from_request({}, body)
    assert status == 400
    assert payload["success"] is False


def test_request_adapter_rejects_unknown_objective():
    body = {
        "locations": [{"state": "Texas"}, {"state": "Florida"}],
        "move1_window": {"earliest_sale_year": 2027, "latest_sale_year": 2027,
                          "earliest_purchase_year": 2027, "latest_purchase_year": 2027},
        "objective": "not_a_real_objective",
    }
    payload, status = optimize_housing_from_request({}, body)
    assert status == 400
    assert "objective" in payload["error"].lower()
