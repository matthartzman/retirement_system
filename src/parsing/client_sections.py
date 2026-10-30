"""client_sections.py -- helpers lifted out of ``parse_client`` (WI-034, ARC-005).

Mechanical extraction from src/data_io.py: the nested closures of
``parse_client`` and its contiguous sections now live here as module-level
functions with explicit parameters.  The bodies are the original statements,
moved verbatim; nothing about parse order or arithmetic changed.

Module-level helpers (``_v``, ``_n``, ``fetch_price`` ...) are imported inside
each function, at call time, from ``src.data_io``.  That keeps this module free
of an import cycle (``src.data_io`` imports it at load time) and means a test
that monkeypatches ``src.data_io.<name>`` still takes effect here, exactly as it
did when the code was inline.
"""
from __future__ import annotations


# Nicknames: short names used in every user-facing report/chart label.
# Fall back to the first word of the full name when not provided.
def nickname(raw, full_name):
    raw = str(raw or '').strip()
    if raw:
        return raw
    return str(full_name or '').strip().split(' ')[0] if str(full_name or '').strip() else ''


def ss_benefit_table(data, person):
    from ..data_io import _n, _v
    table = {}
    for age in range(62, 71):
        v = _v(data, 'Social Security', person, f'ss_benefit_age_{age}', None)
        if v not in (None, ''):
            table[age] = _n(v, 0.0)
    return table


def annuity_pv_rate(data):
    """Discount rate for annuity/pension PV in net worth; None (blank) = the portfolio return."""
    from ..data_io import _n, _v
    return _n(_v(data, 'Economic Assumptions', '', 'annuity_pv_discount_rate', ''), None)


def add_liquidity_rule(c, start_raw='', end_raw='', yrs_raw='0', account_raw='Taxable/Trust'):
    from ..data_io import _n, _y
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


def load_stream(data, c, name, annuitant='wife'):
    from ..data_io import _b, _date_parts, _n, _td, _v, _y
    s = {}
    _fp_raw = _v(data,'Income Streams',name,'first_payment', str(c['plan_start'] + 3))
    s['first_yr'] = _y(_fp_raw.split('/')[-1], c['plan_start'] + 3)
    # First-year cash-flow proration (annuity_cash_income() in core.py):
    # a contract whose first_payment is mid-year (e.g. 6/1/2026) should
    # only pay the remaining months of that calendar year, not a full 12
    # -- see _date_parts' month component. None (not just month 1) for a
    # legacy/year-only value on purpose: annuity_cash_income() treats a
    # missing month as "don't prorate," matching this function's
    # pre-existing behavior for data that never carried a real date.
    _fp_parts = _date_parts(_fp_raw)
    s['first_payment_month'] = _fp_parts[1] if _fp_parts else None
    s['base']     = _n(_v(data,'Income Streams',name,'base','0'), 0)
    s['div_rate'] = _n(_v(data,'Income Streams',name,'dividend_rate',str(c['ann_div'])), c['ann_div'])
    # add_pct = reinvested fraction (20% default); cash payout = 1 - add_pct
    s['add_pct']  = _n(_v(data,'Income Streams',name,'additional_income_pct',str(c['ann_add'])), c['ann_add'])
    # Gross monthly payment: the engine taxes this itself (FUNCTIONAL_SPEC §6).
    s['init_pmt'] = _n(_v(data,'Income Streams',name,'initial_guaranteed_income_payment','0'), 0)
    # Optional net deposit after withholding -- reference only, never fed to the
    # engine. Blank = no withholding (net = gross).
    _net = _n(_v(data,'Income Streams',name,'net_monthly_payment',''), None)
    s['net_monthly_payment'] = s['init_pmt'] if _net is None else _net
    s['monthly_withholding'] = s['init_pmt'] - s['net_monthly_payment']
    # Deferral years: contract years before income starts where dividends are 100% reinvested
    s['deferral_years']   = int(_n(_v(data,'Income Streams',name,'deferral_years','0'), 0))
    # Reserve model calibration (deferred income annuity): reserve_factor anchors the dividend base,
    # deferral_dampening scales deferral-period income growth.
    s['reserve_factor']   = _n(_v(data,'Income Streams',name,'reserve_factor','0.853'), 0.853)
    # Market type: qualified (IRA/401k) vs non-qualified (Personal) — affects state taxation
    s['qualified']        = _b(_v(data,'Income Streams',name,'qualified','TRUE'))
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



# #295: QLAC (Qualified Longevity Annuity Contract) -- a deferred-income
# annuity bought with pre-tax retirement dollars. Reuses load_stream()'s
# payment machinery (base=0/div_rate=0/add_pct=0 collapses it to a pure
# guaranteed payment starting at first_yr -- see annuity_cash_income() in
# core.py) plus QLAC-specific fields load_stream doesn't have: the
# purchase premium (what src/core.py's qlac_excluded_rmd_balance()
# subtracts from the RMD base) and the source account it was purchased
# from. Two fixed slots (one per member), matching the existing
# single/joint annuity and pension slot pattern above rather than the
# "Other Asset N" numbered-row pattern -- SECURE 2.0 permits only one
# QLAC-eligible aggregate premium limit per person, not a list.
def load_qlac(data, c, name, annuitant='wife'):
    from ..data_io import _b, _n, _v, _y
    s = load_stream(data, c, name, annuitant=annuitant)
    s['base'] = 0.0
    s['div_rate'] = 0.0
    s['add_pct'] = 0.0
    # CSV labels prefixed qlac_ where they'd otherwise collide with an
    # existing generic field-help entry keyed by label alone (frontend
    # FIELD_GUIDANCE_OVERRIDES has no section/subsection disambiguation)
    # -- "enabled" already means the ACA subsidy toggle and
    # "source_account" already means a Roth conversion's source account;
    # showing that text on a QLAC row would be actively misleading.
    s['enabled'] = _b(_v(data,'Income Streams',name,'qlac_enabled','FALSE'))
    s['premium'] = _n(_v(data,'Income Streams',name,'premium','0'), 0)
    s['source_account'] = str(_v(data,'Income Streams',name,'qlac_source_account','') or '').strip()
    # Year the premium is actually paid out of source_account -- distinct
    # from first_yr (income START year, i.e. first_payment above), since
    # the whole point of a QLAC is deferring income years past purchase.
    s['purchase_year'] = _y(_v(data,'Income Streams',name,'purchase_year', str(c['plan_start'])), c['plan_start'])
    # Return-of-premium death benefit: % of unpaid premium returned to
    # beneficiaries if the annuitant dies before recovering the full
    # premium in payments. 0 = no death benefit (higher payout rate).
    s['death_benefit_pct'] = max(0.0, min(1.0, _n(_v(data,'Income Streams',name,'death_benefit_pct','0'), 0)))
    return s


def load_security_classes():
    # Shipped reference data (reference.db), not per-workspace plan data: a
    # workspace redirect must not make symbol classification vanish.
    from ..stores.ref_getters.security_master import security_master_rows
    out = {}
    for _r in security_master_rows():
        _sym = (_r.get('symbol') or '').strip().upper()
        if _sym:
            out[_sym] = (_r.get('asset_class') or '').strip().upper()
    return out


def account_cma_return(_holdings, _security_classes, _broad_to_cma_class, _cm_returns, _preset, url_template, skip_live_pricing):
    from ..data_io import fetch_price
    _val = 0.0; _weighted = 0.0
    for _sym, _shares in (_holdings or {}).items():
        _sym_u = str(_sym or '').strip().upper()
        try:
            _price = float(fetch_price(_sym_u, url_template, skip_live=skip_live_pricing) or 0.0)
        except Exception:
            _price = 0.0
        _value = float(_shares or 0.0) * _price
        if _value <= 0:
            continue
        _broad = str(_security_classes.get(_sym_u, '')).strip().upper()
        _cls = _broad_to_cma_class.get(_broad)
        _class_ret = _cm_returns.get((_preset, _cls)) if _cls else None
        if _class_ret is None:
            continue
        _val += _value
        _weighted += _value * _class_ret
    return (_weighted / _val, _val) if _val > 0 else (None, 0.0)


