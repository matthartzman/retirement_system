"""Scoring one engine run and ranking the results (§4).

``score_candidate`` reads only the engine's own cashflow rows, so adding an
objective means adding a row-reader here and an entry in ``OBJECTIVES`` --
nothing in search or candidate generation changes.
"""
from __future__ import annotations

from typing import Any

from .models import HousingCandidate, ScoredCandidate
from .constraints import sec121_exclusion_flag
from .rent_out import ESTIMATED_TAX_NOTE, converted_after_tax_net_cash, rent_out_notes

def _lifetime_cost(rows: list[dict[str, Any]], rent_tax: float | None = None) -> float:
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
    # WP12.8: a home converted to a rental moved its carrying costs out of
    # housing_total_yr; its after-tax rental net cash (rent less those costs
    # and the estimated tax) counts here instead. 0 with no converted home,
    # so nothing changes off. ``rent_tax`` (M7): the engine's exact tax delta
    # for the rental in place of the estimate.
    return total - converted_after_tax_net_cash(rows, rent_tax)


def score_candidate(c: dict[str, Any], cand: HousingCandidate, rows: list[dict[str, Any]],
                    *, via_rental: bool = False) -> ScoredCandidate:
    """Score one engine run. ``c`` is the config the run actually used (the
    mutated copy ``_run_engine`` returns), not the caller's base config.

    Both moves' sale proceeds are already real deposits the engine's own run
    reflects in ``rows[-1]['total_nw']`` (see home_sale.py's
    ``apply_next_housing_sale`` and ``src.housing``'s package docstring), so
    -- unlike the out-of-loop estimate this replaced -- no post-hoc net
    worth/lifetime cost adjustment is needed for move 2.

    The old ``family_presence_via_rental`` boolean is now one entry in a free
    ``notes`` list (§7.2): a result row needs to carry several unrelated
    caveats, and a new boolean field per caveat forced every consumer to grow
    a branch for each one.
    """
    net_worth = float(rows[-1].get('total_nw', 0.0) or 0.0) if rows else 0.0
    lifetime_cost = _lifetime_cost(rows)
    notes: list[str] = []
    if via_rental:
        notes.append('family presence via rental')

    sale_year = cand.original_home.sale_year
    # The original home's own sale is never flagged: ownership start is not
    # tracked for a home the household already lives in, so the two-of-five
    # test is assumed met. Each MOVE's home is flagged on its own span.
    sec121_flags = [False]
    m2 = cand.move2
    if m2 is not None:
        if m2.mode == 'concurrent':
            # Concurrent mode never sells the move-1 home -- nothing to flag.
            sec121_flags.append(False)
        else:
            # A sequential move 2 sells the move-1 home in its acquisition
            # year -- but only if move 1 actually bought one.
            bought1 = cand.move1.acquisition_year if cand.move1.action == 'buy' else None
            sec121_flags.append(sec121_exclusion_flag(bought1, m2.acquisition_year))
    # WP12.8 keep-and-rent-out: the section 121 window, recapture and
    # passive-loss notes (the plan never sells a rented-out home).
    rent_notes = rent_out_notes(c, cand, rows)
    if any(sec121_flags):
        notes.append('likely loses §121 exclusion')
    notes.extend(rent_notes)
    if rent_notes:
        # M7: Pass 1 scores rent-out with an estimated tax on the rent; the
        # optimizer swaps in the exact delta (and this label) for the shortlist.
        notes.append(ESTIMATED_TAX_NOTE)

    buys = [m for m in cand.moves if m.action == 'buy' and m.mode != 'concurrent']
    overlapping = [m.acquisition_year for m in buys
                   if sale_year is not None and m.acquisition_year < sale_year]
    if overlapping:
        notes.append(f'dual_ownership_years {min(overlapping)}-{sale_year}')
    if rent_notes and buys:
        notes.append(f'owns two homes from {min(m.acquisition_year for m in buys)} (current home rented out)')

    return ScoredCandidate(
        candidate=cand, net_worth=net_worth, lifetime_cost=lifetime_cost,
        mc_success_rate=None, sec121_exclusion_lost=sec121_flags, notes=notes,
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
