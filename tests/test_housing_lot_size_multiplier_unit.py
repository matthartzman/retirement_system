"""Lot-size band as a price multiplier (design 2026-09-16 Sec6.3)."""
import pytest

from src.housing.models import Location
from src.server_services.strategy_asset_service import (
    LOT_SIZE_BAND_LABELS,
    LOT_SIZE_BAND_MULT,
    estimate_housing_cost,
)

pytestmark = pytest.mark.unit


def _estimate(**overrides):
    """Local helper: estimate_housing_cost is keyword-only with every
    argument required except lot_size_band, so fill in reasonable defaults
    for everything the individual tests below don't care about.
    """
    kwargs = dict(
        state='IL',
        housing_type='purchase',
        city_type='suburban',
        population_size=20000,
        bedrooms=3,
        bathrooms=2.0,
        property_type='single_family',
        sqft_band='1800_2500',
        built_within_years=None,
        start_year=0,
        home_appr=0.03,
        inflation_general=0.025,
    )
    kwargs.update(overrides)
    return estimate_housing_cost(**kwargs)


def test_bands_and_labels_cover_the_same_five_keys():
    expected = {'under_quarter', 'quarter_half', 'half_one', 'one_three', 'over_three'}
    assert set(LOT_SIZE_BAND_MULT) == expected
    assert set(LOT_SIZE_BAND_LABELS) == expected


def test_quarter_half_is_the_neutral_default():
    assert LOT_SIZE_BAND_MULT['quarter_half'] == 1.00
    assert Location(state='IL').lot_size_band == 'quarter_half'


def test_multiplier_increases_monotonically_with_lot_size():
    order = ['under_quarter', 'quarter_half', 'half_one', 'one_three', 'over_three']
    values = [LOT_SIZE_BAND_MULT[k] for k in order]
    assert values == sorted(values)
    assert len(set(values)) == len(values)


def test_a_bigger_lot_raises_the_estimated_purchase_price():
    base = _estimate(lot_size_band='quarter_half')
    big = _estimate(lot_size_band='one_three')
    assert big['purchase_price'] > base['purchase_price']


def test_an_unknown_band_falls_back_to_neutral_rather_than_raising():
    neutral = _estimate(lot_size_band='quarter_half')
    junk = _estimate(lot_size_band='not_a_band')
    assert junk['purchase_price'] == neutral['purchase_price']