def parse_household_and_pricing(data, c, _sv):
    """Household identity, dates of birth, retirement timing, residency schedule, pricing settings and filing status."""
    from ..data_io import (
        _last_earned_income_year_from_retirement_date,
        _n,
        _parse_member_dob,
        _retirement_year,
        _td,
        _v,
        _y,
        active_workspace_id,
        configure_api_keys,
        configure_holdings_pricing,
        nickname,
        os,
        require_residence_state_for_build,
        set_frozen_prices,
    )
    # Household
    c['h_name']    = _v(data,'Household','','member_1_name','Matthew')
    c['w_name']    = _v(data,'Household','','member_2_name','Patricia')
    # Nicknames: short names used in every user-facing report/chart label.
    # Fall back to the first word of the full name when not provided.
    c['h_nick'] = nickname(_v(data,'Household','','member_1_nickname',''), c['h_name'])
    c['w_nick'] = nickname(_v(data,'Household','','member_2_nickname',''), c['w_name'])
    # WI-401 (system review 2026-09-25-2, QA-001): DOBs go through the one
    # shared plan-date parser, and a missing/blank/unparseable/2-digit-year
    # DOB is a hard error instead of a silent literal fallback ('8/3/1962',
    # '5/30/1961') or a raw 2-digit birth year (which modeled the member as
    # dead in every plan year). Member 2's DOB is only required when there is
    # a member 2 (resolved below, once member_2_name is known).
    _h_dob_parts = _parse_member_dob(_v(data,'Household','','member_1_dob',''), 'member_1_dob')
    _w_dob_raw = _v(data,'Household','','member_2_dob','')
    try:
        _w_dob_parts = _parse_member_dob(_w_dob_raw, 'member_2_dob')
        _w_dob_error = None
    except ValueError as _exc:
        _w_dob_parts, _w_dob_error = None, _exc
    c['h_dob_yr'] = _h_dob_parts[0]
    c['w_dob_yr'] = _w_dob_parts[0] if _w_dob_parts else c['h_dob_yr']
    # Birth month, from the same parsed member_*_dob value. Used only to
    # prorate the Medicare/pre-65 bridge premium switch in the calendar year
    # someone turns 65 (Medicare begins the 1st of the birth month) -- see
    # deterministic_engine._medicare_month_fraction.
    c['h_dob_month'] = _h_dob_parts[1]
    c['w_dob_month'] = _w_dob_parts[1] if _w_dob_parts else c['h_dob_month']
    _h_ret_raw = _v(data,'Household','','member_1_retirement_date','1/1/2027')
    _w_ret_raw = _v(data,'Household','','member_2_retirement_date','2/28/2023')
    c['h_ret_yr']  = _retirement_year(_h_ret_raw, 2027)
    c['w_ret_yr']  = _retirement_year(_w_ret_raw, 2023)
    c['h_earned_last_year'] = _last_earned_income_year_from_retirement_date(_h_ret_raw, c['h_ret_yr'])
    c['h_mort_age']= _n(_v(data,'Household','','member_1_mortality_age','92'), 92)
    c['w_mort_age']= _n(_v(data,'Household','','member_2_mortality_age','95'), 95)
    c['h_death_yr']= int(c['h_dob_yr'] + c['h_mort_age'])
    c['w_death_yr']= int(c['w_dob_yr'] + c['w_mort_age'])
    c['state']     = _v(data,'Household','','residence_state','')
    require_residence_state_for_build(c['state'])
    # #302: an optional residency SCHEDULE for households that change state
    # residency mid-plan (state, start_year, end_year rows; the last row is
    # open-ended). Purely additive -- when empty, every consumer keeps using
    # the single c['state'] field above unchanged. Rows live under numbered
    # 'State Residency Schedule'/'period_N' subsections (see
    # src/server_services/strategy_asset_service.py's residency_schedule_payload /
    # save_residency_schedule_payload, the read/write pair the UI's add/delete-row
    # editor round-trips through). state_for_year() in deterministic_engine.py
    # is the resolver every state-tax call site uses instead of the static
    # field, so this is where "taxes actually change" lives.
    c['residency_schedule'] = []
    for _sub, _vals in (data.get('State Residency Schedule') or {}).items():
        if not str(_sub or '').strip().lower().startswith('period_'):
            continue
        _rstate = str(_vals.get('state', '') or '').strip()
        if not _rstate:
            continue
        _rstart = _y(_vals.get('start_year', ''), 0)
        if not _rstart:
            continue
        _rend = _y(_vals.get('end_year', ''), 0)
        c['residency_schedule'].append({
            'state': _rstate,
            'start_year': _rstart,
            'end_year': _rend if _rend else 9999,
        })
    c['residency_schedule'].sort(key=lambda p: p['start_year'])

    # Market pricing settings are runtime settings (app.db, src/system_config.py).
    configure_api_keys(
        fmp_api_key=_sv('Market Pricing', 'API', 'fmp_api_key', ''),
        alpha_vantage_api_key=_sv('Market Pricing', 'API', 'alpha_vantage_api_key', ''),
    )
    # Test/CI determinism hook: when RETIREMENT_SYSTEM_FORCE_PRICING_MODE is set
    # (tests/conftest.py pins it to OFFLINE), holdings are priced only from the
    # committed cache snapshot / cost basis — never live market data — so
    # golden-master projections are reproducible in CI. Scoped to parse_client
    # so the generic market_data.configure_holdings_pricing() stays pure for the
    # unit tests that assert its mode-handling behavior directly.
    _forced_pricing_mode = os.getenv('RETIREMENT_SYSTEM_FORCE_PRICING_MODE', '').strip()
    configure_holdings_pricing(
        mode=_forced_pricing_mode or _sv('Market Pricing', 'Holdings', 'pricing_mode', 'CACHE'),
        cache_hours=_sv('Market Pricing', 'Holdings', 'cache_hours', '24'),
    )
    # A user-controlled pricing freeze overrides live/cache mode for builds so
    # advisor report packages can be reproduced after market prices change.
    try:
        from ..portfolio_analytics import pricing_freeze_status
        freeze = pricing_freeze_status(workspace_id=active_workspace_id(), include_prices=True)
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
    # Survivor spending factor: the share of joint core spending and recurring
    # extras a one-person household still spends. Housing is excluded (the
    # survivor keeps the same home) and so are wellness/LTC premiums, which are
    # already modelled per person and would otherwise be reduced twice.
    c['survivor_spend_factor'] = min(1.0, max(0.0, _n(
        _v(data,'Household','','survivor_spend_factor','0.65'), 0.65)))
    return _w_dob_error


