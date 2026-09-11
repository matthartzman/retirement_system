"""Housing move optimizer (grid search over sale/purchase year and location).

Implements docs/superpowers/specs/2026-09-09-housing-optimization-design.md.
Given a set of candidate locations and search windows, generates plan-config
variants, runs them through the existing deterministic engine
(``planning_engines.run_scenario`` -> ``projection_stages.deterministic_engine``)
and Monte Carlo runner (``planning_engines.monte_carlo``) unmodified, filters
by ``no_dual_ownership``/``family_presence``, scores by the selected
objective, and ranks. No new tax logic is added, for move 1 or move 2: both
sales reuse the engine's own gain/§121 pathway in ``home_sale.py`` exactly as
a manually-configured plan would.

**Move 2 is a real, cascade-visible sale (§8.2 P0 of the design doc).** The
engine now has a second sale-with-capital-gain pathway --
``home_sale.py``'s ``apply_next_housing_sale``, sharing the same gain/§121
arithmetic ``apply_home_sale`` uses for the original home -- that a
``next_housing_steps`` purchase step can be pointed at via a ``sale_year``
field. This module sets that field (``_apply_candidate`` below) instead of
computing move-2's gain/tax itself: the engine's own run produces a real
deposit its withdrawal cascade and Monte Carlo runner both see, so
``net_worth``/``lifetime_cost``/``mc_success_rate`` for a two-move candidate
are as accurate as for a one-move candidate -- no separate out-of-loop
estimate, and no ``mc_approximate`` flag (removed; see git history for the
prior out-of-loop ``Move2SaleEstimate``/``_estimate_move2_sale`` approach
this replaced).

The §121 two-of-five-year ownership/use test is not modeled by the engine at
all (``home_sale.py`` always grants the full statutory exclusion regardless
of ownership duration). Per §3.1.3 of the design doc, failing candidates are
not dropped, only flagged -- so ``sec121_exclusion_lost`` here is an
informational flag (ownership span < 2 years) that never changes a computed
dollar figure, for either move.

**Narrowed search mode (§8.2 P2).** ``optimize_housing``'s default
``search_mode='full'`` is the grid above, byte-for-byte unchanged. Opting
into ``search_mode='narrowed'`` replaces, per candidate location, the full
``(sale_year x purchase_year)`` grid with a bounded coordinate/pattern search
(``_coordinate_search_2d``): a handful of seed points (grid corners plus
center) followed by hill-climbing to the best-improving integer-year
neighbor until none improves, capped at a small evaluation budget -- and
replaces the rent-indefinitely branch's full ``sale_year`` sweep with the
same style of 1D neighbor search (``_coordinate_search_1d``). Move 2's
window is narrowed the same way when both ``search_mode='narrowed'`` and a
``move2_window`` are given. This is a local-search heuristic on whatever
score surface the real engine happens to produce -- it is not guaranteed
unimodal, so narrowed mode can converge on a local rather than the global
optimum and trades completeness for far fewer engine runs (see §7/§8.2 of
the design doc). Candidate *generation* is the only thing that differs;
scoring, filtering, and ranking (``_run_engine``/``score_candidate``/
``family_presence_ok``/``no_dual_ownership``/``rank_candidates``) are shared
unmodified with the full-grid path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from . import planning_engines as _pe
from .server_services.strategy_asset_service import housing_state_estimate_payload

OBJECTIVES = ('net_worth', 'lifetime_cost', 'mc_success_rate')
SEARCH_MODES = ('full', 'narrowed')

_DEFAULT_MORTGAGE_RATE = 0.0685
_DEFAULT_DOWN_PAYMENT_PCT = 0.20

# ``Location.state`` is a full state name (e.g. "Texas") -- the form
# ``core.state_for_year``/``state_income_tax`` and ``residency_schedule``
# require (``core.STATE_TAX_RULES`` is keyed this way). The housing cost
# estimate lookup (``housing_state_estimate_payload``/``STATE_ESTIMATES`` in
# strategy_asset_service.py) is keyed by two-letter abbreviation instead --
# an existing mismatch between those two features, not introduced here. This
# maps the common ones so one ``Location.state`` value serves both; an
# unmapped state still works, it just falls back to
# ``housing_state_estimate_payload``'s generic default cost estimate.
_STATE_ABBREV = {
    'Arizona': 'AZ', 'California': 'CA', 'Colorado': 'CO', 'Florida': 'FL',
    'Illinois': 'IL', 'Indiana': 'IN', 'Nevada': 'NV', 'New York': 'NY',
    'North Carolina': 'NC', 'South Dakota': 'SD', 'Tennessee': 'TN',
    'Texas': 'TX', 'Wyoming': 'WY',
}


# ---------------------------------------------------------------------------
# Input types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Location:
    state: str
    city_type: str = 'suburban'
    population_size: int = 20000
    target_purchase_price_range: tuple[float, float] | None = None


@dataclass(frozen=True)
class SearchWindow:
    earliest_sale_year: int
    latest_sale_year: int
    earliest_purchase_year: int
    latest_purchase_year: int


@dataclass(frozen=True)
class Move2Window:
    latest_sale_year_2: int
    latest_purchase_year_2: int


@dataclass(frozen=True)
class FamilyPresence:
    region: str
    start_year: int
    end_year: int


@dataclass
class HousingCandidate:
    """One fully-specified plan variant: move 1, and optionally move 2.

    ``purchase_year is None`` means "rent indefinitely" after ``sale_year``
    (move 1) or after ``sale_year_2`` (move 2, when ``purchase_year_2`` is
    also ``None``).
    """
    location_1: Location
    sale_year: int
    purchase_year: int | None
    location_2: Location | None = None
    sale_year_2: int | None = None
    purchase_year_2: int | None = None
    anchor_of: "HousingCandidate | None" = None

    @property
    def is_two_move(self) -> bool:
        return self.location_2 is not None


@dataclass
class ScoredCandidate:
    candidate: HousingCandidate
    net_worth: float
    lifetime_cost: float
    mc_success_rate: float | None
    sec121_exclusion_lost: list[bool]
    family_presence_via_rental: bool = False


# ---------------------------------------------------------------------------
# Location cost estimates (reuses the existing housing_state_estimate_v1
# helper -- see strategy_asset_service.py -- so purchase price/rent/tax/
# insurance/HOA figures come from the one place the UI already sources them)
# ---------------------------------------------------------------------------

def _estimate_for_location(loc: Location, housing_type: str) -> dict[str, Any]:
    payload, _status = housing_state_estimate_payload({
        'state': _STATE_ABBREV.get(loc.state, loc.state),
        'type': housing_type,
        'city_type': loc.city_type,
        'population_size': loc.population_size,
    })
    return payload['estimate']


def _purchase_price_for_location(loc: Location) -> float:
    if loc.target_purchase_price_range:
        lo, hi = loc.target_purchase_price_range
        return (float(lo) + float(hi)) / 2.0
    return float(_estimate_for_location(loc, 'purchase')['purchase_price'])


def _purchase_step(step_id: str, loc: Location, start_year: int, end_year: int | None) -> dict[str, Any]:
    est = _estimate_for_location(loc, 'purchase')
    return {
        'id': step_id, 'type': 'purchase',
        'start_year': start_year, 'end_year': end_year or 0,
        'state': loc.state, 'city_type': loc.city_type, 'population_size': loc.population_size,
        'purchase_price': _purchase_price_for_location(loc),
        'down_payment_pct': _DEFAULT_DOWN_PAYMENT_PCT,
        'mortgage_rate_pct': float(est.get('mortgage_rate_pct', _DEFAULT_MORTGAGE_RATE) or _DEFAULT_MORTGAGE_RATE),
        'monthly_rent': 0.0,
        'insurance_annual': float(est.get('insurance_annual', 0.0) or 0.0),
        'utilities_annual': float(est.get('utilities_annual', 0.0) or 0.0),
        'maintenance_annual': float(est.get('maintenance_annual', 0.0) or 0.0),
        'real_estate_tax_pct': float(est.get('re_tax_pct', 0.0) or 0.0),
        'hoa_pct': float(est.get('hoa_pct', 0.0) or 0.0),
    }


def _rent_step(step_id: str, loc: Location, start_year: int, end_year: int | None) -> dict[str, Any]:
    est = _estimate_for_location(loc, 'rent')
    return {
        'id': step_id, 'type': 'rent',
        'start_year': start_year, 'end_year': end_year or 0,
        'state': loc.state, 'city_type': loc.city_type, 'population_size': loc.population_size,
        'monthly_rent': float(est.get('monthly_rent', 0.0) or 0.0),
        'insurance_annual': float(est.get('insurance_annual', 0.0) or 0.0),
        'utilities_annual': float(est.get('utilities_annual', 0.0) or 0.0),
        'purchase_price': 0.0, 'down_payment_pct': 0.0, 'mortgage_rate_pct': 0.0,
        'maintenance_annual': 0.0, 'real_estate_tax_pct': 0.0, 'hoa_pct': 0.0,
    }


def _residency_schedule(base_state: str, transitions: list[tuple[int, str]]) -> list[dict[str, Any]]:
    """Build a full ``residency_schedule`` from an ordered list of
    ``(year, new_state)`` transitions (each state applies from ``year``
    onward, up to the next transition). Replaces any base-config schedule
    for this candidate run -- see ``core.state_for_year``.
    """
    if not transitions:
        return []
    transitions = sorted(transitions, key=lambda t: t[0])
    sched = [{'state': base_state, 'start_year': 1, 'end_year': transitions[0][0] - 1}]
    for i, (yr, st) in enumerate(transitions):
        end = transitions[i + 1][0] - 1 if i + 1 < len(transitions) else 9999
        sched.append({'state': st, 'start_year': yr, 'end_year': end})
    return sched


def _apply_candidate(c: dict[str, Any], cand: HousingCandidate) -> None:
    """Mutate engine config ``c`` in place to reflect ``cand`` -- rewrites
    ``next_housing_steps`` and ``residency_schedule`` only (§3.1/§3.2 of the
    design doc), plus the existing ``home_sale_yr`` field for move 1's sale
    of the current home. Intended as the ``mutate`` callback to
    ``planning_engines.run_scenario`` (deep-copies the base config first).
    """
    base_state = str(c.get('state', '') or '')
    c['home_sale_yr'] = cand.sale_year

    move1_start = cand.sale_year if cand.purchase_year is None else cand.purchase_year
    move1_end = (cand.sale_year_2 - 1) if cand.is_two_move else None
    steps = []
    transitions: list[tuple[int, str]] = [(move1_start, cand.location_1.state)]
    if cand.purchase_year is None:
        steps.append(_rent_step('opt_move1', cand.location_1, cand.sale_year, move1_end))
    else:
        move1_step = _purchase_step('opt_move1', cand.location_1, cand.purchase_year, move1_end)
        if cand.is_two_move:
            # Real second-sale pathway (design doc §8.2 P0): the engine sells
            # this step itself -- see home_sale.py's apply_next_housing_sale
            # -- instead of this module estimating move 2's gain/tax
            # out-of-loop. `move1_end` above is already `sale_year_2 - 1`, so
            # the step also stops accruing ongoing cash flow the year before.
            move1_step['sale_year'] = cand.sale_year_2
        steps.append(move1_step)

    if cand.is_two_move:
        move2_start = cand.sale_year_2 if cand.purchase_year_2 is None else cand.purchase_year_2
        transitions.append((move2_start, cand.location_2.state))
        if cand.purchase_year_2 is None:
            steps.append(_rent_step('opt_move2', cand.location_2, cand.sale_year_2, None))
        else:
            steps.append(_purchase_step('opt_move2', cand.location_2, cand.purchase_year_2, None))

    c['next_housing_steps'] = steps
    c['residency_schedule'] = _residency_schedule(base_state, transitions)


def _run_engine(c0: dict[str, Any], cand: HousingCandidate) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return _pe.run_scenario(c0, mutate=lambda cc: _apply_candidate(cc, cand))


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


# ---------------------------------------------------------------------------
# Narrowed/gradient search (§8.2 P2, §7) -- opt-in alternative to the full
# grid above. Pure integer coordinate/pattern search, decoupled from the
# engine so it's unit-testable against a synthetic score surface: callers
# supply a ``score_fn`` where higher is always better (the engine-scoring
# wrappers below flip the sign for the lifetime_cost objective) and that
# returns ``None`` for a point that must be skipped (e.g. filtered out by
# no_dual_ownership or family_presence) without spending eval budget on it.
# ---------------------------------------------------------------------------

def _coordinate_search_2d(
    x_bounds: tuple[int, int],
    y_bounds: tuple[int, int],
    score_fn: "Any",
    max_evals: int = 25,
) -> dict[tuple[int, int], float]:
    """Bounded hill-climb over the integer grid ``x_bounds x y_bounds``.
    Seeds with the four corners and the center, then repeatedly moves to
    the best-improving 4-neighbor of the current best point until none
    improves or ``max_evals`` is reached. Returns every point actually
    scored (``score_fn`` returned non-``None``), keyed by score -- callers
    that also need the ScoredCandidate objects build them alongside calling
    this. This is a local search: on a non-unimodal surface it can settle
    on a local rather than the global optimum (see module docstring).
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
    max_evals: int = 8,
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
# Constraint filters (§3.1.2 / §3.2.2)
# ---------------------------------------------------------------------------

