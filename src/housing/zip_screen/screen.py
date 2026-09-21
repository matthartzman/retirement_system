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

from ...server_services.strategy_asset_service import HOME_APPR_DEFAULT
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
    # Budget-basis fields (design 2026-09-19 §6.4 site 4). ``target_purchase_
    # price_range`` in ``property_spec`` is move-year dollars (OQ-2); the
    # screen's own price estimate stays today's dollars (screen.estimate_price
    # is untouched), so the *bounds* -- never the estimate -- are deflated by
    # ``home_appr`` over the years from ``plan_start`` to ``reference_year``
    # before the affordability comparison. Defaults are a no-op (deflator 1),
    # so a caller that does not care about basis (most existing tests) is
    # unaffected.
    home_appr: float = HOME_APPR_DEFAULT
    plan_start: int = 0
    reference_year: int = 0


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
    nearest_anchor_zip: str = ''
    family_distance_miles: float | None = None
    # = plan_start at screen time (design §6.4 site 4), so a downstream
    # consumer can never mistake est_price's basis: it is always today's
    # (this) dollars, never the move's own year.
    est_price_basis_year: int = 0


@dataclass(frozen=True)
class ScreenResult:
    anchor: dict[str, Any]
    radius_miles: int
    funnel: dict[str, int]
    shortlist: list[ScreenedZip]
    all_passing: list[ScreenedZip]
    relaxation: dict[str, Any] | None = None
    anchors: list[dict[str, Any]] = field(default_factory=list)
    stage_zctas: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class MultiAnchorRequest:
    anchor_zips: list[str]
    radius_miles: int
    min_quality_score: float
    shortlist_size: int
    property_spec: dict[str, Any]
    area_type: str = 'any'
    max_population: int | None = None
    # See ScreenRequest's matching fields -- same budget-basis deflation,
    # applied per anchor by run_multi_anchor_screen below.
    home_appr: float = HOME_APPR_DEFAULT
    plan_start: int = 0
    reference_year: int = 0


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


def family_distance_for_zip(
    zip_code: str | None, family_zip: str | None,
    coords: dict[str, tuple[float, float]],
) -> float | None:
    """Miles from ``zip_code`` to ``family_zip``, or None if either is
    unknown. The one distance-to-family calculation, shared by the screen's
    ``annotate_family_distance`` below and by the optimizer, which annotates
    the ``Location``s it was handed rather than ``ScreenedZip``s.
    """
    family = coords.get(family_zip) if family_zip else None
    here = coords.get(zip_code) if zip_code else None
    if family is None or here is None:
        return None
    return round(haversine_miles(family[0], family[1], here[0], here[1]), 2)


