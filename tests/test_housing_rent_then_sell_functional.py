"""H6: "rent out, then sell in year X" (RENTAL_TAX_RULES.md section 13; WP12.8 doubt 1).

The frozen sample plan, one move-1 location (2028), sale years 2029-2033: the home is rented
from move 1's year and sold in the searched year, through the engine's converted-home sale
(recapture, two-of-five test) with the sale gain in AGI and the IRMAA lookback (H1).
"""
from __future__ import annotations

import pytest

import src.housing_optimizer as ho
from src.housing.api import validate_request
from src.housing.models import RENT_OUT, RENT_THEN_SELL
from src.housing.rent_out import exact_rent_tax
from tests.test_housing_rent_out_functional import RENT, _by_disposition, _c0, _optimize

pytestmark = pytest.mark.integration


@pytest.fixture(scope='module')
def result():
    return _optimize(_c0(True), sale_window=ho.SaleWindow(2029, 2033), rent_out_monthly_rent=RENT)


def _then_sell(result):
    return {r['original_home']['sale_year']: r for r in result['candidates']
            if r['original_home']['disposition'] == RENT_THEN_SELL}


def test_auto_searches_the_sale_year_after_the_conversion(result):
    rows = _then_sell(result)
    assert sorted(rows) == [2029, 2030, 2031, 2032, 2033]
    assert RENT_OUT in {r['original_home']['disposition'] for r in result['candidates']}
    assert rows[2030]['original_home']['conversion_year'] == 2028
    assert rows[2030]['original_home']['monthly_rent'] == RENT


def test_a_sale_in_or_before_the_conversion_year_is_not_generated():
    out = _optimize(_c0(True), sale_window=ho.SaleWindow(2027, 2028), rent_out_monthly_rent=RENT)
    assert RENT_THEN_SELL not in {r['original_home']['disposition'] for r in out['candidates']}


def test_notes_carry_the_sale_facts_and_no_dual_ownership_flag(result):
    notes = _then_sell(result)[2030]['notes']
    assert notes[0] == 'rented out from 2028, sold in 2030'
    assert any(n.startswith('§121 two-of-five met for the 2030 sale') for n in notes)
    assert any(n.startswith('§1250 recapture on the sale: $') for n in notes)
    assert any('is in 2030 AGI; IRMAA tier' in n and 'in 2032' in n for n in notes)
    assert not any(n.startswith('dual_ownership_years') for n in notes)
    late = _then_sell(result)[2033]['notes']
    assert any(n.startswith('§121 two-of-five NOT met for the 2033 sale') and '2031' in n for n in late)


def test_exact_rent_tax_leaves_the_sale_tax_to_the_lifetime_cost():
    with_rent = [{'total_tax': 100.0, 'home_sale_tax': 40.0}, {'total_tax': 10.0}]
    without = [{'total_tax': 70.0, 'home_sale_tax': 35.0}, {'total_tax': 5.0}]
    assert exact_rent_tax(with_rent, without) == pytest.approx((100 - 40 + 10) - (70 - 35 + 5))


def _body(**home):
    return {'objective': 'net_worth', 'search_mode': 'full', 'move2_strategy': 'anchored',
            'original_home': {'disposition': RENT_THEN_SELL, 'earliest_sale_year': 2029,
                              'latest_sale_year': 2033, **home},
            'move1': {'earliest_acquisition_year': 2028, 'latest_acquisition_year': 2029, 'action': 'buy',
                      'search': {'anchors': [{'kind': 'zip', 'anchor_zip': '78701'}], 'radius_miles': 25,
                                 'area_type': 'any', 'selected_zips': ['78701'], 'dwelling': {}}}}


def test_rent_then_sell_is_an_unknown_disposition_off_and_validated_on():
    assert validate_request(_body()) == "Unknown disposition: 'rent_then_sell'."
    assert validate_request(_body(), rent_out_enabled=True) is None
    assert 'Earliest sale year' in validate_request(_body(earliest_sale_year=2034), rent_out_enabled=True)
    with pytest.raises(ValueError, match="Unknown disposition: 'rent_then_sell'"):
        _optimize(_c0(False), dispositions=(RENT_THEN_SELL,), rent_out_monthly_rent=RENT)
