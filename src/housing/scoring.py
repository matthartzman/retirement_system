"""Scoring one engine run and ranking the results (§4).

``score_candidate`` reads only the engine's own cashflow rows, so adding an
objective means adding a row-reader here and an entry in ``OBJECTIVES`` --
nothing in search or candidate generation changes.
"""
from __future__ import annotations

from typing import Any

from .models import HousingCandidate, ScoredCandidate
from .constraints import sec121_exclusion_flag

def _lifetime_cost(rows: list[dict[str, Any]]) -> float:
    """Total after-tax housing-attributable cost (§4): ongoing housing cash
    flow (mortgage P&I, RE tax, insurance/HOA/utilities/maintenance, rent --
    already summed by the engine into ``housing_total_yr``) plus each sale's
    gain tax, minus its pretax capital gain (selling costs already netted
    out of ``home_sale_gain``/``next_housing_sale_gain``) -- i.e. cost net of
    equity growth realized at sale, computed entirely from this run's
    existing cashflow breakdown, per §4. Covers both the original home's
    sale (``home_sale_*``) and, for a two-move candidate, move 2's sale of
    the ``next_housing_steps`` home (``next_housing_sale_*`` -- see
    home_sale.py's ``apply_next_housing_sale``); both are 0 in every year
    without that sale, so this needs no candidate-specific branching.
    """
    total = 0.0
    for r in rows:
        total += float(r.get('housing_total_yr', 0.0) or 0.0)
        total += float(r.get('home_sale_tax', 0.0) or 0.0)
        total -= float(r.get('home_sale_gain', 0.0) or 0.0)
        total += float(r.get('next_housing_sale_tax', 0.0) or 0.0)
        total -= float(r.get('next_housing_sale_gain', 0.0) or 0.0)
    return total


def score_candidate(c: dict[str, Any], cand: HousingCandidate, rows: list[dict[str, Any]]) -> ScoredCandidate:
    """Score one engine run. Both moves' sale proceeds are already real
    deposits the engine's own run reflects in ``rows[-1]['total_nw']`` (see
    home_sale.py's ``apply_next_housing_sale`` and ``src.housing``'s package
    docstring),
    so -- unlike the out-of-loop estimate this replaced -- no post-hoc net
    worth/lifetime cost adjustment is needed for move 2.
    """
    net_worth = float(rows[-1].get('total_nw', 0.0) or 0.0) if rows else 0.0
    lifetime_cost = _lifetime_cost(rows)
    sec121_flags = [False]  # move 1 sells the current/original home -- ownership start isn't tracked, assume met
    if cand.is_two_move:
        if cand.move2_mode == 'concurrent':
            sec121_flags.append(False)  # concurrent mode never sells anything -- nothing to flag
        else:
            sec121_flags.append(sec121_exclusion_flag(cand.purchase_year, cand.sale_year_2))
    return ScoredCandidate(
        candidate=cand, net_worth=net_worth, lifetime_cost=lifetime_cost,
        mc_success_rate=None, sec121_exclusion_lost=sec121_flags,
    )


def _pass1_objective(objective: str) -> str:
    """§4 Pass 1a: mc_success_rate is not computed until Pass 2 -- falls
    back to net_worth for the provisional deterministic ranking."""
    return 'net_worth' if objective == 'mc_success_rate' else objective


def rank_candidates(scored: list[ScoredCandidate], objective: str) -> list[ScoredCandidate]:
    reverse = objective != 'lifetime_cost'

    def key_fn(s: ScoredCandidate) -> float:
        if objective == 'lifetime_cost':
            return s.lifetime_cost
        if objective == 'mc_success_rate':
            return s.mc_success_rate if s.mc_success_rate is not None else s.net_worth
        return s.net_worth

    return sorted(scored, key=key_fn, reverse=reverse)

def _pass1_value(sc: ScoredCandidate, pass1_objective: str) -> float:
    """Orient a ScoredCandidate's Pass-1 score so higher is always better,
    matching what ``_coordinate_search_2d``/``_coordinate_search_1d`` expect
    (``rank_candidates`` sorts lifetime_cost ascending instead)."""
    return -sc.lifetime_cost if pass1_objective == 'lifetime_cost' else sc.net_worth
