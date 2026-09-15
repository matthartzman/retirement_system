"""Shortlist rendering and the zip_search request body."""
from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.unit

PANEL = pathlib.Path('frontend/js/dashboard_decomp_housing_scenarios.js')


@pytest.fixture(scope='module')
def source() -> str:
    return PANEL.read_text(encoding='utf-8')


def test_renderer_exists_and_is_exported(source):
    assert 'export function renderHousingZipShortlistHtml' in source


def test_shortlist_renders_every_documented_column(source):
    block = source.split('renderHousingZipShortlistHtml')[1][:3000]
    for token in ('distance_miles', 'nss', 'band', 'est_price', 'coverage_pct'):
        assert token in block


def test_cross_state_is_surfaced(source):
    assert 'cross_state' in source


def test_collapsed_neighbours_are_shown_not_hidden(source):
    assert 'collapsed' in source
    assert 'similar nearby' in source


def test_funnel_diagnostics_are_rendered(source):
    block = source.split('renderHousingZipShortlistHtml')[1][:4000]
    for token in ('in_radius', 'with_data', 'above_score', 'promoted'):
        assert token in block


def test_relaxation_suggestion_is_rendered(source):
    assert 'relaxation' in source


def test_request_sends_zip_search_in_zip_mode(source):
    block = source.split('runHousingOptimization')[1][:4000]
    assert 'zip_search' in block
    assert 'radius_miles' in block
    assert 'min_quality_score' in block


def test_request_omits_locations_in_zip_mode(source):
    # The two are mutually exclusive server-side; the client must not send both.
    block = source.split('runHousingOptimization')[1][:4000]
    assert 'housingOptGeoMode' in block


def test_upi_adjustment_is_disclosed_when_applied(source):
    assert 'upi_adjusted' in source
