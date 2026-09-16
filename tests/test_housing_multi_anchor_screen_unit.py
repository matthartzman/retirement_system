"""Union-then-dedup across 2-5 anchors (design 2026-09-16 §6.1)."""
import pytest

from src.housing.zip_screen.screen import MultiAnchorRequest, run_multi_anchor_screen
from tests.test_zip_screen_filters_unit import _rec

pytestmark = pytest.mark.unit


def _table():
    # Two anchors ~34 miles apart, with one ZIP sitting between them. 80002 is
    # deliberately >DEDUP_RADIUS_MILES (5.0) from 80001: these fixtures share
    # percentiles, so anything closer would be collapsed by dedup and look
    # like a filter bug rather than the near-duplicate suppression it is.
    return {
        '80001': _rec('80001', lat=39.70, lon=-104.90, place_pop=500000),
        '80002': _rec('80002', lat=39.82, lon=-104.90, place_pop=40000),
        '90001': _rec('90001', lat=40.20, lon=-104.90, place_pop=60000),
    }


def _req(**kw):
    kw.setdefault('anchor_zips', ['80001', '90001'])
    kw.setdefault('radius_miles', 50)
    kw.setdefault('min_quality_score', 0)
    kw.setdefault('shortlist_size', 5)
    kw.setdefault('property_spec', {})
    kw.setdefault('area_type', 'any')
    kw.setdefault('max_population', None)
    return MultiAnchorRequest(**kw)


def test_a_zip_in_both_radii_appears_exactly_once():
    result = run_multi_anchor_screen(_req(), table=_table())
    zctas = [z.zcta for z in result.shortlist]
    assert len(zctas) == len(set(zctas))


def test_distance_is_measured_to_the_nearest_anchor():
    result = run_multi_anchor_screen(_req(), table=_table())
    z = next(z for z in result.shortlist if z.zcta == '80002')
    assert z.nearest_anchor_zip == '80001'
    assert z.distance_miles < 10


def test_every_anchor_is_reported_for_display():
    result = run_multi_anchor_screen(_req(), table=_table())
    assert [a['zip'] for a in result.anchors] == ['80001', '90001']


def test_funnel_counts_the_union_not_the_sum_of_per_anchor_runs():
    """Summing per-anchor funnels would double-count the overlap and make the
    displayed 'N ZIPs in range' larger than the number of distinct ZIPs."""
    result = run_multi_anchor_screen(_req(), table=_table())
    assert result.funnel['in_radius'] == 3


def test_a_single_anchor_behaves_exactly_like_the_one_anchor_screen():
    result = run_multi_anchor_screen(_req(anchor_zips=['80001'], radius_miles=25),
                                     table=_table())
    assert result.anchors[0]['zip'] == '80001'
    assert all(z.nearest_anchor_zip == '80001' for z in result.shortlist)
