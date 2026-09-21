"""The optimizer panel exposes the ZIP-radius search controls, per move.

Task 11 (docs/superpowers/specs/2026-09-16-housing-optimizer-refinement-design.md)
extracted the panel to frontend/js/dashboard_decomp_housing_optimizer.js, rewrote
it row-oriented, and made a move's where/what/when rows a single templated
function shared by both moves (housingOptMoveWhereRowHtml/housingOptMoveWhatRowHtml
called once per move index) rather than one hand-written block per field. Two
tests below (mode toggle, manual path) pinned the manual-location entry mode,
which design §14 removed outright ("Manual location mode: Removed" -- it produced
candidates with no ZIP, score, or distance). There is no replacement id for those
assertions to move to, so they are deleted rather than updated."""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.unit

PANEL = pathlib.Path('frontend/js/dashboard_decomp_housing_optimizer.js')


@pytest.fixture(scope='module')
def source() -> str:
    return PANEL.read_text(encoding='utf-8')


def test_both_radius_selects_share_the_same_approved_options(source):
    # Renamed: the single "housingOptRadius" select became a per-move
    # "${p}Radius" select built once by housingOptMoveWhereRowHtml and invoked
    # for both move 1 and move 2, so the two can never offer different radii.
    assert 'housingOptMoveWhereRowHtml(1)' in source
    assert 'housingOptMoveWhereRowHtml(2)' in source
    assert '${p}Radius' in source


def _move_radii_block(source: str) -> str:
    # housingOptSelect() assembles `<option value="...">` at runtime from this
    # data array rather than the markup containing literal `<option value="5">`
    # text, so the array is the actual source of truth to assert against.
    return source.split('HOUSING_OPT_MOVE_RADII = [')[1].split('];')[0]


def test_every_radius_option_is_present(source):
    block = _move_radii_block(source)
    for r in (5, 10, 25, 50):
        assert f'value: "{r}"' in block


def test_no_unapproved_radius_is_offered(source):
    block = _move_radii_block(source)
    offered = {int(m) for m in re.findall(r'value: "(\d+)"', block)}
    assert offered == {5, 10, 25, 50}


def test_min_score_control_exists_with_the_spec_default(source):
    # Renamed: "housingOptMinScore" became the per-move "${p}MinScore".
    assert '${p}MinScore' in source
    assert 'value="60"' in source


def test_anchor_offers_both_a_city_dropdown_and_a_zip_field(source):
    # Renamed: "housingOptAnchorCity"/"housingOptAnchorZip" became per-move,
    # per-index ids assembled as `housingOptMove${moveIndex}AnchorCity${i}` /
    # `...AnchorZip${i}` inside housingOptAnchorEntryHtml.
    assert 'AnchorCity' in source
    assert 'AnchorZip' in source
    assert 'export function housingOptAnchorEntryHtml' in source


def test_the_shortlist_size_control_is_gone(source):
    """DELIBERATELY INVERTED, not an accidental break.

    This asserted the per-move "${p}ShortlistSize" select existed. The
    2026-09-19 anchor-flow design §5.4 removes that control outright: it
    asked how many screened ZIPs to promote, a number standing in for a
    choice the user could not see, and once step 1 ends with them ticking
    the ZIPs they want the count *is* the selection. Keeping both would let
    the two disagree (six ticked with the size set to four -- which four?),
    and any rule resolving that would override an explicit user choice with
    an implicit one.

    Asserted as an absence rather than deleted, so re-adding the control
    fails here and has to be argued for again.
    """
    assert '${p}ShortlistSize' not in source
    assert 'HOUSING_OPT_SHORTLIST_SIZES' not in source


def test_the_selection_table_replaced_it(source):
    """§5.3: step 1 ends in "Find candidate locations", which renders a
    checkbox row per screened ZIP; the selection is what reaches the wire."""
    assert 'findHousingOptCandidates' in source
    assert 'toggleHousingOptZipSelection' in source
    assert 'selected_zips' in source


def test_preview_button_calls_the_screen_only_endpoint(source):
    assert 'previewHousingZipShortlist' in source
    assert '/api/housing/zip-screen' in source


def test_the_disclosure_is_rendered_from_the_server_payload(source):
    # Renamed: the disclosure sentence used to be a hardcoded div in this
    # panel; it is now rendered from the server's own payload field
    # (src/housing/zip_screen/schema.py owns the exact wording, checked by
    # tests/test_zip_screen_schema_unit.py and tests/test_zip_screen_api_contract.py).
    block = source.split('function renderHousingZipShortlistHtml')[1][:500]
    assert 'zs.disclosure' in block
