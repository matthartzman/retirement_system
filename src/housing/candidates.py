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
    NARROWED_MAX_EVALS_PER_AXIS,
    NARROWED_MOVE2_AXES,
    SaleWindow,
    ScoredCandidate,
)


def _action_count(action: str) -> int:
    """How many action values ``action`` expands to (2 for 'auto', else 1),
    location-independent. Used only for pre-search SIZE ESTIMATES
    (``estimate_move2_candidate_count``, ``optimizer.py``'s rejection-tally
    upper bound) where the estimate covers a whole location list, not one
    specific location -- so it deliberately does NOT apply the apartment
    exclusion ``actions_for_location`` does: it stays an upper bound (safe
    for a safety cap to over-count against) rather than a location-specific
    exact count."""
    if action == 'auto':
        return 2
    if action in ('buy', 'rent'):
        return 1
    raise ValueError(f"Unknown action: {action!r}")


def actions_for_location(action: str, location: Location) -> tuple[str, ...]:
    """Which of 'buy'/'rent' a move can consider at this location.

    Apartment is rental-only in this model: 'buy' is excluded even under
    'auto' (so 'auto' silently narrows to rent-only for an apartment
    location rather than ever proposing an apartment purchase), and an
    explicit 'buy' request against an apartment location yields an empty
    tuple -- ``api.validate_request`` rejects that combination before
    generation ever runs, so this function itself never needs to raise for
    it.

    Shared by both search strategies (imported into ``search.py``) so the
    full-grid and narrowed paths can never disagree about which actions a
    location supports.
    """
    if action == 'auto':
        opts: tuple[str, ...] = ('buy', 'rent')
    elif action in ('buy', 'rent'):
        opts = (action,)
    else:
        raise ValueError(f"Unknown action: {action!r}")
    if location.property_type == 'apartment':
        opts = tuple(a for a in opts if a != 'buy')
    return opts


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


def no_housing_gap_ok(cand: HousingCandidate) -> bool:
    """Reject a candidate that would leave the household with no housing
    arrangement for one or more years.

    Sale year and move-1 acquisition year are searched on independent axes
    (see ``generate_candidates`` below), so a candidate can pair an early
    sale with a much later move-in with nothing bridging the years between
    -- the deterministic engine has no housing step covering those years at
    all, not even a placeholder rental, which is the "gap year" bug this
    guards against. Selling and acquiring in the same year, or acquiring the
    year right after the sale, is the transition itself, not a gap, so only
    a larger separation is rejected. Move 1 to move 2 needs no equivalent
    check: ``plan_variant._apply_candidate`` builds their steps back-to-back
    by construction, so a sequential move 2 never leaves a gap after move 1.
    """
    home = cand.original_home
    if home.disposition != 'sell' or home.sale_year is None:
        return True
    return cand.move1.acquisition_year <= home.sale_year + 1


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
                    for action in actions_for_location(move1_action, loc):
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
                for action in actions_for_location(move2_action, loc):
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
        # axes x actions, from the same constants the search itself uses:
        # ``generate_move2_candidates_narrowed`` runs one descent per
        # (anchor, location, action) with a budget of
        # NARROWED_MAX_EVALS_PER_AXIS * NARROWED_MOVE2_AXES.
        return (len(eligible) * len(locations2)
                * NARROWED_MAX_EVALS_PER_AXIS * NARROWED_MOVE2_AXES
                * _action_count(move2_action))
    return len(extend_with_move2(
        eligible, locations2=locations2, move2_window=move2_window,
        move2_action=move2_action, concurrent=concurrent,
        no_dual_ownership=no_dual_ownership,
    ))
