"""Shared enumerate/evaluate/rank/gate primitive for exhaustive strategy
sweeps (system review 2026-08-31, finding A4 / item 2.3).

Both `planning_engines.optimize_roth_conversion_strategy` (~30 Roth policy
candidates) and `reporting.sheets_strategy`'s Social Security claim-age grid
(62-70 x 62-70, up to 81 pairs) independently re-implemented the identical
enumerate-candidates -> evaluate-each -> sort-by-score -> feasibility-gate-
with-fallback -> pick-best shape, each with its own domain-specific scoring
formula (the Roth sweep's multi-weight legacy/estate/survivor/ACA objective
is not the same computation as the SS sweep's simpler LCV-plus-survivor-
income score, and this module does not touch either). Only that shared
SHAPE is extracted here -- every scoring formula stays exactly where it was,
unchanged, in its own call site.

This is a pure extraction: run_sweep() below reproduces the two sweeps'
existing inline logic exactly (same iteration order, same sort semantics,
same fallback-to-full-set-when-everything-fails-the-gate behavior), so
adopting it should not change either sweep's numeric output at all -- see
each call site's own comment on how it was verified against the golden
master and the frozen candidate/pair tables before and after.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence


@dataclass(frozen=True)
class SweepResult:
    """Every candidate the sweep scored, plus the gated pick.

    `candidates` is in the ORIGINAL sort order (best-scoring first) and is
    what a disclosure table should iterate for "every candidate, ranked" --
    it is NOT filtered by feasibility, matching both sweeps' existing
    behavior of showing every candidate for comparison even when it could
    not have been selected.
    """

    candidates: list[dict]
    best: dict
    all_infeasible: bool


def run_sweep(
    specs: Sequence[Mapping[str, Any]],
    evaluate_fn: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    *,
    sort_key: Callable[[Mapping[str, Any]], Any],
    feasibility_key: str = "feasibility_gate_met",
    fallback_best: Mapping[str, Any] | None = None,
) -> SweepResult:
    """Enumerate `specs`, evaluate each, rank, and gate on feasibility.

    For every spec: calls `evaluate_fn(spec)` (which must return a metrics
    mapping -- the candidate's own scoring/feasibility computation lives
    entirely inside this callback, unchanged from before extraction) and
    merges it onto a copy of `spec` to form one candidate dict. Candidates
    are then sorted descending by `sort_key` (matching both sweeps'
    `list.sort(key=..., reverse=True)` convention exactly).

    Feasibility gating mirrors both sweeps' existing "Option C, full
    sign-off" behavior identically: a candidate is only eligible for
    selection when `candidate[feasibility_key]` is truthy. If at least one
    candidate clears the gate, `best` is chosen from that feasible subset
    only (still ranked by `sort_key`, since the feasible subset is a
    sort-stable filter of the already-sorted list). If NONE clear the gate,
    the gate is treated as uninformative and `best` falls back to the top of
    the FULL ranked set instead of failing to produce a recommendation --
    `all_infeasible` is True in that case so the caller can disclose it.

    `fallback_best` is returned as `best` only when `specs` is empty (no
    candidates were ever generated); both existing call sites use this for
    their own "no voluntary conversions" / "current configured ages"
    default rather than raising on an empty sweep.
    """
    candidates = [{**spec, **evaluate_fn(spec)} for spec in specs]
    candidates.sort(key=sort_key, reverse=True)

    feasible = [x for x in candidates if x.get(feasibility_key)]
    all_infeasible = bool(candidates) and not feasible
    ranked_pool = feasible if feasible else candidates
    if ranked_pool:
        best = ranked_pool[0]
    elif fallback_best is not None:
        best = dict(fallback_best)
    else:
        best = {}

    return SweepResult(candidates=candidates, best=best, all_infeasible=all_infeasible)