def parse_members_and_economics(data, c, _w_dob_error):
    """Members list, economic assumptions, Social Security, 72(t) exceptions and healthcare inputs."""
    from ..data_io import (
        TAX_BASE_YEAR,
        _apply_tax_assumptions,
        _b,
        _n,
        _platform_runtime,
        _ss_claim_from_date_or_age,
        _v,
        ss_benefit_table,
    )
    # ── Members Abstraction (9.2) ─────────────────────────────────────────────
    # Build a members list from the Household data. Supports 1 or 2 adult
    # members. If wife_name is blank/absent, it's a single-member household.
    # The members list is the generalized interface used by the model.
    _m1 = {
        'name':          c['h_name'],
        'nickname':      c['h_nick'],
        'role':          'member_1',
        'dob_yr':        c['h_dob_yr'],
        'dob_month':     c['h_dob_month'],
        'retire_yr':     c['h_ret_yr'],
        'mortality_age': c['h_mort_age'],
        'death_yr':      c['h_death_yr'],
    }
    _has_member_2 = bool(c['w_name'] and c['w_name'].strip())
    if _has_member_2:
        if _w_dob_error is not None:
            raise _w_dob_error
        _m2 = {
            'name':          c['w_name'],
            'nickname':      c['w_nick'],
            'role':          'member_2',
            'dob_yr':        c['w_dob_yr'],
            'dob_month':     c['w_dob_month'],
            'retire_yr':     c['w_ret_yr'],
            'mortality_age': c['w_mort_age'],
            'death_yr':      c['w_death_yr'],
        }
        c['members'] = [_m1, _m2]
    else:
        # Single-member household
        c['members'] = [_m1]
        c['w_dob_yr']   = c['h_dob_yr']   # zero-impact defaults
        c['w_dob_month']= c['h_dob_month']
        c['w_ret_yr']   = c['h_ret_yr']
        c['w_mort_age'] = 0
        c['w_death_yr'] = c['h_dob_yr']   # already dead → engine sees no spouse
        if c['filing_status'] == 'MFJ':
            c['filing_status'] = 'Single'  # can't be MFJ with one member
    c['household_size'] = len(c['members'])

    c['plan_start'] = _platform_runtime.today().year
    c['plan_end']   = max(c['h_death_yr'], c['w_death_yr'])
    c['first_death_yr'] = min(c['h_death_yr'], c['w_death_yr'])

    # Economic Assumptions
    c['inf']       = _n(_v(data,'Economic Assumptions','','inflation_general','0.025'), 0.025)
    c['ss_cola']   = _n(_v(data,'Economic Assumptions','','social_security_cola','0.02'), 0.02)
    c['med_inf']   = _n(_v(data,'Economic Assumptions','','medicare_part_b_inflation','0.055'), 0.055)
    c['partd_inf'] = _n(_v(data,'Economic Assumptions','','medicare_part_d_inflation','0.0125'), 0.0125)
    c['ret']       = _n(_v(data,'Economic Assumptions','','portfolio_nominal_return','0.06'), 0.06)
    # Tax assumptions resolve through one place (Auto model value vs. plan
    # override); see src/tax_assumptions.py. Blank/absent fields mean Auto.
    _apply_tax_assumptions(c, {
        'fed_tax_bracket_inflator': _v(data,'Economic Assumptions','','fed_tax_bracket_inflator',''),
        'state_income_tax_rate': _v(data,'Economic Assumptions','','state_income_tax_rate',''),
    }, {
        'tax_law_scenario': _v(data,'Economic Assumptions','','tax_law_scenario',''),
        'higher_rates_start_year': _v(data,'Economic Assumptions','','higher_rates_start_year',''),
    })
    # Social Security solvency / funding haircut. This explicit assumption reduces
    # gross Social Security benefits from the configured year onward when the
    # user wants to model trust-fund underfunding risk.
    c['ss_funding_discount_year'] = int(_n(_v(data,'Social Security','Funding Discount','ss_funding_discount_year','2032'), 2032))
    c['ss_funding_discount_pct'] = max(0.0, min(1.0, _n(_v(data,'Social Security','Funding Discount','ss_funding_discount_pct','22%'), 0.22)))
    c['roth_brk']  = _n(_v(data,'Economic Assumptions','',f'roth_conversion_target_bracket_{TAX_BASE_YEAR}','0.22'), 0.22)
    c['ann_div']   = _n(_v(data,'Economic Assumptions','','annuity_default_dividend_rate','0.0575'), 0.0575)
    c['ann_add']   = _n(_v(data,'Economic Assumptions','','annuity_default_additional_income_pct','0.2'), 0.2)
    c['ann_pv_rate'] = annuity_pv_rate(data)

    # Social Security.  Users enter a per-spouse claim age plus the actual
    # SSA-quoted monthly benefit for each claim age 62-70 (facts from the SSA
    # statement/estimator, not estimated) - see ss_benefit_age_62..70 below.
    # "Monthly at Claim Age" is derived by looking up the table entry for the
    # current claim age, so it always reflects the real government figure for
    # whatever age is selected instead of being back-solved from a single
    # reference amount.
    c['w_ss_benefit_table'] = ss_benefit_table(data, 'Member 2')
    c['h_ss_benefit_table'] = ss_benefit_table(data, 'Member 1')
    c['w_ss_claim_age'], c['w_ss_claim_year'], c['w_ss_claim_month'], c['w_ss_claim_age_precise'] = _ss_claim_from_date_or_age(
        data, 'Member 2', c['w_dob_yr'], c['w_dob_month'],
        _v(data,'Model Constants','Retirement','ss_claim_age','70'))
    c['h_ss_claim_age'], c['h_ss_claim_year'], c['h_ss_claim_month'], c['h_ss_claim_age_precise'] = _ss_claim_from_date_or_age(
        data, 'Member 1', c['h_dob_yr'], c['h_dob_month'],
        _v(data,'Model Constants','Retirement','ss_claim_age','70'))
    # Full Retirement Age override, in years (e.g. 66.67). Left at 0, the
    # engine auto-derives FRA from date of birth via the SSA birth-year table.
    c['w_fra_age'] = _n(_v(data,'Social Security','Member 2','fra_age','0'), 0) or None
    c['h_fra_age'] = _n(_v(data,'Social Security','Member 1','fra_age','0'), 0) or None
    # WI-039 / FIN-004: per-owner 72(t) exception inputs (blank / 0 = none).
    c['early_dist_exceptions'] = {
        idx: {
            'separation_year': int(_n(_v(data, 'Withdrawal Policy', f'Early Distributions Member {idx + 1}', 'separation_year', '0'), 0) or 0),
            'disability_year': int(_n(_v(data, 'Withdrawal Policy', f'Early Distributions Member {idx + 1}', 'disability_start_year', '0'), 0) or 0),
            'sepp_year': int(_n(_v(data, 'Withdrawal Policy', f'Early Distributions Member {idx + 1}', 'sepp_start_year', '0'), 0) or 0),
            'sepp_amount': float(_n(_v(data, 'Withdrawal Policy', f'Early Distributions Member {idx + 1}', 'sepp_annual_amount', '0'), 0) or 0.0),
        } for idx in (0, 1)
    }
    c['w_ss_claim_monthly'] = c['w_ss_benefit_table'].get(max(62, min(70, c['w_ss_claim_age'])), 0.0)
    c['h_ss_claim_monthly'] = c['h_ss_benefit_table'].get(max(62, min(70, c['h_ss_claim_age'])), 0.0)
    c['w_ss70']    = c['w_ss_benefit_table'].get(70, c['w_ss_claim_monthly'])
    c['h_ss70']    = c['h_ss_benefit_table'].get(70, c['h_ss_claim_monthly'])
    c['w_ss_pia']  = _n(_v(data,'Social Security','Member 2','monthly_pia_at_fra_today_dollars','0'), 0) or c['w_ss_benefit_table'].get(67, c['w_ss_claim_monthly'])
    c['h_ss_pia']  = _n(_v(data,'Social Security','Member 1','monthly_pia_at_fra_today_dollars','0'), 0) or c['h_ss_benefit_table'].get(67, c['h_ss_claim_monthly'])
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
    # WI-307 / FIN-007: a blank field takes the dated
    # aca_enhanced_subsidies_through_year row in tax_law_v10.json (an
    # UNVERIFIED assumption -- see that row's source); an explicit value wins.
    from ..tax_law import aca_enhanced_subsidies_through_year_default as _aca_thru_default
    _aca_thru_raw = _n(_v(data,'Wellness','ACA Premium Tax Credit','enhanced_subsidies_through_year',''), None)
    c['aca_enhanced_subsidies_through_year'] = int(_aca_thru_raw) if _aca_thru_raw else _aca_thru_default()


