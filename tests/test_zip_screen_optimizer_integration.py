"""zip_search drives the real optimizer through resolved Locations."""
from __future__ import annotations

import pytest

from src.housing.api import optimize_housing_from_request

from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
from conftest import TEST_INPUT_DIR

pytestmark = pytest.mark.integration

FIXTURE = 'tests/fixtures/zip_metrics_sample.csv'

SPEC = {
    'bedrooms': 3, 'bathrooms': 2.0, 'property_type': 'single_family',
    'sqft_band': '1800_2500', 'built_within_years': None,
}


def _base_config():
    """The same engine config the existing housing integration suite uses
    (tests/test_housing_optimizer_integration.py:20). Skips itself on a fresh
    worktree, where input/ is gitignored."""
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        return ensure_engine_config(dict(c), source="test")


def _body(**overrides):
    body = {
        'zip_search': {
            'anchor': {'zip': '60521'}, 'radius_miles': 50,
            'min_quality_score': 0, 'shortlist_size': 2,
            'property_spec': dict(SPEC),
        },
        'move1_window': {
            'earliest_sale_year': 2028, 'latest_sale_year': 2029,
            'earliest_purchase_year': 2028, 'latest_purchase_year': 2029,
        },
        'objective': 'net_worth',
        'search_mode': 'narrowed',
    }
    body.update(overrides)
    return body


def test_zip_search_and_locations_together_is_a_400():
    payload, status = optimize_housing_from_request(
        _base_config(),
        _body(locations=[{'state': 'Texas'}, {'state': 'Florida'}]),
        table_path=FIXTURE,
    )
    assert status == 400
    assert 'mutually exclusive' in payload['error']


def test_neither_zip_search_nor_locations_is_a_400():
    payload, status = optimize_housing_from_request(_base_config(), {}, table_path=FIXTURE)
    assert status == 400


def test_zip_search_produces_a_zip_screen_block():
    payload, status = optimize_housing_from_request(_base_config(), _body(), table_path=FIXTURE)
    assert status == 200
    assert payload['zip_screen']['schema'] == 'zip_screen_v1'


def test_promoted_zips_become_the_optimizers_locations():
    payload, _ = optimize_housing_from_request(_base_config(), _body(), table_path=FIXTURE)
    promoted = {z['zip'] for z in payload['zip_screen']['shortlist']}
    assert payload['recommendation'] is not None
    recommended = payload['recommendation']['moves'][0]['location']
    assert recommended['zip_code'] in promoted


def test_recommendation_carries_the_nss_for_the_chosen_zip():
    payload, _ = optimize_housing_from_request(_base_config(), _body(), table_path=FIXTURE)
    loc = payload['recommendation']['moves'][0]['location']
    assert 0.0 <= loc['nss'] <= 100.0


def test_an_empty_shortlist_returns_200_without_running_the_engine():
    payload, status = optimize_housing_from_request(
        _base_config(),
        _body(zip_search={**_body()['zip_search'], 'min_quality_score': 99.9}),
        table_path=FIXTURE,
    )
    assert status == 200
    assert payload['recommendation'] is None
    assert payload['zip_screen']['relaxation'] is not None


def test_fewer_than_two_survivors_explains_rather_than_erroring():
    payload, status = optimize_housing_from_request(
        _base_config(),
        _body(zip_search={**_body()['zip_search'], 'anchor': {'zip': '80424'},
                          'radius_miles': 5, 'min_quality_score': 0}),
        table_path=FIXTURE,
    )
    assert status == 200
    assert payload['recommendation'] is None
    assert 'at least 2' in payload['message']


def test_the_hand_picked_path_still_works():
    payload, status = optimize_housing_from_request(_base_config(), {
        'locations': [{'state': 'Texas'}, {'state': 'Florida'}],
        'move1_window': {
            'earliest_sale_year': 2028, 'latest_sale_year': 2029,
            'earliest_purchase_year': 2028, 'latest_purchase_year': 2029,
        },
        'objective': 'net_worth', 'search_mode': 'narrowed',
    })
    assert status == 200
    assert 'zip_screen' not in payload
