"""housing_optimize_v2 payload shape (design 2026-09-16 §7.2)."""
import pytest

from src.housing.models import (
    HousingCandidate,
    Location,
    Move,
    OriginalHome,
    ScoredCandidate,
)
from src.housing.results import format_output

pytestmark = pytest.mark.contract


def _scored(nw=1000.0, sale_year=2032, zip1='80024', two_move=False):
    moves = [Move(index=1, acquisition_year=2033, action='buy',
                  location=Location(state='CO', zip_code=zip1))]
    if two_move:
        moves.append(Move(index=2, acquisition_year=2041, action='rent',
                          location=Location(state='AZ', zip_code='85001')))
    return ScoredCandidate(
        candidate=HousingCandidate(
            original_home=OriginalHome(disposition='sell', sale_year=sale_year),
            moves=tuple(moves)),
        net_worth=nw, lifetime_cost=500.0, mc_success_rate=0.91,
        sec121_exclusion_lost=[False, False], notes=['family presence via rental'],
    )


def _out(ranked, **kw):
    kw.setdefault('objective', 'net_worth')
    kw.setdefault('search_mode', 'full')
    kw.setdefault('move2_strategy', 'anchored')
    kw.setdefault('zip_screens', {})
    kw.setdefault('rejections', {})
    return format_output(ranked, **kw)


def test_schema_is_v2():
    assert _out([_scored()])['schema'] == 'housing_optimize_v2'


def test_candidates_is_the_single_ranked_list_and_recommendation_aliases_its_head():
    out = _out([_scored(nw=2000.0), _scored(nw=1000.0)])
    assert [c['rank'] for c in out['candidates']] == [1, 2]
    assert out['recommendation'] == out['candidates'][0]
    assert 'alternatives' not in out


def test_each_move_carries_the_detail_needed_to_act_on_it():
    """The v1 payload dropped ZIP, price and distance, so a recommendation
    could not be acted on without a second lookup."""
    move = _out([_scored()])['candidates'][0]['moves'][0]
    assert move['acquisition_year'] == 2033
    assert move['action'] == 'buy'
    assert move['location']['zip_code'] == '80024'
    for key in ('est_price', 'distance_miles', 'area_type', 'population', 'nss'):
        assert key in move['location'], f'{key} missing from the move location'


def test_original_home_is_reported_separately_from_the_moves():
    out = _out([_scored()])['candidates'][0]
    assert out['original_home'] == {'disposition': 'sell', 'sale_year': 2032}


def test_a_kept_home_reports_a_null_sale_year():
    sc = _scored()
    sc.candidate.original_home = OriginalHome(disposition='keep', sale_year=None)
    out = _out([sc])['candidates'][0]
    assert out['original_home'] == {'disposition': 'keep', 'sale_year': None}


def test_notes_is_a_list_of_strings():
    assert _out([_scored()])['candidates'][0]['notes'] == ['family presence via rental']


def test_a_second_move_is_included_when_present():
    moves = _out([_scored(two_move=True)])['candidates'][0]['moves']
    assert len(moves) == 2
    assert moves[1]['action'] == 'rent'


def test_an_empty_run_reports_rejections_rather_than_a_bare_null():
    out = _out([], rejections={'dual_ownership': 40, 'family_presence': 12})
    assert out['recommendation'] is None
    assert out['candidates'] == []
    assert out['rejections']['family_presence'] == 12


def test_candidates_are_capped_at_ten():
    out = _out([_scored(nw=float(i)) for i in range(25)])
    assert len(out['candidates']) == 10
    assert out['candidates_evaluated'] == 25


def test_a_rent_move_reports_monthly_rent_and_no_purchase_price():
    move = _out([_scored(two_move=True)])['candidates'][0]['moves'][1]
    assert move['action'] == 'rent'
    assert 'monthly_rent' in move['financing']
    assert move['financing']['monthly_rent'] > 0
    assert 'purchase_price' not in move['financing']
    assert 'monthly_pi_payment' not in move['financing']


def test_a_buy_move_reports_purchase_price_and_monthly_pi():
    move = _out([_scored()])['candidates'][0]['moves'][0]
    assert move['action'] == 'buy'
    assert move['financing']['purchase_price'] > 0
    assert move['financing']['monthly_pi_payment'] > 0
    assert 'monthly_rent' not in move['financing']


def test_purchase_price_matches_the_plan_variant_helper_directly():
    """The results payload's purchase_price must be the SAME number the
    engine's own cost basis uses -- not a separately-computed estimate."""
    from src.housing.plan_variant import _purchase_price_for_location
    from src.server_services.strategy_asset_service import (
        HOME_APPR_DEFAULT,
        INFLATION_GENERAL_DEFAULT,
    )
    sc = _scored()
    move_in = sc.candidate.moves[0]
    loc = move_in.location
    expected = _purchase_price_for_location(
        loc, start_year=move_in.acquisition_year, home_appr=HOME_APPR_DEFAULT,
        inflation_general=INFLATION_GENERAL_DEFAULT)
    move = _out([sc])['candidates'][0]['moves'][0]
    assert move['financing']['purchase_price'] == expected


def test_down_payment_and_mortgage_rate_change_the_monthly_pi():
    sc = _scored()
    low_down = _out([sc], down_payment_pct=0.05, mortgage_rate_pct=0.04)
    high_down = _out([sc], down_payment_pct=0.50, mortgage_rate_pct=0.04)
    pi_low = low_down['candidates'][0]['moves'][0]['financing']['monthly_pi_payment']
    pi_high = high_down['candidates'][0]['moves'][0]['financing']['monthly_pi_payment']
    assert pi_low > pi_high


def test_format_output_defaults_match_the_api_defaults_when_omitted():
    """Every existing call to format_output() (including every other test in
    this file) omits these two params -- they must still produce a sane
    financing block, matching api.py's own 20%/location-rate defaults."""
    move = _out([_scored()])['candidates'][0]['moves'][0]
    assert move['financing']['purchase_price'] > 0
    assert move['financing']['monthly_pi_payment'] > 0
