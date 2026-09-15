"""Distance math and the radius query (criterion 9)."""
from __future__ import annotations

import pytest

from src.housing.zip_screen.geo import (
    InvalidRadiusError,
    haversine_miles,
    zips_within,
)
from src.housing.zip_screen.table import clear_cache, load_table

pytestmark = pytest.mark.unit

FIXTURE = 'tests/fixtures/zip_metrics_sample.csv'


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


def test_distance_to_self_is_zero():
    assert haversine_miles(41.8, -87.9, 41.8, -87.9) == pytest.approx(0.0, abs=1e-9)


def test_known_distance_hinsdale_to_naperville():
    # ~11.5 miles apart; allow a mile of slack for centroid choice.
    d = haversine_miles(41.8007, -87.9370, 41.7508, -88.1535)
    assert 10.0 < d < 13.0


def test_distance_is_symmetric():
    a = haversine_miles(41.8007, -87.9370, 25.7050, -80.3020)
    b = haversine_miles(25.7050, -80.3020, 41.8007, -87.9370)
    assert a == pytest.approx(b)


def test_radius_includes_the_anchor_itself_at_zero_miles():
    table = load_table(FIXTURE)
    hits = zips_within(table, table['60521'], 25)
    assert any(r.zcta == '60521' and d == pytest.approx(0.0, abs=1e-9) for r, d in hits)


def test_radius_excludes_zips_beyond_it():
    table = load_table(FIXTURE)
    hits = {r.zcta for r, _ in zips_within(table, table['60521'], 5)}
    assert '60521' in hits
    assert '33143' not in hits
    assert '80206' not in hits


def test_larger_radius_is_a_superset_of_a_smaller_one():
    table = load_table(FIXTURE)
    small = {r.zcta for r, _ in zips_within(table, table['60521'], 10)}
    large = {r.zcta for r, _ in zips_within(table, table['60521'], 50)}
    assert small <= large


def test_results_are_sorted_by_distance():
    table = load_table(FIXTURE)
    distances = [d for _, d in zips_within(table, table['80206'], 50)]
    assert distances == sorted(distances)


def test_radius_crosses_state_lines():
    # A 50-mile radius must not be clipped at a state boundary (spec D4).
    table = load_table(FIXTURE)
    hits = zips_within(table, table['80206'], 50)
    assert all(isinstance(d, float) for _, d in hits)
    assert {r.state for r, _ in hits} == {'Colorado'}


@pytest.mark.parametrize('bad', [0, 3, 15, 100, -5])
def test_disallowed_radius_is_rejected(bad):
    table = load_table(FIXTURE)
    with pytest.raises(InvalidRadiusError, match='5, 10, 25, 50'):
        zips_within(table, table['60521'], bad)
