"""The ZIP panel exposes its own property-spec and price-range controls,
rather than silently reusing the hidden manual-entry row's fields."""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.unit

PANEL = pathlib.Path('frontend/js/dashboard_decomp_housing_scenarios.js')


@pytest.fixture(scope='module')
def source() -> str:
    return PANEL.read_text(encoding='utf-8')


def test_zip_panel_has_its_own_bedroom_bathroom_controls(source):
    zip_block = source.split('id="housingOptZipFields"')[1].split('id="housingOptManualFields"')[0]
    assert 'housingOptZipBedrooms' in zip_block
    assert 'housingOptZipBathrooms' in zip_block


def test_zip_panel_has_its_own_property_type_and_sqft_controls(source):
    zip_block = source.split('id="housingOptZipFields"')[1].split('id="housingOptManualFields"')[0]
    assert 'housingOptZipPropertyType' in zip_block
    assert 'housingOptZipSqftBand' in zip_block


def test_zip_panel_has_price_range_controls(source):
    zip_block = source.split('id="housingOptZipFields"')[1].split('id="housingOptManualFields"')[0]
    assert 'housingOptZipPriceMin' in zip_block
    assert 'housingOptZipPriceMax' in zip_block


def test_zip_search_body_reads_the_zip_panels_own_fields_not_row_zero(source):
    block = source.split('function housingOptZipSearchBody')[1][:2000]
    assert 'housingOptZipBedrooms' in block
    assert 'housingOptLocBedrooms0' not in block


def test_zip_search_body_sends_a_price_range_when_provided(source):
    block = source.split('function housingOptZipSearchBody')[1][:2000]
    assert 'target_purchase_price_range' in block
    assert 'housingOptZipPriceMin' in block
    assert 'housingOptZipPriceMax' in block
