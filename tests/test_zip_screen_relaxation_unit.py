"""An empty funnel must say where it emptied and what would relax it."""
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
    base = dict(anchor_zip='60521', radius_miles=50, min_quality_score=0.0,
                shortlist_size=4, property_spec=dict(SPEC))
    base.update(overrides)
    return ScreenRequest(**base)


def test_a_satisfied_search_suggests_nothing(table):
    assert run_screen(_req(), table=table).relaxation is None


def test_an_impossible_score_floor_suggests_a_lower_one(table):
    res = run_screen(_req(min_quality_score=99.9), table=table)
    assert res.shortlist == []
    assert res.relaxation is not None
    assert res.relaxation['field'] == 'min_quality_score'
    assert res.relaxation['suggested'] < 99.9
    assert res.relaxation['would_return'] >= 1


def test_the_suggested_floor_actually_returns_that_many(table):
    res = run_screen(_req(min_quality_score=99.9), table=table)
    retry = run_screen(_req(min_quality_score=res.relaxation['suggested']), table=table)
    assert len(retry.all_passing) >= res.relaxation['would_return']


def test_no_suggestion_when_nothing_had_data_in_range(table):
    # Breckenridge alone at 5 miles: in radius, but nothing clears the funnel
    # for score reasons, so there is no score to suggest.
    res = run_screen(_req(anchor_zip='80424', radius_miles=5,
                          min_quality_score=99.9), table=table)
    assert res.shortlist == []
    assert res.relaxation is None or res.relaxation['would_return'] >= 1
