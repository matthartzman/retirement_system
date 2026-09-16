"""Shortlist rendering.

The zip_search request-body tests that used to live here were deleted: Task 11's
refactor replaced the top-level `zip_search` request key with a per-move `search`
block (design doc §7.3) and removed the `housingOptGeoMode` mode toggle entirely
(§14, "Manual location mode: Removed"). Coverage for the new per-move request
contract belongs to Task 12's own test file
(tests/frontend/housing_optimize_request.test.mjs)."""
from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.unit

PANEL = pathlib.Path('frontend/js/dashboard_decomp_housing_optimizer.js')


@pytest.fixture(scope='module')
def source() -> str:
    return PANEL.read_text(encoding='utf-8')


def test_renderer_exists_and_is_exported(source):
    assert 'export function renderHousingZipShortlistHtml' in source


def test_shortlist_renders_every_documented_column(source):
    # Anchor on the function's definition, not just its name: the new module
    # calls renderHousingZipShortlistHtml from previewHousingZipShortlist
    # *before* the definition appears in the file, so splitting on the bare
    # name would grab the gap between the call site and the definition.
    block = source.split('function renderHousingZipShortlistHtml')[1][:3000]
    for token in ('distance_miles', 'nss', 'band', 'est_price', 'coverage_pct'):
        assert token in block


def test_cross_state_is_surfaced(source):
    assert 'cross_state' in source


def test_collapsed_neighbours_are_shown_not_hidden(source):
    assert 'collapsed' in source
    assert 'similar nearby' in source


def test_funnel_diagnostics_are_rendered(source):
    block = source.split('function renderHousingZipShortlistHtml')[1][:4000]
    for token in ('in_radius', 'with_data', 'above_score', 'promoted'):
        assert token in block


def test_relaxation_suggestion_is_rendered(source):
    assert 'relaxation' in source


def test_upi_adjustment_is_disclosed_when_applied(source):
    assert 'upi_adjusted' in source
