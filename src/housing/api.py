"""HTTP request adapter for ``POST /api/housing/optimize``
(see src/server/plan_routes.py).

Request parsing and validation only: the optimizer itself takes typed
dataclasses and never sees a request body, so the wire contract can change
without touching the search.
"""
from __future__ import annotations

from typing import Any

from .models import (
    FamilyPresence,
    Location,
    MOVE2_STRATEGIES,
    Move2Window,
    OBJECTIVES,
    SEARCH_MODES,
    SearchWindow,
)
from .optimizer import optimize_housing

def _parse_location(raw: dict[str, Any]) -> Location:
    price_range = raw.get('target_purchase_price_range')
    parsed_range = None
    if isinstance(price_range, (list, tuple)) and len(price_range) == 2:
        parsed_range = (float(price_range[0]), float(price_range[1]))
    built_within_years_raw = raw.get('built_within_years')
    try:
        built_within_years = int(built_within_years_raw) if built_within_years_raw not in (None, '') else None
    except (TypeError, ValueError):
        built_within_years = None
    return Location(
        state=str(raw.get('state', '') or '').strip(),
        city_type=str(raw.get('city_type', 'suburban') or 'suburban').strip().lower(),
        population_size=int(raw.get('population_size', 20000) or 20000),
        target_purchase_price_range=parsed_range,
        bedrooms=int(raw.get('bedrooms', 3) or 3),
        bathrooms=float(raw.get('bathrooms', 2.0) or 2.0),
        property_type=str(raw.get('property_type', 'single_family') or 'single_family').strip().lower(),
        sqft_band=str(raw.get('sqft_band', '1800_2500') or '1800_2500').strip().lower(),
        built_within_years=built_within_years,
    )


def _parse_search_window(raw: dict[str, Any]) -> SearchWindow:
    return SearchWindow(
        earliest_sale_year=int(raw.get('earliest_sale_year', 0) or 0),
        latest_sale_year=int(raw.get('latest_sale_year', 0) or 0),
        earliest_purchase_year=int(raw.get('earliest_purchase_year', 0) or 0),
        latest_purchase_year=int(raw.get('latest_purchase_year', 0) or 0),
    )


def _parse_move2_window(raw: dict[str, Any]) -> Move2Window:
    return Move2Window(
        latest_sale_year_2=int(raw.get('latest_sale_year_2', 0) or 0),
        latest_purchase_year_2=int(raw.get('latest_purchase_year_2', 0) or 0),
    )


def _parse_family_presence(raw: dict[str, Any]) -> FamilyPresence:
    return FamilyPresence(
        region=str(raw.get('region', '') or '').strip(),
        start_year=int(raw.get('start_year', 0) or 0),
        end_year=int(raw.get('end_year', 0) or 0),
    )


def optimize_housing_from_request(
    c0: dict[str, Any], body: dict[str, Any], table_path: str | None = None
) -> tuple[dict[str, Any], int]:
    """Parse an ``/api/housing/optimize`` request body, run the optimizer
    against the current plan config ``c0``, and return a ``(payload, status)``
    pair ready for ``jsonify``. Never mutates ``c0``.

    Candidate locations arrive one of two ways, never both: ``locations`` (the
    hand-picked path) or ``zip_search`` (Stage 1 discovers them -- see
    src/housing/zip_screen/).
    """
    try:
        raw_locations = body.get('locations') or []
        raw_zip_search = body.get('zip_search')
        if raw_zip_search and raw_locations:
            return {'success': False,
                    'error': 'locations and zip_search are mutually exclusive.'}, 400

        screen_block: dict[str, Any] | None = None
        if raw_zip_search:
            if not isinstance(raw_zip_search, dict):
                return {'success': False, 'error': 'zip_search must be an object.'}, 400
            req = parse_zip_search(raw_zip_search)
            table = load_table(table_path) if table_path else None
            result = run_screen(req, table=table,
                                current_state=str(c0.get('state', '') or ''))
            screen_block = screen_payload(result)
            if len(result.shortlist) < 2:
                return {
                    'success': True, 'schema': 'housing_optimize_v1',
                    'zip_screen': screen_block, 'recommendation': None,
                    'alternatives': [],
                    'message': (
                        'The screen returned fewer than 2 ZIPs; the optimizer needs '
                        'at least 2 candidate locations. Widen the radius or lower '
                        'the minimum quality score.'
                    ),
                }, 200
            nss_by_zip = {z.zcta: z.nss for z in result.shortlist}
            locations = [
                resolve_location(load_table(table_path)[z.zcta] if table_path
                                 else load_table()[z.zcta], req.property_spec)
                for z in result.shortlist
            ]
        else:
            if not isinstance(raw_locations, list) or not (2 <= len(raw_locations) <= 4):
                return {'success': False,
                        'error': 'Provide 2-4 candidate locations, or a zip_search block.'}, 400
            nss_by_zip = {}
            locations = [_parse_location(x) for x in raw_locations]
            if any(not loc.state for loc in locations):
                return {'success': False, 'error': 'Every candidate location needs a state.'}, 400

        move1_window = _parse_search_window(body.get('move1_window') or {})
        move2_raw = body.get('move2_window')
        move2_window = _parse_move2_window(move2_raw) if move2_raw else None

        family_presence_raw = body.get('family_presence')
        family_presence = _parse_family_presence(family_presence_raw) if family_presence_raw else None

        objective = str(body.get('objective', 'net_worth') or 'net_worth')
        if objective not in OBJECTIVES:
            return {'success': False, 'error': f"Unknown objective: {objective!r}"}, 400

        search_mode = str(body.get('search_mode', 'full') or 'full')
        if search_mode not in SEARCH_MODES:
            return {'success': False, 'error': f"Unknown search_mode: {search_mode!r}"}, 400

        move2_strategy = str(body.get('move2_strategy', 'anchored') or 'anchored')
        if move2_strategy not in MOVE2_STRATEGIES:
            return {'success': False, 'error': f"Unknown move2_strategy: {move2_strategy!r}"}, 400

        result = optimize_housing(
            c0,
            locations=locations,
            move1_window=move1_window,
            move2_window=move2_window,
            anchor_count=int(body.get('anchor_count', 5) or 5),
            no_dual_ownership=bool(body.get('no_dual_ownership', True)),
            family_presence=family_presence,
            objective=objective,
            search_mode=search_mode,
            move2_strategy=move2_strategy,
            move1_action=str(body.get('move1_action', 'auto') or 'auto'),
            move2_action=str(body.get('move2_action', 'auto') or 'auto'),
            move2_concurrent=bool(body.get('move2_concurrent', False)),
        )
        if screen_block is not None:
            result['zip_screen'] = screen_block
            for row in [result.get('recommendation')] + list(result.get('alternatives') or []):
                for move in (row or {}).get('moves', []):
                    zc = (move.get('location') or {}).get('zip_code')
                    if zc in nss_by_zip:
                        move['location']['nss'] = nss_by_zip[zc]
        result['success'] = True
        result['schema'] = 'housing_optimize_v1'
        return result, 200
    except ValueError as exc:
        return {'success': False, 'error': str(exc)}, 400
    except Exception as exc:  # pragma: no cover - defensive
        return {'success': False, 'error': str(exc)}, 500


