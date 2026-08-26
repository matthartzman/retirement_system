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

**Wiring status (2026-08-19):** `resolve_year_amount`'s precedence ladder
(override > locked > optimizer > mode) is live end-to-end -- a user-entered
`override_amount` in `client_hsa_schedule.csv` reaches the withdrawal cascade
via `planning_engines.withdraw_hsa_window`'s `'optimize'` branch. The search
itself, `rerun_optimizer`/`build_schedule` below, is NOT called anywhere in
the projection pipeline: it needs full per-year projection rows for tax
context (`score_year`'s `row` argument), which only exist after a projection
runs -- and that projection is exactly what would consume the schedule this
function produces. Wiring it needs a real two-pass sequence (a baseline run
for context, then `build_schedule`/`rerun_optimizer`, then the real run using
the result) and is deliberately left as separate future work, not attempted
alongside the override plumbing.

**Default schedule (2026-08-20):** `generate_default_schedule` below is
NOT that search algorithm -- it is a static, level-draw placeholder,
written once by `workbook_builder._ensure_hsa_default_schedule` the first
time a build runs in `optimize` mode with no schedule file yet, so the mode
has something sane to fall back on before the real search exists. It never
overwrites an existing file, so a household's own entries -- or, eventually,
a real optimizer run -- always take precedence the moment they exist.
"""
from __future__ import annotations

import re
import warnings
from typing import Any, Mapping, MutableMapping, Optional, Sequence, Tuple

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


def generate_default_schedule(c: Mapping[str, Any]) -> list:
    """A static, level-draw placeholder schedule for `optimize` mode when no
    real schedule exists yet.

    Deliberately NOT the search algorithm (`build_schedule`/`rerun_optimizer`
    above) -- that needs full per-year projection rows this call site does not
    have (see the module docstring's "Wiring status"). This produces one flat
    number: divide the HSA's current balance evenly across every year from
    `plan_start` through `resolve_consume_by_year`'s own deadline. Every year
    gets the exact same `optimizer_amount`.

    That flatness is the point, not a simplification of it. The bug this
    function exists to fix (2026-08-20) was a PER-YEAR-recalculated fallback
    (`total remaining / years remaining`, re-evaluated fresh each year against
    the household's own `plan_end`) that is mathematically guaranteed to draw
    100% of whatever is left in the account's final year, however far that
    balance had drifted from the original plan by then -- `years_remaining`
    hits exactly 1 at the horizon and the formula collapses to "draw
    everything." A schedule computed ONCE, up front, against the shorter
    mortality-percentile deadline (not the household's full life horizon,
    which can run decades past when a single survivor should have drained the
    account) cannot reproduce that cliff: the shares are fixed the moment
    this function returns, so no later year's draw depends on how much of the
    balance is left by the time that year arrives.

    This is a placeholder, not the optimizer's real answer -- it does not
    weight survivor years, does not account for tax bracket headroom, and
    does not react to bad market years. It exists so `optimize` mode has
    something sane to fall back on the moment a household turns it on, before
    the real search algorithm is built. A real optimizer run, or a
    household's own manual entries, both take precedence over this the
    instant they exist (`resolve_year_amount`'s precedence ladder: override >
    locked > optimizer > mode -- this function only ever populates
    `optimizer_amount`, the lowest tier a real entry can still override).

    Returns `[]` (write nothing) when there is no HSA balance to schedule, or
    the resolved deadline does not leave at least one year on or after
    `plan_start` -- there is nothing sensible to divide in either case.
    """
    ids = list(c.get('hsa_ids', []) or [])
    balances = c.get('balances', {}) or {}
    total = sum(max(0.0, _as_float(balances.get(aid), 0.0)) for aid in ids)
    if total <= 0.0:
        return []

    plan_start = c.get('plan_start')
    if plan_start is None:
        return []
    plan_start = int(plan_start)

    # No projection rows exist yet at this call site (this runs once, right
    # after parse_client, before the projection loop starts) -- resolve_consume_by_year
    # falls back to c['plan_start']/c['plan_end'] when rows is empty, which is
    # exactly what we want here.
    deadline = resolve_consume_by_year(c, [])
    years = list(range(plan_start, deadline + 1))
    if not years:
        return []

    level = round(total / len(years), 2)
    return [
        {
            'year': y,
            'optimizer_amount': level,
            'override_amount': None,
            'locked': False,
            'note': 'Default level draw -- placeholder until the schedule search is built.',
        }
        for y in years
    ]


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


# `_as_float`'s sentinel for "this cell is absent". Typed `Any` so passing it as
# the `default` of a `-> float` helper stays type-honest at the call site; the
# result is then presence-checked with `is not None`, never with truthiness --
# a 0.0 override is a real, deliberate instruction to draw nothing.
_ABSENT: Any = None

_TRUTHY_CELLS = ('TRUE', 'YES', '1')


def _as_bool(value: Any) -> bool:
    """Parse a boolean that may be a real bool or a CSV cell's text.

    `client_hsa_schedule.csv` round-trips through a CSV, so `locked` reaches
    this module as a string far more often than as a Python `bool`. The naive
    `if row.get('locked'):` is actively dangerous here: the string `"False"` is
    truthy, so an explicitly *unlocked* row would silently read as locked and
    freeze a year the user never pinned.

    Mirrors the `_b` idiom in `src/data_io.py` rather than importing it -- that
    is a private name in an unrelated module, and this file's convention is
    small local helpers (see `_as_float`).

    Truthy: `True`, `"True"` / `"TRUE"` / `"true"` (any case or surrounding
    whitespace), `"1"`, `"yes"`. Everything else -- `False`, `"False"`, `"0"`,
    `"no"`, `""`, whitespace, `None`, an absent key -- is falsy.
    """
    return str(value).strip().upper() in _TRUTHY_CELLS


def resolve_year_amount(row: Mapping[str, Any]) -> Tuple[float, str]:
    """Resolve one schedule year to `(amount, source)` -- the whole precedence ladder.

    The ladder is **override > locked > optimizer > mode**, and this is the one
    place it is decided. Do not re-derive any tier of it at a call site: a
    precedence bug is silent, and the user finds out only when an edit they
    made vanishes.

    The four sources, and exactly what `amount` means for each:

    * ``'override'`` -- the user typed a number into `override_amount`. The
      optimizer never writes that column, which is what makes a re-run safe:
      there is no path by which recomputing the schedule can overwrite the
      user's intent. Wins unconditionally, including over `locked`, and
      including when the optimizer never produced a value for this year at all.
      `amount` is the user's number.
    * ``'locked'`` -- no override, but the user pinned the optimizer's own value
      for this year. `amount` is that pinned `optimizer_amount`; later re-runs
      must plan *around* this year rather than through it.
    * ``'optimizer'`` -- the schedule search's answer for this year, unpinned
      and unedited. `amount` is `optimizer_amount`.
    * ``'mode'`` -- **there is no schedule-layer answer for this year.** The
      search did not cover it, or the row does not exist. `amount` is `0.0`,
      and it is a placeholder, *not* a withdrawal of zero: callers must ignore
      it entirely and take the year's figure from the `hsa_withdrawal_mode`
      path instead (`withdraw_hsa_window`). This function has no access to `c`
      or to live engine state and cannot compute that value itself. Reading the
      `0.0` as a real instruction would silently suppress the mode-based
      withdrawal for that year.

    `locked` with no `optimizer_amount` behind it also resolves to ``'mode'``.
    "Locked" means *pin the value the optimizer wrote*; with nothing written
    there is nothing to pin, and inventing a 0.0 to freeze would be a stronger
    claim than the data supports -- it would suppress the year's withdrawal on
    the strength of a checkbox alone. The user can still express "draw nothing
    this year" unambiguously, by entering a 0 override.

    Zero is real at every tier: `override_amount` of `0.0` (or the string
    `"0.0"`) is an override, and `optimizer_amount` of `0.0` is a schedule
    value. Absence is only ever `None`, a blank cell, or unparseable text.

    Pure: reads nothing but `row`, and mutates nothing.
    """
    row = row or {}

    # Presence is `is not None` on the parsed value, never truthiness --
    # `if row.get('override_amount'):` would discard a deliberate 0 override.
    override = _as_float(row.get('override_amount'), _ABSENT)
    if override is not None:
        return override, 'override'

    optimizer = _as_float(row.get('optimizer_amount'), _ABSENT)
    if optimizer is None:
        return 0.0, 'mode'

    if _as_bool(row.get('locked')):
        return optimizer, 'locked'

    return optimizer, 'optimizer'


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


# --- Schedule search --------------------------------------------------------
#
# `score_year` ranks one (year, amount) pair. This section decides the whole
# schedule: given that the balance must reach zero by `resolve_consume_by_year`,
# which years do the draws land in, and how much lands in each.
#
# Two terms fight each other here, and the fight is the point:
#
# * The per-year value (`score_year`) plus tax-free compounding pulls dollars
#   LATER -- a dollar left in the HSA grows untaxed, and survivor years price
#   the displaced dollar dearer (compressed Single brackets).
# * The residual-mortality-risk penalty pulls dollars EARLIER -- every year the
#   balance is still standing is a year the second death could land on it and
#   hand a non-spouse beneficiary the whole balance as ordinary income in one
#   year.
#
# Drop the second term and the search back-loads into the final years before
# the deadline: that schedule satisfies every constraint and every feasibility
# check while maximizing exposure to an early death. That is the failure mode
# `test_optimizer_does_not_back_load_into_the_final_years` exists to catch, and
# it is why the penalty lives here rather than in `score_year` -- it is a
# function of the running balance the schedule leaves standing, not of any one
# candidate (year, amount) pair.

# Residual below this (in dollars) counts as "the balance reached zero". The
# grow-then-draw recursion below empties the account exactly when there is no
# floor, so this only absorbs float noise, not a real shortfall.
_RESIDUAL_TOL = 1.0

# How sharply the search concentrates on its best years. The objective is
# linear in each year's draw, so its unconstrained optimum is degenerate: put
# the ENTIRE balance in the single highest-net-weight year. That is not a
# schedule anyone can execute -- a real draw is bounded by the year's qualified
# expense bank (Task 6) and by what the household can absorb -- and this
# signature carries no per-year capacity to bound it with. So the allocation is
# proportional to net weight raised to this exponent: 0 would BE the level
# schedule, infinity would be the degenerate single-year answer, and 3.0 sits
# between -- concentrated enough that the good years genuinely win, spread
# enough that the answer stays executable. It is a calibration constant, not a
# derived quantity; the tests do not depend on its exact value, only on the
# ordering it produces.
_CONCENTRATION = 3.0


def level_schedule(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict:
    """The naive baseline: the starting balance split evenly across the window.

    This is deliberately what `hsa_withdrawal_mode='smooth_window'` already
    does today (balance / years remaining), and it is the reference point the
    real search has to beat. It is nominal and growth-blind on purpose: it does
    not know that an undrawn dollar compounds, does not know that a survivor
    year prices the displaced dollar higher, and does not know that a balance
    left standing is exposed to the terminal cliff. Making it smarter would
    only make the comparison less informative.
    """
    years = _schedule_years(c, rows)
    balance = _starting_balance(rows)
    if not years:
        return {}
    share = balance / float(len(years))
    return {year: share for year in years}


def schedule_score(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]],
                   by_year: Mapping[int, float]) -> float:
    """Present-valued value, in dollars, of drawing `by_year` out of the HSA.

    The balance is tracked grow-then-draw: each year the account grows at the
    plan's own return assumption (`c['ret']`, the same field
    `planning_engines` uses for exactly this purpose), then that year's draw
    comes out of what is there, capped at the balance -- a schedule cannot
    withdraw money that does not exist, and one that tries is scored on what it
    actually got, not on what it asked for.

    Each year's `score_year` is passed the ACTUAL grown dollar amount withdrawn,
    never a constant nominal one. `score_year`'s own docstring flags why: its
    carry-cost term discounts but does not credit the tax-free compounding a
    deferred dollar earns, so scoring one fixed amount across candidate years
    systematically front-loads. Passing the grown amount is what closes that
    gap, and it is why an allocation expressed as a share of the ORIGINAL
    balance is valued at the grown dollars it actually becomes.

    From the raw sum, the residual-mortality-risk penalty is subtracted:

        for each year Y:
            P(second death lands in Y) x hsa_terminal_tax(balance entering Y, Y)

    discounted with the same `_pv_factor` every other term here uses. The
    balance entering Y (before that year's draw) is the money that would still
    be sitting there if death occurred at the start of Y -- the whole of which
    becomes ordinary income to a non-spouse beneficiary in that single year.
    Note that `hsa_terminal_tax` returns exactly 0.0 for a spouse or charity
    beneficiary, which is the schema default: for those households this penalty
    is correctly zero, and the schedule is driven by rate and discounting
    alone.
    """
    years = _schedule_years(c, rows)
    if not years:
        return 0.0

    growth = _as_float(c.get('ret', 0.0), 0.0)
    pmf = _second_death_pmf(c, years)
    balance = _starting_balance(rows)
    total = 0.0

    for year in years:
        row = _row_for_year(rows, year)
        balance *= (1.0 + growth)
        # Money standing at the START of the year is what an early death in
        # that year would hand the beneficiary -- priced before the draw.
        pv = _pv_factor(c, row)
        probability = pmf.get(year, 0.0)
        if probability > 0.0 and balance > 0.0:
            total -= probability * _hsa_terminal_tax(c, balance, year) * pv

        draw = min(max(0.0, _as_float(by_year.get(year), 0.0)), max(0.0, balance))
        if draw > 0.0:
            total += score_year(c, row, draw)
            balance -= draw

    return total


def build_schedule(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict:
    """Choose which years the HSA is drawn in, and report whether it can close.

    Returns ``{'by_year': {year: dollars}, 'feasibility': str, 'residual': float}``.

    **The search.** Each year in `plan_start`..`resolve_consume_by_year` gets a
    net weight: what a reference increment allocated to that year is worth
    (`score_year` on the increment GROWN to that year, so the comparison is
    like-for-like) minus the mortality risk of carrying that increment through
    every year up to and including it. The second half is cumulative and
    therefore strictly increasing in the year -- that is the anti-back-loading
    gradient, and it is the only thing in the objective that penalizes waiting.
    Years whose net weight is negative -- where the expected terminal-cliff cost
    of carrying a dollar that long exceeds the tax value of drawing it then --
    get nothing at all.

    The balance is then allocated in proportion to those weights raised to
    `_CONCENTRATION` (see that constant for why the answer is not simply "all of
    it in the best year"). Allocations are expressed as shares of the STARTING
    balance and converted to nominal draws at the point of withdrawal, which is
    what makes the grow-then-draw recursion in `schedule_score` land exactly on
    the floor: a schedule whose shares sum to 1 leaves precisely
    `hsa_min_ending_balance` grown to the deadline, and nothing else.

    **Feasibility.** `hsa_min_ending_balance` is the only thing at this
    signature that can make the constraint genuinely unsatisfiable, and it does
    so structurally: a floor the optimizer may not draw through is a residual
    that cannot reach zero, so those plans report `'infeasible'` with the
    residual they are actually left holding. The deadline is NEVER moved to
    rescue them -- no year key past `resolve_consume_by_year` is ever emitted,
    infeasible or not, because a schedule that answers "cannot be consumed by
    the deadline" with "then use a later deadline" has not answered anything.
    `'feasible_with_surplus'` reports the case where the balance is consumed
    with room to spare -- the last funded year lands strictly before the
    deadline, i.e. the deadline never bound at all. `'feasible'` is the ordinary
    case: consumed, using the window up to the deadline.
    """
    years = _schedule_years(c, rows)
    balance = _starting_balance(rows)
    floor = max(0.0, _as_float(c.get('hsa_min_ending_balance', 0.0), 0.0))
    growth = _as_float(c.get('ret', 0.0), 0.0)

    if not years:
        return {'by_year': {}, 'feasibility': 'infeasible', 'residual': balance}

    drawable = max(0.0, balance - floor)
    shares = _allocation_shares(c, rows, years, drawable)

    by_year = {}
    for offset, year in enumerate(years):
        # `drawable` is a share of the STARTING balance; by the time it is
        # withdrawn it has compounded for `offset + 1` years (the account grows
        # before each year's draw). Expressing it this way is what makes the
        # shares sum to a schedule that lands exactly on the floor.
        by_year[year] = shares[year] * drawable * (1.0 + growth) ** (offset + 1)

    residual = _simulate_residual(c, rows, years, by_year)
    funded = [y for y in years if by_year[y] > 0.0]

    if floor > 0.0 or residual > _RESIDUAL_TOL:
        feasibility = 'infeasible'
    elif funded and max(funded) < years[-1]:
        feasibility = 'feasible_with_surplus'
    else:
        feasibility = 'feasible'

    return {'by_year': by_year, 'feasibility': feasibility, 'residual': residual}


def rerun_optimizer(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]],
                    schedule_rows: Sequence[Mapping[str, Any]]) -> list:
    """Re-run the schedule search over a schedule the user has already edited.

    `rows` is the projection (the row list `build_schedule` reads, carrying
    `hsa_nw` on row 0). `schedule_rows` is the current flat-CSV shape --
    `year` / `optimizer_amount` / `override_amount` / `locked` / `note`.
    Returns a NEW list in that same shape, one row per year of the true
    horizon. Neither input is mutated.

    **The contract this function exists to keep.** A re-run may never eat the
    user's intent. Concretely:

    * `override_amount` is copied through untouched on every path, for every
      year, whatever `locked` says. It is never overwritten, never defaulted,
      never "helpfully" cleared. The optimizer does not write that column at
      all -- that is the whole reason a re-run is safe to press.
    * A year pinned by an override or a lock is planned AROUND, not through.
      Its dollars are honored exactly and the remaining years divide only what
      is genuinely left after it draws.
    * The deadline is never moved to accommodate the result. If the user's own
      numbers cannot close the account, `schedule_feasibility` says so; nothing
      here quietly redistributes into a pinned year to make the answer prettier.

    **`optimizer_amount` is refreshed** -- that is the point of a re-run -- with
    one deliberate exception. For a year that is pinned by `locked` with no
    override behind it, `resolve_year_amount` reads the pin OUT of
    `optimizer_amount`: that column *is* the locked value. Refreshing it would
    silently move the very number the lock exists to hold, which is the same
    class of failure as eating an override. So:

    * override-backed year -- refreshed to what the unconstrained search would
      propose if the year were free. The override wins regardless, so the
      column is inert until the user clears the override, at which point they
      get a current number rather than a stale one.
    * locked-only year -- preserved exactly. The lock is the value.
    * every other year -- refreshed to this run's answer.

    **Why the remaining pool comes from `_simulate_residual`.** The pinned
    years' dollars are not simply subtracted from the starting balance: a draw
    in 2030 stops compounding in 2030, so what it costs the rest of the
    schedule depends on where in the growth sequence it lands. Running the
    pinned amounts through the same grow-then-draw recursion `build_schedule`
    and `schedule_score` already trust gives the balance genuinely left over,
    priced at the deadline; dividing back out by the window's total growth
    returns it to the starting-balance units `_allocation_shares` works in. A
    flat `balance - sum(pinned)` would be a second, quietly disagreeing balance
    model.

    Robustness, both directions, because the CSV can be stale relative to a
    changed `hsa_consume_by`: a `schedule_rows` entry for a year outside the
    true horizon is ignored (never emitted -- that would be moving the
    deadline), and a horizon year with no entry at all is simply unpinned.

    **Row order.** The rows the caller handed in come back in the order they
    were handed in; horizon years the file did not cover are appended after
    them, ascending. A re-run refreshes the user's table, it does not reshuffle
    it, and the caller can address `out[i]` for the row it passed at `i`. With
    no input rows (the first run) that degenerates to plain ascending order.
    """
    years = _schedule_years(c, rows)
    if not years:
        return []

    in_window = set(years)
    existing_by_year = {}
    emit_order = []
    for row in schedule_rows or ():
        try:
            year = int(row['year'])
        except (KeyError, TypeError, ValueError):
            continue
        if year in existing_by_year:
            continue
        existing_by_year[year] = row
        if year in in_window:
            emit_order.append(year)
    emit_order.extend(year for year in years if year not in existing_by_year)

    # What is already committed, and by which tier. `resolve_year_amount` is
    # the ONE place the precedence ladder is decided; re-deriving any tier of
    # it here is exactly how a silent precedence bug gets in.
    fixed = {}
    locked_only = set()
    for year in years:
        row = existing_by_year.get(year)
        if row is None:
            continue
        amount, source = resolve_year_amount(row)
        if source in ('override', 'locked'):
            fixed[year] = amount
            if source == 'locked':
                locked_only.add(year)

    growth = _as_float(c.get('ret', 0.0), 0.0)
    floor = max(0.0, _as_float(c.get('hsa_min_ending_balance', 0.0), 0.0))
    plan_start = _horizon(c, rows)[0]
    window_growth = (1.0 + growth) ** len(years)

    # `_simulate_residual` reports at the deadline; `_allocation_shares` and the
    # draw formula below both work in starting-balance dollars, so discount it
    # back over the window before subtracting the floor (which is also a
    # starting-balance figure -- see `build_schedule`).
    residual_after_fixed = _simulate_residual(c, rows, years, fixed)
    pool = max(0.0, (residual_after_fixed / window_growth if window_growth else 0.0) - floor)

    free_years = [year for year in years if year not in fixed]
    # `free_years` is already filtered, so the `fixed=` mask is redundant here
    # by construction. It is passed anyway: it costs nothing, it keeps the
    # parameter exercised by a real caller, and it means a future caller that
    # stops filtering still cannot hand a pinned year a share of the pool.
    shares = _allocation_shares(c, rows, free_years, pool, fixed=fixed)

    # What the search would say with nothing pinned at all -- the number an
    # override-backed year's inert `optimizer_amount` column is refreshed to.
    unconstrained = build_schedule(c, rows)['by_year']

    out = []
    for year in emit_order:
        source_row = existing_by_year.get(year) or {}
        if year in locked_only:
            optimizer_amount = _as_float(source_row.get('optimizer_amount'), 0.0)
        elif year in fixed:
            optimizer_amount = unconstrained.get(year, 0.0)
        else:
            offset = (int(year) - int(plan_start)) + 1
            optimizer_amount = shares.get(year, 0.0) * pool * (1.0 + growth) ** offset
        out.append({
            'year': year,
            'optimizer_amount': optimizer_amount,
            # Untouched, on every path, including when it is absent.
            'override_amount': source_row.get('override_amount'),
            'locked': source_row.get('locked', False),
            'note': source_row.get('note'),
        })

    if out:
        # `schedule_feasibility` takes only (c, rows) and cannot see the
        # projection separately, so the round trip has to be self-describing
        # about the balance it was built to consume.
        out[0]['hsa_nw'] = _starting_balance(rows)
    return out


#: Bound on schedule-search rounds. Each round costs two full projections
#: (~20-60ms each), and gains fall off fast -- the frozen fixture's second
#: round adds ~1.7% over the first and the third essentially nothing. The
#: bound exists so a pathological config cannot spin: rounds stop early the
#: moment a round fails to beat the incumbent by _SCHEDULE_SEARCH_MIN_GAIN.
_SCHEDULE_SEARCH_MAX_ROUNDS = 4

#: Dollars of present-valued score a round must add to be worth adopting.
#: Guards against an infinite alternation between two schedules whose scores
#: differ only by floating-point noise.
_SCHEDULE_SEARCH_MIN_GAIN = 1.0


def run_schedule_search(c: MutableMapping[str, Any]) -> dict:
    """Wire the schedule search into a build: propose a schedule, score it
    against the one already in effect, and keep the better.

    This is the piece this module's header called out as missing -- the search
    (`build_schedule`/`rerun_optimizer`) needs full per-year projection rows
    for tax context, and those only exist after a projection runs, which is
    the projection that would consume the schedule.

    **How that circularity is resolved: candidate scoring, not a one-shot
    two-pass.** This follows the pattern
    `planning_engines.optimize_roth_conversion_strategy` already uses for the
    identical problem -- enumerate candidates, run a FULL projection per
    candidate, score each on its own rows, keep the winner. Every score is
    therefore self-consistent (the projection has that candidate in effect),
    so there is no fixed point to iterate toward. Scoring a proposal against
    a baseline's tax context -- the obvious two-pass shortcut -- would instead
    price a schedule using rates it changes.

    Two candidates are compared:

    * **incumbent** -- whatever is configured now, which for a first build is
      `generate_default_schedule`'s static level draw (written by
      `workbook_builder._ensure_hsa_default_schedule`), and thereafter the
      household's own table.
    * **proposal** -- `rerun_optimizer` run over a baseline projection.

    Because the incumbent is always a candidate, **the result can never be
    worse than today's behavior**: a degenerate or unhelpful search simply
    loses the comparison. That is a stronger guarantee than a feature flag,
    and it needs no flag to deliver.

    User intent is safe by construction: `rerun_optimizer` copies
    `override_amount` through untouched on every path and plans *around*
    locked years rather than through them. This function only ever installs
    what that returns, and never writes `override_amount` itself.

    Returns a diagnostic dict -- ``{'ran': bool, 'reason': str,
    'chosen': 'proposal'|'incumbent', 'incumbent_score': float,
    'proposal_score': float}`` -- and, when the proposal wins, installs it on
    ``c`` as `hsa_schedule_rows`/`hsa_schedule_by_year`. Cost is one extra
    `project()` per candidate; a full-horizon projection measures ~20-60ms,
    which is not the class of cost that caused the 81x Monte Carlo CI
    timeouts (see documentation/OPTIMIZATION_REFACTOR_STATUS.md).

    Never raises into a build: any failure returns ``ran=False`` with a
    reason and leaves ``c`` untouched, so the incumbent schedule stands.
    """
    out = {'ran': False, 'reason': '', 'chosen': 'incumbent',
           'incumbent_score': None, 'proposal_score': None}
    if str(c.get('hsa_withdrawal_mode', '') or '').strip().lower() != 'optimize':
        out['reason'] = 'not in optimize mode'
        return out
    try:
        import copy as _copy
        from .planning_engines import project as _project

        def _score_with(schedule_rows):
            """Full projection with `schedule_rows` installed, scored on its
            OWN rows -- the self-consistency R1 requires."""
            trial = _copy.deepcopy(dict(c))
            trial['hsa_schedule_rows'] = list(schedule_rows or [])
            trial['hsa_schedule_by_year'] = {r['year']: r for r in (schedule_rows or [])}
            trial_rows = _project(trial)
            by_year = {}
            for r in (schedule_rows or []):
                amount, source = resolve_year_amount(r)
                if source != 'mode':
                    by_year[int(r['year'])] = amount
            return schedule_score(trial, trial_rows, by_year), trial_rows

        incumbent_rows = list(c.get('hsa_schedule_rows') or [])
        incumbent_score, incumbent_projection = _score_with(incumbent_rows)
        first_incumbent_score = incumbent_score

        best_rows = incumbent_rows
        best_score = incumbent_score
        best_projection = incumbent_projection
        latest_proposal_score = None
        iterations = 0

        # Candidate SCORING is self-consistent (each candidate is scored on
        # its own projection), but candidate GENERATION still reads the
        # incumbent's rows for tax context -- so one pass does not reach a
        # fixed point: re-running against an adopted proposal measurably
        # improves it again. Iterate while that keeps paying, which is cheap
        # (a full projection is ~20-60ms) and safe: a round is adopted only
        # when it scores strictly higher, so the sequence is monotonic and
        # can never end below where it started.
        for _ in range(_SCHEDULE_SEARCH_MAX_ROUNDS):
            proposal_rows = rerun_optimizer(c, best_projection, best_rows)
            if not proposal_rows:
                break
            proposal_score, proposal_projection = _score_with(proposal_rows)
            latest_proposal_score = proposal_score
            iterations += 1
            if proposal_score <= best_score + _SCHEDULE_SEARCH_MIN_GAIN:
                break
            best_rows = proposal_rows
            best_score = proposal_score
            best_projection = proposal_projection

        if not best_rows and not incumbent_rows:
            out['reason'] = 'search produced no schedule'
            return out

        out['ran'] = True
        out['rounds'] = iterations
        out['incumbent_score'] = float(first_incumbent_score)
        out['proposal_score'] = float(
            latest_proposal_score if latest_proposal_score is not None else first_incumbent_score)
        out['chosen_score'] = float(best_score)
        if best_score > first_incumbent_score:
            out['chosen'] = 'proposal'
            out['reason'] = f'proposal scored higher after {iterations} round(s)'
            c['hsa_schedule_rows'] = best_rows
            c['hsa_schedule_by_year'] = {r['year']: r for r in best_rows}
        else:
            out['reason'] = 'incumbent scored at least as high; kept'
        return out
    except Exception as exc:  # never fail a build over a schedule proposal
        out['reason'] = f'search failed, incumbent kept ({exc})'
        return out


def schedule_feasibility(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> str:
    """`'feasible' | 'feasible_with_surplus' | 'infeasible'` for a SCHEDULE.

    `rows` here is a schedule in the flat-CSV shape -- `rerun_optimizer`'s
    output, or the CSV as the user last edited it -- **not** the projection
    rows. Row 0 carries `hsa_nw`, the balance being consumed, which is what
    `rerun_optimizer` stamps there.

    The classification is `build_schedule`'s, unchanged, so the two cannot
    disagree about the same plan:

    * a positive `hsa_min_ending_balance` is a floor the optimizer may not draw
      through, which is a residual that cannot reach zero -- `'infeasible'`
      structurally, however well the rest of the window is scheduled;
    * any residual left standing past `_RESIDUAL_TOL` is `'infeasible'`, and it
      is reported rather than papered over: the user's overrides are honored
      and the consequence surfaced;
    * an account emptied strictly before the deadline is
      `'feasible_with_surplus'` -- the deadline never bound;
    * otherwise `'feasible'`.

    The per-year amount is `resolve_year_amount`'s, so the same precedence
    ladder decides what this function scores as the user's schedule decides.
    Rows outside the true horizon are ignored entirely -- for their amount AND
    for the `hsa_nw` they carry (a stale CSV must not move the deadline, and it
    must not restate the balance either), and a row whose source is `'mode'`
    contributes nothing: that
    tier means "no schedule-layer answer for this year", and reading its
    placeholder 0.0 as a real instruction would be the documented misuse.
    """
    years = _schedule_years(c, rows)
    if not years:
        return 'infeasible'
    in_window = set(years)

    by_year = {}
    for row in rows or ():
        try:
            year = int(row['year'])
        except (KeyError, TypeError, ValueError):
            continue
        if year not in in_window:
            continue
        amount, source = resolve_year_amount(row)
        if source == 'mode':
            continue
        by_year[year] = amount

    # The balance being consumed. `rerun_optimizer` stamps it on the first row
    # it emits, but it is looked up by SCANNING rather than by position: a
    # schedule is a table, a caller is entitled to sort it by year before
    # handing it back, and a feasibility answer that silently depended on which
    # row happened to be first would be exactly the kind of order-coupling that
    # only shows up in production. `_simulate_residual` reads its balance
    # through `_starting_balance` (i.e. `rows[0]`), so it is handed a synthetic
    # one-row projection carrying the balance found here.
    #
    # The scan applies the SAME `in_window` filter the amount loop above does,
    # for the same documented reason: a stale row is stale for every column it
    # carries, not just its amount. Without the filter a leftover row past the
    # deadline could supply the balance purely by sorting ahead of the real
    # one -- the same order-coupling this scan exists to remove, reintroduced
    # through the horizon.
    balance = 0.0
    for row in rows or ():
        if not isinstance(row, Mapping):
            continue
        try:
            year = int(row['year'])
        except (KeyError, TypeError, ValueError):
            continue
        if year not in in_window:
            continue
        value = _as_float(row.get('hsa_nw'), _ABSENT)
        if value is not None:
            balance = max(0.0, value)
            break

    residual = _simulate_residual(c, [{'hsa_nw': balance}], years, by_year)
    floor = max(0.0, _as_float(c.get('hsa_min_ending_balance', 0.0), 0.0))

    if floor > 0.0 or residual > _RESIDUAL_TOL:
        return 'infeasible'
    funded = [year for year in years if by_year.get(year, 0.0) > 0.0]
    if funded and max(funded) < years[-1]:
        return 'feasible_with_surplus'
    return 'feasible'


def _allocation_shares(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]],
                       years: Sequence[int], drawable: float,
                       fixed: Optional[Mapping[int, float]] = None) -> dict:
    """{year: share of the drawable balance}, summing to 1 (or to 0 if empty).

    `years` does NOT have to be contiguous. Growth is compounded from each
    year's TRUE distance from `plan_start`, never from its position in this
    list. For `build_schedule`'s own call the two are identical -- that list is
    always the full `plan_start`..deadline range -- but `rerun_optimizer` hands
    in a FILTERED list (the years not already pinned by a lock or an override),
    and there the list index is simply the wrong number: the third entry of a
    filtered list can be eight years past `plan_start`, and compounding it for
    three would systematically misprice every remaining year.

    `fixed` marks years whose amount is already committed elsewhere (a lock or
    an override). Their weight is forced to 0.0 so they cannot compete for the
    drawable pool. Their dollars are accounted for by the caller's balance
    tracking, NOT here: this function never deducts them from `drawable`, and
    doing so here as well would double-count them.
    """
    if not years:
        return {}
    if drawable <= 0.0:
        return {year: 0.0 for year in years}

    fixed = fixed or {}
    # The anchor the growth offsets are measured from. `_schedule_years` starts
    # its range here, so for the unfiltered call `year - plan_start` and the old
    # `enumerate` index are the same integer for every year -- the fix is inert
    # there by construction. The `years[0]` fallback covers a config with no
    # horizon at all, and reproduces the old index behaviour exactly.
    plan_start = _horizon(c, rows)[0]
    if plan_start is None:
        plan_start = int(years[0])

    growth = _as_float(c.get('ret', 0.0), 0.0)
    pmf = _second_death_pmf(c, years)
    reference_balance = _starting_balance(rows)
    # One increment's worth of balance. Scoring a realistic increment rather
    # than a nominal $1 matters: the IRMAA cliff term is not linear in the
    # amount, so a $1 probe would read every year as nowhere near a threshold.
    increment = drawable / float(len(years))

    weights = {}
    carried_risk = 0.0
    for year in years:
        row = _row_for_year(rows, year)
        grown = increment * (1.0 + growth) ** ((int(year) - int(plan_start)) + 1)
        # Risk of carrying this increment THROUGH this year, accumulated: an
        # increment drawn in year Y was exposed in every year up to Y.
        #
        # The increment is priced at the rate the WHOLE balance would face, not
        # at the rate the increment would face standing alone. That is not a
        # detail: `hsa_terminal_tax` runs the balance through the progressive
        # brackets from the bottom, so a $60k slice prices at ~13% while the
        # $600k balance it is part of prices at ~30%. An increment is not
        # inherited by itself -- it is inherited on top of everything else the
        # schedule has not yet drawn -- and pricing it standalone would halve
        # the penalty relative to what `schedule_score` actually charges,
        # leaving the search optimizing a materially different objective from
        # the one it is judged on.
        carried_risk += (pmf.get(year, 0.0)
                         * _terminal_tax_rate(c, reference_balance, year) * grown
                         * _pv_factor(c, row))
        if year in fixed:
            # Already committed elsewhere. It still accumulated carried risk
            # above -- the balance really was carried through this year -- but
            # it must not bid for the pool the free years are dividing up.
            weights[year] = 0.0
        else:
            weights[year] = max(0.0, score_year(c, row, grown) - carried_risk)

    powered = {year: weight ** _CONCENTRATION for year, weight in weights.items()}
    total = sum(powered.values())
    if total <= 0.0:
        # Every year is net-negative (or the rows carry no rate at all). The
        # deadline still has to be met, so fall back to the level split rather
        # than refusing to draw -- declining to schedule is not an option the
        # constraint leaves open. Fixed years stay out of that split too.
        free = [year for year in years if year not in fixed]
        if not free:
            return {year: 0.0 for year in years}
        share = 1.0 / float(len(free))
        return {year: (share if year in set(free) else 0.0) for year in years}
    return {year: value / total for year, value in powered.items()}


def _simulate_residual(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]],
                       years: Sequence[int], by_year: Mapping[int, float]) -> float:
    """Balance still standing after the deadline year's draw.

    Same grow-then-draw recursion `schedule_score` uses, so the reported
    residual is the one the score was computed against rather than an
    independently derived (and potentially disagreeing) figure.
    """
    growth = _as_float(c.get('ret', 0.0), 0.0)
    balance = _starting_balance(rows)
    for year in years:
        balance *= (1.0 + growth)
        balance -= min(max(0.0, _as_float(by_year.get(year), 0.0)), max(0.0, balance))
    return max(0.0, balance)


def _hsa_terminal_tax(c: Mapping[str, Any], balance: float, year: int) -> float:
    """`after_tax.hsa_terminal_tax`, imported lazily and read defensively.

    Zero for a spouse or charity beneficiary -- which is the schema default --
    because those inherit the account AS an HSA with no tax event at all.
    """
    try:
        from .after_tax import hsa_terminal_tax
    except ImportError:  # pragma: no cover - direct execution fallback
        from src.after_tax import hsa_terminal_tax
    return max(0.0, _as_float(hsa_terminal_tax(c, balance, terminal_year=year), 0.0))


def _terminal_tax_rate(c: Mapping[str, Any], balance: float, year: int) -> float:
    """Average terminal-cliff tax rate on `balance`, as a fraction of it.

    Zero for a spouse or charity beneficiary, for the same reason
    `hsa_terminal_tax` is: nothing is owed, so no schedule should be distorted
    to avoid it.
    """
    if balance <= 0.0:
        return 0.0
    return _hsa_terminal_tax(c, balance, year) / balance


def _second_death_pmf(c: Mapping[str, Any], years: Sequence[int]) -> dict:
    """{year: P(the SECOND death lands in that year)}.

    Differenced out of the same per-member CDFs `_second_death_year_at_percentile`
    reads, combining members as independent lives exactly the way that function
    does -- this is not a second mortality model. An empty dict (no members, no
    birth years) correctly switches the residual-risk term off rather than
    inventing a distribution.
    """
    members = c.get('members') or []
    plan_start = _horizon(c, [])[0]
    if plan_start is None and years:
        plan_start = years[0]
    if not members or plan_start is None:
        return {}

    cdfs = []
    for idx, member in enumerate(members):
        cdf = _member_death_cdf(member, 0 if idx == 0 else 1, plan_start)
        if cdf is None:
            return {}
        cdfs.append(cdf)

    pmf = {}
    for year in years:
        prior = 1.0
        current = 1.0
        for cdf in cdfs:
            prior *= _cdf_at(cdf, year - 1)
            current *= _cdf_at(cdf, year)
        pmf[year] = max(0.0, current - prior)
    return pmf


def _schedule_years(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> list:
    """`plan_start`..deadline, inclusive. Empty when there is no horizon at all."""
    plan_start = _horizon(c, rows)[0]
    if plan_start is None:
        return []
    deadline = resolve_consume_by_year(c, rows)
    if deadline < plan_start:
        return []
    return list(range(int(plan_start), int(deadline) + 1))


def _starting_balance(rows: Sequence[Mapping[str, Any]]) -> float:
    """`rows[0]['hsa_nw']` -- the balance the schedule has to consume.

    Both `build_schedule` and `schedule_score` derive it this way independently,
    so neither can be handed a balance that disagrees with the rows it is
    scoring against.
    """
    if not rows:
        return 0.0
    return max(0.0, _as_float(rows[0].get('hsa_nw'), 0.0))


def _row_for_year(rows: Sequence[Mapping[str, Any]], year: int) -> dict:
    """The projection row for `year`, synthesized from the nearest one if sparse.

    A schedule window can outrun the rows it was handed (a sparse fixture, a
    horizon that comes from the config rather than the rows). Falling back to
    the nearest row's tax characteristics with the right `year` keeps
    discounting correct rather than silently scoring a missing year at zero,
    which would read as "this year is worthless" instead of "this year is
    unknown".
    """
    for row in rows or ():
        try:
            if int(row['year']) == int(year):
                return dict(row)
        except (KeyError, TypeError, ValueError):
            continue
    nearest = None
    best = None
    for row in rows or ():
        try:
            distance = abs(int(row['year']) - int(year))
        except (KeyError, TypeError, ValueError):
            continue
        if best is None or distance < best:
            nearest, best = row, distance
    out = dict(nearest) if nearest else {}
    out['year'] = year
    return out
