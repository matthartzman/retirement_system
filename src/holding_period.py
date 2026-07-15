from __future__ import annotations
"""holding_period.py — derive the holding-period distribution of today's
liquid balance from the household's own withdrawal schedule.

The deterministic projection already knows, year by year, how many real
dollars leave the liquid portfolio (RMDs, elective pre-tax withdrawals,
taxable/trust draws, Roth withdrawals — see row['_account_withdrawals'] in
projection_stages/deterministic_engine.py). That schedule is a precise,
household-specific holding-period signal: instead of guessing one global
capital-market horizon (1/3/5/10/20/25/30 years), we can compute how long
each dollar of today's balance is actually expected to stay invested before
it is spent.

This module only reads an already-computed projection; it does not run or
mutate one, so it cannot introduce cash-flow drift in existing golden
masters.
"""

import datetime

# Bucket starts (in years-from-now); the implied ranges are 0-2, 3-5, 6-10,
# 11-15, 16+. Chosen to roughly track the chart's near/short/mid/long groupings.
DEFAULT_BUCKET_EDGES = (0, 3, 6, 11, 16)
DEFAULT_BUCKET_LABELS = ('0-2 yr', '3-5 yr', '6-10 yr', '11-15 yr', '16+ yr')

# Representative single holding-year value per bucket, used wherever a bucket
# needs to be looked up against a holding-year-keyed curve (see
# src/real_loss_curves.py's real_loss_prob) instead of the bucket's full
# range. Kept here as the single source of truth so callers (e.g.
# optimization.py's real-loss-aware allocation mode) don't duplicate these
# numbers. 20, not 16, represents the "16+ yr" bucket: it stays within the
# real-loss curves' sampled range (up to 21 years) rather than sitting right
# at the bucket's lower edge.
DEFAULT_BUCKET_MIDPOINTS = {
    '0-2 yr': 1, '3-5 yr': 4, '6-10 yr': 8, '11-15 yr': 13, '16+ yr': 20,
}


def _year_offsets_and_withdrawals(rows, plan_start):
    """[(year_offset, nominal_withdrawal_total), ...] sorted ascending.

    Sums row['_account_withdrawals'], the engine's own per-account ledger of
    real cash leaving the liquid portfolio that year (RMD + HSA + pre-tax
    elective + taxable/trust + Roth). Using that ledger instead of
    re-deriving the withdrawal cascade keeps this module correct even as the
    cascade's internals evolve.
    """
    out = []
    for r in rows or []:
        yr = r.get('year')
        if yr is None:
            continue
        offset = int(yr) - int(plan_start)
        wd = r.get('_account_withdrawals') or {}
        total = sum(float(v or 0.0) for v in wd.values())
        out.append((offset, total))
    out.sort(key=lambda t: t[0])
    return out


def withdrawal_liability_schedule(rows, c):
    """{year_offset: real (today's-dollar) withdrawal amount}, offset >= 0 only.

    Nominal withdrawals are deflated by the plan's general inflation
    assumption (c['inf']), a flat-rate approximation consistent with how
    optimization.py already discounts human capital and guaranteed-income PV
    (compute_human_capital, compute_allocation_coverage) — precision to the
    exact CPI path is not needed for a holding-period *bucket* assignment.
    """
    plan_start = int(c.get('plan_start', datetime.date.today().year))
    _raw_inf = c.get('inf', 0.025)
    inf = float(_raw_inf) if _raw_inf is not None else 0.025
    schedule: dict[int, float] = {}
    for offset, nominal in _year_offsets_and_withdrawals(rows, plan_start):
        if offset < 0 or nominal <= 0:
            continue
        real = nominal / ((1.0 + inf) ** offset) if inf > -0.999 else nominal
        schedule[offset] = schedule.get(offset, 0.0) + real
    return schedule


def _liquid_nw_today(c):
    return float(sum((c.get('balances') or {}).values()))