def _location_timeline(base_state: str, cand: HousingCandidate) -> list[tuple[int, int, str, bool]]:
    """Ordered ``(start_year, end_year_inclusive, state, is_rental)`` legs
    covering the whole plan horizon for this candidate."""
    move1_start = cand.sale_year if cand.purchase_year is None else cand.purchase_year
    move1_is_rental = cand.purchase_year is None
    legs = [(1, move1_start - 1, base_state, False)]
    if cand.is_two_move:
        move2_start = cand.sale_year_2 if cand.purchase_year_2 is None else cand.purchase_year_2
        move2_is_rental = cand.purchase_year_2 is None
        legs.append((move1_start, move2_start - 1, cand.location_1.state, move1_is_rental))
        legs.append((move2_start, 9999, cand.location_2.state, move2_is_rental))
    else:
        legs.append((move1_start, 9999, cand.location_1.state, move1_is_rental))
    return legs


def family_presence_ok(base_state: str, cand: HousingCandidate, presence: FamilyPresence | None) -> tuple[bool, bool]:
    """Hard filter (§3.1.2/§3.2.2): returns ``(covered, via_rental)``.
    ``covered`` is False if any year in the presence window lacks an
    owned-or-rented residence in ``presence.region``. ``via_rental`` is True
    when a rent leg (rather than the current home or an owned purchase) is
    what satisfies coverage for at least one of those years.
    """
    if presence is None:
        return True, False
    legs = _location_timeline(base_state, cand)
    via_rental = False
    for year in range(presence.start_year, presence.end_year + 1):
        leg = next((l for l in legs if l[0] <= year <= l[1]), None)
        if leg is None or leg[2] != presence.region:
            return False, False
        if leg[3]:
            via_rental = True
    return True, via_rental


