"""Each move's ZIP search drives the real optimizer through resolved,
screen-spliced Locations (design 2026-09-16 §7.1/§7.2)."""
from __future__ import annotations

import pytest

from src.housing.api import optimize_housing_from_request

from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
from conftest import TEST_INPUT_DIR

pytestmark = pytest.mark.integration

FIXTURE = 'tests/fixtures/zip_metrics_sample.csv'

DWELLING = {
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


def _search(**overrides):
    search = {
        'anchors': [{'kind': 'zip', 'anchor_zip': '60521'},
                   {'kind': 'zip', 'anchor_zip': '60540'}],
        'radius_miles': 50, 'min_quality_score': 0,
        'area_type': 'any', 'max_population': None,
        # shortlist_size left the request schema with the step-1 selection
        # table (design 2026-09-19 §5.4); the caller now names the ZIPs.
        'selected_zips': ['60521', '60540'],
        'dwelling': dict(DWELLING),
    }
    search.update(overrides)
    return search


def _body(**overrides):
    body = {
        'objective': 'net_worth', 'search_mode': 'narrowed',
        'move2_strategy': 'anchored', 'no_dual_ownership': True,
        'original_home': {'disposition': 'sell',
                          'earliest_sale_year': 2028, 'latest_sale_year': 2029},
        'move1': {'earliest_acquisition_year': 2028,
                 'latest_acquisition_year': 2029, 'action': 'auto',
                 'search': _search()},
    }
    body.update(overrides)
    return body


def test_locations_is_rejected_end_to_end():
    """The manual-location mode is gone; the request adapter's own
    validate_request call is what catches it, not just the unit test."""
    payload, status = optimize_housing_from_request(
        _base_config(), _body(locations=[{'state': 'Texas'}]), table_path=FIXTURE)
    assert status == 400
    assert 'locations' in payload['error'].lower()


def test_an_unresolvable_anchor_is_a_400_naming_the_zip():
    body = _body()
    body['move1']['search'] = _search(anchors=[
        {'kind': 'zip', 'anchor_zip': '99999'}, {'kind': 'zip', 'anchor_zip': '60521'}])
    payload, status = optimize_housing_from_request(_base_config(), body, table_path=FIXTURE)
    assert status == 400
    assert '99999' in payload['error']


def test_zip_search_produces_a_zip_screens_block():
    payload, status = optimize_housing_from_request(_base_config(), _body(), table_path=FIXTURE)
    assert status == 200
    assert payload['zip_screens']['move1']['schema'] == 'zip_screen_v2'
    assert 'move2' not in payload['zip_screens']


def test_promoted_zips_become_the_optimizers_locations():
    payload, _ = optimize_housing_from_request(_base_config(), _body(), table_path=FIXTURE)
    promoted = {z['zip'] for z in payload['zip_screens']['move1']['shortlist']}
    assert payload['recommendation'] is not None
    recommended = payload['recommendation']['moves'][0]['location']
    assert recommended['zip_code'] in promoted


def test_recommendation_carries_the_nss_and_city_for_the_chosen_zip():
    payload, _ = optimize_housing_from_request(_base_config(), _body(), table_path=FIXTURE)
    loc = payload['recommendation']['moves'][0]['location']
    assert 0.0 <= loc['nss'] <= 100.0
    assert loc['city']


def test_an_empty_shortlist_returns_200_without_running_the_engine():
    body = _body()
    body['move1']['search'] = _search(min_quality_score=99.9)
    payload, status = optimize_housing_from_request(_base_config(), body, table_path=FIXTURE)
    assert status == 200
    assert payload['recommendation'] is None
    assert payload['candidates_evaluated'] == 0
    assert 'message' in payload


def test_a_zip_outside_the_screen_is_rejected_end_to_end_naming_it():
    """A stale saved selection, screened against different filters, must come
    back as a named failure rather than quietly running a smaller search than
    the user asked for (design 2026-09-19 §5.5)."""
    body = _body()
    body['move1']['search'] = _search(selected_zips=['60521', '99999'])
    payload, status = optimize_housing_from_request(
        _base_config(), body, table_path=FIXTURE)
    assert status == 400
    assert payload['success'] is False
    assert '99999' in payload['error']


def test_an_empty_screen_keeps_its_own_message_rather_than_blaming_the_selection():
    """An empty screen and a stale selection both leave the requested ZIP out
    of all_passing, but only the second is the user's selection being wrong.
    An emptied funnel keeps the "widen the radius" message."""
    body = _body()
    body['move1']['search'] = _search(min_quality_score=99.9)
    payload, status = optimize_housing_from_request(
        _base_config(), body, table_path=FIXTURE)
    assert status == 200
    assert 'radius' in payload['message']


def test_only_the_selected_zips_reach_the_optimizer():
    body = _body()
    body['move1']['search'] = _search(min_quality_score=0, selected_zips=['60521'])
    payload, _ = optimize_housing_from_request(
        _base_config(), body, table_path=FIXTURE)
    searched = {z['zip'] for z in payload['zip_screens']['move1']['shortlist']}
    assert searched == {'60521'}


def test_a_down_payment_pct_of_zero_is_honored_not_rewritten_to_20_pct():
    """An explicit 0% down payment must not be silently replaced by the
    20% default (`0 or 0.20` truthiness bug -- see api.py's
    `optimize_housing_from_request`). A $0-down purchase finances the full
    purchase price, so its monthly P&I must be strictly higher than the
    20%-down default's."""
    body = _body()
    body['move1']['action'] = 'buy'
    zero_down_payload, status = optimize_housing_from_request(
        _base_config(), dict(body, down_payment_pct=0), table_path=FIXTURE)
    assert status == 200
    default_payload, status = optimize_housing_from_request(
        _base_config(), body, table_path=FIXTURE)
    assert status == 200

    zero_down_pi = zero_down_payload['recommendation']['moves'][0]['financing']['monthly_pi_payment']
    default_pi = default_payload['recommendation']['moves'][0]['financing']['monthly_pi_payment']
    assert zero_down_pi > default_pi


def test_a_second_move_produces_a_second_zip_screens_block():
    body = _body(move2={
        'earliest_acquisition_year': 2032, 'latest_acquisition_year': 2033,
        'action': 'auto', 'concurrent': False, 'anchor_count': 2,
        'search': _search(),
    })
    payload, status = optimize_housing_from_request(_base_config(), body, table_path=FIXTURE)
    assert status == 200
    assert payload['zip_screens']['move2']['schema'] == 'zip_screen_v2'
