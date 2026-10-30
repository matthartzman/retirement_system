from __future__ import annotations
import sys as _sys


# ===== BEGIN data_parser.py =====

"""data_parser.py — CSV/JSON input mapping for the retirement engine.

Owns load_csv(), parse_client(), and build_plan_from_json(). No workbook
presentation code belongs here.
"""

import io
import datetime
import os
import re
import copy as _copy
from pathlib import Path

# Wall-clock reads route through platform_runtime.today() so a frozen fixture
# can pin the date; see that function's docstring for why data alone is not
# enough to make a projection reproducible.
from . import platform_runtime as _platform_runtime
from .csv_exchange import text_csv as _tcsv
from . import plan_dates as _plan_dates


# Fallback Social Security wage base used only when a plan's own
# ss_wage_base_base_year field is blank. The household field is expected to be
# populated per-plan (see reference_src/tax_update_dashboard.csv's
# ss_wage_base row for the current authoritative annual figure); this constant
# exists once so it can't drift across the CSV- and JSON-parsing code paths.
DEFAULT_SS_WAGE_BASE = 184500

# Roth optimizer discount rate, NOMINAL. The flows it discounts -- lifetime
# tax, estate tax, the ACA PTC loss, and the terminal-wealth component -- are
# all projected in nominal dollars, so the rate has to be nominal too.
#
# This used to fall through to c['inf'] (2.5%). Dividing nominal flows by
# inflation is a pure deflator: it restates the objective in today's purchasing
# power with NO time preference on top, i.e. a 0% real discount rate. That
# under-rewards locking in current tax rates, because future tax savings were
# discounted more slowly than the portfolio generating them compounds. 6.5% is
# roughly the expected long-run portfolio return -- what a dollar paid to the
# IRS today would otherwise have earned.
#
# Deliberately NOT tied to c['inf']: they are different quantities, and the
# coupling meant editing an inflation assumption silently retuned the
# optimizer's time preference.
DEFAULT_ROTH_TAX_DISCOUNT_RATE = 0.065

from .plan_data_registry import CLIENT_DATA_PART_FILES


def _client_data_csv_paths(path):
    p = Path(path)
    paths = [p]
    if p.name == "client_data.csv":
        for name in CLIENT_DATA_PART_FILES:
            part = p.parent / name
            if part.exists():
                paths.append(part)
    return paths

from . import taxes as _td  # consolidated from tax_data
from .tax_law import default_tax_law_dataset as _default_tax_law_dataset
from .money import decimal_from_user_value as _money_decimal, strict_float as _strict_float
import logging as _logging
_log = _logging.getLogger(__name__)
from .plan_config import ensure_engine_config
from . import core as _ar  # consolidated from account_registry
from . import optimization as _ao  # consolidated from allocation_optimizer
from . import allocation_policy as _ap
from .core import ASSET_CLASS_RETURNS, TAX_BASE_YEAR, statutory_rmd_start_age, require_residence_state_for_build  # consolidated from engine_core
from .market_data import PRICE_CACHE, fetch_price, prewarm_prices, set_fallback_prices, set_frozen_prices, configure_holdings_pricing, configure_api_keys  # consolidated from market_data_providers
from .workspace_context import active_workspace_id
from .roth_ui_build_guard import normalize_roth_policy, normalize_irmaa_guardrail_mode, percent_to_float, is_explicit_user_roth_policy, strategy_for_roth_policy
from .plan_data_migration import migrate_sectioned_data
from .plan_label_rules import canonical_label
from .engine_defaults import engine_defaults
try:
    from .system_config import load_system_config
except ImportError:  # direct execution fallback
    load_system_config = None

__all__ = [
    'load_csv',
    'parse_client',
    'build_plan_from_json',
    'validate_projection',
    'summarize_validation',
]


def _load_capital_market_income_assumptions() -> dict:
    """Read yield/qualified-dividend/tax-exempt assumptions from reference data.

    The projection falls back to conservative defaults, but the shipped
    capital-market reference table is the authoritative source when it contains
    distribution_yield, qualified_dividend_fraction, and tax_exempt_yield.
    """
    from .stores.ref_getters.cma import capital_market_rows
    out = {}
    for row in capital_market_rows():
        preset = str(row.get('preset') or 'BASELINE').strip().upper()
        cls = _ap.canonical_asset_class(row.get('asset_class') or '')
        if not cls:
            continue
        y = _n(row.get('distribution_yield',''), None)
        q = _n(row.get('qualified_dividend_fraction',''), None)
        te = _n(row.get('tax_exempt_yield',''), None)
        if y is None and q is None and te is None:
            continue
        out[(preset, cls)] = (
            max(0.0, float(y if y is not None else 0.0)),
            max(0.0, min(1.0, float(q if q is not None else 0.0))),
            max(0.0, float(te if te is not None else 0.0)),
        )
    return out

def _load_capital_market_return_assumptions() -> dict:
    """Read expected_return by (preset, asset_class) from reference data.

    Same table/shape as _load_capital_market_income_assumptions, just the
    return column instead of the income columns. Used to derive per-account
    (sleeve-level) growth rates from each account's actual holdings mix --
    see the account_returns block below.
    """
    from .stores.ref_getters.cma import capital_market_rows
    out = {}
    for row in capital_market_rows():
        preset = str(row.get('preset') or 'BASELINE').strip().upper()
        cls = _ap.canonical_asset_class(row.get('asset_class') or '')
        if not cls:
            continue
        ret = _n(row.get('expected_return', ''), None)
        if ret is None:
            continue
        out[(preset, cls)] = float(ret)
    return out


