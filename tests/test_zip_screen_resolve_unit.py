"""ZipRecord -> Location. The boundary where ZIPs stop existing."""
from __future__ import annotations

import pytest

from src.housing.models import Location
from src.housing.zip_screen.resolve import city_type_for_density, resolve_location
from src.housing.zip_screen.table import clear_cache, load_table

pytestmark = pytest.mark.unit

FIXTURE = 'tests/fixtures/zip_metrics_sample.csv'

SPEC = {
    'bedrooms': 4,
    'bathrooms': 2.5,
    'property_type': 'single_family',
    'sqft_band': '2500_3500',
    'built_within_years': 20,
    'target_purchase_price_range': (400000.0, 900000.0),
}


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.mark.parametrize('density,expected', [
    (12000.0, 'urban'),
    (3000.0, 'urban'),
    (2999.0, 'suburban'),
    (1000.0, 'suburban'),
    (999.0, 'exurban'),
    (200.0, 'exurban'),
    (199.0, 'rural'),
    (0.0, 'rural'),
])
def test_density_thresholds(density, expected):
    assert city_type_for_density(density) == expected


def test_resolves_state_from_the_record():
    loc = resolve_location(load_table(FIXTURE)['60521'], SPEC)
    assert loc.state == 'Illinois'


def test_resolves_city_type_from_density():
    table = load_table(FIXTURE)
    # 60623: 88000 people over 4.6 sq mi -> dense urban.
    assert resolve_location(table['60623'], SPEC).city_type == 'urban'
    # 80424: 6200 over 68.4 sq mi -> ~91/sq mi -> rural.
    assert resolve_location(table['80424'], SPEC).city_type == 'rural'


def test_population_size_prefers_the_primary_place():
    loc = resolve_location(load_table(FIXTURE)['60521'], SPEC)
    assert loc.population_size == 17395


def test_population_size_falls_back_to_zcta_population():
    table = load_table(FIXTURE)
    rec = table['60521'].__class__(
        zcta='99999', state='Illinois', lat=0.0, lon=0.0,
        place_population=0, zcta_population=8200, land_area_sqmi=10.0,
    )
    assert resolve_location(rec, SPEC).population_size == 8200


def test_property_spec_passes_through_untouched():
    loc = resolve_location(load_table(FIXTURE)['60521'], SPEC)
    assert loc.bedrooms == 4
    assert loc.bathrooms == 2.5
    assert loc.property_type == 'single_family'
    assert loc.sqft_band == '2500_3500'
    assert loc.built_within_years == 20
    assert loc.target_purchase_price_range == (400000.0, 900000.0)


def test_zip_code_is_carried_for_display():
    assert resolve_location(load_table(FIXTURE)['60521'], SPEC).zip_code == '60521'


def test_result_is_an_ordinary_location_the_optimizer_accepts():
    loc = resolve_location(load_table(FIXTURE)['60521'], SPEC)
    assert isinstance(loc, Location)


def test_location_without_a_zip_still_constructs():
    # The hand-pick path must be unaffected.
    assert Location(state='Texas').zip_code is None
