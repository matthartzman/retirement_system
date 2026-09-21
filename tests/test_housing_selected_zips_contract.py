"""``selected_zips`` on the wire (design 2026-09-19 §5.4/§5.5).

The per-move "Shortlist size" pulldown asked the user how many screened ZIPs
to promote -- a number standing in for a choice they could not see. Step 1's
selection table replaces it: the user ticks the ZIPs, and the count *is* the
selection. ``shortlist_size`` therefore leaves the request schema entirely
and survives only as ``MultiAnchorRequest.shortlist_size``, an internal
preview cap.

The compatibility hazard this creates is a stale saved selection screened
against different filters, so these tests pin the half that matters: a ZIP
that is not among the move's screened candidates is an error naming it, not
a silent degrade into a smaller search.
"""
from __future__ import annotations

import pytest

from src.housing.api import (
    DEFAULT_PREVIEW_SIZE,
    SELECTED_ZIPS_MAX,
    StaleSelectionError,
    parse_move_search,
    parse_selected_zips,
    select_screened_zips,
    validate_request,
)
from src.housing.zip_screen.screen import ScreenedZip, ScreenResult

pytestmark = pytest.mark.contract


def _screened(zcta, nss):
    return ScreenedZip(
        zcta=zcta, city=f'Place{zcta}', state='Colorado', distance_miles=1.0,
        nss=nss, band='Mixed', coverage_pct=78.8, est_price=400000.0,
        components={},
    )


def _screen(*zctas):
    passing = [_screened(z, 90.0 - i) for i, z in enumerate(zctas)]
    return ScreenResult(anchor={}, radius_miles=25, funnel={}, shortlist=[],
                        all_passing=passing)


def _search(**overrides):
    search = {
        'anchors': [{'kind': 'zip', 'anchor_zip': '80014'},
                    {'kind': 'zip', 'anchor_zip': '60521'}],
        'radius_miles': 25, 'min_quality_score': 60,
        'area_type': 'any', 'max_population': None,
        'selected_zips': ['80014', '60521'], 'dwelling': {},
    }
    search.update(overrides)
    return search


def _body(**move1_overrides):
    return {
        'objective': 'net_worth', 'search_mode': 'full',
        'move2_strategy': 'anchored', 'no_dual_ownership': True,
        'original_home': {'disposition': 'sell',
                          'earliest_sale_year': 2030, 'latest_sale_year': 2045},
        'move1': {'earliest_acquisition_year': 2031,
                  'latest_acquisition_year': 2046, 'action': 'auto',
                  'search': _search(**move1_overrides)},
    }


# --- the request schema ----------------------------------------------------


def test_a_request_carrying_selected_zips_validates():
    assert validate_request(_body()) is None


def test_a_move_with_no_selection_is_rejected_before_any_screen_runs():
    msg = validate_request(_body(selected_zips=[]))
    assert msg and 'move 1' in msg
    assert 'Find candidate locations' in msg


def test_a_move_missing_the_key_entirely_is_rejected():
    search = _search()
    search.pop('selected_zips')
    body = _body()
    body['move1']['search'] = search
    assert validate_request(body) is not None


def test_more_than_ten_selected_zips_is_rejected():
    msg = validate_request(_body(selected_zips=[str(80000 + i) for i in range(11)]))
    assert msg and str(SELECTED_ZIPS_MAX) in msg


def test_a_blank_entry_is_rejected_rather_than_dropped():
    msg = validate_request(_body(selected_zips=['80014', '  ']))
    assert msg and 'needs a value' in msg


def test_shortlist_size_is_no_longer_read_from_the_request():
    """Deliberately inverted (§5.4). A stale client still sending the old key
    must not be able to shrink the preview, so it is ignored outright."""
    req = parse_move_search(_search(shortlist_size=2))
    assert req.shortlist_size == DEFAULT_PREVIEW_SIZE


def test_the_internal_preview_cap_always_seats_every_anchor():
    anchors = [{'kind': 'zip', 'anchor_zip': str(80000 + i)} for i in range(5)]
    req = parse_move_search(_search(anchors=anchors))
    assert req.shortlist_size == 5


# --- parsing ---------------------------------------------------------------


def test_duplicate_ticks_do_not_become_a_second_candidate():
    assert parse_selected_zips(
        {'selected_zips': ['80014', '80014', '60521']}, 'move 1') == ['80014', '60521']


def test_a_non_list_selection_is_a_wire_ready_message():
    with pytest.raises(ValueError, match='move 1'):
        parse_selected_zips({'selected_zips': '80014'}, 'move 1')


# --- membership ------------------------------------------------------------


def test_the_selection_filters_the_screen_to_exactly_those_zips():
    picked = select_screened_zips(_screen('80014', '80015', '60521'),
                                  ['80014', '60521'], 'move 1')
    assert [z.zcta for z in picked] == ['80014', '60521']


def test_every_selected_zip_comes_back_promoted():
    picked = select_screened_zips(_screen('80014', '60521'), ['60521'], 'move 1')
    assert all(z.promoted for z in picked)


def test_rows_come_back_in_score_order_not_the_order_they_were_ticked():
    """Two clients sending the same set must get the same candidate ordering,
    or the optimizer's tie-breaks depend on which checkbox was clicked
    first."""
    picked = select_screened_zips(_screen('80014', '80015', '60521'),
                                  ['60521', '80014'], 'move 1')
    assert [z.zcta for z in picked] == ['80014', '60521']


def test_a_zip_outside_the_screen_is_an_error_naming_it():
    """A stale localStorage selection made against different filters must not
    silently degrade into a smaller search -- the same class of silent
    discard §1.1 exists to fix."""
    with pytest.raises(StaleSelectionError) as exc:
        select_screened_zips(_screen('80014', '60521'), ['80014', '99999'], 'move 1')
    assert '99999' in str(exc.value)
    assert 'move 1' in str(exc.value)


def test_a_stale_selection_is_a_value_error_so_the_route_returns_success_false():
    """StaleSelectionError subclasses ValueError, which
    optimize_housing_from_request already maps to
    ``{'success': False, 'error': ...}`` with a 400."""
    assert issubclass(StaleSelectionError, ValueError)
