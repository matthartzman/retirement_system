"""Wire contract for the ``POST /api/housing/zip-screen`` "Preview shortlist"
endpoint (design 2026-09-16 §7.3): a ``{'search': {...}}`` block, the same
shape as ``move1.search``/``move2.search``, screened via
``run_multi_anchor_screen`` -- no engine runs."""
from __future__ import annotations

import pytest

from src.housing.api import zip_screen_from_request

pytestmark = pytest.mark.contract

FIXTURE = 'tests/fixtures/zip_metrics_sample.csv'

DWELLING = {
    'bedrooms': 3, 'bathrooms': 2.0, 'property_type': 'single_family',
    'sqft_band': '1800_2500', 'built_within_years': None,
}

C0 = {'state': 'Illinois'}


def _body(**overrides):
    search = {
        'anchors': [{'kind': 'zip', 'anchor_zip': '60521'},
                   {'kind': 'zip', 'anchor_zip': '60540'}],
        'radius_miles': 25, 'min_quality_score': 60,
        'area_type': 'any', 'max_population': None,
        'shortlist_size': 4, 'dwelling': dict(DWELLING),
    }
    search.update(overrides.pop('search', {}))
    body = {'search': search}
    body.update(overrides)
    return body


def test_valid_body_returns_200():
    payload, status = zip_screen_from_request(C0, _body(), table_path=FIXTURE)
    assert status == 200
    assert payload['success'] is True


def test_response_carries_the_schema_and_model_version():
    payload, _ = zip_screen_from_request(C0, _body(), table_path=FIXTURE)
    assert payload['zip_screen']['schema'] == 'zip_screen_v2'
    assert payload['zip_screen']['score_model'] == 'nss-1.0'


def test_response_carries_the_disclosure_string():
    payload, _ = zip_screen_from_request(C0, _body(), table_path=FIXTURE)
    assert payload['zip_screen']['disclosure'] == (
        'Measures housing and economic stability. Does not measure crime or safety.'
    )


def test_response_carries_the_funnel():
    payload, _ = zip_screen_from_request(C0, _body(), table_path=FIXTURE)
    assert set(payload['zip_screen']['funnel']) >= {
        'in_radius', 'with_data', 'above_score', 'matching_area_type',
        'under_population_cap', 'affordable', 'distinct', 'near_family', 'promoted',
    }


def test_response_carries_the_anchors_list():
    payload, _ = zip_screen_from_request(C0, _body(), table_path=FIXTURE)
    assert [a['zip'] for a in payload['zip_screen']['anchors']] == ['60521', '60540']


@pytest.mark.parametrize('bad', [0, 3, 15, 100, -5, 'twenty'])
def test_bad_radius_is_a_400(bad):
    payload, status = zip_screen_from_request(
        C0, _body(search={'radius_miles': bad}), table_path=FIXTURE)
    assert status == 400
    assert 'radius_miles' in payload['error']


def test_missing_search_is_a_400():
    payload, status = zip_screen_from_request(C0, {}, table_path=FIXTURE)
    assert status == 400
    assert 'search' in payload['error']


def test_single_anchor_is_valid():
    # Housing move anchors now accept 1-5 (was 2-5) -- see
    # src/housing/api.py parse_move_search.
    payload, status = zip_screen_from_request(
        C0, _body(search={'anchors': [{'kind': 'zip', 'anchor_zip': '60521'}]}),
        table_path=FIXTURE)
    assert status == 200
    assert payload['success'] is True


def test_zero_anchors_is_a_400():
    payload, status = zip_screen_from_request(
        C0, _body(search={'anchors': []}),
        table_path=FIXTURE)
    assert status == 400
    assert 'anchors' in payload['error'].lower()


def test_unknown_anchor_is_a_400_naming_the_zip():
    payload, status = zip_screen_from_request(
        C0, _body(search={'anchors': [{'kind': 'zip', 'anchor_zip': '99999'},
                                      {'kind': 'zip', 'anchor_zip': '60521'}]}),
        table_path=FIXTURE)
    assert status == 400
    assert '99999' in payload['error']


def test_shortlist_size_is_clamped_to_two_through_five():
    for requested, expected in ((1, 2), (9, 5)):
        payload, _ = zip_screen_from_request(
            C0, _body(search={'shortlist_size': requested, 'min_quality_score': 0}),
            table_path=FIXTURE)
        assert len(payload['zip_screen']['shortlist']) <= expected


def test_shortlist_rows_carry_the_documented_fields():
    payload, _ = zip_screen_from_request(
        C0, _body(search={'min_quality_score': 0}), table_path=FIXTURE)
    row = payload['zip_screen']['shortlist'][0]
    for key in ('zip', 'city', 'state', 'distance_miles', 'nss', 'band',
                'components', 'coverage_pct', 'est_price', 'cross_state',
                'promoted', 'collapsed', 'area_type', 'population',
                'nearest_anchor_zip', 'family_distance_miles'):
        assert key in row
