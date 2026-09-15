"""Shaping ranked ``ScoredCandidate``s into the ``housing_optimize_v1``
response body. Presentation only -- kept apart from ``optimizer.py`` so the
payload can be reshaped without touching the search, and from ``api.py`` so
the optimizer never imports the HTTP layer.
"""
from __future__ import annotations

from typing import Any

from .models import Location, ScoredCandidate

def _format_move(location: Location | None, sale_year: int | None, purchase_year: int | None,
                  sec121_lost: bool, mode: str = 'sequential', start_year: int | None = None) -> dict[str, Any] | None:
    if location is None:
        return None
    return {
        'sale_year': sale_year,
        'purchase_year': purchase_year,
        'start_year': start_year,
        'mode': mode,
        'rent_indefinitely': purchase_year is None,
        'location': {
            'state': location.state,
            'city_type': location.city_type,
            'population_size': location.population_size,
            'zip_code': location.zip_code,
        },
        'sec121_exclusion_lost': sec121_lost,
    }


def _format_candidate(sc: ScoredCandidate, objective: str) -> dict[str, Any]:
    cand = sc.candidate
    moves = [_format_move(cand.location_1, cand.sale_year, cand.purchase_year,
                           sc.sec121_exclusion_lost[0] if sc.sec121_exclusion_lost else False)]
    if cand.is_two_move:
        sec121_2 = sc.sec121_exclusion_lost[1] if len(sc.sec121_exclusion_lost) > 1 else False
        if cand.move2_mode == 'concurrent':
            moves.append(_format_move(cand.location_2, None, cand.purchase_year_2, sec121_2,
                                       mode='concurrent', start_year=cand.concurrent_start_year_2))
        else:
            moves.append(_format_move(cand.location_2, cand.sale_year_2, cand.purchase_year_2, sec121_2))
    return {
        'moves': moves,
        'net_worth': sc.net_worth,
        'lifetime_cost': sc.lifetime_cost,
        'mc_success_rate': sc.mc_success_rate,
        'objective_value': {
            'net_worth': sc.net_worth,
            'lifetime_cost': sc.lifetime_cost,
            'mc_success_rate': sc.mc_success_rate,
        }[objective],
        'family_presence_via_rental': sc.family_presence_via_rental,
    }


def _format_output(
    ranked: list[ScoredCandidate], objective: str, search_mode: str = 'full',
    move2_strategy: str = 'anchored',
) -> dict[str, Any]:
    formatted = [_format_candidate(sc, objective) for sc in ranked]
    return {
        'objective': objective,
        'search_mode': search_mode,
        'move2_strategy': move2_strategy,
        'recommendation': formatted[0] if formatted else None,
        'alternatives': formatted[1:11],
        'candidates_evaluated': len(ranked),
    }
