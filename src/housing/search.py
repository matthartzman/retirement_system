"""Narrowed search: bounded integer coordinate descent (§8.2 P2, §7).

Two layers, deliberately separate: ``_descend`` is a pure integer hill-climb
over a caller-supplied ``score_fn`` (so a search change can be exercised
against a synthetic surface with no engine at all), and the
``generate_*_narrowed`` wrappers below bind that ``score_fn`` to a real
engine run. Scoring, filtering and ranking are shared unmodified with the
full-grid path in ``candidates.py``.

The axes are the year variables of the decoupled model: the original home's
sale year (collapsed away entirely when it is kept) and each move's
acquisition year. Rent is an ``action`` now rather than a missing purchase
year, so the pre-2026-09-16 version's separate 1D "rent indefinitely" branch
is gone -- a rental is just another point on the same acquisition axis, and
the action is an outer loop instead of a search dimension.
"""
from __future__ import annotations

from itertools import product
from typing import Callable

from .candidates import actions_for_location, dual_ownership_ok
from .models import (
    HousingCandidate,
    Location,
    Move,
    MoveWindow,
    NARROWED_MAX_EVALS_PER_AXIS,
    NARROWED_MOVE1_AXES,
    NARROWED_MOVE2_AXES,
    OriginalHome,
    SaleWindow,
    ScoredCandidate,
)
from .scoring import _pass1_objective, _pass1_value

ScoreFn = Callable[[HousingCandidate], "ScoredCandidate | None"]


def _descend(axes, build, score_fn, max_evals, objective: str = 'net_worth'):
    """Seed at each axis corner plus the centre, then hill-climb one axis at a
    time until no single-step neighbour improves.

    ``axes`` is a list of ``range`` objects; ``build(point)`` turns a tuple of
    axis values into a candidate. A point whose ``score_fn`` returns ``None``
    is infeasible: it is recorded as visited so it is never re-scored, but it
    never becomes the incumbent. Treating it as a very low score instead would
    push the climb away from a feasible region it has not reached yet.

    The incumbent is chosen with ``_pass1_value``, which orients the score so
    higher is always better. Comparing raw ``net_worth`` would be wrong for
    ``objective='lifetime_cost'``: that objective is MINIMISED, so a raw
    comparison would climb towards the worst candidate on the surface while
    still returning a plausible-looking list of scored points.
    """
    pass1_objective = _pass1_objective(objective)
    seen: dict[tuple[int, ...], ScoredCandidate | None] = {}
    results: list[ScoredCandidate] = []

    def evaluate(point):
        if point in seen:
            return seen[point]
        if len(seen) >= max_evals:
            return None
        scored = score_fn(build(point))
        seen[point] = scored
        if scored is not None:
            results.append(scored)
        return scored

    corners = [tuple(v) for v in product(*[(a[0], a[-1]) for a in axes])]
    centre = tuple(a[len(a) // 2] for a in axes)
    incumbent, incumbent_score = None, None
    for seed in list(dict.fromkeys(corners + [centre])):
        scored = evaluate(seed)
        if scored is None:
            continue
        value = _pass1_value(scored, pass1_objective)
        if incumbent_score is None or value > incumbent_score:
            incumbent, incumbent_score = seed, value

    while incumbent is not None and len(seen) < max_evals:
        improved = False
        for i, axis in enumerate(axes):
            for delta in (-1, 1):
                nxt = list(incumbent)
                nxt[i] += delta
                if nxt[i] < axis[0] or nxt[i] > axis[-1]:
                    continue
                scored = evaluate(tuple(nxt))
                if scored is None:
                    continue
                value = _pass1_value(scored, pass1_objective)
                if value > incumbent_score:
                    incumbent, incumbent_score, improved = tuple(nxt), value, True
        if not improved:
            break
    return results


def _axes_for_move1(sale_window, move1_window, disposition):
    """One axis when the original home is kept (there is no sale year to
    search), otherwise (sale year, acquisition year). ``build`` below indexes
    ``point`` accordingly."""
    axes = [range(move1_window.earliest_acquisition_year,
                  move1_window.latest_acquisition_year + 1)]
    if disposition != 'keep':
        axes.insert(0, range(sale_window.earliest_sale_year,
                             sale_window.latest_sale_year + 1))
    return axes


def generate_move1_candidates_narrowed(
    *, locations1: list[Location], move1_window: MoveWindow, sale_window: SaleWindow,
    dispositions: tuple[str, ...], move1_action: str, no_dual_ownership: bool,
    score_fn: ScoreFn, max_evals: int = NARROWED_MAX_EVALS_PER_AXIS * NARROWED_MOVE1_AXES,
    objective: str = 'net_worth',
) -> list[ScoredCandidate]:
    """Bounded descent per (disposition, location, action) over the year axes.

    ``objective`` is the caller's Pass-1 objective; it only decides which
    direction is "better" for the incumbent, and defaults to ``'net_worth'``
    so existing call sites keep their behaviour.
    """
    out: list[ScoredCandidate] = []
    for disposition in dispositions:
        axes = _axes_for_move1(sale_window, move1_window, disposition)
        keep = disposition == 'keep'
        for loc in locations1:
            for action in actions_for_location(move1_action, loc):
                def build(point, _loc=loc, _action=action, _keep=keep, _d=disposition):
                    sale_year = None if _keep else point[0]
                    year = point[0] if _keep else point[1]
                    return HousingCandidate(
                        original_home=OriginalHome(disposition=_d, sale_year=sale_year),
                        moves=(Move(index=1, acquisition_year=year,
                                    action=_action, location=_loc),),
                    )

                def guarded(cand, _fn=score_fn):
                    if no_dual_ownership and not dual_ownership_ok(cand):
                        return None
                    return _fn(cand)

                out.extend(_descend(axes, build, guarded, max_evals, objective))
    return out


def generate_move2_candidates_narrowed(
    anchors: list[HousingCandidate], *, locations2: list[Location],
    move2_window: MoveWindow, move2_action: str, concurrent: bool,
    no_dual_ownership: bool, score_fn: ScoreFn,
    max_evals: int = NARROWED_MAX_EVALS_PER_AXIS * NARROWED_MOVE2_AXES,
    objective: str = 'net_worth',
) -> list[ScoredCandidate]:
    """Bounded descent over move 2's OWN declared acquisition window.

    The window is authoritative -- the ordering rule (a sequential move 2 must
    come strictly after move 1) is a guard on the point, not a clamp on the
    axis, matching ``candidates.extend_with_move2``.
    """
    mode = 'concurrent' if concurrent else 'sequential'
    out: list[ScoredCandidate] = []
    axis = range(move2_window.earliest_acquisition_year,
                 move2_window.latest_acquisition_year + 1)
    for anchor in anchors:
        for loc in locations2:
            for action in actions_for_location(move2_action, loc):
                def build(point, _a=anchor, _loc=loc, _action=action, _mode=mode):
                    return HousingCandidate(
                        original_home=_a.original_home,
                        moves=_a.moves + (Move(index=2, acquisition_year=point[0],
                                               action=_action, location=_loc, mode=_mode),),
                        anchor_of=_a,
                    )

                def guarded(cand, _fn=score_fn, _a=anchor):
                    if not concurrent and cand.move2.acquisition_year <= _a.move1.acquisition_year:
                        return None
                    if no_dual_ownership and not concurrent and not dual_ownership_ok(cand):
                        return None
                    return _fn(cand)

                out.extend(_descend([axis], build, guarded, max_evals, objective))
    return out