def parse_cashflow_and_retirement(data, c):
    """Earned income, cash-flow inputs, RMD start ages, QCDs and the mortgage amortization schedule."""
    from ..data_io import _b, _n, _v, _y, statutory_rmd_start_age
    # Cashflow / income
    c['earned']     = _n(_v(data,'Cashflow','Earned Income','annual_earned_income','290000'), 290000)
    c['earn_start'] = _y(_v(data,'Cashflow','Earned Income','earned_income_start_year', str(c['plan_start'])), c['plan_start'])
    # Earned income runs from the Work Income start year through the retirement
    # year from Retirement Timing. There is intentionally no separate earned-
    # income end-year input or legacy fallback.
    c['earn_end']   = c.get('h_earned_last_year', c['h_ret_yr'])
    c['earn_inc']   = _n(_v(data,'Cashflow','Earned Income','earned_income_annual_increase','0.03'), 0.03)
    c['entity']     = _v(data,'Cashflow','Earned Income','entity_type','sole_prop')
    c['ytd_remainder_earned_income_override'] = _n(_v(data,'Cashflow','Earned Income','ytd_remainder_earned_income_override',''), None)
    c['biz_exp']    = _n(_v(data,'Cashflow','Self-Employment','business_expenses_annual','15000'), 15000)
    c['home_off']   = _n(_v(data,'Cashflow','Self-Employment','home_office_expenses_annual','4000'), 4000)
    # SEHI defaults to a derived estimate from Healthcare premiums (Pre-65
    # Healthcare Premium before age 65, then Medicare Part B/D/G once Medicare
    # age is reached). An explicit health_insurance_premiums_annual entry
    # overrides that estimate with the household's actual known premium --
    # previously this field was read from the CSV but never consulted anywhere.
    c['sehi_user_override'] = _n(_v(data,'Cashflow','Self-Employment','health_insurance_premiums_annual',''), None)
    c['sehi']       = 0.0
    c['sehi_derived_from_wellness'] = True
    c['qbi_elig']   = _b(_v(data,'Cashflow','Self-Employment','qbi_eligible','TRUE'))

    c['k401_mo']   = _n(_v(data,'Cashflow','Retirement Contributions','monthly_401k_contribution','2000'), 2000)
    c['k401_lim']  = _n(_v(data,'Cashflow','Retirement Contributions','annual_401k_limit_base_year','32500'), 32500)
    c['k401_limit_indexed'] = _b(_v(data,'Cashflow','Retirement Contributions','index_401k_limit','TRUE'))

    # Default RMD start age is derived from each member's date of birth per the
    # SECURE 2.0 age ramp (see statutory_rmd_start_age). The per-member CSV
    # fields remain a user override (an explicitly-set value is honored as-is),
    # but if it disagrees with the statutory default for that member's birth
    # year, a non-blocking advisory warning is recorded (see
    # 'rmd_start_age_warnings' / Sheet 26). Item 195: the household-level
    # shared 'rmd_start_age' fallback field was removed (redundant with these
    # per-member fields, and its own value never differed from the statutory
    # default in practice) - c['rmd_start_age'] below is now purely derived,
    # anchored to member 1, for legacy callers that don't distinguish members.
    _h_rmd_statutory = statutory_rmd_start_age(c['h_dob_yr'])
    _w_rmd_statutory = statutory_rmd_start_age(c['w_dob_yr'])
    _h_rmd_raw = _v(data,'Model Constants','Retirement','member_1_rmd_start_age','')
    _w_rmd_raw = _v(data,'Model Constants','Retirement','member_2_rmd_start_age','')
    c['h_rmd_start_age'] = int(_n(_h_rmd_raw, _h_rmd_statutory)) if str(_h_rmd_raw or '').strip() else _h_rmd_statutory
    c['w_rmd_start_age'] = int(_n(_w_rmd_raw, _w_rmd_statutory)) if str(_w_rmd_raw or '').strip() else _w_rmd_statutory
    c['rmd_start_age_warnings'] = c.get('rmd_start_age_warnings') or []
    if c['h_rmd_start_age'] != _h_rmd_statutory:
        c['rmd_start_age_warnings'].append({
            'code': 'RMD_START_AGE_OVERRIDE_DISAGREES_WITH_STATUTORY',
            'severity': 'WARN',
            'message': (f"{c.get('h_nick') or c.get('h_name') or 'Member 1'}'s RMD start age "
                        f"is set to {c['h_rmd_start_age']}, but the statutory default for a "
                        f"{c['h_dob_yr']} birth year is {_h_rmd_statutory} (SECURE 2.0)."),
            'action': 'Confirm the override is intentional; otherwise clear it to use the statutory default.',
        })
    if c['w_rmd_start_age'] != _w_rmd_statutory:
        c['rmd_start_age_warnings'].append({
            'code': 'RMD_START_AGE_OVERRIDE_DISAGREES_WITH_STATUTORY',
            'severity': 'WARN',
            'message': (f"{c.get('w_nick') or c.get('w_name') or 'Member 2'}'s RMD start age "
                        f"is set to {c['w_rmd_start_age']}, but the statutory default for a "
                        f"{c['w_dob_yr']} birth year is {_w_rmd_statutory} (SECURE 2.0)."),
            'action': 'Confirm the override is intentional; otherwise clear it to use the statutory default.',
        })
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
    # Item 4.1 (P3): Qualified Charitable Distributions. Each member's own IRA
    # can fund QCDs once they're age 70 1/2-eligible; blank start/end years
    # fall back to that member's own eligibility year / plan_end in the engine.
    c['qcd_enabled'] = _b(_v(data,'Cashflow','Charitable Giving','qcd_enabled','FALSE') or 'FALSE')
    c['h_qcd_annual_amount'] = _n(_v(data,'Cashflow','Charitable Giving','h_qcd_annual_amount','0'), 0)
    c['w_qcd_annual_amount'] = _n(_v(data,'Cashflow','Charitable Giving','w_qcd_annual_amount','0'), 0)
    c['h_qcd_start_year'] = _n(_v(data,'Cashflow','Charitable Giving','h_qcd_start_year',''), None)
    c['h_qcd_end_year']   = _n(_v(data,'Cashflow','Charitable Giving','h_qcd_end_year',''), None)
    c['w_qcd_start_year'] = _n(_v(data,'Cashflow','Charitable Giving','w_qcd_start_year',''), None)
    c['w_qcd_end_year']   = _n(_v(data,'Cashflow','Charitable Giving','w_qcd_end_year',''), None)
    c['ytd_remainder_spending_override'] = _n(_v(data,'Cashflow','Spending','ytd_remainder_spending_override',''), None)
    c['ytd_blend_enabled'] = _b(_v(data,'Cashflow','Spending','ytd_blend_enabled','TRUE') or 'TRUE')
    c['travel_end_year'] = _y(_v(data,'Cashflow','Spending','travel_end_year',''), 0)

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
    # Large Discretionary is one-time only (#336, src/large_discretionary.py):
    # the unified budget resolver below turns every LD budget row into dated
    # lumps (legacy ranged rows are expanded one row per year, with import
    # notices in c['ld_import_notices']). The legacy Cashflow rows under
    # "Large Discretionary Expenses" (extra_N_*) are not an engine input.
    # Home Improvement items route to housing costs.
    c['lump'] = {}
    c['home_improvement_lump'] = {}


def parse_spending_and_home_sale(data, c):
    """Large-discretionary and spending-budget rows, other assets and the home-sale parameters."""
    from ..data_io import TAX_BASE_YEAR, _insurance_policy_premium_sum, _n, _v, _y
    c['recurring_extras'] = []
    c['ld_import_notices'] = []
    # #335 Spending Adjustments (Cashflow / Spending Adjustments adj_N_* rows),
    # read before the unified budget resolver so it can apply them.
    try:
        from ..spending_adjustments import load_adjustments as _load_spending_adjustments
        c['spending_adjustments'] = _load_spending_adjustments(data.get('Cashflow') or {})
    except Exception:
        c['spending_adjustments'] = []
    c.setdefault('home_proj', 0.0)
    c.setdefault('home_proj_end', c['plan_start'] - 1)
    c.setdefault('vac', 0.0)
    c.setdefault('vac_end', c['plan_start'] - 1)

    # ── Spending Budget per-line table (#95) ──────────────────────────────────
    # Additive plan-file table ``spending_budget_lines`` (WP6.3b; was client_spending_budget_lines.csv): each row is its own budget
    # line with per-line start/end/one-time/amount. Lines in the
    # ``home_improvement`` section route to housing costs; ``gifts_charity`` and
    # all others route to rec_extra. Guarded so plans without the table behave
    # exactly as before.
    try:
        from ..plan_datasets import active_dataset_rows as _active_dataset_rows
        for _bl in _active_dataset_rows('spending_budget_lines'):
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
        # Never fail a build because of the optional budget-lines table.
        pass

    # Unified Spending Budget: the consolidated budget supersedes both
    # the legacy Core Spending base input and the budget-lines table.
    # Apply after legacy parsing so the budget can replace those compatibility
    # values rather than double-counting them.
    try:
        from ..spending_budget_resolver import apply_budget_to_engine_config as _apply_unified_spending_budget
        _apply_unified_spending_budget(c)
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
    # #299: house sale proceeds may be split across multiple accounts by
    # percentage instead of going to a single account. Rows live under
    # numbered 'Home Sale Split N' subsections (see
    # src/server_services/strategy_asset_service.py's home_sale_splits_payload /
    # save_home_sale_splits_payload, the read/write pair the UI's add/delete-row
    # editor round-trips through). Empty when unconfigured -- the engine
    # falls back to the single home_sale_acct field above in that case.
    c['home_sale_splits'] = []
    for _sub, _vals in (data.get('Home Sale Split') or {}).items():
        if not str(_sub or '').strip().lower().startswith('split_'):
            continue
        _acct = str(_vals.get('account', '') or '').strip()
        _pct = _n(_vals.get('percentage', '0'), 0.0)
        if _pct > 1.0:
            _pct = _pct / 100.0
        if not _acct or _pct <= 0:
            continue
        c['home_sale_splits'].append({'account': _acct, 'pct': _pct})

    # Current-home operating costs are entered in Housing Budget Detail/current
    # home rows.  Future housing steps carry explicit rent/buy operating costs;
    # rental utilities and renters insurance are not seeded from current-home
    # utilities/homeowners insurance because owned-home costs drop off once the
    # home is sold.  Keep the raw current-home amounts on the engine config so
    # projection and workbook code do not have to re-read CSV rows.
    # #224: a Home/Auto Insurance Policy record (Insurance page) supersedes
    # these baselines once one exists with a nonzero premium.
    _home_policy_premium = _insurance_policy_premium_sum(data, 'Home')
    c['current_homeowners_insurance_annual'] = _home_policy_premium if _home_policy_premium > 0 else _n(_v(data,'Housing','current_home','homeowners_insurance_annual','0'), 0)
    c['current_home_utilities_annual'] = _n(_v(data,'Housing','current_home','utilities_annual','0'), 0)
    c['current_home_maintenance_annual'] = _n(_v(data,'Housing','current_home','home_maintenance_annual','0'), 0)

    # State Residency Analysis: target relocation state and the current-state
    # (baseline) auto-insurance budget.  Homeowners insurance, utilities, and
    # maintenance baselines come from the Housing current-home amounts above;
    # auto insurance is a separate transportation budget captured here.
    c['residency_target_state'] = str(_v(data,'State Comparison','','target_state','') or '').strip()
    _auto_policy_premium = _insurance_policy_premium_sum(data, 'Auto')
    # Label 'current_state_baseline_annual' (item 291, was 'illinois_baseline_annual';
    # migrate_sectioned_data, called above, upgrades any legacy row first).
    c['current_auto_insurance_annual'] = _auto_policy_premium if _auto_policy_premium > 0 else _n(_v(data,'State Comparison','auto_insurance','current_state_baseline_annual','0'), 0)


