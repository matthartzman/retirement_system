from __future__ import annotations

"""Independently importable deterministic projection stage.

This module contains the retained year-by-year calculation body.  The public
``planning_engines.project`` function is intentionally a thin orchestrator, so
calculation ownership is outside the API facade and can be tested/imported as a
stage module.  Additional fine-grained stage files can replace pieces behind
this same contract without changing callers.
"""

from .budget_rollups import category_budget_rollup, housing_budget_rollup
from .year_state import MutableYearState, create_initial_year_state
from ..planning_engines import *  # noqa: F401,F403 - import legacy helper functions/classes
from .. import planning_engines as _legacy_pe

# Star import intentionally skips private module aliases used by the retained
# deterministic calculation body.  Rebind those aliases explicitly.
_ar = _legacy_pe._ar
_aa = _legacy_pe._aa
_we = _legacy_pe._we
_ce = _legacy_pe._ce
_ie = _legacy_pe._ie
_ge = _legacy_pe._ge


def run_deterministic_projection_stage(c):
    """Primary year-by-year projection implementation.

    Workbook, PDF, API, and scenario builds call this module as the single
    projection source of truth.
    """
    c = ensure_engine_config(c, source='project')
    rows = []
    event_log = []  # append-only event log for traceability

    # Clear any cached annuity payment state (prevents stale data when
    # scenarios deep-copy c with a populated cache from the base run).
    for _sk in ['wife_pension','wife_single','wife_joint','h_single','h_joint']:
        if _sk in c and isinstance(c[_sk], dict):
            c[_sk].pop('_pmt_cache', None)

    def emit(ev):
        event_log.append(ev)

    def _add_account_flow(target, acct, amount):
        amount = float(amount or 0.0)
        if acct and abs(amount) > 1e-9:
            target[acct] = target.get(acct, 0.0) + amount

    def _tag_deposit_source(row, acct, source, amount):
        """Record a human-readable source label for a deposit, alongside the
        existing flat `_account_deposits` total (which remains unchanged and
        is still the authoritative per-account aggregate for reconciliation).
        """
        amount = float(amount or 0.0)
        if acct and abs(amount) > 1e-9:
            sources = row.setdefault('_account_deposit_sources', {})
            sources.setdefault(acct, []).append({'source': source, 'amount': amount})

    def _mortgage_payment_and_balance(principal, annual_rate, year_index, term_years=30):
        """Return annual P&I payment and end-of-year balance for a fixed mortgage."""
        principal = max(0.0, float(principal or 0.0))
        if principal <= 0.0:
            return 0.0, 0.0
        term_years = max(1, int(term_years or 30))
        total_pmts = term_years * 12
        made_pmts = max(0, min(total_pmts, int(year_index) * 12))
        remaining_pmts_start = max(0, total_pmts - made_pmts)
        if remaining_pmts_start <= 0:
            return 0.0, 0.0
        monthly_rate = max(0.0, float(annual_rate or 0.0)) / 12.0
        if monthly_rate > 1e-9:
            monthly_pmt = principal * monthly_rate / (1 - (1 + monthly_rate) ** (-total_pmts))
            bal_start = principal * ((1 + monthly_rate) ** total_pmts - (1 + monthly_rate) ** made_pmts) / ((1 + monthly_rate) ** total_pmts - 1)
        else:
            monthly_pmt = principal / total_pmts
            bal_start = max(0.0, principal - monthly_pmt * made_pmts)
        bal = bal_start
        principal_paid = 0.0
        for _ in range(min(12, remaining_pmts_start)):
            interest = bal * monthly_rate
            principal_component = max(0.0, min(bal, monthly_pmt - interest))
            bal = max(0.0, bal - principal_component)
            principal_paid += principal_component
        return monthly_pmt * min(12, remaining_pmts_start), bal

    def _next_housing_for_year(year):
        """Compute cash-flow and net-worth impacts from Housing next-step rows.

        Purchase down payments are not ordinary spending; they are exposed as
        `other_cash_need` so the workbook cash bridge can reconcile them
        separately from annual spending.  Rent and ongoing purchase operating
        costs are Housing spending.
        """
        out = {
            'rent': 0.0, 'mortgage_payment': 0.0, 'real_estate_tax': 0.0,
            'insurance': 0.0, 'utilities': 0.0, 'maintenance': 0.0, 'hoa': 0.0,
            'purchase_cash': 0.0, 'home_value': 0.0, 'mortgage_balance': 0.0,
            'equity': 0.0, 'active_labels': [],
        }
        for step in c.get('next_housing_steps', []) or []:
            try:
                start = int(step.get('start_year') or 0)
            except Exception:
                start = 0
            if not start or year < start:
                continue
            try:
                end = int(step.get('end_year') or 0)
            except Exception:
                end = 0
            if end and year > end:
                continue
            typ = str(step.get('type') or 'purchase').strip().lower()
            base = start
            infl = _infl_ratio(year, base)
            label = step.get('id') or 'next_housing'
            out['active_labels'].append(str(label))
            if typ == 'rent':
                out['rent'] += float(step.get('monthly_rent', 0.0) or 0.0) * 12.0 * infl
                # Rent steps use explicit renters-insurance and rental-utility
                # inputs.  Current-home utilities/homeowners insurance do not
                # carry over after sale.
                out['insurance'] += float(step.get('insurance_annual', 0.0) or 0.0) * infl
                out['utilities'] += float(step.get('utilities_annual', 0.0) or 0.0) * infl
                continue
            price = float(step.get('purchase_price', 0.0) or 0.0)
            if price <= 0.0:
                # Even without a purchase price, carry operating costs if present.
                out['insurance'] += float(step.get('insurance_annual', 0.0) or 0.0) * infl
                out['utilities'] += float(step.get('utilities_annual', 0.0) or 0.0) * infl
                out['maintenance'] += float(step.get('maintenance_annual', 0.0) or 0.0) * infl
                continue
            down_pct = max(0.0, min(1.0, float(step.get('down_payment_pct', 0.20) or 0.20)))
            loan = max(0.0, price * (1.0 - down_pct))
            if year == start:
                out['purchase_cash'] += price * down_pct
            year_index = max(0, year - start)
            pmt, bal_end = _mortgage_payment_and_balance(loan, float(step.get('mortgage_rate_pct', 0.0) or 0.0), year_index)
            home_value = price * ((1.0 + float(c.get('home_appr', 0.0) or 0.0)) ** max(0, year - start + 1))
            out['mortgage_payment'] += pmt
            out['mortgage_balance'] += bal_end
            out['home_value'] += home_value
            out['equity'] += max(0.0, home_value - bal_end)
            out['real_estate_tax'] += price * float(step.get('real_estate_tax_pct', 0.0) or 0.0) * infl
            out['insurance'] += float(step.get('insurance_annual', 0.0) or 0.0) * infl
            out['utilities'] += float(step.get('utilities_annual', 0.0) or 0.0) * infl
            out['maintenance'] += float(step.get('maintenance_annual', 0.0) or 0.0) * infl
            out['hoa'] += price * float(step.get('hoa_pct', 0.0) or 0.0) * infl
        return out

    # TCJA warning
    emit(EvWarning(0, 'TCJA_PERMANENT',
         'Tax brackets assume TCJA made permanent. If TCJA sunsets, '
         'brackets revert to higher 2017 levels — Roth conversion strategy '
         'and lifetime tax estimates would change materially.'))

    # Mutable per-run/year state is explicitly separated from immutable run
    # configuration.  The deterministic stage keeps legacy variable names below
    # for calculation compatibility, but each value is initialized from the
    # state container rather than mutating the config boundary.
    year_state: MutableYearState = create_initial_year_state(c)
    bal = year_state.balances

    # Account movement is registry-driven; no role-name balance aliases are used.

    home_val = year_state.home_value
    # Tracks dollars in trust accounts that carry a stepped-up (cash) basis —
    # e.g. home-sale proceeds whose gain was already taxed at sale. These are
    # drawn first and incur no further LTCG tax.
    bal_basis_free = year_state.basis_free_balances
    # HELOC state — initialized once before the year loop
    if '_heloc_balance' not in bal:
        bal['_heloc_balance'] = 0.0
    # Additional liabilities (auto / student_loan / heloc / other) — initialize
    # each outstanding balance once before the year loop. Stored on `bal` under a
    # private key so a liability-free plan keeps the dict empty and unchanged.
    if '_liability_balances' not in bal:
        bal['_liability_balances'] = {}
        for _li_idx, _li in enumerate(c.get('liabilities', []) or []):
            _li_key = _li.get('liability_id') or f'liability_{_li_idx}'
            bal['_liability_balances'][_li_key] = float(_li.get('balance', 0.0) or 0.0)
    autos_val = year_state.autos_value
    startup = year_state.startup_value
    note_bal = year_state.note_balance
    # Per-note remaining balances (Note Receivable is repeatable — one or more
    # named notes, e.g. "RedMane Note"). Each note amortizes on its own
    # first/last payment schedule; note_bal above is only the aggregate
    # remaining balance shown on the balance sheet.
    _note_items = c.get('note_items') or []
    _note_bals = {id(n): float(n.get('face_value', 0.0) or 0.0) for n in _note_items}

    filing = year_state.filing_status
    first_death_done = year_state.first_death_done
    cst_funded_total = year_state.cst_funded_total
    cst_balance = year_state.cst_balance

    def _path_factor(path_key, annual_rate, year):
        path = c.get(path_key)
        if isinstance(path, dict) and year in path:
            try:
                return float(path[year])
            except Exception:
                pass
        return (1 + float(annual_rate or 0.0)) ** (year - c['plan_start'])

    def _path_ratio(path_key, annual_rate, year, base_year):
        if year <= base_year:
            return (1 + float(annual_rate or 0.0)) ** max(0, year - base_year)
        path = c.get(path_key)
        if isinstance(path, dict) and year in path and base_year in path:
            try:
                denom = float(path[base_year])
                if denom != 0:
                    return float(path[year]) / denom
            except Exception:
                pass
        return (1 + float(annual_rate or 0.0)) ** (year - base_year)

    def _infl_factor(year):
        return _path_factor('inflation_index_by_year', c['inf'], year)

    def _spending_factor(year):
        if c.get('core_spending_growth_mode') == 'manual_override':
            return (1 + float(c.get('spend_inf', c.get('inf', 0.0)) or 0.0)) ** max(0, year - c['plan_start'])
        return _infl_factor(year)

    def _wellness_premium_for_age(age, year):
        """Return the annual per-person premium used for SEHI in this year.

        There is intentionally no standalone "health insurance premiums"
        input.  Before age 65, use Pre-65 Healthcare Premium; at 65+ use
        Medicare Part B + Part D + Part G costs.
        """
        try:
            age = float(age)
        except Exception:
            age = 0.0
        if age < 65:
            return float(c.get('bridge_premium', 0.0) or 0.0) * _path_factor('medical_index_by_year', c.get('med_inf', c['inf']), year)
        part_b = float(c.get('partb', 0.0) or 0.0) * 12 * _path_factor('medical_index_by_year', c.get('med_inf', c['inf']), year)
        part_d = float(c.get('partd', 0.0) or 0.0) * 12 * _path_factor('partd_index_by_year', c.get('partd_inf', c.get('med_inf', c['inf'])), year)
        part_g = float(c.get('partg', 0.0) or 0.0) * 12 * _path_factor('medical_index_by_year', c.get('med_inf', c['inf']), year)
        return part_b + part_d + part_g

    def _sehi_deduction_source_amount(year, h_age, w_age, h_alive=True, w_alive=True):
        if c.get('sehi_derived_from_wellness', True):
            total = 0.0
            if h_alive:
                total += _wellness_premium_for_age(h_age, year)
            if w_alive:
                total += _wellness_premium_for_age(w_age, year)
            return max(0.0, total)
        return max(0.0, float(c.get('sehi', 0.0) or 0.0))

    def _infl_ratio(year, base_year):
        return _path_ratio('inflation_index_by_year', c['inf'], year, base_year)

    def _ss_ratio(year, claim_year):
        return _path_ratio('ss_cola_index_by_year', c['ss_cola'], year, claim_year)

    def _bracket_factor_for_year(year):
        idx = c.get('bracket_index_by_year') if isinstance(c.get('bracket_index_by_year'), dict) else None
        if idx:
            base_year = getattr(getattr(_ar, '_td', None), 'FEDERAL_BRACKETS_VALUE_YEAR', TAX_BASE_YEAR)
            base_to_plan = (1.0 + float(c.get('brk_inf', 0.02) or 0.0)) ** (int(c.get('plan_start', year)) - int(base_year))
            return base_to_plan * float(idx.get(year, idx.get(int(year), 1.0)) or 1.0)
        return (1.0 + float(c.get('brk_inf', 0.02) or 0.0)) ** (int(year) - getattr(getattr(_ar, '_td', None), 'FEDERAL_BRACKETS_VALUE_YEAR', TAX_BASE_YEAR))

    def _inflate_brackets_path(brackets, inflator_unused, years_from_plan_start):
        year_eff = int(c.get('plan_start', 0) or 0) + int(years_from_plan_start or 0)
        factor = _bracket_factor_for_year(year_eff)
        return [(lo * factor, hi * factor if hi != float('inf') else float('inf'), rate) for lo, hi, rate in brackets]

    def _compute_fed_tax_path(taxable, year, filing, brk_inf_unused=None):
        brk = FEDERAL_BRACKETS_BASE_YEAR.get(filing, FEDERAL_BRACKETS_BASE_YEAR['Single'])
        brk = _inflate_brackets_path(brk, None, int(year) - int(c.get('plan_start', year)))
        tax = 0.0
        taxable = max(0.0, float(taxable or 0.0))
        for lo, hi, rate in brk:
            if taxable <= lo:
                break
            tax += (min(taxable, hi) - lo) * rate
        return max(0.0, tax)

    def _standard_deduction_path(year, filing, brk_inf_unused=None, n_over_65=2):
        td = getattr(_ar, '_td', None)
        base = getattr(td, 'STANDARD_DEDUCTION_BASE_YEAR', {}).get(filing, 15750) if td else 15750
        add_per = getattr(td, 'STANDARD_DEDUCTION_OVER65_BASE_YEAR', {}).get(filing, 1650) if td else 1650
        return (base + add_per * n_over_65) * _bracket_factor_for_year(year)

    def _irmaa_factor_for_year(year):
        idx = c.get('irmaa_index_by_year') if isinstance(c.get('irmaa_index_by_year'), dict) else None
        if idx:
            return float(idx.get(year, idx.get(int(year), 1.0)) or 1.0)
        return (1.0 + float(c.get('irmaa_inflator', 0.02) or 0.0)) ** (int(year) - int(c.get('plan_start', year)))

    def _irmaa_surcharge_path(agi, year, n_people, filing):
        tiers = IRMAA_TIERS_BASE_YEAR.get(filing, IRMAA_TIERS_BASE_YEAR['MFJ'])
        infl = _irmaa_factor_for_year(year)
        for threshold, partb, partd in reversed(tiers):
            if agi > threshold * infl:
                return (partb + partd) * n_people * 12
        return 0.0

    def _irmaa_tier_path(agi, year, filing):
        tiers = IRMAA_TIERS_BASE_YEAR.get(filing, IRMAA_TIERS_BASE_YEAR['MFJ'])
        infl = _irmaa_factor_for_year(year)
        for i, (threshold, _, _) in enumerate(reversed(tiers)):
            if agi > threshold * infl:
                return len(tiers) - i
        return 0

    def _ltcg_tax_on_gain_path(gain, ordinary_income, year):
        if gain <= 0:
            return 0.0
        infl = _bracket_factor_for_year(year)
        top0 = c['ltcg_0_top'] * infl
        top15 = c['ltcg_15_top'] * infl
        base = max(0.0, ordinary_income)
        tax = 0.0
        remaining = float(gain or 0.0)
        in0 = min(remaining, max(0.0, top0 - base)); remaining -= in0
        in15 = min(remaining, max(0.0, top15 - max(base, top0))); tax += in15 * 0.15; remaining -= in15
        tax += max(0.0, remaining) * 0.20
        return max(0.0, tax)

    def _fra_for_birth_year(dob_year):
        dob_year = int(dob_year or 1960)
        if dob_year >= 1960:
            return 67.0
        if dob_year <= 1937:
            return 65.0
        if dob_year <= 1942:
            return 65.0 + (dob_year - 1937) * (2.0 / 12.0)
        if dob_year <= 1954:
            return 66.0
        return 66.0 + (dob_year - 1954) * (2.0 / 12.0)

    def _ss_claim_factor(claim_age, dob_year):
        # SSA reduction/credit factors relative to PIA at FRA.
        fra = _fra_for_birth_year(dob_year)
        months = int(round((float(claim_age or fra) - fra) * 12))
        if months >= 0:
            return 1.0 + months * (0.08 / 12.0)
        early = abs(months)
        first36 = min(36, early) * (5.0 / 900.0)
        extra = max(0, early - 36) * (5.0 / 1200.0)
        return max(0.0, 1.0 - first36 - extra)

    def _ss_benefit_from_age70(monthly_at_70, claim_age, dob_year):
        f70 = _ss_claim_factor(70, dob_year) or 1.0
        return float(monthly_at_70 or 0.0) * (_ss_claim_factor(claim_age, dob_year) / f70)

    def _basis_stepup_fraction(decedent_owned=True):
        regime = str(c.get('basis_step_up_property_regime', 'COMMON_LAW') or 'COMMON_LAW').upper()
        if regime in ('COMMUNITY_PROPERTY', 'FULL_STEP_UP'):
            return 1.0
        if regime == 'HALF_STEP_UP':
            return 0.5
        return 1.0 if decedent_owned else 0.5

    def _taxable_portfolio_income_for_year():
        # Dividends/interest are taxable in the year earned whether or not they
        # are reinvested (an account holds every investment type, but only
        # taxable/Trust accounts generate a current tax event; IRA/401k/Roth/
        # HSA dividends aren't taxed until a separate withdrawal occurs).
        # Whether the yield compounds into the holding or converts to
        # account-internal cash is a growth-engine concern (see
        # planning_engines.apply_end_of_year_growth) — either way the money
        # never leaves the account, so this no longer funds spending directly.
        ordinary = qualified = tax_exempt = 0.0
        taxable_ids_set = set(c.get('taxable_ids', []))
        for _acct, _info in (c.get('account_taxable_income_assumptions') or {}).items():
            if _acct not in taxable_ids_set:
                continue
            _bal = max(0.0, float(bal.get(_acct, 0.0) or 0.0))
            ordinary += _bal * float(_info.get('ordinary_yield', 0.0) or 0.0)
            qualified += _bal * float(_info.get('qualified_yield', 0.0) or 0.0)
            tax_exempt += _bal * float(_info.get('tax_exempt_yield', 0.0) or 0.0)
        return ordinary, qualified, tax_exempt

    def _ss_funding_factor(year):
        try:
            cut_year = int(c.get('ss_funding_discount_year', 2032) or 2032)
            pct = max(0.0, min(1.0, float(c.get('ss_funding_discount_pct', 0.22) or 0.0)))
        except Exception:
            cut_year, pct = 2032, 0.22
        return 1.0 - pct if int(year) >= cut_year and pct > 0 else 1.0

    for year in range(c['plan_start'], c['plan_end']+1):
        h_age = year - c['h_dob_yr']
        w_age = year - c['w_dob_yr']
        row = {'year': year, 'h_age': h_age, 'w_age': w_age, 'filing': filing}
        row['_account_opening'] = {acct_id: float(bal.get(acct_id, 0.0) or 0.0) for acct_id in c['all_acct_ids']}
        row['_account_deposits'] = {}
        row['_account_deposit_sources'] = {}
        row['_account_transfers_in'] = {}
        row['_account_transfers_out'] = {}
        row['_account_conversions_in'] = {}
        row['_account_conversions_out'] = {}
        row['_account_withdrawals'] = {}
        row['_account_growth'] = {}

        # ── Deaths ──────────────────────────────────────────────────────────
        h_alive = year <= c['h_death_yr']
        w_alive = year <= c['w_death_yr']
        row['h_alive'] = h_alive
        row['w_alive'] = w_alive

        # Filing status change year after first death.  Year of death remains
        # MFJ where applicable.  QSS is available for the next two years when
        # the plan marks a dependent survivor; tax brackets use MFJ during QSS.
        _survivor_filing = c.get('survivor_filing', 'Single')
        _first_death_year = int(c.get('first_death_yr', 0) or 0)
        if _first_death_year and c.get('qss_dependent', False) and _first_death_year < year <= _first_death_year + 2:
            filing = 'MFJ'
        elif not h_alive and not first_death_done and year == c['h_death_yr']+1:
            filing = _survivor_filing
            first_death_done = True
        elif not w_alive and not first_death_done and year == c['w_death_yr']+1:
            filing = _survivor_filing
            first_death_done = True
        elif _first_death_year and year > _first_death_year + 2 and c.get('qss_dependent', False):
            filing = _survivor_filing
            first_death_done = True
        row['filing'] = filing

        # ── Spousal rollover & terminal estate consolidation ────────────────
        inher = _ie.apply_death_transition(c, bal, year, h_alive, w_alive, bal_basis_free)
        spousal_rollover = inher.description
        estate_trust = inher.estate_account or _aa.first_taxable(c) or ''
        if spousal_rollover:
            emit(EvDeath(year, 'member', spousal_rollover))
            for tr in inher.transfers:
                emit(EvTransfer(year, tr.from_acct, tr.to_acct, tr.amount, tr.reason))
                _add_account_flow(row['_account_transfers_out'], tr.from_acct, tr.amount)
                _add_account_flow(row['_account_transfers_in'], tr.to_acct, tr.amount)
        cst_funded_yr = 0.0
        if spousal_rollover and inher.survivor_owner_idx is not None and c.get('cs_enabled', False):
            available_from_decedent = sum(float(tr.amount or 0.0) for tr in inher.transfers)
            cap = max(0.0, min(float(c.get('cs_amount', c.get('il_exempt', 0.0)) or 0.0), float(c.get('il_exempt', 0.0) or 0.0)))
            cst_funded_yr = min(cap, max(0.0, available_from_decedent))
            # Actual CST funding: remove the funded amount from survivor-accessible
            # taxable/cash balances and track it as a separate estate-excluded trust
            # value. It remains part of household net worth but is not available to
            # the survivor withdrawal cascade or survivor estate base.
            _remaining_cst = cst_funded_yr
            _candidate_ids = []
            try:
                _candidate_ids.extend(_ar.ids_by_tax(c.get('account_registry', []), 'taxable', inher.survivor_owner_idx))
            except Exception:
                _candidate_ids.extend(c.get('taxable_ids', []))
            _candidate_ids.extend(c.get('cash_ids', []))
            for _aid in list(dict.fromkeys(_candidate_ids)):
                if _remaining_cst <= 0:
                    break
                _take = min(_remaining_cst, float(bal.get(_aid, 0.0) or 0.0))
                if _take > 0:
                    bal[_aid] = float(bal.get(_aid, 0.0) or 0.0) - _take
                    _add_account_flow(row['_account_transfers_out'], _aid, _take)
                    _remaining_cst -= _take
            _funded_actual = cst_funded_yr - max(0.0, _remaining_cst)
            cst_balance += _funded_actual
            cst_funded_total += _funded_actual
            cst_funded_yr = _funded_actual
        row['spousal_rollover'] = spousal_rollover
        row['estate_trust'] = estate_trust
        row['cst_funded_yr'] = cst_funded_yr
        row['cst_excluded_from_survivor_estate'] = cst_funded_total

        # ── Asset appreciation ───────────────────────────────────────────────
        if cst_balance > 0:
            cst_balance *= (1 + float(c.get('ret', 0.0) or 0.0))
        row['cst_balance'] = cst_balance
        # Note: home_val appreciation is handled inside the home sale block below
        autos_val = max(0, c['autos'] - c['autos'] / max(1, c['auto_dep_yrs']) * (year - c['plan_start'] + 1))
        # Startup equity: grow until sale year, then sell and deposit proceeds to Trust
        sale_yr   = c.get('startup_sale_year', 0)
        sale_px   = c.get('startup_sale_price', 0)
        if sale_yr and year == sale_yr and startup > 0:
            # Sale proceeds deposit to the first available taxable account.
            proceeds = sale_px if sale_px > 0 else startup
            _startup_acct = _aa.first_taxable(c)
            _aa.deposit(bal, _startup_acct, proceeds)
            _add_account_flow(row['_account_deposits'], _startup_acct, proceeds)
            _tag_deposit_source(row, _startup_acct, 'Startup Equity Sale', proceeds)
            startup = 0.0
            row['startup_sale_proceeds'] = proceeds
        elif startup > 0 and (not sale_yr or year < sale_yr):
            # Only appreciate if growth_rate > 0; stays flat when 0
            if c['startup_gr'] > 0:
                startup *= (1 + c['startup_gr'])
            row['startup_sale_proceeds'] = 0.0
        else:
            row['startup_sale_proceeds'] = 0.0

        # ── Home value appreciation & planned sale ───────────────────────────
        home_sold = home_val <= 0   # already sold in a prior year
        # Mortgage balance — computed once here, used in both sale and non-sale branches
        mort_bal_yr = c['mort_schedule'].get(year, 0.0)
        if year > c['mort_end'] or home_sold:
            mort_bal_yr = 0.0
        if not home_sold and c.get('home_sale_yr') and year == c['home_sale_yr']:
            # ── Home sale year ────────────────────────────────────────────────
            # 1. Gross proceeds
            gross_proceeds = c['home_sale_px'] if c['home_sale_px'] > 0 else home_val
            # 2. Selling costs (realtor commission + closing)
            selling_costs = gross_proceeds * c['home_sell_cost_pct']
            # 3. Pay off remaining mortgage (from amortization schedule)
            mort_payoff = mort_bal_yr
            mort_bal_yr = 0.0  # mortgage retired at sale
            proceeds_after = max(0, gross_proceeds - selling_costs - mort_payoff)
            # 4. Capital gain: (gross - selling costs) - basis  [selling costs reduce gain]
            basis = c.get('home_basis', 0) or c['home_val'] * 0.5
            cap_gain = max(0, gross_proceeds - selling_costs - basis)
            # 5. §121 exclusion: $500k for MFJ, $250k otherwise. The filing
            # status is already switched to survivor_filing after the configured
            # survivor window, so post-window survivor sales do not over-exclude.
            sec121_exclusion = 500000.0 if filing == 'MFJ' else 250000.0
            sec121_exclusion = min(float(c.get('sec121', sec121_exclusion) or sec121_exclusion), sec121_exclusion)
            taxable_gain = max(0, cap_gain - sec121_exclusion)
            # 6. LTCG tax is computed later in this same-year tax pass after
            # ordinary taxable income is known. Deposit gross-after-cost/mortgage
            # proceeds now; the withdrawal cascade funds the tax like every other
            # current-year liability.
            home_sale_tax = 0.0
            row['_home_sale_taxable_gain_pending'] = taxable_gain
            # 7. Proceeds deposited to designated account (basis-free)
            net_proceeds = max(0, proceeds_after)
            # Pay off HELOC from home sale proceeds before depositing
            if c.get('heloc_enabled', False):
                _heloc_bal_at_sale = float(bal.get('_heloc_balance', 0.0) or 0.0)
                heloc_payoff_yr = min(_heloc_bal_at_sale, net_proceeds)
                net_proceeds = max(0.0, net_proceeds - heloc_payoff_yr)
                bal['_heloc_balance'] = max(0.0, _heloc_bal_at_sale - heloc_payoff_yr)
                row['heloc_payoff'] = heloc_payoff_yr
            acct = c.get('home_sale_acct') or _aa.first_taxable(c)
            if acct not in bal:
                acct = _aa.first_taxable(c)
            _aa.deposit(bal, acct, net_proceeds)
            _add_account_flow(row['_account_deposits'], acct, net_proceeds)
            _tag_deposit_source(row, acct, 'Home Sale Proceeds', net_proceeds)
            # These dollars already had their gain taxed → stepped-up basis.
            # Track as basis-free so future trust draws don't tax them again.
            if acct in bal_basis_free:
                bal_basis_free[acct] += net_proceeds
            # 8. Zero out home value — no longer owned
            home_val = 0.0
            home_equity = 0.0
            row['home_sale_gross']    = gross_proceeds
            row['home_sale_costs']    = selling_costs
            row['home_sale_mort_off'] = mort_payoff
            row['home_sale_gain']     = cap_gain
            row['home_sale_sec121_exclusion'] = sec121_exclusion
            row['home_sale_taxable']  = taxable_gain
            row['home_sale_tax']      = home_sale_tax
            row['home_sale_net']      = net_proceeds
            row['home_sale_acct']     = acct
            emit(EvHomeSale(year, gross_proceeds, selling_costs, mort_payoff,
                            home_sale_tax, net_proceeds, acct))
        else:
            # Normal year — appreciate home if still owned
            if not home_sold:
                home_val *= (1 + c['home_appr'])
            home_equity = max(0, home_val - mort_bal_yr)
            # Reduce home equity by outstanding HELOC balance in non-sale years
            if c.get('heloc_enabled', False):
                home_equity = max(0.0, home_equity - float(bal.get('_heloc_balance', 0.0) or 0.0))
            row['home_sale_gross'] = row['home_sale_mort_off'] = 0
            row['home_sale_gain']  = row['home_sale_taxable']  = 0
            row['home_sale_tax']   = row['home_sale_net']      = 0
            row['home_sale_costs'] = 0
            row['home_sale_acct']  = ''

        # Note Receivable — sum principal/interest across every note, since
        # each note (e.g. "RedMane Note") can have its own face value,
        # payment schedule, and interest-by-year detail.
        note_princ_yr = 0.0
        note_int_yr = 0.0
        for _nitem in _note_items:
            _nfirst = _nitem.get('first_payment_year', c['plan_start'])
            _nlast = _nitem.get('last_payment_year', c['plan_start'])
            if _nfirst <= year <= _nlast:
                _nprinc_yr = _nitem.get('annual_principal', 0.0) if year < _nlast else _nitem.get('final_principal', 0.0)
                note_princ_yr += _nprinc_yr
                note_int_yr += _nitem.get('interest_by_year', {}).get(year, 0)
                _note_bals[id(_nitem)] = max(0.0, _note_bals[id(_nitem)] - _nprinc_yr)
        note_bal = sum(_note_bals.values()) if _note_items else max(0, note_bal - note_princ_yr)

        # ── Income ──────────────────────────────────────────────────────────
        # Earned income — with optional scenario overrides for extension years
        # (years beyond the base earn_end, used in Retire Later scenario re-runs)
        if c['earn_start'] <= year <= c['earn_end']:
            base_earn_end = c.get('base_earn_end', c['earn_end'])   # original before scenario
            if year > base_earn_end:
                # Extension years: use scenario-specific growth rate and base income
                ext_growth  = c.get('scen_retire_inc_growth', c['earn_inc'])
                ext_base    = c['earned'] * (1 + c['earn_inc']) ** (base_earn_end - c['earn_start'])
                earned_base = ext_base * (1 + ext_growth) ** (year - base_earn_end)
            else:
                earned_base = c['earned'] * (1 + c['earn_inc']) ** (year - c['earn_start'])
        else:
            earned_base = 0.0
        earned_base = c.get('ytd_blend_earned_override', {}).get(year, earned_base)
        row['earned'] = earned_base
        if earned_base > 0:
            emit(EvIncome(year, 'earned', earned_base, c['entity']))

        # Payroll / self-employment tax
        se_tax = 0.0; half_se_ded = 0.0; sehi_ded = 0.0; qbi_ded = 0.0
        payroll_tax = 0.0
        if earned_base > 0:
            if c['entity'] == 'sole_prop':
                net_se   = earned_base - c['biz_exp'] - c['home_off']
                se_base  = net_se * c['se_factor']
                ss_se    = min(se_base, c['ss_wage_base']) * c['ss_se_rate']
                med_se   = se_base * c['med_se_rate']
                se_tax   = ss_se + med_se
                if c['se_half_ded']:
                    half_se_ded = se_tax / 2
                sehi_source = _sehi_deduction_source_amount(year, h_age, w_age, h_alive, w_alive)
                sehi_ded = min(sehi_source, net_se)
                if c['qbi_elig']:
                    qbi_base = net_se - half_se_ded - sehi_ded
                    qbi_ded  = qbi_base * 0.20
                payroll_tax = se_tax
            else:
                # S-Corp: payroll tax only on W-2 salary, not the full distribution
                # Extension years may use a scenario salary override
                base_earn_end = c.get('base_earn_end', c['earn_end'])
                if year > base_earn_end and 'scen_retire_salary' in c:
                    salary = c['scen_retire_salary']
                else:
                    salary = c['scorp_salary']
                salary       = min(salary, earned_base)   # can't exceed total income
                # Employee + employer FICA on salary only.  Employer FICA is a
                # business expense that reduces distributable income/QBI.
                ss_ee   = min(salary, c['ss_wage_base']) * c['ss_ee_rate']
                ss_er   = min(salary, c['ss_wage_base']) * c['ss_ee_rate']   # employer match
                med_ee  = salary * c['med_ee_rate']
                med_er  = salary * c['med_ee_rate']
                employer_fica = ss_er + med_er
                payroll_tax  = ss_ee + ss_er + med_ee + med_er
                distribution = max(0, earned_base - c['biz_exp'] - c['home_off'] - salary - employer_fica)
                # SEHI: deducted via W-2 box 1 treatment
                sehi_source = _sehi_deduction_source_amount(year, h_age, w_age, h_alive, w_alive)
                sehi_ded = min(sehi_source, salary + distribution)
                # QBI on distribution (salary excluded from QBI base)
                if c['qbi_elig']:
                    qbi_base = distribution - sehi_ded
                    qbi_ded  = max(0, qbi_base * 0.20)
                # IL corporate surcharge on distributable income
                # (already captured in state_tax via AGI; no separate payroll item)

            # Additional Medicare tax applies to Medicare wages / SE earnings,
            # not to S-corp distributions.
            add_med_base = se_base if c['entity'] == 'sole_prop' else salary
            if add_med_base > c['add_med_thr']:
                payroll_tax += (add_med_base - c['add_med_thr']) * c['add_med_rate']

        row['sehi_deduction_source'] = _sehi_deduction_source_amount(year, h_age, w_age, h_alive, w_alive) if earned_base > 0 else 0.0
        row['payroll_tax'] = payroll_tax

        # Remaining-year proration for the current calendar year (see
        # ytd_projection_blend.py) — today's live balance already reflects
        # whatever contributions have actually happened so far this year, so
        # only the remaining fraction of the year's contribution is added.
        _contrib_proration = c.get('ytd_blend_contrib_proration', {}).get(year, 1.0)

        # 401k contribution
        k401_contrib = 0.0
        if c['earn_start'] <= year <= c['earn_end']:
            k401_limit_yr = c['k401_lim'] * ((1 + c.get('brk_inf', c.get('inf', 0.025))) ** max(0, year - c['plan_start'])) if c.get('k401_limit_indexed', True) else c['k401_lim']
            k401_contrib = min(c['k401_mo']*12, k401_limit_yr) * _contrib_proration
            row['k401_limit_used'] = k401_limit_yr
            _k401_acct = _aa.first_account(c, owner_idx=0, acct_type='401k') or _aa.first_pretax(c, 0)
            _aa.deposit(bal, _k401_acct, k401_contrib)
            _add_account_flow(row['_account_deposits'], _k401_acct, k401_contrib)
            _tag_deposit_source(row, _k401_acct, '401(k) Contribution', k401_contrib)
        row['k401_contrib'] = k401_contrib

        # workplace plan rollover after contributions end
        ROLLOVER_401K_YEAR = c['rollover_401k_yr']
        _k401_id = _aa.first_account(c, owner_idx=0, acct_type='401k')
        _ira_dest = _aa.first_account(c, owner_idx=0, acct_type='traditional_ira') or _aa.first_pretax(c, 0)
        _rolled = False
        if year == ROLLOVER_401K_YEAR and _k401_id and _ira_dest and bal.get(_k401_id, 0) > 0:
            amt = bal.get(_k401_id, 0)
            bal[_ira_dest] = bal.get(_ira_dest, 0) + amt
            bal[_k401_id] = 0.0
            _add_account_flow(row['_account_transfers_out'], _k401_id, amt)
            _add_account_flow(row['_account_transfers_in'], _ira_dest, amt)
            _rolled = True
        row['k401_rollover'] = 1.0 if _rolled else 0.0

        # HSA contribution
        hsa_contrib = 0.0
        hsa_people_eligible = (1 if h_alive and h_age < 65 else 0) + (1 if w_alive and w_age < 65 else 0)
        if year <= c['hsa_last_contrib'] and (not c.get('hsa_requires_hdhp', True) or hsa_people_eligible > 0):
            hsa_limit_yr = c['hsa_contrib_base'] * ((1 + c.get('brk_inf', c.get('inf', 0.025))) ** max(0, year - c['plan_start'])) if c.get('hsa_limit_indexed', True) else c['hsa_contrib_base']
            catchups = ((1 if h_alive and 55 <= h_age < 65 else 0) + (1 if w_alive and 55 <= w_age < 65 else 0)) * c.get('hsa_catchup', 0.0)
            hsa_contrib = min(hsa_limit_yr + catchups, hsa_limit_yr + catchups) * _contrib_proration
            row['hsa_limit_used'] = hsa_limit_yr
            row['hsa_catchups_used'] = catchups
            _hsa_acct = _aa.first_hsa(c, 0)
            _aa.deposit(bal, _hsa_acct, hsa_contrib)
            _add_account_flow(row['_account_deposits'], _hsa_acct, hsa_contrib)
            _tag_deposit_source(row, _hsa_acct, 'HSA Contribution', hsa_contrib)
        row['hsa_contrib'] = hsa_contrib

        # Social Security.  Benefits are entered as age-70 amounts; honor
        # configured claim ages by back-solving PIA with SSA early/delayed factors.
        h_claim_age = max(62, min(70, int(c.get('h_ss_claim_age', c.get('ss_claim_age', 70)) or 70)))
        w_claim_age = max(62, min(70, int(c.get('w_ss_claim_age', c.get('ss_claim_age', 70)) or 70)))
        h_ss_yr = c['h_dob_yr'] + h_claim_age
        w_ss_yr = c['w_dob_yr'] + w_claim_age
        h_pia = float(c.get('h_ss_pia', 0.0) or 0.0) or (float(c.get('h_ss_claim_monthly', 0.0) or 0.0) / (_ss_claim_factor(h_claim_age, c['h_dob_yr']) or 1.0)) or (float(c.get('h_ss70', 0.0) or 0.0) / (_ss_claim_factor(70, c['h_dob_yr']) or 1.0))
        w_pia = float(c.get('w_ss_pia', 0.0) or 0.0) or (float(c.get('w_ss_claim_monthly', 0.0) or 0.0) / (_ss_claim_factor(w_claim_age, c['w_dob_yr']) or 1.0)) or (float(c.get('w_ss70', 0.0) or 0.0) / (_ss_claim_factor(70, c['w_dob_yr']) or 1.0))
        h_monthly_claim = h_pia * _ss_claim_factor(h_claim_age, c['h_dob_yr'])
        w_monthly_claim = w_pia * _ss_claim_factor(w_claim_age, c['w_dob_yr'])
        if c.get('spousal_benefits_enabled', True):
            # Deemed filing/spousal top-up approximation: once both spouses have
            # claimed, each can receive up to 50% of the other's PIA, reduced for
            # claiming before FRA.
            if h_claim_age < _fra_for_birth_year(c['h_dob_yr']):
                h_spousal_factor = _ss_claim_factor(h_claim_age, c['h_dob_yr'])
            else:
                h_spousal_factor = 1.0
            if w_claim_age < _fra_for_birth_year(c['w_dob_yr']):
                w_spousal_factor = _ss_claim_factor(w_claim_age, c['w_dob_yr'])
            else:
                w_spousal_factor = 1.0
            h_monthly_claim = max(h_monthly_claim, 0.5 * w_pia * h_spousal_factor)
            w_monthly_claim = max(w_monthly_claim, 0.5 * h_pia * w_spousal_factor)

        h_ss = 0.0
        if h_alive and year >= h_ss_yr:
            h_ss = h_monthly_claim * 12 * _ss_ratio(year, h_ss_yr)
        w_ss = 0.0
        if w_alive and year >= w_ss_yr:
            w_ss = w_monthly_claim * 12 * _ss_ratio(year, w_ss_yr)

        # SS survivor benefit is symmetrical: survivor receives the larger
        # claimed benefit record (subject to survivor percentage), regardless of
        # which spouse dies first.
        if not h_alive and w_alive and year > c['h_death_yr']:
            if c.get('survivor_benefit_uses_deceased_claim_age', True):
                h_record = h_monthly_claim
            else:
                h_record = h_pia * _ss_claim_factor(70, c['h_dob_yr'])
            h_ss_at_death = h_record * 12 * _ss_ratio(c['h_death_yr'], h_ss_yr) if c['h_death_yr'] >= h_ss_yr else 0
            w_ss_at_death = w_monthly_claim * 12 * _ss_ratio(c['h_death_yr'], w_ss_yr) if c['h_death_yr'] >= w_ss_yr else 0
            w_ss = max(w_ss, h_ss_at_death * c['ss_surv'], w_ss_at_death)
            h_ss = 0
        if not w_alive and h_alive and year > c['w_death_yr']:
            if c.get('survivor_benefit_uses_deceased_claim_age', True):
                w_record = w_monthly_claim
            else:
                w_record = w_pia * _ss_claim_factor(70, c['w_dob_yr'])
            w_ss_at_death = w_record * 12 * _ss_ratio(c['w_death_yr'], w_ss_yr) if c['w_death_yr'] >= w_ss_yr else 0
            h_ss_at_death = h_monthly_claim * 12 * _ss_ratio(c['w_death_yr'], h_ss_yr) if c['w_death_yr'] >= h_ss_yr else 0
            h_ss = max(h_ss, w_ss_at_death * c['ss_surv'], h_ss_at_death)
            w_ss = 0

        row['h_ss_claim_age_used'] = h_claim_age
        row['w_ss_claim_age_used'] = w_claim_age

        ss_funding_factor = _ss_funding_factor(year)
        if ss_funding_factor != 1.0:
            h_ss *= ss_funding_factor
            w_ss *= ss_funding_factor
        row['ss_funding_factor'] = ss_funding_factor
        row['ss_funding_discount_pct'] = max(0.0, 1.0 - ss_funding_factor)
        row['h_ss'] = h_ss
        row['w_ss'] = w_ss

        # Annuity income (death-governed)
        pension = annuity_cash_income(c['wife_pension'], year) if w_alive else 0
        wife_single_ann = annuity_cash_income(c['wife_single'], year) if w_alive else 0
        wife_joint_ann  = (annuity_cash_income(c['wife_joint'], year)
                          if (w_alive or h_alive) else 0)
        if not w_alive and h_alive:
            wife_joint_ann *= c['js_pct']
        h_single_ann    = annuity_cash_income(c['h_single'], year) if h_alive else 0
        h_joint_ann     = (annuity_cash_income(c['h_joint'], year)
                          if (h_alive or w_alive) else 0)
        if not h_alive and w_alive:
            h_joint_ann *= c['js_pct']

        row.update({'pension': pension,
                    'wife_single_ann': wife_single_ann,
                    'wife_joint_ann': wife_joint_ann,
                    'h_single_ann': h_single_ann,
                    'h_joint_ann': h_joint_ann})

        # Note income
        row['note_princ'] = note_princ_yr
        row['note_int']   = note_int_yr

        # ── Spending ─────────────────────────────────────────────────────────
        # Base spending (inflated until freeze year)
        if year <= c['spending_freeze_yr']:
            spend = c['spend_base'] * _spending_factor(year)
        else:
            spend = c['spend_base'] * _spending_factor(c['spending_freeze_yr'])
        spend = c.get('ytd_blend_spend_override', {}).get(year, spend)
        row['spend_base_yr'] = spend

        # Recurring extras — Home Improvement items route to housing costs; all others to rec_extra
        rec_extra = 0.0
        home_improvement_extra = 0.0
        if year <= c.get('home_proj_end', c['plan_start'] - 1):
            rec_extra += c.get('home_proj', 0.0) * _infl_factor(year)
        if year <= c.get('vac_end', c['plan_start'] - 1):
            rec_extra += c.get('vac', 0.0) * _infl_factor(year)
        for ev in c.get('recurring_extras', []):
            start_yr = int(ev.get('start_year') or c['plan_start'])
            end_yr = int(ev.get('end_year') or start_yr)
            if start_yr <= year <= end_yr:
                base_yr = max(c['plan_start'], start_yr)
                _ev_amt = float(ev.get('amount') or 0.0) * _infl_ratio(year, base_yr)
                if ev.get('is_home_improvement'):
                    home_improvement_extra += _ev_amt
                else:
                    rec_extra += _ev_amt
        # Higher-of floor for Travel / Large Discretionary: a current-year top-up
        # (annualized actual minus budget, when positive) computed by the YTD blend
        # so the discretionary spend never projects below the client's run rate.
        rec_extra += c.get('ytd_blend_extra_topup', {}).get(year, 0.0)
        row['rec_extra'] = rec_extra
        row['home_improvement_extra'] = home_improvement_extra

        # Lump events (including DAF contribution as a deductible lump)
        lump_yr = c['lump'].get(year, 0)
        # DAF contribution: added to spending in contribution year, tax-deductible
        daf_contrib_yr = 0.0
        if c.get('daf_enabled', False) and year == c.get('daf_year', 0):
            daf_contrib_yr = c.get('daf_amount', 0)
            lump_yr += daf_contrib_yr
        row['lump']          = lump_yr
        row['daf_contrib_yr']= daf_contrib_yr
        # DAF grants (reduces annual charitable giving from the DAF balance, not new cash)
        daf_grant_yr = 0.0
        if (c.get('daf_enabled', False) and
                c.get('daf_use_start', 9999) <= year <= c.get('daf_use_end', 9999)):
            daf_grant_yr = c.get('daf_use_amount', 0)
        row['daf_grant_yr'] = daf_grant_yr

        # Mortgage, real-estate taxes, home improvement, and Housing Budget Detail.
        # Current-year Housing budgets seed projection rows when the dedicated
        # model inputs are blank. Dedicated inputs still win when configured.
        housing_budget_groups = housing_budget_rollup(c, year, _infl_ratio)
        mort_pmt_configured = float(c.get('mort_pmt', 0.0) or 0.0) > 0
        mort_end_configured = int(c.get('mort_end', 0) or 0) >= int(c.get('plan_start', year) or year)
        mort_yr = c['mort_pmt'] if (mort_pmt_configured and year <= c['mort_end']) else 0
        # If the current mortgage detail is missing entirely, allow the Housing
        # budget detail to seed mortgage cash flow.  Once a mortgage payment/end
        # year is configured, however, never resurrect the budget amount after
        # the payoff year.
        if mort_yr <= 0 and not (mort_pmt_configured and mort_end_configured):
            mort_yr = float(housing_budget_groups.get('Mortgage', 0.0) or 0.0)
        sale_yr_active = c.get('home_sale_yr', 0)
        owns_home_for_re_tax = not sale_yr_active or sale_yr_active <= 0 or year < sale_yr_active
        re_tax_growth = float(c.get('real_estate_tax_growth_rate', c.get('inf', 0.0)) or 0.0)
        re_tax_factor = (1.0 + re_tax_growth) ** max(0, year - int(c.get('plan_start', year)))
        re_tax_base = float(c.get('real_estate_tax_base', 0.0) or 0.0)
        if re_tax_base <= 0:
            re_tax_base = float(housing_budget_groups.get('Real Estate Taxes', 0.0) or 0.0)
        re_tax_yr = (re_tax_base * re_tax_factor) if owns_home_for_re_tax else 0.0
        home_improvement_lump_yr = float(c.get('home_improvement_lump', {}).get(year, 0) or 0.0)
        home_improvement_override_yr = home_improvement_extra + home_improvement_lump_yr
        home_improvement_budget_yr = float(housing_budget_groups.get('Home Improvement', 0.0) or 0.0)
        if home_improvement_budget_yr > 0:
            home_improvement_budget_yr *= _infl_ratio(year, int(c.get('plan_start', year) or year))
        home_improvement_yr = home_improvement_override_yr if home_improvement_override_yr > 0 else home_improvement_budget_yr
        # Next Housing Step rows are authoritative future rent/buy events.
        # They add ongoing Housing cash flow and, for purchases, home equity /
        # mortgage liability.  Start-year down payment is a separate cash need.
        next_housing_yr = _next_housing_for_year(year)
        mort_yr += float(next_housing_yr.get('mortgage_payment', 0.0) or 0.0)
        re_tax_yr += float(next_housing_yr.get('real_estate_tax', 0.0) or 0.0)

        # Rent is modeled only through Housing Next Step rows.  The retired
        # post-sale rent setting is intentionally ignored so there is one
        # obvious place for rent, renters insurance, and rental utilities.
        rent_yr = float(next_housing_yr.get('rent', 0.0) or 0.0)

        current_home_operating_active = owns_home_for_re_tax
        housing_budget_utilities_yr = float(housing_budget_groups.get('Utilities', 0.0) or 0.0) if current_home_operating_active else 0.0
        housing_budget_maintenance_yr = float(housing_budget_groups.get('Maintenance', 0.0) or 0.0) if current_home_operating_active else 0.0
        housing_budget_other_yr = float(housing_budget_groups.get('Other', 0.0) or 0.0) if current_home_operating_active else 0.0
        housing_utilities_yr = housing_budget_utilities_yr + float(next_housing_yr.get('utilities', 0.0) or 0.0)
        housing_maintenance_yr = housing_budget_maintenance_yr + float(next_housing_yr.get('maintenance', 0.0) or 0.0)
        housing_other_yr = (housing_budget_other_yr + float(next_housing_yr.get('insurance', 0.0) or 0.0)
                            + float(next_housing_yr.get('hoa', 0.0) or 0.0))
        housing_operating_yr = housing_utilities_yr + housing_maintenance_yr + housing_other_yr
        other_cash_need_yr = float(next_housing_yr.get('purchase_cash', 0.0) or 0.0)
        row['next_housing_purchase_cash_yr'] = other_cash_need_yr
        row['next_housing_home_value'] = float(next_housing_yr.get('home_value', 0.0) or 0.0)
        row['next_housing_mortgage_balance'] = float(next_housing_yr.get('mortgage_balance', 0.0) or 0.0)
        row['next_housing_equity'] = float(next_housing_yr.get('equity', 0.0) or 0.0)
        row['next_housing_active'] = ', '.join(next_housing_yr.get('active_labels', []) or [])
        row['mortgage_payment_yr'] = mort_yr
        row['real_estate_tax_yr'] = re_tax_yr
        row['home_improvement_yr'] = home_improvement_yr
        row['mortgage'] = mort_yr + re_tax_yr + home_improvement_yr
        row['rent_yr'] = rent_yr
        row['housing_utilities_yr'] = housing_utilities_yr
        row['housing_maintenance_yr'] = housing_maintenance_yr
        row['housing_other_yr'] = housing_other_yr
        row['housing_operating_yr'] = housing_operating_yr
        row['housing_total_yr'] = (mort_yr + re_tax_yr + row['home_improvement_yr'] + rent_yr + housing_operating_yr)
        row['other_cash_need_yr'] = other_cash_need_yr
        # Hybrid LTC premium (if enabled)
        ltc_prem_yr = 0.0
        if (c.get('ltc_enabled', False) and c.get('ltc_annual_prem', 0) > 0
                and year >= c.get('ltc_start_year', 9999)):
            ltc_prem_yr = c.get('ltc_annual_prem', 0)
        row['ltc_prem_yr'] = ltc_prem_yr

        wellness_shock_yr = 0.0
        _health_path = c.get('wellness_shock_by_year')
        if isinstance(_health_path, dict):
            wellness_shock_yr = float(_health_path.get(year, 0.0) or 0.0)
        row['wellness_shock_yr'] = wellness_shock_yr

        # Compute RMDs and taxable portfolio income before wellness and Roth
        # conversion planning, because ACA PTC, SS provisional income, NIIT, and
        # conversion headroom all depend on these income lines.
        rmd_result = _we.compute_rmds(c, bal, year, h_age, w_age, h_alive, w_alive, rmd_divisor)
        rmd_h = rmd_result['h']; rmd_w = rmd_result['w']; rmd_total = rmd_result['total']
        portfolio_ordinary, portfolio_qualified, portfolio_tax_exempt = _taxable_portfolio_income_for_year()
        # Informational only — taxable dividend/interest income for the year,
        # for AGI/MAGI/NIIT/IRMAA. It no longer funds spending: the money
        # never leaves the account (see apply_end_of_year_growth).
        portfolio_income_total = portfolio_ordinary + portfolio_qualified + portfolio_tax_exempt
        row['portfolio_ordinary_income'] = portfolio_ordinary
        row['portfolio_qualified_dividends'] = portfolio_qualified
        row['portfolio_tax_exempt_interest'] = portfolio_tax_exempt
        row['portfolio_income_total'] = portfolio_income_total

        # Deterministic wellness spending that earlier builds collected but
        # did not spend: pre-65 bridge, Medicare B/D/G base premiums, and OOP.
        h_bridge = (1 if h_alive and h_age < 65 and year >= c.get('h_ret_yr', 9999) else 0)
        w_bridge = (1 if w_alive and w_age < 65 and year >= c.get('w_ret_yr', 9999) else 0)
        bridge_people = h_bridge + w_bridge
        bridge_premium_gross = bridge_people * float(c.get('bridge_premium', 0.0) or 0.0) * _path_factor('medical_index_by_year', c.get('med_inf', c['inf']), year)
        # Preliminary ACA PTC estimate before Roth conversions; the conversion
        # planner receives bridge_people to constrain avoidable MAGI spikes.
        # The final PTC is recomputed after the actual Roth conversion and
        # Social Security taxable amount are known, so conversion-driven MAGI
        # changes reduce the subsidy before the withdrawal cascade runs.
        _aca_pre_non_ss = (earned_base - half_se_ded - sehi_ded + rmd_total + pension + wife_single_ann + wife_joint_ann + h_single_ann + h_joint_ann + note_int_yr + portfolio_ordinary + portfolio_qualified)
        _aca_pre_ss_tax = social_security_taxable_amount(h_ss + w_ss, _aca_pre_non_ss + portfolio_tax_exempt, filing)
        aca_ptc_pre_conversion = aca_premium_tax_credit(c, year=year, magi=_aca_pre_non_ss + _aca_pre_ss_tax + portfolio_tax_exempt, bridge_people=bridge_people)
        aca_ptc_yr = aca_ptc_pre_conversion
        bridge_premium_yr = max(0.0, bridge_premium_gross - aca_ptc_yr)
        partb_yr = ((1 if h_alive and h_age >= 65 else 0) + (1 if w_alive and w_age >= 65 else 0)) * float(c.get('partb', 0.0) or 0.0) * 12 * _path_factor('medical_index_by_year', c.get('med_inf', c['inf']), year)
        partd_yr = ((1 if h_alive and h_age >= 65 else 0) + (1 if w_alive and w_age >= 65 else 0)) * float(c.get('partd', 0.0) or 0.0) * 12 * _path_factor('partd_index_by_year', c.get('partd_inf', c.get('med_inf', c['inf'])), year)
        partg_yr = ((1 if h_alive and h_age >= 65 else 0) + (1 if w_alive and w_age >= 65 else 0)) * float(c.get('partg', 0.0) or 0.0) * 12 * _path_factor('medical_index_by_year', c.get('med_inf', c['inf']), year)
        alive_count = (1 if h_alive else 0) + (1 if w_alive else 0)
        oop_yr = (float(c.get('oop', 0.0) or 0.0) * float(c.get('oop_utilization_pct', 1.0) or 1.0)
                  * (1.0 if alive_count >= 2 else (0.5 if alive_count == 1 else 0.0))
                  * _path_factor('medical_index_by_year', c.get('med_inf', c['inf']), year))
        wellness_premium_yr = bridge_premium_yr + partb_yr + partd_yr + partg_yr
        wellness_transaction_premium_yr = category_budget_rollup(c, year, [
            'wellness_premium', 'pre65_wellness_premium', 'medicare_part_b',
            'medicare_part_d', 'medigap_premium'
        ], _path_factor, 'medical_index_by_year', 'med_inf')
        if wellness_premium_yr <= 0:
            wellness_premium_yr = wellness_transaction_premium_yr

        # Wellness detail budgets (Medical, Dental, Vision, Rx/OTC and other
        # Wellness categories) are the workbook/UI detail expansion. The household
        # Medical OOP Cap is a cap/reference for non-premium medical spending, not a
        # standalone expense. When detail rows exist, cap non-premium detail at
        # the modeled Medical OOP Cap; when detail rows are absent, do not create a
        # duplicate OOP expense.
        wellness_medical_yr = category_budget_rollup(c, year, ['medical', 'dermatologist'], _path_factor, 'medical_index_by_year', 'med_inf')
        wellness_dental_yr = category_budget_rollup(c, year, ['dentist', 'dental'], _path_factor, 'medical_index_by_year', 'med_inf')
        wellness_vision_yr = category_budget_rollup(c, year, ['vision', 'eye_exams', 'glasses_contacts'], _path_factor, 'medical_index_by_year', 'med_inf')
        wellness_rx_otc_yr = category_budget_rollup(c, year, ['drugs_rx_and_otc', 'prescription_drugs', 'otc_meds'], _path_factor, 'partd_index_by_year', 'partd_inf')
        wellness_other_yr = category_budget_rollup(c, year, [
            'health_club', 'exercise_health_equipment', 'vitamins_supplements',
            'supplements', 'wellness_other'
        ], _path_factor, 'medical_index_by_year', 'med_inf')
        wellness_detail_budget_yr = wellness_medical_yr + wellness_dental_yr + wellness_vision_yr + wellness_rx_otc_yr + wellness_other_yr
        if wellness_detail_budget_yr > 0 and oop_yr > 0 and wellness_detail_budget_yr > oop_yr:
            scale = oop_yr / wellness_detail_budget_yr
            wellness_medical_yr *= scale
            wellness_dental_yr *= scale
            wellness_vision_yr *= scale
            wellness_rx_otc_yr *= scale
            wellness_other_yr *= scale
            wellness_detail_budget_yr = oop_yr
        wellness_base_yr = wellness_premium_yr + wellness_detail_budget_yr
        row['wellness_bridge_premium_gross'] = bridge_premium_gross
        row['aca_premium_tax_credit_pre_conversion'] = aca_ptc_pre_conversion
        row['aca_premium_tax_credit'] = aca_ptc_yr
        row['aca_ptc_loss_from_conversion'] = 0.0
        row['wellness_bridge_premium'] = bridge_premium_yr
        row['medicare_base_premium'] = partb_yr + partd_yr + partg_yr
        row['wellness_premiums_yr'] = wellness_premium_yr
        row['medicare_part_g_premium'] = partg_yr
        row['wellness_oop_max_reference_yr'] = oop_yr
        row['wellness_medical_yr'] = wellness_medical_yr
        row['wellness_dental_yr'] = wellness_dental_yr
        row['wellness_vision_yr'] = wellness_vision_yr
        row['wellness_rx_otc_yr'] = wellness_rx_otc_yr
        row['wellness_other_yr'] = wellness_other_yr
        row['wellness_detail_budget_yr'] = wellness_detail_budget_yr
        row['wellness_oop_estimate'] = wellness_detail_budget_yr
        row['wellness_base_yr'] = wellness_base_yr

        # ── HELOC P&I: pre-computed here so it shows in spending, not withdrawals ─
        # Interest accrues on the opening-of-year balance; repayment principal is
        # amortized over the remaining repayment term. Both are spending obligations
        # funded by the withdrawal cascade, exactly like mortgage P&I. The draw
        # phase (new borrowing that offsets the gap) is handled further below.
        heloc_draw_yr = 0.0
        heloc_interest_yr = 0.0
        heloc_payoff_yr = 0.0
        heloc_repayment_principal_yr = 0.0
        _heloc_rate_yr = 0.0
        if c.get('heloc_enabled', False) and c.get('heloc_credit_limit', 0) > 0:
            _heloc_bal_pre = float(bal.get('_heloc_balance', 0.0) or 0.0)
            _heloc_years_elapsed = max(0, year - c.get('plan_start', year))
            _heloc_rate_yr = (float(c.get('heloc_initial_rate_pct', 0.085) or 0.085)
                              + _heloc_years_elapsed * float(c.get('heloc_rate_drift_bps_yr', 25) or 25) / 10000.0)
            heloc_interest_yr = _heloc_bal_pre * _heloc_rate_yr
            if year > c.get('heloc_draw_end_year', 0) and _heloc_bal_pre > 1.0:
                _repay_total_yrs = max(1, int(c.get('heloc_repayment_years', 10) or 10))
                _repay_end_yr = int(c.get('heloc_draw_end_year', 0)) + _repay_total_yrs
                _repay_yrs_left = max(1, _repay_end_yr - year + 1)
                _monthly_rate = _heloc_rate_yr / 12.0
                _n_pmts = _repay_yrs_left * 12
                if _monthly_rate > 1e-9:
                    _monthly_pmt = _heloc_bal_pre * _monthly_rate / (1 - (1 + _monthly_rate) ** (-_n_pmts))
                else:
                    _monthly_pmt = _heloc_bal_pre / max(1, _n_pmts)
                heloc_repayment_principal_yr = min(_heloc_bal_pre, max(0.0, _monthly_pmt * 12 - heloc_interest_yr))

        # Total pre-tax spending need (including deterministic wellness, LTC
        # premium, post-sale rent, stochastic MC wellness/LTC shocks, and
        # HELOC P&I). home_improvement items included via home_improvement_extra
        # and home_improvement_lump_yr.
        total_spend_need = (spend + rec_extra + lump_yr + mort_yr + row['home_improvement_yr']
                            + rent_yr + housing_operating_yr + ltc_prem_yr
                            + wellness_base_yr + wellness_shock_yr
                            + heloc_interest_yr + heloc_repayment_principal_yr)
        row['total_spend'] = total_spend_need

        # ── RMDs ─────────────────────────────────────────────────────────────
        _rmd_draws = _we.apply_rmds(bal, rmd_result)
        row['_rmd_by_account'] = dict(_rmd_draws)
        for _aid, _amt in _rmd_draws.items():
            emit(EvRMD(year, _aid, 0, 0, _amt))
            _add_account_flow(row['_account_withdrawals'], _aid, _amt)

        row['rmd_h'] = rmd_h
        row['rmd_w'] = rmd_w
        row['rmd_total'] = rmd_total

        # ── Roth Conversions ─────────────────────────────────────────────────
        def _state_tax_estimate_for_conversion(_agi_est, _tax_year):
            # Use the same state-tax engine as final taxes, with the known
            # pre-conversion components. This replaces the historical Illinois
            # flat-rate shortcut and keeps Roth sizing state-aware.
            _ws_taxable_est = wife_single_ann * c['wife_single'].get('exclusion_ratio', 1.0)
            _hs_taxable_est = h_single_ann * c['h_single'].get('exclusion_ratio', 1.0)
            _ss_total_est = h_ss + w_ss
            _non_ss_est = (earned_base - half_se_ded - sehi_ded + rmd_total + pension
                           + _ws_taxable_est + wife_joint_ann + _hs_taxable_est
                           + h_joint_ann + note_int_yr + portfolio_ordinary + portfolio_qualified)
            _ss_taxable_est = social_security_taxable_amount(_ss_total_est, _non_ss_est, filing)
            _qual_ann_est = sum(annuity_cash_income(c[k], year) for k in
                                ['wife_pension','wife_joint','h_joint']
                                if c[k].get('qualified', True))
            _nonqual_ann_est = sum(annuity_cash_income(c[k], year) * c[k].get('exclusion_ratio', 1.0)
                                   for k in ['wife_single','h_single']
                                   if not c[k].get('qualified', True))
            return state_income_tax(
                c['state'], max(0, earned_base - half_se_ded - sehi_ded),
                rmd_total + _qual_ann_est, _ss_taxable_est, note_int_yr + portfolio_ordinary + portfolio_qualified,
                _nonqual_ann_est, 0.0, _tax_year, h_age >= 65 or w_age >= 65, filing=filing,
            )

        conv_plan = _ce.plan_roth_conversion(
            c, bal, year=year, filing=filing, earned_base=earned_base,
            half_se_ded=half_se_ded, sehi_ded=sehi_ded, h_ss=h_ss, w_ss=w_ss,
            rmd_total=rmd_total, pension=pension, wife_single_ann=wife_single_ann,
            wife_joint_ann=wife_joint_ann, h_single_ann=h_single_ann,
            h_joint_ann=h_joint_ann, note_int_yr=note_int_yr, note_princ_yr=note_princ_yr,
            total_spend_need=total_spend_need, spend=spend, h_age=h_age, w_age=w_age,
            portfolio_ordinary=portfolio_ordinary, portfolio_qualified=portfolio_qualified,
            portfolio_tax_exempt=portfolio_tax_exempt,
            aca_bridge_people=bridge_people,
            brackets_by_status=FEDERAL_BRACKETS_BASE_YEAR, brackets_mfj=FEDERAL_BRACKETS_MFJ,
            inflate_brackets_fn=_inflate_brackets_path, standard_deduction_fn=_standard_deduction_path,
            compute_fed_tax_fn=_compute_fed_tax_path, state_tax_estimate_fn=_state_tax_estimate_for_conversion,
        )
        moved = _ce.apply_roth_conversion(c, bal, conv_plan.amount, forced=conv_plan.forced, source_account=getattr(conv_plan, "source_account", ""), forced_sources=getattr(conv_plan, "forced_sources", []))
        roth_conv = moved.amount
        row.update(conv_plan.as_row_fields())
        row['roth_conv'] = roth_conv
        row['roth_conv_src'] = moved.source_note
        row['_conversion_by_source'] = dict(getattr(moved, 'by_source', {}) or {})
        row['_conversion_by_dest'] = dict(getattr(moved, 'by_dest', {}) or {})
        _owner_by_account = {str(a.get('id')): int(a.get('owner_idx', 0) or 0)
                             for a in (c.get('account_registry') or []) if a.get('id')}
        h_ira_conversion = 0.0
        w_ira_conversion = 0.0
        for _aid, _amt in row['_conversion_by_source'].items():
            _add_account_flow(row['_account_conversions_out'], _aid, _amt)
            if _owner_by_account.get(str(_aid), 0) == 1:
                w_ira_conversion += float(_amt or 0.0)
            else:
                h_ira_conversion += float(_amt or 0.0)
        for _aid, _amt in row['_conversion_by_dest'].items():
            _add_account_flow(row['_account_conversions_in'], _aid, _amt)
        row['h_ira_conversion'] = h_ira_conversion
        row['w_ira_conversion'] = w_ira_conversion
        # Cash withdrawals and Roth conversions are different cash-flow events,
        # but account-level IRA/401(k) review needs both. Keep the legacy *_total_wd
        # fields as cash withdrawals only and add explicit total-outflow fields for
        # account depletion / reconciliation.
        row['h_ira_total_outflow'] = h_ira_conversion
        row['w_ira_total_outflow'] = w_ira_conversion
        if roth_conv > 0:
            emit(EvConversion(year, moved.source_note, 'Roth', roth_conv))

        # ── AGI / Tax ────────────────────────────────────────────────────────
        # Social Security taxation uses the statutory provisional-income phase-in,
        # not a flat 85% inclusion. High-income plans will still usually land at
        # the 85% cap, but lower-income gap years now calculate correctly.
        ws_taxable = wife_single_ann * c['wife_single'].get('exclusion_ratio', 1.0)
        hs_taxable = h_single_ann * c['h_single'].get('exclusion_ratio', 1.0)
        ss_total = h_ss + w_ss
        non_ss_income = (earned_base - half_se_ded - sehi_ded + rmd_total + roth_conv +
                         pension + ws_taxable + wife_joint_ann +
                         hs_taxable + h_joint_ann + note_int_yr +
                         portfolio_ordinary + portfolio_qualified)
        provisional_other_income = non_ss_income + portfolio_tax_exempt
        ss_taxable = social_security_taxable_amount(ss_total, provisional_other_income, filing)
        row['ss_taxable'] = ss_taxable
        row['ss_taxable_pct_actual'] = ss_taxable / ss_total if ss_total else 0.0
        agi_pre_slid = max(0.0, non_ss_income + ss_taxable)
        # Above-the-line student-loan interest deduction: actual interest paid this
        # year on active student_loan liabilities (start-of-year balances, before the
        # amortization block runs below), capped at $2,500 with a MAGI phaseout.
        student_loan_int_ded = 0.0
        if c.get('liabilities'):
            _sl_int = 0.0
            _sl_bals = bal.get('_liability_balances', {}) or {}
            for _sl_i, _sl in enumerate(c.get('liabilities', []) or []):
                if _sl.get('type') != 'student_loan':
                    continue
                _sl_b = float(_sl_bals.get(_sl.get('liability_id') or f'liability_{_sl_i}', 0.0) or 0.0)
                if _sl_b <= 1e-6:
                    continue
                _sl_s = int(_sl.get('start_year', 0) or 0)
                _sl_p = int(_sl.get('payoff_year', 0) or 0)
                if (_sl_s and year < _sl_s) or (_sl_p and year > _sl_p):
                    continue
                _sl_int += _sl_b * float(_sl.get('interest_rate', 0.0) or 0.0)
            if _sl_int > 0.0:
                _sl_f = str(filing or 'MFJ').upper()
                if not _sl_f.startswith('MFS') and 'SEPARATE' not in _sl_f:
                    _sl_lo, _sl_hi = (165000.0, 195000.0) if (_sl_f.startswith('MFJ') or _sl_f.startswith('MARRIED') or _sl_f.startswith('Q')) else (80000.0, 95000.0)
                    if agi_pre_slid <= _sl_lo:
                        _sl_phase = 1.0
                    elif agi_pre_slid >= _sl_hi:
                        _sl_phase = 0.0
                    else:
                        _sl_phase = 1.0 - (agi_pre_slid - _sl_lo) / (_sl_hi - _sl_lo)
                    student_loan_int_ded = min(_sl_int, 2500.0) * _sl_phase
        row['student_loan_interest_deduction'] = student_loan_int_ded
        agi = max(0.0, agi_pre_slid - student_loan_int_ded)
        irmaa_magi_current = agi + portfolio_tax_exempt
        row['agi'] = agi
        row['irmaa_magi_current'] = irmaa_magi_current

        # Recompute ACA Premium Tax Credit after actual Roth conversions. ACA
        # MAGI is federal AGI plus tax-exempt interest. If a conversion reduces
        # the credit, the extra net premium is included in spending before the
        # withdrawal cascade and is also exposed to the Roth optimizer metrics.
        aca_ptc_final = aca_premium_tax_credit(c, year=year, magi=irmaa_magi_current, bridge_people=bridge_people)
        if abs(aca_ptc_final - aca_ptc_yr) > 1e-9:
            aca_ptc_yr = aca_ptc_final
            bridge_premium_yr = max(0.0, bridge_premium_gross - aca_ptc_yr)
            wellness_premium_yr = bridge_premium_yr + partb_yr + partd_yr + partg_yr
            if wellness_premium_yr <= 0:
                wellness_premium_yr = wellness_transaction_premium_yr
            wellness_base_yr = wellness_premium_yr + wellness_detail_budget_yr
            total_spend_need = (spend + rec_extra + lump_yr + mort_yr + row.get('home_improvement_yr', 0.0)
                                + rent_yr + housing_operating_yr + ltc_prem_yr
                                + wellness_base_yr + wellness_shock_yr
                                + heloc_interest_yr + heloc_repayment_principal_yr)
            row['aca_premium_tax_credit'] = aca_ptc_yr
            row['aca_ptc_loss_from_conversion'] = max(0.0, aca_ptc_pre_conversion - aca_ptc_yr)
            row['wellness_bridge_premium'] = bridge_premium_yr
            row['wellness_premiums_yr'] = wellness_premium_yr
            row['wellness_base_yr'] = wellness_base_yr
            row['total_spend'] = total_spend_need

        # SALT
        # Preliminary state tax estimate for SALT deduction (computed before final state_tax)
        # SALT estimate: use residence state rate (not hardcoded IL)
        _state_rules = STATE_TAX_RULES.get(c['state'], STATE_TAX_RULES['Illinois'])
        il_tax_est = agi * _state_rules.get('rate', 0.0495)
        configured_prop_tax_yr = float(row.get('real_estate_tax_yr', 0.0) or 0.0)
        estimated_prop_tax_yr = (home_val * _state_rules.get('prop_rate', 0.0)) if home_val > 0 else 0.0
        prop_tax_yr = configured_prop_tax_yr if configured_prop_tax_yr > 0 else estimated_prop_tax_yr
        mort_interest_yr = float((c.get('mort_interest_schedule') or {}).get(year, 0.0) or 0.0)
        salt_gross = il_tax_est + prop_tax_yr
        salt = min(salt_gross, salt_cap(year, agi))
        char = max(0, c['char_low'] - 0.005*agi)

        # Standard vs itemized
        n65 = (1 if h_age >= 65 else 0) + (1 if w_age >= 65 else 0)
        senior_bonus = senior_bonus_deduction(year, filing, agi, n65)
        std_ded = _standard_deduction_path(year, filing, c['brk_inf'], n65) + senior_bonus
        item_ded = salt + char + mort_interest_yr
        row['property_tax_for_salt'] = prop_tax_yr
        row['salt_gross'] = salt_gross
        row['mortgage_interest_deduction'] = mort_interest_yr
        row['senior_bonus_deduction'] = senior_bonus
        ded = max(std_ded, item_ded)
        if c['qbi_elig']:
            ded += qbi_ded

        taxable_inc = max(0, agi - ded)
        fed_tax = _compute_fed_tax_path(taxable_inc, year, filing, c['brk_inf'])
        # Classify income for state taxation (retirement income may be exempt)
        qual_ann = sum(annuity_cash_income(c[k], year) for k in
                       ['wife_pension','wife_joint','h_joint']
                       if c[k].get('qualified', True))
        nonqual_ann = sum(annuity_cash_income(c[k], year) * c[k].get('exclusion_ratio', 1.0)
                          for k in ['wife_single','h_single']
                          if not c[k].get('qualified', True))
        retirement_dist = rmd_total + qual_ann  # pension already included in qual_ann if qualified
        earned_net = max(0, earned_base - half_se_ded - sehi_ded)
        h_over_65 = h_age >= 65 or w_age >= 65
        state_tax = state_income_tax(c['state'], earned_net, retirement_dist,
                                     ss_taxable, note_int_yr + portfolio_ordinary + portfolio_qualified, nonqual_ann,
                                     roth_conv, year, h_over_65, filing=filing)

        # NIIT placeholder — computed after trust draws where ltcg_gain is available
        niit = 0.0
        row['_niit_ws_taxable'] = ws_taxable  # stash for later NIIT calc
        row['_niit_hs_taxable'] = hs_taxable

        # IRMAA uses the statutory two-year MAGI lookback when prior rows exist.
        n_medicare = (1 if h_age >= 65 and h_alive else 0) + (1 if w_age >= 65 and w_alive else 0)
        irmaa_magi = irmaa_lookback_magi(rows, irmaa_magi_current, c.get('irmaa_lookback_years', 2))
        row['irmaa_magi_used'] = irmaa_magi
        irmaa_yr = _irmaa_surcharge_path(irmaa_magi, year, n_medicare, filing) if n_medicare > 0 else 0.0
        row['irmaa_tier'] = _irmaa_tier_path(irmaa_magi, year, filing)

        home_sale_ltcg_gain = float(row.get('_home_sale_taxable_gain_pending', 0.0) or 0.0)
        home_sale_ltcg_tax = _ltcg_tax_on_gain_path(home_sale_ltcg_gain, max(0.0, taxable_inc), year) if home_sale_ltcg_gain > 0 else 0.0
        if home_sale_ltcg_gain > 0:
            row['home_sale_tax'] = home_sale_ltcg_tax
        total_tax_pre_niit = fed_tax + state_tax + payroll_tax + irmaa_yr
        total_tax = total_tax_pre_niit + home_sale_ltcg_tax  # updated below if NIIT/LTCG fixed-point applies
        if fed_tax > 0: emit(EvTax(year, 'federal', fed_tax, 0))
        row['state_earned_net']   = earned_net
        row['state_retirement']  = retirement_dist
        row['state_nonqual_ann'] = nonqual_ann
        row['state_ss_taxable']  = ss_taxable
        row['state_investment']  = note_int_yr
        row['state_roth_conv']   = roth_conv
        if state_tax > 0: emit(EvTax(year, 'state', state_tax, 0))
        if niit > 0: emit(EvTax(year, 'niit', niit, 0))
        if payroll_tax > 0: emit(EvTax(year, 'payroll', payroll_tax, 0))
        row.update({'fed_tax':fed_tax, 'state_tax':state_tax,
                    'niit':niit, 'irmaa':irmaa_yr, 'total_tax':total_tax,
                    'taxable_inc': taxable_inc, 'std_ded': std_ded})

        # ── Gross income / net income ─────────────────────────────────────────
        gross_income = agi   # simplified
        net_income = gross_income - total_tax
        row['gross_income'] = gross_income
        row['net_income'] = net_income

        # ── Apply Trust portfolio growth BEFORE withdrawal cascade ────────────
        # (Trust growth is now applied at end-of-year with all other accounts below)

        # ── Spending gap and withdrawal cascade ───────────────────────────────
        income_from_streams = (h_ss + w_ss + pension + wife_single_ann +
                               wife_joint_ann + h_single_ann + h_joint_ann +
                               note_princ_yr + note_int_yr + rmd_total + earned_base)
        other_cash_need_yr = float(row.get('other_cash_need_yr', 0.0) or 0.0)
        row['income_funding'] = income_from_streams
        row['other_cash_need_yr'] = other_cash_need_yr
        row['total_cash_need'] = total_spend_need + total_tax + other_cash_need_yr
        gap = row['total_cash_need'] - income_from_streams

        # ── HELOC draw: new borrowing offsets gap (P&I already in spending above) ─
        # Interest and repayment principal were added to total_spend_need before
        # the gap calculation, so gap already includes those costs. Here we only
        # handle new draws (which reduce the gap) and balance updates.
        if c.get('heloc_enabled', False) and c.get('heloc_credit_limit', 0) > 0:
            _heloc_bal_now = float(bal.get('_heloc_balance', 0.0) or 0.0)
            if year <= c.get('heloc_draw_end_year', 0):
                _remaining_credit = max(0.0, float(c['heloc_credit_limit']) - _heloc_bal_now)
                _disc_spend = float(rec_extra or 0.0) + float(lump_yr or 0.0)
                heloc_draw_yr = min(_disc_spend, _remaining_credit, max(0.0, gap))
                if heloc_draw_yr > 1e-6:
                    gap -= heloc_draw_yr
                    bal['_heloc_balance'] = _heloc_bal_now + heloc_draw_yr
            elif _heloc_bal_now > 1.0:
                # Repayment period: reduce balance by principal already counted in spending
                bal['_heloc_balance'] = max(0.0, _heloc_bal_now - heloc_repayment_principal_yr)
        row['heloc_draw'] = heloc_draw_yr
        row['heloc_interest'] = heloc_interest_yr
        row['heloc_repayment_principal'] = heloc_repayment_principal_yr
        row['heloc_balance'] = float(bal.get('_heloc_balance', 0.0) or 0.0)
        row['heloc_payoff'] = 0.0  # set to nonzero in home sale year below

        # ── Additional liabilities: amortize into yearly cash outflow ──────────
        # auto / student_loan / other / heloc line items use standard fixed
        # amortization. Interest + principal for the year is added to `gap` (the
        # cash need funded by income/withdrawals), mirroring how HELOC interest
        # and repayment principal feed `gap` above. Outstanding balances reduce
        # net worth below. A plan with no liabilities skips this loop entirely.
        liability_payment_yr = 0.0
        liability_interest_yr = 0.0
        liability_principal_yr = 0.0
        student_loan_interest_yr = 0.0
        _liab_balances = bal.get('_liability_balances', {})
        if c.get('liabilities'):
            for _li_idx, _li in enumerate(c.get('liabilities', []) or []):
                _li_key = _li.get('liability_id') or f'liability_{_li_idx}'
                _li_bal = float(_liab_balances.get(_li_key, 0.0) or 0.0)
                if _li_bal <= 1e-6:
                    continue
                _li_start = int(_li.get('start_year', 0) or 0)
                _li_payoff = int(_li.get('payoff_year', 0) or 0)
                # Not yet originated, or already past the scheduled payoff year.
                if _li_start and year < _li_start:
                    continue
                if _li_payoff and year > _li_payoff:
                    # Forgiven/assumed-settled after payoff year: drop the balance.
                    _liab_balances[_li_key] = 0.0
                    continue
                _li_rate = float(_li.get('interest_rate', 0.0) or 0.0)
                _li_annual_interest = _li_bal * _li_rate
                _li_monthly_pmt = float(_li.get('monthly_payment', 0.0) or 0.0)
                _li_annual_pmt = _li_monthly_pmt * 12.0
                if _li_annual_pmt <= 0.0:
                    # No payment specified: if a payoff year is given, level-amortize
                    # the remaining balance over the years left; else interest-only.
                    if _li_payoff and _li_payoff >= year:
                        _yrs_left = max(1, _li_payoff - year + 1)
                        _mrate = _li_rate / 12.0
                        _n = _yrs_left * 12
                        if _mrate > 1e-9:
                            _li_annual_pmt = (_li_bal * _mrate / (1 - (1 + _mrate) ** (-_n))) * 12.0
                        else:
                            _li_annual_pmt = (_li_bal / max(1, _n)) * 12.0
                    else:
                        _li_annual_pmt = _li_annual_interest  # interest-only
                # Cap the payment so it never overpays the balance + interest.
                _li_annual_pmt = min(_li_annual_pmt, _li_bal + _li_annual_interest)
                _li_principal = max(0.0, _li_annual_pmt - _li_annual_interest)
                _li_principal = min(_li_principal, _li_bal)
                _liab_balances[_li_key] = max(0.0, _li_bal - _li_principal)
                liability_payment_yr += _li_annual_pmt
                liability_interest_yr += _li_annual_interest
                liability_principal_yr += _li_principal
                if _li.get('type') == 'student_loan':
                    student_loan_interest_yr += _li_annual_interest
            gap += liability_payment_yr
        row['liability_payment'] = liability_payment_yr
        row['liability_interest'] = liability_interest_yr
        row['liability_principal'] = liability_principal_yr
        row['liability_student_loan_interest'] = student_loan_interest_yr

        # ── Withdrawal Cascade — order matches client_data.csv Withdrawal Policy ──
        # Priority 1: RMD  (handled above, already applied to income)
        # Priority 2: HSA  (scheduled window draw, not gap-dependent)
        # Priority 3: IRA elective (gross-up; draws down pre-tax before forced RMDs grow)
        # Priority 4: Taxable/trust (above reserve floor; pro-rata by spouse/member)
        # Priority 5: Roth (tax-free last resort; maximise tax-free growth)
        # Priority 6: Home equity tap

        buf_yrs = liquidity_buffer_years_for_year(c, year)

        # ── Priority 2: HSA (scheduled, not gap-driven) ────────────────────────
        hsa_res = _we.withdraw_hsa_window(c, bal, year, wellness_cost=row.get('wellness_base_yr', 0.0))
        hsa_wd = hsa_res['amount']
        gap -= hsa_wd
        row['hsa_wd'] = hsa_wd
        row['_hsa_by_account'] = dict(hsa_res.get('by_account', {}) or {})
        for _aid, _amt in row['_hsa_by_account'].items():
            _add_account_flow(row['_account_withdrawals'], _aid, _amt)

        # ── Priority 3: Pre-tax elective withdrawal ─────────────────────────
        h_ira_elective = 0.0; w_ira_elective = 0.0; ira_wd = 0.0; pretax_by_account = {}
        if gap > 0:
            brk_yr = _inflate_brackets_path(FEDERAL_BRACKETS_MFJ, c['brk_inf'], year - c['plan_start'])
            top_24_yr = next((hi for lo, hi, rate in brk_yr if rate == 0.24), 400_000)
            irmaa_thr_yr = c['irmaa_base'] * _irmaa_factor_for_year(year)
            marg = marginal_rate(taxable_inc, year, filing, c['brk_inf'])
            pretax_res = _we.withdraw_pretax_elective(
                c, bal, gap, agi, taxable_inc, year, filing, top_24_yr, irmaa_thr_yr, marg
            )
            ira_wd = pretax_res['amount']
            h_ira_elective = pretax_res['h_amount']
            w_ira_elective = pretax_res['w_amount']
            pretax_by_account = dict(pretax_res.get('by_account', {}) or {})
            gap = pretax_res['new_gap']
        row['_pretax_elective_by_account'] = pretax_by_account
        for _aid, _amt in pretax_by_account.items():
            _add_account_flow(row['_account_withdrawals'], _aid, _amt)
        row['ira_wd'] = ira_wd
        row['h_ira_elective'] = h_ira_elective
        row['w_ira_elective'] = w_ira_elective
        row['h_ira_total_wd'] = rmd_h + h_ira_elective
        row['w_ira_total_wd'] = rmd_w + w_ira_elective
        row['h_ira_total_outflow'] = row.get('h_ira_conversion', 0.0) + row['h_ira_total_wd']
        row['w_ira_total_outflow'] = row.get('w_ira_conversion', 0.0) + row['w_ira_total_wd']
        row['h_ira_rmd_pct'] = rmd_h / (rmd_h + h_ira_elective) if (rmd_h + h_ira_elective) > 0 else 0
        row['w_ira_rmd_pct'] = rmd_w / (rmd_w + w_ira_elective) if (rmd_w + w_ira_elective) > 0 else 0

        # ── Priority 4: Taxable/trust withdrawal ─────────────────────────────
        trust_res = _we.withdraw_taxable_trust(c, bal, year, gap, spend)
        trust_wd = trust_res['amount']
        ht_wd = trust_res['h_amount']
        wt_wd = trust_res['w_amount']
        trust_by_account = dict(trust_res.get('by_account', {}) or {})
        gap = trust_res['new_gap']
        if trust_wd > 0:
            emit(EvWithdraw(year, 4, 'Taxable', trust_wd, 'gap'))
        row['trust_wd'] = trust_wd
        row['h_trust_wd'] = ht_wd
        row['w_trust_wd'] = wt_wd
        row['_trust_by_account'] = dict(trust_by_account or {})
        for _aid, _amt in row['_trust_by_account'].items():
            _add_account_flow(row['_account_withdrawals'], _aid, _amt)

        # ── LTCG/NIIT fixed-point funding on taxable withdrawals ────────────
        # A taxable draw can create LTCG and NIIT; paying those taxes can in turn
        # require another taxable draw.  Earlier versions added the first LTCG/
        # NIIT result to the gap and let the next bucket fund it, which subtly
        # shifted depletion into pre-tax/Roth.  This bounded loop re-solves the
        # taxable-draw/investment-tax coupling before moving on.
        ltcg_tax = home_sale_ltcg_tax; ltcg_gain = home_sale_ltcg_gain
        investment_tax_iterations = 0
        investment_tax_funded_by_taxable = 0.0

        def _realize_taxable_gain(draws_by_account):
            gain = 0.0
            taxable_draw = 0.0
            lot_engine = c.get('lot_engine')
            for _aid, _draw in dict(draws_by_account or {}).items():
                _draw = float(_draw or 0.0)
                bf = min(_draw, bal_basis_free.get(_aid, 0.0))
                bal_basis_free[_aid] = max(0.0, bal_basis_free.get(_aid, 0.0) - bf)
                acct_taxable_draw = max(0.0, _draw - bf)
                taxable_draw += acct_taxable_draw
                if acct_taxable_draw > 0 and lot_engine and getattr(lot_engine, 'use_lots', False):
                    g, _ = lot_engine.gain_on_withdrawal(_aid, acct_taxable_draw, current_year=year, mutate=True)
                    gain += g
            if taxable_draw > 0 and not (lot_engine and getattr(lot_engine, 'use_lots', False)):
                gain = taxable_draw * c.get('trust_gain_fraction', 0.50)
            return gain

        base_nii_without_ltcg = (note_int_yr + portfolio_ordinary + portfolio_qualified +
                                 row.get('_niit_ws_taxable', 0) +
                                 row.get('_niit_hs_taxable', 0))

        def _refresh_investment_taxes():
            nonlocal ltcg_tax, niit, total_tax
            new_ltcg_tax = _ltcg_tax_on_gain_path(ltcg_gain, max(0, taxable_inc), year) if ltcg_gain > 0 else 0.0
            delta_ltcg = max(0.0, new_ltcg_tax - ltcg_tax)
            ltcg_tax = new_ltcg_tax
            delta_niit = 0.0
            if c['model_niit']:
                # Keep the engine's existing MAGI convention but recompute on
                # cumulative NII as additional taxable withdrawals are made.
                new_niit = niit_tax(base_nii_without_ltcg + ltcg_gain, agi, filing)
                delta_niit = max(0.0, new_niit - niit)
                niit = new_niit
            return delta_ltcg + delta_niit

        if ltcg_gain > 0:
            inv_tax_delta = _refresh_investment_taxes()
            gap += inv_tax_delta
        if trust_wd > 0:
            ltcg_gain += _realize_taxable_gain(trust_by_account)
            inv_tax_delta = _refresh_investment_taxes()
            gap += inv_tax_delta

        max_tax_iters = max(0, int(c.get('tax_withdrawal_fixed_point_iterations', 3) or 0))
        for _tax_iter in range(max_tax_iters):
            if gap <= 1e-6:
                break
            add_res = _we.withdraw_taxable_trust(c, bal, year, gap, spend)
            add_wd = float(add_res.get('amount', 0.0) or 0.0)
            if add_wd <= 1e-6:
                break
            investment_tax_iterations += 1
            investment_tax_funded_by_taxable += add_wd
            trust_wd += add_wd
            ht_wd += float(add_res.get('h_amount', 0.0) or 0.0)
            wt_wd += float(add_res.get('w_amount', 0.0) or 0.0)
            add_by_account = dict(add_res.get('by_account', {}) or {})
            for _aid, _amt in add_by_account.items():
                trust_by_account[_aid] = trust_by_account.get(_aid, 0.0) + _amt
                row['_trust_by_account'][_aid] = row['_trust_by_account'].get(_aid, 0.0) + _amt
                _add_account_flow(row['_account_withdrawals'], _aid, _amt)
            gap = add_res['new_gap']
            if add_wd > 0:
                emit(EvWithdraw(year, 4, 'Taxable', add_wd, 'investment tax fixed-point'))
            ltcg_gain += _realize_taxable_gain(add_by_account)
            inv_tax_delta = _refresh_investment_taxes()
            gap += inv_tax_delta

        row['trust_wd'] = trust_wd
        row['h_trust_wd'] = ht_wd
        row['w_trust_wd'] = wt_wd
        row['ltcg_gain'] = ltcg_gain
        row['ltcg_tax'] = ltcg_tax
        row['niit'] = niit
        row['investment_tax_iterations'] = investment_tax_iterations
        row['investment_tax_funded_by_taxable'] = investment_tax_funded_by_taxable
        if niit > 0:
            emit(EvTax(year, 'niit', niit, 0))
        total_tax = total_tax_pre_niit + ltcg_tax + niit
        row['total_tax'] = total_tax
        row['net_income'] = row.get('gross_income', agi) - total_tax
        # Refresh total_cash_need now that ltcg_tax/niit reflect the fixed-point
        # investment-tax passes above; the earlier value (used to seed `gap`)
        # predates those passes and would otherwise understate cash need,
        # causing the cashflow sheet's recomputed Cash Bridge Gap to disagree
        # with the true engine gap (Surplus/unfunded_gap).
        row['total_cash_need'] = total_spend_need + total_tax + other_cash_need_yr

        # ── Priority 4b: Final pre-tax draw before any Roth withdrawal ───────
        # The tax-sensitive IRA pass above can stop at a bracket/IRMAA cap even
        # when a cash gap remains.  That caused Roth to be tapped while IRA/401(k)
        # balances were still available.  The policy is now explicit: Roth is a
        # true last resort and is not used until pre-tax accounts have been
        # depleted, with this final pass still drawn pro-rata across owners.
        if gap > 0 and sum(max(0.0, float(bal.get(_aid, 0.0) or 0.0)) for _aid in c.get('pre_tax_ids', [])) > 0:
            pretax_res2 = _we.withdraw_pretax_elective(
                c, bal, gap, agi, taxable_inc, year, filing, top_24_yr, irmaa_thr_yr, marg,
                respect_tax_caps=False,
            )
            ira_wd += pretax_res2['amount']
            h_ira_elective += pretax_res2['h_amount']
            w_ira_elective += pretax_res2['w_amount']
            for _aid, _amt in dict(pretax_res2.get('by_account', {}) or {}).items():
                pretax_by_account[_aid] = pretax_by_account.get(_aid, 0.0) + _amt
                _add_account_flow(row['_account_withdrawals'], _aid, _amt)
            gap = pretax_res2['new_gap']
            row['_pretax_elective_by_account'] = dict(pretax_by_account)
            row['ira_wd'] = ira_wd
            row['h_ira_elective'] = h_ira_elective
            row['w_ira_elective'] = w_ira_elective
            row['h_ira_total_wd'] = rmd_h + h_ira_elective
            row['w_ira_total_wd'] = rmd_w + w_ira_elective
            row['h_ira_total_outflow'] = row.get('h_ira_conversion', 0.0) + row['h_ira_total_wd']
            row['w_ira_total_outflow'] = row.get('w_ira_conversion', 0.0) + row['w_ira_total_wd']
            row['h_ira_rmd_pct'] = rmd_h / (rmd_h + h_ira_elective) if (rmd_h + h_ira_elective) > 0 else 0
            row['w_ira_rmd_pct'] = rmd_w / (rmd_w + w_ira_elective) if (rmd_w + w_ira_elective) > 0 else 0

        # ── Priority 4c: Final non-Roth HSA draw before any Roth withdrawal ──
        # Roth remains the last liquid source. If the planned HSA window left a
        # remaining HSA balance and all pre-tax/taxable sources are exhausted or
        # unavailable for the cash gap, draw HSA before touching Roth.
        if gap > 0 and sum(max(0.0, float(bal.get(_aid, 0.0) or 0.0)) for _aid in c.get('hsa_ids', [])) > 0:
            hsa_res2 = _we.withdraw_hsa_gap(c, bal, gap, year=year)
            hsa_wd += hsa_res2['amount']
            gap = hsa_res2['new_gap']
            for _aid, _amt in dict(hsa_res2.get('by_account', {}) or {}).items():
                row['_hsa_by_account'][_aid] = row['_hsa_by_account'].get(_aid, 0.0) + _amt
                _add_account_flow(row['_account_withdrawals'], _aid, _amt)
            row['hsa_wd'] = hsa_wd

        # ── Priority 5: Roth withdrawal ─────────────────────────────────────
        roth_res = _we.withdraw_roth(c, bal, gap)
        roth_wd = roth_res['amount']
        h_roth_wd = roth_res['h_amount']
        w_roth_wd = roth_res['w_amount']
        gap = roth_res['new_gap']
        if roth_wd > 0:
            emit(EvWithdraw(year, 5, 'Roth', roth_wd, 'gap'))
        row['roth_wd'] = roth_wd
        row['h_roth_wd'] = h_roth_wd
        row['w_roth_wd'] = w_roth_wd
        row['_roth_by_account'] = dict(roth_res.get('by_account', {}) or {})
        for _aid, _amt in row['_roth_by_account'].items():
            _add_account_flow(row['_account_withdrawals'], _aid, _amt)

        row['home_eq_tap'] = 0.0  # eliminated; HELOC draw (in withdrawals) replaces this
        # Residual cash shortfall after all modeled funding sources. Earlier
        # Monte Carlo logic only tested ending net worth, which could remain
        # positive due to home equity / annuity PV even when spendable assets
        # were exhausted. Persist the unfunded gap so MC success can use a
        # true funded-plan definition.
        row['unfunded_gap'] = max(0.0, gap)

        # Surplus
        surplus = max(0, -gap)
        if surplus > 0:
            _surplus_target = _aa.first_taxable(c) or (_aa.first_account(c) if c.get('all_acct_ids') else None)
            bal[_surplus_target] = bal.get(_surplus_target, 0) + surplus
            _add_account_flow(row['_account_deposits'], _surplus_target, surplus)
            _tag_deposit_source(row, _surplus_target, 'Year-End Surplus Sweep', surplus)
        row['surplus'] = surplus

        # total_tax already includes current-year LTCG and NIIT from the fixed-point pass above.
        row['total_tax'] = total_tax
        row['net_income'] = row.get('gross_income', agi) - total_tax

        # ── Portfolio growth (end-of-year) ───────────────────────────────────
        port_ret = c['ret']
        def _growth_event(acct, before, rate, growth):
            return EvGrowth(year, acct, before, rate, growth)
        growth_res = _ge.apply_end_of_year_growth(c, bal, port_ret, emit, _growth_event, year=year)
        row['_account_growth'] = dict(growth_res.by_account or {})
        for _msg in growth_res.warnings:
            emit(EvWarning(year, 'GROWTH_WARNING', _msg))

        # Snapshot end-of-year account balances so validators can use row[acct_id].
        for _acct_id in c['all_acct_ids']:
            row[_acct_id] = float(bal.get(_acct_id, 0.0) or 0.0)

        # ── Annuity value for net worth ──────────────────────────────────────
        # Value = PV of remaining income payments through the relevant death.
        #   - Single-life: PV of payments from this year through annuitant's death
        #   - Joint-life: PV through the second death (continues to survivor)
        # PLUS, in the death year only, if the Cash Refund death benefit hasn't
        # yet eroded to $0, add that year's death benefit (heirs receive the
        # unrecovered contribution as a lump sum).
        def ann_pv_to_death(stream, death_yr):
            """PV of annuity payments from current year through death_yr."""
            if year > death_yr:
                return 0.0
            pv = 0.0
            for y in range(year, death_yr + 1):
                pmt = annuity_cash_income(stream, y)
                pv += pmt / ((1 + c['ret']) ** (y - year))
            return pv

        second_death = max(c['h_death_yr'], c['w_death_yr'])
        db = c['ann_db'].get(year, {})

        # Single-life: value through that annuitant's death
        w_single_val = ann_pv_to_death(c['wife_single'], c['w_death_yr']) if w_alive else 0
        h_single_val = ann_pv_to_death(c['h_single'], c['h_death_yr']) if h_alive else 0
        # Joint-life: value through second death
        w_joint_val  = ann_pv_to_death(c['wife_joint'], second_death) if (w_alive or h_alive)  else 0
        h_joint_val  = ann_pv_to_death(c['h_joint'], second_death) if (h_alive or w_alive) else 0
        # Pension: PV through wife's death (no death benefit)
        pension_val  = ann_pv_to_death(c['wife_pension'], c['w_death_yr']) if w_alive else 0

        # Death benefit in the death year only (if DB still positive)
        if year == c['w_death_yr']:
            w_single_val += db.get('W_Single', 0)
        if year == c['h_death_yr']:
            h_single_val += db.get('H_Single', 0)
        if year == second_death:
            w_joint_val += db.get('W_Joint', 0)
            h_joint_val += db.get('H_Joint', 0)

        row.update({'pension_pv': pension_val,
                    'w_single_pv': w_single_val, 'w_joint_pv': w_joint_val,
                    'h_single_pv': h_single_val, 'h_joint_pv': h_joint_val})

        # ── Net Worth ────────────────────────────────────────────────
        ann_nw = pension_val + w_single_val + w_joint_val + h_single_val + h_joint_val
        pretax_nw = sum(max(0.0, float(bal.get(_id, 0.0) or 0.0)) for _id in c.get('pre_tax_ids', []))
        roth_nw   = sum(max(0.0, float(bal.get(_id, 0.0) or 0.0)) for _id in c.get('roth_ids', []))
        trust_nw  = sum(max(0.0, float(bal.get(_id, 0.0) or 0.0)) for _id in c.get('taxable_ids', []))
        hsa_nw    = sum(max(0.0, float(bal.get(_id, 0.0) or 0.0)) for _id in c.get('hsa_ids', []))
        cash_nw   = sum(max(0.0, float(bal.get(_id, 0.0) or 0.0)) for _id in c.get('cash_ids', []))
        cst_nw    = max(0.0, float(cst_balance or 0.0))

        # other_nw = current home equity + next-housing equity + depreciating assets + note receivable + cash
        next_housing_equity = float(row.get('next_housing_equity', 0.0) or 0.0)
        other_nw = home_equity + next_housing_equity + autos_val + float(startup or 0.0) + float(note_bal or 0.0) + cash_nw

        # Outstanding balances on additional liabilities (auto/student/other/heloc
        # line items) directly reduce net worth. Empty for a liability-free plan.
        additional_liabilities = float(sum((bal.get('_liability_balances', {}) or {}).values()))

        total_nw = ann_nw + pretax_nw + roth_nw + trust_nw + cst_nw + hsa_nw + other_nw - additional_liabilities

        # Inflation-adjusted real NW (for trend analysis)
        inflation_cumu = float(row.get('inflation_cumu') or 1.0) or 1.0
        total_nw_real = total_nw / inflation_cumu

        # Liability decomposition (for NW chart and table)
        heloc_liability = float(bal.get('_heloc_balance', 0.0) or 0.0)
        next_housing_mortgage_balance = float(row.get('next_housing_mortgage_balance', 0.0) or 0.0)
        total_liabilities = mort_bal_yr + next_housing_mortgage_balance + heloc_liability + additional_liabilities

        row.update({
            'ann_nw': ann_nw,
            'pretax_nw': pretax_nw,
            'roth_nw': roth_nw,
            'trust_nw': trust_nw,
            'hsa_nw': hsa_nw,
            'cash_nw': cash_nw,
            'cst_nw': cst_nw,
            'other_nw': other_nw,
            'total_nw': total_nw,
            'total_nw_real': total_nw_real,
            'home_equity': home_equity,
            'home_val': home_val,
            'next_housing_equity': next_housing_equity,
            'next_housing_home_value': float(row.get('next_housing_home_value', 0.0) or 0.0),
            'next_housing_mortgage_balance': next_housing_mortgage_balance,
            'startup_val': float(startup or 0.0),
            'autos_val': float(autos_val or 0.0),
            'note_bal': float(note_bal or 0.0),
            'mort_bal_yr': mort_bal_yr,
            'heloc_liability': heloc_liability,
            'additional_liabilities': additional_liabilities,
            'total_liabilities': total_liabilities,
        })
        rows.append(row)
    return rows
