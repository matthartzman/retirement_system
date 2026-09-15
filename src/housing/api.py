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


def optimize_housing_from_request(c0: dict[str, Any], body: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Parse an ``/api/housing/optimize`` request body, run the optimizer
    against the current plan config ``c0``, and return a ``(payload, status)``
    pair ready for ``jsonify``. Never mutates ``c0`` (every candidate runs on
    a deep copy via ``planning_engines.run_scenario``).
    """
    try:
        raw_locations = body.get('locations') or []
        if not isinstance(raw_locations, list) or not (2 <= len(raw_locations) <= 4):
            return {'success': False, 'error': 'Provide 2-4 candidate locations.'}, 400
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
        result['success'] = True
        result['schema'] = 'housing_optimize_v1'
        return result, 200
    except ValueError as exc:
        return {'success': False, 'error': str(exc)}, 400
    except Exception as exc:  # pragma: no cover - defensive
        return {'success': False, 'error': str(exc)}, 500
