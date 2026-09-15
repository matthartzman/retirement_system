"""The two-pass orchestrator (§4): generate -> filter -> score -> rank,
then Monte Carlo the shortlist.

Everything it does is delegated -- candidate generation to ``candidates``/
``search``, filtering to ``constraints``, scoring to ``scoring``, engine
runs to ``plan_variant``, output shaping to ``results`` -- so this file
reads as the algorithm and nothing else.
"""
from __future__ import annotations

from typing import Any, Literal

from .. import planning_engines as _pe
from .models import (
    FamilyPresence,
    Location,
    MOVE2_CROSS_PRODUCT_CAP,
    MOVE2_STRATEGIES,
    Move2Window,
    OBJECTIVES,
    SEARCH_MODES,
    ScoredCandidate,
    SearchWindow,
)
from .candidates import (
    estimate_move2_candidate_count,
    filter_candidates_by_action,
    generate_move1_candidates,
    generate_move2_candidates,
    generate_move2_concurrent_candidates,
    select_all_eligible_move1_candidates,
    select_anchors,
)
from .constraints import family_presence_ok
from .plan_variant import _run_engine
from .results import _format_output
from .scoring import _pass1_objective, rank_candidates, score_candidate
from .search import (
    generate_move1_candidates_narrowed,
    generate_move2_candidates_narrowed,
)

