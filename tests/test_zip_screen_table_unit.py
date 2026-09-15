"""Loading the bundled ZCTA snapshot. The only module that reads the file."""
from __future__ import annotations

import pytest

from src.housing.zip_screen.table import clear_cache, load_table

pytestmark = pytest.mark.unit

FIXTURE = 'tests/fixtures/zip_metrics_sample.csv'


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


def test_loads_every_fixture_row_keyed_by_zcta():
    table = load_table(FIXTURE)
    assert len(table) == 12
    assert '60521' in table
    assert table['60521'].primary_place == 'Hinsdale'


def test_numeric_columns_are_parsed():
    rec = load_table(FIXTURE)['60521']
    assert rec.lat == pytest.approx(41.8007)
    assert rec.place_population == 17395
    assert rec.pctl_owner_occupied == pytest.approx(0.94)


def test_empty_percentile_cells_become_none_not_zero():
    rec = load_table(FIXTURE)['60187']
    assert rec.pctl_eviction_execution is None
    assert rec.pctl_eviction_filing is None
    assert rec.pctl_owner_occupied == pytest.approx(0.84)


def test_zcta_is_kept_as_a_string_preserving_leading_zeros():
    table = load_table(FIXTURE)
    assert isinstance(table['60521'].zcta, str)


def test_density_is_derived_not_stored():
    rec = load_table(FIXTURE)['60623']
    assert rec.density == pytest.approx(88000 / 4.6)


def test_second_load_is_served_from_cache():
    first = load_table(FIXTURE)
    second = load_table(FIXTURE)
    assert first is second


def test_missing_file_raises_a_named_error():
    with pytest.raises(FileNotFoundError, match='zip_metrics'):
        load_table('tests/fixtures/does_not_exist_zip_metrics.csv')