def _apply_allocation_projection_assumptions(c):
    """Apply allocation-mode choice without replacing economic assumptions.

    v8.3 originally translated the selected allocation mix directly into the
    engine-wide return/volatility. That made account balances compound at the
    raw capital-market-assumption return (for example ~8% instead of the
    configured 6%), which materially overstated account-level net worth.

    The configured Economic Assumptions return remains the absolute baseline.
    Allocation mode now applies only the *relative* return/volatility difference
    between the selected allocation and the user-defined allocation baseline:

    * user-defined mode: keep configured return/sigma unchanged.
    * optimizer mode: configured return plus optimizer-vs-user expected-return
      spread, and configured sigma scaled by optimizer-vs-user volatility ratio.

    This preserves the user's forecast calibration while still allowing the
    allocation toggle to have a measured projection impact.
    """
    try:
        selected_mode = c.get('allocation_selection_mode', 'user_target')
        selected = _ao.allocation_portfolio_stats(c, force_mode=selected_mode)
        baseline = _ao.allocation_portfolio_stats(c, force_mode='user_target')
        targets = selected.get('targets') or {}
        if not targets:
            return c

        base_ret = float(c.get('ret', 0.0) or 0.0)
        base_sigma = float(c.get('mc_sigma', 0.0) or 0.0)
        selected_ret = float(selected.get('expected_return', base_ret) or base_ret)
        selected_sigma = float(selected.get('volatility', base_sigma) or base_sigma)
        baseline_ret = float(baseline.get('expected_return', selected_ret) or selected_ret)
        baseline_sigma = float(baseline.get('volatility', selected_sigma) or selected_sigma)

        adjusted_ret = base_ret
        adjusted_sigma = base_sigma
        if selected.get('mode') != 'user_target':
            adjusted_ret = base_ret + (selected_ret - baseline_ret)
            if baseline_sigma > 0 and base_sigma > 0:
                adjusted_sigma = base_sigma * (selected_sigma / baseline_sigma)
            elif selected_sigma > 0:
                adjusted_sigma = selected_sigma

        # Guard against accidental capital-market-input mistakes causing the
        # projection to explode. 50 percentage points above the configured return
        # would indicate a data-entry or unit error, not a plausible tactical tilt.
        if abs(adjusted_ret - base_ret) > 0.50:
            raise ValueError(
                f"allocation return adjustment {adjusted_ret - base_ret:.4f} is outside sanity bounds"
            )

        c['configured_portfolio_nominal_return'] = base_ret
        c['configured_mc_sigma'] = base_sigma
        c['allocation_raw_expected_return'] = selected_ret
        c['allocation_raw_volatility'] = selected_sigma
        c['allocation_baseline_expected_return'] = baseline_ret
        c['allocation_baseline_volatility'] = baseline_sigma
        c['allocation_return_adjustment'] = adjusted_ret - base_ret
        c['allocation_volatility_ratio'] = (selected_sigma / baseline_sigma) if baseline_sigma else 1.0
        c['ret'] = adjusted_ret
        c['mc_sigma'] = adjusted_sigma
        c['allocation_projection_applied'] = True
        c['allocation_projection_mode'] = selected.get('mode')
        c['allocation_projection_label'] = selected.get('label')
        c['allocation_projection_expected_return'] = c['ret']
        c['allocation_projection_volatility'] = c['mc_sigma']
        c['allocation_projection_geometric_return'] = float(
            ((1.0 + c['ret']) / (1.0 + 0.5 * c['mc_sigma'] * c['mc_sigma']) - 1.0)
            if c['mc_sigma'] else c['ret']
        )
        c['allocation_projection_targets'] = dict(targets)
    except Exception as ex:
        c['allocation_projection_applied'] = False
        c['allocation_projection_error'] = str(ex)
    return c


# _resolve_auto_horizon_and_reapply and _resolve_holding_period_floors_and_
# reapply used to live here, but both call planning_engines.project() to run
# a preliminary projection -- parsing must not call the engine (system review
# 2026-08-04, architect finding `data-io-calls-the-engine`). They now live in
# report_compute.py as resolve_auto_horizon_and_reapply /
# resolve_holding_period_floors_and_reapply. parse_client() and
# build_plan_from_json() below still resolve both synchronously (same
# end-to-end behavior every existing caller and test depends on) via a
# function-scoped import -- deferred to call time, not module load time, so
# it doesn't create a data_io <-> report_compute import cycle (report_compute
# already imports parse_client/build_plan_from_json from this module).
def _resolve_auto_horizon_and_reapply(c):
    from .report_compute import resolve_auto_horizon_and_reapply
    return resolve_auto_horizon_and_reapply(c)


def _resolve_holding_period_floors_and_reapply(c):
    from .report_compute import resolve_holding_period_floors_and_reapply
    return resolve_holding_period_floors_and_reapply(c)


# Year-stamped label canonicalisation: src/plan_label_rules.py (single source, shared with csv_exchange).
_normalize_label = canonical_label

# ─────────────────────────────────────────────────────────────────────────────
# 1.  CSV LOADER
# ─────────────────────────────────────────────────────────────────────────────

def load_csv(path):
    # Plan Data is v1.0 canonical (pre-v1.0 auto-migration was dropped); readers
    # assume the current schema.
    data = {}   # {section: {subsection: {label: value}}}
    for csv_path in _client_data_csv_paths(path):
        if not Path(csv_path).exists():
            continue
        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            reader = _tcsv.dict_reader_stream(f)
            for row in reader:
                sec  = (row.get('section')    or '').strip()
                sub  = (row.get('subsection') or '').strip()
                lbl  = _normalize_label(row.get('label') or '')
                val  = (row.get('value')      or '').strip()
                if not sec or sec.startswith('#') or not lbl:
                    continue
                data.setdefault(sec, {}).setdefault(sub, {})[lbl] = val
    return data

def _v(data, section, subsection, label, default=''):
    try:
        return data[section][subsection][label]
    except KeyError:
        return default


def reserve_checking_import_warning(legacy_value, balances):
    """#339 spec §8 (2026-09-24 W-F Task F2): the retired Reserve Requirements
    "Checking accounts" field was never read by the engine -- ``cash_other``
    has always come from ``_Checking``-suffixed holdings accounts. Returns an
    import warning naming the stale amount when a plan still carries a
    non-zero legacy value with no such account to receive it, else None.
    """
    if not legacy_value or any(str(k).endswith('_Checking') for k in balances):
        return None
    return (
        f"Reserve Requirements had an unused Checking accounts value of "
        f"${legacy_value:,.0f} that the plan never applied. Add it as a "
        f"_Checking holdings account on Investment Holdings if it should count "
        f"toward the cash reserve."
    )

MC_ENGINE_MODE_DEFAULT = 'quick_vectorized'

def _mc_engine_mode_from_plan_data(data):
    """Resolve the plan's Monte Carlo engine to a canonical engine key.

    The DEFAULT when the plan does not state one (row absent, or the value is
    blank/whitespace) is the vectorized batched engine. That matches what every
    shipped plan already sets explicitly (``input/demo/client_policy.csv`` and
    ``tests/fixtures/csv_exchange/sample_plan_frozen/client_policy.csv`` both say
    ``quick_vectorized``), what ``planning_engines.monte_carlo()``'s own in-code
    fallback assumes (``vectorized_batched``), and what the test suite
    exercises. The exact-scalar path stays fully supported as an explicit
    opt-in and as the validation oracle the vectorized engine is checked
    against - see ``tests/test_mc_engine_fidelity_tolerance_unit.py``.

    An unrecognized value is passed through unchanged (as before), so a typo
    surfaces in diagnostics rather than being silently coerced.
    """
    raw = str(_v(data, 'Model Constants', 'Monte Carlo',
                 'mc_engine_mode', MC_ENGINE_MODE_DEFAULT) or '').strip().lower()
    if not raw:
        raw = MC_ENGINE_MODE_DEFAULT
    _mc_engine_map = {
        'advanced_exact_scalar': 'exact_scalar',
        'exact_scalar': 'exact_scalar',
        'quick_vectorized': 'vectorized',
        'vectorized': 'vectorized',
    }
    return _mc_engine_map.get(raw, raw)

def _n(v, default=0.0):
    # Boundary parse uses Decimal for money/percentage precision, then returns
    # a float execution copy for the retained numerical engine.
    if default is None and (v is None or str(v).strip() == ''):
        return None
    try:
        return _strict_float(v, float(default if default is not None else 0.0))
    except (ValueError, TypeError, ArithmeticError):
        _log.warning("unparseable number %r; using default %r", v, default)
        return default

def _b(v):
    return str(v).strip().upper() in ('TRUE','YES','1')

def _y(v, default=0):
    try:
        s = str(v).strip()
        if '/' in s:
            parts = s.split('/')
            return int(parts[-1]) if len(parts[-1])==4 else int(parts[2])
        if '-' in s and len(s) >= 4:
            return int(s[:4])
        return int(s)
    except Exception:
        return default

