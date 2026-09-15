"""Wire contract for zip_search parsing and the screen-only endpoint."""
from __future__ import annotations

import pytest

from src.housing.api import zip_screen_from_request

pytestmark = pytest.mark.contract

SPEC = {
    'bedrooms': 3, 'bathrooms': 2.0, 'property_type': 'single_family',
    'sqft_band': '1800_2500', 'built_within_years': None,
}

C0 = {'state': 'Illinois'}


def _body(**overrides):
    zs = {'anchor': {'zip': '60521'}, 'radius_miles': 25,
          'min_quality_score': 60, 'shortlist_size': 4,
          'property_spec': dict(SPEC)}
    zs.update(overrides.pop('zip_search', {}))
    body = {'zip_search': zs}
    body.update(overrides)
    return body


def test_valid_body_returns_200(monkeypatch):
    payload, status = zip_screen_from_request(C0, _body(), table_path='tests/fixtures/zip_metrics_sample.csv')
    assert status == 200
    assert payload['success'] is True


def test_response_carries_the_schema_and_model_version():
    payload, _ = zip_screen_from_request(C0, _body(), table_path='tests/fixtures/zip_metrics_sample.csv')
    assert payload['zip_screen']['schema'] == 'zip_screen_v1'
    assert payload['zip_screen']['score_model'] == 'nss-1.0'


def test_response_carries_the_disclosure_string():
    payload, _ = zip_screen_from_request(C0, _body(), table_path='tests/fixtures/zip_metrics_sample.csv')
    assert payload['zip_screen']['disclosure'] == (
        'Measures housing and economic stability. Does not measure crime or safety.'
    )


def test_response_carries_the_funnel():
    payload, _ = zip_screen_from_request(C0, _body(), table_path='tests/fixtures/zip_metrics_sample.csv')
    assert set(payload['zip_screen']['funnel']) >= {
        'in_radius', 'with_data', 'above_score', 'affordable', 'after_dedup', 'promoted'
    }


@pytest.mark.parametrize('bad', [0, 3, 15, 100, -5, 'twenty'])
def test_bad_radius_is_a_400(bad):
    payload, status = zip_screen_from_request(
        C0, _body(zip_search={'radius_miles': bad}),
        table_path='tests/fixtures/zip_metrics_sample.csv')
    assert status == 400
    assert 'radius_miles' in payload['error']


def test_missing_zip_search_is_a_400():
    payload, status = zip_screen_from_request(C0, {}, table_path='tests/fixtures/zip_metrics_sample.csv')
    assert status == 400
    assert 'zip_search' in payload['error']


def test_unknown_anchor_is_a_400_naming_the_zip():
    payload, status = zip_screen_from_request(
        C0, _body(zip_search={'anchor': {'zip': '99999'}}),
        table_path='tests/fixtures/zip_metrics_sample.csv')
    assert status == 400
    assert '99999' in payload['error']


def test_shortlist_size_is_clamped_to_two_through_four():
    for requested, expected in ((1, 2), (9, 4)):
        payload, _ = zip_screen_from_request(
            C0, _body(zip_search={'shortlist_size': requested, 'min_quality_score': 0}),
            table_path='tests/fixtures/zip_metrics_sample.csv')
        assert len(payload['zip_screen']['shortlist']) <= expected


def test_shortlist_rows_carry_the_documented_fields():
    payload, _ = zip_screen_from_request(
        C0, _body(zip_search={'min_quality_score': 0}),
        table_path='tests/fixtures/zip_metrics_sample.csv')
    row = payload['zip_screen']['shortlist'][0]
    for key in ('zip', 'city', 'state', 'distance_miles', 'nss', 'band',
                'components', 'coverage_pct', 'est_price', 'cross_state',
                'promoted', 'collapsed'):
        assert key in row
