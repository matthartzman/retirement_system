"""Full-grid candidate enumeration (§5.4) and move-2 anchor selection.

Pure combinatorics over years and locations -- no engine runs -- so grid
bounds and the ``no_dual_ownership`` rule can be exercised directly. The
narrowed alternative to this enumeration lives in ``search.py``.

The three axes -- the original home's disposition (and, when it is sold, its
sale year), each move's acquisition year, and each move's action -- are
independent. The old nested sale/purchase loop coupled them by clamping loop
bounds; that is what silently overrode a declared move-2 window. Ordering
rules are now expressed as explicit predicates instead.
"""
from __future__ import annotations

from .models import (
    HousingCandidate,
    Location,
    Move,
    MoveWindow,
    OriginalHome,
    SaleWindow,
    ScoredCandidate,
    _NARROWED_EVALS_PER_ANCHOR_LOCATION,
)


def _actions(action: str) -> tuple[str, ...]:
    if action == 'auto':
        return ('buy', 'rent')
    if action in ('buy', 'rent'):
        return (action,)
    raise ValueError(f"Unknown action: {action!r}")


def dual_ownership_ok(cand: HousingCandidate) -> bool:
    """The single place the 'never own two homes' rule is decided (§5.3).

    Two ways a candidate can own two homes at once:
      1. The original home is kept and something else is bought. With no
         rental-income model (Phase 2), a kept home is a pure cost centre, so
         this is refused outright rather than scored.
      2. A home is bought before the original one is sold.

    Concurrent mode is exempt: it always keeps two homes by construction, so
    the flag does not apply and the UI disables it.
    """
    home = cand.original_home
    buys = [m for m in cand.moves if m.action == 'buy' and m.mode != 'concurrent']
    if home.disposition == 'keep':
        return not buys
    if home.sale_year is None:
        return True
    return all(m.acquisition_year >= home.sale_year for m in buys)


def generate_candidates(
    *,
    locations1: list[Location],
    move1_window: MoveWindow,
    sale_window: SaleWindow,
    dispositions: tuple[str, ...],
    move1_action: str,
    no_dual_ownership: bool,
) -> list[HousingCandidate]:
    """Every (disposition, sale year, location, acquisition year, action) point.

    The three axes are independent -- that is the whole change from the old
    nested sale/purchase loop. ``no_dual_ownership`` prunes at the end via the
    single predicate rather than by clamping a loop bound, so the rule lives in
    one readable place.
    """
    out: list[HousingCandidate] = []
    for disposition in dispositions:
        if disposition == 'keep':
            sale_years: list[int | None] = [None]
        else:
            sale_years = list(range(sale_window.earliest_sale_year,
                                    sale_window.latest_sale_year + 1))
        for sale_year in sale_years:
            home = OriginalHome(disposition=disposition, sale_year=sale_year)
            for loc in locations1:
                for year in range(move1_window.earliest_acquisition_year,
                                  move1_window.latest_acquisition_year + 1):
                    for action in _actions(move1_action):
                        cand = HousingCandidate(
                            original_home=home,
                            moves=(Move(index=1, acquisition_year=year,
                                        action=action, location=loc),),
                        )
                        if no_dual_ownership and not dual_ownership_ok(cand):
                            continue
                        out.append(cand)
    return out


def extend_with_move2(
    anchors: list[HousingCandidate],
    *,
    locations2: list[Location],
    move2_window: MoveWindow,
    move2_action: str,
    concurrent: bool,
    no_dual_ownership: bool,
) -> list[HousingCandidate]:
    """Add a second move to each anchor, using move 2's OWN declared window.

    The old implementation derived move 2's lower bound from the anchor's
    purchase year, silently overriding whatever the user asked for. Here the
    declared window is authoritative and the only coupling is the ordering
    rule: a sequential move 2 must come strictly after move 1. A concurrent
    move 2 is a second simultaneous residence, not a relocation, so it may
    share move 1's year.
    """
    mode = 'concurrent' if concurrent else 'sequential'
    out: list[HousingCandidate] = []
    for anchor in anchors:
        for loc in locations2:
            for year in range(move2_window.earliest_acquisition_year,
                              move2_window.latest_acquisition_year + 1):
                if not concurrent and year <= anchor.move1.acquisition_year:
                    continue
                for action in _actions(move2_action):
                    cand = HousingCandidate(
                        original_home=anchor.original_home,
                        moves=anchor.moves + (Move(index=2, acquisition_year=year,
                                                   action=action, location=loc,
                                                   mode=mode),),
                        anchor_of=anchor,
                    )
                    if no_dual_ownership and not concurrent and not dual_ownership_ok(cand):
                        continue
                    out.append(cand)
    return out


def select_anchors(ranked: list[ScoredCandidate], anchor_count: int) -> list[HousingCandidate]:
    """Top move-1 candidates eligible to carry a move 2.

    Unlike the old rule, a rental move 1 IS eligible: with sale decoupled from
    acquisition, renting first and buying at move 2 is an ordinary plan, not a
    dead end.
    """
    return [s.candidate for s in ranked][:max(0, anchor_count)]


def select_all_eligible(scored: list[ScoredCandidate]) -> list[HousingCandidate]:
    return [s.candidate for s in scored]


def estimate_move2_candidate_count(
    eligible: list[HousingCandidate],
    *,
    locations2: list[Location],
    move2_window: MoveWindow,
    move2_action: str,
    concurrent: bool,
    no_dual_ownership: bool,
    narrowed: bool,
) -> int:
    """Move-2 candidates cross_product would evaluate, computed before any
    engine call (see MOVE2_CROSS_PRODUCT_CAP).

    Keyword-only past ``eligible`` on purpose. This signature gained
    ``move2_action`` and ``concurrent`` in the MIDDLE of the old positional
    order ``(eligible, locations, move2_window, no_dual_ownership, narrowed)``.
    A caller left on the old order would bind ``no_dual_ownership`` to
    ``move2_action`` and ``narrowed`` to ``concurrent`` -- all truthy, so the
    count would come back silently wrong and the cross-product cap would
    misfire. Keyword-only makes that a TypeError instead.
    """
    if narrowed:
        return len(eligible) * len(locations2) * _NARROWED_EVALS_PER_ANCHOR_LOCATION
    return len(extend_with_move2(
        eligible, locations2=locations2, move2_window=move2_window,
        move2_action=move2_action, concurrent=concurrent,
        no_dual_ownership=no_dual_ownership,
    ))
