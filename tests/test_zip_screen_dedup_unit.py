"""De-duplication: four adjacent suburbs of one town are not four bets."""
from __future__ import annotations

import pytest

from src.housing.zip_screen.screen import ScreenRequest, run_screen
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
    base = dict(anchor_zip='80206', radius_miles=50, min_quality_score=0.0,
                shortlist_size=4, property_spec=dict(SPEC))
    base.update(overrides)
    return ScreenRequest(**base)


def test_the_denver_cluster_collapses_to_one_survivor(table):
    # 80206/80209/80210 are all within 5 miles, same state, within 5 NSS points.
    res = run_screen(_req(), table=table)
    denver = [z for z in res.shortlist if z.zcta in ('80206', '80209', '80210')]
    assert len(denver) == 1


def test_collapsed_neighbours_are_returned_not_dropped(table):
    res = run_screen(_req(), table=table)
    survivor = next(z for z in res.shortlist if z.zcta in ('80206', '80209', '80210'))
    assert set(survivor.collapsed) == {'80206', '80209', '80210'} - {survivor.zcta}


def test_the_highest_scoring_member_of_a_cluster_survives(table):
    res = run_screen(_req(), table=table)
    survivor = next(z for z in res.shortlist if z.zcta in ('80206', '80209', '80210'))
    assert survivor.zcta == '80209'


def test_a_distant_zip_is_never_collapsed(table):
    # 80424 (Breckenridge) is ~65 miles from Denver -- outside a 50-mile radius
    # entirely, and would not be collapsed even if it were in range.
    res = run_screen(_req(), table=table)
    assert all('80424' not in z.collapsed for z in res.shortlist)


def test_a_nearby_zip_with_a_distant_score_is_not_collapsed(table):
    # Score-gap guard: different bets stay separate even when adjacent.
    res = run_screen(ScreenRequest(
        anchor_zip='60521', radius_miles=50, min_quality_score=0.0,
        shortlist_size=4, property_spec=dict(SPEC),
    ), table=table)
    zctas = {z.zcta for z in res.shortlist}
    assert '60521' in zctas
    assert '60623' not in {c for z in res.shortlist for c in z.collapsed}


def test_funnel_after_dedup_reflects_the_collapse(table):
    res = run_screen(_req(), table=table)
    assert res.funnel['after_dedup'] < res.funnel['affordable']


def test_dedup_never_reduces_below_what_was_available(table):
    res = run_screen(_req(shortlist_size=4), table=table)
    assert res.funnel['promoted'] <= res.funnel['after_dedup']
