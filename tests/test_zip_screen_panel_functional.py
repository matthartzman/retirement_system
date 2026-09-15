"""The optimizer panel exposes the ZIP-radius mode and its controls."""
from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.unit

PANEL = pathlib.Path('frontend/js/dashboard_decomp_housing_scenarios.js')


@pytest.fixture(scope='module')
def source() -> str:
    return PANEL.read_text(encoding='utf-8')


def test_mode_toggle_exists(source):
    assert 'housingOptGeoMode' in source
    assert 'toggleHousingOptSearchMode' in source


def test_both_modes_are_offered(source):
    assert 'value="manual"' in source
    assert 'value="zip_radius"' in source


def test_every_radius_option_is_present(source):
    for r in (5, 10, 25, 50):
        assert f'<option value="{r}"' in source


def test_no_unapproved_radius_is_offered(source):
    import re
    block = source.split('housingOptRadius')[1].split('</select>')[0]
    offered = {int(m) for m in re.findall(r'<option value="(\d+)"', block)}
    assert offered == {5, 10, 25, 50}


def test_min_score_control_exists_with_the_spec_default(source):
    assert 'housingOptMinScore' in source
    assert 'value="60"' in source


def test_anchor_offers_both_a_city_dropdown_and_a_zip_field(source):
    assert 'housingOptAnchorCity' in source
    assert 'housingOptAnchorZip' in source


def test_shortlist_size_control_exists(source):
    assert 'housingOptShortlistSize' in source


def test_preview_button_calls_the_screen_only_endpoint(source):
    assert 'previewHousingZipShortlist' in source
    assert '/api/housing/zip-screen' in source


def test_the_disclosure_string_is_present_verbatim(source):
    assert (
        'Measures housing and economic stability. Does not measure crime or safety.'
    ) in source


def test_the_manual_path_is_preserved(source):
    assert 'housingOptLocCount' in source
    assert 'housingOptLocState0' in source or 'housingOptLocState${i}' in source
