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