def _date_parts(v):
    """Return (year, month, day) for common plan-date strings, else None.

    Retirement dates are date-effective boundaries. A retirement date of
    1/1/2027 means earned income stops before 2027; a later date in 2027
    still allows modeled 2027 work income in the annual projection.

    Delegates to src/plan_dates.parse_plan_date (WI-401): a 2-digit year uses
    the single shared century pivot (yy > 40 -> 19yy, else 20yy, matching the
    UI/grid-save normalizer) instead of the old blanket +2000, and a bare YYYY
    keeps its long-standing Dec 31 reading.
    """
    return _plan_dates.parse_plan_date(v, bare_year_as='end')


def _apply_tax_assumptions(c, raw, scenario_raw=None):
    """Resolve plan tax levers (Auto vs override) into the engine config."""
    from . import tax_assumptions as _ta
    from .core import STATE_TAX_RULES as _rules
    resolved = _ta.resolve_tax_assumptions(
        raw, _n, state=c.get('state', ''), state_rules=_rules)
    _ta.apply_to_config(c, resolved)
    scen = _ta.resolve_law_scenario(
        (scenario_raw or {}).get('tax_law_scenario'),
        (scenario_raw or {}).get('higher_rates_start_year'),
        int(c.get('plan_start') or _platform_runtime.today().year), _n)
    c['law_scenario'] = scen
    c['tax_assumptions_effective']['tax_law_scenario'] = dict(scen)


def _month_year_parts(v):
    """Return (year, month) for a MM/YYYY (or M/YYYY, YYYY-MM) string, else
    None. Distinct from _date_parts, which requires a day component -- a
    Social Security claim date is only ever precise to the month."""
    s = str(v or '').strip()
    if not s:
        return None
    try:
        if '/' in s:
            parts = [int(float(x)) for x in s.split('/') if str(x).strip()]
            if len(parts) == 2:
                m, y = parts[0], parts[1]
                if y < 100:
                    y += 2000
                if 1 <= m <= 12:
                    return (y, m)
        if '-' in s:
            parts = [int(float(x)) for x in s.split('-') if str(x).strip()]
            if len(parts) == 2:
                y, m = parts[0], parts[1]
                if 1 <= m <= 12:
                    return (y, m)
    except Exception:
        pass
    return None


def _ss_claim_from_date_or_age(data, person, dob_yr, dob_month, legacy_default_age):
    """Resolve (claim_age, claim_year, claim_month, claim_age_precise) for one
    Social Security claimant.

    ``claim_date`` (MM/YYYY) is the primary input, replacing the older bare
    ``claim_age`` (an integer with no month, which forced every claim year
    to be treated as a full 12 months of benefits -- see
    deterministic_engine._ss_first_claim_year_month_fraction). When a real
    claim_date is present, claim_age is *derived* from it (claim_year -
    dob_yr) rather than read directly, so the two can never disagree.

    ``claim_age`` (the whole-year value) is kept for the SSA benefit-table
    lookup, which is genuinely keyed on whole ages (SSA quotes are only ever
    given for ages 62-70) -- that part of the design is not a defect.
    ``claim_age_precise`` is a *fractional* age (e.g. 66.333 for 4 months
    past 66) for use only where SSA's reduction/delayed-credit schedule is
    actually applied (_ss_claim_factor already interpolates by month; it was
    simply never given anything but a whole-year age). System review
    2026-09-07 finding N2: claim_year - dob_yr alone can misattribute up to
    11 months of credit/reduction (e.g. a claim_date of March for a
    November-birth-month claimant), a permanent, lifelong benefit-amount
    error -- claim_age_precise closes that gap without changing the
    whole-year claim_age used everywhere else (storage, UI, benefit-table
    lookup, reporting).

    Falls back to the legacy claim_age field (defaulting to age 70, this
    codebase's existing default) for plans that predate claim_date, using
    the claimant's own birth month for proration -- the same assumption
    _ss_first_claim_year_month_fraction relied on before claim_date existed.
    """
    parsed = _month_year_parts(_v(data, 'Social Security', person, 'claim_date', ''))
    if parsed:
        claim_year, claim_month = parsed
        claim_age = claim_year - dob_yr
        claim_age_precise = claim_age + (claim_month - dob_month) / 12.0
        return claim_age, claim_year, claim_month, claim_age_precise
    claim_age = int(_n(_v(data, 'Social Security', person, 'claim_age', legacy_default_age), 70))
    return claim_age, dob_yr + claim_age, dob_month, float(claim_age)


def _parse_member_dob(raw, label):
    """Parse a household member's date of birth via the shared plan-date rule.

    Raises ValueError (with a message naming the field) when the value is
    blank, uses an ambiguous 2-digit year, or cannot be parsed -- a DOB drives
    every age milestone and the plan horizon, so guessing is never safe.
    Returns (year, month, day).
    """
    s = str(raw or '').strip()
    if not s:
        raise ValueError(
            f'{label} is not set. A date of birth is required for every household '
            f'member (it drives every age milestone and the plan horizon). Enter it '
            f'as M/D/YYYY on the Household page (Plan Data field: {label}), then rebuild.'
        )
    if _plan_dates.has_two_digit_year(s):
        raise ValueError(
            f'{label} {s!r} has a 2-digit year, which is ambiguous for a date of birth. '
            f'Enter it as M/D/YYYY with a 4-digit year (Plan Data field: {label}).'
        )
    parts = _plan_dates.parse_plan_date(s)
    if parts is None:
        raise ValueError(
            f'{label} {s!r} is not a recognizable date. Enter it as M/D/YYYY '
            f'(Plan Data field: {label}).'
        )
    return parts


def _retirement_year(raw, default):
    """Calendar year of a retirement date, using the shared plan-date parser
    (so '1/1/27' is 2027, not 27); falls back to _y for anything else."""
    parts = _plan_dates.parse_plan_date(raw)
    return parts[0] if parts else _y(raw, default)


def _last_earned_income_year_from_retirement_date(v, default=0):
    """Convert retirement timing to the final year with earned income.

    A retirement date is the first date retired. Therefore January 1 of a
    year excludes that entire year from earned income. Non-January-1 dates
    keep the existing annual model behavior and include that calendar year.
    """
    parts = _date_parts(v)
    if not parts:
        return _y(v, default)
    year, month, day = parts
    if month == 1 and day == 1:
        return year - 1
    return year



# ─────────────────────────────────────────────────────────────────────────────
# 4.  DATA PARSING
# ─────────────────────────────────────────────────────────────────────────────

# Life-insurance policy types recognized in the "Insurance In Force" section.
_LIFE_POLICY_TYPES = {'term', 'whole', 'universal', 'ul', 'iul', 'vul', 'gul', 'life', 'permanent'}



# parse_advanced_modules() extracted to src/parsing/advanced_modules.py
# System review 2026-08-31, finding A5 / Wave 3 item 3.13 ("split
# parse_client into src/parsing/ siblings; move validation out"). Re-exported
# here so existing callers (`from src.data_io import parse_advanced_modules`)
# keep working unchanged.
from .parsing.advanced_modules import parse_advanced_modules  # noqa: F401

