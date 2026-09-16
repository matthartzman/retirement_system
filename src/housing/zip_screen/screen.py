"""Stage 1: narrow every ZCTA in range down to a promotable shortlist.

Pure table math -- no engine runs. A 50-mile radius can cover ~300 ZCTAs and
the optimizer runs the full deterministic engine (and Monte Carlo) per
candidate, so the screen exists to hand the optimizer a handful of genuinely
different bets rather than three hundred near-duplicates.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .geo import haversine_miles, zips_within
from .quality import score_zip
from .resolve import city_type_for_density
from .schema import (
    COVERAGE_FLOOR_PCT,
    DEDUP_RADIUS_MILES,
    DEDUP_SCORE_POINTS,
    ZipRecord,
)
from .table import load_table


class AnchorNotFoundError(ValueError):
    """The anchor ZIP is not in the snapshot."""


@dataclass(frozen=True)
class ScreenRequest:
    anchor_zip: str
    radius_miles: int
    min_quality_score: float
    shortlist_size: int
    property_spec: dict[str, Any]
    area_type: str = 'any'
    max_population: int | None = None


@dataclass(frozen=True)
class ScreenedZip:
    zcta: str
    city: str
    state: str
    distance_miles: float
    nss: float
    band: str
    coverage_pct: float
    est_price: float
    components: dict[str, float]
    area_type: str = 'suburban'
    population: int = 0
    upi_adjusted: bool = False
    cross_state: str | None = None
    promoted: bool = False
    collapsed: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScreenResult:
    anchor: dict[str, Any]
    radius_miles: int
    funnel: dict[str, int]
    shortlist: list[ScreenedZip]
    all_passing: list[ScreenedZip]
    relaxation: dict[str, Any] | None = None


def estimate_price(rec: ZipRecord, base_estimate: float) -> float:
    """Scale a state-level price estimate by this ZIP's relative home value.

    STATE_ESTIMATES is keyed on state + city_type + population, so without this
    every ZIP in a state sharing a city_type would price identically and the
    affordability filter would have no discriminating power. ACS median home
    value supplies the within-state spread.
    """
    if not rec.median_home_value or not rec.state_median_home_value:
        return base_estimate
    return base_estimate * (rec.median_home_value / rec.state_median_home_value)


def _base_estimate(rec: ZipRecord) -> float:
    """State-median anchor for the affordability ratio.

    ``estimate_price`` multiplies this by the ZIP's median-home-value ratio to
    its state. Keeping the anchor at the state median leaves this module free
    of any engine or STATE_ESTIMATES dependency; the optimizer does the real
    cost modelling in Stage 2 on the resolved Location.
    """
    return float(rec.state_median_home_value or 0.0)


def deduplicate(
    candidates: list[ScreenedZip], coords: dict[str, tuple[float, float]]
) -> list[ScreenedZip]:
    """Collapse near-identical neighbours, highest score first.

    A candidate is suppressed when an already-kept candidate is within
    DEDUP_RADIUS_MILES, in the same state, and within DEDUP_SCORE_POINTS.
    Without this the top 4 of a metro search are routinely four adjacent
    suburbs of one town, and the engine spends four full runs comparing
    near-duplicates.

    Suppressed ZIPs are recorded on their survivor's ``collapsed`` list, never
    silently discarded -- a hidden ranking policy is indistinguishable from a
    bug to the person reading the results.
    """
    kept: list[ScreenedZip] = []
    collapsed_by: dict[str, list[str]] = {}
    for cand in sorted(candidates, key=lambda z: (-z.nss, z.distance_miles, z.zcta)):
        lat, lon = coords[cand.zcta]
        survivor = None
        for k in kept:
            klat, klon = coords[k.zcta]
            if (
                k.state == cand.state
                and abs(k.nss - cand.nss) <= DEDUP_SCORE_POINTS
                and haversine_miles(klat, klon, lat, lon) <= DEDUP_RADIUS_MILES
            ):
                survivor = k
                break
        if survivor is None:
            kept.append(cand)
            collapsed_by.setdefault(cand.zcta, [])
        else:
            collapsed_by[survivor.zcta].append(cand.zcta)
    return [
        ScreenedZip(**{**z.__dict__, 'collapsed': sorted(collapsed_by.get(z.zcta, []))})
        for z in kept
    ]


def _relaxation(
    stages: dict[str, list], min_quality_score: float,
    area_type: str, max_population: int | None,
) -> dict[str, Any] | None:
    """What would the user have to give up to get results?

    A bare "no results" on a nine-stage funnel is unusable: the user cannot
    tell which constraint emptied it. Report the FIRST stage that went to zero
    while its predecessor had survivors -- that is the binding constraint, and
    relaxing anything later would change nothing.
    """
    with_data = stages['with_data']
    if not with_data:
        return None

    scores = sorted((t[2].score for t in with_data), reverse=True)
    if not stages['above_score']:
        suggested = math.floor(scores[0] * 10) / 10
        return {'stage': 'above_score', 'field': 'min_quality_score',
                'current': min_quality_score, 'suggested': suggested,
                'would_return': sum(1 for s in scores if s >= suggested)}

    if not stages['matching_area_type']:
        available = sorted({city_type_for_density(t[0].density)
                            for t in stages['above_score']})
        return {'stage': 'matching_area_type', 'field': 'area_type',
                'current': area_type, 'suggested': available[0] if available else 'any',
                'would_return': len(stages['above_score'])}

    if not stages['under_population_cap']:
        pops = sorted((t[0].place_population or t[0].zcta_population or 0)
                      for t in stages['matching_area_type'])
        return {'stage': 'under_population_cap', 'field': 'max_population',
                'current': max_population, 'suggested': pops[0],
                'would_return': sum(1 for p in pops if p <= pops[0])}

    if not stages['affordable']:
        return {'stage': 'affordable', 'field': 'target_purchase_price_range',
                'current': None, 'suggested': None,
                'would_return': len(stages['under_population_cap'])}
    return None


def run_screen(
    req: ScreenRequest,
    table: dict[str, ZipRecord] | None = None,
    current_state: str = '',
) -> ScreenResult:
    """Run the Stage-1 funnel, recording each stage's surviving count."""
    data = table if table is not None else load_table()
    anchor = data.get(str(req.anchor_zip).strip())
    if anchor is None:
        raise AnchorNotFoundError(
            f'anchor ZIP {req.anchor_zip!r} is not in the screening snapshot'
        )

    in_radius = zips_within(data, anchor, req.radius_miles)
    funnel = {'in_radius': len(in_radius)}

    price_range = req.property_spec.get('target_purchase_price_range')
    lo, hi = (float(price_range[0]), float(price_range[1])) if price_range else (None, None)

    with_data: list[tuple[ZipRecord, float, Any]] = []
    for rec, dist in in_radius:
        nss = score_zip(rec)
        if nss.coverage_pct < COVERAGE_FLOOR_PCT:
            continue
        with_data.append((rec, dist, nss))
    funnel['with_data'] = len(with_data)

    above_score = [t for t in with_data if t[2].score >= req.min_quality_score]
    funnel['above_score'] = len(above_score)

    area_type = str(req.area_type or 'any').strip().lower()
    if area_type in ('', 'any'):
        matching_area = above_score
    else:
        matching_area = [t for t in above_score
                         if city_type_for_density(t[0].density) == area_type]
    funnel['matching_area_type'] = len(matching_area)

    cap = req.max_population
    if cap is None:
        under_cap = matching_area
    else:
        under_cap = [t for t in matching_area
                     if (t[0].place_population or t[0].zcta_population or 0) <= int(cap)]
    funnel['under_population_cap'] = len(under_cap)

    passing: list[ScreenedZip] = []
    for rec, dist, nss in under_cap:
        price = estimate_price(rec, _base_estimate(rec))
        if lo is not None and not (lo <= price <= hi):
            continue
        passing.append(ScreenedZip(
            zcta=rec.zcta,
            city=rec.primary_place,
            state=rec.state,
            distance_miles=round(dist, 2),
            nss=round(nss.score, 1),
            band=nss.band,
            coverage_pct=round(nss.coverage_pct, 1),
            est_price=round(price, 2),
            components={k: round(v, 1) for k, v in nss.components.items()},
            area_type=city_type_for_density(rec.density),
            population=rec.place_population or rec.zcta_population or 0,
            upi_adjusted=nss.upi_adjusted,
            cross_state=rec.state if current_state and rec.state != current_state else None,
        ))
    funnel['affordable'] = len(passing)
    affordable_passing = list(passing)

    coords = {rec.zcta: (rec.lat, rec.lon) for rec, _, _ in under_cap}
    passing = deduplicate(passing, coords)
    funnel['distinct'] = len(passing)
    funnel['near_family'] = len(passing)

    shortlist = [
        ScreenedZip(**{**z.__dict__, 'promoted': True})
        for z in passing[: max(0, int(req.shortlist_size))]
    ]
    funnel['promoted'] = len(shortlist)

    return ScreenResult(
        anchor={'zip': anchor.zcta, 'city': anchor.primary_place,
                'state': anchor.state, 'lat': anchor.lat, 'lon': anchor.lon},
        radius_miles=req.radius_miles,
        funnel=funnel,
        shortlist=shortlist,
        all_passing=passing,
        relaxation=_relaxation(
            {'with_data': with_data, 'above_score': above_score,
             'matching_area_type': matching_area, 'under_population_cap': under_cap,
             'affordable': affordable_passing},
            req.min_quality_score, area_type, req.max_population,
        ) if not shortlist else None,
    )
