"""The optimizer panel exposes its own property-spec and price-range controls
per move, rather than silently reusing a hidden manual-entry row's fields.

Task 11 (docs/superpowers/specs/2026-09-16-housing-optimizer-refinement-design.md)
extracted the panel to frontend/js/dashboard_decomp_housing_optimizer.js and
replaced the single ZIP-panel-vs-manual-row distinction with a per-move field set:
the concept survives as ``housingOptZipBedrooms`` -> ``housingOptMove1Bedrooms``
plus a matching Move-2 set, both built by the same templated row functions
(housingOptMoveWhereRowHtml/housingOptMoveWhatRowHtml) so the two moves can never
drift apart. The manual-entry row itself is gone (design §14), so there is no
longer a second block to exclude these fields from."""
from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.unit

PANEL = pathlib.Path('frontend/js/dashboard_decomp_housing_optimizer.js')


@pytest.fixture(scope='module')
def source() -> str:
    return PANEL.read_text(encoding='utf-8')


def test_both_moves_render_their_own_dwelling_spec_row(source):
    # housingOptMoveWhatRowHtml is the single templated source for both moves'
    # bedroom/bathroom/property-type/sqft controls; both call sites must exist
    # or move 2 silently loses its own dwelling spec.
    assert 'housingOptMoveWhatRowHtml(1)' in source
    assert 'housingOptMoveWhatRowHtml(2)' in source


def test_zip_panel_has_its_own_bedroom_bathroom_controls(source):
    block = source.split('function housingOptMoveWhatRowHtml')[1].split(
        'function housingOptMoveWhenRowHtml'
    )[0]
    assert '${p}Bedrooms' in block
    assert '${p}Bathrooms' in block


def test_zip_panel_has_its_own_property_type_and_sqft_controls(source):
    block = source.split('function housingOptMoveWhatRowHtml')[1].split(
        'function housingOptMoveWhenRowHtml'
    )[0]
    assert '${p}PropertyType' in block
    assert '${p}SqftBand' in block


def test_zip_panel_has_price_range_controls(source):
    block = source.split('function housingOptMoveWhatRowHtml')[1].split(
        'function housingOptMoveWhenRowHtml'
    )[0]
    assert '${p}PriceMin' in block
    assert '${p}PriceMax' in block


def test_zip_search_body_reads_the_zip_panels_own_fields_not_a_fixed_row(source):
    # Renamed from housingOptZipSearchBody: the reader is now parameterized by
    # moveIndex (housingOptMoveSearchBody) so it reads whichever move's own
    # fields it is called for, rather than a hardcoded manual "row zero".
    block = source.split('function housingOptMoveSearchBody')[1][:2000]
    assert '${p}Bedrooms' in block
    assert 'housingOptLocBedrooms0' not in block


def test_zip_search_body_sends_a_price_range_when_provided(source):
    block = source.split('function housingOptMoveSearchBody')[1][:2000]
    assert 'target_purchase_price_range' in block
    assert '${p}PriceMin' in block
    assert '${p}PriceMax' in block
