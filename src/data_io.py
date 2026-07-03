from __future__ import annotations
import sys as _sys


# ===== BEGIN data_parser.py =====

"""data_parser.py — CSV/JSON input mapping for the retirement engine.

Owns load_csv(), parse_client(), and build_plan_from_json(). No workbook
presentation code belongs here.
"""

import csv
import datetime
import os
import re
import copy as _copy
from pathlib import Path


CLIENT_DATA_PART_FILES = [
    "client_household.csv",
    "client_income.csv",
    "client_spending.csv",
    "client_assets.csv",
    "client_policy.csv",
    "client_insurance_estate.csv",
    "client_optional_functions.csv",
    "asset_class_optimizer_controls.csv",
]


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
from .money import decimal_from_user_value as _money_decimal
from .plan_config import ensure_engine_config
from . import core as _ar  # consolidated from account_registry
from . import optimization as _ao  # consolidated from allocation_optimizer
from . import allocation_policy as _ap
from .core import ASSET_CLASS_RETURNS, TAX_BASE_YEAR  # consolidated from engine_core
from .market_data import PRICE_CACHE, fetch_price, set_fallback_prices, set_frozen_prices, configure_holdings_pricing, configure_api_keys  # consolidated from market_data_providers
from .workspace_context import candidate_input_files, active_workspace_id
from . import platform_runtime as _platform_runtime
from .roth_ui_build_guard import normalize_roth_policy, normalize_irmaa_guardrail_mode, percent_to_float, is_explicit_user_roth_policy, strategy_for_roth_policy
try:
    from .system_config import load_system_config
except Exception:  # direct execution fallback
    load_system_config = None




