"""WP12.8 keep-and-rent-out: generation, the dual-ownership predicate, the
converted-home entry a candidate writes, and request validation. Pure: no
engine run (the engine-backed cases are in test_housing_rent_out_functional.py).
"""
import pytest

import src.module_catalog as mc
from src.housing.api import validate_request
from src.housing.candidates import dual_ownership_ok, generate_candidates, no_housing_gap_ok
from src.housing.models import (
    HousingCandidate, Location, Move, MoveWindow, OriginalHome, RENT_OUT, SaleWindow,
)
from src.housing.plan_variant import _apply_candidate
from src.housing.rent_out import DEFAULT_NAME, RentOutPlan, apply_rent_out, rent_out_plan

pytestmark = pytest.mark.unit

LOC = Location(state='Texas', zip_code='78701')
CONVERTED = {'name': 'Our house', 'kind': 'converted_home', 'conversion_year': 2027,
             'conversion_month': 7, 'monthly_rent': 5500.0, 'vacancy_rate': 0.04}
STANDALONE = {'name': 'Duplex', 'kind': 'standalone', 'purchase_price': 350000.0}


def _cand(disposition, action='buy', year=2028, sale_year=None):
    return HousingCandidate(OriginalHome(disposition, sale_year),
                            (Move(index=1, acquisition_year=year, action=action, location=LOC),))


def _c(on=True, props=None, home_val=900000.0):
    c = {'home_val': home_val, 'rental_properties': list(props or [])}
    mc.set_feature(c, 'rental_property_income', on)
    return c


def test_rent_out_while_buying_is_allowed_but_plain_keep_is_not():
    assert dual_ownership_ok(_cand(RENT_OUT, 'buy'))
    assert not dual_ownership_ok(_cand('keep', 'buy'))
    assert no_housing_gap_ok(_cand(RENT_OUT, 'buy', year=2040))


def test_generation_gives_rent_out_no_sale_year_and_keeps_it_under_no_dual_ownership():
    cands = generate_candidates(
        locations1=[LOC], move1_window=MoveWindow(2028, 2029), sale_window=SaleWindow(2028, 2030),
        dispositions=('sell', 'keep', RENT_OUT), move1_action='buy', no_dual_ownership=True)
    rent_out = [c for c in cands if c.original_home.disposition == RENT_OUT]
    assert [c.move1.acquisition_year for c in rent_out] == [2028, 2029]
    assert all(c.original_home.sale_year is None for c in rent_out)
    assert not [c for c in cands if c.original_home.disposition == 'keep']


def test_plan_is_none_when_the_feature_is_off_whatever_is_typed():
    assert rent_out_plan(_c(on=False, props=[CONVERTED]), 3000.0) is None


def test_rent_is_never_invented():
    assert rent_out_plan(_c()).template is None
    assert rent_out_plan(_c(props=[dict(CONVERTED, monthly_rent=None)])).template is None
    assert rent_out_plan(_c(home_val=0.0), 3000.0).template is None
    with pytest.raises(ValueError):
        rent_out_plan(_c(), 0.0)


def test_typed_rent_wins_and_keeps_the_converted_entrys_other_inputs():
    typed = rent_out_plan(_c(props=[STANDALONE]), 3000.0).template
    assert typed == {'name': DEFAULT_NAME, 'kind': 'converted_home', 'conversion_month': 7, 'sale_month': 7,
                     'monthly_rent': 3000.0}
    over = rent_out_plan(_c(props=[CONVERTED]), 4000.0).template
    assert over['monthly_rent'] == 4000.0 and over['vacancy_rate'] == 0.04
    assert rent_out_plan(_c(props=[CONVERTED])).template['monthly_rent'] == 5500.0


def test_apply_converts_in_move_1s_year_and_strips_the_plans_conversion_otherwise():
    plan = rent_out_plan(_c(props=[STANDALONE, CONVERTED]))
    c = _c(props=[STANDALONE, CONVERTED])
    apply_rent_out(c, _cand(RENT_OUT, year=2031), plan)
    assert c['rental_properties'][0] == STANDALONE
    assert c['rental_properties'][1]['conversion_year'] == 2031
    assert c['rental_properties'][1]['monthly_rent'] == 5500.0
    for disposition, sale in (('keep', None), ('sell', 2030)):
        c = _c(props=[STANDALONE, CONVERTED])
        apply_rent_out(c, _cand(disposition, sale_year=sale), plan)
        assert c['rental_properties'] == [STANDALONE]


def test_apply_drops_a_purchase_or_rental_end_that_no_longer_fits():
    plan = RentOutPlan(dict(CONVERTED, purchase_year=2030, purchase_month=3, rental_end_year=2027))
    c = _c()
    apply_rent_out(c, _cand(RENT_OUT, year=2028), plan)
    entry = c['rental_properties'][0]
    assert 'purchase_year' not in entry and 'purchase_month' not in entry and 'rental_end_year' not in entry


def test_apply_candidate_keeps_the_home_and_leaves_properties_alone_without_a_plan():
    c = _c(props=[CONVERTED])
    c.update(state='Colorado', home_sale_yr=2030)
    _apply_candidate(c, _cand('keep', 'rent'))
    assert c['home_sale_yr'] == 0 and c['rental_properties'] == [CONVERTED]
    _apply_candidate(c, _cand(RENT_OUT, 'rent'), rent_out=RentOutPlan(CONVERTED))
    assert c['home_sale_yr'] == 0 and c['rental_properties'][0]['conversion_year'] == 2028


def _body(**home):
    return {'objective': 'net_worth', 'search_mode': 'full', 'move2_strategy': 'anchored',
            'original_home': {'disposition': RENT_OUT, **home},
            'move1': {'earliest_acquisition_year': 2028, 'latest_acquisition_year': 2029, 'action': 'buy',
                      'search': {'anchors': [{'kind': 'zip', 'anchor_zip': '78701'}], 'radius_miles': 25,
                                 'area_type': 'any', 'selected_zips': ['78701'], 'dwelling': {}}}}


def test_validation_refuses_rent_out_exactly_as_before_when_off():
    assert validate_request(_body()) == "Unknown disposition: 'rent_out'."
    assert validate_request(_body(), rent_out_enabled=True) is None
    assert validate_request(_body(monthly_rent=4200), rent_out_enabled=True) is None
    assert 'more than 0' in validate_request(_body(monthly_rent='-5'), rent_out_enabled=True)
    assert 'more than 0' in validate_request(_body(monthly_rent='abc'), rent_out_enabled=True)