def parse_housing_and_other_assets(data, c):
    """Housing steps, typed other assets, note receivable, HSA policy and the liquidity-reserve start."""
    from ..data_io import _n, _v, _y, parse_hsa_policy, parse_note_receivable, re
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

    # Note Receivable — see src/parsing/note_receivable.py for the full
    # per-note parsing and legacy scalar aggregation logic.
    c.update(parse_note_receivable(data, c['plan_start']))

    # HSA Policy scalars (withdrawal mode/window/contribution, plus
    # beneficiary/death-tax-treatment) — see src/parsing/hsa_policy.py for
    # the full parsing logic. hsa_schedule_rows/hsa_schedule_by_year (loaded
    # from client_hsa_schedule.csv) are parsed separately below by
    # parse_hsa_withdrawal_schedule(), next to the liabilities-CSV load it
    # mirrors.
    c.update(parse_hsa_policy(data, c['plan_start']))

    # Liquidity reserve requirement
    # Reserve rules are defined only by start_year, end_year, and
    # years_of_expenses to retain.  The default reserve requirement is zero.
    c['liquidity_buffer_schedule'] = []


def parse_liquidity_and_trust(data, c):
    """Liquidity-reserve rules, trust inputs and annuity/pension/QLAC income streams."""
    from ..data_io import (
        DEFAULT_SS_WAGE_BASE,
        _b,
        _n,
        _v,
        _y,
        add_liquidity_rule,
        load_qlac,
        load_stream,
        parse_estate_planning,
        parse_roth_conversion_policy,
        parse_withdrawal_spending_policy,
    )
    _lb = data.get('Liquidity Buffer', {})

    for sub, vals in _lb.items():
        if str(sub).lower().startswith('buffer_'):
            add_liquidity_rule(
                c,
                vals.get('start_year', ''),
                vals.get('end_year', ''),
                vals.get('years_of_expenses', vals.get('years_of_expenses_in_trust', '0')),
                vals.get('reserve_account', vals.get('preserve_account', 'Taxable/Trust')),
            )

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
    # NOTE: this CSV section used to also carry a "Withdrawal Policy > Priority N"
    # sub-table that a planner could reorder. It never reached the withdrawal
    # engine (the engine's cascade is fixed — see taxes.FIXED_WITHDRAWAL_CASCADE_
    # DESCRIPTION and documentation/archive/reports/SYSTEM_REVIEW_2026-07-18.md §10.1) so
    # the dead input, its CSV rows, and the UI table that edited it were removed
    # rather than wired up.

    # Withdrawal Policy bracket-target / spending-decline pair extracted to
    # src/parsing/withdrawal_policy.py (ticket 312).
    c.update(parse_withdrawal_spending_policy(data))

    # ── Roth Conversion Policy (9.5) ──────────────────────────────────────────
    c.update(parse_roth_conversion_policy(data))

    # Estate
    c.update(parse_estate_planning(data, household_size=c.get('household_size')))

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
    c['ss_wage_base'] = _n(_v(data,'Payroll Tax','Social Security','ss_wage_base_base_year',str(DEFAULT_SS_WAGE_BASE)), DEFAULT_SS_WAGE_BASE)
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

    c['wife_pension']   = load_stream(data, c, 'Member 2 Pension',          annuitant='wife')
    c['wife_single']    = load_stream(data, c, 'Member 2 Single Annuity',   annuitant='wife')
    c['wife_joint']     = load_stream(data, c, 'Member 2 Joint Annuity',    annuitant='wife')
    c['h_single']       = load_stream(data, c, 'Member 1 Single Annuity',   annuitant='husband')
    c['h_joint']        = load_stream(data, c, 'Member 1 Joint Annuity',    annuitant='husband')

    # #295: QLAC (Qualified Longevity Annuity Contract) -- a deferred-income
    # annuity bought with pre-tax retirement dollars. Reuses load_stream()'s
    # payment machinery (base=0/div_rate=0/add_pct=0 collapses it to a pure
    # guaranteed payment starting at first_yr -- see annuity_cash_income() in
    # core.py) plus QLAC-specific fields load_stream doesn't have: the
    # purchase premium (what src/core.py's qlac_excluded_rmd_balance()
    # subtracts from the RMD base) and the source account it was purchased
    # from. Two fixed slots (one per member), matching the existing
    # single/joint annuity and pension slot pattern above rather than the
    # "Other Asset N" numbered-row pattern -- SECURE 2.0 permits only one
    # QLAC-eligible aggregate premium limit per person, not a list.
    c['h_qlac']    = load_qlac(data, c, 'Member 1 QLAC', annuitant='husband')
    c['wife_qlac'] = load_qlac(data, c, 'Member 2 QLAC', annuitant='wife')
    _js_raw = _v(data,'Income Streams','Joint-and-Survivor Percentage','js_pct','100')
    c['js_pct'] = _n(_js_raw, 100)
    # If the source string contained '%', _n already converted to fraction (e.g. "100%" → 1.0).
    # If it was a plain integer like "100", _n returns 100.0 → divide by 100.
    if '%' not in str(_js_raw):
        c['js_pct'] /= 100.0


