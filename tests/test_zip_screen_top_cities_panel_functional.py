"""The ZIP-radius panel fetches and renders the top-cities dropdown."""
from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.unit

PANEL = pathlib.Path('frontend/js/dashboard_decomp_housing_optimizer.js')


@pytest.fixture(scope='module')
def source() -> str:
    return PANEL.read_text(encoding='utf-8')


def test_a_loader_function_exists(source):
    assert 'function loadHousingOptTopCities' in source or \
           'export async function loadHousingOptTopCities' in source


def test_the_loader_calls_the_top_cities_endpoint(source):
    block = source.split('loadHousingOptTopCities')[1][:2000]
    assert '/api/housing/top-cities' in block


def test_the_loader_populates_the_shared_array(source):
    block = source.split('loadHousingOptTopCities')[1][:2000]
    assert 'HOUSING_OPT_TOP_CITIES' in block


def test_the_loader_is_invoked_when_the_panel_renders(source):
    # Called from renderHousingOptimizePanelHtml's caller path or from the
    # mode-toggle handler -- either is acceptable, but SOME call site must
    # exist besides the function's own definition.
    occurrences = source.count('loadHousingOptTopCities')
    assert occurrences >= 2
