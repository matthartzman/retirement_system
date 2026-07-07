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
- The spending blend is CORE-SCOPED: it replaces the engine's spend_base_yr,
  which by definition never includes Housing, Wellness, Business, Travel, or
  Large Discretionary (those project through their own columns/flows). So the
  actual side counts only transactions whose taxonomy tracking type feeds
  spend_base, and the remainder side prorates the same core spend_base the
  engine would have modeled for the year — not the all-in household plan.
  Plans without a spending taxonomy fall back to the legacy unscoped blend
  (all tracked spending + the legacy core plan field), since they have no
  category data to scope with.
- The remainder (projected, not-yet-elapsed) portion of earned income and
  core spending can each be manually overridden by the user - see
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
    from .ytd_tracking import ytd_summary, annual_spending_forecast
    from .spending_tracker import ytd_core_spending_actual
except Exception:  # pragma: no cover - direct execution fallback
    from src.ytd_tracking import ytd_summary, annual_spending_forecast
    from src.spending_tracker import ytd_core_spending_actual


def _year_days(year: int) -> int:
    return 366 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 365


def _remaining_fraction(today: date) -> float:
    year_days = _year_days(today.year)
    elapsed_days = (today - date(today.year, 1, 1)).days + 1
    fraction = 1.0 - (elapsed_days / year_days)
    return max(0.0, min(1.0, fraction))


def _taxonomy_plan_root(data_dir: Path) -> Path | None:
    """Map the blend's plan-data dir to the project root spending_tracker expects.

    The blend is called with the plan-data (input) directory; spending_tracker
    resolves its files as <root>/input/<file>. When the data dir isn't a
    conventional 'input' folder (unit-test fixtures), taxonomy scoping is
    unavailable and callers fall back to the legacy unscoped blend.
    """
    data_dir = Path(data_dir)
    if data_dir.name.lower() == "input":
        return data_dir.parent
    return None


def _modeled_current_year_core_spend(c: dict[str, Any], current_year: int) -> float | None:
    """Replicate the engine's core spend_base_yr for the current year.

    Mirrors projection_stages/deterministic_engine.py: spend_base grown by the
    core-spending growth mode (manual rate or CPI) until the freeze year. Uses
    the flat compound rate; a custom inflation_index_by_year path is not
    consulted (the blend only runs for the standard current-year build, where
    the divergence is zero or negligible).
    """
    base = c.get('spend_base')
    if base is None:
        return None
    base = float(base or 0.0)
    plan_start = int(c.get('plan_start') or current_year)
    freeze_yr = c.get('spending_freeze_yr')
    growth_year = min(current_year, int(freeze_yr)) if freeze_yr else current_year
    if c.get('core_spending_growth_mode') == 'manual_override':
        rate = float(c.get('core_spending_manual_growth_rate', c.get('spend_inf', 0.0)) or 0.0)
    else:
        rate = float(c.get('inf', 0.0) or 0.0)
    return base * (1.0 + rate) ** max(0, growth_year - plan_start)


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

        # ── Spending: core-scoped blend ──────────────────────────────────
        # spend_base_yr never includes Housing/Wellness/Business/Travel/Large
        # Discretionary, so both sides of the blend must be core-scoped too.
        plan_root = _taxonomy_plan_root(Path(root))
        core_scope = None
        if plan_root is not None:
            try:
                core_scope = ytd_core_spending_actual(plan_root, current_year)
            except Exception:
                core_scope = None

        if core_scope is not None:
            # Unmatched (unmapped-category) spend is counted as core rather than
            # silently dropped from the plan; the amount is surfaced in the meta
            # so a nonzero value is auditable.
            spend_actual = (float(core_scope.get('core_actual') or 0.0)
                            + float(core_scope.get('unmatched_spending_actual') or 0.0))
            blend_meta['spend_scope'] = 'core_taxonomy'
            blend_meta['spend_actual_core'] = round(float(core_scope.get('core_actual') or 0.0), 2)
            blend_meta['spend_actual_unmatched_included'] = round(float(core_scope.get('unmatched_spending_actual') or 0.0), 2)
        else:
            spend_actual = float(actual.get('spending') or 0.0)
            blend_meta['spend_scope'] = 'all_spending_no_taxonomy'

        # Annual core plan for the remainder: the same spend_base the engine
        # projects (budget-derived when the unified budget drives the plan),
        # falling back to the legacy core-spending field for plans without one.
        spend_annual_plan = _modeled_current_year_core_spend(c, current_year)
        if spend_annual_plan is None:
            try:
                spend_annual_plan = annual_spending_forecast(root)
            except Exception:
                spend_annual_plan = None

        spend_remaining_override = c.get('ytd_remainder_spending_override')
        if spend_annual_plan is not None or spend_remaining_override is not None:
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
            blend_meta['spend_core_annual_plan'] = round(float(spend_annual_plan or 0.0), 2)
            blend_meta['spend_remaining'] = round(spend_remaining, 2)
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
