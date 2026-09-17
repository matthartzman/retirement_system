"""Generation over decoupled sale/acquisition (design 2026-09-16 §5.3, §5.4)."""
import pytest

from src.housing.candidates import (
    dual_ownership_ok,
    extend_with_move2,
    generate_candidates,
)
from src.housing.models import Location, MoveWindow, SaleWindow

pytestmark = pytest.mark.unit

LOCS = [Location(state='CO'), Location(state='AZ')]


def _gen(**kw):
    kw.setdefault('locations1', LOCS)
    kw.setdefault('sale_window', SaleWindow(2030, 2031))
    kw.setdefault('move1_window', MoveWindow(2030, 2032))
    kw.setdefault('dispositions', ('sell',))
    kw.setdefault('move1_action', 'auto')
    kw.setdefault('no_dual_ownership', True)
    return generate_candidates(**kw)


def test_acquisition_year_is_not_forced_to_follow_the_sale_year_for_a_rental():
    """The whole point of decoupling: rent at the new place in 2030 while the
    old home is still on the market until 2031."""
    cands = _gen(move1_action='rent')
    assert any(c.original_home.sale_year == 2031 and c.move1.acquisition_year == 2030
               for c in cands)


def test_no_dual_ownership_blocks_buying_before_the_sale_but_not_renting():
    bought_early = [c for c in _gen(move1_action='buy')
                    if c.move1.acquisition_year < c.original_home.sale_year]
    assert bought_early == []

    rented_early = [c for c in _gen(move1_action='rent')
                    if c.move1.acquisition_year < c.original_home.sale_year]
    assert rented_early != []


def test_dual_ownership_off_allows_the_overlap():
    cands = _gen(move1_action='buy', no_dual_ownership=False)
    assert any(c.move1.acquisition_year < c.original_home.sale_year for c in cands)


def test_keep_produces_a_null_sale_year_and_ignores_the_sale_window():
    cands = _gen(dispositions=('keep',), move1_action='rent')
    assert cands
    assert all(c.original_home.sale_year is None for c in cands)
    assert all(c.original_home.disposition == 'keep' for c in cands)


def test_keep_plus_buy_is_rejected_under_no_dual_ownership():
    assert _gen(dispositions=('keep',), move1_action='buy', no_dual_ownership=True) == []
    assert _gen(dispositions=('keep',), move1_action='buy', no_dual_ownership=False) != []


def test_auto_expands_into_both_dispositions():
    cands = _gen(dispositions=('sell', 'keep'), move1_action='rent')
    assert {c.original_home.disposition for c in cands} == {'sell', 'keep'}


def test_auto_action_generates_both_buy_and_rent():
    assert {c.move1.action for c in _gen(move1_action='auto')} == {'buy', 'rent'}


def test_apartment_locations_never_generate_a_buy_candidate_under_auto():
    apt_locs = [Location(state='CO', property_type='apartment'),
                Location(state='AZ', property_type='apartment')]
    cands = _gen(locations1=apt_locs, move1_action='auto')
    assert cands
    assert {c.move1.action for c in cands} == {'rent'}


def test_apartment_locations_generate_no_candidates_at_all_under_an_explicit_buy():
    apt_locs = [Location(state='CO', property_type='apartment')]
    assert _gen(locations1=apt_locs, move1_action='buy') == []


def test_a_mixed_shortlist_only_excludes_buy_for_the_apartment_locations():
    mixed = [Location(state='CO', property_type='apartment'),
              Location(state='AZ', property_type='single_family')]
    cands = _gen(locations1=mixed, move1_action='auto')
    by_state = {}
    for c in cands:
        by_state.setdefault(c.move1.location.state, set()).add(c.move1.action)
    assert by_state['CO'] == {'rent'}
    assert by_state['AZ'] == {'buy', 'rent'}


def test_move2_uses_its_own_window_not_the_move1_acquisition_year():
    """The screenshot bug: move 2's lower bound used to be derived from move 1's
    purchase year, so a declared move-2 window was silently overridden."""
    anchors = _gen(move1_action='buy')
    out = extend_with_move2(anchors, locations2=LOCS,
                            move2_window=MoveWindow(2035, 2036),
                            move2_action='buy', concurrent=False,
                            no_dual_ownership=True)
    assert out
    assert {c.move2.acquisition_year for c in out} == {2035, 2036}


def test_move2_must_come_after_move1_when_sequential():
    anchors = _gen(move1_action='buy', move1_window=MoveWindow(2035, 2035))
    out = extend_with_move2(anchors, locations2=LOCS,
                            move2_window=MoveWindow(2030, 2036),
                            move2_action='buy', concurrent=False,
                            no_dual_ownership=True)
    assert out
    assert all(c.move2.acquisition_year > c.move1.acquisition_year for c in out)


def test_an_impossible_move2_window_yields_nothing_rather_than_being_coerced():
    anchors = _gen(move1_action='buy', move1_window=MoveWindow(2040, 2040))
    out = extend_with_move2(anchors, locations2=LOCS,
                            move2_window=MoveWindow(2030, 2035),
                            move2_action='buy', concurrent=False,
                            no_dual_ownership=True)
    assert out == []


def test_concurrent_move2_may_share_a_year_with_move1():
    """A second simultaneous residence is not a relocation, so the
    strictly-after rule does not apply to it."""
    anchors = _gen(move1_action='buy', move1_window=MoveWindow(2035, 2035))
    out = extend_with_move2(anchors, locations2=LOCS,
                            move2_window=MoveWindow(2035, 2035),
                            move2_action='rent', concurrent=True,
                            no_dual_ownership=True)
    assert out
    assert all(c.move2.mode == 'concurrent' for c in out)


def test_dual_ownership_ok_is_the_single_predicate():
    sell_then_buy = _gen(move1_action='buy')[0]
    assert dual_ownership_ok(sell_then_buy) is True