def parse_plan_settings(data, c, _sv, system_data):
    """Plan Settings and runtime-setting rows layered over the engine defaults."""
    from ..data_io import (
        _b,
        _n,
        _ss_claim_from_date_or_age,
        _v,
        _y,
        parse_advanced_modules,
        statutory_rmd_start_age,
    )
    # Plan settings: plan rows over the engine defaults (src/engine_defaults.py).
    c['model_niit']       = _b(_sv('Plan Settings','Tax Detail','model_niit','TRUE'))
    # Realized-sales ledger (step 3b.2): FALSE runs the plan without the ledger's year-1 gains and loss pool.
    c['use_realized_sales'] = _b(_sv('Plan Settings','Tax Detail','use_realized_sales','TRUE'))
    c['model_state_est']  = _b(_sv('Plan Settings','Estate','model_state_estate_tax','TRUE'))

    # Global/tax-aware rebalancing controls: plan rows over the engine defaults.
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
    # Next Housing Move off (design 2026-09-24 §6 [C]): the plan stays in the
    # current home and state for its whole length. Only the engine view is
    # blanked -- the rows in `data` (and so the CSV) are kept, and come back
    # when the switch is turned on again.
    from ..module_catalog import module_enabled
    if not module_enabled(c, 'housing_location_search'):
        c['home_sale_yr'] = 0
        c['home_sale_splits'] = []
        c['next_housing_steps'] = []
        c['residency_schedule'] = []

    # Advanced planning modules (529, existing life, disability, P&C/umbrella,
    # equity comp, special-needs, business succession). Report-only in Phase 1.
    c.update(parse_advanced_modules(data))

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
    # Divorce/QDRO scenario (optimization-refactor Phase 6): a one-time,
    # tax-free (IRC S1041) split of all investment accounts at a configured
    # year. Mirrors Sell Home's pattern exactly -- a CSV-editable Scenarios
    # subsection feeding generic `divorce_split_yr`/`divorce_split_pct`
    # override keys the deterministic engine reads the same way it reads
    # `home_sale_yr`.
    c['scen_divorce_yr']       = _y(_v(data,'Scenarios','Divorce',
                                        'divorce_year', '2029'), 2029)
    c['scen_divorce_split_pct'] = max(0.0, min(1.0, _n(_v(data,'Scenarios','Divorce',
                                        'divorce_split_pct', '50%'), 0.50)))
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
    # LTC Stress Test onset ages (Sheet 17) — age of the older spouse at which
    # each scenario's care-cost stream starts.
    c['ltc_onset_age_moderate_home_care']    = int(_n(_v(data,'Scenarios','LTC Stress Test','onset_age_moderate_home_care','80'), 80))
    c['ltc_onset_age_severe_home_care']      = int(_n(_v(data,'Scenarios','LTC Stress Test','onset_age_severe_home_care','82'), 82))
    c['ltc_onset_age_facility_memory_care']  = int(_n(_v(data,'Scenarios','LTC Stress Test','onset_age_facility_memory_care','85'), 85))
    c['ltc_onset_age_catastrophic_both']     = int(_n(_v(data,'Scenarios','LTC Stress Test','onset_age_catastrophic_both','87'), 87))
    c['rollover_401k_yr']  = _y(_v(data,'Model Constants','Retirement',
                                     'rollover_401k_year', str(c['plan_start'] + 4)), c['plan_start'] + 4)
    # Item 195: the shared household-level 'ss_claim_age'/'rmd_start_age' CSV
    # fields were removed as a redundant echo of the per-member fields below -
    # both fixed constants here (70 / statutory) match the schema.csv defaults
    # those removed fields carried, so this is a documentation-only fallback,
    # not a behavior change.
    c['ss_claim_age']      = 70
    c['h_ss_claim_age'], c['h_ss_claim_year'], c['h_ss_claim_month'], c['h_ss_claim_age_precise'] = _ss_claim_from_date_or_age(
        data, 'Member 1', c['h_dob_yr'], c['h_dob_month'], '70')
    c['w_ss_claim_age'], c['w_ss_claim_year'], c['w_ss_claim_month'], c['w_ss_claim_age_precise'] = _ss_claim_from_date_or_age(
        data, 'Member 2', c['w_dob_yr'], c['w_dob_month'], '70')
    # Generic/household RMD start age, anchored to the primary member's (h)
    # birth year, for conversion_window_end_year and any legacy caller that
    # doesn't distinguish members. Purely derived now (no CSV override) - see
    # the per-member override handling above.
    c['rmd_start_age'] = statutory_rmd_start_age(c['h_dob_yr'])


def parse_model_constants(data, c):
    """Model Constants, scenarios, Monte Carlo and Roth-conversion constants."""
    from ..data_io import (
        ASSET_CLASS_RETURNS,
        _b,
        _mc_engine_mode_from_plan_data,
        _n,
        _td,
        _v,
        os,
        parse_allocation_optimizer_inputs,
        parse_daf,
    )
    c['conv_window_offset']= int(_n(_v(data,'Model Constants','Roth Conversion',
                                     'roth_conv_window_end_offset','-1'), -1))
    # Actual household MAGI for the two tax years immediately before plan
    # start (item 2.6). Seeds the statutory IRMAA 2-year lookback for plan
    # years 1-2, where no projected AGI row exists yet to look back at.
    # Optional: a blank/absent value (including saved plans that predate
    # these two inputs) parses to None here, and irmaa_lookback_magi()
    # falls back to retirement/current-year AGI -- the same behavior the
    # engine used before these inputs existed.
    c['irmaa_actual_magi_2yr_prior'] = _n(_v(data,'Model Constants','IRMAA',
                                     'irmaa_actual_magi_2yr_prior',''), None)
    c['irmaa_actual_magi_1yr_prior'] = _n(_v(data,'Model Constants','IRMAA',
                                     'irmaa_actual_magi_1yr_prior',''), None)
    # P12 second half (item 4.5): an approved Form SSA-44 life-changing-event
    # appeal suppresses the IRMAA *surcharge* (not the base Part B/D/G
    # premium, which is still owed) for that member from the stated year
    # onward. Blank/absent parses to None, matching pre-4.5 behavior exactly.
    c['h_ssa44_relief_year'] = _n(_v(data,'Model Constants','IRMAA',
                                     'h_ssa44_relief_year',''), None)
    c['w_ssa44_relief_year'] = _n(_v(data,'Model Constants','IRMAA',
                                     'w_ssa44_relief_year',''), None)
    c['mc_sigma']          = _n(_v(data,'Model Constants','Monte Carlo',
                                     'mc_portfolio_sigma','0.12'), 0.12)
    c['mc_sims']           = int(os.getenv('RETIREMENT_MC_SIMS') or _n(_v(data,'Model Constants','Monte Carlo',
                                     'mc_simulations','1000'), 1000))
    c['mc_sensitivity_sims'] = int(os.getenv('RETIREMENT_MC_SENSITIVITY_SIMS') or _n(_v(data,'Model Constants','Monte Carlo',
                                     'mc_sensitivity_simulations','200'), 200))
    c['mc_engine_mode'] = _mc_engine_mode_from_plan_data(data)
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
    # LTCG bracket thresholds. WI-023 / FIN-003 (decision 3): the verified 2026 federal
    # dataset (LTCG_BRACKETS_BASE_YEAR, by filing status) is the source. The Model
    # Constants rows ltcg_0pct_top_mfj_base_year / ltcg_15pct_top_mfj_base_year used to
    # supply 2025 values (96,700 / 600,050) that the engine then indexed as if they were
    # 2026 values; those two legacy numbers are treated as "unset" and replaced by the
    # dataset. Any other explicit value is a deliberate client override and is kept.
    _ltcg_ds = _td.LTCG_BRACKETS_BASE_YEAR.get(c['filing_status']) or _td.LTCG_BRACKETS_BASE_YEAR.get('MFJ', {})
    _ltcg0_raw = _n(_v(data,'Model Constants','Capital Gains',
                       'ltcg_0pct_top_mfj_base_year',''), None)
    _ltcg15_raw = _n(_v(data,'Model Constants','Capital Gains',
                        'ltcg_15pct_top_mfj_base_year',''), None)
    c['ltcg_0_top'] = (float(_ltcg_ds.get('zero_top', 98_900)) if _ltcg0_raw in (None, 0, 96_700)
                       else _ltcg0_raw)
    c['ltcg_15_top'] = (float(_ltcg_ds.get('fifteen_top', 613_700)) if _ltcg15_raw in (None, 0, 600_050)
                        else _ltcg15_raw)
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
    # Extracted to src/parsing/allocation_optimizer_inputs.py (ticket 312).
    c.update(parse_allocation_optimizer_inputs(data))

    # ── Tax Provenance Registry (9.6) ─────────────────────────────────────────
    # Provenance of the dated tax-law constants.
    c['tax_constants_registry'] = _td.load_tax_constants()
    c['tax_provenance'] = dict(_td.TAX_YEAR_PROVENANCE)  # copy for the methodology sheet
    c['tax_table_currency_warnings'] = _td.tax_table_currency_warnings(max_lag_years=int(c.get('tax_table_currency_max_lag_years', 1) or 1))

    # DAF (Donor Advised Fund) parameters
    c.update(parse_daf(data, c['plan_start']))


