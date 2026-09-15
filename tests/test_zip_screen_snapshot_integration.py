"""The bundled snapshot must satisfy the schema the runtime assumes."""
from __future__ import annotations

import os

import pytest

from src.housing.zip_screen.quality import score_zip
from src.housing.zip_screen.schema import COLUMNS
from src.housing.zip_screen.table import clear_cache, default_table_path, load_table

pytestmark = pytest.mark.integration

PILOT_STATES = {'Illinois', 'Florida', 'Colorado'}


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def table():
    if not os.path.exists(default_table_path()):
        pytest.skip('snapshot not built; run scripts/build_zip_metrics.py')
    return load_table()


def test_snapshot_covers_the_three_pilot_states(table):
    assert PILOT_STATES <= {r.state for r in table.values()}


def test_snapshot_has_a_plausible_pilot_row_count(table):
    assert 2500 <= len(table) <= 5000


def test_every_row_has_usable_coordinates(table):
    for rec in table.values():
        assert -180.0 <= rec.lon <= 180.0
        assert 15.0 <= rec.lat <= 72.0


def test_percentiles_are_all_within_zero_and_one(table):
    for rec in table.values():
        for col in COLUMNS:
            if not col.startswith('pctl_'):
                continue
            v = getattr(rec, col, None)
            if v is not None:
                assert 0.0 <= v <= 1.0, f'{rec.zcta}.{col} = {v}'


def test_the_pdf_reference_zips_are_present_and_scoreable(table):
    for zcta in ('60521', '60115'):
        assert zcta in table
        assert 0.0 <= score_zip(table[zcta]).score <= 100.0


def test_hinsdale_outscores_the_high_poverty_chicago_zip(table):
    assert score_zip(table['60521']).score > score_zip(table['60623']).score


def test_dekalb_is_upi_adjusted(table):
    # NIU puts 60115's UPI well above the 15% threshold.
    assert table['60115'].upi > 0.15
    assert score_zip(table['60115']).upi_adjusted is True


def test_most_rows_clear_the_coverage_floor(table):
    scored = [score_zip(r) for r in table.values()]
    clearing = sum(1 for s in scored if s.coverage_pct >= 70.0)
    assert clearing / len(scored) > 0.80


def test_top_cities_file_resolves_anchors(table):
    import csv
    path = os.path.join(os.path.dirname(default_table_path()), 'top_cities.csv')
    with open(path, encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) >= 200
    pilot = [r for r in rows if r['state'] in PILOT_STATES]
    assert pilot
    for r in pilot:
        assert r['anchor_zip'] in table, f"{r['city']} anchor missing"