def annotate_family_distance(
    shortlist: list[ScreenedZip], family_zip: str | None,
    coords: dict[str, tuple[float, float]],
) -> list[ScreenedZip]:
    """Record each ZIP's distance to the family ZIP for display.

    An empty result under a tight family radius is otherwise undiagnosable:
    the user sees zero candidates with no indication of how close the search
    came.
    """
    if not family_zip or coords.get(family_zip) is None:
        return list(shortlist)
    return [
        ScreenedZip(**{**z.__dict__,
                       'family_distance_miles': family_distance_for_zip(
                           z.zcta, family_zip, coords)})
        for z in shortlist
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
    if lo is not None:
        # §6.4 site 4: the budget is move-year dollars (OQ-2); the screen's
        # own est_price stays today's dollars. Deflate the bounds -- never
        # the estimate -- by the same rate the engine uses for a home's own
        # appreciation, over the years from plan_start to the reference year
        # (the move window's midpoint). A current-year window (reference_year
        # <= plan_start, or unset) deflates by 1 -- a no-op, so funnel counts
        # are unchanged for it.
        years_out = max(0, int(req.reference_year) - int(req.plan_start)) if req.reference_year else 0
        deflator = (1.0 + float(req.home_appr)) ** years_out if years_out else 1.0
        lo, hi = lo / deflator, hi / deflator

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
            est_price_basis_year=int(req.plan_start),
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

    # Which ZCTAs survived each stage, not just how many. A multi-anchor union
    # needs the identities to count distinct ZIPs; summing per-anchor counts
    # would double-count every ZIP that sits inside two overlapping radii.
    stage_zctas = {
        'in_radius': [r.zcta for r, _ in in_radius],
        'with_data': [t[0].zcta for t in with_data],
        'above_score': [t[0].zcta for t in above_score],
        'matching_area_type': [t[0].zcta for t in matching_area],
        'under_population_cap': [t[0].zcta for t in under_cap],
        'affordable': [z.zcta for z in affordable_passing],
        'distinct': [z.zcta for z in passing],
        'near_family': [z.zcta for z in passing],
        'promoted': [z.zcta for z in shortlist],
    }

    return ScreenResult(
        anchor={'zip': anchor.zcta, 'city': anchor.primary_place,
                'state': anchor.state, 'lat': anchor.lat, 'lon': anchor.lon},
        radius_miles=req.radius_miles,
        funnel=funnel,
        shortlist=shortlist,
        all_passing=passing,
        stage_zctas=stage_zctas,
        relaxation=_relaxation(
            {'with_data': with_data, 'above_score': above_score,
             'matching_area_type': matching_area, 'under_population_cap': under_cap,
             'affordable': affordable_passing},
            req.min_quality_score, area_type, req.max_population,
        ) if not shortlist else None,
    )


def run_multi_anchor_screen(
    req: MultiAnchorRequest, table: dict[str, ZipRecord] | None = None,
    current_state: str = '',
) -> ScreenResult:
    """Screen each anchor, then union before dedup and promotion.

    Unioning first is what makes two overlapping metros behave like one
    search: dedup and the shortlist cap both then operate on distinct ZIPs, so
    a ZIP in both radii cannot occupy two shortlist slots and the funnel counts
    ZIPs rather than (ZIP, anchor) pairs.
    """
    data = table if table is not None else load_table()
    per_anchor: list[ScreenResult] = []
    for zip_code in req.anchor_zips:
        per_anchor.append(run_screen(
            ScreenRequest(
                anchor_zip=zip_code, radius_miles=req.radius_miles,
                min_quality_score=req.min_quality_score,
                shortlist_size=len(data),          # no per-anchor truncation
                property_spec=req.property_spec,
                area_type=req.area_type, max_population=req.max_population,
                home_appr=req.home_appr, plan_start=req.plan_start,
                reference_year=req.reference_year,
            ),
            table=data, current_state=current_state,
        ))

    best: dict[str, ScreenedZip] = {}
    for anchor_result, zip_code in zip(per_anchor, req.anchor_zips):
        for z in anchor_result.all_passing:
            tagged = ScreenedZip(**{**z.__dict__, 'nearest_anchor_zip': zip_code,
                                    'promoted': False})
            prior = best.get(z.zcta)
            if prior is None or tagged.distance_miles < prior.distance_miles:
                best[z.zcta] = tagged

    # Per-anchor stages are unioned on ZCTA identity; the three stages that
    # follow dedup are recomputed below on the unioned set, overwriting these.
    funnel = {k: 0 for k in per_anchor[0].funnel} if per_anchor else {}
    for key in funnel:
        seen: set[str] = set()
        for anchor_result in per_anchor:
            seen |= set(anchor_result.stage_zctas.get(key, ()))
        funnel[key] = len(seen)

    union = sorted(best.values(), key=lambda z: (-z.nss, z.distance_miles, z.zcta))
    coords = {z.zcta: (data[z.zcta].lat, data[z.zcta].lon) for z in union}
    distinct = deduplicate(union, coords)
    funnel['distinct'] = len(distinct)
    funnel['near_family'] = len(distinct)

    shortlist = [ScreenedZip(**{**z.__dict__, 'promoted': True})
                 for z in distinct[: max(0, int(req.shortlist_size))]]
    funnel['promoted'] = len(shortlist)

    return ScreenResult(
        anchor=per_anchor[0].anchor if per_anchor else {},
        anchors=[r.anchor for r in per_anchor],
        radius_miles=req.radius_miles,
        funnel=funnel,
        shortlist=shortlist,
        all_passing=distinct,
        relaxation=next((r.relaxation for r in per_anchor if r.relaxation), None)
        if not shortlist else None,
    )