def parse_ltc_and_holdings(data, c):
    """Hybrid LTC parameters, asset allocation, tax lots and the liabilities load."""
    from ..data_io import _b, _log, _n, _strict_float, _tcsv, _v, _y
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
    from ..core import TaxLot, LotEngine  # consolidated from events
    lots_by_account = {}   # {acct: {sym: [TaxLot, ...]}}
    lots_reconcile = {}    # {(acct, sym): total_lot_shares} for QC reconciliation
    from ..plan_datasets import active_dataset_text
    holdings_text = active_dataset_text('holdings')
    if holdings_text:
        reader = _tcsv.dict_reader(holdings_text)
        for row in reader:
            acct = (row.get('account','') or '').strip()
            sym  = (row.get('symbol','') or '').strip()
            if not acct or not sym:
                continue
            try:
                shares = _strict_float(row.get('shares'), 0.0)
                price = _strict_float(row.get('purchase_price'), 0.0)
            except ValueError as _exc:
                _msg = f"holdings lot skipped ({acct} {sym}): {_exc}"
                _log.warning(_msg)
                c.setdefault('config_contract_warnings', []).append(_msg)
                continue
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
    # type in (auto | heloc | student_loan | credit_card | other). A zero/absent file yields
    # an empty list so a liability-free plan behaves exactly as before.
    liabilities = []
    liab_text = active_dataset_text('liabilities')
    if liab_text:
        def _clean_year(raw):
            try:
                return int(float(str(raw or '0').replace(',', '').strip() or 0))
            except Exception:
                return 0
        for _lrow_no, row in enumerate(_tcsv.dict_reader(liab_text), start=1):
            _lid = (row.get('liability_id', '') or row.get('label', '') or '').strip()
            try:
                # '%' is stripped, not divided: the 0.06-or-6 heuristic below handles rates.
                def _clean_num(raw):
                    return _strict_float(raw, 0.0, percent_as_fraction=False)
                ltype = (row.get('type', '') or 'other').strip().lower()
                balance = _clean_num(row.get('balance', '0'))
                if balance <= 0:
                    continue
                rate = _clean_num(row.get('interest_rate', '0'))
                # Accept either a fraction (0.06) or a percent (6) for the rate.
                if rate > 1.0:
                    rate = rate / 100.0
                liabilities.append({
                    'liability_id': (row.get('liability_id', '') or '').strip(),
                    'type': ltype,
                    'label': (row.get('label', '') or '').strip(),
                    'balance': balance,
                    'interest_rate': rate,
                    'monthly_payment': _clean_num(row.get('monthly_payment', '0')),
                    'start_year': _clean_year(row.get('start_year', '0')),
                    'payoff_year': _clean_year(row.get('payoff_year', '0')),
                    'payoff_month': min(12, max(0, _clean_year(row.get('payoff_month', '0')))),
                    # Blank = carry zero after the payoff date (the default for every type).
                    'carry_zero': str(row.get('carry_zero', '') or '').strip().lower() not in ('no', 'false', '0', 'n'),
                    'notes': (row.get('notes', '') or '').strip(),
                })
            except Exception as _exc:
                # Skip only the bad row; never drop the whole list silently.
                _msg = f"liability row {_lrow_no} ({_lid or 'unnamed'}) skipped: {_exc}"
                _log.warning(_msg)
                c.setdefault('config_contract_warnings', []).append(_msg)
    c['liabilities'] = liabilities
    return LotEngine, lots_by_account, lots_reconcile


def parse_hsa_schedule_and_account_income(data, c, lots_by_account, lots_reconcile, skip_live_pricing, url_template):
    """HSA withdrawal schedule, holdings valuation and per-account income assumptions."""
    from ..data_io import (
        _ar,
        _copy,
        _n,
        _v,
        fetch_price,
        load_security_classes,
        parse_account_draw_priority,
        parse_hsa_withdrawal_schedule,
        prewarm_prices,
        reserve_checking_import_warning,
        set_fallback_prices,
    )
    # ── Load HSA withdrawal schedule from client_hsa_schedule.csv ─────────────
    # See src/parsing/hsa_policy.py:parse_hsa_withdrawal_schedule — mirrors
    # the liabilities load above; an absent/unparseable file yields an empty
    # list, which resolve_year_amount treats as "no schedule entry for any
    # year" (mode fallback for every year), matching a plan that never used
    # this feature.
    c.update(parse_hsa_withdrawal_schedule())

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

    # Compute account balances (from whichever source populated positions).
    # Every distinct symbol in the plan gets fetched here for the first time
    # (later report code re-fetches the same symbols, but quote() memoizes so
    # those are instant) -- prewarm them concurrently so the once-per-symbol
    # live-provider cost overlaps instead of running one ticker at a time.
    all_symbols = {sym for holdings in c['positions'].values() for sym in holdings}
    prewarm_prices(all_symbols, skip_live=skip_live_pricing)
    balances = {}
    for acct, holdings in c['positions'].items():
        total = 0
        for sym, shares in holdings.items():
            price = fetch_price(sym, url_template, skip_live=skip_live_pricing)
            total += shares * price
        balances[acct] = total
    c['balances'] = balances
    c['cash_other'] = sum(v for k, v in balances.items() if k.endswith('_Checking'))

    # #339 spec §8 (2026-09-24 W-F Task F2): the legacy Reserve Requirements
    # "Checking accounts" field (Other Assets,Cash,value) was removed from the
    # UI, demo CSV and schema -- it was never read by the engine, which has
    # always sourced cash_other from _Checking holdings accounts above. Kept
    # here only to warn a plan carrying a stale non-zero value forward: it
    # is not counted toward reserves unless re-entered as a _Checking account.
    _legacy_checking_value = _n(_v(data, 'Other Assets', 'Cash', 'value', '0'), 0.0)
    _checking_warning = reserve_checking_import_warning(_legacy_checking_value, balances)
    if _checking_warning:
        c.setdefault('config_contract_warnings', []).append(_checking_warning)

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

    # ── Realized-sales ledger seed (step 3b.1) ───────────────────────────────
    # The active plan's confirmed taxable sales for the plan year plus the carryforward into it, netted; None for
    # an empty ledger or with Plan Settings > use_realized_sales off, which leaves the projection exactly as it was
    # (see src/realized_seed.py).
    from ..realized_seed import active_realized_seed
    c['realized_seed'] = (active_realized_seed(c['plan_start'], c['filing_status'])
                          if c['use_realized_sales'] else None)

    # ── Individual-account withdrawal-order override (#276) ──────────────────
    c.update(parse_account_draw_priority(data))

    # Taxable portfolio income assumptions.  Taxable-account ETFs/funds distribute
    # dividends/interest that must enter AGI, SS provisional income, IRMAA MAGI,
    # NIIT, and cash-flow funding.  Use the security master to identify asset
    # class, with conservative defaults when a symbol is unmapped.
    _security_classes = load_security_classes()
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
    return _class_income_defaults, _security_classes


