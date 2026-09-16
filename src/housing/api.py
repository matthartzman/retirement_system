"""HTTP request adapter for ``POST /api/housing/optimize`` and
``POST /api/housing/zip-screen`` (see src/server/plan_routes.py).

Request parsing and validation only: the optimizer itself takes typed
dataclasses and never sees a request body, so the wire contract can change
without touching the search.

v2 (design 2026-09-16). The manual-location mode (``locations``) is gone --
every candidate location now comes from a per-move ZIP-radius screen
(``search``), and each move carries its own acquisition window instead of the
old single sale/purchase grid. ``validate_request`` is the server-side copy
of design §8's rules: the panel duplicates them for speed of feedback, but
this copy is the one that is trusted, and it is evaluated in the same order
so client and server never disagree about which rule fired first.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from .models import (
    AREA_TYPES,
    DISPOSITIONS,
    FAMILY_RADII_MILES,
    FamilyPresence,
    MOVE2_STRATEGIES,
    MoveWindow,
    OBJECTIVES,
    SEARCH_MODES,
    SaleWindow,
)
from .optimizer import optimize_housing
from .zip_screen.schema import (
    ALLOWED_RADII_MILES,
    NSS_DISCLOSURE,
    RESPONSE_SCHEMA,
    SCORE_MODEL_VERSION,
)
from .zip_screen.resolve import resolve_location
from .zip_screen.screen import (
    AnchorNotFoundError,
    MultiAnchorRequest,
    ScreenedZip,
    ScreenResult,
    annotate_family_distance,
    run_multi_anchor_screen,
)
from .zip_screen.table import load_table

OPTIMIZE_SCHEMA = 'housing_optimize_v2'


def validate_request(body: dict[str, Any]) -> str | None:
    """The design §8 rules, server-side, plus the three enum checks Task 9
    dropped (``objective``, ``search_mode``, ``move2_strategy`` -- see the
    inherited-obligation note above Task 10 Step 1 in the design doc). Rules
    are checked in a fixed order and the FIRST violation's message is
    returned, so the client's own copy and this one never disagree about
    which rule fired.

    Returns ``None`` when the request is valid.
    """
    if body.get('locations'):
        return ('Manual candidate locations are no longer supported. '
                'Provide 2-5 anchors per move instead.')

    objective = str(body.get('objective', 'net_worth') or 'net_worth')
    if objective not in OBJECTIVES:
        return f'Unknown objective: {objective!r}.'

    search_mode = str(body.get('search_mode', 'full') or 'full')
    if search_mode not in SEARCH_MODES:
        return f'Unknown search_mode: {search_mode!r}.'

    move2_strategy = str(body.get('move2_strategy', 'anchored') or 'anchored')
    if move2_strategy not in MOVE2_STRATEGIES:
        return f'Unknown move2_strategy: {move2_strategy!r}.'

    home = body.get('original_home') or {}
    disposition = str(home.get('disposition', 'auto') or 'auto').lower()
    if disposition not in DISPOSITIONS:
        return f'Unknown disposition: {disposition!r}.'

    sells = disposition in ('sell', 'auto')
    earliest_sale = int(home.get('earliest_sale_year') or 0)
    latest_sale = int(home.get('latest_sale_year') or 0)
    if sells and earliest_sale > latest_sale:
        return 'Earliest sale year must not be after the latest sale year.'

    move1 = body.get('move1') or {}
    e1 = int(move1.get('earliest_acquisition_year') or 0)
    l1 = int(move1.get('latest_acquisition_year') or 0)
    if e1 > l1:
        return 'Earliest move-1 year must not be after the latest.'

    move2 = body.get('move2')
    if move2:
        e2 = int(move2.get('earliest_acquisition_year') or 0)
        l2 = int(move2.get('latest_acquisition_year') or 0)
        if e2 > l2:
            return 'Earliest move-2 year must not be after the latest.'
        if not move2.get('concurrent') and l2 <= e1:
            return (f'Move 2 must be able to happen after move 1. '
                    f'Raise the move-2 latest year above {e1}.')
        if move2.get('concurrent') and str(body.get('search_mode')) != 'full':
            return 'Concurrent mode is only available with Full grid search mode.'

    no_dual = bool(body.get('no_dual_ownership', True))
    actions = [str((body.get(f'move{i}') or {}).get('action', 'auto'))
               for i in (1, 2) if body.get(f'move{i}')]
    if no_dual and disposition == 'keep' and actions and all(a == 'buy' for a in actions):
        return ('Keeping the current home and buying another means owning two '
                "homes. Choose Rent, sell the current home, or turn off "
                "'Never own two homes at once'.")
    if no_dual and disposition == 'sell' and move1.get('action') == 'buy' \
            and l1 < earliest_sale:
        return ('With no dual ownership, move 1 cannot be bought before the home '
                f'is sold. Raise the move-1 latest year to at least {earliest_sale}.')

    for key in ('move1', 'move2'):
        block = body.get(key)
        if not block:
            continue
        search = block.get('search') or {}
        anchors = search.get('anchors') or []
        if not (2 <= len(anchors) <= 5):
            return f'Choose between 2 and 5 anchors for {key.replace("move", "move ")}.'
        if any(not str(a.get('anchor_zip', '')).strip() for a in anchors):
            return f'Every anchor for {key.replace("move", "move ")} needs a ZIP.'
        if int(search.get('radius_miles') or 0) not in ALLOWED_RADII_MILES:
            return f'Radius must be one of {", ".join(map(str, ALLOWED_RADII_MILES))} miles.'
        if str(search.get('area_type', 'any')) not in AREA_TYPES:
            return f"Unknown area type {search.get('area_type')!r}."
        rng = (search.get('dwelling') or {}).get('target_purchase_price_range')
        if rng and float(rng[0]) > float(rng[1]):
            return 'Minimum target price must not exceed the maximum.'

    fp = body.get('family_presence')
    if fp:
        zip_code = str(fp.get('zip', '') or '').strip()
        if len(zip_code) != 5 or not zip_code.isdigit():
            return ('Family presence needs a 5-digit ZIP and a from-year no later '
                    'than the through-year.')
        if int(fp.get('from_year') or 0) > int(fp.get('through_year') or 0):
            return ('Family presence needs a 5-digit ZIP and a from-year no later '
                    'than the through-year.')
        if int(fp.get('radius_miles') or 0) not in FAMILY_RADII_MILES:
            return f'Family radius must be one of {", ".join(map(str, FAMILY_RADII_MILES))} miles.'
    return None


def parse_move_search(raw: dict[str, Any]) -> MultiAnchorRequest:
    """Parse one move's ``search`` block into a ``MultiAnchorRequest``.
    Raises ``ValueError`` with a wire-ready message."""
    anchors = raw.get('anchors') or []
    anchor_zips = [str(a.get('anchor_zip', '') or '').strip() for a in anchors]
    anchor_zips = [z for z in anchor_zips if z]
    if not (2 <= len(anchor_zips) <= 5):
        raise ValueError('Choose between 2 and 5 anchors.')

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

    area_type = str(raw.get('area_type', 'any') or 'any').strip().lower()
    if area_type not in AREA_TYPES:
        raise ValueError(f'Unknown area_type: {area_type!r}.')

    max_population_raw = raw.get('max_population')
    try:
        max_population = (int(max_population_raw)
                          if max_population_raw not in (None, '') else None)
    except (TypeError, ValueError):
        max_population = None

    size = int(raw.get('shortlist_size', 4) or 4)

    return MultiAnchorRequest(
        anchor_zips=anchor_zips,
        radius_miles=radius,
        min_quality_score=min_score,
        shortlist_size=max(2, min(5, size)),
        property_spec=dict(raw.get('dwelling') or {}),
        area_type=area_type,
        max_population=max_population,
    )


def _splice_screen_detail(location, screened: ScreenedZip):
    """Attach screening-derived display fields to a resolved ``Location``.

    ``Location`` is frozen and these six fields (``city``, ``nss``, ``band``,
    ``distance_miles``, ``family_distance_miles``, ``est_price``) are real
    optional fields on it (Task 8), so this is ``dataclasses.replace`` rather
    than the untyped ``copy.copy`` + ``object.__setattr__`` the original plan
    sketched -- that approach is explicitly rejected in the Task 8 amendment,
    because ``dataclasses.replace`` on a Location with unknown extra
    attributes would silently drop them.
    """
    return replace(
        location,
        city=screened.city,
        nss=screened.nss,
        band=screened.band,
        distance_miles=screened.distance_miles,
        family_distance_miles=screened.family_distance_miles,
        est_price=screened.est_price,
    )


def _resolve_screened_locations(
    shortlist: list[ScreenedZip], property_spec: dict[str, Any],
    table: dict[str, Any], family_zip: str | None,
    family_coords: dict[str, tuple[float, float]],
):
    annotated = annotate_family_distance(shortlist, family_zip, family_coords)
    return [
        _splice_screen_detail(resolve_location(table[z.zcta], property_spec), z)
        for z in annotated
    ]


def _family_coords_from_table(table: dict[str, Any]) -> dict[str, tuple[float, float]]:
    """Every ZCTA's coordinates, keyed by ZCTA.

    Both the family ZIP and every candidate ZIP must be present here or
    ``family_presence_ok`` fails closed and drops the candidate -- using the
    whole loaded table (rather than assembling a narrower subset) guarantees
    that trivially.
    """
    return {zcta: (rec.lat, rec.lon) for zcta, rec in table.items()}


def optimize_housing_from_request(
    c0: dict[str, Any], body: dict[str, Any], table_path: str | None = None
) -> tuple[dict[str, Any], int]:
    """Parse an ``/api/housing/optimize`` v2 request body, run the optimizer
    against the current plan config ``c0``, and return a ``(payload, status)``
    pair ready for ``jsonify``. Never mutates ``c0``.

    Every candidate location comes from a ZIP-radius screen -- one per
    searched move -- run via ``run_multi_anchor_screen``. There is no more
    hand-picked-location path.
    """
    try:
        err = validate_request(body)
        if err:
            return {'success': False, 'error': err}, 400

        home = body.get('original_home') or {}
        disposition = str(home.get('disposition', 'auto') or 'auto').lower()
        sale_window = SaleWindow(
            earliest_sale_year=int(home.get('earliest_sale_year') or 0),
            latest_sale_year=int(home.get('latest_sale_year') or 0),
        )

        move1 = body.get('move1') or {}
        move1_window = MoveWindow(
            earliest_acquisition_year=int(move1.get('earliest_acquisition_year') or 0),
            latest_acquisition_year=int(move1.get('latest_acquisition_year') or 0),
        )
        move1_action = str(move1.get('action', 'auto') or 'auto')

        table = load_table(table_path) if table_path else load_table()
        family_coords = _family_coords_from_table(table)
        current_state = str(c0.get('state', '') or '')

        fp_raw = body.get('family_presence')
        family_presence = None
        family_zip: str | None = None
        if fp_raw:
            family_zip = str(fp_raw.get('zip', '') or '').strip()
            family_presence = FamilyPresence(
                zip_code=family_zip,
                radius_miles=int(fp_raw.get('radius_miles') or 0),
                from_year=int(fp_raw.get('from_year') or 0),
                through_year=int(fp_raw.get('through_year') or 0),
            )

        move1_req = parse_move_search(move1.get('search') or {})
        move1_screen = run_multi_anchor_screen(
            move1_req, table=table, current_state=current_state)
        locations1 = _resolve_screened_locations(
            move1_screen.shortlist, move1_req.property_spec, table,
            family_zip, family_coords)

        objective = str(body.get('objective', 'net_worth') or 'net_worth')
        search_mode = str(body.get('search_mode', 'full') or 'full')
        move2_strategy = str(body.get('move2_strategy', 'anchored') or 'anchored')

        zip_screens: dict[str, Any] = {'move1': screen_payload(move1_screen)}

        move2_window = None
        move2_action = 'auto'
        move2_concurrent = False
        anchor_count = 5
        locations2: list | None = None
        move2 = body.get('move2')
        if move2:
            move2_window = MoveWindow(
                earliest_acquisition_year=int(move2.get('earliest_acquisition_year') or 0),
                latest_acquisition_year=int(move2.get('latest_acquisition_year') or 0),
            )
            move2_action = str(move2.get('action', 'auto') or 'auto')
            move2_concurrent = bool(move2.get('concurrent', False))
            anchor_count = int(move2.get('anchor_count', 5) or 5)

            move2_req = parse_move_search(move2.get('search') or {})
            move2_screen = run_multi_anchor_screen(
                move2_req, table=table, current_state=current_state)
            locations2 = _resolve_screened_locations(
                move2_screen.shortlist, move2_req.property_spec, table,
                family_zip, family_coords)
            zip_screens['move2'] = screen_payload(move2_screen)

        if not locations1:
            return {
                'success': True, 'schema': OPTIMIZE_SCHEMA,
                'objective': objective, 'search_mode': search_mode,
                'move2_strategy': move2_strategy, 'zip_screens': zip_screens,
                'recommendation': None, 'candidates': [], 'candidates_evaluated': 0,
                'rejections': {},
                'message': (
                    'The move-1 screen returned no candidate ZIPs. Widen the '
                    'radius, lower the minimum quality score, or add anchors.'
                ),
            }, 200

        down_payment_pct = float(body.get('down_payment_pct', 0.20) or 0.20)
        mortgage_rate_raw = body.get('mortgage_rate_pct')
        mortgage_rate_pct = (
            float(mortgage_rate_raw) if mortgage_rate_raw not in (None, '') else None
        )
        shortlist_size = int(body.get('shortlist_size', 5) or 5)

        result = optimize_housing(
            c0,
            locations1=locations1,
            locations2=locations2,
            sale_window=sale_window,
            move1_window=move1_window,
            move2_window=move2_window,
            dispositions=(disposition,),
            move1_action=move1_action,
            move2_action=move2_action,
            move2_concurrent=move2_concurrent,
            no_dual_ownership=bool(body.get('no_dual_ownership', True)),
            family_presence=family_presence,
            family_coords=family_coords,
            anchor_count=anchor_count,
            objective=objective,
            search_mode=search_mode,
            move2_strategy=move2_strategy,
            zip_screens=zip_screens,
            down_payment_pct=down_payment_pct,
            mortgage_rate_pct=mortgage_rate_pct,
            shortlist_size=shortlist_size,
        )
        return result, 200
    except AnchorNotFoundError as exc:
        return {'success': False, 'error': str(exc)}, 400
    except ValueError as exc:
        return {'success': False, 'error': str(exc)}, 400
    except Exception as exc:  # pragma: no cover - defensive
        return {'success': False, 'error': str(exc)}, 500


def _screened_zip_payload(z: ScreenedZip) -> dict[str, Any]:
    return {
        'zip': z.zcta, 'city': z.city, 'state': z.state,
        'distance_miles': z.distance_miles, 'nss': z.nss, 'band': z.band,
        'components': z.components, 'coverage_pct': z.coverage_pct,
        'est_price': z.est_price, 'upi_adjusted': z.upi_adjusted,
        'cross_state': z.cross_state, 'promoted': z.promoted,
        'collapsed': z.collapsed, 'area_type': z.area_type,
        'population': z.population, 'nearest_anchor_zip': z.nearest_anchor_zip,
        'family_distance_miles': z.family_distance_miles,
    }


def screen_payload(result: ScreenResult) -> dict[str, Any]:
    """The ``zip_screen`` block shared by both endpoints."""
    return {
        'schema': RESPONSE_SCHEMA,
        'score_model': SCORE_MODEL_VERSION,
        'disclosure': NSS_DISCLOSURE,
        'anchor': result.anchor,
        'anchors': result.anchors,
        'radius_miles': result.radius_miles,
        'funnel': result.funnel,
        'relaxation': result.relaxation,
        'shortlist': [_screened_zip_payload(z) for z in result.shortlist],
    }


def zip_screen_from_request(
    c0: dict[str, Any], body: dict[str, Any], table_path: str | None = None
) -> tuple[dict[str, Any], int]:
    """Run Stage 1 alone -- the "Preview shortlist" endpoint. No engine runs.

    Accepts ``{'search': {...}}``, the same shape as ``move1.search`` /
    ``move2.search``, so this one endpoint serves either move without
    knowing which.
    """
    raw = body.get('search')
    if not isinstance(raw, dict):
        return {'success': False, 'error': 'search block is required.'}, 400
    try:
        req = parse_move_search(raw)
        result = run_multi_anchor_screen(
            req,
            table=load_table(table_path) if table_path else load_table(),
            current_state=str(c0.get('state', '') or ''),
        )
    except AnchorNotFoundError as exc:
        return {'success': False, 'error': str(exc)}, 400
    except ValueError as exc:
        return {'success': False, 'error': str(exc)}, 400
    return {'success': True, 'zip_screen': screen_payload(result)}, 200


import csv as _csv
import os as _os


def _top_cities_path() -> str:
    return _os.path.join(
        _os.path.dirname(_os.path.abspath(__file__)),
        'zip_screen', 'data', 'top_cities.csv',
    )


def top_cities_payload() -> tuple[dict[str, Any], int]:
    """The bundled top-cities list, for the ZIP-radius panel's anchor dropdown.

    Static, bundled data (built by scripts/build_zip_metrics.py) -- this is
    a read of a committed file, not a live query, matching the rest of the
    zip_screen package's offline-first design.
    """
    path = _top_cities_path()
    if not _os.path.exists(path):
        return {'success': False, 'error': 'top_cities.csv not found; run scripts/build_zip_metrics.py'}, 500
    with open(path, newline='', encoding='utf-8') as fh:
        rows = list(_csv.DictReader(fh))
    cities = [
        {
            'city_id': r['city_id'], 'city': r['city'], 'state': r['state'],
            'state_abbrev': r['state_abbrev'], 'population': int(r['population']),
            'anchor_zip': r['anchor_zip'],
        }
        for r in rows
    ]
    cities.sort(key=lambda c: -c['population'])
    return {'success': True, 'cities': cities}, 200
