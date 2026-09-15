"""build_top_cities anchors on land-overlap, not centroid distance."""
from __future__ import annotations

import csv
import gzip
import io
import os
import tempfile

import pytest

from scripts.build_zip_metrics import build_top_cities

pytestmark = pytest.mark.unit


def _write_snapshot(path, rows):
    """A minimal gzipped CSV matching the real snapshot's column set, for
    just the fields build_top_cities actually reads."""
    fieldnames = ['zcta', 'state', 'state_abbrev', 'lat', 'lon',
                  'zcta_population', 'place_gid', 'place_area_m2']
    with gzip.open(path, 'wt', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _rel_row(zcta, place, area):
    """A row in the real ZCTA<->place relationship file's 17-field layout,
    populated only at the fields build_top_cities reads: index 1 (ZCTA
    GEOID), index 9 (place GEOID), index 16 (AREALAND_PART)."""
    row = [''] * 17
    row[1] = zcta
    row[9] = place
    row[16] = area
    return row


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Isolate the REL/Gazetteer/ACS fetch helpers this test stubs out."""
    d = tmp_path
    monkeypatch.chdir(d)
    return d


def test_anchor_prefers_largest_land_overlap_over_nearest_centroid(workdir, monkeypatch):
    # Two ZCTAs "near" a fictional city's centroid: 00001 is geographically
    # nearer to the place's INTPTLAT/INTPTLONG but has almost no land overlap
    # with the place (e.g. it's a neighboring town's ZIP that happens to be
    # close by); 00002 is farther from the raw centroid but has the large
    # land-overlap that actually makes it "the city's ZIP."
    import scripts.build_zip_metrics as bzm

    snapshot_path = os.path.join(workdir, 'zip_metrics.csv.gz')
    _write_snapshot(snapshot_path, [
        {'zcta': '00001', 'state': 'Illinois', 'state_abbrev': 'IL',
         'lat': '41.900', 'lon': '-87.900', 'zcta_population': '500'},
        {'zcta': '00002', 'state': 'Illinois', 'state_abbrev': 'IL',
         'lat': '41.700', 'lon': '-87.700', 'zcta_population': '40000'},
    ])

    # NAME matches the real Gazetteer place file's format: just the place
    # name + type suffix, no trailing ", <State>" (unlike the ZCTA<->place
    # relationship file's NAMELSAD_PLACE_20, which the committed
    # top_cities.csv confirms -- e.g. "New York" from "New York city").
    monkeypatch.setattr(bzm, '_gazetteer', lambda url, name: [
        {'GEOID': '1729000', 'USPS': 'IL', 'NAME': 'Faketown city',
         'INTPTLAT': '41.905', 'INTPTLONG': '-87.905'},
    ])
    monkeypatch.setattr(bzm, '_acs_table', lambda table, prefixes: {
        f'{bzm.P_PLACE}1729000': {'001': 45000.0},
    })
    # 00001: tiny overlap with the place. 00002: dominant overlap.
    # Rows follow the real ZCTA<->place relationship file's column layout
    # (17 pipe-delimited fields), matching the r[1]/r[9]/r[16] convention
    # build_top_cities and build() both use: index 1 is the ZCTA GEOID,
    # index 9 is the place GEOID, index 16 is AREALAND_PART.
    monkeypatch.setattr(bzm, '_relationship', lambda url, name: (
        ['GEOID_ZCTA5_20', 'GEOID_PLACE_20', 'NAMELSAD_PLACE_20', 'AREALAND_PART'],
        [
            _rel_row(zcta='00001', place='1729000', area='5000'),
            _rel_row(zcta='00002', place='1729000', area='5000000'),
        ],
    ))

    out_path = os.path.join(workdir, 'top_cities.csv')
    n = build_top_cities(out_path, snapshot_path, limit=10)

    assert n == 1
    with open(out_path, newline='', encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]['anchor_zip'] == '00002'
    assert rows[0]['city'] == 'Faketown'


def test_anchor_never_selects_a_zero_population_zcta(workdir, monkeypatch):
    import scripts.build_zip_metrics as bzm

    snapshot_path = os.path.join(workdir, 'zip_metrics.csv.gz')
    _write_snapshot(snapshot_path, [
        {'zcta': '00003', 'state': 'Illinois', 'state_abbrev': 'IL',
         'lat': '41.900', 'lon': '-87.900', 'zcta_population': '0'},
        {'zcta': '00004', 'state': 'Illinois', 'state_abbrev': 'IL',
         'lat': '41.910', 'lon': '-87.910', 'zcta_population': '12000'},
    ])
    monkeypatch.setattr(bzm, '_gazetteer', lambda url, name: [
        {'GEOID': '1729000', 'USPS': 'IL', 'NAME': 'Faketown city',
         'INTPTLAT': '41.900', 'INTPTLONG': '-87.900'},
    ])
    monkeypatch.setattr(bzm, '_acs_table', lambda table, prefixes: {
        f'{bzm.P_PLACE}1729000': {'001': 45000.0},
    })
    # 00003 (zero population) has the largest raw overlap; 00004 is second.
    monkeypatch.setattr(bzm, '_relationship', lambda url, name: (
        ['GEOID_ZCTA5_20', 'GEOID_PLACE_20', 'NAMELSAD_PLACE_20', 'AREALAND_PART'],
        [
            _rel_row(zcta='00003', place='1729000', area='9000000'),
            _rel_row(zcta='00004', place='1729000', area='3000000'),
        ],
    ))

    out_path = os.path.join(workdir, 'top_cities.csv')
    build_top_cities(out_path, snapshot_path, limit=10)

    with open(out_path, newline='', encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]['anchor_zip'] == '00004'
