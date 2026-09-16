# tests/test_housing_models_decoupled.py
"""The sale/acquisition-decoupled value types (design 2026-09-16 §5.1)."""
import dataclasses

import pytest

from src.housing.models import (
    AREA_TYPES,
    DISPOSITIONS,
    FAMILY_RADII_MILES,
    FamilyPresence,
    HousingCandidate,
    Location,
    Move,
    MoveWindow,
    OriginalHome,
    SaleWindow,
)

pytestmark = pytest.mark.unit


def _cand(*moves, disposition='sell', sale_year=2032):
    return HousingCandidate(
        original_home=OriginalHome(disposition=disposition, sale_year=sale_year),
        moves=tuple(moves),
    )


def _move(index=1, year=2033, action='buy', state='CO', mode='sequential'):
    return Move(index=index, acquisition_year=year, action=action,
                location=Location(state=state), mode=mode)


def test_keep_carries_no_sale_year():
    home = OriginalHome(disposition='keep', sale_year=None)
    assert home.sale_year is None


def test_a_move_has_an_acquisition_year_not_a_purchase_year():
    field_names = {f.name for f in dataclasses.fields(Move)}
    assert 'acquisition_year' in field_names
    assert 'purchase_year' not in field_names


def test_candidate_exposes_move1_and_move2():
    one = _cand(_move(index=1))
    assert one.move1.index == 1
    assert one.move2 is None
    assert one.is_two_move is False

    two = _cand(_move(index=1), _move(index=2, year=2041))
    assert two.move2.acquisition_year == 2041
    assert two.is_two_move is True


def test_rent_is_an_action_not_a_missing_year():
    """The old model encoded 'rent' as purchase_year=None, which made a rental
    indistinguishable from an unset field. A rental now has a real year."""
    m = _move(action='rent', year=2035)
    assert m.action == 'rent'
    assert m.acquisition_year == 2035


def test_family_presence_is_a_zip_and_a_radius():
    fp = FamilyPresence(zip_code='60521', radius_miles=25,
                        from_year=2026, through_year=2050)
    assert fp.zip_code == '60521'
    assert fp.radius_miles in FAMILY_RADII_MILES
    assert not hasattr(fp, 'region')


def test_windows_are_separate_types():
    assert SaleWindow(2030, 2045).latest_sale_year == 2045
    assert MoveWindow(2031, 2046).earliest_acquisition_year == 2031


def test_enumerations_match_the_spec_exactly():
    assert DISPOSITIONS == ('sell', 'keep', 'auto')
    assert AREA_TYPES == ('any', 'urban', 'suburban', 'exurban', 'rural')
    assert FAMILY_RADII_MILES == (10, 25, 50, 100)
