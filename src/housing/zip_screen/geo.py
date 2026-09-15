"""Distance math and the radius query -- criterion 9.

Great-circle distance between ZCTA centroids. A radius is deliberately NOT
clipped at state lines: ``Location.state`` drives the residency schedule and
state income tax, so a ZIP just over the border is frequently the most
valuable result a search can return (spec decision D4).
"""
from __future__ import annotations

import math

from .schema import ALLOWED_RADII_MILES, ZipRecord

EARTH_RADIUS_MILES = 3958.7613


class InvalidRadiusError(ValueError):
    """Raised for a radius outside the four the UI offers."""


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in statute miles."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def zips_within(
    table: dict[str, ZipRecord], anchor: ZipRecord, radius_miles: int
) -> list[tuple[ZipRecord, float]]:
    """Every ZCTA within ``radius_miles`` of ``anchor``, nearest first.

    Includes the anchor itself at distance 0.
    """
    if radius_miles not in ALLOWED_RADII_MILES:
        allowed = ', '.join(str(r) for r in ALLOWED_RADII_MILES)
        raise InvalidRadiusError(f'radius_miles must be one of {allowed}; got {radius_miles!r}')
    hits: list[tuple[ZipRecord, float]] = []
    for rec in table.values():
        d = haversine_miles(anchor.lat, anchor.lon, rec.lat, rec.lon)
        if d <= radius_miles:
            hits.append((rec, d))
    hits.sort(key=lambda pair: (pair[1], pair[0].zcta))
    return hits