# parse_daf() extracted to src/parsing/daf.py
# System review 2026-08-31, finding A5 / Wave 3 item 3.13 ("split
# parse_client into src/parsing/ siblings; move validation out"). Re-exported
# here so existing callers (`from src.data_io import parse_daf`) keep working
# unchanged.
from .parsing.daf import parse_daf  # noqa: F401

# parse_note_receivable() extracted to src/parsing/note_receivable.py
# System review 2026-08-31, finding A5 / Wave 3 item 3.13 ("split
# parse_client into src/parsing/ siblings; move validation out"). Re-exported
# here so existing callers (`from src.data_io import parse_note_receivable`)
# keep working unchanged.
from .parsing.note_receivable import parse_note_receivable  # noqa: F401

# _insurance_policy_premium_sum() extracted to src/parsing/insurance.py
# System review 2026-08-31, finding A5 / Wave 3 item 3.13 ("split
# parse_client into src/parsing/ siblings; move validation out"). Re-exported
# here so existing callers (`from src.data_io import
# _insurance_policy_premium_sum`) keep working unchanged.
from .parsing.insurance import _insurance_policy_premium_sum  # noqa: F401

# parse_estate_planning() extracted to src/parsing/estate_planning.py
# System review 2026-08-31, finding A5 / Wave 3 item 3.13 ("split
# parse_client into src/parsing/ siblings; move validation out"). Re-exported
# here so existing callers (`from src.data_io import parse_estate_planning`)
# keep working unchanged.
from .parsing.estate_planning import parse_estate_planning  # noqa: F401

# parse_account_draw_priority() extracted to src/parsing/withdrawal_order.py
# Ticket 312 (see documentation/archive/superpowers/plans/
# 2026-09-09-parse-client-remaining-sections-design.md, section 5).
# Re-exported here so existing callers
# (`from src.data_io import parse_account_draw_priority`) keep working
# unchanged.
from .parsing.withdrawal_order import parse_account_draw_priority  # noqa: F401

# parse_hsa_policy() / parse_hsa_withdrawal_schedule() extracted to
# src/parsing/hsa_policy.py. Ticket 312, per
# documentation/archive/superpowers/plans/2026-09-09-parse-client-remaining-sections-design.md
# (section 1, "HSA Policy scalars"). Re-exported here so existing callers
# (`from src.data_io import parse_hsa_policy`) keep working unchanged.
from .parsing.hsa_policy import parse_hsa_policy, parse_hsa_withdrawal_schedule  # noqa: F401

# parse_allocation_optimizer_inputs() extracted to
# src/parsing/allocation_optimizer_inputs.py. Ticket 312 (design doc
# documentation/archive/superpowers/plans/2026-09-09-parse-client-remaining-sections-design.md,
# section 4). Re-exported here so existing callers (`from src.data_io import
# parse_allocation_optimizer_inputs`) keep working unchanged.
from .parsing.allocation_optimizer_inputs import parse_allocation_optimizer_inputs  # noqa: F401

# parse_roth_conversion_policy() extracted to src/parsing/roth_conversion_policy.py
# Ticket 312 (documentation/archive/superpowers/plans/2026-09-09-parse-client-remaining-sections-design.md,
# section 3). Re-exported here so existing callers (`from src.data_io import
# parse_roth_conversion_policy`) keep working unchanged.
from .parsing.roth_conversion_policy import parse_roth_conversion_policy  # noqa: F401

# parse_withdrawal_spending_policy() extracted to src/parsing/withdrawal_policy.py
# Ticket 312 ("parse_client() remaining sections", design doc
# documentation/archive/superpowers/plans/2026-09-09-parse-client-remaining-sections-design.md,
# section 2: "Withdrawal Policy bracket-target/spending-decline"). Re-exported
# here so existing callers (`from src.data_io import
# parse_withdrawal_spending_policy`) keep working unchanged.
from .parsing.withdrawal_policy import parse_withdrawal_spending_policy  # noqa: F401

# WP12.3: the Rental Properties parse boundary (source rows -> c['rental_properties']
# and the optional household c['mfs_lived_apart']); see src/parsing/rental_properties.py.
from .parsing.rental_properties import RentalPropertyInputError, parse_rental_properties  # noqa: F401

from .parsing.client_sections import (  # noqa: F401
    account_cma_return, add_liquidity_rule, load_qlac, load_security_classes,
    load_stream, nickname, ss_benefit_table,
    parse_household_and_pricing,
    parse_members_and_economics,
    parse_cashflow_and_retirement,
    parse_spending_and_home_sale,
    parse_housing_and_other_assets,
    parse_liquidity_and_trust,
    parse_plan_settings,
    parse_model_constants,
    parse_ltc_and_holdings,
    parse_hsa_schedule_and_account_income,
    parse_capital_market_returns,
    parse_harvest_policies_and_lots,
)


def parse_client(data, url_template, *, skip_live_pricing=False):
    """Parse sectioned client data into an engine-ready config dict.

    ``skip_live_pricing``: use whatever's already in the in-process price
    cache (or 0.0 if never fetched) instead of making a live network call per
    held symbol. For callers that only need config/toggle values, not
    accurate current holdings valuation (#234: this was 12+ of ~13s on every
    /api/config/rows call, refetched on every save/navigation for a value
    nothing downstream of that call used).
    """
    c = {}
    system_data = {}
    if load_system_config is not None:
        try:
            system_data = load_system_config()
        except Exception:
            system_data = {}

    _engine = engine_defaults()

    # Runtime settings (app.db) win; then the plan's own row; then the engine-knob code default.
    def _sv(section, subsection, label, default=''):
        return _v(system_data, section, subsection, label,
                  _v(data, section, subsection, label, _v(_engine, section, subsection, label, default)))

    # Upgrade any legacy husband/wife plan shapes to the member_1/member_2
    # schema before reading. The centralized, tested at-rest migration (see
    # src/plan_data_migration.py) replaces the former inline key aliasing so the
    # backward-compat logic lives in one place instead of scattered here and in
    # domain_models.py.
    migrate_sectioned_data(data)

    _w_dob_error = parse_household_and_pricing(data, c, _sv)

    parse_members_and_economics(data, c, _w_dob_error)

    parse_cashflow_and_retirement(data, c)
    parse_spending_and_home_sale(data, c)

    parse_housing_and_other_assets(data, c)
    parse_liquidity_and_trust(data, c)

    parse_plan_settings(data, c, _sv, system_data)
    parse_model_constants(data, c)

    LotEngine, lots_by_account, lots_reconcile = parse_ltc_and_holdings(data, c)

    _class_income_defaults, _security_classes = parse_hsa_schedule_and_account_income(data, c, lots_by_account, lots_reconcile, skip_live_pricing, url_template)
    parse_capital_market_returns(data, c, _class_income_defaults, _security_classes, skip_live_pricing, url_template)
    parse_harvest_policies_and_lots(data, c, LotEngine, lots_by_account)

    _apply_allocation_projection_assumptions(c)
    c = ensure_engine_config(c, source='sectioned')
    _resolve_auto_horizon_and_reapply(c)
    _resolve_holding_period_floors_and_reapply(c)
    return c