def _load_capital_market_income_assumptions() -> dict:
    """Read yield/qualified-dividend/tax-exempt assumptions from reference data.

    The projection falls back to conservative defaults, but the editable
    capital_market_assumptions.csv is the authoritative source when it contains
    distribution_yield, qualified_dividend_fraction, and tax_exempt_yield.
    """
    path = Path(__file__).resolve().parent.parent / 'reference_data' / 'capital_market_assumptions.csv'
    out = {}
    if not path.exists():
        return out
    try:
        with path.open(newline='', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
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
    except Exception:
        return {}
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


_YEAR_LABEL_PATTERNS = [
    (re.compile(r'^annual_401k_limit_\d{4}$'), 'annual_401k_limit_base_year'),
    (re.compile(r'^annual_spending_\d{4}$'), 'annual_spending_base_year'),
    (re.compile(r'^balance_\d{1,2}_\d{1,2}_\d{4}$'), 'balance_as_of_plan_start'),
    (re.compile(r'^value_\d{1,2}_\d{1,2}_\d{4}$'), 'value_as_of_plan_start'),
    (re.compile(r'^family_annual_limit_\d{4}$'), 'family_annual_limit_base_year'),
    (re.compile(r'^self_only_annual_limit_\d{4}$'), 'self_only_annual_limit_base_year'),
    (re.compile(r'^coverage_\d{4}_family_months$'), 'coverage_base_year_family_months'),
    (re.compile(r'^coverage_\d{4}_self_only_months$'), 'coverage_base_year_self_only_months'),
    (re.compile(r'^ss_wage_base_\d{4}$'), 'ss_wage_base_base_year'),
    (re.compile(r'^irmaa_tier2_mfj_\d{4}$'), 'irmaa_tier2_mfj_base_year'),
    (re.compile(r'^ltcg_0pct_top_mfj_\d{4}$'), 'ltcg_0pct_top_mfj_base_year'),
    (re.compile(r'^ltcg_15pct_top_mfj_\d{4}$'), 'ltcg_15pct_top_mfj_base_year'),
    (re.compile(r'^part_b_premium_\d{4}$'), 'part_b_base_premium_monthly'),
    (re.compile(r'^part_d_premium_\d{4}$'), 'part_d_base_premium_monthly'),
    (re.compile(r'^annual_premium_\d{4}$'), 'annual_premium_base_year'),
]

def _normalize_label(label):
    label = (label or '').strip()
    for pat, replacement in _YEAR_LABEL_PATTERNS:
        if pat.match(label):
            return replacement
    return label

# ─────────────────────────────────────────────────────────────────────────────
# 1.  CSV LOADER
# ─────────────────────────────────────────────────────────────────────────────

def load_csv(path):
    data = {}   # {section: {subsection: {label: value}}}
    for csv_path in _client_data_csv_paths(path):
        if not Path(csv_path).exists():
            continue
        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
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

def _n(v, default=0.0):
    # Boundary parse uses Decimal for money/percentage precision, then returns
    # a float execution copy for the retained numerical engine.
    if default is None and (v is None or str(v).strip() == ''):
        return None
    try:
        return float(_money_decimal(v, _money_decimal(default if default is not None else 0.0)))
    except Exception:
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
    """
    s = str(v or '').strip()
    if not s:
        return None
    try:
        if '/' in s:
            parts = [int(float(x)) for x in s.split('/') if str(x).strip()]
            if len(parts) >= 3:
                m, d, y = parts[0], parts[1], parts[2]
                if y < 100:
                    y += 2000
                return (y, m, d)
        if '-' in s:
            head = s.split('T', 1)[0]
            parts = [int(float(x)) for x in head.split('-') if str(x).strip()]
            if len(parts) >= 3:
                return (parts[0], parts[1], parts[2])
        y = int(float(s))
        return (y, 12, 31)
    except Exception:
        return None


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

def parse_client(data, url_template):
    c = {}
    system_data = {}
    if load_system_config is not None:
        try:
            system_data = load_system_config()
        except Exception:
            system_data = {}

    def _sv(section, subsection, label, default=''):
        return _v(system_data, section, subsection, label, _v(data, section, subsection, label, default))

    # Backward compat: alias old husband/wife keys → member_1/member_2 for saved plans
    _hh = data.setdefault('Household', {}).setdefault('', {})
    for _old, _new in [
        ('husband_name','member_1_name'),('husband_dob','member_1_dob'),
        ('husband_retirement_date','member_1_retirement_date'),('husband_mortality_age','member_1_mortality_age'),
        ('wife_name','member_2_name'),('wife_dob','member_2_dob'),
        ('wife_retirement_date','member_2_retirement_date'),('wife_mortality_age','member_2_mortality_age'),
    ]:
        if _old in _hh and _new not in _hh: _hh[_new] = _hh[_old]
    for _sec, _old, _new in [
        ('Social Security','Wife','Member 2'),('Social Security','Husband','Member 1'),
        ('Income Streams','Wife Pension','Member 2 Pension'),
        ('Income Streams','Wife Single Annuity','Member 2 Single Annuity'),
        ('Income Streams','Wife Joint Annuity','Member 2 Joint Annuity'),
        ('Income Streams','Husband Single Annuity','Member 1 Single Annuity'),
        ('Income Streams','Husband Joint Annuity','Member 1 Joint Annuity'),
    ]:
        if _sec in data and _old in data[_sec] and _new not in data[_sec]:
            data[_sec][_new] = data[_sec][_old]
    _mc = data.setdefault('Model Constants', {}).setdefault('Retirement', {})
    for _old, _new in [('husband_rmd_start_age','member_1_rmd_start_age'),('wife_rmd_start_age','member_2_rmd_start_age')]:
        if _old in _mc and _new not in _mc: _mc[_new] = _mc[_old]
    _scen_rl = data.setdefault('Scenarios', {}).setdefault('Retire Later', {})
    if 'husband_retire_year' in _scen_rl and 'member_1_retire_year' not in _scen_rl:
        _scen_rl['member_1_retire_year'] = _scen_rl['husband_retire_year']

    # Household
    c['h_name']    = _v(data,'Household','','member_1_name','Matthew')
    c['w_name']    = _v(data,'Household','','member_2_name','Patricia')
    # Nicknames: short names used in every user-facing report/chart label.
    # Fall back to the first word of the full name when not provided.
    def _nick(raw, full_name):
        raw = str(raw or '').strip()
        if raw:
            return raw
        return str(full_name or '').strip().split(' ')[0] if str(full_name or '').strip() else ''
    c['h_nick'] = _nick(_v(data,'Household','','member_1_nickname',''), c['h_name'])
    c['w_nick'] = _nick(_v(data,'Household','','member_2_nickname',''), c['w_name'])
    c['h_dob_yr']  = _y(_v(data,'Household','','member_1_dob','8/3/1962').split('/')[-1], 1962)
    c['w_dob_yr']  = _y(_v(data,'Household','','member_2_dob','5/30/1961').split('/')[-1], 1961)
    _h_ret_raw = _v(data,'Household','','member_1_retirement_date','1/1/2027')
    _w_ret_raw = _v(data,'Household','','member_2_retirement_date','2/28/2023')
    c['h_ret_yr']  = _y(_h_ret_raw, 2027)
    c['w_ret_yr']  = _y(_w_ret_raw, 2023)
    c['h_earned_last_year'] = _last_earned_income_year_from_retirement_date(_h_ret_raw, c['h_ret_yr'])
    c['h_mort_age']= _n(_v(data,'Household','','member_1_mortality_age','92'), 92)
    c['w_mort_age']= _n(_v(data,'Household','','member_2_mortality_age','95'), 95)
    c['h_death_yr']= int(c['h_dob_yr'] + c['h_mort_age'])
    c['w_death_yr']= int(c['w_dob_yr'] + c['w_mort_age'])
    c['state']     = _v(data,'Household','','residence_state','Illinois')
    c['trust_type']= _v(data,'Estate Planning','Trust Structure','trust_type','revocable living trust')

    # Market pricing settings live in multi_user/system_config.csv and are merged by the active config loader.
    configure_api_keys(
        fmp_api_key=_sv('Market Pricing', 'API', 'fmp_api_key', ''),
        alpha_vantage_api_key=_sv('Market Pricing', 'API', 'alpha_vantage_api_key', ''),
    )
    configure_holdings_pricing(
        mode=_sv('Market Pricing', 'Holdings', 'pricing_mode', 'CACHE'),
        cache_hours=_sv('Market Pricing', 'Holdings', 'cache_hours', '24'),
    )
    # A user-controlled pricing freeze overrides live/cache mode for builds so
    # advisor report packages can be reproduced after market prices change.
    try:
        from .portfolio_analytics import pricing_freeze_status
        from .config_backend import DEFAULT_DB
        freeze = pricing_freeze_status(workspace_id=active_workspace_id(), db_path=DEFAULT_DB, include_prices=True)
        if freeze.get('active') and freeze.get('prices'):
            configure_holdings_pricing(
                mode='FROZEN',
                cache_hours=_sv('Market Pricing', 'Holdings', 'cache_hours', '24'),
            )
            set_frozen_prices(freeze.get('prices') or {}, metadata={k: v for k, v in freeze.items() if k != 'prices'})
    except Exception:
        pass

    # ── Filing Status (9.1) ───────────────────────────────────────────────────
    # Supported: MFJ, Single, HOH, MFS.
    # After first death, MFJ → Single; HOH stays HOH; MFS → Single; Single stays.
    raw_filing = (_v(data,'Household','','filing_status','MFJ') or 'MFJ').strip().upper()
    if raw_filing not in _td.FILING_STATUSES:
        raw_filing = 'MFJ'
    c['filing_status'] = raw_filing
    # Survivor filing status: what the surviving spouse files as after first death
    c['survivor_filing'] = _v(data,'Household','','survivor_filing_status','Single').strip() or 'Single'
    if c['survivor_filing'] not in _td.FILING_STATUSES:
        c['survivor_filing'] = 'Single'

    # ── Members Abstraction (9.2) ─────────────────────────────────────────────
    # Build a members list from the Household data. Supports 1 or 2 adult
    # members. If wife_name is blank/absent, it's a single-member household.
    # The members list is the generalized interface used by the model.
    _m1 = {
        'name':          c['h_name'],
        'nickname':      c['h_nick'],
        'role':          'member_1',
        'dob_yr':        c['h_dob_yr'],
        'retire_yr':     c['h_ret_yr'],
        'mortality_age': c['h_mort_age'],
        'death_yr':      c['h_death_yr'],
    }
    _has_member_2 = bool(c['w_name'] and c['w_name'].strip())
    if _has_member_2:
        _m2 = {
            'name':          c['w_name'],
            'nickname':      c['w_nick'],
            'role':          'member_2',
            'dob_yr':        c['w_dob_yr'],
            'retire_yr':     c['w_ret_yr'],
            'mortality_age': c['w_mort_age'],
            'death_yr':      c['w_death_yr'],
        }
        c['members'] = [_m1, _m2]
    else:
        # Single-member household
        c['members'] = [_m1]
        c['w_dob_yr']   = c['h_dob_yr']   # zero-impact defaults
        c['w_ret_yr']   = c['h_ret_yr']
        c['w_mort_age'] = 0
        c['w_death_yr'] = c['h_dob_yr']   # already dead → engine sees no spouse
        if c['filing_status'] == 'MFJ':
            c['filing_status'] = 'Single'  # can't be MFJ with one member
    c['household_size'] = len(c['members'])

    c['plan_start'] = datetime.date.today().year
    c['plan_end']   = max(c['h_death_yr'], c['w_death_yr'])
    c['first_death_yr'] = min(c['h_death_yr'], c['w_death_yr'])

    # Economic Assumptions
    c['inf']       = _n(_v(data,'Economic Assumptions','','inflation_general','0.025'), 0.025)
    c['ss_cola']   = _n(_v(data,'Economic Assumptions','','social_security_cola','0.02'), 0.02)
    c['med_inf']   = _n(_v(data,'Economic Assumptions','','medicare_part_b_inflation','0.055'), 0.055)
    c['partd_inf'] = _n(_v(data,'Economic Assumptions','','medicare_part_d_inflation','0.0125'), 0.0125)
    c['ret']       = _n(_v(data,'Economic Assumptions','','portfolio_nominal_return','0.06'), 0.06)
    c['brk_inf']   = _n(_v(data,'Economic Assumptions','','fed_tax_bracket_inflator','0.02'), 0.02)
    c['ss_taxable']= _n(_v(data,'Economic Assumptions','','social_security_taxable_fraction','0.85'), 0.85)
    # Social Security solvency / funding haircut. This explicit assumption reduces
    # gross Social Security benefits from the configured year onward when the
    # user wants to model trust-fund underfunding risk.
    c['ss_funding_discount_year'] = int(_n(_v(data,'Social Security','Funding Discount','ss_funding_discount_year','2032'), 2032))
    c['ss_funding_discount_pct'] = max(0.0, min(1.0, _n(_v(data,'Social Security','Funding Discount','ss_funding_discount_pct','22%'), 0.22)))
    c['roth_brk']  = _n(_v(data,'Economic Assumptions','',f'roth_conversion_target_bracket_{TAX_BASE_YEAR}','0.22'), 0.22)
    c['ann_div']   = _n(_v(data,'Economic Assumptions','','annuity_default_dividend_rate','0.0575'), 0.0575)
    c['ann_add']   = _n(_v(data,'Economic Assumptions','','annuity_default_additional_income_pct','0.2'), 0.2)
    c['ann_cash']  = _n(_v(data,'Economic Assumptions','','annuity_default_pay_in_cash_pct','0.8'), 0.8)

    # Social Security.  Users enter a per-spouse claim age, the expected monthly
    # payment at that claim age, and optionally the monthly PIA at FRA.
    c['w_ss_claim_monthly'] = _n(_v(data,'Social Security','Member 2','monthly_at_claim_age_today_dollars', _v(data,'Social Security','Member 2','monthly_at_age_70_today_dollars','4174')), 4174)
    c['h_ss_claim_monthly'] = _n(_v(data,'Social Security','Member 1','monthly_at_claim_age_today_dollars', _v(data,'Social Security','Member 1','monthly_at_age_70_today_dollars','5080')), 5080)
    c['w_ss70']    = _n(_v(data,'Social Security','Member 2','monthly_at_age_70_today_dollars', str(c['w_ss_claim_monthly'])), c['w_ss_claim_monthly'])
    c['h_ss70']    = _n(_v(data,'Social Security','Member 1','monthly_at_age_70_today_dollars', str(c['h_ss_claim_monthly'])), c['h_ss_claim_monthly'])
    c['w_ss_pia']  = _n(_v(data,'Social Security','Member 2','monthly_pia_at_fra_today_dollars','0'), 0)
    c['h_ss_pia']  = _n(_v(data,'Social Security','Member 1','monthly_pia_at_fra_today_dollars','0'), 0)
    c['w_ss_claim_age'] = int(_n(_v(data,'Social Security','Member 2','claim_age', _v(data,'Model Constants','Retirement','ss_claim_age','70')), 70))
    c['h_ss_claim_age'] = int(_n(_v(data,'Social Security','Member 1','claim_age', _v(data,'Model Constants','Retirement','ss_claim_age','70')), 70))
    c['ss_surv']   = _n(_v(data,'Social Security','Policy','survivor_pct_of_higher_benefit','100'), 100)/100
    c['survivor_benefit_uses_deceased_claim_age'] = _b(_v(data,'Social Security','Policy','survivor_benefit_uses_deceased_claim_age','TRUE'))
    c['spousal_benefits_enabled'] = _b(_v(data,'Social Security','Policy','spousal_benefits_enabled','TRUE'))

    # Wellness / Medicare cash-flow inputs.
    # UI label: Pre-65 Healthcare Premium. Store annual per-person
    # premium directly for projection math; monthly is retained only for
    # display/reporting convenience.
    c['bridge_premium'] = _n(_v(data,'Wellness','Pre-65 Bridge','annual_premium_base_year','0'), 0)
    c['bridge_premium_monthly'] = c['bridge_premium'] / 12 if c['bridge_premium'] else 0
    c['partb']     = _n(_v(data,'Wellness','Medicare','part_b_base_premium_monthly','185'), 185)
    c['partd']     = _n(_v(data,'Wellness','Medicare','part_d_base_premium_monthly','40'), 40)
    c['partg']     = _n(_v(data,'Wellness','Medicare','part_g_base_premium_monthly','0'), 0)
    c['oop']       = _n(_v(data,'Wellness','Out-of-Pocket','annual_oop_estimate_today','8000'), 8000)
    c['oop_utilization_pct'] = _n(_v(data,'Wellness','Out-of-Pocket','oop_utilization_pct','100%'), 1.0)
    c['aca_ptc_enabled'] = _b(_v(data,'Wellness','ACA Premium Tax Credit','enabled','TRUE'))
    c['aca_household_size'] = int(_n(_v(data,'Wellness','ACA Premium Tax Credit','household_size','2'), 2))
    c['aca_fpl_base'] = _n(_v(data,'Wellness','ACA Premium Tax Credit','federal_poverty_level_base_year','21150'), 21150)
    c['aca_benchmark_silver_premium'] = _n(_v(data,'Wellness','ACA Premium Tax Credit','benchmark_silver_premium_annual','32000'), 32000)
    c['aca_applicable_pct_cap'] = _n(_v(data,'Wellness','ACA Premium Tax Credit','applicable_pct_cap','8.50%'), 0.085)
    c['aca_enhanced_subsidies_through_year'] = int(_n(_v(data,'Wellness','ACA Premium Tax Credit','enhanced_subsidies_through_year','2026'), 2026))

    # Cashflow / income
    c['earned']     = _n(_v(data,'Cashflow','Earned Income','annual_earned_income','290000'), 290000)
    c['earn_start'] = _y(_v(data,'Cashflow','Earned Income','earned_income_start_year', str(c['plan_start'])), c['plan_start'])
    # Earned income runs from the Work Income start year through the retirement
    # year from Retirement Timing. There is intentionally no separate earned-
    # income end-year input or legacy fallback.
    c['earn_end']   = c.get('h_earned_last_year', c['h_ret_yr'])
    c['earn_inc']   = _n(_v(data,'Cashflow','Earned Income','earned_income_annual_increase','0.03'), 0.03)
    c['entity']     = _v(data,'Cashflow','Earned Income','entity_type','sole_prop')
    c['biz_exp']    = _n(_v(data,'Cashflow','Self-Employment','business_expenses_annual','15000'), 15000)
    c['home_off']   = _n(_v(data,'Cashflow','Self-Employment','home_office_expenses_annual','4000'), 4000)
    # SEHI has no standalone input. It is derived per projection year from
    # Healthcare premiums: Pre-65 Healthcare Premium before age 65, then
    # Medicare Part B/D/G costs once Medicare age is reached.
    c['sehi']       = 0.0
    c['sehi_derived_from_wellness'] = True
    c['qbi_elig']   = _b(_v(data,'Cashflow','Self-Employment','qbi_eligible','TRUE'))

    c['k401_mo']   = _n(_v(data,'Cashflow','Retirement Contributions','monthly_401k_contribution','2000'), 2000)
    c['k401_lim']  = _n(_v(data,'Cashflow','Retirement Contributions','annual_401k_limit_base_year','32500'), 32500)
    c['k401_limit_indexed'] = _b(_v(data,'Cashflow','Retirement Contributions','index_401k_limit','TRUE'))

    c['h_rmd_start_age'] = int(_n(_v(data,'Model Constants','Retirement','member_1_rmd_start_age', _v(data,'Model Constants','Retirement','rmd_start_age','75')), 75))
    c['w_rmd_start_age'] = int(_n(_v(data,'Model Constants','Retirement','member_2_rmd_start_age', _v(data,'Model Constants','Retirement','rmd_start_age','75')), 75))
    c['real_dollar_reporting_enabled'] = _b(_v(data,'Reporting','Output','real_dollar_reporting_enabled','TRUE'))

    c['spend_base']= _n(_v(data,'Cashflow','Spending','annual_spending_base_year','225000'), 225000)
    _spend_growth_mode = str(_v(data,'Cashflow','Spending','core_spending_growth_mode','cpi') or 'cpi').strip().lower().replace(' ', '_')
    if _spend_growth_mode not in ('cpi','manual_override'):
        _spend_growth_mode = 'cpi'
    c['core_spending_growth_mode'] = _spend_growth_mode
    c['core_spending_manual_growth_rate'] = _n(_v(data,'Cashflow','Spending','core_spending_manual_growth_rate','0'), 0)
    c['spend_inf'] = c['core_spending_manual_growth_rate'] if _spend_growth_mode == 'manual_override' else c['inf']
    c['spending_freeze_yr'] = _y(_v(data,'Model Constants','Retirement',
                                     'spending_freeze_year','2040'), 2040)
    c['char_low']  = _n(_v(data,'Cashflow','Spending','annual_charitable_giving_low','3000'), 3000)
    c['char_high'] = _n(_v(data,'Cashflow','Spending','annual_charitable_giving_high','5000'), 5000)

    c['mort_pmt']  = _n(_v(data,'Cashflow','Mortgage','monthly_payment','3000'), 3000)*12
    c['real_estate_tax_base'] = _n(_v(data,'Cashflow','Mortgage','annual_real_estate_taxes','0'), 0)
    c['real_estate_tax_growth_rate'] = _n(
        _v(data,'Cashflow','Mortgage','real_estate_tax_annual_adjustment_pct', str(c.get('inf', 0.025))),
        c.get('inf', 0.025),
    )
    c['mort_bal']  = _n(_v(data,'Cashflow','Mortgage','balance_as_of_plan_start','293284'), 293284)
    c['mort_rate'] = _n(_v(data,'Cashflow','Mortgage','interest_rate','0.0199'), 0.0199)
    c['mort_end']  = _y(_v(data,'Cashflow','Mortgage','last_payment_year','2034'), 2034)
    # Build a proper amortization schedule: balance at the START of each year.
    # Each year: interest = balance*rate; principal = min(payment-interest, balance).
    # This replaces the previous (incorrect) use of the note's principal to amortize.
    _mort_sched = {}
    _bal = c['mort_bal']
    _pstart = c['plan_start']
    for _yr in range(_pstart, c['mort_end'] + 2):
        _mort_sched[_yr] = max(0.0, _bal)
        if _yr <= c['mort_end'] and _bal > 0:
            _interest  = _bal * c['mort_rate']
            _principal = min(c['mort_pmt'] - _interest, _bal)
            _bal = max(0.0, _bal - _principal)
        else:
            _bal = 0.0
    c['mort_schedule'] = _mort_sched
    c['mort_interest_schedule'] = {}
    _bal_i = c['mort_bal']
    for _yr in range(_pstart, c['mort_end'] + 2):
        _interest = max(0.0, _bal_i) * c['mort_rate'] if _yr <= c['mort_end'] else 0.0
        c['mort_interest_schedule'][_yr] = _interest
        if _yr <= c['mort_end'] and _bal_i > 0:
            _principal = min(max(0.0, c['mort_pmt'] - _interest), _bal_i)
            _bal_i = max(0.0, _bal_i - _principal)
        else:
            _bal_i = 0.0
    # Large Discretionary Expenses use only the canonical Cashflow rows.
    # Home Improvement items are routed to housing costs; all others go to rec_extra.
    c['lump'] = {}
    c['home_improvement_lump'] = {}
    c['recurring_extras'] = []
    # When the new per-line Spending Budget file (#95) exists it is the source of
    # truth for these sections; suppress the legacy extra_N rows to avoid
    # double-counting. Plans without the budget-lines file keep legacy behavior.
    _budget_lines_present = False
    try:
        for _bl_probe in candidate_input_files(
            'client_spending_budget_lines.csv', active_workspace_id(),
            root=Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))):
            if os.path.exists(str(_bl_probe)):
                _budget_lines_present = True
                break
    except Exception:
        _budget_lines_present = False
    _cashflow = data.get('Cashflow', {})
    _extra_subsection = 'Large Discretionary Expenses'
    _travel = _cashflow.get(_extra_subsection, {})
    _idxs = sorted({m.group(1) for lbl in _travel for m in [re.match(r'^extra_(\d+)_', lbl)] if m}, key=lambda x: int(x))
    if _idxs and not _budget_lines_present:
        for _idx in _idxs:
            _typ = _v(data, 'Cashflow', _extra_subsection, f'extra_{_idx}_type', 'Other') or 'Other'
            _amt = _n(_v(data, 'Cashflow', _extra_subsection, f'extra_{_idx}_amount', '0'), 0)
            _yr = _y(_v(data, 'Cashflow', _extra_subsection, f'extra_{_idx}_year', '0'), 0)
            _start = _y(_v(data, 'Cashflow', _extra_subsection, f'extra_{_idx}_start_year', '0'), 0)
            _end = _y(_v(data, 'Cashflow', _extra_subsection, f'extra_{_idx}_end_year', '0'), 0)
            _comment = _v(data, 'Cashflow', _extra_subsection, f'extra_{_idx}_comment', '')
            if _amt <= 0:
                continue
            _is_home_improvement = _typ.strip().lower() in {'home improvement', 'home improvements', 'home projects', 'home project'}
            if _end and not _yr:
                if not _start:
                    _start = c['plan_start']
                if _end < _start:
                    _end = _start
                c['recurring_extras'].append({'type': _typ, 'amount': _amt, 'start_year': _start, 'end_year': _end, 'comment': _comment, 'is_home_improvement': _is_home_improvement})
            elif _start and _end:
                if _end < _start:
                    _end = _start
                c['recurring_extras'].append({'type': _typ, 'amount': _amt, 'start_year': _start, 'end_year': _end, 'comment': _comment, 'is_home_improvement': _is_home_improvement})
            elif _yr:
                if _is_home_improvement:
                    c['home_improvement_lump'][_yr] = c['home_improvement_lump'].get(_yr, 0) + _amt
                else:
                    c['lump'][_yr] = c['lump'].get(_yr, 0) + _amt
    c.setdefault('home_proj', 0.0)
    c.setdefault('home_proj_end', c['plan_start'] - 1)
    c.setdefault('vac', 0.0)
    c.setdefault('vac_end', c['plan_start'] - 1)

    # ── Spending Budget per-line table (#95) ──────────────────────────────────
    # Additive, flat file (like client_holdings.csv): each row is its own budget
    # line with per-line start/end/one-time/amount. Lines in the
    # ``home_improvement`` section route to housing costs; ``gifts_charity`` and
    # all others route to rec_extra. Guarded so plans without the file behave
    # exactly as before.
    try:
        _bl_file = None
        for _bl_path in candidate_input_files(
            'client_spending_budget_lines.csv', active_workspace_id(),
            root=Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))):
            if os.path.exists(str(_bl_path)):
                _bl_file = str(_bl_path)
                break
        if _bl_file:
            with open(_bl_file, newline='', encoding='utf-8-sig') as _blf:
                for _bl in csv.DictReader(_blf):
                    _section = (_bl.get('section', '') or '').strip().lower()
                    # gifts_charity is a budget-tracking target only (like the
                    # taxonomy budget); the legacy annual_charitable_giving_* fields
                    # were never consumed by the projection, so keep it out of
                    # spending to preserve identical engine results.
                    if _section in ('gifts_charity', 'category_budget'):
                        continue
                    _amt = _n((_bl.get('amount_per_year', '0') or '0'), 0)
                    if _amt <= 0:
                        continue
                    _one_time = _y((_bl.get('one_time_year', '0') or '0'), 0)
                    _bstart = _y((_bl.get('start_year', '0') or '0'), 0)
                    _bend = _y((_bl.get('end_year', '0') or '0'), 0)
                    _label = (_bl.get('label', '') or '').strip()
                    _is_home = (_section == 'home_improvement')
                    if _one_time and not (_bstart or _bend):
                        # One-time spend in a single year.
                        if _is_home:
                            c['home_improvement_lump'][_one_time] = c['home_improvement_lump'].get(_one_time, 0) + _amt
                        else:
                            c['lump'][_one_time] = c['lump'].get(_one_time, 0) + _amt
                    else:
                        # Recurring (or open-ended) line. Blank end = run to plan end.
                        _rs = _bstart or c['plan_start']
                        _re_end = _bend or c['plan_end']
                        if _re_end < _rs:
                            _re_end = _rs
                        c['recurring_extras'].append({
                            'type': _label or _section,
                            'amount': _amt,
                            'start_year': _rs,
                            'end_year': _re_end,
                            'comment': (_bl.get('notes', '') or '').strip(),
                            'is_home_improvement': _is_home,
                        })
    except Exception:
        # Never fail a build because of the optional budget-lines file.
        pass

    # Unified Spending Budget: the consolidated budget file supersedes both
    # the legacy Core Spending base input and client_spending_budget_lines.csv.
    # Apply after legacy parsing so the budget can replace those compatibility
    # values rather than double-counting them.
    try:
        from .spending_budget_resolver import apply_budget_to_engine_config as _apply_unified_spending_budget
        _apply_unified_spending_budget(c, root=Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    except Exception:
        # Optional during migration/blank-plan startup; keep legacy values if unavailable.
        pass

    # Other Assets
    c['home_val']    = _n(_v(data,'Other Assets','Home','value_as_of_plan_start', _v(data,'Other Assets','Home',f'value_4_1_{TAX_BASE_YEAR}','1313000')), 1313000)
    c['home_appr']   = _n(_v(data,'Other Assets','Home','appreciation_rate','0.03'), 0.03)
    c['sec121']      = _n(_v(data,'Other Assets','Home','section_121_exclusion_mfj','500000'), 500000)
    # Home sale parameters (0 = no planned sale)
    c['home_sale_yr']  = _y(_v(data,'Other Assets','Home','home_sale_year','0'), 0)
    c['home_sale_px']  = _n(_v(data,'Other Assets','Home','home_sale_price','0'), 0)
    # Home basis is a canonical Home asset fact.  Legacy Plan Data may also
    # contain Scenarios > Sell Home > home_basis, but that duplicate can drift
    # from the UI/CSV Home value.  Keep one source of truth for both base-plan
    # home-sale math and the Sell Home scenario.
    c['home_basis']    = _n(_v(data,'Other Assets','Home','home_basis','0'), 0)
    c['home_sale_acct']= _v(data,'Other Assets','Home','home_sale_proceeds_account','').strip()

    # Current-home operating costs are entered in Housing Budget Detail/current
    # home rows.  Future housing steps carry explicit rent/buy operating costs;
    # rental utilities and renters insurance are not seeded from current-home
    # utilities/homeowners insurance because owned-home costs drop off once the
    # home is sold.  Keep the raw current-home amounts on the engine config so
    # projection and workbook code do not have to re-read CSV rows.
    c['current_homeowners_insurance_annual'] = _n(_v(data,'Housing','current_home','homeowners_insurance_annual','0'), 0)
    c['current_home_utilities_annual'] = _n(_v(data,'Housing','current_home','utilities_annual','0'), 0)
    c['current_home_maintenance_annual'] = _n(_v(data,'Housing','current_home','home_maintenance_annual','0'), 0)

    # Future housing steps (rent/buy) are entered on the Housing page and feed
    # both annual cash flow and net worth.  A blank start year disables a step.
    c['next_housing_steps'] = []
    for _step_key in ('next_step_1', 'next_step_2'):
        _start = _y(_v(data, 'Housing', _step_key, 'start_year', ''), 0)
        if not _start:
            continue
        _end = _y(_v(data, 'Housing', _step_key, 'end_year', '0'), 0)
        _typ = str(_v(data, 'Housing', _step_key, 'type', 'purchase') or 'purchase').strip().lower()
        if _typ not in ('rent', 'purchase', 'buy'):
            _typ = 'purchase'
        if _typ == 'buy':
            _typ = 'purchase'
        _down = _n(_v(data, 'Housing', _step_key, 'down_payment', '20%'), 0.20)
        if _down > 1.0:
            _down = _down / 100.0
        _rate = _n(_v(data, 'Housing', _step_key, 'mortgage_rate_pct', '0'), 0.0)
        if _rate > 1.0:
            _rate = _rate / 100.0
        _re_tax = _n(_v(data, 'Housing', _step_key, 're_tax_pct', '0'), 0.0)
        if _re_tax > 1.0:
            _re_tax = _re_tax / 100.0
        _hoa = _n(_v(data, 'Housing', _step_key, 'hoa_pct', '0'), 0.0)
        if _hoa > 1.0:
            _hoa = _hoa / 100.0
        c['next_housing_steps'].append({
            'id': _step_key,
            'type': _typ,
            'start_year': _start,
            'end_year': _end,
            'state': str(_v(data, 'Housing', _step_key, 'state', '') or '').strip(),
            'city_type': str(_v(data, 'Housing', _step_key, 'city_type', '') or '').strip().lower(),
            'population_size': _n(_v(data, 'Housing', _step_key, 'population_size', '0'), 0.0),
            'purchase_price': _n(_v(data, 'Housing', _step_key, 'purchase_price', '0'), 0.0),
            'down_payment_pct': max(0.0, min(1.0, _down)),
            'mortgage_rate_pct': max(0.0, _rate),
            'monthly_rent': _n(_v(data, 'Housing', _step_key, 'monthly_rent', '0'), 0.0),
            'insurance_annual': _n(_v(data, 'Housing', _step_key, 'insurance_annual', '0'), 0.0),
            'utilities_annual': _n(_v(data, 'Housing', _step_key, 'utilities_annual', '0'), 0.0),
            'maintenance_annual': _n(_v(data, 'Housing', _step_key, 'maintenance_annual', '0'), 0.0),
            'real_estate_tax_pct': max(0.0, _re_tax),
            'hoa_pct': max(0.0, _hoa),
        })

    # Typed other assets are entered as compact rows under
    # Other Assets > Other Asset N.  The UI stores the estimated value, the
    # date of that estimate, an annual appreciation/depreciation rate, optional
    # basis for appreciating assets, and an optional sell date.  Convert those
    # rows into the legacy aggregate fields used by the projection/report tabs
    # (startup_val/autos_val) without supporting the old Startup Equity/Autos
    # subsections.
    c['other_asset_items'] = []
    c['startup_eq'] = 0.0
    c['startup_gr'] = 0.0
    c['startup_sale_year'] = 0
    c['startup_sale_price'] = 0.0
    c['autos'] = 0.0
    c['auto_dep_yrs'] = 7
    _startup_weight = 0.0
    _auto_dep_years_weight = 0.0
    _auto_weight = 0.0
    for _sub, _vals in (data.get('Other Assets') or {}).items():
        if not str(_sub or '').strip().lower().startswith('other asset'):
            continue
        _typ = str(_vals.get('type') or 'Other').strip() or 'Other'
        _name = str(_vals.get('name') or _sub).strip() or _sub
        _value = _n(_vals.get('value', '0'), 0.0)
        _asof_year = _y(_vals.get('as_of_date', ''), c['plan_start']) or c['plan_start']
        _rate = _n(_vals.get('annual_appreciation_pct', '0'), 0.0)
        _basis = _n(_vals.get('basis', '0'), 0.0)
        _sell_year = _y(_vals.get('sell_date', ''), 0)
        _base = 1.0 + _rate
        try:
            _current_value = _value * (_base ** (c['plan_start'] - _asof_year)) if _base > 0 else _value
        except Exception:
            _current_value = _value
        _item = {
            'section': _sub, 'type': _typ, 'name': _name,
            'value': _current_value, 'as_of_year': _asof_year,
            'annual_appreciation_pct': _rate, 'basis': _basis,
            'sell_year': _sell_year,
        }
        c['other_asset_items'].append(_item)
        _ntyp = re.sub(r'[^a-z0-9]+', '_', _typ.lower()).strip('_')
        if any(tok in _ntyp for tok in ('auto', 'boat', 'vehicle', 'car', 'truck', 'rv')):
            c['autos'] += _current_value
            if _rate < 0:
                _yrs = max(1.0, min(100.0, 1.0 / abs(_rate)))
                _auto_dep_years_weight += _yrs * max(0.0, _current_value)
                _auto_weight += max(0.0, _current_value)
        else:
            c['startup_eq'] += _current_value
            _startup_weight += max(0.0, _current_value)
            c['startup_gr'] += _rate * max(0.0, _current_value)
            if _sell_year and (not c['startup_sale_year'] or _sell_year < c['startup_sale_year']):
                c['startup_sale_year'] = _sell_year
    if _startup_weight > 0:
        c['startup_gr'] = c['startup_gr'] / _startup_weight
    if _auto_weight > 0:
        c['auto_dep_yrs'] = int(round(_auto_dep_years_weight / _auto_weight)) if _auto_dep_years_weight else 7
    if c['startup_sale_year'] and c['startup_eq'] > 0:
        # When no explicit sale price exists in the new compact table, project
        # sale proceeds from the current value and annual appreciation rate.
        _years_to_sale = max(0, c['startup_sale_year'] - c['plan_start'])
        c['startup_sale_price'] = c['startup_eq'] * ((1.0 + c['startup_gr']) ** _years_to_sale if (1.0 + c['startup_gr']) > 0 else 1.0)
    # Straight-line depreciation: value / depreciation_years per year → $0 at end of life.

    # Note Receivable
    c['note_face']   = _n(_v(data,'Note Receivable','Summary','face_value','474252.96'), 474252.96)
    c['note_first']  = _y(_v(data,'Note Receivable','Summary','first_payment', f"1/2/{c['plan_start']}"), c['plan_start'])
    c['note_last']   = _y(_v(data,'Note Receivable','Summary','last_payment','1/2/2033'), 2033)
    c['note_princ']  = _n(_v(data,'Note Receivable','Summary',f'annual_principal_{TAX_BASE_YEAR}_{TAX_BASE_YEAR + 6}','59281.62'), 59281.62)
    c['note_princ_final'] = _n(_v(data,'Note Receivable','Summary','final_principal_2033','59327.50'), 59327.50)
    c['note_interest'] = {}
    for yr in range(c['plan_start'], c['plan_start'] + 8):
        iv = _v(data,'Note Receivable','Interest by Year',str(yr),'0')
        c['note_interest'][yr] = _n(iv, 0)

    # HSA withdrawal policy. Default is spend_as_needed: do not schedule HSA draws;
    # use HSA only when needed for a funding gap before touching Roth. Optional
    # annual_pct and smooth_window modes allow an advisor/user to spend HSA over a
    # controlled window. Legacy withdrawal_window is still honored when present.
    c['hsa_withdrawal_mode'] = str(_v(data,'HSA Policy','Withdrawals','hsa_withdrawal_mode','spend_as_needed') or 'spend_as_needed').strip().lower()
    if c['hsa_withdrawal_mode'] not in ('spend_as_needed','annual_pct','smooth_window'):
        c['hsa_withdrawal_mode'] = 'spend_as_needed'
    c['hsa_annual_spend_pct'] = min(1.0, max(0.0, _n(_v(data,'HSA Policy','Withdrawals','hsa_annual_spend_pct','10%'), 0.10)))
    c['hsa_win_start'] = 9999
    c['hsa_win_end']   = 0
    hsa_start_raw = str(_v(data,'HSA Policy','Withdrawals','hsa_withdrawal_start_year','') or '').strip()
    hsa_end_raw = str(_v(data,'HSA Policy','Withdrawals','hsa_withdrawal_end_year','') or '').strip()
    hsa_win_raw = str(_v(data,'HSA Policy','Window','withdrawal_window','') or '').strip()
    if hsa_start_raw or hsa_end_raw:
        try:
            c['hsa_win_start'] = int(float(hsa_start_raw)) if hsa_start_raw else c['plan_start']
            c['hsa_win_end'] = int(float(hsa_end_raw)) if hsa_end_raw else 9999
        except Exception:
            c['hsa_win_start'], c['hsa_win_end'] = 9999, 0
    elif '-' in hsa_win_raw and c['hsa_withdrawal_mode'] != 'spend_as_needed':
        try:
            parts = hsa_win_raw.split('-')
            c['hsa_win_start'] = int(parts[0].strip())
            c['hsa_win_end']   = int(parts[1].strip())
        except Exception:
            pass
    # Be forgiving with legacy UI/data entry: older files sometimes stored the
    # HSA window as 2040/2031 instead of 2031/2040.  The Other Assets page now
    # exposes the start/end controls directly, and the projection normalizes the
    # window before applying scheduled HSA cash-flow withdrawals.
    if c.get('hsa_withdrawal_mode') != 'spend_as_needed' and c.get('hsa_win_start', 9999) > c.get('hsa_win_end', 0):
        c['hsa_win_start'], c['hsa_win_end'] = c['hsa_win_end'], c['hsa_win_start']
    c['hsa_contrib_base'] = (
        _n(_v(data,'HSA Policy','Contributions','family_annual_limit_base_year','8750'),8750) *
        _n(_v(data,'HSA Policy','Contributions','coverage_base_year_family_months','6'),6)/12 +
        _n(_v(data,'HSA Policy','Contributions','self_only_annual_limit_base_year','4400'),4400) *
        _n(_v(data,'HSA Policy','Contributions','coverage_base_year_self_only_months','6'),6)/12 +
        _n(_v(data,'HSA Policy','Contributions','catchup_amount','1000'),1000)
    )
    c['hsa_last_contrib'] = _y(_v(data,'HSA Policy','Contributions','contribution_last_year', str(c['plan_start'])), c['plan_start'])

    # Liquidity reserve requirement
    # Reserve rules are defined only by start_year, end_year, and
    # years_of_expenses to retain.  The default reserve requirement is zero.
    # Legacy Near Term / Long Term and Through YYYY rows are accepted only when
    # explicitly populated, then normalized into the same schedule structure.
    c['liquidity_buffer_schedule'] = []
    _lb = data.get('Liquidity Buffer', {})

    def _add_liquidity_rule(start_raw='', end_raw='', yrs_raw='0', account_raw='Taxable/Trust'):
        yrs = _n(yrs_raw, 0)
        has_any_value = any(str(x).strip() for x in (start_raw, end_raw, yrs_raw, account_raw))
        if not has_any_value:
            return
        account = str(account_raw or 'Taxable/Trust').strip() or 'Taxable/Trust'
        c['liquidity_buffer_schedule'].append({
            'start_year': _y(start_raw, c['plan_start']) if str(start_raw).strip() else c['plan_start'],
            'end_year': _y(end_raw, c.get('horizon', c['plan_start'] + 40)) if str(end_raw).strip() else 9999,
            'years_of_expenses': max(0.0, yrs),
            'reserve_account': account,
        })

    for sub, vals in _lb.items():
        if str(sub).lower().startswith('buffer_'):
            _add_liquidity_rule(
                vals.get('start_year', ''),
                vals.get('end_year', ''),
                vals.get('years_of_expenses', vals.get('years_of_expenses_in_trust', '0')),
                vals.get('reserve_account', vals.get('preserve_account', 'Taxable/Trust')),
            )

    if not c['liquidity_buffer_schedule'] and _lb:
        near_yrs_raw = _v(data, 'Liquidity Buffer', 'Near Term', 'years_of_expenses_in_trust', '')
        if str(near_yrs_raw).strip() == '':
            near_yrs_raw = _v(data, 'Liquidity Buffer', 'Through 2028', 'years_of_expenses_in_trust', '')
        long_yrs_raw = _v(data, 'Liquidity Buffer', 'Long Term', 'years_of_expenses_in_trust', '')
        if str(long_yrs_raw).strip() == '':
            long_yrs_raw = _v(data, 'Liquidity Buffer', '2029_onwards', 'years_of_expenses_in_trust', '')
        near_end_raw = _v(data, 'Liquidity Buffer', 'Near Term', 'end_year', '')
        if str(near_yrs_raw).strip():
            _near_end = _y(near_end_raw, 2028) if str(near_end_raw).strip() else 2028
            _add_liquidity_rule(c['plan_start'], _near_end, near_yrs_raw)
        if str(long_yrs_raw).strip():
            _long_start = (_y(near_end_raw, 2028) + 1) if str(near_end_raw).strip() else 2029
            _add_liquidity_rule(_long_start, '', long_yrs_raw)

    c['near_term_buffer_years'] = 0.0
    c['long_term_buffer_years'] = 0.0
    c['near_term_buffer_end_year'] = c['plan_start']
    if c['liquidity_buffer_schedule']:
        c['liquidity_buffer_schedule'].sort(key=lambda x: (x['start_year'], x['end_year']))
        _first = c['liquidity_buffer_schedule'][0]
        _last = c['liquidity_buffer_schedule'][-1]
        c['near_term_buffer_years'] = _first['years_of_expenses']
        c['near_term_buffer_end_year'] = _first['end_year'] if _first['end_year'] != 9999 else c['plan_start']
        c['long_term_buffer_years'] = _last['years_of_expenses']
    # Trust LTCG gain fraction: proportion of each trust dollar that is unrealized gain.
    # Trust draws trigger LTCG tax on this fraction at 0/15/20% rates.
    # Default 0.50 — configurable via CSV as trust basis changes.
    c['trust_gain_fraction'] = _n(_v(data,'Liquidity Buffer','Trust Tax','ltcg_gain_fraction','0.50'), 0.50)
    # Withdrawal cascade order — parsed from CSV Withdrawal Policy priorities
    # Validated: Trust must precede Roth (LTCG tax coupling).
    _raw_cascade = {}
    for sub, vals in data.get('Withdrawal Policy', {}).items():
        if sub.startswith('Priority'):
            try:
                pri = int(sub.replace('Priority','').strip())
                lbl = list(vals.keys())[0] if vals else ''
                _raw_cascade[pri] = lbl
            except (ValueError, IndexError):
                pass
    if _raw_cascade:
        _order_list = [_raw_cascade[k] for k in sorted(_raw_cascade.keys())]
        c['cascade_order_list'], c['cascade_warnings'] = _td.validate_cascade_order(_order_list)
    else:
        c['cascade_order_list'] = list(_td.DEFAULT_CASCADE_ORDER)
        c['cascade_warnings'] = []
    c['cascade_order'] = _raw_cascade

    # ── Roth Conversion Policy (9.5) ──────────────────────────────────────────
    # optimize_terminal_tax: evaluate multiple conversion policies and choose the
    #                        weighted after-tax terminal NW / lifetime-tax optimum
    # fill_to_bracket:       fill to top of target bracket, capped by IRMAA
    # fill_to_irmaa:         fill to IRMAA tier threshold only (no bracket cap)
    # fixed_dollar:          convert a fixed dollar amount per year
    # none:                  no voluntary conversions (forced-only via Forced Actions)
    c['roth_policy'] = normalize_roth_policy(_v(data,'Withdrawal Policy','Roth Conversion',
                           'roth_conversion_policy','optimize_terminal_tax'), 'optimize_terminal_tax').strip().lower()
    if c['roth_policy'] not in _td.ROTH_POLICIES:
        c['roth_policy'] = 'optimize_terminal_tax'
    if is_explicit_user_roth_policy(c['roth_policy']):
        c['roth_policy_lock'] = 'USER_SELECTED'
    _roth_bracket_strategy = str(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_bracket_strategy','OPTIMIZER_CHOOSES') or 'OPTIMIZER_CHOOSES').strip().upper()
    if _roth_bracket_strategy not in ('NONE','FILL_CURRENT_BRACKET','FILL_TARGET_BRACKET','PARTIAL_TARGET_BRACKET','IRMAA_GUARDED','SURVIVOR_TAX_AWARE','RMD_REDUCTION','LEGACY_TARGETED','OPTIMIZER_CHOOSES','FIXED_DOLLAR'):
        _roth_bracket_strategy = 'OPTIMIZER_CHOOSES'
    if is_explicit_user_roth_policy(c['roth_policy']) and _roth_bracket_strategy == 'OPTIMIZER_CHOOSES':
        _roth_bracket_strategy = strategy_for_roth_policy(c['roth_policy'], _roth_bracket_strategy)
    c['roth_bracket_strategy'] = _roth_bracket_strategy
    c['roth_target_rate'] = percent_to_float(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_target_bracket_rate','0.22'), 0.22)
    _roth_irmaa_target_tier = str(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_irmaa_target_tier','TIER_2') or 'TIER_2').strip().upper().replace(' ', '_')
    if _roth_irmaa_target_tier not in ('TIER_1','TIER_2','TIER_3','TIER_4','TIER_5'):
        _roth_irmaa_target_tier = 'TIER_2'
    c['roth_irmaa_target_tier'] = _roth_irmaa_target_tier
    try:
        _idx = int(_roth_irmaa_target_tier.split('_')[-1]) - 1
        c['roth_irmaa_target_threshold_mfj'] = float(_td.IRMAA_TIERS_BASE_YEAR.get('MFJ', [])[max(0, _idx)][0])
    except Exception:
        c['roth_irmaa_target_threshold_mfj'] = 268000.0
    c['roth_fixed_amount']= _n(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_fixed_annual_amount','50000'), 50000)
    c['roth_max_annual_conversion_pct_of_traditional_ira'] = min(1.0, max(0.0, _n(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'max_annual_conversion_pct_of_traditional_ira','20%'), 0.20)))
    try:
        c['roth_max_conversion_years'] = int(_n(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'max_conversion_years','10'), 10))
    except Exception:
        c['roth_max_conversion_years'] = 10
    _roth_objective_mode = str(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_objective_mode','BALANCED_RETIREMENT') or 'BALANCED_RETIREMENT').strip().upper()
    if _roth_objective_mode not in ('BALANCED_RETIREMENT','MINIMIZE_LIFETIME_TAX','MAXIMIZE_TERMINAL_NET_WORTH','LEGACY_OPTIMIZED','ESTATE_TAX_AWARE','CUSTOM_WEIGHTED'):
        _roth_objective_mode = 'BALANCED_RETIREMENT'
    c['roth_objective_mode'] = _roth_objective_mode
    c['roth_headroom_usage_pct'] = min(1.0, max(0.0, _n(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_headroom_usage_pct','95%'), 0.95)))
    c['roth_irmaa_headroom_usage_pct'] = min(1.0, max(0.0, _n(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_irmaa_headroom_usage_pct','95%'), 0.95)))
    c['irmaa_guardrail_mode'] = normalize_irmaa_guardrail_mode(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'irmaa_guardrail_mode','AVOID_NEXT_TIER'), 'AVOID_NEXT_TIER')
    if c['irmaa_guardrail_mode'] not in ('IGNORE','WARN_ONLY','AVOID_NEXT_TIER','AVOID_TIER_2_OR_ABOVE','CUSTOM_MAGI_CAP'):
        c['irmaa_guardrail_mode'] = 'AVOID_NEXT_TIER'
    # The single controlling setting is IRMAA Guardrail Behavior.
    if c['roth_policy'] == 'fill_to_irmaa':
        c['roth_irmaa_cap'] = True
    else:
        c['roth_irmaa_cap'] = c['irmaa_guardrail_mode'] not in ('IGNORE', 'WARN_ONLY')
    _estate_mode = str(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'estate_tax_objective_mode','BALANCED') or 'BALANCED').strip().upper()
    if _estate_mode not in ('OFF','MONITOR_ONLY','BALANCED','STRONG'):
        _estate_mode = 'BALANCED'
    c['estate_tax_objective_mode'] = _estate_mode
    c['roth_optimize_terminal_weight'] = _n(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_optimize_terminal_weight','1.0'), 1.0)
    c['roth_optimize_tax_weight'] = _n(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_optimize_lifetime_tax_weight','0.25'), 0.25)
    c['roth_optimize_terminal_tax_rate'] = _n(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_optimize_terminal_pretax_tax_rate','0.24'), 0.24)
    # Legacy-aware Roth conversion objective controls. These inputs let the
    # optimizer value tax-rate diversification, future ordinary-tax risk,
    # survivor tax compression, and the tax burden inherited with pre-tax IRA
    # balances. They are objective weights only; the projection cash-flow/tax
    # mechanics still use the standard tax assumptions.
    _legacy_mode = str(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'legacy_objective_mode','BALANCED') or 'BALANCED').strip().upper()
    if _legacy_mode not in ('OFF', 'LOW', 'BALANCED', 'STRONG'):
        _legacy_mode = 'BALANCED'
    c['roth_legacy_objective_mode'] = _legacy_mode
    c['roth_future_tax_rate_stress_pct'] = _n(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'future_tax_rate_stress_pct','10%'), 0.10)
    c['roth_future_tax_risk_weight'] = _n(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'future_tax_risk_weight','0.35'), 0.35)
    c['roth_inheritance_tax_burden_weight'] = _n(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'inheritance_tax_burden_weight','0.25'), 0.25)
    c['roth_heir_ordinary_tax_rate_assumption'] = _n(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'heir_ordinary_tax_rate_assumption_pct','24%'), 0.24)
    c['roth_pre_tax_bequest_penalty_pct'] = _n(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'pre_tax_bequest_penalty_pct','15%'), 0.15)
    c['roth_bequest_preference_bonus_pct'] = _n(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_bequest_preference_bonus_pct','5%'), 0.05)
    c['roth_survivor_tax_risk_weight'] = _n(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'survivor_tax_risk_weight','0.25'), 0.25)
    c['roth_tax_discount_rate'] = _n(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_tax_discount_rate', str(c.get('inf', 0.025))), c.get('inf', 0.025))

    # Estate
    c['fed_exempt']  = _n(_v(data,'Estate Planning','Federal','exemption_mfj','30000000'), 30000000)
    c['il_exempt']   = _n(_v(data,'Estate Planning','Illinois','state_estate_exemption','4000000'), 4000000)
    c['basis_step_up_at_death'] = _b(_v(data,'Estate Planning','Step-Up','basis_step_up_at_death','TRUE'))
    c['basis_step_up_property_regime'] = str(_v(data,'Estate Planning','Step-Up','property_regime','COMMON_LAW') or 'COMMON_LAW').strip().upper()
    if c['basis_step_up_property_regime'] not in ('COMMON_LAW','COMMUNITY_PROPERTY','HALF_STEP_UP','FULL_STEP_UP'):
        c['basis_step_up_property_regime'] = 'COMMON_LAW'
    c['federal_portability_enabled'] = _b(_v(data,'Estate Planning','Federal','portability_enabled','TRUE'))
    c['qss_dependent'] = _b(_v(data,'Household','','survivor_has_dependent','FALSE'))
    # Credit Shelter Trust: if enabled, each spouse uses their own exemption → doubles effective exemption
    c['credit_shelter_trust'] = str(_v(data,'Estate Planning','Trust Structure',
                                       'credit_shelter_trust','FALSE')).strip().upper() in ('TRUE','YES','ON','1')
    # Do not double the IL exemption as a shortcut.  The projection now tracks
    # actual first-death credit-shelter funding and subtracts that funded amount
    # from the survivor's taxable estate.
    c['gift_excl']   = _n(_v(data,'Estate Planning','Gifting','annual_exclusion_per_donee','19000'), 19000)
    # QTIP Trust — elected by executor to qualify marital deduction; controls disposition after survivor's death
    c['qtip_enabled']      = _b(_v(data,'Estate Planning','QTIP Trust','enabled','FALSE'))
    c['qtip_amount']       = _n(_v(data,'Estate Planning','QTIP Trust','funding_amount','0'), 0)
    c['qtip_note']         = _v(data,'Estate Planning','QTIP Trust','note',
                                 'Provides income to surviving spouse; controls ultimate beneficiaries')
    # Credit Shelter Trust (Bypass Trust) — preserves IL $4M exemption at first death
    c['cs_enabled']        = _b(_v(data,'Estate Planning','Credit Shelter Trust','enabled','TRUE'))
    c['cs_amount']         = _n(_v(data,'Estate Planning','Credit Shelter Trust','amount',
                                  str(c['il_exempt'])), c['il_exempt'])
    c['cs_note']           = _v(data,'Estate Planning','Credit Shelter Trust','note',
                                 'Funds up to IL exemption ($4M); bypasses survivor estate for IL tax')
    # QTIP manages annuity income after first death (annuity held in QTIP for benefit of survivor)
    c['qtip_manages_annuity'] = _b(_v(data,'Estate Planning','QTIP Trust','manages_annuity_after_first_death','TRUE'))

    # Forced Actions — supports normalized Roth Conversion N rows:
    # source_account / year / amount. Legacy date-subsection rows still parse.
    c['forced_roth'] = {}  # {year: amount}
    c['forced_roth_accounts'] = {}  # {year: [{'source_account': id, 'amount': dollars}]}
    for sub, vals in data.get('Forced Actions',{}).items():
        low_sub = str(sub or '').lower()
        if low_sub.startswith('roth conversion'):
            yr = _y(vals.get('year', 0), 0)
            amt = _n(vals.get('amount', 0), 0)
            acct = str(vals.get('source_account', '') or '').strip()
            if yr and amt:
                c['forced_roth'][yr] = c['forced_roth'].get(yr, 0) + amt
                c['forced_roth_accounts'].setdefault(yr, []).append({'source_account': acct, 'amount': amt})
            continue
        for lbl, val in vals.items():
            if 'roth_conversion' in str(lbl).lower() or ('roth' in str(lbl).lower() and 'amount' in str(lbl).lower()):
                yr = _y(str(sub).split('/')[-1], 0)
                if yr:
                    amt = _n(val,0)
                    c['forced_roth'][yr] = c['forced_roth'].get(yr,0) + amt
                    c['forced_roth_accounts'].setdefault(yr, []).append({'source_account': '', 'amount': amt})

    # Payroll tax
    c['ss_wage_base'] = _n(_v(data,'Payroll Tax','Social Security','ss_wage_base_base_year','184500'), 184500)
    c['ss_ee_rate']   = _n(_v(data,'Payroll Tax','Social Security','ss_employee_rate','0.062'), 0.062)
    c['ss_se_rate']   = _n(_v(data,'Payroll Tax','Social Security','ss_self_employment_rate','0.124'), 0.124)
    c['med_ee_rate']  = _n(_v(data,'Payroll Tax','Medicare','medicare_employee_rate','0.0145'), 0.0145)
    c['med_se_rate']  = _n(_v(data,'Payroll Tax','Medicare','medicare_self_employment_rate','0.029'), 0.029)
    c['add_med_rate'] = _n(_v(data,'Payroll Tax','Medicare','additional_medicare_rate','0.009'), 0.009)
    c['add_med_thr']  = _n(_v(data,'Payroll Tax','Medicare','additional_medicare_threshold_mfj','250000'), 250000)
    c['se_factor']    = _n(_v(data,'Payroll Tax','Self-Employment','se_net_earnings_factor','0.9235'), 0.9235)
    c['se_half_ded']  = _b(_v(data,'Payroll Tax','Self-Employment','se_half_deductible','TRUE'))

    # Annuity Death Benefits
    c['ann_db'] = {}   # {year: {W_Single, W_Joint, H_Single, H_Joint}}
    for sub, vals in data.get('Annuity Death Benefits',{}).items():
        yr = _y(sub, 0)
        if yr:
            c['ann_db'][yr] = {k: _n(v,0) for k,v in vals.items()}

    # Income Streams (annuities) — age-86 principal recovery model
    # recovery_age: age at which principal is fully recovered (default 86)
    ann_recovery_age = _n(_v(data,'Income Streams','Recovery Age','principal_recovery_age','86'), 86)
    c['ann_recovery_age'] = int(ann_recovery_age)

    def load_stream(name, annuitant='wife'):
        s = {}
        s['first_yr'] = _y(_v(data,'Income Streams',name,'first_payment', str(c['plan_start'] + 3)).split('/')[-1], c['plan_start'] + 3)
        s['base']     = _n(_v(data,'Income Streams',name,'base','0'), 0)
        s['div_rate'] = _n(_v(data,'Income Streams',name,'dividend_rate',str(c['ann_div'])), c['ann_div'])
        # add_pct = reinvested fraction (20% default); cash payout = 80%
        s['add_pct']  = _n(_v(data,'Income Streams',name,'additional_income_pct',str(c['ann_add'])), c['ann_add'])
        s['cash_pct'] = 1.0 - s['add_pct']   # 80% cash out
        s['init_pmt'] = _n(_v(data,'Income Streams',name,'initial_guaranteed_income_payment','0'), 0)
        s['cum_at_death']     = _n(_v(data,'Income Streams',name,'cumulative_at_death','0'), 0)
        # Deferral years: contract years before income starts where dividends are 100% reinvested
        s['deferral_years']   = int(_n(_v(data,'Income Streams',name,'deferral_years','0'), 0))
        # Reserve model calibration (deferred income annuity): reserve_factor anchors the dividend base,
        # deferral_dampening scales deferral-period income growth.
        s['reserve_factor']   = _n(_v(data,'Income Streams',name,'reserve_factor','0.853'), 0.853)
        # Market type: qualified (IRA/401k) vs non-qualified (Personal) — affects state taxation
        s['qualified']        = _b(_v(data,'Income Streams',name,'qualified','TRUE'))
        # Purchase year: when the premium transfers from IRA to annuity.
        # 0 = already purchased (no deduction). >0 = deduct base from source IRA that year.
        s['purchase_year']    = _y(_v(data,'Income Streams',name,'purchase_year','0'), 0)
        s['source_account']   = (_v(data,'Income Streams',name,'source_account','') or '').strip()
        # Exclusion ratio for non-qualified annuities: taxable fraction of each payment.
        # Qualified (IRA) annuities are 100% taxable (no basis). Default 1.0.
        s['exclusion_ratio']  = _n(_v(data,'Income Streams',name,'exclusion_ratio','1.0'), 1.0)
        s['deferral_dampening'] = _n(_v(data,'Income Streams',name,'deferral_dampening','0.55'), 0.55)
        # Payout type: Fixed (guaranteed), Variable (market-linked), COLA (inflation-linked)
        raw_payout = str(_v(data,'Income Streams',name,'payout_type','fixed') or 'fixed').strip().lower()
        s['payout_type'] = 'variable' if 'var' in raw_payout else ('cola' if 'cola' in raw_payout else 'fixed')
        # Annuitant info for recovery logic
        s['annuitant_dob_yr'] = c['w_dob_yr'] if annuitant == 'wife' else c['h_dob_yr']
        s['recovery_age']     = c['ann_recovery_age']
        s['annuity_calib']    = c.get('annuity_calib', _td.DEFAULT_ANNUITY_CALIB)
        return s

    c['wife_pension']   = load_stream('Member 2 Pension',          annuitant='wife')
    c['wife_single']    = load_stream('Member 2 Single Annuity',   annuitant='wife')
    c['wife_joint']     = load_stream('Member 2 Joint Annuity',    annuitant='wife')
    c['h_single']       = load_stream('Member 1 Single Annuity',   annuitant='husband')
    c['h_joint']        = load_stream('Member 1 Joint Annuity',    annuitant='husband')
    _js_raw = _v(data,'Income Streams','Joint-and-Survivor Percentage','js_pct','100')
    c['js_pct'] = _n(_js_raw, 100)
    # If the source string contained '%', _n already converted to fraction (e.g. "100%" → 1.0).
    # If it was a plain integer like "100", _n returns 100.0 → divide by 100.
    if '%' not in str(_js_raw):
        c['js_pct'] /= 100.0
    c['pv_age']         = _n((_v(data,'Income Streams','Present Value Horizon','age_to_value_through',None) or _v(data,'Income Streams','PV Horizon','age_to_value_through','85')), 85)

    # Plan settings are system/model controls, sourced from system_config.csv.
    c['model_niit']       = _b(_sv('Plan Settings','Tax Detail','model_niit','TRUE'))
    c['model_state_est']  = _b(_sv('Plan Settings','Estate','model_state_estate_tax','TRUE'))

    # Global/tax-aware rebalancing controls. These live in system_config.csv so
    # a UI build and a command-line build use the same trade recommendation mode.
    c['trade_optimizer_mode'] = (_sv('Rebalancing','Optimization','trade_optimizer_mode','GLOBAL_TAX_AWARE') or 'GLOBAL_TAX_AWARE').strip().upper()
    c['rebalance_max_tax_cost_bps'] = _n(_sv('Rebalancing','Optimization','max_tax_cost_bps','25'), 25)
    c['rebalance_min_trade_amount'] = _n(_sv('Rebalancing','Optimization','min_trade_amount','500'), 500)
    c['rebalance_max_turnover_pct'] = _n(_sv('Rebalancing','Optimization','max_turnover_pct','20.00%'), 0.20)
    c['rebalance_wash_sale_policy'] = (_sv('Rebalancing','Optimization','wash_sale_policy','FLAG_ONLY') or 'FLAG_ONLY').strip().upper()
    c['rebalance_allow_taxable_gain_sales'] = (_sv('Rebalancing','Optimization','allow_taxable_gain_sales','DRIFT_THRESHOLD') or 'DRIFT_THRESHOLD').strip().upper()
    c['rebalance_asset_location_strength'] = (_sv('Rebalancing','Optimization','asset_location_strength','BALANCED') or 'BALANCED').strip().upper()
    c['rebalance_max_account_single_asset_pct'] = _n(_sv('Rebalancing','Risk Controls','max_account_single_asset_pct','45.00%'), 0.45)
    c['rebalance_max_roth_high_growth_pct'] = _n(_sv('Rebalancing','Risk Controls','max_roth_high_growth_pct','85.00%'), 0.85)
    c['rebalance_max_pre_tax_fixed_income_pct'] = _n(_sv('Rebalancing','Risk Controls','max_pre_tax_fixed_income_pct','85.00%'), 0.85)
    c['rebalance_max_trades_per_account'] = _n(_sv('Rebalancing','Risk Controls','max_trades_per_account','8'), 8)
    c['rebalance_legacy_gain_deferral_pct'] = _n(_sv('Rebalancing','Risk Controls','legacy_gain_deferral_pct','20.00%'), 0.20)
    c['rebalance_taxable_gain_budget_annual'] = _n(_sv('Rebalancing','Tax-aware Trades','taxable_gain_budget_annual','2500'), 2500)
    c['rebalance_ltcg_rate'] = _n(_sv('Rebalancing','Tax-aware Trades','ltcg_rate','15.00%'), 0.15)
    c['rebalance_max_tax_drag_pct'] = _n(_sv('Rebalancing','Tax-aware Trades','max_tax_drag_pct','1.50%'), 0.015)
    c['rebalance_force_taxable_sell_drift_pct'] = _n(_sv('Rebalancing','Tax-aware Trades','force_taxable_sell_drift_pct','8.00%'), 0.08)
    c['rebalance_taxable_review_drift_pct'] = _n(_sv('Rebalancing','Tax-aware Trades','taxable_review_drift_pct','5.00%'), 0.05)
    c['rebalance_drift_penalty_per_dollar'] = _n(_sv('Rebalancing','Objective Weights','drift_penalty_per_dollar','1.0'), 1.0)
    c['rebalance_turnover_penalty_per_dollar'] = _n(_sv('Rebalancing','Objective Weights','turnover_penalty_per_dollar','0.02'), 0.02)
    c['rebalance_solver_fallback_policy'] = (_sv('Rebalancing','Optimization','solver_fallback_policy','HEURISTIC') or 'HEURISTIC').strip().upper()

    # Positions — derived from client_holdings.csv (primary) or client_data.csv when holdings are absent
    # The holdings file is the single source of truth for all positions.
    # client_data.csv Positions rows are only used if no holdings file exists.
    _csv_positions = {}
    for sub, vals in data.get('Positions',{}).items():
        _csv_positions[sub] = {k: _n(v,0) for k,v in vals.items()}
    c['positions'] = _csv_positions  # may be overridden after lots loading
    c['balances'] = {}               # computed after lots loading
    c['cash_other'] = 0.0

    # Workbook optional-function toggles are system/model controls.
    opts = system_data.get('Optional Functions',{}).get('',{}) or data.get('Optional Functions',{}).get('',{})
    c['opt'] = {k: _b(v) for k,v in opts.items()}

    # Scenario parameters — all sourced from CSV Scenarios section
    c['scen_retire_later_yr']  = _y(_v(data,'Scenarios','Retire Later',
                                        'member_1_retire_year',
                                        str(c['h_ret_yr'] + 2)), c['h_ret_yr'] + 2)
    # Income growth rate for extension years (default: flat — 0% raise after base earn_end)
    c['scen_retire_inc_growth']= _n(_v(data,'Scenarios','Retire Later',
                                        'income_growth_rate_override', '0.00%'), 0.0)
    # Salary for extension years — parsed after scorp_salary is set (see below)
    c['scen_spend_mult']       = _n(_v(data,'Scenarios','Higher Spending',
                                        'spend_multiplier', '1.20'), 1.20)
    c['scen_downsize_yr']      = _y(_v(data,'Scenarios','Downsize Home',
                                        'home_downsize_year', '2035'), 2035)
    c['scen_downsize_net']     = _n(_v(data,'Scenarios','Downsize Home',
                                        'home_downsize_net_proceeds', '400000'), 400_000)
    # Sell Home scenario — full model (basis, §121, LTCG, mortgage payoff).
    # Sale value and basis are single-source: canonical Other Assets > Home
    # rows drive both base-plan and scenario calculations.  Scenario rows only
    # set the scenario year, proceeds destination, and scenario-specific rent.
    c['scen_sell_yr']          = _y(_v(data,'Scenarios','Sell Home',
                                        'home_sale_year', '2035'), 2035)
    c['scen_sell_px']          = 0
    c['scen_sell_px_source']   = 'Projected Other Assets/Home/value_as_of_plan_start using appreciation_rate'
    c['scen_sell_basis']       = c.get('home_basis', 0)
    c['scen_sell_basis_source'] = 'Other Assets/Home/home_basis'
    c['scen_sell_acct']        = (_v(data,'Scenarios','Sell Home',
                                        'home_sale_proceeds_account', '') or '').strip()
    c['scen_inf_override']     = _n(_v(data,'Scenarios','High Inflation',
                                        'inflation_override', '0.045'), 0.045)
    c['scen_ret_override']     = _n(_v(data,'Scenarios','Low Return',
                                        'portfolio_return_override', '0.04'), 0.04)
    # PDIA what-if scenarios
    c['scen_pdia_div_lo']      = _n(_v(data,'Scenarios','PDIA Lower Dividend',
                                        'annuity_div_override', '0.045'), 0.045)
    c['scen_pdia_split_5050']  = _n(_v(data,'Scenarios','PDIA 50-50 Split',
                                        'annuity_split_override', '0.50'), 0.50)
    # Stackable combined-scenario toggles
    c['combo_sell_home']      = _b(_v(data,'Scenarios','Combined Stress Test','include_sell_home','TRUE'))
    c['combo_low_return']     = _b(_v(data,'Scenarios','Combined Stress Test','include_low_return','TRUE'))
    c['combo_high_inflation'] = _b(_v(data,'Scenarios','Combined Stress Test','include_high_inflation','FALSE'))
    c['combo_spend_more']     = _b(_v(data,'Scenarios','Combined Stress Test','include_spend_more','FALSE'))
    c['combo_retire_later']   = _b(_v(data,'Scenarios','Combined Stress Test','include_retire_later','FALSE'))
    c['combo_pdia_low_div']   = _b(_v(data,'Scenarios','Combined Stress Test','include_pdia_low_div','TRUE'))
    c['combo_pdia_5050']      = _b(_v(data,'Scenarios','Combined Stress Test','include_pdia_5050','FALSE'))
    c['rollover_401k_yr']  = _y(_v(data,'Model Constants','Retirement',
                                     'rollover_401k_year', str(c['plan_start'] + 4)), c['plan_start'] + 4)
    c['ss_claim_age']      = int(_n(_v(data,'Model Constants','Retirement',
                                     'ss_claim_age','70'), 70))
    c['h_ss_claim_age']    = int(_n(_v(data,'Social Security','Member 1','claim_age',
                                     str(c['ss_claim_age'])), c['ss_claim_age']))
    c['w_ss_claim_age']    = int(_n(_v(data,'Social Security','Member 2','claim_age',
                                     str(c['ss_claim_age'])), c['ss_claim_age']))
    c['rmd_start_age']     = int(_n(_v(data,'Model Constants','Retirement',
                                     'rmd_start_age','75'), 75))
    c['conv_window_offset']= int(_n(_v(data,'Model Constants','Roth Conversion',
                                     'roth_conv_window_end_offset','-1'), -1))
    c['irmaa_base']   = _n(_v(data,'Model Constants','IRMAA',
                                     'irmaa_tier2_mfj_base_year', str(_td.IRMAA_TIERS_BASE_YEAR.get('MFJ', [(0,), (268000,)])[1][0])), 268_000)
    c['irmaa_inflator']    = _n(_v(data,'Model Constants','IRMAA',
                                     'irmaa_annual_inflator','0.02'), 0.02)
    c['mc_sigma']          = _n(_v(data,'Model Constants','Monte Carlo',
                                     'mc_portfolio_sigma','0.12'), 0.12)
    c['mc_sims']           = int(os.getenv('RETIREMENT_MC_SIMS') or _n(_v(data,'Model Constants','Monte Carlo',
                                     'mc_simulations','1000'), 1000))
    c['mc_sensitivity_sims'] = int(os.getenv('RETIREMENT_MC_SENSITIVITY_SIMS') or _n(_v(data,'Model Constants','Monte Carlo',
                                     'mc_sensitivity_simulations','200'), 200))
    # Phones run the exact-scalar Monte Carlo engine several times slower than
    # a desktop CPU, so mobile hosts cap the path counts (a plan authored on
    # desktop with mc_simulations=1000 would otherwise take minutes on-device).
    # None everywhere else — desktop/server results are untouched.
    _mc_cap = _platform_runtime.mobile_mc_sims_cap()
    if _mc_cap is not None:
        c['mc_sims'] = min(c['mc_sims'], _mc_cap)
        c['mc_sensitivity_sims'] = min(c['mc_sensitivity_sims'], max(1, _mc_cap // 5))
    _mc_engine_raw = str(_v(data,'Model Constants','Monte Carlo',
                                     'mc_engine_mode','advanced_exact_scalar') or 'advanced_exact_scalar').strip().lower()
    _mc_engine_map = {
        'advanced_exact_scalar': 'exact_scalar',
        'exact_scalar': 'exact_scalar',
        'quick_vectorized': 'vectorized',
        'vectorized': 'vectorized',
    }
    c['mc_engine_mode'] = _mc_engine_map.get(_mc_engine_raw, _mc_engine_raw)
    c['mc_success_liquid_floor'] = _n(_v(data,'Model Constants','Monte Carlo',
                                     'success_liquid_floor','0'), 0)
    c['mc_recenter_regime_returns'] = _b(_v(data,'Model Constants','Monte Carlo',
                                     'recenter_regime_returns','TRUE'))
    # Asset allocation — drives blended return per account
    c['alloc_equity']      = _n(_v(data,'Model Constants','Asset Allocation',
                                     'equity_pct','85.00%'), 0.85)
    c['alloc_commodity']   = _n(_v(data,'Model Constants','Asset Allocation',
                                     'commodity_pct','10.00%'), 0.10)
    c['alloc_cash']        = _n(_v(data,'Model Constants','Asset Allocation',
                                     'cash_pct','5.00%'), 0.05)
    # Blended return from allocation (informational only — CSV portfolio_nominal_return
    # is the authoritative return for deterministic projection)
    c['blended_return_info'] = (c['alloc_equity'] * ASSET_CLASS_RETURNS.get('equity', 0.08) +
                                c['alloc_commodity'] * ASSET_CLASS_RETURNS.get('commodity', 0.05) +
                                c['alloc_cash'] * ASSET_CLASS_RETURNS.get('cash', 0.02))
    # Stochastic MC settings
    c['mc_bracket_stochastic'] = _b(_v(data,'Model Constants','Monte Carlo',
                                        'stochastic_tax_brackets','TRUE'))
    c['mc_irmaa_stochastic']   = _b(_v(data,'Model Constants','Monte Carlo',
                                        'stochastic_irmaa','TRUE'))
    c['mc_wellness_shocks']  = _b(_v(data,'Model Constants','Monte Carlo',
                                        'wellness_cost_shocks','TRUE'))
    c['mc_wellness_prob']    = _n(_v(data,'Model Constants','Monte Carlo',
                                        'wellness_shock_annual_prob','0.03'), 0.03)
    c['mc_wellness_mean']    = _n(_v(data,'Model Constants','Monte Carlo',
                                        'wellness_shock_mean_cost','150000'), 150000)
    c['mc_inflation_stochastic'] = _b(_v(data,'Model Constants','Monte Carlo',
                                        'stochastic_inflation','TRUE'))
    c['mc_inflation_sigma'] = _n(_v(data,'Model Constants','Monte Carlo',
                                        'inflation_sigma','1.50%'), 0.015)
    c['mc_return_inflation_corr'] = _n(_v(data,'Model Constants','Monte Carlo',
                                        'return_inflation_correlation','-0.25'), -0.25)
    c['mc_use_asset_class_covariance'] = _b(_v(data,'Model Constants','Monte Carlo',
                                        'use_asset_class_covariance','TRUE'))
    c['mc_serial_correlation'] = _n(_v(data,'Model Constants','Monte Carlo',
                                        'return_serial_correlation','0.15'), 0.15)
    # Home sale selling costs (realtor commission + closing), as fraction of gross
    c['home_sell_cost_pct']= _n(_v(data,'Model Constants','Home Sale',
                                     'selling_cost_pct','0.06'), 0.06)
    # LTCG bracket thresholds (MFJ, tax-reference-year base; inflated by irmaa-style inflator)
    c['ltcg_0_top']        = _n(_v(data,'Model Constants','Capital Gains',
                                     'ltcg_0pct_top_mfj_base_year','96700'), 96_700)
    c['ltcg_15_top']       = _n(_v(data,'Model Constants','Capital Gains',
                                     'ltcg_15pct_top_mfj_base_year','600050'), 600_050)
    c['niit_threshold']    = _n(_v(data,'Model Constants','Capital Gains',
                                     'niit_magi_threshold_mfj','250000'), 250_000)

    # ── Annuity Calibration (9.4) — carrier-agnostic purchase-rate curve ──────
    # Each segment: age_start, age_end, base_rate, slope (per year).
    # Defaults match the current calibration; edit to match any carrier.
    _default_calib = _td.DEFAULT_ANNUITY_CALIB
    c['annuity_calib'] = dict(_default_calib)  # copy defaults
    # Override from CSV if present (Annuity Calibration section)
    _ac = data.get('Annuity Calibration', {})
    if _ac.get('Purchase Rate', {}):
        _pr = _ac['Purchase Rate']
        segments = []
        for i in range(1, 10):
            _key_start = f'seg{i}_age_start'
            _key_end   = f'seg{i}_age_end'
            _key_base  = f'seg{i}_base_rate'
            _key_slope = f'seg{i}_slope'
            if _key_start in _pr:
                segments.append({
                    'age_start': int(_n(_pr[_key_start], 0)),
                    'age_end':   int(_n(_pr[_key_end], 999)),
                    'base_rate': _n(_pr[_key_base], 0.05),
                    'slope':     _n(_pr[_key_slope], 0.0),
                })
        if segments:
            c['annuity_calib']['purchase_rate_segments'] = segments
    if _ac.get('Reserve Decay', {}):
        _rd = _ac['Reserve Decay']
        for key in ['reserve_decay_rate','reserve_decay_period','mortality_credit_boost',
                     'post_credit_decay_rate','post_credit_decay_period','late_life_growth_rate']:
            if key in _rd:
                c['annuity_calib'][key] = _n(_rd[key], _default_calib[key])

    # ── Allocation Optimizer Inputs ──────────────────────────────────────
    # 1. Risk tolerance (1-10, 0 = auto-derive from age + withdrawal rate)
    c['risk_tolerance'] = _n(_v(data,'Model Constants','Allocation',
                                'risk_tolerance','0'), 0)
    # 2. Asset class assumptions (use selected capital-market horizon/preset
    # unless overridden). Returns/volatility are user-editable; full pairwise
    # correlations are editable in advanced/expert mode.
    c['asset_class_overrides'] = {}
    c['asset_class_enabled'] = {}
    c['asset_class_selection_action'] = {}
    c['asset_class_alternate_first'] = {}
    c['allocation_target_pct'] = {}
    c['allocation_optimizer_override_pct'] = {}
    c['allocation_target_notes'] = {}
    c['allocation_target_sum'] = 0.0
    c['allocation_selection_mode'] = 'user_target'
    c['allocation_optimizer_comment'] = getattr(_ap, 'OPTIMIZER_RECOMMENDATION_COMMENT', '')
    c['capital_market_config'] = {}
    c['asset_correlation_overrides'] = {}
    _aco = data.get('Asset Class Assumptions', {})
    # Client-owned asset allocation policy lives separately from system-owned
    # capital-market assumptions. Expected return/volatility and correlations
    # come from Asset Class Assumptions / Asset Correlations in system_config.csv
    # or reference files; include/min/max allocation controls come from
    # client_policy.csv under Asset Allocation Policy.
    _aap = data.get('Asset Allocation Policy', {})
    _opt_controls = data.get('Asset Class Optimizer Controls', {})
    _aap_global = _aap.get('Global', {}) if isinstance(_aap, dict) else {}
    _aap_global = _aap_global if isinstance(_aap_global, dict) else {}
    c['allocation_selection_mode'] = _ap.normalize_allocation_mode(
        _aap_global.get('allocation_selection_mode',
                        _aap_global.get('allocation_mode',
                                        _aap_global.get('use_allocation_optimizer', 'user_target')))
    )
    _global = _aco.get('Global', {}) if isinstance(_aco, dict) else {}
    if isinstance(_global, dict):
        c['capital_market_config'] = {
            'assumption_mode': (_global.get('capital_market_assumption_mode') or _global.get('assumption_mode') or 'PRESET'),
            'horizon_years': _n(_global.get('capital_market_assumption_horizon_years', _global.get('horizon_years', '30')), 30),
            'preset': (_global.get('capital_market_assumption_preset') or _global.get('preset') or 'BASELINE'),
            'use_custom_capital_market_file': _b(_global.get('use_custom_capital_market_file', 'NO')),
            'custom_capital_market_file': (_global.get('custom_capital_market_file') or 'capital_market_assumptions.csv'),
            'correlation_assumption_mode': (_global.get('correlation_assumption_mode') or 'PRESET'),
            'correlation_preset': (_global.get('correlation_preset') or 'MODERATE'),
            'use_custom_correlations_file': _b(_global.get('use_custom_correlations_file', 'NO')),
            'custom_correlations_file': (_global.get('custom_correlations_file') or 'asset_correlations.csv'),
        }
    raw_class_names = set(getattr(_ap, 'DEFAULT_ALLOCATION_TARGETS', {}).keys())
    if isinstance(_aco, dict):
        raw_class_names.update(k for k in _aco.keys() if k != 'Global')
    if isinstance(_aap, dict):
        raw_class_names.update(k for k in _aap.keys() if k != 'Global')
    if isinstance(_opt_controls, dict):
        raw_class_names.update(k for k in _opt_controls.keys() if k != 'Global')
    class_names = sorted({_ap.canonical_asset_class(k) for k in raw_class_names})
    for cls_name in class_names:
        # Gold/precious-metal sleeves are intentionally excluded from the v7.8
        # recommendation model and from future allocation consideration.
        if cls_name not in getattr(_ao, 'ASSET_CLASSES', {}):
            continue
        def _section_vals(src, canonical):
            if not isinstance(src, dict):
                return {}
            for key, vals in src.items():
                if key == 'Global':
                    continue
                if _ap.canonical_asset_class(key) == canonical and isinstance(vals, dict):
                    return vals
            return {}
        cap_vals = _section_vals(_aco, cls_name)
        policy_vals = _section_vals(_aap, cls_name)
        opt_vals = _section_vals(_opt_controls, cls_name)
        cap_vals = cap_vals if isinstance(cap_vals, dict) else {}
        policy_vals = policy_vals if isinstance(policy_vals, dict) else {}
        default_target = getattr(_ap, 'DEFAULT_ALLOCATION_TARGETS', {}).get(cls_name, 0.0)
        raw_target = policy_vals.get('target_pct', '')
        target_pct = _n(raw_target, default_target)
        c['allocation_target_pct'][cls_name] = max(0.0, target_pct)
        c['allocation_target_notes'][cls_name] = getattr(_ap, 'ASSET_CLASS_NOTES', {}).get(cls_name, '')
        c['asset_class_overrides'][cls_name] = {
            'ret': _n(cap_vals.get('expected_return', ''), -1),
            'vol': _n(cap_vals.get('volatility', ''), -1),
            'target_pct': max(0.0, target_pct),
            'min_target': -1,
            'max_target': -1,
        }
        raw_override = opt_vals.get('optimizer_override_pct', '')
        c['allocation_optimizer_override_pct'][cls_name] = max(0.0, _n(raw_override, 0.0)) if str(raw_override).strip() else 0.0

        raw_action = opt_vals.get('selection_action', '')
        if str(raw_action).strip():
            action = _ap.normalize_selection_action(raw_action)
        else:
            action = getattr(_ap, 'DEFAULT_SELECTION_ACTIONS', {}).get(cls_name, getattr(_ap, 'SELECTION_INCLUDE', 'include'))
        c['asset_class_enabled'][cls_name] = action != getattr(_ap, 'SELECTION_EXCLUDE', 'exclude')
        raw_alt = opt_vals.get('alternate_asset_class', '')
        alt_text = str(raw_alt or '').strip()
        alt_cls = _ap.canonical_asset_class(alt_text) if alt_text else ''
        if alt_cls == cls_name:
            alt_cls = ''
        # If the alternate is another asset class, the optimizer redirects target
        # weight to that class. If it is an existing plan asset/source (e.g.
        # Social Security, Pension, Home Equity, Note Receivable), store the
        # source-to-target mapping so compute_allocation_coverage can count that
        # existing asset toward the selected class target.
        if alt_cls and alt_cls not in getattr(_ao, 'ASSET_CLASSES', {}):
            alt_cls = _ap.normalize_existing_asset_source(alt_cls)
            if action == getattr(_ap, 'SELECTION_ALTERNATE_FIRST', 'consider_alternate_first'):
                c.setdefault('allocation_source_target_class', {})[alt_cls] = cls_name
        c['asset_class_selection_action'][cls_name] = action
        c['asset_class_alternate_first'][cls_name] = alt_cls
    c['allocation_target_sum'] = sum(c['allocation_target_pct'].values())
    c['allocation_optimizer_override_sum'] = sum(c['allocation_optimizer_override_pct'].values())
    _corrs = data.get('Asset Correlations', {})
    if isinstance(_corrs, dict):
        for pair_name, vals in _corrs.items():
            if not isinstance(vals, dict):
                continue
            if '|' not in str(pair_name):
                continue
            _pair_parts = [_ap.canonical_asset_class(p.strip()) for p in str(pair_name).split('|', 1)]
            if any(part not in getattr(_ao, 'ASSET_CLASSES', {}) for part in _pair_parts):
                continue
            corr_val = vals.get('correlation', vals.get('corr', ''))
            if str(corr_val).strip():
                c['asset_correlation_overrides']['|'.join(_pair_parts)] = corr_val
    # 3. SS/pension bond PV — computed automatically from existing fields
    # (no new input needed — computed in allocation_optimizer.compute_optimal_allocation)
    # 4. Human capital stability factor (0-1, 0.8=stable W-2, 0.5=variable/SE)
    c['human_capital_stability'] = _n(_v(data,'Model Constants','Allocation',
                                          'human_capital_stability','0.80'), 0.80)
    # 5. Concentration flags (% of total wealth already in these categories)
    c['concentration_employer_stock'] = _n(_v(data,'Model Constants','Allocation',
                                               'concentration_employer_stock','0'), 0)
    c['concentration_real_estate'] = _n(_v(data,'Model Constants','Allocation',
                                            'concentration_real_estate','0'), 0)
    c['concentration_business'] = _n(_v(data,'Model Constants','Allocation',
                                         'concentration_business','0'), 0)
    # 6. Glide path: 'target_date' or 'static'
    c['glide_path'] = (_v(data,'Model Constants','Allocation',
                          'glide_path','target_date') or 'target_date').strip().lower()
    # 7. Inflation-sensitive spending (fraction of total spending)
    c['inflation_sensitive_spending_pct'] = _n(_v(data,'Model Constants','Allocation',
                                                   'inflation_sensitive_spending_pct','0.15'), 0.15)
    # Cash buffer target (% of portfolio to keep in cash as market-timing buffer).
    # The guided UI exposes this in the first asset-allocation table as the
    # Cash target_pct row.
    c['cash_target_pct'] = _n(_v(data,'Model Constants','Allocation',
                                  'cash_target_pct','0.05'), 0.05)
    if c.get('allocation_target_pct', {}).get('Cash') is not None:
        try:
            c['cash_target_pct'] = float(c['allocation_target_pct'].get('Cash') or c['cash_target_pct'])
        except Exception:
            pass

    # Allocation coverage policy is generated from the first allocation table.
    # No separate count-* Plan Data switches are read.
    c['allocation_coverage'] = {
        'social_security_satisfies_fixed_income_target': False,
        'pension_satisfies_fixed_income_target': False,
        'annuities_satisfy_fixed_income_target': False,
        'note_receivable_satisfies_fixed_income_target': False,
        'include_home_equity_in_allocation_view': _b(_v(data,'Model Constants','Allocation','include_home_equity_in_allocation_view','YES')),
        'home_equity_satisfies_reit_target': False,
        'liquid_reit_target_pct_when_home_not_counted': _n(_v(data,'Model Constants','Allocation','liquid_reit_target_pct_when_home_not_counted','5%'), 0.05),
    }
    _source_targets = c.get('allocation_source_target_class') or {}
    if _source_targets:
        _known = {'Social Security', 'Pension', 'Annuities', 'Note Receivable', 'Guaranteed income + note receivable', 'Home Equity'}
        if any(src in _known for src in _source_targets):
            # When the first allocation table is used, it becomes authoritative
            # for the old coverage-source-to-target flags.
            c['allocation_coverage']['social_security_satisfies_fixed_income_target'] = False
            c['allocation_coverage']['pension_satisfies_fixed_income_target'] = False
            c['allocation_coverage']['annuities_satisfy_fixed_income_target'] = False
            c['allocation_coverage']['note_receivable_satisfies_fixed_income_target'] = False
            c['allocation_coverage']['home_equity_satisfies_reit_target'] = False
        for _src, _target in _source_targets.items():
            _target = _ap.canonical_asset_class(_target)
            _is_fi = _target in getattr(_ap, 'FIXED_INCOME_CLASSES', set()) or _target in {'Bonds', 'Bonds/Fixed Income'}
            _is_re = _target in getattr(_ap, 'REAL_ESTATE_CLASSES', set()) or _target in {'REITs', 'REITs/Real Estate'}
            if _src == 'Guaranteed income + note receivable' and _is_fi:
                c['allocation_coverage']['social_security_satisfies_fixed_income_target'] = True
                c['allocation_coverage']['pension_satisfies_fixed_income_target'] = True
                c['allocation_coverage']['annuities_satisfy_fixed_income_target'] = True
                c['allocation_coverage']['note_receivable_satisfies_fixed_income_target'] = True
            elif _src == 'Social Security' and _is_fi:
                c['allocation_coverage']['social_security_satisfies_fixed_income_target'] = True
            elif _src == 'Pension' and _is_fi:
                c['allocation_coverage']['pension_satisfies_fixed_income_target'] = True
            elif _src == 'Annuities' and _is_fi:
                c['allocation_coverage']['annuities_satisfy_fixed_income_target'] = True
            elif _src == 'Note Receivable' and _is_fi:
                c['allocation_coverage']['note_receivable_satisfies_fixed_income_target'] = True
            elif _src == 'Home Equity' and _is_re:
                c['allocation_coverage']['include_home_equity_in_allocation_view'] = True
                c['allocation_coverage']['home_equity_satisfies_reit_target'] = True
    # Which account types should primarily accumulate cash (comma-separated)
    _cash_acct_pref = _v(data,'Model Constants','Allocation',
                          'cash_accumulation_accounts','taxable') or 'taxable'
    c['cash_accumulation_tax_types'] = [s.strip() for s in _cash_acct_pref.split(',')]

    # ── Tax Provenance Registry (9.6) ─────────────────────────────────────────
    # Load scalar overrides from tax_constants.csv; record provenance.
    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _search_dirs = [_project_root, os.getcwd(), '/mnt/user-data/outputs']
    c['tax_constants_registry'] = _td.load_tax_constants(_search_dirs)
    c['tax_provenance'] = dict(_td.TAX_YEAR_PROVENANCE)  # copy for the methodology sheet
    c['tax_table_currency_warnings'] = _td.tax_table_currency_warnings(max_lag_years=int(c.get('tax_table_currency_max_lag_years', 1) or 1))

    # DAF (Donor Advised Fund) parameters
    c['daf_enabled']      = _b(_v(data,'DAF','Settings','enabled','FALSE'))
    c['daf_amount']       = _n(_v(data,'DAF','Settings','contribution_amount','0'), 0)
    c['daf_year']         = _y(_v(data,'DAF','Settings','contribution_year', str(c['plan_start'])), c['plan_start'])
    c['daf_use_amount']   = _n(_v(data,'DAF','Settings','annual_grant_amount','0'), 0)
    c['daf_use_start']    = _y(_v(data,'DAF','Settings','grant_start_year','2027'), 2027)
    c['daf_use_end']      = _y(_v(data,'DAF','Settings','grant_end_year','2035'), 2035)

    # Hybrid Life/LTC parameters
    c['ltc_enabled']      = _b(_v(data,'Hybrid LTC','Settings','enabled','FALSE'))
    c['ltc_face']         = _n(_v(data,'Hybrid LTC','Settings','face_value','250000'), 250000)
    c['ltc_annual_prem']  = _n(_v(data,'Hybrid LTC','Settings','annual_premium','0'), 0)
    c['ltc_start_year']   = _y(_v(data,'Hybrid LTC','Settings','start_year','2027'), 2027)
    c['ltc_insured']      = _v(data,'Hybrid LTC','Settings','insured','Member 1')

    # ── HELOC strategy ──────────────────────────────────────────────────────────
    c['heloc_enabled'] = str(_v(data, 'HELOC', 'Setup', 'heloc_enabled', 'false') or 'false').strip().lower() in ('true', 'yes', '1')
    c['heloc_credit_limit'] = _n(_v(data, 'HELOC', 'Setup', 'heloc_credit_limit', '0'), 0.0)
    c['heloc_draw_end_year'] = int(float(_n(_v(data, 'HELOC', 'Setup', 'heloc_draw_end_year', '0'), 0) or 0))
    c['heloc_initial_rate_pct'] = _n(_v(data, 'HELOC', 'Setup', 'heloc_initial_rate_pct', '0.085'), 0.085)
    c['heloc_rate_drift_bps_yr'] = _n(_v(data, 'HELOC', 'Setup', 'heloc_rate_drift_bps_yr', '25'), 25.0)
    c['heloc_repayment_years'] = int(float(_n(_v(data, 'HELOC', 'Setup', 'heloc_repayment_years', '10'), 10) or 10))

    # S-Corp parameters
    c['scorp_salary']     = _n(_v(data,'Cashflow','S-Corp','reasonable_salary_annual','80000'), 80000)
    c['scorp_sehi_on_w2'] = _b(_v(data,'Cashflow','S-Corp','sehi_added_to_w2','TRUE'))
    c['scorp_state_rate'] = _n(_v(data,'Cashflow','S-Corp','state_corporate_surcharge_rate','0.015'), 0.015)
    c['scorp_qbi_phaseout']= _b(_v(data,'Cashflow','S-Corp','qbi_phaseout_applies','FALSE'))
    # Salary for retire-later extension years (default = base scorp_salary)
    c['scen_retire_salary'] = _n(_v(data,'Scenarios','Retire Later',
                                     'salary_override', str(int(c['scorp_salary']))),
                                  c['scorp_salary'])

    # Holdings lots (for tax basis calculation)
    c['client_holdings'] = {}  # {account: {symbol: {avg_price, last_purchase_date}}}
    for sub, vals in data.get('Client Holdings',{}).items():
        parts = sub.rsplit('_', 1)
        if len(parts) == 2:
            acct, sym = parts[0], parts[1]
            if acct not in c['client_holdings']:
                c['client_holdings'][acct] = {}
            c['client_holdings'][acct][sym] = {
                'avg_price':        _n(vals.get('avg_purchase_price','0'), 0),
                'last_purchase':    vals.get('last_purchase_date',''),
                'shares':           _n(vals.get('shares','0'), 0),
            }

    # ── Load lot-level holdings from client_holdings.csv ───────────────────────
    # Separate file: account, symbol, purchase_date, shares, purchase_price, lot_type, note
    # Builds {account: {symbol: [TaxLot, ...]}} for the LotEngine.
    import csv as _csv
    from .core import TaxLot, LotEngine  # consolidated from events
    lots_by_account = {}   # {acct: {sym: [TaxLot, ...]}}
    lots_reconcile = {}    # {(acct, sym): total_lot_shares} for QC reconciliation
    lots_file = None
    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Workspace-aware search order: explicit env path/input dir, workspace input, shared input, hosted fallbacks.
    for _lp_path in candidate_input_files('client_holdings.csv', active_workspace_id(), root=__import__('pathlib').Path(_project_root)):
        _lp = str(_lp_path)
        if os.path.exists(_lp):
            lots_file = _lp
            break
    if lots_file:
        with open(lots_file, newline='', encoding='utf-8') as lf:
            reader = _csv.DictReader(lf)
            for row in reader:
                acct = (row.get('account','') or '').strip()
                sym  = (row.get('symbol','') or '').strip()
                if not acct or not sym:
                    continue
                shares = float((row.get('shares','0') or '0').replace(',',''))
                price  = float((row.get('purchase_price','0') or '0').replace('$','').replace(',',''))
                pdate  = (row.get('purchase_date','') or '').strip()
                ltype  = (row.get('lot_type','buy') or 'buy').strip().lower()
                if shares <= 0:
                    continue
                cost_basis = shares * price
                lot = TaxLot(sym, shares, cost_basis, pdate)
                if acct not in lots_by_account:
                    lots_by_account[acct] = {}
                if sym not in lots_by_account[acct]:
                    lots_by_account[acct][sym] = []
                lots_by_account[acct][sym].append(lot)
                key = (acct, sym)
                lots_reconcile[key] = lots_reconcile.get(key, 0) + shares
    c['lots_by_account'] = lots_by_account

    # ── Load additional liabilities from client_liabilities.csv ───────────────
    # Flat table: liability_id, type, label, balance, interest_rate,
    # monthly_payment, start_year, payoff_year, notes. Each row becomes a dict
    # the deterministic engine amortizes into yearly cash flow + net worth.
    # type in (auto | heloc | student_loan | other). A zero/absent file yields
    # an empty list so a liability-free plan behaves exactly as before.
    liabilities = []
    liab_file = None
    for _li_path in candidate_input_files('client_liabilities.csv', active_workspace_id(), root=__import__('pathlib').Path(_project_root)):
        _li = str(_li_path)
        if os.path.exists(_li):
            liab_file = _li
            break
    if liab_file:
        try:
            with open(liab_file, newline='', encoding='utf-8-sig') as lf:
                for row in _csv.DictReader(lf):
                    def _clean_num(raw):
                        return float((str(raw or '0')).replace('$', '').replace(',', '').replace('%', '').strip() or 0.0)
                    ltype = (row.get('type', '') or 'other').strip().lower()
                    balance = _clean_num(row.get('balance', '0'))
                    if balance <= 0:
                        continue
                    rate = _clean_num(row.get('interest_rate', '0'))
                    # Accept either a fraction (0.06) or a percent (6) for the rate.
                    if rate > 1.0:
                        rate = rate / 100.0
                    def _clean_year(raw):
                        try:
                            return int(float(str(raw or '0').replace(',', '').strip() or 0))
                        except Exception:
                            return 0
                    liabilities.append({
                        'liability_id': (row.get('liability_id', '') or '').strip(),
                        'type': ltype,
                        'label': (row.get('label', '') or '').strip(),
                        'balance': balance,
                        'interest_rate': rate,
                        'monthly_payment': _clean_num(row.get('monthly_payment', '0')),
                        'start_year': _clean_year(row.get('start_year', '0')),
                        'payoff_year': _clean_year(row.get('payoff_year', '0')),
                        'notes': (row.get('notes', '') or '').strip(),
                    })
        except Exception:
            liabilities = []
    c['liabilities'] = liabilities

    # Keep an immutable copy for the workbook rebalancing tax optimizer.
    # Projection withdrawals can mutate c['lots_by_account'] through LotEngine,
    # but recommended trades must be scored against the starting tax lots.
    c['rebalance_lots_by_account'] = _copy.deepcopy(lots_by_account)
    c['lots_reconcile']  = lots_reconcile

    # ── Pricing fallback from holdings cost basis ─────────────────────────────
    # Live market pricing can fail offline or due to rate limits. Before computing
    # account balances, seed the centralized market-data provider with weighted
    # average purchase prices from client_holdings.csv. This prevents failed live
    # quotes from valuing securities at $0 and collapsing retirement balances.
    fallback_prices = {}
    fallback_qty = {}
    for acct, syms in lots_by_account.items():
        for sym, lots in syms.items():
            sym_clean = (sym or '').strip().upper()
            if not sym_clean or sym_clean == 'CASH':
                continue
            qty = sum(getattr(lot, 'qty', 0.0) for lot in lots)
            basis = sum(getattr(lot, 'cost_basis', 0.0) for lot in lots)
            if qty > 0 and basis > 0:
                fallback_prices[sym_clean] = fallback_prices.get(sym_clean, 0.0) + basis
                fallback_qty[sym_clean] = fallback_qty.get(sym_clean, 0.0) + qty
    if fallback_prices:
        weighted_fallback = {
            sym: fallback_prices[sym] / fallback_qty[sym]
            for sym in fallback_prices
            if fallback_qty.get(sym, 0.0) > 0
        }
        set_fallback_prices(weighted_fallback)

    # ── Derive ALL positions from client_holdings.csv ─────────────────────────
    # The holdings file is the single source of truth for every position
    # (securities AND cash). If no holdings file was found, fall back to
    # whatever Positions rows exist in client_data.csv.
    if lots_reconcile:
        positions = {}   # {account: {symbol: total_shares}}
        for (acct, sym), total_shares in lots_reconcile.items():
            if acct not in positions:
                positions[acct] = {}
            positions[acct][sym] = positions[acct].get(sym, 0) + total_shares
        c['positions'] = positions

    # Compute account balances (from whichever source populated positions)
    balances = {}
    for acct, holdings in c['positions'].items():
        total = 0
        for sym, shares in holdings.items():
            price = fetch_price(sym, url_template)
            total += shares * price
        balances[acct] = total
    c['balances'] = balances
    c['cash_other'] = sum(v for k, v in balances.items() if k.endswith('_Checking'))

    # ── Account Registry (generic calculator) ────────────────────────────────
    # Build a data-driven registry from whatever accounts exist in the balances.
    # The projection engine uses this instead of hardcoded owner-specific names.
    c['account_registry'] = _ar.build_registry_from_balances(balances, c['members'])
    c['all_acct_ids']     = _ar.all_ids(c['account_registry'])
    c['pre_tax_ids']      = _ar.ids_by_tax(c['account_registry'], 'pre_tax')
    c['roth_ids']         = _ar.ids_by_tax(c['account_registry'], 'roth')
    c['taxable_ids']      = _ar.taxable_ids(c['account_registry'])
    c['hsa_ids']          = _ar.hsa_ids(c['account_registry'])
    c['cash_ids']         = _ar.ids_by_tax(c['account_registry'], 'cash')
    c['invest_ids']       = _ar.all_investment_ids(c['account_registry'])

    # Taxable portfolio income assumptions.  Taxable-account ETFs/funds distribute
    # dividends/interest that must enter AGI, SS provisional income, IRMAA MAGI,
    # NIIT, and cash-flow funding.  Use security_master.csv to identify asset
    # class, with conservative defaults when a symbol is unmapped.
    def _load_security_classes():
        out = {}
        _root = __import__('pathlib').Path(_project_root)
        for _sm in candidate_input_files('security_master.csv', active_workspace_id(), root=_root):
            if os.path.exists(_sm):
                try:
                    with open(_sm, newline='', encoding='utf-8-sig') as _sf:
                        for _r in _csv.DictReader(_sf):
                            _sym = (_r.get('symbol') or '').strip().upper()
                            if _sym:
                                out[_sym] = (_r.get('asset_class') or '').strip().upper()
                    break
                except Exception:
                    pass
        if not out:
            _fallback = _root / 'reference_data' / 'security_master.csv'
            if _fallback.exists():
                try:
                    with open(_fallback, newline='', encoding='utf-8-sig') as _sf:
                        for _r in _csv.DictReader(_sf):
                            _sym = (_r.get('symbol') or '').strip().upper()
                            if _sym:
                                out[_sym] = (_r.get('asset_class') or '').strip().upper()
                except Exception:
                    pass
        return out

    _security_classes = _load_security_classes()
    _class_income_defaults = {
        'US EQUITY': (0.015, 0.90, 0.0),
        'US LARGE CAP': (0.015, 0.90, 0.0),
        'US MID CAP': (0.015, 0.90, 0.0),
        'US SMALL CAP': (0.015, 0.90, 0.0),
        'INTERNATIONAL': (0.030, 0.75, 0.0),
        'INTERNATIONAL EQUITY': (0.030, 0.75, 0.0),
        'EMERGING MARKETS': (0.025, 0.70, 0.0),
        'COMMODITIES': (0.030, 0.00, 0.0),
        'BONDS': (0.040, 0.00, 0.0),
        'SHORT-TERM BONDS': (0.035, 0.00, 0.0),
        'TIPS': (0.030, 0.00, 0.0),
        'MUNICIPAL BONDS': (0.000, 0.00, 0.030),
        'MANAGED FUTURES': (0.020, 0.00, 0.0),
        'PRIVATE CREDIT': (0.060, 0.00, 0.0),
        'REITS': (0.035, 0.00, 0.0),
        'CASH': (0.020, 0.00, 0.0),
    }
    _cm_income = _load_capital_market_income_assumptions()
    _preset = str((c.get('capital_market_config') or {}).get('preset') or 'BASELINE').strip().upper()
    for (_p, _cls), _vals in _cm_income.items():
        if _p == _preset:
            _class_income_defaults[_cls.upper()] = _vals
    _symbol_income_defaults = {
        'ITOT': (0.014, 0.95, 0.0), 'VTI': (0.014, 0.95, 0.0), 'SPY': (0.013, 0.95, 0.0),
        'AVUV': (0.012, 0.90, 0.0), 'IXUS': (0.030, 0.75, 0.0), 'VXUS': (0.030, 0.75, 0.0),
        'PDBC': (0.030, 0.00, 0.0), 'BND': (0.040, 0.00, 0.0), 'AGG': (0.040, 0.00, 0.0),
        'CASH': (0.020, 0.00, 0.0), 'SGOV': (0.040, 0.00, 0.0), 'BIL': (0.040, 0.00, 0.0),
    }
    account_income = {}
    taxable_ids_set = set(c.get('taxable_ids', []))
    for _acct, _holdings in c.get('positions', {}).items():
        if _acct not in taxable_ids_set:
            continue
        _total_value = 0.0; _ord = 0.0; _qual = 0.0; _tax_exempt = 0.0
        for _sym, _shares in (_holdings or {}).items():
            _sym_u = str(_sym or '').strip().upper()
            try:
                _value = float(_shares or 0.0) * float(fetch_price(_sym_u, url_template) or 0.0)
            except Exception:
                _value = 0.0
            if _value <= 0:
                continue
            _total_value += _value
            _yield, _qfrac, _te_yield = _symbol_income_defaults.get(
                _sym_u, _class_income_defaults.get(_ap.canonical_asset_class(_security_classes.get(_sym_u, '')).upper(), _class_income_defaults.get(str(_security_classes.get(_sym_u, '')).upper(), (0.015, 0.50, 0.0)))
            )
            _taxable_yield = max(0.0, float(_yield or 0.0))
            _qfrac = max(0.0, min(1.0, float(_qfrac or 0.0)))
            _te_yield = max(0.0, float(_te_yield or 0.0))
            _qual += _value * _taxable_yield * _qfrac
            _ord += _value * _taxable_yield * (1.0 - _qfrac)
            _tax_exempt += _value * _te_yield
        if _total_value > 0:
            account_income[_acct] = {
                'ordinary_yield': _ord / _total_value,
                'qualified_yield': _qual / _total_value,
                'tax_exempt_yield': _tax_exempt / _total_value,
                'total_distribution_yield': (_ord + _qual + _tax_exempt) / _total_value,
            }
    c['account_taxable_income_assumptions'] = account_income
    c['portfolio_income_reduces_growth'] = True

    # Instantiate LotEngine with current prices
    lot_method = _v(data, 'Withdrawal Policy', '', 'lot_method', 'HIFO') or 'HIFO'
    c['lot_engine'] = LotEngine(
        lots_by_account, PRICE_CACHE,
        fallback_gain_fraction=c.get('trust_gain_fraction', 0.50),
        method=lot_method.upper()
    )

    _apply_allocation_projection_assumptions(c)
    return ensure_engine_config(c, source='sectioned')


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
                                        'retirement_year': datetime.date.today().year + 4, 'mortality_age': 90}])
    m1 = members_in[0]
    c['h_name']     = m1.get('name', 'Member 1')
    c['h_nick']     = str(m1.get('nickname') or '').strip() or str(c['h_name']).strip().split(' ')[0]
    c['h_dob_yr']   = int(m1.get('dob_year', 1965))
    c['h_ret_yr']   = int(m1.get('retirement_year', datetime.date.today().year + 4))
    c['h_mort_age'] = int(m1.get('mortality_age', 90))
    c['h_death_yr'] = c['h_dob_yr'] + c['h_mort_age']

    if len(members_in) > 1:
        m2 = members_in[1]
        c['w_name']     = m2.get('name', 'Member 2')
        c['w_nick']     = str(m2.get('nickname') or '').strip() or str(c['w_name']).strip().split(' ')[0]
        c['w_dob_yr']   = int(m2.get('dob_year', 1965))
        c['w_ret_yr']   = int(m2.get('retirement_year', datetime.date.today().year + 4))
        c['w_mort_age'] = int(m2.get('mortality_age', 92))
        c['w_death_yr'] = c['w_dob_yr'] + c['w_mort_age']
    else:
        c['w_name'] = ''
        c['w_nick'] = ''
        c['w_dob_yr'] = c['h_dob_yr']
        c['w_ret_yr'] = c['h_ret_yr']
        c['w_mort_age'] = 0
        c['w_death_yr'] = c['h_dob_yr']

    c['members'] = [{'name': c['h_name'], 'role': 'member_1',
                     'dob_yr': c['h_dob_yr'], 'retire_yr': c['h_ret_yr'],
                     'mortality_age': c['h_mort_age'], 'death_yr': c['h_death_yr']}]
    if c['w_name']:
        c['members'].append({'name': c['w_name'], 'role': 'member_2',
                             'dob_yr': c['w_dob_yr'], 'retire_yr': c['w_ret_yr'],
                             'mortality_age': c['w_mort_age'], 'death_yr': c['w_death_yr']})
    c['household_size'] = len(c['members'])

    # ── Filing & State ────────────────────────────────────────────────────
    filing = plan.get('filing_status', 'MFJ' if c['household_size'] > 1 else 'Single')
    c['filing_status']  = filing if filing in _td.FILING_STATUSES else ('MFJ' if c['household_size'] > 1 else 'Single')
    c['survivor_filing'] = plan.get('survivor_filing_status', 'Single')
    c['state']          = plan.get('state', 'Illinois')
    c['trust_type']     = 'revocable living trust'

    # ── Timeline ──────────────────────────────────────────────────────────
    c['plan_start'] = plan.get('plan_start', datetime.date.today().year)
    c['plan_end']   = max(c['h_death_yr'], c.get('w_death_yr', c['h_death_yr']))

    # ── Economic assumptions ──────────────────────────────────────────────
    a = plan.get('assumptions', {})
    c['ret']             = a.get('return_rate', 0.074)
    c['inf']             = a.get('inflation', 0.025)
    c['brk_inf']         = a.get('bracket_inflation', 0.028)
    c['irmaa_inflator']  = a.get('irmaa_inflation', 0.02)
    c['irmaa_base'] = a.get('irmaa_base', 268000)
    c['ret_eq']          = a.get('equity_return', 0.10)
    c['ret_bond']        = a.get('bond_return', 0.04)
    c['mc_vol']          = a.get('mc_volatility', 0.15)
    c['mc_paths']        = int(a.get('mc_paths', 1000))
    c['ss_cola']         = a.get('ss_cola', 0.023)
    c['ss_taxable']      = a.get('ss_taxable_pct', 0.85)

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
    c['roth_irmaa_cap']     = True
    c['roth_fixed_amount']  = a.get('roth_fixed_amount', 50000)
    c['roth_optimize_terminal_weight'] = a.get('roth_optimize_terminal_weight', 1.0)
    c['roth_optimize_tax_weight'] = a.get('roth_optimize_lifetime_tax_weight', 0.25)
    c['roth_optimize_terminal_tax_rate'] = a.get('roth_optimize_terminal_pretax_tax_rate', 0.24)
    c['roth_brk']           = c['roth_target_rate']
    c['conv_window_offset'] = a.get('conv_window_offset', 0)
    c['cascade_order_list'] = a.get('cascade_order', ['IRA', 'Trust', 'Roth', 'Home'])
    c['cascade_warnings']   = []; c['cascade_order'] = {}
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
    c['rmd_start_age']     = a.get('rmd_start_age', 75)
    c['rollover_yr']       = a.get('rollover_year', c['plan_start'] + 5)
    c['salt_cap']          = a.get('salt_cap', 10000)
    c['payroll_wage_base'] = a.get('ss_wage_base', 184500)
    c['payroll_ee_rate']   = 0.0765
    c['ltcg_0_top']        = _td.LTCG_BRACKETS_BASE_YEAR.get(c['filing_status'], {}).get('zero_top', 96700)
    c['ltcg_15_top']       = _td.LTCG_BRACKETS_BASE_YEAR.get(c['filing_status'], {}).get('fifteen_top', 600050)
    c['niit_threshold']    = _td.NIIT_THRESHOLD.get(c['filing_status'], 250000)
    c['tax_constants_registry'] = _td.load_tax_constants()
    c['tax_provenance']    = dict(_td.TAX_YEAR_PROVENANCE)
    c['tax_table_currency_warnings'] = _td.tax_table_currency_warnings(max_lag_years=int(c.get('tax_table_currency_max_lag_years', 1) or 1))

    # ── Estate ────────────────────────────────────────────────────────────
    c['fed_exempt']    = plan.get('estate_federal_exemption', 30000000)
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
    c['ss_wage_base'] = a.get('ss_wage_base', 184500)
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
    return ensure_engine_config(c, source='flat_json')



# ===== END data_parser.py =====


# ===== BEGIN validation_engine.py =====

"""validation_engine.py — registry-aware validation for retirement projections.

Centralizes projection quality checks so workbook/API/reporting layers do not
need to embed validation rules.  The functions return simple tuples for
the existing QC sheet:

    (year, severity, code, message)

Severity is either FAIL or WARN.
"""


import math
from typing import Any, Dict, Iterable, List, Sequence, Tuple

ValidationFailure = Tuple[Any, str, str, str]


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except Exception:
        return True  # non-numeric values are ignored by numeric validation


def _account_ids(c: Dict[str, Any]) -> List[str]:
    ids = list(c.get('all_acct_ids') or [])
    if ids:
        return ids
    registry = c.get('account_registry') or []
    ids = [a.get('id') for a in registry if a.get('id')]
    if ids:
        return ids
    # No hardcoded account fallback: validation must follow the active registry.
    return []


def validate_projection(rows: Sequence[Dict[str, Any]], c: Dict[str, Any]) -> List[ValidationFailure]:
    """Validate projection rows using registry-aware checks.

    The checks intentionally avoid asserting a precise financial-planning answer;
    they assert accounting integrity and presentation sanity.
    """
    failures: List[ValidationFailure] = []
    acct_ids = _account_ids(c)
    plan_end = c.get('plan_end')

    for row in rows:
        yr = row.get('year', '?')

        # NaN/Inf detection across numeric row values.
        for key, val in row.items():
            if isinstance(val, (int, float)) and not _finite(val):
                failures.append((yr, 'FAIL', 'NON_FINITE', f'{key} is {val!r}'))

        # Registry-driven account non-negativity and roll-forward footing.
        opening_map = row.get('_account_opening', {}) or {}
        deposits_map = row.get('_account_deposits', {}) or {}
        transfers_in_map = row.get('_account_transfers_in', {}) or {}
        transfers_out_map = row.get('_account_transfers_out', {}) or {}
        conv_in_map = row.get('_account_conversions_in', {}) or {}
        conv_out_map = row.get('_account_conversions_out', {}) or {}
        withdrawals_map = row.get('_account_withdrawals', {}) or {}
        growth_map = row.get('_account_growth', {}) or {}
        for acct in acct_ids:
            bal = row.get(acct, 0)
            if isinstance(bal, (int, float)) and bal < -0.01:
                failures.append((yr, 'FAIL', 'ACCOUNT_NEGATIVE', f'{acct} = ${bal:,.0f}'))
            if opening_map:
                calc_bal = (float(opening_map.get(acct, 0) or 0) +
                            float(deposits_map.get(acct, 0) or 0) +
                            float(transfers_in_map.get(acct, 0) or 0) -
                            float(transfers_out_map.get(acct, 0) or 0) +
                            float(conv_in_map.get(acct, 0) or 0) -
                            float(conv_out_map.get(acct, 0) or 0) -
                            float(withdrawals_map.get(acct, 0) or 0) +
                            float(growth_map.get(acct, 0) or 0))
                delta = float(bal or 0) - calc_bal
                if abs(delta) > 10:
                    failures.append((yr, 'FAIL', 'ACCOUNT_RECON',
                                     f'{acct} roll-forward delta = ${delta:,.2f}'))

        home_eq = row.get('home_equity', row.get('home_eq_nw', 0))
        if isinstance(home_eq, (int, float)) and home_eq < -0.01:
            failures.append((yr, 'FAIL', 'HOME_EQ_NEGATIVE', f'home equity = ${home_eq:,.0f}'))

        agi = max(1.0, float(row.get('agi', 0) or 0))
        total_tax = float(row.get('total_tax', 0) or 0)
        if total_tax > agi * 0.55 + 10_000:
            failures.append((yr, 'WARN', 'TAX_HIGH', f'tax/AGI = {total_tax / agi:.0%}'))

        if float(row.get('spend_base_yr', 0) or 0) < 0:
            failures.append((yr, 'FAIL', 'SPEND_NEGATIVE', 'Negative base spending'))
        if plan_end is None or (isinstance(yr, int) and yr <= plan_end):
            if float(row.get('total_spend', 0) or 0) <= 0:
                failures.append((yr, 'WARN', 'SPEND_ZERO', 'Total spending is zero or missing'))

        recon_delta = abs(float(row.get('cash_recon_delta', 0) or 0))
        tolerance = max(100.0, float(row.get('cash_uses', 0) or 0) * float(c.get('qc_cash_tolerance_pct', 0.01)))
        if recon_delta > tolerance:
            failures.append((yr, 'WARN', 'CASH_RECON_DRIFT', f'cash sources - uses = ${row.get("cash_recon_delta", 0):,.0f}'))

        unfunded_gap = float(row.get('unfunded_gap', 0) or 0)
        if unfunded_gap > tolerance:
            failures.append((yr, 'FAIL', 'UNFUNDED_GAP', f'unfunded cash need = ${unfunded_gap:,.0f}'))

        alloc_sum = row.get('allocation_sum')
        if isinstance(alloc_sum, (int, float)) and abs(alloc_sum - 1.0) > 0.01:
            failures.append((yr, 'WARN', 'ALLOCATION_SUM', f'allocation sum = {alloc_sum:.2%}'))

    return failures


def summarize_validation(rows: Sequence[Dict[str, Any]], c: Dict[str, Any]) -> Dict[str, Any]:
    failures = validate_projection(rows, c)
    return {
        'failures': failures,
        'fail_count': sum(1 for _y, sev, _code, _msg in failures if sev == 'FAIL'),
        'warn_count': sum(1 for _y, sev, _code, _msg in failures if sev == 'WARN'),
        'years': [_y for _y, _sev, _code, _msg in failures],
        'first_fail': next(((yr, code, msg) for yr, sev, code, msg in failures if sev == 'FAIL'), None),
    }
