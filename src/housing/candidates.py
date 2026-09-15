"""Full-grid candidate enumeration (§3) and move-2 anchor selection.

Pure combinatorics over years and locations -- no engine runs -- so grid
bounds and the ``no_dual_ownership`` rule can be exercised directly. The
narrowed alternative to this enumeration lives in ``search.py``.
"""
from __future__ import annotations

from .models import (
    HousingCandidate,
    Location,
    Move2Window,
    ScoredCandidate,
    SearchWindow,
    _NARROWED_EVALS_PER_ANCHOR_LOCATION,
)


# ---------------------------------------------------------------------------
# Candidate generation (§3)
# ---------------------------------------------------------------------------

def generate_move1_candidates(
    locations: list[Location], window: SearchWindow, no_dual_ownership: bool,
) -> list[HousingCandidate]:
    out: list[HousingCandidate] = []
    for loc in locations:
        for sale_year in range(window.earliest_sale_year, window.latest_sale_year + 1):
            out.append(HousingCandidate(location_1=loc, sale_year=sale_year, purchase_year=None))
            for purchase_year in range(window.earliest_purchase_year, window.latest_purchase_year + 1):
                if no_dual_ownership and purchase_year < sale_year:
                    continue
                out.append(HousingCandidate(location_1=loc, sale_year=sale_year, purchase_year=purchase_year))
    return out


def generate_move2_candidates(
    anchors: list[HousingCandidate], locations: list[Location],
    move2_window: Move2Window, no_dual_ownership: bool,
) -> list[HousingCandidate]:
    """Anchored on ``anchors`` (top move-1 candidates that ended in
    ownership -- §3.2/§4: a rent-indefinitely-forever move-1 outcome is not
    extended). Sale-2's earliest bound is derived (can't sell before move 1's
    purchase); purchase-2's earliest bound follows ``no_dual_ownership``.
    """
    out: list[HousingCandidate] = []
    for anchor in anchors:
        if anchor.purchase_year is None:
            continue
        earliest_sale_2 = anchor.purchase_year
        for loc in locations:
            for sale_year_2 in range(earliest_sale_2, move2_window.latest_sale_year_2 + 1):
                out.append(HousingCandidate(
                    location_1=anchor.location_1, sale_year=anchor.sale_year, purchase_year=anchor.purchase_year,
                    location_2=loc, sale_year_2=sale_year_2, purchase_year_2=None, anchor_of=anchor,
                ))
                earliest_purchase_2 = sale_year_2 if no_dual_ownership else earliest_sale_2
                for purchase_year_2 in range(earliest_purchase_2, move2_window.latest_purchase_year_2 + 1):
                    if no_dual_ownership and purchase_year_2 < sale_year_2:
                        continue
                    out.append(HousingCandidate(
                        location_1=anchor.location_1, sale_year=anchor.sale_year, purchase_year=anchor.purchase_year,
                        location_2=loc, sale_year_2=sale_year_2, purchase_year_2=purchase_year_2, anchor_of=anchor,
                    ))
    return out