def sec121_exclusion_flag(purchase_year: int | None, sale_year: int) -> bool:
    """Informational-only two-of-five-year ownership/use flag (see module
    docstring): True means the exclusion would likely NOT survive the real
    IRS test, even though the engine's (and this module's) computed dollar
    figures still assume it applies in full. ``purchase_year is None`` means
    there is nothing to flag (nothing was purchased under this leg).
    """
    if purchase_year is None:
        return False
    return (sale_year - purchase_year) < 2


# ---------------------------------------------------------------------------
# Scoring (§4)
# ---------------------------------------------------------------------------

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
    home_sale.py's ``apply_next_housing_sale`` and this module's docstring),
    so -- unlike the out-of-loop estimate this replaced -- no post-hoc net
    worth/lifetime cost adjustment is needed for move 2.
    """
    net_worth = float(rows[-1].get('total_nw', 0.0) or 0.0) if rows else 0.0
    lifetime_cost = _lifetime_cost(rows)
    sec121_flags = [False]  # move 1 sells the current/original home -- ownership start isn't tracked, assume met
    if cand.is_two_move:
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


def select_anchors(ranked_move1: list[ScoredCandidate], anchor_count: int) -> list[HousingCandidate]:
    """Top ``anchor_count`` move-1 candidates (by Pass-1 score) that ended
    in ownership -- rent-indefinitely-forever outcomes are not extended."""
    owned = [s.candidate for s in ranked_move1 if s.candidate.purchase_year is not None]
    return owned[:max(0, anchor_count)]


# ---------------------------------------------------------------------------
# Narrowed search: engine-scoring wrappers (§8.2 P2)
# ---------------------------------------------------------------------------

def _pass1_value(sc: ScoredCandidate, pass1_objective: str) -> float:
    """Orient a ScoredCandidate's Pass-1 score so higher is always better,
    matching what ``_coordinate_search_2d``/``_coordinate_search_1d`` expect
    (``rank_candidates`` sorts lifetime_cost ascending instead)."""
    return -sc.lifetime_cost if pass1_objective == 'lifetime_cost' else sc.net_worth


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
    scores candidates as it searches (§8.2 P2 module docstring): per
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


# ---------------------------------------------------------------------------
# Orchestrator (§4)
# ---------------------------------------------------------------------------

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
) -> dict[str, Any]:
    if objective not in OBJECTIVES:
        raise ValueError(f"Unknown objective: {objective!r}")
    if search_mode not in SEARCH_MODES:
        raise ValueError(f"Unknown search_mode: {search_mode!r}")
    if not (2 <= len(locations) <= 4):
        raise ValueError("Provide 2-4 candidate locations.")

    base_state = str(c0.get('state', '') or '')
    pass1_objective = _pass1_objective(objective)
    narrowed = search_mode == 'narrowed'

    if narrowed:
        move1_scored = generate_move1_candidates_narrowed(
            c0, base_state, locations, move1_window, no_dual_ownership, family_presence, pass1_objective,
        )
    else:
        move1_scored = []
        for cand in generate_move1_candidates(locations, move1_window, no_dual_ownership):
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
        anchors = select_anchors(move1_scored, anchor_count)
        if narrowed:
            move2_scored = generate_move2_candidates_narrowed(
                c0, base_state, anchors, locations, move2_window, no_dual_ownership, family_presence,
                pass1_objective,
            )
        else:
            for cand in generate_move2_candidates(anchors, locations, move2_window, no_dual_ownership):
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

    return _format_output(final_ranked, objective, search_mode)


def _format_move(location: Location | None, sale_year: int | None, purchase_year: int | None,
                  sec121_lost: bool) -> dict[str, Any] | None:
    if location is None:
        return None
    return {
        'sale_year': sale_year,
        'purchase_year': purchase_year,
        'rent_indefinitely': purchase_year is None,
        'location': {
            'state': location.state,
            'city_type': location.city_type,
            'population_size': location.population_size,
        },
        'sec121_exclusion_lost': sec121_lost,
    }


def _format_candidate(sc: ScoredCandidate, objective: str) -> dict[str, Any]:
    cand = sc.candidate
    moves = [_format_move(cand.location_1, cand.sale_year, cand.purchase_year,
                           sc.sec121_exclusion_lost[0] if sc.sec121_exclusion_lost else False)]
    if cand.is_two_move:
        moves.append(_format_move(cand.location_2, cand.sale_year_2, cand.purchase_year_2,
                                   sc.sec121_exclusion_lost[1] if len(sc.sec121_exclusion_lost) > 1 else False))
    return {
        'moves': moves,
        'net_worth': sc.net_worth,
        'lifetime_cost': sc.lifetime_cost,
        'mc_success_rate': sc.mc_success_rate,
        'objective_value': {
            'net_worth': sc.net_worth,
            'lifetime_cost': sc.lifetime_cost,
            'mc_success_rate': sc.mc_success_rate,
        }[objective],
        'family_presence_via_rental': sc.family_presence_via_rental,
    }


def _format_output(ranked: list[ScoredCandidate], objective: str, search_mode: str = 'full') -> dict[str, Any]:
    formatted = [_format_candidate(sc, objective) for sc in ranked]
    return {
        'objective': objective,
        'search_mode': search_mode,
        'recommendation': formatted[0] if formatted else None,
        'alternatives': formatted[1:11],
        'candidates_evaluated': len(ranked),
    }


# ---------------------------------------------------------------------------
# HTTP request adapter (see src/server/plan_routes.py POST /api/housing/optimize)
# ---------------------------------------------------------------------------

def _parse_location(raw: dict[str, Any]) -> Location:
    price_range = raw.get('target_purchase_price_range')
    parsed_range = None
    if isinstance(price_range, (list, tuple)) and len(price_range) == 2:
        parsed_range = (float(price_range[0]), float(price_range[1]))
    return Location(
        state=str(raw.get('state', '') or '').strip(),
        city_type=str(raw.get('city_type', 'suburban') or 'suburban').strip().lower(),
        population_size=int(raw.get('population_size', 20000) or 20000),
        target_purchase_price_range=parsed_range,
    )


def _parse_search_window(raw: dict[str, Any]) -> SearchWindow:
    return SearchWindow(
        earliest_sale_year=int(raw.get('earliest_sale_year', 0) or 0),
        latest_sale_year=int(raw.get('latest_sale_year', 0) or 0),
        earliest_purchase_year=int(raw.get('earliest_purchase_year', 0) or 0),
        latest_purchase_year=int(raw.get('latest_purchase_year', 0) or 0),
    )


def _parse_move2_window(raw: dict[str, Any]) -> Move2Window:
    return Move2Window(
        latest_sale_year_2=int(raw.get('latest_sale_year_2', 0) or 0),
        latest_purchase_year_2=int(raw.get('latest_purchase_year_2', 0) or 0),
    )


def _parse_family_presence(raw: dict[str, Any]) -> FamilyPresence:
    return FamilyPresence(
        region=str(raw.get('region', '') or '').strip(),
        start_year=int(raw.get('start_year', 0) or 0),
        end_year=int(raw.get('end_year', 0) or 0),
    )


def optimize_housing_from_request(c0: dict[str, Any], body: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Parse an ``/api/housing/optimize`` request body, run the optimizer
    against the current plan config ``c0``, and return a ``(payload, status)``
    pair ready for ``jsonify``. Never mutates ``c0`` (every candidate runs on
    a deep copy via ``planning_engines.run_scenario``).
    """
    try:
        raw_locations = body.get('locations') or []
        if not isinstance(raw_locations, list) or not (2 <= len(raw_locations) <= 4):
            return {'success': False, 'error': 'Provide 2-4 candidate locations.'}, 400
        locations = [_parse_location(x) for x in raw_locations]
        if any(not loc.state for loc in locations):
            return {'success': False, 'error': 'Every candidate location needs a state.'}, 400

        move1_window = _parse_search_window(body.get('move1_window') or {})
        move2_raw = body.get('move2_window')
        move2_window = _parse_move2_window(move2_raw) if move2_raw else None

        family_presence_raw = body.get('family_presence')
        family_presence = _parse_family_presence(family_presence_raw) if family_presence_raw else None

        objective = str(body.get('objective', 'net_worth') or 'net_worth')
        if objective not in OBJECTIVES:
            return {'success': False, 'error': f"Unknown objective: {objective!r}"}, 400

        search_mode = str(body.get('search_mode', 'full') or 'full')
        if search_mode not in SEARCH_MODES:
            return {'success': False, 'error': f"Unknown search_mode: {search_mode!r}"}, 400

        result = optimize_housing(
            c0,
            locations=locations,
            move1_window=move1_window,
            move2_window=move2_window,
            anchor_count=int(body.get('anchor_count', 5) or 5),
            no_dual_ownership=bool(body.get('no_dual_ownership', True)),
            family_presence=family_presence,
            objective=objective,
            search_mode=search_mode,
        )
        result['success'] = True
        result['schema'] = 'housing_optimize_v1'
        return result, 200
    except ValueError as exc:
        return {'success': False, 'error': str(exc)}, 400
    except Exception as exc:  # pragma: no cover - defensive
        return {'success': False, 'error': str(exc)}, 500
