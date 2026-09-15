"""Narrowed search: bounded integer coordinate/pattern search (§8.2 P2, §7).

Two layers, deliberately separate: ``_coordinate_search_2d``/``_1d`` are
pure integer hill-climbs over a caller-supplied ``score_fn`` (so a search
change can be exercised against a synthetic surface with no engine at all),
and the ``generate_*_narrowed`` wrappers below bind that ``score_fn`` to a
real engine run. Scoring, filtering, and ranking are shared unmodified with
the full-grid path in ``candidates.py``.
"""
from __future__ import annotations

from typing import Any

from .models import (
    FamilyPresence,
    HousingCandidate,
    Location,
    Move2Window,
    NARROWED_1D_MAX_EVALS,
    NARROWED_2D_MAX_EVALS,
    ScoredCandidate,
    SearchWindow,
)
from .constraints import family_presence_ok
from .plan_variant import _run_engine
from .scoring import _pass1_value, score_candidate


# ---------------------------------------------------------------------------
# Search primitives -- decoupled from the engine so they are testable
# against a synthetic score surface: callers supply a ``score_fn`` where
# higher is always better (the engine-scoring wrappers below flip the sign
# for the lifetime_cost objective) and that returns ``None`` for a point
# that must be skipped (e.g. filtered out by no_dual_ownership or
# family_presence) without spending eval budget on it.
# ---------------------------------------------------------------------------