def build_plan_from_json(plan, url_template=''):
    """Build the engine's `c` dict from a wizard JSON plan.

    This is the generic-calculator entry point. The wizard collects user input
    as a JSON dict and this function maps it to the same `c` dict that
    parse_client() produces from CSVs. The projection engine doesn't care
    which path built `c`.
    """
    import datetime

    def _looks_like_sectioned_client_data(obj):
        if not isinstance(obj, dict):
            return False
        section_keys = {'Household', 'Economic Assumptions', 'Model Constants',
                        'Social Security', 'Assets', 'Income', 'Spending',
                        'Withdrawal Policy', 'Estate Planning'}
        if any(k in obj for k in section_keys):
            return True
        # Exported section/subsection data usually has nested dictionaries two levels deep.
        return any(isinstance(v, dict) and any(isinstance(x, dict) for x in v.values()) for v in obj.values())

    if _looks_like_sectioned_client_data(plan):
        c_sectioned = parse_client(plan, url_template)
        if sum(float(v or 0.0) for v in c_sectioned.get('balances', {}).values()) <= 0:
            raise ValueError('Sectioned plan JSON parsed but produced no starting account balances; check client_assets/client_holdings data.')
        return c_sectioned

    c = {}

    # ── Members ───────────────────────────────────────────────────────────
    members_in = plan.get('members', [{'name': 'You', 'dob_year': 1965,
                                        'retirement_year': _platform_runtime.today().year + 4, 'mortality_age': 90}])
    m1 = members_in[0]
    c['h_name']     = m1.get('name', 'Member 1')
    c['h_nick']     = str(m1.get('nickname') or '').strip() or str(c['h_name']).strip().split(' ')[0]
    c['h_dob_yr']   = int(m1.get('dob_year', 1965))
    # dob_month is optional in the wizard JSON; default 1 preserves the prior
    # binary Medicare/pre-65 switch behavior (see _medicare_month_fraction).
    c['h_dob_month']= int(m1.get('dob_month', 1) or 1)
    c['h_ret_yr']   = int(m1.get('retirement_year', _platform_runtime.today().year + 4))
    c['h_mort_age'] = int(m1.get('mortality_age', 90))
    c['h_death_yr'] = c['h_dob_yr'] + c['h_mort_age']

    if len(members_in) > 1:
        m2 = members_in[1]
        c['w_name']     = m2.get('name', 'Member 2')
        c['w_nick']     = str(m2.get('nickname') or '').strip() or str(c['w_name']).strip().split(' ')[0]
        c['w_dob_yr']   = int(m2.get('dob_year', 1965))
        c['w_dob_month']= int(m2.get('dob_month', 1) or 1)
        c['w_ret_yr']   = int(m2.get('retirement_year', _platform_runtime.today().year + 4))
        c['w_mort_age'] = int(m2.get('mortality_age', 92))
        c['w_death_yr'] = c['w_dob_yr'] + c['w_mort_age']
    else:
        c['w_name'] = ''
        c['w_nick'] = ''
        c['w_dob_yr'] = c['h_dob_yr']
        c['w_dob_month'] = c['h_dob_month']
        c['w_ret_yr'] = c['h_ret_yr']
        c['w_mort_age'] = 0
        c['w_death_yr'] = c['h_dob_yr']

    c['members'] = [{'name': c['h_name'], 'nickname': c['h_nick'], 'role': 'member_1',
                     'dob_yr': c['h_dob_yr'], 'dob_month': c['h_dob_month'], 'retire_yr': c['h_ret_yr'],
                     'mortality_age': c['h_mort_age'], 'death_yr': c['h_death_yr']}]
    if c['w_name']:
        c['members'].append({'name': c['w_name'], 'nickname': c['w_nick'], 'role': 'member_2',
                             'dob_yr': c['w_dob_yr'], 'dob_month': c['w_dob_month'], 'retire_yr': c['w_ret_yr'],
                             'mortality_age': c['w_mort_age'], 'death_yr': c['w_death_yr']})
    c['household_size'] = len(c['members'])

    # ── Filing & State ────────────────────────────────────────────────────
    filing = plan.get('filing_status', 'MFJ' if c['household_size'] > 1 else 'Single')
    c['filing_status']  = filing if filing in _td.FILING_STATUSES else ('MFJ' if c['household_size'] > 1 else 'Single')
    c['survivor_filing'] = plan.get('survivor_filing_status', 'Single')
    # See parse_client() for what this scales and, more importantly, what it
    # must not scale (housing, wellness, LTC).
    c['survivor_spend_factor'] = min(1.0, max(0.0, _n(
        plan.get('survivor_spend_factor', 0.65), 0.65)))
    # Item 291 (found during the tickets-284-291 merge, 2026-08-19):
    # build_plan_from_json is a second real-build entry point parse_client's
    # own Class 1 gate never covered -- it defaulted a missing state to
    # 'Illinois' exactly like parse_client used to, silently. Closed the same
    # way: no default, gated by the same require_residence_state_for_build.
    c['state']          = plan.get('state', '')
    require_residence_state_for_build(c['state'])
    c['trust_type']     = 'revocable living trust'

    # ── Timeline ──────────────────────────────────────────────────────────
    c['plan_start'] = plan.get('plan_start', _platform_runtime.today().year)
    c['plan_end']   = max(c['h_death_yr'], c.get('w_death_yr', c['h_death_yr']))

    # ── Economic assumptions ──────────────────────────────────────────────
    a = plan.get('assumptions', {})
    c['ret']             = a.get('return_rate', 0.074)
    c['inf']             = a.get('inflation', 0.025)
    _apply_tax_assumptions(c, {
        'fed_tax_bracket_inflator': a.get('bracket_inflation'),
        'state_income_tax_rate': a.get('state_income_tax_rate'),
    }, {
        'tax_law_scenario': a.get('tax_law_scenario'),
        'higher_rates_start_year': a.get('higher_rates_start_year'),
    })
    c['ret_eq']          = a.get('equity_return', 0.10)
    c['ret_bond']        = a.get('bond_return', 0.04)
    c['mc_vol']          = a.get('mc_volatility', 0.15)
    c['mc_paths']        = int(a.get('mc_paths', 1000))
    c['ss_cola']         = a.get('ss_cola', 0.023)
    c['ann_pv_rate']     = a.get('annuity_pv_discount_rate')

    # ── Accounts & Balances ───────────────────────────────────────────────
    accounts_in = plan.get('accounts', [])
    balances = {}
    for acct in accounts_in:
        acct_id = acct.get('id', acct.get('label', f'Acct_{len(balances)+1}').replace(' ', '_'))
        balances[acct_id] = float(acct.get('balance', 0))
    c['positions'] = {aid: {'CASH': b} for aid, b in balances.items()}
    if not balances or sum(float(v or 0.0) for v in balances.values()) <= 0:
        raise ValueError('No account balances were supplied. Use the flat wizard schema with accounts[] or the section/subsection client_data JSON schema.')
    c['balances'] = balances
    c['cash_other'] = sum(v for k, v in balances.items()
                          if 'checking' in k.lower() or 'saving' in k.lower())

    # Build account registry
    c['account_registry'] = _ar.build_registry_from_json(accounts_in, c['members'])
    c['all_acct_ids']     = _ar.all_ids(c['account_registry'])
    c['pre_tax_ids']      = _ar.ids_by_tax(c['account_registry'], 'pre_tax')
    c['roth_ids']         = _ar.ids_by_tax(c['account_registry'], 'roth')
    c['taxable_ids']      = _ar.taxable_ids(c['account_registry'])
    c['hsa_ids']          = _ar.hsa_ids(c['account_registry'])
    c['cash_ids']         = _ar.ids_by_tax(c['account_registry'], 'cash')
    c['invest_ids']       = _ar.all_investment_ids(c['account_registry'])

    # ── HSA Policy ────────────────────────────────────────────────────────
    # The flat wizard JSON schema has no HSA Policy section, so these are
    # the same conservative defaults parse_client() uses for the CSV path.
    c['hsa_beneficiary_type'] = 'spouse'
    c['hsa_consume_by'] = 'second_death_p90'
    c['hsa_expense_bank'] = None
    c['hsa_nonqualified_treatment'] = 'block'
    c['hsa_state_conformity'] = True

    # ── Income ────────────────────────────────────────────────────────────
    inc = plan.get('income', {})
    c['earned']       = inc.get('earned_income', 0)
    c['earned_end']   = c['h_ret_yr']
    c['earn_growth']  = inc.get('income_growth', 0.03)
    c['se_pct']       = inc.get('self_employment_pct', 0)
    c['qbi_pct']      = inc.get('qbi_pct', 0)
    c['h_ss_pia']     = inc.get('h_ss_pia', inc.get('ss_benefit_1', 0))
    c['w_ss_pia']     = inc.get('w_ss_pia', inc.get('ss_benefit_2', 0))
    c['h_ss70']       = inc.get('h_ss70', inc.get('ss_benefit_1_age70', c.get('h_ss_pia', 0)))
    c['w_ss70']       = inc.get('w_ss70', inc.get('ss_benefit_2_age70', c.get('w_ss_pia', 0)))
    c['ss_claim_age'] = inc.get('ss_claim_age', 70)
    c['h_ss_claim_age'] = inc.get('h_ss_claim_age', c['ss_claim_age'])
    c['w_ss_claim_age'] = inc.get('w_ss_claim_age', c['ss_claim_age'])
    c['h_ss_start']   = c['h_dob_yr'] + c['h_ss_claim_age']
    c['w_ss_start']   = c['w_dob_yr'] + c['w_ss_claim_age'] if c['w_name'] else 9999

    # Pension & Annuities (defaults: none)
    _empty_stream = lambda: {'first_yr': 9999, 'init_pmt': 0, 'base': 0,
        'div_rate': 0.0575, 'add_pct': 0.50, 'deferral_years': 0,
        'deferral_dampening': 0.55, 'reserve_factor': 0.853,
        'owner': 'husband', 'life': 'single',
        'annuitant_dob_yr': c['h_dob_yr'], 'recovery_age': 86,
        'annuity_calib': _td.DEFAULT_ANNUITY_CALIB}
    c['wife_pension'] = _empty_stream()
    if inc.get('pension_monthly'):
        c['wife_pension']['first_yr'] = inc.get('pension_start_year', c['plan_start'])
        c['wife_pension']['init_pmt'] = inc['pension_monthly']
    for key in ['wife_single', 'wife_joint', 'h_single', 'h_joint']:
        c[key] = _empty_stream()
    # #295: QLAC defaults (disabled/no premium) for the JSON/wizard config
    # path -- see parse_client's load_qlac() for the CSV path's equivalent.
    for key, owner_dob in (('h_qlac', c['h_dob_yr']), ('wife_qlac', c['w_dob_yr'])):
        c[key] = _empty_stream()
        c[key]['annuitant_dob_yr'] = owner_dob
        c[key].update({'enabled': False, 'premium': 0.0, 'source_account': '',
                        'purchase_year': c['plan_start'], 'death_benefit_pct': 0.0})
    c['ann_recovery_age'] = 86
    c['ann_db'] = {}
    c['annuity_calib'] = _td.DEFAULT_ANNUITY_CALIB
    c['note_face'] = 0; c['note_rate'] = 0; c['note_last'] = c['plan_start']
    c['note_princ_sched'] = {}

    # ── Spending ──────────────────────────────────────────────────────────
    sp = plan.get('spending', {})
    c['spend_base']         = sp.get('annual_base', 80000)
    c['core_spending_growth_mode'] = sp.get('core_spending_growth_mode', 'cpi')
    c['core_spending_manual_growth_rate'] = sp.get('core_spending_manual_growth_rate', 0.0)
    c['spend_inf'] = c['core_spending_manual_growth_rate'] if c['core_spending_growth_mode'] == 'manual_override' else c.get('inf', 0.025)
    c['rec_extra']          = sp.get('recreational', 0)
    c['rec_end']            = sp.get('recreational_end_year', c['plan_start'] + 10)
    c['lump_events']        = {int(e['year']): float(e['amount']) for e in sp.get('lump_events', [])}
    c['mort_pmt']           = sp.get('mortgage_payment', 0)
    c['real_estate_tax_base'] = sp.get('annual_real_estate_taxes', sp.get('real_estate_taxes', plan.get('property_tax', 0)))
    c['real_estate_tax_growth_rate'] = sp.get('real_estate_tax_annual_adjustment_pct', sp.get('real_estate_tax_growth_rate', c.get('inf', 0.025)))
    c['mort_end']           = sp.get('mortgage_end_year', c['plan_start'])
    c['hc_base']            = sp.get('wellness_annual', 8000)
    c['hc_inf']             = sp.get('wellness_inflation', 0.05)
    c['freeze_yr']          = sp.get('spending_freeze_year', c['plan_start'] + 15)

    # ── Home & Assets ─────────────────────────────────────────────────────
    c['home_val']     = plan.get('home_value', 0)
    c['home_basis']   = plan.get('home_basis', 0)
    c['home_appr']    = plan.get('home_appreciation', 0.03)
    c['mortgage_bal'] = plan.get('mortgage_balance', 0)
    c['home_sale_yr'] = plan.get('home_sale_year', 0)
    c['autos']        = plan.get('auto_value', 0)
    c['startup_eq']   = plan.get('startup_equity', 0)

    # ── Policy ────────────────────────────────────────────────────────────
    c['roth_policy']        = a.get('roth_policy', 'optimize_terminal_tax')
    c['roth_target_rate']   = a.get('roth_target_rate', 0.24)
    c['withdrawal_bracket_target_rate'] = a.get('withdrawal_bracket_target_rate', 0.24)
    _sp = str(a.get('spending_policy', 'fixed_real') or 'fixed_real').strip().lower()
    c['spending_policy'] = _sp if _sp in ('fixed_real', 'guyton_klinger', 'floor_ceiling_band') else 'fixed_real'
    c['spending_phase_decline_pct'] = a.get('spending_phase_decline_pct', 0.0)
    c['spending_phase_start_age'] = a.get('spending_phase_start_age', 0)
    c['spending_phase_end_age'] = a.get('spending_phase_end_age', 0)
    c['roth_irmaa_cap']     = True
    c['roth_fixed_amount']  = a.get('roth_fixed_amount', 50000)
    c['roth_optimize_terminal_weight'] = a.get('roth_optimize_terminal_weight', 1.0)
    c['roth_optimize_tax_weight'] = a.get('roth_optimize_lifetime_tax_weight', 0.25)
    c['roth_optimize_terminal_tax_rate'] = a.get('roth_optimize_terminal_pretax_tax_rate', 0.24)
    # Item 4.3: assumed beneficiary filing status for the derived effective
    # 10-year-rule heir ordinary tax rate (see parse_client for the CSV path).
    _heir_filing_json = str(a.get('roth_heir_filing_status', 'Single') or 'Single').strip()
    c['roth_heir_filing_status'] = _heir_filing_json if _heir_filing_json in ('Single','MFJ','HOH','MFS') else 'Single'
    c['roth_heir_other_taxable_income'] = a.get('roth_heir_other_taxable_income', 200000.0)
    c['roth_brk']           = c['roth_target_rate']
    # -1 matches the CSV path's schema-documented default (see parse_client
    # above) so conversion_window_end_year's default-vs-explicit signal
    # (conv_window_offset == -1) is consistent across both config paths.
    c['conv_window_offset'] = a.get('conv_window_offset', -1)
    c['forced_roth']        = {}
    c['liquidity_buffer_schedule'] = []
    for rec in a.get('liquidity_buffer_schedule', a.get('reserve_schedule', [])) or []:
        if not isinstance(rec, dict):
            continue
        c['liquidity_buffer_schedule'].append({
            'start_year': int(rec.get('start_year') or c['plan_start']),
            'end_year': int(rec.get('end_year') or 9999),
            'years_of_expenses': max(0.0, float(rec.get('years_of_expenses', rec.get('years_of_expenses_in_trust', 0)) or 0)),
        })
    c['liquidity_buffer_schedule'].sort(key=lambda x: (x['start_year'], x['end_year']))
    c['near_term_buffer_years'] = a.get('buffer_years_near', 0)
    c['long_term_buffer_years'] = a.get('buffer_years_far', 0)
    c['near_term_buffer_end_year'] = a.get('buffer_end_year', c['plan_start'])
    if c['liquidity_buffer_schedule']:
        _first = c['liquidity_buffer_schedule'][0]
        _last = c['liquidity_buffer_schedule'][-1]
        c['near_term_buffer_years'] = _first['years_of_expenses']
        c['near_term_buffer_end_year'] = _first['end_year'] if _first['end_year'] != 9999 else c['plan_start']
        c['long_term_buffer_years'] = _last['years_of_expenses']
    c['trust_gain_fraction'] = a.get('ltcg_gain_fraction', 0.50)

    # ── Tax Constants ─────────────────────────────────────────────────────
    # RMD start age: the flat-wizard JSON schema exposes one shared
    # 'rmd_start_age' assumption (no per-member field). When unset, each member
    # gets their OWN statutory default from date of birth (SECURE 2.0 ramp via
    # statutory_rmd_start_age) rather than forcing both members onto one value.
    # When the wizard field IS set, it is honored as an explicit override for
    # both members (matching its historical single-value semantics), and a
    # non-blocking advisory warning is recorded if it disagrees with either
    # member's statutory default.
    _h_rmd_statutory = statutory_rmd_start_age(c['h_dob_yr'])
    _w_rmd_statutory = statutory_rmd_start_age(c['w_dob_yr'])
    _rmd_raw = a.get('rmd_start_age')
    if _rmd_raw is None or str(_rmd_raw).strip() == '':
        c['rmd_start_age']   = _h_rmd_statutory  # primary-member anchor; matches conversion_window_end_year
        c['h_rmd_start_age'] = _h_rmd_statutory
        c['w_rmd_start_age'] = _w_rmd_statutory
    else:
        _rmd_explicit = int(_rmd_raw)
        c['rmd_start_age']   = _rmd_explicit
        c['h_rmd_start_age'] = _rmd_explicit
        c['w_rmd_start_age'] = _rmd_explicit
        c['rmd_start_age_warnings'] = c.get('rmd_start_age_warnings') or []
        if _rmd_explicit != _h_rmd_statutory:
            c['rmd_start_age_warnings'].append({
                'code': 'RMD_START_AGE_OVERRIDE_DISAGREES_WITH_STATUTORY',
                'severity': 'WARN',
                'message': (f"{c.get('h_nick') or c.get('h_name') or 'Member 1'}'s RMD start age "
                            f"is set to {_rmd_explicit}, but the statutory default for a "
                            f"{c['h_dob_yr']} birth year is {_h_rmd_statutory} (SECURE 2.0)."),
                'action': 'Confirm the override is intentional; otherwise clear it to use the statutory default.',
            })
        if c.get('w_name') and _rmd_explicit != _w_rmd_statutory:
            c['rmd_start_age_warnings'].append({
                'code': 'RMD_START_AGE_OVERRIDE_DISAGREES_WITH_STATUTORY',
                'severity': 'WARN',
                'message': (f"{c.get('w_nick') or c.get('w_name') or 'Member 2'}'s RMD start age "
                            f"is set to {_rmd_explicit}, but the statutory default for a "
                            f"{c['w_dob_yr']} birth year is {_w_rmd_statutory} (SECURE 2.0)."),
                'action': 'Confirm the override is intentional; otherwise clear it to use the statutory default.',
            })
    c['rollover_yr']       = a.get('rollover_year', c['plan_start'] + 5)
    c['payroll_wage_base'] = a.get('ss_wage_base', DEFAULT_SS_WAGE_BASE)
    c['payroll_ee_rate']   = 0.0765
    c['ltcg_0_top']        = _td.LTCG_BRACKETS_BASE_YEAR.get(c['filing_status'], {}).get('zero_top', 98900)
    c['ltcg_15_top']       = _td.LTCG_BRACKETS_BASE_YEAR.get(c['filing_status'], {}).get('fifteen_top', 613700)
    c['niit_threshold']    = _td.NIIT_THRESHOLD.get(c['filing_status'], 250000)
    c['tax_constants_registry'] = _td.load_tax_constants()
    c['tax_provenance']    = dict(_td.TAX_YEAR_PROVENANCE)
    c['tax_table_currency_warnings'] = _td.tax_table_currency_warnings(max_lag_years=int(c.get('tax_table_currency_max_lag_years', 1) or 1))

    # ── Estate ────────────────────────────────────────────────────────────
    _fed_per_person = _default_tax_law_dataset().latest_value('federal_estate_basic_exclusion').value
    c['fed_exempt']    = plan.get('estate_federal_exemption', _fed_per_person * (1 if c['household_size'] == 1 else 2))
    c['state_exempt']  = plan.get('estate_state_exemption', 4000000)
    c['gift_exclusion'] = 19000; c['basis_stepup'] = True
    c['state_estate']  = True; c['gifting_plan'] = {}

    # ── Defaults for optional subsystems ──────────────────────────────────
    c['scenarios'] = plan.get('scenarios', {})
    c['daf_enabled'] = False
    c['daf_use_start'] = 9999; c['daf_use_end'] = 9999; c['daf_use_amount'] = 0
    c['ltc_enabled'] = False; c['ltc_annual_prem'] = 0; c['ltc_start_year'] = 9999
    c['life_policies'] = []
    c['auto_dep_yrs'] = plan.get('auto_depreciation_years', 7)
    c['sehi'] = 0.0
    c['sehi_derived_from_wellness'] = True
    c['il_exempt'] = plan.get('estate_state_exemption', 4000000)
    c['prop_tax'] = c.get('real_estate_tax_base', plan.get('property_tax', 0))
    c['hc_start_yr'] = a.get('wellness_start_year', c['plan_start'])
    c['hc_65_adj'] = a.get('wellness_65_adjustment', 0.6)
    c['rec_start'] = plan.get('recreational_start_year', c['plan_start'])
    c['cs_amount'] = 0  # charitable strategies
    c['cs_start'] = 9999; c['cs_end'] = 9999; c['cs_type'] = ''
    # Mortgage schedule
    c['mort_schedule'] = {}; c['mortgage_bal'] = plan.get('mortgage_balance', 0)
    # Payroll / SE / Business
    c['ss_ee_rate'] = 0.062; c['ss_se_rate'] = 0.124
    c['med_ee_rate'] = 0.0145; c['med_se_rate'] = 0.029
    c['add_med_rate'] = 0.009; c['add_med_thr'] = 200000
    c['ss_wage_base'] = a.get('ss_wage_base', DEFAULT_SS_WAGE_BASE)
    c['se_factor'] = 0.9235; c['se_half_ded'] = True
    c['scorp_salary'] = 0; c['biz_exp'] = 0; c['entity'] = 'none'
    c['qbi_elig'] = False; c['k401_mo'] = 0; c['k401_lim'] = 23500
    # Earned income
    c['earn_inc'] = c['earn_growth']  # annual growth rate (not the income amount!)
    c['earn_start'] = c['plan_start']
    c['earn_end'] = c['earned_end']; c['js_pct'] = 0
    # SS age-70 monthly benefit
    c['h_ss70'] = c['h_ss_pia']; c['w_ss70'] = c.get('w_ss_pia', 0)
    c['ss_surv'] = a.get('ss_survivor_pct', 1.0)
    # Home
    c['home_off'] = 0; c['home_basis'] = plan.get('home_basis', c.get('home_val', 0) * 0.5)
    c['home_sell_cost_pct'] = 0.06; c['sec121'] = 500000
    c['home_proj'] = c['home_val']; c['home_proj_end'] = c['plan_end']
    c['home_sale_px'] = 0
    # HSA
    c['hsa_contrib_base'] = a.get('hsa_contribution', 0)
    c['hsa_last_contrib'] = a.get('hsa_last_year', c['plan_start'])
    c['hsa_win_start'] = a.get('hsa_window_start', c['plan_start'])
    c['hsa_win_end'] = a.get('hsa_window_end', c['plan_start'])
    if c.get('hsa_win_start', 9999) > c.get('hsa_win_end', 0):
        c['hsa_win_start'], c['hsa_win_end'] = c['hsa_win_end'], c['hsa_win_start']
    # Spending detail
    c['spending_freeze_yr'] = c['freeze_yr']
    c['vac'] = sp.get('vacation', 0); c['vac_end'] = sp.get('vacation_end_year', c['plan_start'] + 10)
    c['lump'] = c['lump_events']
    c['char_low'] = 0
    # Startup
    c['startup_gr'] = 0
    # Rollover
    c['rollover_401k_yr'] = c.get('rollover_yr', c['plan_start'] + 5)
    # Model flags
    c['model_niit'] = True
    c['mc_sigma'] = a.get('mc_volatility', 0.15)
    # ── Allocation Optimizer Inputs ──────────────────────────────────────
    c['risk_tolerance'] = a.get('risk_tolerance', 0)  # 0 = auto-derive
    c['asset_class_overrides'] = a.get('asset_class_overrides', {})
    c['asset_class_enabled'] = {_ap.canonical_asset_class(k): bool(v) for k, v in (a.get('asset_class_enabled', {}) or {}).items()}
    _flat_targets = a.get('allocation_target_pct') or a.get('allocation_targets') or dict(getattr(_ap, 'DEFAULT_ALLOCATION_TARGETS', {}))
    c['allocation_target_pct'] = {_ap.canonical_asset_class(k): v for k, v in (_flat_targets or {}).items()}
    c['allocation_target_sum'] = sum(float(v or 0) for v in c['allocation_target_pct'].values()) if isinstance(c['allocation_target_pct'], dict) else 0.0
    _flat_opt_override = a.get('allocation_optimizer_override_pct') or a.get('optimizer_override_targets') or {}
    c['allocation_optimizer_override_pct'] = {_ap.canonical_asset_class(k): v for k, v in (_flat_opt_override or {}).items()}
    c['allocation_optimizer_override_sum'] = sum(float(v or 0) for v in c['allocation_optimizer_override_pct'].values()) if isinstance(c['allocation_optimizer_override_pct'], dict) else 0.0
    c['allocation_selection_mode'] = _ap.normalize_allocation_mode(a.get('allocation_selection_mode', a.get('allocation_mode', 'user_target')))
    c['allocation_optimizer_comment'] = getattr(_ap, 'OPTIMIZER_RECOMMENDATION_COMMENT', '')
    c['holding_period_allocation_enabled'] = bool(a.get('holding_period_allocation_enabled', False))
    c['holding_period_floor_strength'] = float(a.get('holding_period_floor_strength', 1.0) or 1.0)
    c['real_loss_aware_risk_aversion'] = float(a.get('real_loss_aware_risk_aversion', 3.0) or 3.0)
    c['real_loss_aware_weight'] = float(a.get('real_loss_aware_weight', 1.0) or 1.0)
    c['capital_market_config'] = a.get('capital_market_config', {})
    c['asset_correlation_overrides'] = a.get('asset_correlation_overrides', {})
    c['human_capital_stability'] = a.get('human_capital_stability', 0.8)
    c['concentration_employer_stock'] = a.get('concentration_employer_stock', 0)
    c['concentration_real_estate'] = a.get('concentration_real_estate', 0)
    c['concentration_business'] = a.get('concentration_business', 0)
    c['glide_path'] = a.get('glide_path', 'target_date')
    c['inflation_sensitive_spending_pct'] = a.get('inflation_sensitive_spending_pct', 0.15)
    c['cash_target_pct'] = a.get('cash_target_pct', 0.05)
    # Scenario defaults
    c['scen_retire_salary'] = a.get('retire_later_salary', 50000)
    # Note receivable detail
    c['note_first'] = c['plan_start']; c['note_interest'] = {}
    c['note_princ'] = 0; c['note_princ_final'] = 0
    c['lots_by_account'] = {}; c['lots_reconcile'] = {}
    from .core import LotEngine  # consolidated from events
    c['lot_engine'] = LotEngine({}, PRICE_CACHE,
                                fallback_gain_fraction=c['trust_gain_fraction'])

    _apply_allocation_projection_assumptions(c)
    c = ensure_engine_config(c, source='flat_json')
    _resolve_auto_horizon_and_reapply(c)
    _resolve_holding_period_floors_and_reapply(c)
    return c



# ===== END data_parser.py =====



# ===== validation_engine.py extracted to src/parsing/validation.py =====
# System review 2026-08-31, finding A5 / Wave 3 item 3.13 ("split
# parse_client into src/parsing/ siblings; move validation out"). Re-exported
# here so existing callers (`from src.data_io import summarize_validation`,
# `from ..data_io import validate_projection`, etc.) keep working unchanged.
from .parsing.validation import (  # noqa: F401
    ValidationFailure,
    _account_ids,
    _finite,
    summarize_validation,
    validate_projection,
)
