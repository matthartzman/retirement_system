"""Shaping ranked ``ScoredCandidate``s into the ``housing_optimize_v2``
response body. Presentation only -- kept apart from ``optimizer.py`` so the
payload can be reshaped without touching the search, and from ``api.py`` so
the optimizer never imports the HTTP layer.
"""
from __future__ import annotations

from typing import Any

from .models import Location, Move, ScoredCandidate

SCHEMA = 'housing_optimize_v2'
MAX_CANDIDATES = 10


def _format_location(loc: Location) -> dict[str, Any]:
    """Every field the results table needs, so a recommendation can be acted
    on without a second lookup. The screening-derived fields are real
    optional fields on ``Location`` (populated by the ZIP screen); they are
    ``None`` for a Location that never came from a screen."""
    return {
        'zip_code': loc.zip_code,
        'city': loc.city,
        'state': loc.state,
        'area_type': loc.city_type,
        'population': loc.population_size,
        'nss': loc.nss,
        'band': loc.band,
        'distance_miles': loc.distance_miles,
        'family_distance_miles': loc.family_distance_miles,
        'est_price': loc.est_price,
    }


def _format_move(move: Move, sec121_lost: bool) -> dict[str, Any]:
    return {
        'index': move.index,
        'acquisition_year': move.acquisition_year,
        'action': move.action,
        'mode': move.mode,
        'location': _format_location(move.location),
        'sec121_exclusion_lost': sec121_lost,
    }


def _format_candidate(sc: ScoredCandidate, objective: str, rank: int) -> dict[str, Any]:
    cand = sc.candidate
    lost = list(sc.sec121_exclusion_lost)
    return {
        'rank': rank,
        'original_home': {
            'disposition': cand.original_home.disposition,
            'sale_year': cand.original_home.sale_year,
        },
        'moves': [
            _format_move(m, lost[i] if i < len(lost) else False)
            for i, m in enumerate(cand.moves)
        ],
        'net_worth': sc.net_worth,
        'lifetime_cost': sc.lifetime_cost,
        'mc_success_rate': sc.mc_success_rate,
        'objective_value': {
            'net_worth': sc.net_worth,
            'lifetime_cost': sc.lifetime_cost,
            'mc_success_rate': sc.mc_success_rate,
        }[objective],
        'notes': list(sc.notes),
    }


def format_output(
    ranked: list[ScoredCandidate], *, objective: str, search_mode: str,
    move2_strategy: str, zip_screens: dict[str, Any],
    rejections: dict[str, int], message: str | None = None,
) -> dict[str, Any]:
    """One ranked ``candidates`` list, not a recommendation plus a disjoint
    alternatives list -- v1 duplicated the rank-1 candidate across both and
    forced the frontend to render it two different ways. ``recommendation``
    remains as an alias of ``candidates[0]``. ``candidates`` is capped at
    ``MAX_CANDIDATES``, but ``candidates_evaluated`` reports the full count.
    """
    formatted = [
        _format_candidate(sc, objective, i + 1)
        for i, sc in enumerate(ranked[:MAX_CANDIDATES])
    ]
    payload = {
        'success': True,
        'schema': SCHEMA,
        'objective': objective,
        'search_mode': search_mode,
        'move2_strategy': move2_strategy,
        'zip_screens': zip_screens,
        'recommendation': formatted[0] if formatted else None,
        'candidates': formatted,
        'candidates_evaluated': len(ranked),
        'rejections': dict(rejections),
    }
    if message:
        payload['message'] = message
    return payload
