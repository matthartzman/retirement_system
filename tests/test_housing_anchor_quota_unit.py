"""Per-anchor reserved slot in the multi-anchor screen (design 2026-09-19 §5.2).

Before this, ``run_multi_anchor_screen`` promoted the global top-N by score,
so a household anchoring on two metros could receive a shortlist drawn
entirely from one of them -- the second anchor contributing zero candidates,
with nothing in the payload to notice (§1.1). The quota reserves one slot per
declared anchor before the open pass fills the rest.
"""
import pytest

from src.housing.zip_screen.schema import HIGHER_IS_BETTER, PCTL_COLUMN, ZipRecord
from src.housing.zip_screen.screen import MultiAnchorRequest, run_multi_anchor_screen

pytestmark = pytest.mark.unit


def _rec(zcta, *, lat, goodness, place_pop=100000, state='Colorado'):
    """A record whose NSS is exactly ``goodness * 100``.

    ``score_zip`` blends higher-is-better metrics (100 * pctl) with
    lower-is-better ones (100 * (1 - pctl)), so setting each column to the
    percentile that scores ``goodness`` for its own direction makes the
    weighted mean collapse to ``100 * goodness`` whatever the weights are.
    That is what lets these fixtures state a score ordering outright rather
    than depending on the weight table.
    """
    pctls = {
        column: (goodness if metric in HIGHER_IS_BETTER else 1.0 - goodness)
        for metric, column in PCTL_COLUMN.items()
    }
    # Eviction Lab columns are empty for every ZIP in the shipped snapshot;
    # leaving them None here keeps these fixtures at the real 78.8% coverage
    # rather than a tier no production row reaches.
    pctls['pctl_eviction_execution'] = None
    pctls['pctl_eviction_filing'] = None
    return ZipRecord(
        zcta=zcta, state=state, state_abbrev='CO', primary_place=f'Place{zcta}',
        place_population=place_pop, zcta_population=100000, land_area_sqmi=10.0,
        lat=lat, lon=-104.90, median_home_value=400000,
        state_median_home_value=400000, upi=0.02,
        pctl_non_student_poverty=pctls['pctl_poverty'],
        pctl_tenure_nonstudent=pctls['pctl_tenure'],
        **pctls,
    )


def _table():
    # Three high-scoring ZIPs around anchor A (80001) and one lower-scoring
    # ZIP out by anchor B (90001), which is itself 62 miles from A and so
    # reachable only from its own anchor. Neighbours sit ~8 miles apart,
    # above DEDUP_RADIUS_MILES (5.0), so dedup keeps all four and the quota
    # is the only thing shaping the shortlist.
    return {
        '80001': _rec('80001', lat=39.70, goodness=0.90, place_pop=500000),
        '80002': _rec('80002', lat=39.82, goodness=0.88, place_pop=40000),
        '80003': _rec('80003', lat=39.94, goodness=0.86, place_pop=40000),
        '90001': _rec('90001', lat=40.60, goodness=0.40, place_pop=60000),
    }


def _req(**kw):
    kw.setdefault('anchor_zips', ['80001', '90001'])
    kw.setdefault('radius_miles', 50)
    kw.setdefault('min_quality_score', 0)
    kw.setdefault('shortlist_size', 3)
    kw.setdefault('property_spec', {})
    kw.setdefault('area_type', 'any')
    kw.setdefault('max_population', None)
    return MultiAnchorRequest(**kw)


def test_without_the_quota_the_second_anchor_would_have_been_shut_out():
    """The fixture must actually reproduce §1.1, or the test below proves
    nothing. Score order alone puts all three of anchor A's ZIPs ahead of
    anchor B's, so the old ``distinct[:shortlist_size]`` promotion would have
    returned a shortlist with no B row in it at all."""
    result = run_multi_anchor_screen(_req(), table=_table())
    by_score = sorted(result.all_passing,
                      key=lambda z: (-z.nss, z.distance_miles, z.zcta))
    assert [z.nearest_anchor_zip for z in by_score[:3]] == ['80001'] * 3


def test_every_anchor_with_a_survivor_gets_a_shortlist_slot():
    result = run_multi_anchor_screen(_req(), table=_table())
    assert {z.nearest_anchor_zip for z in result.shortlist} == {'80001', '90001'}


def test_the_reserved_row_is_flagged_so_the_panel_can_badge_it():
    result = run_multi_anchor_screen(_req(), table=_table())
    assert '90001' in {z.zcta for z in result.shortlist if z.quota_reserved}


def test_the_open_pass_keeps_filling_in_score_order():
    result = run_multi_anchor_screen(_req(), table=_table())
    # One slot each to 80001 and 90001 by reservation; the third goes to the
    # next-highest scorer overall, which is 80002.
    assert {z.zcta for z in result.shortlist} == {'80001', '80002', '90001'}


def test_the_quota_costs_nothing_when_the_natural_top_n_already_covers():
    """Membership and order are both unchanged when every anchor was already
    represented -- the common case, and why §1.1 went unnoticed."""
    result = run_multi_anchor_screen(_req(shortlist_size=4), table=_table())
    expected = [z.zcta for z in sorted(
        result.all_passing, key=lambda z: (-z.nss, z.distance_miles, z.zcta))[:4]]
    assert [z.zcta for z in result.shortlist] == expected


def test_the_shortlist_is_still_presented_in_score_order():
    result = run_multi_anchor_screen(_req(), table=_table())
    keys = [(-z.nss, z.distance_miles, z.zcta) for z in result.shortlist]
    assert keys == sorted(keys)


def test_an_anchor_with_no_survivor_is_recorded_not_raised():
    # 70001 resolves as an anchor but sits ~350 miles from everything else,
    # so the only ZIP in its radius is itself -- and its own score is under
    # the floor.
    table = _table()
    table['70001'] = _rec('70001', lat=45.00, goodness=0.05, place_pop=1000)
    result = run_multi_anchor_screen(
        _req(anchor_zips=['80001', '70001'], min_quality_score=50), table=table)
    assert result.unrepresented_anchors == ['70001']
    assert result.shortlist, 'the surviving anchor still produced a shortlist'


def test_a_shortlist_too_small_to_seat_every_anchor_grows_to_fit():
    """The shipped default was 4 against up to 5 anchors (§1.1), so the cap
    could make the guarantee unsatisfiable in principle. It floors at the
    anchor count rather than dropping an anchor silently."""
    result = run_multi_anchor_screen(_req(shortlist_size=1), table=_table())
    assert {z.nearest_anchor_zip for z in result.shortlist} == {'80001', '90001'}


def test_a_zero_shortlist_still_promotes_nothing():
    result = run_multi_anchor_screen(_req(shortlist_size=0), table=_table())
    assert result.shortlist == []


def test_the_funnel_reports_how_many_slots_the_quota_claimed():
    result = run_multi_anchor_screen(_req(), table=_table())
    assert result.funnel['per_anchor_quota'] == 2
    assert result.funnel['promoted'] == 3


def test_a_single_anchor_run_is_unchanged_by_the_quota():
    result = run_multi_anchor_screen(
        _req(anchor_zips=['80001'], shortlist_size=2), table=_table())
    assert [z.zcta for z in result.shortlist] == ['80001', '80002']
    assert result.unrepresented_anchors == []
