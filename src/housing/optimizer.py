"""The two-pass orchestrator (§4): generate -> filter -> score -> rank,
then Monte Carlo the shortlist.

Everything it does is delegated -- candidate generation to ``candidates``/
``search``, filtering to ``constraints``, scoring to ``scoring``, engine
runs to ``plan_variant``, output shaping to ``results`` -- so this file
reads as the algorithm and nothing else.

Rejections are counted, not discarded. A zero-candidate run used to come back
with a generic sentence that named neither the constraint nor the field; the
``rejections`` tally threaded through ``format_output`` says which rule
emptied the search, which is the only thing that makes such a run actionable.
To make that tally possible the generators are called PERMISSIVELY
(``no_dual_ownership=False``) and the rule is applied here in
``_score_or_reject``, where a rejection can be attributed before any engine
run is paid for.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Literal

from .. import planning_engines as _pe
from ..server_services.strategy_asset_service import (
    HOME_APPR_DEFAULT,
    INFLATION_GENERAL_DEFAULT,
)
from .models import (
    FamilyPresence,
    Location,
    MOVE2_CROSS_PRODUCT_CAP,
    MOVE2_STRATEGIES,
    MoveWindow,
    OBJECTIVES,
    SEARCH_MODES,
    SaleWindow,
    ScoredCandidate,
)
from .candidates import (
    _action_count,
    dual_ownership_ok,
    estimate_move2_candidate_count,
    extend_with_move2,
    generate_candidates,
    no_housing_gap_ok,
    select_all_eligible,
    select_anchors,
)
from .constraints import family_presence_ok
from .plan_variant import _run_engine
from .results import format_output, MAX_CANDIDATES
from .scoring import _lifetime_cost, _pass1_objective, rank_candidates, score_candidate
from .search import (
    generate_move1_candidates_narrowed,
    generate_move2_candidates_narrowed,
)
from .zip_screen.screen import family_distance_for_zip


def _with_family_distance(
    locations: list[Location], family_presence: FamilyPresence | None,
    family_coords: dict[str, tuple[float, float]],
) -> list[Location]:
    """Splice each Location's distance-to-family onto it for display.

    Uses the screen's own ``family_distance_for_zip`` so the number in a
    results row and the number in a screen row are the same calculation.
    Without this the results table shows ``family_distance_miles: null`` for
    every row even when a family ZIP was given.
    """
    if family_presence is None:
        return list(locations)
    out = []
    for loc in locations:
        dist = family_distance_for_zip(loc.zip_code, family_presence.zip_code, family_coords)
        out.append(loc if dist is None else replace(loc, family_distance_miles=dist))
    return out


def optimize_housing(
    c0: dict[str, Any],
    *,
    locations1: list[Location],
    locations2: list[Location] | None = None,
    sale_window: SaleWindow,
    move1_window: MoveWindow,
    move2_window: MoveWindow | None = None,
    dispositions: tuple[str, ...] = ('sell',),
    move1_action: Literal['auto', 'buy', 'rent'] = 'auto',
    move2_action: Literal['auto', 'buy', 'rent'] = 'auto',
    move2_concurrent: bool = False,
    no_dual_ownership: bool = True,
    family_presence: FamilyPresence | None = None,
    family_coords: dict[str, tuple[float, float]] | None = None,
    anchor_count: int = 5,
    objective: str = 'net_worth',
    search_mode: Literal['full', 'narrowed'] = 'full',
    move2_strategy: Literal['anchored', 'cross_product'] = 'anchored',
    zip_screens: dict[str, Any] | None = None,
    down_payment_pct: float = 0.20,
    mortgage_rate_pct: float | None = None,
    shortlist_size: int = 5,
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
    if not locations1:
        raise ValueError("Provide at least one move-1 candidate location.")

    dispositions = tuple(dispositions or ('sell',))
    if 'auto' in dispositions:
        # 'auto' is a request-level value: generation expands it into both
        # concrete dispositions and the objective decides (§5.4).
        dispositions = ('sell', 'keep')
    unknown = [d for d in dispositions if d not in ('sell', 'keep')]
    if unknown:
        raise ValueError(f"Unknown disposition: {unknown[0]!r}")

    family_coords = dict(family_coords or {})
    zip_screens = dict(zip_screens or {})
    locations1 = _with_family_distance(list(locations1), family_presence, family_coords)
    locations2 = _with_family_distance(list(locations2 or []), family_presence, family_coords)

    pass1_objective = _pass1_objective(objective)
    narrowed = search_mode == 'narrowed'
    rejections = {'dual_ownership': 0, 'family_presence': 0, 'move_order': 0, 'housing_gap': 0}

    def _score_or_reject(cand) -> ScoredCandidate | None:
        """The one place a candidate is refused, so every refusal is counted.

        Order matters: the pure predicates run before ``_run_engine``, so a
        rejected candidate costs no engine time.
        """
        m2 = cand.move2
        if (m2 is not None and m2.mode != 'concurrent'
                and m2.acquisition_year <= cand.move1.acquisition_year):
            rejections['move_order'] += 1
            return None
        if not no_housing_gap_ok(cand):
            rejections['housing_gap'] += 1
            return None
        if no_dual_ownership and not dual_ownership_ok(cand):
            rejections['dual_ownership'] += 1
            return None
        covered, via_rental = family_presence_ok(cand, family_presence, family_coords)
        if not covered:
            rejections['family_presence'] += 1
            return None
        c2, rows = _run_engine(c0, cand, down_payment_pct=down_payment_pct,
                               mortgage_rate_pct=mortgage_rate_pct)
        if not rows:
            return None
        return score_candidate(c2, cand, rows, via_rental=via_rental)

    # ---- Pass 1a: move 1 -------------------------------------------------
    if narrowed:
        move1_scored = generate_move1_candidates_narrowed(
            locations1=locations1, move1_window=move1_window, sale_window=sale_window,
            dispositions=dispositions, move1_action=move1_action,
            # Permissive: _score_or_reject owns the rule so it can tally.
            no_dual_ownership=False, score_fn=_score_or_reject,
            objective=pass1_objective,
        )
    else:
        move1_scored = []
        for cand in generate_candidates(
            locations1=locations1, move1_window=move1_window, sale_window=sale_window,
            dispositions=dispositions, move1_action=move1_action,
            no_dual_ownership=False,
        ):
            sc = _score_or_reject(cand)
            if sc is not None:
                move1_scored.append(sc)
    move1_scored = rank_candidates(move1_scored, pass1_objective)

    # ---- Pass 1b: move 2 -------------------------------------------------
    move2_scored: list[ScoredCandidate] = []
    if move2_window is not None and locations2:
        if move2_strategy == 'cross_product':
            # anchor_count is irrelevant here by design (§8.2 P3): every
            # scored move-1 candidate is used, not just the top N.
            anchors = select_all_eligible(move1_scored)
            estimated = estimate_move2_candidate_count(
                anchors, locations2=locations2, move2_window=move2_window,
                move2_action=move2_action, concurrent=False,
                no_dual_ownership=no_dual_ownership, narrowed=narrowed,
            )
        else:
            # anchor_count alone does not bound this branch's candidate count:
            # nothing here validates its upper bound, and even a small
            # anchor_count times a wide move2_window/location count can be
            # large. The non-concurrent anchored count is left unchecked
            # (pre-existing behavior), but move2_concurrent's contribution is
            # not exempt, so it is still counted and capped below.
            anchors = select_anchors(move1_scored, anchor_count)
            estimated = 0

        # move2_concurrent generates its own separate candidate set
        # (``extend_with_move2(..., concurrent=True)``), independent of
        # move2_strategy and not covered by the estimate above. Count it
        # exactly and fold it into the same pre-generation cap check rather
        # than letting it bypass MOVE2_CROSS_PRODUCT_CAP entirely.
        concurrent_estimated = 0
        if move2_concurrent:
            concurrent_estimated = estimate_move2_candidate_count(
                anchors, locations2=locations2, move2_window=move2_window,
                move2_action=move2_action, concurrent=True,
                no_dual_ownership=no_dual_ownership, narrowed=False,
            )
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
                anchors, locations2=locations2, move2_window=move2_window,
                move2_action=move2_action, concurrent=False,
                no_dual_ownership=False, score_fn=_score_or_reject,
                objective=pass1_objective,
            )
        else:
            move2_scored = _extend_and_score(
                anchors, locations2, move2_window, move2_action,
                concurrent=False, score_fn=_score_or_reject, rejections=rejections,
            )
        move2_scored = rank_candidates(move2_scored, pass1_objective)

        if move2_concurrent:
            concurrent_scored = _extend_and_score(
                anchors, locations2, move2_window, move2_action,
                concurrent=True, score_fn=_score_or_reject, rejections=rejections,
            )
            move2_scored = rank_candidates(move2_scored + concurrent_scored, pass1_objective)

    combined = rank_candidates(move1_scored + move2_scored, pass1_objective)

    # A two-move plan almost always scores worse on a pure objective value
    # than a one-move plan (one fewer transaction/moving cost), so when a
    # move-2 search was actually requested and run, its candidates can be
    # crowded out of every one of the MAX_CANDIDATES rows the UI ever sees --
    # "Move 2" then reads as broken/unpopulated even though the search found
    # results. Guarantee the best move-2 candidate a visible seat instead of
    # silently dropping the thing the user explicitly asked to search for.
    if move2_scored and not any(
        sc.candidate.move2 is not None for sc in combined[:MAX_CANDIDATES]
    ):
        combined = combined[:MAX_CANDIDATES - 1] + [move2_scored[0]]

    # ---- Pass 2: Monte Carlo the shortlist --------------------------------
    shortlist = combined[:max(3, min(5, shortlist_size))]
    for sc in shortlist:
        c2, rows = _run_engine(c0, sc.candidate, down_payment_pct=down_payment_pct,
                               mortgage_rate_pct=mortgage_rate_pct)
        mc = _pe.monte_carlo(c2, base_rows=rows)
        sc.mc_success_rate = float(mc.get('success_rate', 0.0) or 0.0)

    if objective == 'mc_success_rate':
        shortlist = sorted(shortlist, key=lambda s: (s.mc_success_rate or 0.0), reverse=True)
        shortlist_ids = {id(s) for s in shortlist}
        final_ranked = shortlist + [s for s in combined if id(s) not in shortlist_ids]
    else:
        final_ranked = combined

    # The do-nothing baseline (no sale, no move -- c0 run unmutated), so the
    # results table's "impact" column can read as "vs. staying put" instead
    # of "vs. the recommendation" (whose own value has no baseline of its
    # own to compare against). Only run it when there is at least one
    # candidate to show it against -- a zero-candidate (all-rejected) run
    # never reaches the engine at all today, and this must not be the one
    # path that changes that. mc_success_rate is only run through Monte
    # Carlo when it is the active objective, matching the shortlist's own
    # policy of not paying for MC on every candidate.
    baseline = None
    if final_ranked:
        baseline_c2, baseline_rows = _pe.run_scenario(c0)
        baseline_mc_success_rate = None
        if objective == 'mc_success_rate':
            baseline_mc = _pe.monte_carlo(baseline_c2, base_rows=baseline_rows)
            baseline_mc_success_rate = float(baseline_mc.get('success_rate', 0.0) or 0.0)
        baseline = {
            'net_worth': float(baseline_rows[-1].get('total_nw', 0.0) or 0.0) if baseline_rows else 0.0,
            'lifetime_cost': _lifetime_cost(baseline_rows),
            'mc_success_rate': baseline_mc_success_rate,
        }

    return format_output(
        final_ranked, objective=objective, search_mode=search_mode,
        move2_strategy=move2_strategy, zip_screens=zip_screens,
        rejections=rejections,
        down_payment_pct=down_payment_pct, mortgage_rate_pct=mortgage_rate_pct,
        home_appr=float(c0.get('home_appr', HOME_APPR_DEFAULT) or HOME_APPR_DEFAULT),
        inflation_general=float(c0.get('inf', INFLATION_GENERAL_DEFAULT) or INFLATION_GENERAL_DEFAULT),
        baseline=baseline,
    )


def _extend_and_score(
    anchors, locations2, move2_window, move2_action, *,
    concurrent: bool, score_fn, rejections: dict[str, int],
) -> list[ScoredCandidate]:
    """Build move-2 candidates and score them, tallying the ordering rule.

    ``extend_with_move2`` drops an out-of-order sequential move 2 inside its
    own loop, so those points never reach ``score_fn`` and cannot be counted
    there. The full cross-product size is known exactly from the loop bounds,
    so the drop count is the difference -- no duplicated ordering logic.
    """
    cands = extend_with_move2(
        anchors, locations2=locations2, move2_window=move2_window,
        move2_action=move2_action, concurrent=concurrent,
        no_dual_ownership=False,
    )
    if not concurrent:
        span = (move2_window.latest_acquisition_year
                - move2_window.earliest_acquisition_year + 1)
        full = len(anchors) * len(locations2) * max(0, span) * _action_count(move2_action)
        rejections['move_order'] += max(0, full - len(cands))
    out = []
    for cand in cands:
        sc = score_fn(cand)
        if sc is not None:
            out.append(sc)
    return out