def _coordinate_search_2d(
    x_bounds: tuple[int, int],
    y_bounds: tuple[int, int],
    score_fn: "Any",
    max_evals: int = NARROWED_2D_MAX_EVALS,
) -> dict[tuple[int, int], float]:
    """Bounded hill-climb over the integer grid ``x_bounds x y_bounds``.
    Seeds with the four corners and the center, then repeatedly moves to
    the best-improving 4-neighbor of the current best point until none
    improves or ``max_evals`` is reached. Returns every point actually
    scored (``score_fn`` returned non-``None``), keyed by score -- callers
    that also need the ScoredCandidate objects build them alongside calling
    this. This is a local search: on a non-unimodal surface it can settle
    on a local rather than the global optimum (see ``src.housing``'s
    package docstring).
    """
    x_lo, x_hi = x_bounds
    y_lo, y_hi = y_bounds
    evaluated: dict[tuple[int, int], float] = {}

    def ev(x: int, y: int) -> float | None:
        if (x, y) in evaluated:
            return evaluated[(x, y)]
        if len(evaluated) >= max_evals:
            return None
        v = score_fn(x, y)
        if v is not None:
            evaluated[(x, y)] = v
        return v

    seeds = {
        (x_lo, y_lo), (x_lo, y_hi), (x_hi, y_lo), (x_hi, y_hi),
        ((x_lo + x_hi) // 2, (y_lo + y_hi) // 2),
    }
    best_pt: tuple[int, int] | None = None
    best_val: float | None = None
    for x, y in seeds:
        v = ev(x, y)
        if v is not None and (best_val is None or v > best_val):
            best_pt, best_val = (x, y), v

    if best_pt is None:
        return evaluated

    improved = True
    while improved and len(evaluated) < max_evals:
        improved = False
        x, y = best_pt
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if not (x_lo <= nx <= x_hi and y_lo <= ny <= y_hi):
                continue
            v = ev(nx, ny)
            if v is not None and v > best_val:
                best_pt, best_val = (nx, ny), v
                improved = True
    return evaluated


def _coordinate_search_1d(
    bounds: tuple[int, int],
    score_fn: "Any",
    max_evals: int = NARROWED_1D_MAX_EVALS,
) -> dict[int, float]:
    """1D analogue of ``_coordinate_search_2d`` (endpoints + midpoint seeds,
    then hill-climb to the better neighbor) for a single-dimension window,
    e.g. the rent-indefinitely branch's ``sale_year`` only."""
    lo, hi = bounds
    evaluated: dict[int, float] = {}

    def ev(x: int) -> float | None:
        if x in evaluated:
            return evaluated[x]
        if len(evaluated) >= max_evals:
            return None
        v = score_fn(x)
        if v is not None:
            evaluated[x] = v
        return v

    best_x: int | None = None
    best_val: float | None = None
    for x in {lo, hi, (lo + hi) // 2}:
        v = ev(x)
        if v is not None and (best_val is None or v > best_val):
            best_x, best_val = x, v

    if best_x is None:
        return evaluated

    improved = True
    while improved and len(evaluated) < max_evals:
        improved = False
        for nx in (best_x + 1, best_x - 1):
            if not (lo <= nx <= hi):
                continue
            v = ev(nx)
            if v is not None and v > best_val:
                best_x, best_val = nx, v
                improved = True
    return evaluated


# ---------------------------------------------------------------------------
# Engine-scoring wrappers (§8.2 P2)
# ---------------------------------------------------------------------------

def _score_move1_point(
    c0: dict[str, Any], base_state: str, loc: Location, family_presence: FamilyPresence | None,
    no_dual_ownership: bool, pass1_objective: str, sink: list[ScoredCandidate],
    sale_year: int, purchase_year: int | None,
) -> float | None:
    if no_dual_ownership and purchase_year is not None and purchase_year < sale_year:
        return None
    cand = HousingCandidate(location_1=loc, sale_year=sale_year, purchase_year=purchase_year)
    ok, via_rental = family_presence_ok(base_state, cand, family_presence)
    if not ok:
        return None
    c2, rows = _run_engine(c0, cand)
    if not rows:
        return None
    sc = score_candidate(c2, cand, rows)
    sc.family_presence_via_rental = via_rental
    sink.append(sc)
    return _pass1_value(sc, pass1_objective)


def generate_move1_candidates_narrowed(
    c0: dict[str, Any], base_state: str, locations: list[Location], window: SearchWindow,
    no_dual_ownership: bool, family_presence: FamilyPresence | None, pass1_objective: str,
) -> list[ScoredCandidate]:
    """Narrowed-mode replacement for ``generate_move1_candidates`` that
    scores candidates as it searches (§8.2 P2 of ``src.housing``'s package
    docstring): per
    location, a bounded 2D coordinate search over ``(sale_year,
    purchase_year)`` plus a bounded 1D search over the rent-indefinitely
    branch's ``sale_year``. Rough upper bound on engine runs: per location,
    at most 25 (2D grid, ``_coordinate_search_2d``'s default ``max_evals``)
    + 8 (rent branch, ``_coordinate_search_1d``'s default) = 33 -- vs. a
    full grid's ``(sale_years * (purchase_years + 1))``, which exceeds that
    for any window bigger than a few years on a side.
    """
    scored: list[ScoredCandidate] = []
    for loc in locations:
        _coordinate_search_2d(
            (window.earliest_sale_year, window.latest_sale_year),
            (window.earliest_purchase_year, window.latest_purchase_year),
            lambda sy, py: _score_move1_point(
                c0, base_state, loc, family_presence, no_dual_ownership, pass1_objective, scored, sy, py,
            ),
        )
        _coordinate_search_1d(
            (window.earliest_sale_year, window.latest_sale_year),
            lambda sy: _score_move1_point(
                c0, base_state, loc, family_presence, no_dual_ownership, pass1_objective, scored, sy, None,
            ),
        )
    return scored


def _score_move2_point(
    c0: dict[str, Any], base_state: str, anchor: HousingCandidate, loc: Location,
    family_presence: FamilyPresence | None, no_dual_ownership: bool, pass1_objective: str,
    sink: list[ScoredCandidate], sale_year_2: int, purchase_year_2: int | None,
) -> float | None:
    if no_dual_ownership and purchase_year_2 is not None and purchase_year_2 < sale_year_2:
        return None
    cand = HousingCandidate(
        location_1=anchor.location_1, sale_year=anchor.sale_year, purchase_year=anchor.purchase_year,
        location_2=loc, sale_year_2=sale_year_2, purchase_year_2=purchase_year_2, anchor_of=anchor,
    )
    ok, via_rental = family_presence_ok(base_state, cand, family_presence)
    if not ok:
        return None
    c2, rows = _run_engine(c0, cand)
    if not rows:
        return None
    sc = score_candidate(c2, cand, rows)
    sc.family_presence_via_rental = via_rental
    sink.append(sc)
    return _pass1_value(sc, pass1_objective)


def generate_move2_candidates_narrowed(
    c0: dict[str, Any], base_state: str, anchors: list[HousingCandidate], locations: list[Location],
    move2_window: Move2Window, no_dual_ownership: bool, family_presence: FamilyPresence | None,
    pass1_objective: str,
) -> list[ScoredCandidate]:
    """Narrowed-mode replacement for ``generate_move2_candidates`` -- same
    per-(anchor, location) 2D-grid-plus-1D-rent-branch search as
    ``generate_move1_candidates_narrowed``, bounded the same way (§8.2 P2)."""
    scored: list[ScoredCandidate] = []
    for anchor in anchors:
        if anchor.purchase_year is None:
            continue
        earliest_sale_2 = anchor.purchase_year
        for loc in locations:
            _coordinate_search_2d(
                (earliest_sale_2, move2_window.latest_sale_year_2),
                (earliest_sale_2, move2_window.latest_purchase_year_2),
                lambda sy2, py2: _score_move2_point(
                    c0, base_state, anchor, loc, family_presence, no_dual_ownership, pass1_objective,
                    scored, sy2, py2,
                ),
            )
            _coordinate_search_1d(
                (earliest_sale_2, move2_window.latest_sale_year_2),
                lambda sy2: _score_move2_point(
                    c0, base_state, anchor, loc, family_presence, no_dual_ownership, pass1_objective,
                    scored, sy2, None,
                ),
            )
    return scored