def _bucket_index(offset, bucket_edges):
    idx = 0
    for i, edge in enumerate(bucket_edges):
        if offset >= edge:
            idx = i
        else:
            break
    return idx


def holding_period_profile(rows, c, bucket_edges=DEFAULT_BUCKET_EDGES, bucket_labels=DEFAULT_BUCKET_LABELS):
    """Assign today's liquid balance to holding-period buckets.

    FIFO against the withdrawal-liability schedule: the soonest-spent
    dollars are the shortest-held dollars (mirrors the withdrawal cascade's
    own priority order, since the schedule is already the cascade's output).
    Any balance the schedule never consumes (long plan horizon, high funded
    ratio, or a legacy-oriented household) is durable, long-horizon money —
    it is assigned a holding period equal to the plan horizon itself
    (plan_end - plan_start), the longest period this plan actually models.

    Returns:
        {
          'buckets': {label: {'dollars', 'share'}},
          'weighted_horizon_years': dollar-weighted mean holding period
              across all liquid dollars, or None if there is no liquid
              balance to bucket,
          'liquid_nw': today's liquid balance,
          'source': 'withdrawal_schedule' | 'no_projected_withdrawals' | 'no_liquid_assets',
        }
    """
    liquid_nw = _liquid_nw_today(c)
    if liquid_nw <= 0:
        return {'buckets': {}, 'weighted_horizon_years': None, 'liquid_nw': 0.0, 'source': 'no_liquid_assets'}

    schedule = withdrawal_liability_schedule(rows, c)
    if not schedule:
        # Accumulation phase or no projected withdrawals in the modeled
        # window: no near-term liability, so the balance is durable money.
        label = bucket_labels[-1]
        return {
            'buckets': {label: {'dollars': liquid_nw, 'share': 1.0}},
            'weighted_horizon_years': None,
            'liquid_nw': liquid_nw,
            'source': 'no_projected_withdrawals',
        }

    plan_start = int(c.get('plan_start', datetime.date.today().year))
    plan_end_offset = max(0, int(c.get('plan_end', plan_start)) - plan_start)

    remaining = liquid_nw
    bucket_dollars = {label: 0.0 for label in bucket_labels}
    weighted_years_sum = 0.0
    allocated = 0.0
    for offset in sorted(schedule.keys()):
        if remaining <= 1e-9:
            break
        take = min(remaining, schedule[offset])
        if take <= 0:
            continue
        idx = _bucket_index(offset, bucket_edges)
        bucket_dollars[bucket_labels[idx]] += take
        weighted_years_sum += take * offset
        allocated += take
        remaining -= take

    if remaining > 1e-9:
        bucket_dollars[bucket_labels[-1]] += remaining
        weighted_years_sum += remaining * plan_end_offset
        allocated += remaining
        remaining = 0.0

    weighted_horizon = weighted_years_sum / allocated if allocated > 0 else None
    buckets = {
        label: {'dollars': dollars, 'share': dollars / liquid_nw if liquid_nw > 0 else 0.0}
        for label, dollars in bucket_dollars.items()
    }
    return {
        'buckets': buckets,
        'weighted_horizon_years': weighted_horizon,
        'liquid_nw': liquid_nw,
        'source': 'withdrawal_schedule',
    }


def withdrawal_weighted_horizon(rows, c, default=None):
    """Dollar-weighted mean holding period (years) across today's liquid balance.

    Falls back to ``default`` (or plan_end - plan_start) when there is no
    usable withdrawal schedule to derive one from, e.g. a pure
    accumulation-phase plan with no liquid balance yet.
    """
    profile = holding_period_profile(rows, c)
    horizon = profile.get('weighted_horizon_years')
    if horizon is not None:
        return horizon
    if default is not None:
        return default
    plan_start = int(c.get('plan_start', datetime.date.today().year))
    plan_end = int(c.get('plan_end', plan_start + 30))
    return max(1, plan_end - plan_start)
