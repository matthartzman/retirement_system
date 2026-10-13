"""WP12.8 keep-and-rent-out through the real engine (design 2026-10-05 decision 2,
sections 4 and 8; housing refinement design section 13).

The frozen sample plan (home 1,313,000, basis 800,000) with one move-1 location.
Off, a typed rent and a converted-home entry change nothing and ``rent_out`` is an
unknown disposition. On, ``rent_out`` is searched next to sell and keep, owns the home
beside a bought one, moves its carrying costs to Schedule E (counted once), and its
row notes the section 121 window, the depreciation recaptured on a sale and the
two-home overlap. A home lived in under two years fails the test (warn only).
"""
from __future__ import annotations

import copy
import json

import pytest

import src.housing_optimizer as ho
import src.module_catalog as mc
from src.data_io import parse_rental_properties
from src.housing.models import RENT_OUT
from src.housing.rent_out import rent_out_plan
from tests import rental_fixtures as rf
from tests.golden_pricing import frozen_holdings_prices
from tests.test_deterministic_engine_full_row_snapshot_regression import empty_workspace

pytestmark = pytest.mark.integration

TX = ho.Location(state='Texas', population_size=150000, zip_code='78701')
RENT = 5500.0


def _c0(on: bool, converted: dict | None = None) -> dict:
    c = rf.base_config()
    if converted is not None:
        parse_rental_properties(c, [converted])
    mc.set_feature(c, 'rental_property_income', on)
    return c


def _optimize(c0: dict, **kw) -> dict:
    args = dict(locations1=[TX], sale_window=ho.SaleWindow(2028, 2028),
                move1_window=ho.MoveWindow(2028, 2028), dispositions=('auto',),
                move1_action='buy', no_dual_ownership=False, mortgage_rate_pct=0.065)
    args.update(kw)
    with empty_workspace(), frozen_holdings_prices():
        return ho.optimize_housing(copy.deepcopy(c0), **args)


def _by_disposition(result: dict) -> dict:
    return {r['original_home']['disposition']: r for r in result['candidates']}


@pytest.fixture(scope='module')
def runs():
    off = _c0(False, rf.CONVERTED_HOME)
    on = _c0(True)
    # Warm-up: the first optimizer run in a pytest process ends a few thousand dollars
    # away from every later one (baseline included). That predates WP12.8; it is not
    # what these comparisons are about.
    _optimize(off)
    return {
        'off': _optimize(off),
        'off_with_rent': _optimize(off, rent_out_monthly_rent=RENT),
        'on': _optimize(on, rent_out_monthly_rent=RENT),
        'on_again': _optimize(on, rent_out_monthly_rent=RENT),
    }


def test_off_the_candidate_set_and_results_ignore_rent_out(runs):
    assert json.dumps(runs['off'], sort_keys=True) == json.dumps(runs['off_with_rent'], sort_keys=True)
    assert set(_by_disposition(runs['off'])) == {'sell', 'keep'}
    assert not any('rent' in n for r in runs['off']['candidates'] for n in r['notes'])
    with pytest.raises(ValueError, match="Unknown disposition: 'rent_out'"):
        _optimize(_c0(False), dispositions=(RENT_OUT,), rent_out_monthly_rent=RENT)


def test_on_auto_compares_rent_out_with_sell_and_keep_after_tax(runs):
    rows = _by_disposition(runs['on'])
    assert set(rows) == {'sell', 'keep', RENT_OUT}
    rent, keep = rows[RENT_OUT], rows['keep']
    assert rent['original_home'] == {'disposition': RENT_OUT, 'sale_year': None, 'conversion_year': 2028}
    # Same home kept, same purchase: the difference is the rent and its tax.
    assert rent['net_worth'] > keep['net_worth']
    assert rent['lifetime_cost'] < keep['lifetime_cost']
    assert 'conversion_year' not in keep['original_home']


def test_rent_out_notes_carry_the_section_121_window_and_the_recapture(runs):
    notes = _by_disposition(runs['on'])[RENT_OUT]['notes']
    assert notes[0] == 'rented out from 2028'
    # Lived in through July 2028: a sale by July 2031 still has 730 days of use in five years.
    assert '§121 two-of-five: exclusion only if sold by 2031' in notes
    recapture = [n for n in notes if n.startswith('§1250 recapture: $')]
    assert recapture and 'taxed up to 25% on a sale' in recapture[0]
    assert 'dual_ownership_years 2028- (current home rented out)' in notes
    assert not any(m['sec121_exclusion_lost'] for m in _by_disposition(runs['on'])[RENT_OUT]['moves'])


def test_rent_out_is_allowed_with_no_dual_ownership_and_plain_keep_is_not():
    result = _optimize(_c0(True), no_dual_ownership=True, rent_out_monthly_rent=RENT)
    assert set(_by_disposition(result)) == {'sell', RENT_OUT}
    assert result['rejections']['dual_ownership'] == 1


def test_both_homes_carrying_costs_are_counted_once():
    c0 = _c0(True)
    plan = rent_out_plan(c0, RENT)
    cand = ho.HousingCandidate(ho.OriginalHome(RENT_OUT), (ho.Move(1, 2028, 'buy', TX),))
    keep = ho.HousingCandidate(ho.OriginalHome('keep'), (ho.Move(1, 2028, 'buy', TX),))
    with empty_workspace(), frozen_holdings_prices():
        _c, rent_rows = ho._run_engine(c0, cand, mortgage_rate_pct=0.065, rent_out=plan)
        _c, keep_rows = ho._run_engine(c0, keep, mortgage_rate_pct=0.065, rent_out=plan)
    r, k = rf.by_year(rent_rows)[2029], rf.by_year(keep_rows)[2029]
    shifted = r['converted_home_carrying_costs']
    assert r['converted_home_share'] == 1.0 and shifted > 0
    # Spending drops by exactly what moved to Schedule E; the new home's costs stay.
    assert k['total_spend'] - r['total_spend'] == pytest.approx(shifted)
    assert r['next_housing_mortgage_balance'] == pytest.approx(k['next_housing_mortgage_balance'])
    assert r['home_val'] == pytest.approx(k['home_val']) and r['rental_property_value'] == 0
    assert r['rental_gross_rent'] == pytest.approx(RENT * 12 * 1.025 ** 3)


def test_a_home_lived_in_under_two_years_warns_that_section_121_fails():
    recent = dict(rf.CONVERTED_HOME, purchase_year=2027, purchase_month=1)  # bought Jan 2027
    result = _optimize(_c0(True, recent), dispositions=(RENT_OUT,))
    row = result['candidates'][0]
    assert row['original_home']['disposition'] == RENT_OUT
    assert '§121 two-of-five test fails: no exclusion on any sale of the rented home' in row['notes']
    assert any(n.startswith('§1250 recapture') for n in row['notes'])


def test_no_rent_means_no_rent_out_candidate():
    with pytest.raises(ValueError, match='needs a monthly rent'):
        _optimize(_c0(True), dispositions=(RENT_OUT,))
    # Auto without a rent never invents one: it searches sell and keep only.
    assert 'rent_out' not in str(rent_out_plan(_c0(True)))


def test_deterministic(runs):
    assert json.dumps(runs['on'], sort_keys=True) == json.dumps(runs['on_again'], sort_keys=True)
