from __future__ import annotations
"""Blend real year-to-date actuals into the current-year projection row.

The projection engine (see projection_stages/deterministic_engine.py) treats
every plan year, including the current calendar year, as a pure full
Jan-1-through-Dec-31 model. The opening account balances it starts from are
today's live-priced holdings values, which already reflect however much of
the current year has actually elapsed (real growth, real contributions). If
the engine then applies a *full year* of assumed growth/contributions on top
of that already-partially-realized balance, it double-counts the elapsed
portion - and that error compounds into every later year's balance too.

This module computes a small set of override keys, merged into the engine
config before project() runs, that correct this for the current calendar
year only:

- Balances (investment growth, 401k/HSA contributions): the "actual so far"
  is already embedded in today's live balance, so the fix is pure date math
  - assume growth/contributions only for the *remaining* fraction of the
  year. This needs no YTD tracking data and is always computed.
- Flows (earned income, spending): these are not captured in any running
  balance, so the fix is genuine actual-to-date (from ytd_transactions.csv)
  + a prorated remainder of the assumed annual plan. This only applies when
  YTD tracking has current-year transactions; otherwise it's a no-op and the
  old full-year behavior is unchanged.
- The remainder (projected, not-yet-elapsed) portion of earned income and
  spending can each be manually overridden by the user - see
  ytd_remainder_earned_income_override / ytd_remainder_spending_override in
  client_income.csv / client_spending.csv - for known lumpy events (a
  year-end bonus, a planned large purchase) that a linear pro-ration would
  miss. Blank (the default) keeps the linear pro-rated estimate. This never
  affects investment growth/contribution proration, which stays purely
  date-based to avoid performance-chasing.
- Flow blending can be turned off entirely for a given plan via
  ytd_blend_enabled (client_spending.csv, Cashflow/Spending), for plans that
  are deliberately hypothetical and should not inherit real bank/brokerage
  activity tracked elsewhere in the workspace (e.g. a fresh "Start New Plan"
  scenario). This only suppresses the flow (earned income/spending) blend -
  the growth/contribution date-proration above is a pure bug fix with no
  performance-chasing risk and always applies regardless of this setting.

All override keys are absent from the returned dict when there's nothing to
apply, so callers that don't merge this in (Monte Carlo, optimizers, tests)
are completely unaffected.
"""

from datetime import date
from pathlib import Path
from typing import Any

try:
    from .ytd_tracking import ytd_summary
except Exception:  # pragma: no cover - direct execution fallback
    from src.ytd_tracking import ytd_summary


def _year_days(year: int) -> int:
    return 366 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 365


def _remaining_fraction(today: date) -> float:
    year_days = _year_days(today.year)
    elapsed_days = (today - date(today.year, 1, 1)).days + 1
    fraction = 1.0 - (elapsed_days / year_days)
    return max(0.0, min(1.0, fraction))


def compute_current_year_overrides(c: dict[str, Any], root: str | Path, *, today: date | None = None) -> dict[str, Any]:
    """Return override keys to merge into the engine config for the current year.

    Returns {} if the current calendar year isn't within the plan's
    [plan_start, plan_end] window. Growth/contribution proration is always
    computed when within range; earned-income/spending overrides are only
    added when YTD tracking has current-year transactions logged.
    """
    today = today or date.today()
    current_year = today.year
    plan_start = c.get('plan_start')
    plan_end = c.get('plan_end')
    if plan_start is None or plan_end is None or not (plan_start <= current_year <= plan_end):
        return {}

    remaining_fraction = _remaining_fraction(today)

    overrides: dict[str, Any] = {
        'return_by_year': {current_year: float(c.get('ret', 0.0) or 0.0) * remaining_fraction},
        'ytd_blend_contrib_proration': {current_year: remaining_fraction},
    }

    flow_blend_enabled = c.get('ytd_blend_enabled', True)

    blend_meta: dict[str, Any] = {
        'current_year': current_year,
        'as_of': today.isoformat(),
        'remaining_fraction': round(remaining_fraction, 4),
        'flows_blended': False,
        'flow_blend_enabled': bool(flow_blend_enabled),
    }

    try:
        summary = ytd_summary(root, today=today)
    except Exception:
        summary = {}

    has_current_year_actuals = flow_blend_enabled and bool(summary.get('enabled')) and bool(summary.get('ytd_end'))
    if not flow_blend_enabled and bool(summary.get('enabled')):
        blend_meta['flow_blend_skipped_by_user_choice'] = True
        blend_meta['ytd_end'] = summary.get('ytd_end')
    if has_current_year_actuals:
        actual = summary.get('actual') or {}
        forecast = summary.get('forecast') or {}
        earned_actual = float(actual.get('earned_income') or 0.0)
        earned_remaining_override = c.get('ytd_remainder_earned_income_override')
        if earned_remaining_override is not None:
            earned_remaining = float(earned_remaining_override)
            blend_meta['earned_remainder_overridden'] = True
        else:
            earned_remaining = float(forecast.get('earned_income_remaining') or 0.0)
        overrides['ytd_blend_earned_override'] = {current_year: earned_actual + earned_remaining}

        spend_annual_plan = forecast.get('spending_annual_plan')
        spend_remaining_override = c.get('ytd_remainder_spending_override')
        if spend_annual_plan is not None or spend_remaining_override is not None:
            spend_actual = float(actual.get('spending') or 0.0)
            if spend_remaining_override is not None:
                spend_remaining = float(spend_remaining_override)
                blend_meta['spend_remainder_overridden'] = True
            else:
                # Use our own today-anchored remaining_fraction rather than
                # ytd_summary()'s ytd_days (anchored to the *latest logged
                # transaction date*) - if the transaction log has a gap between
                # the last entry and today, ytd_days understates how much of
                # the year has actually elapsed and overstates what's
                # "remaining".
                spend_remaining = float(spend_annual_plan) * remaining_fraction
            overrides['ytd_blend_spend_override'] = {current_year: spend_actual + spend_remaining}

        blend_meta['flows_blended'] = 'ytd_blend_spend_override' in overrides
        blend_meta['ytd_end'] = summary.get('ytd_end')
        blend_meta['ytd_days'] = summary.get('ytd_days')
        blend_meta['year_days'] = summary.get('year_days')

    investment_balance = summary.get('investment_balance') or {}
    if investment_balance.get('actual_growth_available'):
        blend_meta['account_growth_rows'] = investment_balance.get('account_growth_rows', [])
        blend_meta['prior_year_end_balance'] = investment_balance.get('prior_year_end_balance')
        blend_meta['current_balance'] = investment_balance.get('current_balance')

    overrides['ytd_blend_applied'] = blend_meta
    return overrides
