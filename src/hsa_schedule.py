"""HSA drawdown schedule helpers.

The household's decision is that the HSA must be fully consumed before the
second death: a spouse inherits an HSA tax-free, but any later beneficiary owes
ordinary income tax on the whole balance in the single year of death. "Before
second death" is not a date, so it has to be resolved to one -- that is what
`resolve_consume_by_year` does.

The failure modes around that date are asymmetric, and every fallback here is
chosen accordingly:

* Too early (plan to the median, household lives longer) -- the tax-free bucket
  is gone in the survivor years when it is scarcest, and every later dollar is
  taxed at compressed Single-filer rates. Expensive and unbounded.
* Too late (plan to a high percentile, death comes sooner) -- a residual is left
  and pays the terminal cliff. Bounded at residual x heir rate.

So the default is the conservative end (`second_death_p90`), and no fallback in
this module ever resolves earlier than that default would.
"""
from __future__ import annotations

import re
import warnings
from typing import Any, Mapping, Optional, Sequence

DEFAULT_CONSUME_BY = 'second_death_p90'

_EXPLICIT_YEAR_RE = re.compile(r'^\d{4}$')
_PERCENTILE_RE = re.compile(r'^second_death_p(\d{1,3})$')


def resolve_consume_by_year(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> int:
    """Resolve `c['hsa_consume_by']` to a single calendar year in the horizon.

    Accepted forms:

    * ``second_death_pNN`` (NN in 1..99) -- the year by which the second death
      has occurred with probability NN%, taken off the engine's own mortality
      table (see `_second_death_year_at_percentile`).
    * an explicit four-digit year.

    Anything else is a configuration error. It is **not** silently accepted:
    the function warns loudly and then falls back to `DEFAULT_CONSUME_BY`, the
    conservative end. Falling back rather than raising is deliberate -- a
    deadline is a backstop constraint, and a hard failure here would take down
    a whole projection over one mistyped cell -- but the fallback is never
    earlier than the default, because early is the unbounded failure.

    A missing/blank value is treated as unset, not malformed, and takes the
    default silently.

    The result is clamped to `plan_start`..`plan_end` (falling back to the
    first/last year in `rows` when the config does not carry them), because a
    schedule that indexes projection rows cannot use a year outside them.
    """
    raw = c.get('hsa_consume_by')
    spec = '' if raw is None else str(raw).strip()
    plan_start, plan_end = _horizon(c, rows)

    if spec:
        year = _resolve_spec(spec, c, plan_start, plan_end)
        if year is None:
            warnings.warn(
                f"hsa_consume_by={raw!r} is not a recognized deadline; expected "
                f"'second_death_pNN' with NN in 1..99, or a four-digit year. "
                f"Falling back to {DEFAULT_CONSUME_BY!r}. This is a configuration "
                f"error -- fix the input rather than relying on the fallback.",
                UserWarning, stacklevel=2)
            year = _resolve_spec(DEFAULT_CONSUME_BY, c, plan_start, plan_end)
    else:
        year = _resolve_spec(DEFAULT_CONSUME_BY, c, plan_start, plan_end)

    return _clamp(int(year), plan_start, plan_end)


def _resolve_spec(spec: str, c: Mapping[str, Any],
                  plan_start: Optional[int], plan_end: Optional[int]) -> Optional[int]:
    """Resolve one deadline spec to an unclamped year, or None if malformed."""
    if _EXPLICIT_YEAR_RE.match(spec):
        return int(spec)

    match = _PERCENTILE_RE.match(spec)
    if not match:
        return None
    percentile = int(match.group(1))
    if not 1 <= percentile <= 99:
        return None

    year = _second_death_year_at_percentile(c, percentile / 100.0, plan_start)
    if year is not None:
        return year
    # No distribution available (no members, no birth years, or no plan_start
    # to anchor ages against). Fall back to the end of the horizon -- the
    # latest year the schedule can express -- never to something earlier.
    if plan_end is not None:
        return plan_end
    raise ValueError(
        f"Cannot resolve hsa_consume_by={spec!r}: the config carries neither a "
        f"mortality distribution (members with dob_yr) nor a plan horizon.")


def _second_death_year_at_percentile(c: Mapping[str, Any], percentile: float,
                                     plan_start: Optional[int]) -> Optional[int]:
    """First year in which P(both members have died) >= `percentile`.

    Built from the same table and the same per-member calibration the engine's
    own death-year sampler uses (`planning_engines.sample_death_year`), so this
    is not a second mortality model -- it is the closed-form read of the one
    that already exists. Members are combined as independent lives, which is
    also what the sampler does (`sample_household_death_years` draws each member
    with its own trial).

    Returns None when the config cannot express a distribution.
    """
    members = c.get('members') or []
    if not members or plan_start is None:
        return None

    cdfs = []
    for idx, member in enumerate(members):
        # h = male column, w = female column, by the registry convention the
        # sampler already follows.
        cdf = _member_death_cdf(member, 0 if idx == 0 else 1, plan_start)
        if cdf is None:
            return None
        cdfs.append(cdf)

    last_year = max(max(cdf) for cdf in cdfs)
    for year in range(plan_start, last_year + 1):
        both_dead = 1.0
        for cdf in cdfs:
            both_dead *= _cdf_at(cdf, year)
        if both_dead >= percentile:
            return year
    return last_year


def _member_death_cdf(member: Mapping[str, Any], sex_idx: int,
                      plan_start: int) -> Optional[dict]:
    """{calendar year: P(this member has died by the end of it)}."""
    from .planning_engines import _age_shift_for_member, _mortality_qx

    dob = member.get('dob_yr')
    if dob is None:
        return None
    dob = int(dob)
    shift = _age_shift_for_member(member, sex_idx)

    age = max(18, plan_start - dob)
    survival = 1.0
    cdf = {}
    while age < 119:
        survival *= (1.0 - _mortality_qx(age - shift, sex_idx))
        cdf[dob + age] = 1.0 - survival
        age += 1
    cdf[dob + 119] = 1.0  # the sampler's own terminal age
    return cdf


def _cdf_at(cdf: Mapping[int, float], year: int) -> float:
    if year in cdf:
        return cdf[year]
    return 1.0 if year > max(cdf) else 0.0


def _horizon(c: Mapping[str, Any],
             rows: Sequence[Mapping[str, Any]]) -> tuple[Optional[int], Optional[int]]:
    """(plan_start, plan_end), falling back to the span of `rows`."""
    start = c.get('plan_start')
    end = c.get('plan_end')
    row_years = [int(r['year']) for r in (rows or [])
                 if isinstance(r, Mapping) and r.get('year') is not None]
    if start is None and row_years:
        start = min(row_years)
    if end is None and row_years:
        end = max(row_years)
    return (int(start) if start is not None else None,
            int(end) if end is not None else None)


def _clamp(year: int, plan_start: Optional[int], plan_end: Optional[int]) -> int:
    if plan_end is not None:
        year = min(year, plan_end)
    if plan_start is not None:
        year = max(year, plan_start)
    return year


# --- Per-year scoring -------------------------------------------------------
#
# `score_year` answers the only question the consume-by constraint leaves open:
# given that the balance must reach zero by the deadline, WHICH years should the
# withdrawals land in? It returns the present-valued benefit, in dollars, of
# drawing `amount` in that row's year, so a search can rank candidate years
# against each other on one comparable scale.

# Section 1.3 of the design spec: after the first death the survivor files
# Single at roughly half the MFJ bracket widths. `effective_marginal_rate` is a
# POINT estimate at the current margin (deterministic_engine's `_EMR_BUMP`
# perturbation), so it already carries the level effect of those compressed
# brackets. What it cannot carry is the CONVEXITY: a whole block of `amount`
# dollars traverses more bracket boundaries at half-width, so the average rate
# across the displaced block sits further above the marginal rate for a Single
# filer than for an MFJ one. This premium prices that gap, and nothing else --
# it is deliberately small, because the level effect is already in the rate and
# double-counting it would let a cheap survivor year outrank a genuinely
# expensive joint one.
_SINGLE_BRACKET_COMPRESSION_PREMIUM = 1.10

# Filing statuses whose brackets are compressed relative to MFJ, upper-cased to
# match `_filing`. HOH belongs here with Single: `survivor_filing_status` is
# `Single | HOH` (reference_data/schema.csv) and the engine writes that value
# straight into `row['filing']`, so leaving HOH out would silently switch the
# survivor premium off for every plan that configures an HOH survivor -- which
# is the whole economic rationale of the term.
_COMPRESSED_FILINGS = frozenset({'SINGLE', 'MFS', 'HOH'})

# Medicare enrollees the IRMAA surcharge is charged to, by filing status. The
# surcharge is per beneficiary, which is why an MFJ crossing costs twice a
# Single one at the same tier (`core.irmaa_surcharge`'s `n_people`).
_IRMAA_ENROLLEES = {'MFJ': 2}


def score_year(c: Mapping[str, Any], row: Mapping[str, Any], amount: Any) -> float:
    """Present-valued benefit, in dollars, of drawing `amount` in `row`'s year.

    Four terms, all in the same units so they can simply be added:

    * **Displacement** -- the tax avoided on the alternative dollar the HSA
      draw displaces, at that year's marginal rate and filing status. This is
      the term that makes an expensive year beat a cheap one.
    * **Cliff** -- the IRMAA tier crossing avoided. A step, not a slope: worth
      the full annual surcharge step when the draw actually keeps the household
      under the next threshold, and very little when the threshold is far away.
    * **Carry cost / discount** -- later years are worth less, discounted at the
      shared `roth_tax_discount_rate` (see `_roth_discount_rate`). The HSA
      optimizer deliberately does NOT get its own rate: section 3.1 of the
      design spec requires HSA draws and Roth conversions to be scored jointly,
      and two discount rates would make that joint answer depend on which
      optimizer ran first.
    * **Residual risk** -- NOT priced here, on purpose. The expected lump-sum
      tax on a balance still held at death is a function of the balance the
      schedule leaves standing, not of one candidate (year, amount) pair, so it
      cannot be evaluated from this signature without being double-counted
      across every candidate year. It belongs to the schedule search that owns
      the running balance. Nothing here substitutes for it: the discount factor
      also pulls draws earlier, but it prices impatience, not mortality, and
      section 3.1 is explicit that the residual term is load-bearing rather
      than a refinement.

    `row` is a projection row. `effective_marginal_rate`, `irmaa_tier`,
    `filing` and `year` are real fields the deterministic engine sets.
    ``row['irmaa_headroom']`` is **optional** and is not a field any projection
    row carries today -- IRMAA headroom is computed at candidate-scoring time
    (the Roth optimizer does exactly that inline). When it is absent the cliff
    term contributes nothing, which is the only honest reading of "no cliff
    information available": assuming a number would bias every real row toward
    either always-crossing or never-crossing. A malformed value (non-numeric,
    NaN, negative) is read the same way absence is, for the same reason.

    **Known gap, owned by the caller (Task 10's schedule search).** The
    carry-cost/discount term only discounts -- it does not credit the tax-free
    compounding a dollar left in the HSA would earn by NOT being drawn this
    year. So scoring one fixed `amount` across several years is not a
    like-for-like comparison: the discount factor alone makes early years
    dominate late survivor years even where the late year has the better tax
    characteristics, because the deferred dollar's growth is never counted.
    This signature is only coherent if the caller passes each candidate year's
    actual grown draw amount rather than a constant nominal one. Scoring equal
    nominal amounts across candidate years will systematically front-load the
    schedule and fail the H3.5(a) rejection test (the optimizer must beat
    `smooth_window` specifically by weighting survivor years). Measured: a
    joint 2028 year at 22% scores ~1939.65 against a survivor 2048 year at 32%
    plus the compression premium scoring ~880.75 for the SAME fixed amount --
    a 2.2x gap in the wrong direction, and it only closes once realistic
    compounding is applied to the later year's dollar.

    Every field is read defensively. A scoring function that raised on a
    malformed row would take down a whole projection over one diagnostic.
    """
    amount = _as_float(amount, 0.0)
    if amount <= 0.0:
        return 0.0

    displacement = amount * _displaced_dollar_rate(row)
    cliff = _irmaa_cliff_value(row, amount)
    return (displacement + cliff) * _pv_factor(c, row)


def _displaced_dollar_rate(row: Mapping[str, Any]) -> float:
    """Effective rate on the dollar the draw displaces, incl. the Single premium."""
    rate = _as_float(row.get('effective_marginal_rate'), 0.0)
    # Clamped, not trusted: the field is a finite-difference diagnostic and the
    # engine itself sets it to None when the difference blows up.
    rate = min(1.0, max(0.0, rate))
    if _filing(row) in _COMPRESSED_FILINGS:
        rate *= _SINGLE_BRACKET_COMPRESSION_PREMIUM
    return rate


def _irmaa_cliff_value(row: Mapping[str, Any], amount: float) -> float:
    """Value of the IRMAA tier crossing this draw avoids, in dollars.

    `irmaa_headroom` is the room left under the next tier's threshold. If the
    displaced dollars would have run past it, the draw buys the whole surcharge
    step; if the threshold is far off, it buys almost nothing. The quadratic
    taper below the crossing point is not a probability -- it exists so a
    search sees a gradient toward the cliff instead of a flat plateau, and it
    decays fast enough (headroom 5x the draw is worth 4% of the step) that a
    year nowhere near a threshold cannot win on this term.

    A missing, non-numeric, NaN or negative `irmaa_headroom` carries no cliff
    information and contributes nothing, the same as absence. Only a genuine
    0.0 means "at the edge" and buys the full step.
    """
    # Absent, unparseable and negative headrooms are all the same statement --
    # "no cliff information available" -- and all degrade to no cliff term. A
    # malformed value must NOT land on 0.0, because 0.0 is a real signal here
    # ("no room left, the next dollar crosses") that pays out the whole step.
    headroom = _as_float(row.get('irmaa_headroom'), -1.0)
    if headroom < 0.0:
        return 0.0

    step = _next_tier_surcharge_step(row)
    if step <= 0.0:
        return 0.0
    if amount >= headroom:
        return step
    return step * (amount / headroom) ** 2


def _next_tier_surcharge_step(row: Mapping[str, Any]) -> float:
    """Annual household cost of moving from this row's IRMAA tier to the next.

    Read off the same `IRMAA_TIERS_BASE_YEAR` table `core.irmaa_surcharge`
    uses, at this row's filing status, so this is not a second IRMAA model.
    Zero at the top tier -- there is no next tier to cross.
    """
    filing = _filing(row)
    tiers = _irmaa_tiers_for(filing)
    if not tiers:
        return 0.0

    tier = int(_as_float(row.get('irmaa_tier'), 0.0))
    tier = max(0, min(tier, len(tiers)))
    if tier >= len(tiers):
        return 0.0

    enrollees = _IRMAA_ENROLLEES.get(filing, 1)
    return max(0.0, (_tier_annual(tiers, tier + 1) - _tier_annual(tiers, tier)) * enrollees)


def _irmaa_tiers_for(filing: str) -> Sequence[Sequence[float]]:
    """`IRMAA_TIERS_BASE_YEAR` rows for an upper-cased filing status.

    The table's keys are mixed case ('Single', 'MFJ', 'MFS', 'HOH') while
    `_filing` normalizes to upper case, so a direct `.get()` misses 'Single'
    and quietly reads whatever the fallback names instead. Matching on the
    table's own keys keeps the two conventions from having to agree, and an
    unrecognized status still falls back to MFJ -- the conservative direction,
    since MFJ is what an unlabeled row already defaults to.
    """
    try:
        from .taxes import IRMAA_TIERS_BASE_YEAR
    except ImportError:  # pragma: no cover - direct execution fallback
        from src.taxes import IRMAA_TIERS_BASE_YEAR
    for key, tiers in IRMAA_TIERS_BASE_YEAR.items():
        if key.upper() == filing:
            return tiers
    return IRMAA_TIERS_BASE_YEAR.get('MFJ') or []


def _tier_annual(tiers: Sequence[Sequence[float]], tier: int) -> float:
    """Per-beneficiary annual Part B + Part D surcharge at `tier` (0 = none).

    Tier numbering follows `core.irmaa_tier`: 0 is below the lowest threshold,
    and tier k is the k-th entry of the table.
    """
    if tier <= 0:
        return 0.0
    part_b, part_d = tiers[tier - 1][1], tiers[tier - 1][2]
    return (float(part_b) + float(part_d)) * 12.0


def _pv_factor(c: Mapping[str, Any], row: Mapping[str, Any]) -> float:
    """Discount from this row's year back to `plan_start`.

    No `plan_start` (or no `year`) means no anchor to discount against, so this
    degrades to 1.0 rather than raising. That is safe for ranking: with no
    anchor the factor is the same constant for every candidate year, so it
    scales scores without reordering them.
    """
    plan_start = row_year = None
    try:
        if c.get('plan_start') is not None:
            plan_start = int(c['plan_start'])
        if row.get('year') is not None:
            row_year = int(row['year'])
    except (TypeError, ValueError):
        return 1.0
    if plan_start is None or row_year is None:
        return 1.0

    from .planning_engines import _roth_discount_rate
    rate = _roth_discount_rate(dict(c))
    if rate <= -1.0:
        return 1.0
    return (1.0 + rate) ** -max(0, row_year - plan_start)


def _filing(row: Mapping[str, Any]) -> str:
    """This row's filing status, normalized. Missing means the joint case.

    Defaulting to MFJ is the conservative direction here: it declines to award
    the survivor premium and declines to halve the IRMAA enrollee count, so an
    unlabeled row can never be flattered into looking like a survivor year.

    Upper-cased, so every comparison against it must be too -- see
    `_irmaa_tiers_for` for the table whose keys are not.
    """
    raw = row.get('filing')
    return ('' if raw is None else str(raw).strip().upper()) or 'MFJ'


def _as_float(value: Any, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out or out in (float('inf'), float('-inf')):  # NaN / inf
        return default
    return out


def allocate_surplus(c: Mapping[str, Any], row: Mapping[str, Any], surplus: Any) -> dict:
    """Waterfall a year's HSA surplus across three priorities, in order.

    Consuming by the deadline (design spec S2) can produce more cash than the
    plan needs to spend that year. This decides where it goes:

    1. **Spending** -- fund whatever the year still needs first. This is not
       optional; a schedule that leaves a real spending gap while "optimizing"
       is not a schedule.
    2. **Roth conversion tax** -- paying conversion tax from outside the IRA is
       what makes a conversion efficient, and a tax-free bucket you have to
       drain anyway is the cheapest possible source for it. `row` supplies
       `conversion_tax_capacity`: how much MORE conversion tax this year could
       usefully absorb, computed by whoever is running the schedule search --
       this function only allocates against it, it does not derive it.
    3. **Taxable** -- whatever is left spills to a taxable account. Always a
       safe landing; never a defect if this is nonzero.

    Every priority is filled in full before the next opens, and the three
    outputs sum to exactly `surplus` (short of it only if `surplus` itself is
    negative, which is clamped to zero). This is deliberately a pure
    allocation with no tax logic of its own -- `row['conversion_tax_capacity']`
    is the only place a conversion-sizing decision could sneak in, and Task 9's
    own guardrail test pins that it can't (see
    `test_surplus_never_increases_the_conversion_itself`): this function
    changes how conversion tax gets FUNDED, never how much conversion is worth
    doing in the first place.
    """
    surplus = max(0.0, _as_float(surplus, 0.0))
    spending_need = max(0.0, _as_float(row.get('spending_need'), 0.0))
    conversion_tax_capacity = max(0.0, _as_float(row.get('conversion_tax_capacity'), 0.0))

    to_spending = min(surplus, spending_need)
    remaining = surplus - to_spending
    to_conversion_tax = min(remaining, conversion_tax_capacity)
    remaining -= to_conversion_tax
    to_taxable = remaining

    return {
        'to_spending': to_spending,
        'to_conversion_tax': to_conversion_tax,
        'to_taxable': to_taxable,
    }


def joint_headroom_used(c: Mapping[str, Any], row: Mapping[str, Any],
                        hsa_draw: Any, conversion: Any) -> float:
    """Bracket headroom the pair {HSA draw, Roth conversion} claims TOGETHER.

    Section 3.1 of the design spec names this the most likely correctness bug
    in the whole feature. An HSA draw funds spending that would otherwise have
    come from a taxable IRA withdrawal, so relative to that baseline it lowers
    AGI and frees `hsa_draw` of ADDITIONAL bracket room beyond `bracket_room`
    (`row['bracket_room']`, the room `plan_roth_conversion` already computes as
    `top_target - pre_agi` -- see `conv_bracket_room` on a real
    `ConversionPlan`). A conversion then consumes some of that combined,
    larger pool. Scored separately -- the draw credited its full freeing
    effect, the conversion sized against `bracket_room` alone -- both claims
    can be added up to `bracket_room + hsa_draw` even though they draw from
    the SAME pool. That double-counted sum is this function's upper bound, not
    its answer: `joint_headroom_used` returns the corrected, non-doubled
    figure a schedule search should actually charge against the pool.

    Two easy cases pin the shape: with no conversion at all, nothing is
    claiming any room, so the freed headroom is real but unused --
    `joint_headroom_used` is 0, not `bracket_room`. With no HSA draw, there is
    nothing to correct for -- it collapses to whatever the conversion alone
    claims, `min(conversion, bracket_room)`.

    Between those, the fraction of `hsa_draw` charged as used scales with how
    much of `bracket_room` the conversion itself fills: a conversion using a
    small sliver of the base room should not get credited with claiming a
    large sliver of the freed room too, and a conversion that saturates the
    base room is treated as reaching fully into the freed room as well, on the
    conservative assumption that a real optimizer would keep pushing into it
    rather than stopping exactly at the old ceiling. This is a first-pass
    estimate, not a derived tax identity -- there is no closed form for "how
    much of a displaced dollar and a converted dollar overlap" the way there
    is for, say, a discount factor. It is deliberately the conservative
    direction: it biases toward MORE headroom counted as used, not less,
    because the double-count risk this function exists to prevent is a
    schedule search thinking it got headroom for free.

    Whoever wires this into a real search (Task 10) should treat it as
    provisional and revisit it if candidate schedules cluster suspiciously
    close to IRMAA or bracket thresholds -- the same caution `score_year`'s
    docstring gives its own compounding gap.
    """
    bracket_room = max(0.0, _as_float(row.get('bracket_room'), 0.0))
    hsa_draw = max(0.0, _as_float(hsa_draw, 0.0))
    conversion = max(0.0, _as_float(conversion, 0.0))

    if hsa_draw <= 0.0 or conversion <= 0.0:
        return min(conversion, bracket_room)

    if bracket_room <= 0.0:
        # No base room to speak of -- the only pool that exists is what the
        # draw freed, so usage is simply how much of THAT the conversion
        # reaches. `min(conversion, bracket_room)` would wrongly floor this
        # at zero, discarding the conversion's real claim on the freed room.
        return min(conversion, hsa_draw)

    fraction = min(1.0, conversion / bracket_room)
    return min(conversion, bracket_room) + hsa_draw * fraction