def parse_capital_market_returns(data, c, _class_income_defaults, _security_classes, skip_live_pricing, url_template):
    """Capital-market return assumptions and per-account expected returns."""
    from ..data_io import (
        _ap,
        _b,
        _load_capital_market_income_assumptions,
        _load_capital_market_return_assumptions,
        _n,
        _v,
        account_cma_return,
        fetch_price,
    )
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
    # Dividend reinvestment: global default plus per-account override
    # (client_policy.csv, Account Policy section). Blank override inherits
    # the global default. Applies to every investment account (taxable/Trust,
    # IRA, 401k, Roth, HSA) — not just taxable ones, since a dividend that
    # isn't reinvested still stays inside the account as cash rather than
    # being paid out to the household (see cash_yield_rate below).
    c['reinvest_dividends_default'] = _b(_v(data, 'Economic Assumptions', '', 'reinvest_dividends_default', 'NO'))
    c['cash_yield_rate'] = _n(_v(data, 'Economic Assumptions', '', 'cash_yield_rate', '2.00%'), 0.02)
    _reinvest_overrides = {}
    for _sub, _vals in data.get('Account Policy', {}).items():
        _raw = str((_vals or {}).get('reinvest_dividends', '')).strip()
        if _raw:
            _reinvest_overrides[_sub] = _b(_raw)
    account_income = {}
    invest_ids_set = set(c.get('invest_ids', []))
    for _acct, _holdings in c.get('positions', {}).items():
        if _acct not in invest_ids_set:
            continue
        _total_value = 0.0; _ord = 0.0; _qual = 0.0; _tax_exempt = 0.0
        for _sym, _shares in (_holdings or {}).items():
            _sym_u = str(_sym or '').strip().upper()
            try:
                _value = float(_shares or 0.0) * float(fetch_price(_sym_u, url_template, skip_live=skip_live_pricing) or 0.0)
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
                # Global default ON forces reinvestment everywhere; per-account
                # overrides only take effect while the global switch is OFF.
                'reinvest_dividends': True if c['reinvest_dividends_default'] else _reinvest_overrides.get(_acct, False),
            }
    c['account_taxable_income_assumptions'] = account_income
    c['portfolio_income_reduces_growth'] = True

    # C3 / Wave 3.5 (system review 2026-08-04, finding
    # engine-single-return-all-accounts): _account_return() has always read
    # c['account_returns'], but nothing populated it, so every account grew
    # at the identical flat rate regardless of what it actually held --
    # asset location, bucket strategies, and the cash reserve were
    # structurally inert. Every prerequisite for a real fix already existed
    # (per-account holdings, security_master.csv's asset-class mapping,
    # capital_market_assumptions.csv's per-class expected returns) -- this
    # is a dollar-weighted join across data already assembled just above for
    # account_income, not a new draw or a rewrite of the growth math.
    #
    # Mirrors _apply_allocation_projection_assumptions' own anchoring
    # principle: preserve the user's configured c['ret'] as the portfolio-
    # wide average, and apply only each account's RELATIVE tilt away from
    # that average based on its actual holdings -- so a bond-heavy IRA grows
    # slower and an equity-heavy Roth grows faster, without silently
    # overriding the user's own return assumption for the plan as a whole.
    _cm_returns = _load_capital_market_return_assumptions()
    # security_master.csv's asset_class column is a broad category (e.g.
    # "US EQUITY", not "US Large Cap"/"US Mid Cap"/"US Small Cap" -- it has
    # no cap-size granularity at all); capital_market_assumptions.csv (and
    # target_allocation.csv/_opt.ASSET_CLASSES) use the granular class
    # names. This maps the broad security_master category onto the single
    # granular class it best represents, mirroring the same kind of
    # broad-category fallback _class_income_defaults above already uses for
    # dividend/interest assumptions.
    _broad_to_cma_class = {
        'US EQUITY': 'US Large Cap',
        'INTERNATIONAL EQUITY': 'International',
        'INTERNATIONAL': 'International',
        'EMERGING MARKETS': 'Emerging Markets',
        'COMMODITIES': 'Commodities',
        'BONDS': 'Bonds',
        'SHORT-TERM BONDS': 'Short-Term Bonds',
        'TIPS': 'TIPS',
        'MUNICIPAL BONDS': 'Municipal Bonds',
        'MANAGED FUTURES': 'Managed Futures',
        'PRIVATE CREDIT': 'Private Credit',
        'REITS': 'REITs',
        'CASH': 'Cash',
    }
    _base_ret = float(c.get('ret', 0.0) or 0.0)
    _all_holdings = {}
    for _holdings in c.get('positions', {}).values():
        for _sym, _shares in (_holdings or {}).items():
            _all_holdings[_sym] = _all_holdings.get(_sym, 0.0) + float(_shares or 0.0)
    _portfolio_ret, _portfolio_val = account_cma_return(_all_holdings, _security_classes, _broad_to_cma_class, _cm_returns, _preset, url_template, skip_live_pricing)
    account_returns = {}
    if _portfolio_ret is not None and _portfolio_val > 0:
        for _acct, _holdings in c.get('positions', {}).items():
            if _acct not in invest_ids_set:
                continue
            _acct_ret, _acct_val = account_cma_return(_holdings, _security_classes, _broad_to_cma_class, _cm_returns, _preset, url_template, skip_live_pricing)
            if _acct_ret is None:
                continue
            account_returns[_acct] = _base_ret + (_acct_ret - _portfolio_ret)
    c['account_returns'] = account_returns

    # Tax-loss harvesting policy (taxable/Trust accounts only). off = ignore;
    # analyze_only = surface opportunities in reporting but don't change the
    # projection; apply = harvest each year inside the projection so terminal
    # net worth and lifetime tax reflect the strategy.
    _tlh_policy = str(_v(data, 'Withdrawal Policy', 'Tax-Loss Harvesting', 'tlh_policy', 'off') or 'off').strip().lower()
    if _tlh_policy not in ('off', 'analyze_only', 'apply'):
        _tlh_policy = 'off'
    c['tlh_policy'] = _tlh_policy
    c['tlh_min_loss_dollars'] = _n(_v(data, 'Withdrawal Policy', 'Tax-Loss Harvesting', 'tlh_min_loss_dollars', '500'), 500.0)
    c['tlh_min_loss_pct'] = _n(_v(data, 'Withdrawal Policy', 'Tax-Loss Harvesting', 'tlh_min_loss_pct', '5%'), 0.05)
    c['tlh_annual_ceiling'] = _n(_v(data, 'Withdrawal Policy', 'Tax-Loss Harvesting', 'tlh_annual_ceiling', '0'), 0.0)


def parse_harvest_policies_and_lots(data, c, LotEngine, lots_by_account):
    """Tax-loss and gain-harvest policy, lot method and the rental-property tail."""
    from ..data_io import PRICE_CACHE, _n, _v, parse_rental_properties
    c['tlh_transaction_cost_bps'] = _n(_v(data, 'Withdrawal Policy', 'Tax-Loss Harvesting', 'tlh_transaction_cost_bps', '2'), 2.0)
    c['tlh_fraction_sold_before_death'] = _n(_v(data, 'Withdrawal Policy', 'Tax-Loss Harvesting', 'tlh_fraction_sold_before_death', '50%'), 0.5)

    # 0%-bracket gain harvesting (system review 2026-07-21, P2): symmetric
    # counterpart to TLH above -- realizes appreciated long-term lots up to
    # the remaining 0%-LTCG-bracket headroom instead of harvesting losses.
    # Same three-state policy convention as tlh_policy; defaults to off so
    # existing plans are unaffected until explicitly opted in.
    _gain_harvest_policy = str(_v(data, 'Withdrawal Policy', 'Gain Harvesting', 'gain_harvest_policy', 'off') or 'off').strip().lower()
    if _gain_harvest_policy not in ('off', 'analyze_only', 'apply'):
        _gain_harvest_policy = 'off'
    c['gain_harvest_policy'] = _gain_harvest_policy
    c['gain_harvest_min_gain_dollars'] = _n(_v(data, 'Withdrawal Policy', 'Gain Harvesting', 'gain_harvest_min_gain_dollars', '500'), 500.0)
    c['gain_harvest_min_gain_pct'] = _n(_v(data, 'Withdrawal Policy', 'Gain Harvesting', 'gain_harvest_min_gain_pct', '0%'), 0.0)
    c['gain_harvest_transaction_cost_bps'] = _n(_v(data, 'Withdrawal Policy', 'Gain Harvesting', 'gain_harvest_transaction_cost_bps', '2'), 2.0)

    # Instantiate LotEngine with current prices
    lot_method = _v(data, 'Withdrawal Policy', '', 'lot_method', 'HIFO') or 'HIFO'
    c['lot_engine'] = LotEngine(
        lots_by_account, PRICE_CACHE,
        fallback_gain_fraction=c.get('trust_gain_fraction', 0.50),
        method=lot_method.upper()
    )

    # Rental Properties (WP12.4): the typed plan tables feed c['rental_properties'] only while
    # the rental_property_income feature is on. Off: nothing is read or set, the stored
    # properties are kept, and the engine sees no rental input.
    from ..module_catalog import feature_enabled
    if feature_enabled(c, 'rental_property_income'):
        from ..plan_datasets import active_rental_properties
        parse_rental_properties(c, active_rental_properties(),
                                mfs_lived_apart=_v(data, 'Household', '', 'mfs_lived_apart', ''))
