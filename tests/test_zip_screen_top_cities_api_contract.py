"""Wire contract for the top-cities listing endpoint."""
from __future__ import annotations

import pytest

from src.housing.api import top_cities_payload

pytestmark = pytest.mark.contract


def test_returns_success_and_a_city_list():
    payload, status = top_cities_payload()
    assert status == 200
    assert payload['success'] is True
    assert isinstance(payload['cities'], list)
    assert len(payload['cities']) > 0


def test_each_city_carries_the_documented_fields():
    payload, _ = top_cities_payload()
    row = payload['cities'][0]
    for key in ('city_id', 'city', 'state', 'state_abbrev', 'population', 'anchor_zip'):
        assert key in row


def test_cities_are_sorted_by_population_descending():
    payload, _ = top_cities_payload()
    pops = [c['population'] for c in payload['cities']]
    assert pops == sorted(pops, reverse=True)


def test_new_york_is_present_as_the_largest_city():
    payload, _ = top_cities_payload()
    assert payload['cities'][0]['city'] == 'New York'