def optimize_housing(
    c0: dict[str, Any],
    *,
    locations: list[Location],
    move1_window: SearchWindow,
    move2_window: Move2Window | None = None,
    anchor_count: int = 5,
    no_dual_ownership: bool = True,
    family_presence: FamilyPresence | None = None,
    objective: str = 'net_worth',
    shortlist_size: int = 5,
    search_mode: Literal['full', 'narrowed'] = 'full',
    move2_strategy: Literal['anchored', 'cross_product'] = 'anchored',
    move1_action: Literal['auto', 'buy', 'rent'] = 'auto',
    move2_action: Literal['auto', 'buy', 'rent'] = 'auto',
    move2_concurrent: bool = False,
) -> dict[str, Any]:
    if objective not in OBJECTIVES:
        raise ValueError(f"Unknown objective: {objective!r}")
    if search_mode not in SEARCH_MODES:
        raise ValueError(f"Unknown search_mode: {search_mode!r}")
    if move2_strategy not in MOVE2_STRATEGIES:
        raise ValueError(f"Unknown move2_strategy: {move2_strategy!r}")
    if move1_action not in ('auto', 'buy', 'rent'):
        raise ValueError(f"Unknown move1_action: {move1_action!r}")
    if move2_action not in ('auto', 'buy', 'rent'):
        raise ValueError(f"Unknown move2_action: {move2_action!r}")
    if move2_concurrent and search_mode == 'narrowed':
        raise ValueError("move2_concurrent is not supported with search_mode='narrowed'.")
    if not (2 <= len(locations) <= 4):
        raise ValueError("Provide 2-4 candidate locations.")

    base_state = str(c0.get('state', '') or '')
    pass1_objective = _pass1_objective(objective)
    narrowed = search_mode == 'narrowed'

    if narrowed:
        move1_scored = generate_move1_candidates_narrowed(
            c0, base_state, locations, move1_window, no_dual_ownership, move1_action, family_presence, pass1_objective,
        )
    else:
        move1_scored = []
        move1_cands = filter_candidates_by_action(
            generate_move1_candidates(locations, move1_window, no_dual_ownership), move1_action, 'purchase_year',
        )
        for cand in move1_cands:
            ok, via_rental = family_presence_ok(base_state, cand, family_presence)
            if not ok:
                continue
            c2, rows = _run_engine(c0, cand)
            if not rows:
                continue
            sc = score_candidate(c2, cand, rows)
            sc.family_presence_via_rental = via_rental
            move1_scored.append(sc)
    move1_scored = rank_candidates(move1_scored, pass1_objective)

    move2_scored: list[ScoredCandidate] = []
    if move2_window is not None:
        if move2_strategy == 'cross_product':
            # anchor_count is irrelevant here by design (§8.2 P3 module
            # docstring): every eligible move-1 candidate is used, not just
            # the top N.
            anchors = select_all_eligible_move1_candidates(move1_scored)
            estimated = estimate_move2_candidate_count(
                anchors, locations, move2_window, no_dual_ownership, narrowed,
            )
        else:
            # anchor_count alone does not bound this branch's candidate count
            # the way the comment above claims for cross_product: nothing in
            # optimize_housing validates anchor_count's upper bound (a caller
            # -- e.g. optimize_housing_from_request -- can pass anything), and
            # even a small anchor_count times a wide move2_window/location
            # count can still be large. The non-concurrent anchored count
            # itself is left unchecked here (unchanged pre-existing
            # behavior, out of scope for this fix), but move2_concurrent's
            # contribution below is not exempt from that same risk, so it
            # still gets counted and capped.
            anchors = select_anchors(move1_scored, anchor_count)
            estimated = 0

        # move2_concurrent generates its own separate candidate set (§8.2
        # move-2 concurrent mode) via generate_move2_concurrent_candidates,
        # independent of move2_strategy and not covered by
        # estimate_move2_candidate_count above. It's cheap to build (no
        # engine calls), so count it exactly and fold it into the same
        # pre-generation cap check rather than letting it bypass
        # MOVE2_CROSS_PRODUCT_CAP entirely (move2_concurrent is disallowed
        # with search_mode='narrowed' above, so `narrowed` is always False
        # here and generate_move2_concurrent_candidates's real, non-estimated
        # count applies).
        concurrent_estimated = 0
        if move2_concurrent:
            concurrent_estimated = len(generate_move2_concurrent_candidates(anchors, locations, move2_window))
            estimated += concurrent_estimated

        if estimated > MOVE2_CROSS_PRODUCT_CAP:
            if concurrent_estimated and move2_strategy == 'cross_product':
                raise ValueError(
                    f"move2_strategy='cross_product' with move2_concurrent=True would evaluate "
                    f"~{estimated} move-2 candidates (including {concurrent_estimated} concurrent "
                    f"candidates), over the safety cap of {MOVE2_CROSS_PRODUCT_CAP}. Narrow the "
                    "search window(s), use fewer candidate locations, or set search_mode='narrowed' "
                    "to make cross-product search tractable."
                )
            if concurrent_estimated:
                raise ValueError(
                    f"move2_concurrent=True would evaluate ~{concurrent_estimated} concurrent "
                    f"move-2 candidates, over the safety cap of {MOVE2_CROSS_PRODUCT_CAP}. Narrow "
                    "the move-2 window, use fewer candidate locations, or reduce anchor_count."
                )
            raise ValueError(
                f"move2_strategy='cross_product' would evaluate ~{estimated} move-2 "
                f"candidates, over the safety cap of {MOVE2_CROSS_PRODUCT_CAP}. Narrow "
                "the search window(s), use fewer candidate locations, or set "
                "search_mode='narrowed' to make cross-product search tractable."
            )
        if narrowed:
            move2_scored = generate_move2_candidates_narrowed(
                c0, base_state, anchors, locations, move2_window, no_dual_ownership, move2_action, family_presence,
                pass1_objective,
            )
        else:
            move2_cands = filter_candidates_by_action(
                generate_move2_candidates(anchors, locations, move2_window, no_dual_ownership),
                move2_action, 'purchase_year_2',
            )
            for cand in move2_cands:
                ok, via_rental = family_presence_ok(base_state, cand, family_presence)
                if not ok:
                    continue
                c2, rows = _run_engine(c0, cand)
                if not rows:
                    continue
                sc = score_candidate(c2, cand, rows)
                sc.family_presence_via_rental = via_rental
                move2_scored.append(sc)
        move2_scored = rank_candidates(move2_scored, pass1_objective)

        if move2_concurrent:
            concurrent_cands = filter_candidates_by_action(
                generate_move2_concurrent_candidates(anchors, locations, move2_window),
                move2_action, 'purchase_year_2',
            )
            concurrent_scored = []
            for cand in concurrent_cands:
                ok, via_rental = family_presence_ok(base_state, cand, family_presence)
                if not ok:
                    continue
                c2, rows = _run_engine(c0, cand)
                if not rows:
                    continue
                sc = score_candidate(c2, cand, rows)
                sc.family_presence_via_rental = via_rental
                concurrent_scored.append(sc)
            move2_scored = rank_candidates(move2_scored + concurrent_scored, pass1_objective)

    combined = rank_candidates(move1_scored + move2_scored, pass1_objective)

    shortlist = combined[:max(3, min(5, shortlist_size))]
    for sc in shortlist:
        c2, rows = _run_engine(c0, sc.candidate)
        mc = _pe.monte_carlo(c2, base_rows=rows)
        sc.mc_success_rate = float(mc.get('success_rate', 0.0) or 0.0)

    if objective == 'mc_success_rate':
        shortlist = sorted(shortlist, key=lambda s: (s.mc_success_rate or 0.0), reverse=True)
        shortlist_ids = {id(s) for s in shortlist}
        final_ranked = shortlist + [s for s in combined if id(s) not in shortlist_ids]
    else:
        final_ranked = combined

    return _format_output(final_ranked, objective, search_mode, move2_strategy)