from .zip_screen.schema import (
    ALLOWED_RADII_MILES,
    NSS_DISCLOSURE,
    RESPONSE_SCHEMA,
    SCORE_MODEL_VERSION,
)
from .zip_screen.resolve import resolve_location
from .zip_screen.screen import AnchorNotFoundError, ScreenRequest, run_screen
from .zip_screen.table import load_table


def parse_zip_search(raw: dict[str, Any]) -> ScreenRequest:
    """Parse a ``zip_search`` block. Raises ValueError with a wire-ready message."""
    anchor = raw.get('anchor') or {}
    anchor_zip = str(anchor.get('zip', '') or '').strip()
    if not anchor_zip:
        raise ValueError('zip_search.anchor.zip is required.')
    try:
        radius = int(raw.get('radius_miles'))
    except (TypeError, ValueError):
        radius = -1
    if radius not in ALLOWED_RADII_MILES:
        allowed = ', '.join(str(r) for r in ALLOWED_RADII_MILES)
        raise ValueError(f'radius_miles must be one of {allowed}.')
    try:
        min_score = float(raw.get('min_quality_score', 0) or 0)
    except (TypeError, ValueError):
        raise ValueError('min_quality_score must be a number between 0 and 100.')
    if not (0.0 <= min_score <= 100.0):
        raise ValueError('min_quality_score must be between 0 and 100.')
    size = int(raw.get('shortlist_size', 4) or 4)
    return ScreenRequest(
        anchor_zip=anchor_zip,
        radius_miles=radius,
        min_quality_score=min_score,
        shortlist_size=max(2, min(4, size)),
        property_spec=dict(raw.get('property_spec') or {}),
    )


def _screened_zip_payload(z: Any) -> dict[str, Any]:
    return {
        'zip': z.zcta, 'city': z.city, 'state': z.state,
        'distance_miles': z.distance_miles, 'nss': z.nss, 'band': z.band,
        'components': z.components, 'coverage_pct': z.coverage_pct,
        'est_price': z.est_price, 'upi_adjusted': z.upi_adjusted,
        'cross_state': z.cross_state, 'promoted': z.promoted,
        'collapsed': z.collapsed,
    }


def screen_payload(result: Any) -> dict[str, Any]:
    """The ``zip_screen`` block shared by both endpoints."""
    return {
        'schema': RESPONSE_SCHEMA,
        'score_model': SCORE_MODEL_VERSION,
        'disclosure': NSS_DISCLOSURE,
        'anchor': result.anchor,
        'radius_miles': result.radius_miles,
        'funnel': result.funnel,
        'relaxation': result.relaxation,
        'shortlist': [_screened_zip_payload(z) for z in result.shortlist],
    }


def zip_screen_from_request(
    c0: dict[str, Any], body: dict[str, Any], table_path: str | None = None
) -> tuple[dict[str, Any], int]:
    """Run Stage 1 alone -- the "Preview shortlist" endpoint. No engine runs."""
    raw = body.get('zip_search')
    if not isinstance(raw, dict):
        return {'success': False, 'error': 'zip_search block is required.'}, 400
    try:
        req = parse_zip_search(raw)
        result = run_screen(
            req,
            table=load_table(table_path) if table_path else None,
            current_state=str(c0.get('state', '') or ''),
        )
    except AnchorNotFoundError as exc:
        return {'success': False, 'error': str(exc).strip("'")}, 400
    except ValueError as exc:
        return {'success': False, 'error': str(exc)}, 400
    return {'success': True, 'zip_screen': screen_payload(result)}, 200
