"""The Stage-1 funnel: radius, coverage, score floor, affordability."""
from __future__ import annotations

import pytest

from src.housing.zip_screen.screen import (
    AnchorNotFoundError,
    ScreenRequest,
    run_screen,
)
from src.housing.zip_screen.table import clear_cache, load_table

pytestmark = pytest.mark.unit

FIXTURE = 'tests/fixtures/zip_metrics_sample.csv'

SPEC = {
    'bedrooms': 3, 'bathrooms': 2.0, 'property_type': 'single_family',
    'sqft_band': '1800_2500', 'built_within_years': None,
    'target_purchase_price_range': None,
}


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def table():
    return load_table(FIXTURE)


def _req(**overrides) -> ScreenRequest:
    base = dict(
        anchor_zip='60521', radius_miles=50, min_quality_score=0.0,
        shortlist_size=4, property_spec=dict(SPEC),
    )
    base.update(overrides)
    return ScreenRequest(**base)


def test_unknown_anchor_is_named_in_the_error(table):
    with pytest.raises(AnchorNotFoundError, match='99999'):
        run_screen(_req(anchor_zip='99999'), table=table)


def test_funnel_reports_every_stage(table):
    res = run_screen(_req(), table=table)
    for key in ('in_radius', 'with_data', 'above_score', 'matching_area_type',
                'under_population_cap', 'affordable', 'distinct', 'near_family',
                'promoted'):
        assert key in res.funnel


def test_funnel_counts_are_monotonically_non_increasing(table):
    f = run_screen(_req(), table=table).funnel
    counts = [f['in_radius'], f['with_data'], f['above_score'],
              f['matching_area_type'], f['under_population_cap'],
              f['affordable'], f['distinct'], f['near_family'], f['promoted']]
    assert counts == sorted(counts, reverse=True)


def test_coverage_floor_drops_the_sparse_row(table):
    # 60950 has four metrics missing, putting it under COVERAGE_FLOOR_PCT.
    res = run_screen(_req(radius_miles=50), table=table)
    assert '60950' not in {z.zcta for z in res.shortlist}


def test_partial_coverage_above_the_floor_survives(table):
    # 60187 is missing only the two eviction metrics (78.8% coverage).
    res = run_screen(_req(shortlist_size=4, radius_miles=50), table=table)
    surviving = {z.zcta for z in res.all_passing}
    assert '60187' in surviving


def test_score_floor_is_applied(table):
    low = run_screen(_req(min_quality_score=0.0), table=table)
    high = run_screen(_req(min_quality_score=85.0), table=table)
    assert high.funnel['above_score'] < low.funnel['above_score']
    assert all(z.nss >= 85.0 for z in high.shortlist)


def test_affordability_filter_excludes_out_of_range_estimates(table):
    res = run_screen(
        _req(property_spec={**SPEC, 'target_purchase_price_range': (100000.0, 200000.0)}),
        table=table,
    )
    assert all(100000.0 <= z.est_price <= 200000.0 for z in res.shortlist)


def test_no_price_range_disables_the_affordability_filter(table):
    res = run_screen(_req(), table=table)
    assert res.funnel['affordable'] == res.funnel['above_score']


def test_shortlist_never_exceeds_the_requested_size(table):
    assert len(run_screen(_req(shortlist_size=2), table=table).shortlist) <= 2


def test_every_shortlisted_zip_carries_its_score_band_and_distance(table):
    for z in run_screen(_req(), table=table).shortlist:
        assert 0.0 <= z.nss <= 100.0
        assert z.band
        assert z.distance_miles >= 0.0
        assert z.components


def test_cross_state_is_null_within_the_plan_state(table):
    res = run_screen(_req(), table=table, current_state='Illinois')
    il = [z for z in res.shortlist if z.state == 'Illinois']
    assert il and all(z.cross_state is None for z in il)


def test_cross_state_is_flagged_when_the_state_differs(table):
    res = run_screen(_req(anchor_zip='33143', radius_miles=50), table=table,
                     current_state='Illinois')
    assert res.shortlist
    assert all(z.cross_state == 'Florida' for z in res.shortlist)