def generate_move2_concurrent_candidates(
    anchors: list[HousingCandidate], locations: list[Location], move2_window: Move2Window,
) -> list[HousingCandidate]:
    """Concurrent-mode move-2 candidates: the anchor's move-1 home
    (``location_1``) is kept as an ongoing residence and never sold;
    ``location_2`` is added as a second, simultaneous residence starting
    anywhere in ``[anchor.purchase_year, move2_window.latest_purchase_year_2]``
    (``latest_sale_year_2`` is not meaningful here -- nothing is ever sold,
    so it's not used). Both a purchase and a rent-indefinitely variant of
    location_2 are generated per (anchor, location, start_year) point,
    mirroring ``generate_move2_candidates``'s purchase/rent split. Anchors
    that ended move 1 in rent-indefinitely-forever are skipped -- same rule
    ``generate_move2_candidates`` applies (nothing to add a concurrent
    second home to).
    """
    out: list[HousingCandidate] = []
    for anchor in anchors:
        if anchor.purchase_year is None:
            continue
        earliest_start = anchor.purchase_year
        for loc in locations:
            for start_year in range(earliest_start, move2_window.latest_purchase_year_2 + 1):
                out.append(HousingCandidate(
                    location_1=anchor.location_1, sale_year=anchor.sale_year, purchase_year=anchor.purchase_year,
                    location_2=loc, sale_year_2=None, purchase_year_2=start_year,
                    move2_mode='concurrent', concurrent_start_year_2=start_year, anchor_of=anchor,
                ))
                out.append(HousingCandidate(
                    location_1=anchor.location_1, sale_year=anchor.sale_year, purchase_year=anchor.purchase_year,
                    location_2=loc, sale_year_2=None, purchase_year_2=None,
                    move2_mode='concurrent', concurrent_start_year_2=start_year, anchor_of=anchor,
                ))
    return out


def filter_candidates_by_action(
    candidates: list[HousingCandidate], action: str, purchase_year_attr: str,
) -> list[HousingCandidate]:
    """Drops candidates inconsistent with a 'buy only'/'rent only' move
    constraint. ``purchase_year_attr`` is ``'purchase_year'`` for move 1,
    ``'purchase_year_2'`` for move 2 -- both fields use the same None-means-
    rent convention (module docstring)."""
    if action == 'auto':
        return candidates
    if action == 'buy':
        return [c for c in candidates if getattr(c, purchase_year_attr) is not None]
    if action == 'rent':
        return [c for c in candidates if getattr(c, purchase_year_attr) is None]
    raise ValueError(f"Unknown action: {action!r}")


# ---------------------------------------------------------------------------
# Anchor selection and pre-flight cost estimation (§3.2 / §8.2 P3)
# ---------------------------------------------------------------------------

def select_anchors(ranked_move1: list[ScoredCandidate], anchor_count: int) -> list[HousingCandidate]:
    """Top ``anchor_count`` move-1 candidates (by Pass-1 score) that ended
    in ownership -- rent-indefinitely-forever outcomes are not extended."""
    owned = [s.candidate for s in ranked_move1 if s.candidate.purchase_year is not None]
    return owned[:max(0, anchor_count)]


def select_all_eligible_move1_candidates(move1_scored: list[ScoredCandidate]) -> list[HousingCandidate]:
    """Every move-1 candidate eligible to carry a move 2 -- same rule
    ``select_anchors`` applies (ended in ownership; a rent-indefinitely-
    forever outcome is not extended), just not narrowed to the top
    ``anchor_count``. Used by ``move2_strategy='cross_product'`` (§8.2 P3).
    """
    return [s.candidate for s in move1_scored if s.candidate.purchase_year is not None]


def estimate_move2_candidate_count(
    eligible: list[HousingCandidate], locations: list[Location],
    move2_window: Move2Window, no_dual_ownership: bool, narrowed: bool,
) -> int:
    """Candidates ``move2_strategy='cross_product'`` would evaluate, computed
    (or, for ``narrowed``, estimated) before any engine call -- see
    ``MOVE2_CROSS_PRODUCT_CAP``'s docstring for why this check exists.

    ``'full'`` mode builds the actual candidate list -- cheap, no engine
    calls -- and counts it exactly. ``'narrowed'`` mode can't be counted that
    way: ``generate_move2_candidates_narrowed`` scores each point as it
    searches rather than building a list first, so this instead uses the
    same fixed per-(anchor, location) evaluation budget its docstring
    documents as an upper-bound estimate.
    """
    if narrowed:
        return len(eligible) * len(locations) * _NARROWED_EVALS_PER_ANCHOR_LOCATION
    return len(generate_move2_candidates(eligible, locations, move2_window, no_dual_ownership))
