"""Turn a screened ZCTA into the ``Location`` the optimizer already understands.

This is the boundary: past this module nothing knows what a ZIP is.
``Location.state`` drives residency and state income tax, and
``city_type``/``population_size`` drive the STATE_ESTIMATES cost lookup (see
plan_variant.py), so resolution means deriving exactly those three fields and
passing the caller's property spec through unchanged.
"""
from __future__ import annotations

from typing import Any

from ..models import (
    DENSITY_EXURBAN,
    DENSITY_SUBURBAN,
    DENSITY_URBAN,
    Location,
)
from .schema import ZipRecord


def city_type_for_density(density: float) -> str:
    """Bucket a ZCTA's people-per-square-mile into the optimizer's city_type."""
    if density >= DENSITY_URBAN:
        return 'urban'
    if density >= DENSITY_SUBURBAN:
        return 'suburban'
    if density >= DENSITY_EXURBAN:
        return 'exurban'
    return 'rural'


def resolve_location(rec: ZipRecord, spec: dict[str, Any]) -> Location:
    """Build a ``Location`` from a ZCTA plus the caller's property spec.

    ``population_size`` prefers the ZIP's primary Census place -- the cost
    estimate is calibrated on city population, not on ZCTA population -- and
    falls back to the ZCTA's own population for a ZIP with no place match.
    """
    price_range = spec.get('target_purchase_price_range')
    if isinstance(price_range, (list, tuple)) and len(price_range) == 2:
        price_range = (float(price_range[0]), float(price_range[1]))
    else:
        price_range = None
    return Location(
        state=rec.state,
        city_type=city_type_for_density(rec.density),
        population_size=rec.place_population or rec.zcta_population,
        target_purchase_price_range=price_range,
        bedrooms=int(spec.get('bedrooms', 3) or 3),
        bathrooms=float(spec.get('bathrooms', 2.0) or 2.0),
        property_type=str(spec.get('property_type', 'single_family') or 'single_family'),
        sqft_band=str(spec.get('sqft_band', '1800_2500') or '1800_2500'),
        built_within_years=spec.get('built_within_years') or None,
        zip_code=rec.zcta,
    )
