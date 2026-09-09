from __future__ import annotations

"""Independently importable deterministic projection stage.

This module contains the retained year-by-year calculation body.  The public
``planning_engines.project`` function is intentionally a thin orchestrator, so
calculation ownership is outside the API facade and can be tested/imported as a
stage module.  Additional fine-grained stage files can replace pieces behind
this same contract without changing callers.
"""

from .amt_equity_comp_true_up import apply_amt_and_equity_comp_true_up as _apply_amt_and_equity_comp_true_up
from .appreciation_divorce_qlac import apply_appreciation_divorce_qlac as _apply_appreciation_divorce_qlac
from .deaths_and_spousal_rollover import (
    apply_deaths_and_filing_status as _apply_deaths_and_filing_status,
    apply_spousal_rollover_and_cst_funding as _apply_spousal_rollover_and_cst_funding,
)
from .budget_rollups import category_budget_rollup, housing_budget_rollup
from .cashflow_breakdown import compute_cashflow_breakdown as _compute_cashflow_breakdown
from .effective_marginal_rate import compute_effective_marginal_rate as _compute_effective_marginal_rate
from .home_sale import apply_home_sale as _apply_home_sale
from .income import apply_income as _apply_income
from .portfolio_growth_and_net_worth import apply_portfolio_growth_and_net_worth as _apply_portfolio_growth_and_net_worth
from .roth_conversion_and_agi_tax import apply_agi_and_tax as _apply_agi_and_tax
from .roth_conversion_and_agi_tax import apply_roth_conversion_stage as _apply_roth_conversion_stage
from .spending_and_rmd import apply_spending_and_rmd as _apply_spending_and_rmd
from .withdrawal_cascade_gap_assembly import apply_gap_assembly as _apply_gap_assembly
from .withdrawal_cascade_hsa_priority_draws import apply_hsa_priority_draws as _apply_hsa_priority_draws
from .withdrawal_cascade_taxable_trust import apply_taxable_trust_withdrawal as _apply_taxable_trust_withdrawal
from .withdrawal_cascade_ira_true_up import (
    apply_priority_3_pretax_elective as _apply_priority_3_pretax_elective,
    apply_priority_4b_final_pretax_draw as _apply_priority_4b_final_pretax_draw,
)
from .withdrawal_cascade_daf_makeup import apply_daf_carryforward_makeup as _apply_daf_carryforward_makeup
from .withdrawal_cascade_final_draws import apply_final_draws as _apply_final_draws
from .year_state import MutableYearState, create_initial_year_state
# System review 4.2: explicit name list instead of `from ..planning_engines
# import *` -- determined via AST analysis of every Name this module
# actually loads that isn't locally defined or otherwise imported, cross-
# checked against planning_engines' real exports (no ambiguous/unresolved
# names). Prerequisite for any future split of planning_engines.py: a
# reader (or refactoring tool) can now see the real dependency surface here
# instead of "everything, maybe."
from ..planning_engines import (
    EvDeath,
    EvIncome,
    EvTax,
    EvWarning,
    EvWithdraw,
    FEDERAL_BRACKETS_BASE_YEAR,
    FEDERAL_BRACKETS_MFJ,
    IRMAA_TIERS_BASE_YEAR,
    TAX_BASE_YEAR,
    ensure_engine_config,
    liquidity_buffer_years_for_year,
    marginal_rate,
    niit_tax,
    state_income_tax,
)
from .. import planning_engines as _legacy_pe
from .. import core as _ar  # consolidated from account_registry
from .. import core as _aa  # consolidated from account_access
from .. import tlh as _tlh
from .. import gain_harvest as _gh
from .. import tax_kernel as _tk
from ..equity_comp import equity_comp_year_events as _equity_comp_year_events
from ..core import state_for_year
from ..core import qlac_premium_limit

# withdrawal_engine/conversion_engine/inheritance_engine/growth_engine were
# consolidated into planning_engines.py itself; call sites below use
# _legacy_pe directly (system review 4.1) rather than four separate
# _we/_ce/_ie/_ge aliases that all pointed at the identical module -- the
# distinct names implied four separate collaborators that no longer exist
# and that no linter or refactoring tool could see were the same target.


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
    for _sk in ['wife_pension','wife_single','wife_joint','h_single','h_joint','h_qlac','wife_qlac']:
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
    cap_loss_carryforward = year_state.cap_loss_carryforward
    # Item 4.2 (P4): unused DAF-contribution deduction (the part of a year's
    # DAF gift that exceeded that year's AGI% limitation) carries forward for
    # up to 5 succeeding tax years (IRC 170(b)(1)(G)/(d)(1)). Each entry is
    # [origin_year, amount_remaining]; consumed oldest-first so the earliest
    # carryforward expires last among equals but nothing is used out of the
    # order it was generated.
    daf_deduction_carryforward: list = []
    # HSA expense-bank accumulation (optimization refactor, Option B):
    # cumulative substantiated unreimbursed qualified medical expense,
    # available to justify a tax-free HSA draw at any later date (the
    # "shoebox strategy" -- see docs/superpowers/plans/
    # 2026-08-26-hsa-expense-bank-and-double-dip-spec.md). Seeded from the
    # user's entered historical figure (blank means nothing entered yet, not
    # unlimited -- it accrues from here); grown every year by that year's
    # medical_expense_yr; drawn down by Priority 1b/4c's HSA draws, the two
    # sites that enforce it. Never reset across years.
    hsa_bank_balance = float(c.get('hsa_expense_bank')) if c.get('hsa_expense_bank') is not None else 0.0
    # Item 4.8 (P11): cumulative federal lifetime-exemption dollars consumed
    # by taxable gifts (amounts above the per-donee annual exclusion) made
    # during the plan so far. Reduces the exemption still available at
    # death (see sheets_strategy.py's build_sheet14 federal estate tax calc)
    # -- using exemption during life is the "unified credit" being unified.
    lifetime_exemption_used = 0.0

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

    # ── Survivor spending factor ────────────────────────────────────────────
    # A one-person household does not spend what a two-person household spends.
    # The factor applies to core spending and recurring extras (travel, large
    # discretionary) ONLY.
    #
    # Deliberately NOT scaled:
    #   * housing (mortgage/rent/operating/RE tax/HELOC/home improvement) —
    #     the survivor lives in the same house, so those costs do not halve;
    #   * wellness and LTC premiums — those are already built per person and
    #     drop on their own at the first death (~0.53 of the joint figure on
    #     the frozen fixture). Applying the factor on top would compound two
    #     reductions (0.53 x 0.65 ~ 0.34 of joint), which is wrong;
    #   * lumps and business expenses — neither is per-capita consumption.
    #
    # Guarded on household_size: a genuinely single-member plan has
    # w_death_yr forced to w_dob_yr ("already dead") so its w_alive is False
    # in every year. Without this guard such a household would look like a
    # permanent survivor and have its whole plan scaled, even though its
    # spend_base is already one person's spending.
    _survivor_factor_input = c.get('survivor_spend_factor', 0.65)
    try:
        _survivor_factor_input = float(_survivor_factor_input)
    except (TypeError, ValueError):
        _survivor_factor_input = 0.65
    _survivor_spend_factor = min(1.0, max(0.0, _survivor_factor_input))
    _household_is_couple = int(c.get('household_size', len(c.get('members') or []) or 1)) > 1

    # The second death is when the household ceases to exist. For a genuinely
    # single-member plan data_io forces w_death_yr into the past, so max() is
    # still that member's own death.
    _second_death_yr = max(int(c['h_death_yr']), int(c['w_death_yr']))

    def _survivor_factor(n_alive):
        """1.0 unless exactly one member of a couple is still alive.

        n_alive == 0 is deliberately left at 1.0 here: zeroing living
        expenses after the second death is Task S2's job, and returning a
        scale factor for it would be the wrong mechanism anyway.
        """
        if _household_is_couple and n_alive == 1:
            return _survivor_spend_factor
        return 1.0

    def _medicare_month_fraction(dob_yr, dob_month, year):
        """Fraction of `year` (0.0-1.0) a person is Medicare Part B/D enrolled.

        Convention: Medicare eligibility begins the first of the calendar
        month in which a person turns 65 (standard CMS enrollment rule). Age
        follows the engine's existing integer convention (year - dob_yr), so
        this only ever prorates the single transition year where that age
        first equals 65 — 0.0 in all earlier years, 1.0 in all later years,
        and (12 - (birth_month - 1)) / 12 in the turn-65 year itself.
        """
        try:
            age = int(year) - int(dob_yr)
        except Exception:
            return 0.0
        if age < 65:
            return 0.0
        if age > 65:
            return 1.0
        try:
            m = int(dob_month) if dob_month else 1
        except Exception:
            m = 1
        m = min(max(m, 1), 12)
        return (12 - (m - 1)) / 12.0

    def _wellness_premium_for_age(age, year, dob_month=1):
        """Return the annual per-person premium used for SEHI in this year.

        There is intentionally no standalone "health insurance premiums"
        input.  Before age 65, use Pre-65 Healthcare Premium; at 65+ use
        Medicare Part B + Part D + Part G costs. In the calendar year a
        person turns 65, both are prorated by month via
        `_medicare_month_fraction` (Medicare starts the 1st of the birth
        month) instead of switching on a hard binary age gate.
        """
        try:
            age = float(age)
        except Exception:
            age = 0.0
        dob_yr = year - age
        medicare_frac = _medicare_month_fraction(dob_yr, dob_month, year)
        pre65_frac = 1.0 - medicare_frac
        bridge = float(c.get('bridge_premium', 0.0) or 0.0) * _path_factor('medical_index_by_year', c.get('med_inf', c['inf']), year) * pre65_frac
        part_b = float(c.get('partb', 0.0) or 0.0) * 12 * _path_factor('medical_index_by_year', c.get('med_inf', c['inf']), year) * medicare_frac
        part_d = float(c.get('partd', 0.0) or 0.0) * 12 * _path_factor('partd_index_by_year', c.get('partd_inf', c.get('med_inf', c['inf'])), year) * medicare_frac
        part_g = float(c.get('partg', 0.0) or 0.0) * 12 * _path_factor('medical_index_by_year', c.get('med_inf', c['inf']), year) * medicare_frac
        return bridge + part_b + part_d + part_g

    def _sehi_deduction_source_amount(year, h_age, w_age, h_alive=True, w_alive=True):
        _sehi_override = c.get('sehi_user_override')
        if _sehi_override is not None:
            return max(0.0, float(_sehi_override))
        if c.get('sehi_derived_from_wellness', True):
            total = 0.0
            if h_alive:
                total += _wellness_premium_for_age(h_age, year, c.get('h_dob_month'))
            if w_alive:
                total += _wellness_premium_for_age(w_age, year, c.get('w_dob_month'))
            return max(0.0, total)
        return max(0.0, float(c.get('sehi', 0.0) or 0.0))

    def _infl_ratio(year, base_year):
        return _path_ratio('inflation_index_by_year', c['inf'], year, base_year)

    def _ss_ratio(year, claim_year):
        return _path_ratio('ss_cola_index_by_year', c['ss_cola'], year, claim_year)

    def _ss_first_claim_year_month_fraction(year, claim_year, dob_month):
        """Fraction of `year` (0.0-1.0) Social Security is actually payable.

        Wave 5 item W5-3 (finding N3, 2026-09-08 explicit direction):
        Social Security pays in ARREARS -- the check for a given month's
        entitlement arrives the following month -- unlike Medicare coverage
        (a genuine coverage-period concept correctly modeled as starting the
        1st of the entitlement month by _medicare_month_fraction). Reusing
        that same in-advance formula here was the root cause N3 identified:
        an entitlement in month M pays (12-M) months that calendar year, not
        (12-(M-1)) -- e.g. an August claim pays September-December (4
        months), not August-December (5). A December claim pays zero SS
        cash that calendar year (first check arrives the following January).
        Only the claim YEAR itself is ever partial; every later year is a
        full 12 months.
        """
        if year != claim_year:
            return 1.0
        try:
            m = int(dob_month) if dob_month else 1
        except Exception:
            m = 1
        m = min(max(m, 1), 12)
        return (12 - m) / 12.0

    def _bracket_factor_for_year(year):
        return _tk.bracket_factor_for_year(c, year)

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

    def _ira_elective_ordinary_tax_delta(fed_tax_base, state_tax_base, taxable_inc_base,
                                          retirement_dist_base, ira_wd_cumulative, year, filing,
                                          ss_taxable, earned_net, investment_inc, nonqual_ann,
                                          roth_conv, h_over_65):
        """Real incremental fed+state tax caused by `ira_wd_cumulative` of elective
        IRA/401(k) income, vs. the flat marginal-rate estimate baked into
        withdraw_pretax_elective's gross-up. `fed_tax_base`/`state_tax_base`/
        `taxable_inc_base` should be the values as of the last time this income
        was accounted for, so the return is the tax on just the newest increment.
        """
        if ira_wd_cumulative <= 1e-6:
            return 0.0, fed_tax_base, state_tax_base
        new_taxable_inc = taxable_inc_base + ira_wd_cumulative
        new_fed_tax = _compute_fed_tax_path(new_taxable_inc, year, filing, c['brk_inf'])
        new_state_tax = state_income_tax(
            state_for_year(c, year), earned_net, retirement_dist_base + ira_wd_cumulative, ss_taxable,
            investment_inc, nonqual_ann, roth_conv, year, h_over_65, filing=filing,
            brk_inf=c['brk_inf'],
        )
        delta = (new_fed_tax - fed_tax_base) + (new_state_tax - state_tax_base)
        return delta, new_fed_tax, new_state_tax

    def _standard_deduction_path(year, filing, brk_inf_unused=None, n_over_65=2):
        td = getattr(_ar, '_td', None)
        base = getattr(td, 'STANDARD_DEDUCTION_BASE_YEAR', {}).get(filing, 15750) if td else 15750
        add_per = getattr(td, 'STANDARD_DEDUCTION_OVER65_BASE_YEAR', {}).get(filing, 1650) if td else 1650
        return (base + add_per * n_over_65) * _bracket_factor_for_year(year)

    def _irmaa_factor_for_year(year):
        return _tk.irmaa_factor_for_year(c, year)

    def _irmaa_surcharge_path(agi, year, n_people, filing):
        return _tk.irmaa_surcharge(agi, year, n_people, filing, c)

    def _irmaa_tier_path(agi, year, filing):
        return _tk.irmaa_tier(agi, year, filing, c)

    def _ltcg_tax_on_gain_path(gain, ordinary_income, year):
        return _tk.ltcg_tax_on_gain(c, gain, ordinary_income, year)

    def _fra_for_birth_year(dob_year, fra_override=None):
        if fra_override and float(fra_override) > 0:
            return float(fra_override)
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

    def _ss_claim_factor(claim_age, dob_year, fra_override=None):
        # SSA reduction/credit factors relative to PIA at FRA.
        fra = _fra_for_birth_year(dob_year, fra_override)
        months = int(round((float(claim_age or fra) - fra) * 12))
        if months >= 0:
            return 1.0 + months * (0.08 / 12.0)
        early = abs(months)
        first36 = min(36, early) * (5.0 / 900.0)
        extra = max(0, early - 36) * (5.0 / 1200.0)
        return max(0.0, 1.0 - first36 - extra)

    def _ss_benefit_from_age70(monthly_at_70, claim_age, dob_year, fra_override=None):
        f70 = _ss_claim_factor(70, dob_year, fra_override) or 1.0
        return float(monthly_at_70 or 0.0) * (_ss_claim_factor(claim_age, dob_year, fra_override) / f70)

    def _ss_spousal_excess_factor(start_age, dob_year, fra_override=None):
        # Reduction schedule for the EXCESS SPOUSAL benefit, which differs from a
        # worker's own retirement reduction (_ss_claim_factor).  Per SSA the
        # excess spousal amount is reduced 25/36 of 1% per month for the first 36
        # months claimed before FRA, then 5/12 of 1% per month for any months
        # beyond 36.  Delayed retirement credits do NOT apply to the spousal
        # excess: claiming after FRA never grows it past the FRA-level amount, so
        # the factor is capped at 1.0.  `start_age` is the claimant's age when the
        # spousal benefit first becomes payable (the later of their own filing and
        # the worker's filing), relative to the claimant's own FRA.
        fra = _fra_for_birth_year(dob_year, fra_override)
        months = int(round((float(start_age or fra) - fra) * 12))
        if months >= 0:
            return 1.0
        early = abs(months)
        first36 = min(36, early) * (25.0 / 3600.0)
        extra = max(0, early - 36) * (5.0 / 1200.0)
        return max(0.0, 1.0 - first36 - extra)

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

    # Advanced planning modules (Phase 3 engine integration). Gated purely on the
    # saved optional-function toggles in c['opt'] — NOT on module_enabled()/the
    # FORCE_* env flags — so a default plan (all three off) projects identically
    # and golden masters never move, even under RETIREMENT_SYSTEM_FORCE_ALL_MODULES.
    _opt = c.get('opt') or {}
    _equity_on = bool(_opt.get('equity_compensation')) and bool(c.get('equity_comp'))
    _disability_on = bool(_opt.get('disability_income_insurance'))
    amt_credit_carry = 0.0  # ISO minimum-tax credit carried across years
    # Item 3.5 (F6): running state for the adoptable spending guardrail
    # policy (fixed_real/guyton_klinger/floor_ceiling_band), carried across
    # years by spending_guardrail_year -- {} on the first active year.
    _spend_guardrail_state: dict = {}
    # Item 3.6 (F5): rolling 3-calendar-year window of gift_total_yr, for New
    # York's 3-year gift add-back (NY Tax Law Β§954(a)(3) -- gifts made within
    # 3 years of death are added back into the NY gross estate even though
    # federal law no longer adds them back). A plain list capped at 3 entries
    # -- this year plus the two before it -- rather than a full rows scan,
    # since only the terminal (death) year's row ever reads it.
    _recent_gift_totals: list = []

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

        # ── Deaths / filing status (extracted stage) ─────────────────────────
        # filing/first_death_done are multi-year state: seeded once before
        # the loop from year_state, then carried and reassigned across every
        # iteration. Python does not mutate a caller's local through a
        # function parameter, so the updated values must come back via the
        # return value and be reassigned here -- NOT dropped, or every later
        # year silently keeps the pre-death filing status. See
        # deaths_and_spousal_rollover.py's Stage1Result docstring.
        _stage1 = _apply_deaths_and_filing_status(
            c,
            year=year,
            filing=filing,
            first_death_done=first_death_done,
        )
        h_alive = _stage1.h_alive
        w_alive = _stage1.w_alive
        n_alive = _stage1.n_alive
        filing = _stage1.filing
        first_death_done = _stage1.first_death_done
        row['h_alive'] = h_alive
        row['w_alive'] = w_alive
        row['filing'] = filing

        # ── Spousal rollover & CST funding (extracted stage) ─────────────────
        # cst_balance/cst_funded_total are multi-year state, same care as
        # filing/first_death_done above -- see Stage2Result's docstring.
        _stage2 = _apply_spousal_rollover_and_cst_funding(
            c,
            year=year,
            h_alive=h_alive,
            w_alive=w_alive,
            bal=bal,
            bal_basis_free=bal_basis_free,
            cst_balance=cst_balance,
            cst_funded_total=cst_funded_total,
            account_transfers_in=row['_account_transfers_in'],
            account_transfers_out=row['_account_transfers_out'],
            emit=emit,
        )
        cst_balance = _stage2.cst_balance
        cst_funded_total = _stage2.cst_funded_total
        spousal_rollover = _stage2.spousal_rollover
        estate_trust = _stage2.estate_trust
        cst_funded_yr = _stage2.cst_funded_yr
        row['spousal_rollover'] = spousal_rollover
        row['estate_trust'] = estate_trust
        row['cst_funded_yr'] = cst_funded_yr
        row['cst_excluded_from_survivor_estate'] = cst_funded_total

        # ── Appreciation / Divorce / QLAC (extracted stage) ──────────────────
        # Grow CST/startup equity, depreciate autos, apply the year's
        # one-time divorce split and QLAC premium withdrawal. See
        # appreciation_divorce_qlac.py for the full per-event breakdown.
        # cst_balance/startup/autos_val are plain floats: Python does not
        # mutate a caller's local through a function parameter, so the
        # updated values must come back via the return value and be
        # reassigned here -- NOT dropped. bal and the account-flow dicts
        # mutate in place through the reference, same as any dict.
        _stage3 = _apply_appreciation_divorce_qlac(
            c,
            year=year,
            h_alive=h_alive,
            w_alive=w_alive,
            bal=bal,
            cst_balance=cst_balance,
            startup=startup,
            account_deposits=row['_account_deposits'],
            account_deposit_sources=row['_account_deposit_sources'],
            account_transfers_out=row['_account_transfers_out'],
            account_withdrawals=row['_account_withdrawals'],
        )
        cst_balance = _stage3.cst_balance
        startup = _stage3.startup
        autos_val = _stage3.autos_val
        row['cst_balance'] = _stage3.cst_balance
        row['startup_sale_proceeds'] = _stage3.startup_sale_proceeds
        row['divorce_split_amount'] = _stage3.divorce_split_amount
        row['qlac_purchase_yr'] = _stage3.qlac_purchase_yr

        # ── Home value appreciation & planned sale (extracted stage) ─────────
        # Appreciate or sell the home, pay off HELOC/mortgage at sale, and
        # route sale proceeds. See home_sale.py for the full step-by-step
        # breakdown and for why report fields are written directly onto
        # `row` (in place) rather than bundled into the return value: the
        # legacy engine sets a different subset of row keys depending on
        # which branch runs, and the full-row snapshot regression test
        # pins that exact key set. home_val/home_equity/mort_bal_yr ARE
        # plain floats returned via HomeSaleResult and must be reassigned
        # here -- same caveat as the appreciation/divorce/QLAC stage above.
        _stage4 = _apply_home_sale(
            c,
            row,
            year=year,
            home_val=home_val,
            filing=filing,
            second_death_yr=_second_death_yr,
            bal=bal,
            bal_basis_free=bal_basis_free,
            emit=emit,
        )
        home_val = _stage4.home_val
        home_equity = _stage4.home_equity
        mort_bal_yr = _stage4.mort_bal_yr

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

        # ── Income (extracted stage) ─────────────────────────────────────────
        # Earned/payroll/401k/HSA-contrib/Social Security/annuity/note income.
        # See income.py for the full per-topic breakdown. earned_base and the
        # sixteen other returned locals are read as bare names by later
        # stages this same iteration (spending, Roth sizing, AGI/tax, the
        # withdrawal cascade, the equity-comp/AMT post-pass) -- Python does
        # not propagate a reassigned scalar parameter back to the caller, so
        # they must come back via the return value and be reassigned here,
        # NOT dropped. bal and row mutate in place through the reference,
        # same as any dict.
        _stage5 = _apply_income(
            c,
            year=year,
            h_age=h_age,
            w_age=w_age,
            h_alive=h_alive,
            w_alive=w_alive,
            bal=bal,
            row=row,
            note_princ_yr=note_princ_yr,
            note_int_yr=note_int_yr,
            equity_on=_equity_on,
            disability_on=_disability_on,
            sehi_deduction_source_amount=_sehi_deduction_source_amount,
            ss_ratio=_ss_ratio,
            ss_first_claim_year_month_fraction=_ss_first_claim_year_month_fraction,
            ss_claim_factor=_ss_claim_factor,
            ss_spousal_excess_factor=_ss_spousal_excess_factor,
            ss_funding_factor=_ss_funding_factor,
        )
        earned_base = _stage5.earned_base
        net_earned_taxable = _stage5.net_earned_taxable
        half_se_ded = _stage5.half_se_ded
        sehi_ded = _stage5.sehi_ded
        qbi_ded = _stage5.qbi_ded
        payroll_tax = _stage5.payroll_tax
        business_expenses_yr = _stage5.business_expenses_yr
        h_ss = _stage5.h_ss
        w_ss = _stage5.w_ss
        pension = _stage5.pension
        wife_single_ann = _stage5.wife_single_ann
        wife_joint_ann = _stage5.wife_joint_ann
        h_single_ann = _stage5.h_single_ann
        h_joint_ann = _stage5.h_joint_ann
        _equity_events = _stage5.equity_events
        _di_taxable = _stage5.di_taxable
        _di_cash = _stage5.di_cash
        if earned_base > 0:
            emit(EvIncome(year, 'earned', earned_base, c['entity']))

        # ── Spending + RMD sizing/application (design doc Stages 6+7, merged) ──
        # These were split by ~270 lines in the legacy engine (RMD sizing feeds
        # QCD, which feeds total_spend_need, before RMD application finally
        # ran); see spending_and_rmd.py's module docstring for why they are
        # now one extracted function/module instead, and why the internal
        # statement order is preserved exactly rather than reordered.
        _spending_rmd = _apply_spending_and_rmd(
            c, year=year, h_age=h_age, w_age=w_age, h_alive=h_alive, w_alive=w_alive,
            n_alive=n_alive, filing=filing, bal=bal, row=row,
            net_earned_taxable=net_earned_taxable, half_se_ded=half_se_ded, sehi_ded=sehi_ded,
            pension=pension, wife_single_ann=wife_single_ann, wife_joint_ann=wife_joint_ann,
            h_single_ann=h_single_ann, h_joint_ann=h_joint_ann, note_int_yr=note_int_yr,
            h_ss=h_ss, w_ss=w_ss, business_expenses_yr=business_expenses_yr,
            lifetime_exemption_used=lifetime_exemption_used,
            spend_guardrail_state=_spend_guardrail_state,
            recent_gift_totals=_recent_gift_totals,
            spending_factor=_spending_factor, survivor_factor=_survivor_factor,
            infl_factor=_infl_factor, infl_ratio=_infl_ratio, path_factor=_path_factor,
            next_housing_for_year=_next_housing_for_year,
            medicare_month_fraction=_medicare_month_fraction,
            taxable_portfolio_income_for_year=_taxable_portfolio_income_for_year,
            emit=emit,
        )
        # Multi-year state: must be reassigned here, not just read, so next
        # year's call sees this year's update (same reasoning as Stage 3's
        # cst_balance/startup -- see Stage3Result's docstring).
        lifetime_exemption_used = _spending_rmd.lifetime_exemption_used
        _spend_guardrail_state = _spending_rmd.spend_guardrail_state
        # This-year outputs read by later stages (withdrawal cascade, Stage 9's
        # ACA/wellness patch, Roth conversion planner, spending-tier reporting).
        total_spend_need = _spending_rmd.total_spend_need
        spend = _spending_rmd.spend
        rec_extra = _spending_rmd.rec_extra
        lump_yr = _spending_rmd.lump_yr
        mort_yr = _spending_rmd.mort_yr
        re_tax_yr = _spending_rmd.re_tax_yr
        rent_yr = _spending_rmd.rent_yr
        housing_operating_yr = _spending_rmd.housing_operating_yr
        ltc_prem_yr = _spending_rmd.ltc_prem_yr
        business_expenses_yr = _spending_rmd.business_expenses_yr
        rmd_h = _spending_rmd.rmd_h
        rmd_w = _spending_rmd.rmd_w
        rmd_taxable_total = _spending_rmd.rmd_taxable_total
        heloc_interest_yr = _spending_rmd.heloc_interest_yr
        heloc_repayment_principal_yr = _spending_rmd.heloc_repayment_principal_yr
        heloc_draw_yr = _spending_rmd.heloc_draw_yr
        bridge_people = _spending_rmd.bridge_people
        bridge_premium_gross = _spending_rmd.bridge_premium_gross
        bridge_premium_yr = _spending_rmd.bridge_premium_yr
        aca_ptc_pre_conversion = _spending_rmd.aca_ptc_pre_conversion
        aca_ptc_yr = _spending_rmd.aca_ptc_yr
        partb_yr = _spending_rmd.partb_yr
        partd_yr = _spending_rmd.partd_yr
        partg_yr = _spending_rmd.partg_yr
        medicare_fraction_people = _spending_rmd.medicare_fraction_people
        h_medicare_frac = _spending_rmd.h_medicare_frac
        w_medicare_frac = _spending_rmd.w_medicare_frac
        wellness_shock_yr = _spending_rmd.wellness_shock_yr
        wellness_base_yr = _spending_rmd.wellness_base_yr
        wellness_premium_yr = _spending_rmd.wellness_premium_yr
        wellness_transaction_premium_yr = _spending_rmd.wellness_transaction_premium_yr
        wellness_detail_budget_yr = _spending_rmd.wellness_detail_budget_yr
        wellness_medical_yr = _spending_rmd.wellness_medical_yr
        wellness_dental_yr = _spending_rmd.wellness_dental_yr
        wellness_vision_yr = _spending_rmd.wellness_vision_yr
        wellness_rx_otc_yr = _spending_rmd.wellness_rx_otc_yr
        wellness_other_yr = _spending_rmd.wellness_other_yr
        portfolio_ordinary = _spending_rmd.portfolio_ordinary
        portfolio_qualified = _spending_rmd.portfolio_qualified
        portfolio_tax_exempt = _spending_rmd.portfolio_tax_exempt
        qcd_total_yr = _spending_rmd.qcd_total_yr
        daf_contrib_yr = _spending_rmd.daf_contrib_yr
        daf_gift_requested = _spending_rmd.daf_gift_requested
        daf_is_inkind = _spending_rmd.daf_is_inkind
        daf_grant_yr = _spending_rmd.daf_grant_yr

        # ── Roth Conversions (design doc Stage 8, extracted) ────────────────
        # See roth_conversion_and_agi_tax.py's apply_roth_conversion_stage
        # docstring for why the DAF in-kind gift is bundled into the same
        # function/call.
        _stage8 = _apply_roth_conversion_stage(
            c, bal, bal_basis_free, row,
            year=year, filing=filing, h_age=h_age, w_age=w_age,
            earned_base=earned_base, net_earned_taxable=net_earned_taxable,
            half_se_ded=half_se_ded, sehi_ded=sehi_ded, h_ss=h_ss, w_ss=w_ss,
            rmd_taxable_total=rmd_taxable_total, pension=pension,
            wife_single_ann=wife_single_ann, wife_joint_ann=wife_joint_ann,
            h_single_ann=h_single_ann, h_joint_ann=h_joint_ann,
            note_int_yr=note_int_yr, note_princ_yr=note_princ_yr,
            total_spend_need=total_spend_need, spend=spend,
            portfolio_ordinary=portfolio_ordinary, portfolio_qualified=portfolio_qualified,
            portfolio_tax_exempt=portfolio_tax_exempt, bridge_people=bridge_people,
            daf_is_inkind=daf_is_inkind, daf_gift_requested=daf_gift_requested,
            daf_contrib_yr=daf_contrib_yr,
            inflate_brackets_fn=_inflate_brackets_path, standard_deduction_fn=_standard_deduction_path,
            compute_fed_tax_fn=_compute_fed_tax_path, emit=emit,
        )
        roth_conv = _stage8.roth_conv
        daf_contrib_yr = _stage8.daf_contrib_yr

        # ── AGI / Tax (design doc Stage 9, extracted) ────────────────────────
        # See roth_conversion_and_agi_tax.py's apply_agi_and_tax docstring:
        # total_tax (and the agi/taxable_inc/fed_tax/state_tax it is built
        # from) is provisional here -- the still-inline withdrawal cascade
        # below both mutates agi/taxable_inc further and finalizes total_tax
        # only after its own LTCG/NIIT fixed point converges.
        _stage9 = _apply_agi_and_tax(
            c, bal, row, rows,
            year=year, filing=filing, h_age=h_age, w_age=w_age, n_alive=n_alive,
            home_val=home_val, payroll_tax=payroll_tax,
            net_earned_taxable=net_earned_taxable, half_se_ded=half_se_ded, sehi_ded=sehi_ded,
            rmd_taxable_total=rmd_taxable_total, roth_conv=roth_conv, pension=pension,
            wife_single_ann=wife_single_ann, wife_joint_ann=wife_joint_ann,
            h_single_ann=h_single_ann, h_joint_ann=h_joint_ann, h_ss=h_ss, w_ss=w_ss,
            note_int_yr=note_int_yr, portfolio_ordinary=portfolio_ordinary,
            portfolio_qualified=portfolio_qualified, portfolio_tax_exempt=portfolio_tax_exempt,
            equity_events=_equity_events, di_taxable=_di_taxable, qbi_ded=qbi_ded,
            bridge_people=bridge_people, aca_ptc_pre_conversion=aca_ptc_pre_conversion,
            aca_ptc_yr=aca_ptc_yr, bridge_premium_gross=bridge_premium_gross,
            partb_yr=partb_yr, partd_yr=partd_yr, partg_yr=partg_yr,
            wellness_transaction_premium_yr=wellness_transaction_premium_yr,
            wellness_detail_budget_yr=wellness_detail_budget_yr,
            wellness_premium_yr=wellness_premium_yr, wellness_base_yr=wellness_base_yr,
            total_spend_need=total_spend_need,
            spend=spend, rec_extra=rec_extra, lump_yr=lump_yr, mort_yr=mort_yr,
            rent_yr=rent_yr, housing_operating_yr=housing_operating_yr, re_tax_yr=re_tax_yr,
            ltc_prem_yr=ltc_prem_yr, wellness_shock_yr=wellness_shock_yr,
            heloc_interest_yr=heloc_interest_yr, heloc_repayment_principal_yr=heloc_repayment_principal_yr,
            business_expenses_yr=business_expenses_yr,
            wellness_medical_yr=wellness_medical_yr, wellness_dental_yr=wellness_dental_yr,
            wellness_vision_yr=wellness_vision_yr, wellness_rx_otc_yr=wellness_rx_otc_yr,
            wellness_other_yr=wellness_other_yr, qcd_total_yr=qcd_total_yr, daf_grant_yr=daf_grant_yr,
            daf_contrib_yr=daf_contrib_yr, daf_deduction_carryforward=daf_deduction_carryforward,
            medicare_fraction_people=medicare_fraction_people, h_medicare_frac=h_medicare_frac,
            w_medicare_frac=w_medicare_frac,
            standard_deduction_fn=_standard_deduction_path, compute_fed_tax_fn=_compute_fed_tax_path,
            irmaa_surcharge_fn=_irmaa_surcharge_path, irmaa_tier_fn=_irmaa_tier_path, emit=emit,
        )
        # Multi-year state: must be reassigned here, same reasoning as every
        # other cross-year local in this loop (Stage 3's cst_balance/startup,
        # Stage 6's lifetime_exemption_used/spend_guardrail_state, ...).
        daf_deduction_carryforward = _stage9.daf_deduction_carryforward
        # This-year outputs read by the still-inline withdrawal cascade
        # (agi/taxable_inc/fed_tax/state_tax/total_tax/... are re-mutated
        # there as its elective-withdrawal sizing loop and LTCG/NIIT fixed
        # point run), by the already-extracted Stage 11 (AMT/equity-comp)
        # and Stage 12 (effective marginal rate) which run after it, and by
        # the still-inline DAF-carryforward make-up pass further down.
        total_spend_need = _stage9.total_spend_need
        ss_taxable = _stage9.ss_taxable
        ss_total = _stage9.ss_total
        agi = _stage9.agi
        taxable_inc = _stage9.taxable_inc
        fed_tax = _stage9.fed_tax
        state_tax = _stage9.state_tax
        niit = _stage9.niit
        irmaa_yr = _stage9.irmaa_yr
        irmaa_magi = _stage9.irmaa_magi
        irmaa_magi_current = _stage9.irmaa_magi_current
        n_medicare = _stage9.n_medicare
        total_tax_pre_niit = _stage9.total_tax_pre_niit
        total_tax = _stage9.total_tax
        std_ded = _stage9.std_ded
        item_ded = _stage9.item_ded
        medical_ded = _stage9.medical_ded
        medical_expense_yr = _stage9.medical_expense_yr
        ded = _stage9.ded
        char = _stage9.char
        daf_agi_limit_pct = _stage9.daf_agi_limit_pct
        daf_agi_limit = _stage9.daf_agi_limit
        daf_deduction_yr = _stage9.daf_deduction_yr
        retirement_dist = _stage9.retirement_dist
        earned_net = _stage9.earned_net
        nonqual_ann = _stage9.nonqual_ann
        h_over_65 = _stage9.h_over_65
        home_sale_ltcg_gain = _stage9.home_sale_ltcg_gain
        home_sale_ltcg_tax = _stage9.home_sale_ltcg_tax
        gross_income = _stage9.gross_income
        net_income = _stage9.net_income

        # ── Apply Trust portfolio growth BEFORE withdrawal cascade ────────────
        # (Trust growth is now applied at end-of-year with all other accounts below)

        # ── Spending gap and withdrawal cascade (design doc Stage 10, sub-stage #0) ──
        other_cash_need_yr = float(row.get('other_cash_need_yr', 0.0) or 0.0)
        gap = _apply_gap_assembly(
            c, bal, row,
            year=year, h_ss=h_ss, w_ss=w_ss, pension=pension,
            wife_single_ann=wife_single_ann, wife_joint_ann=wife_joint_ann,
            h_single_ann=h_single_ann, h_joint_ann=h_joint_ann,
            note_princ_yr=note_princ_yr, note_int_yr=note_int_yr,
            rmd_taxable_total=rmd_taxable_total, earned_base=earned_base,
            equity_events=_equity_events, di_cash=_di_cash,
            total_spend_need=total_spend_need, total_tax=total_tax,
            other_cash_need_yr=other_cash_need_yr, rec_extra=rec_extra, lump_yr=lump_yr,
            heloc_draw_yr=heloc_draw_yr, heloc_interest_yr=heloc_interest_yr,
            heloc_repayment_principal_yr=heloc_repayment_principal_yr,
        )

        # ── Withdrawal Cascade — order matches client_data.csv Withdrawal Policy ──
        # Priority 1: RMD  (handled above, already applied to income)
        # Priority 2: HSA  (scheduled window draw, not gap-dependent)
        # Priority 3: IRA elective (gross-up; draws down pre-tax before forced RMDs grow)
        # Priority 4: Taxable/trust (above reserve floor; pro-rata by spouse/member)
        # Priority 5: Roth (tax-free last resort; maximise tax-free growth)
        # Priority 6: Home equity tap

        buf_yrs = liquidity_buffer_years_for_year(c, year)

        # ── Priorities 1b + 2: HSA priority draws (design doc Stage 10, sub-stages #1-#2) ──
        _hsa_priority = _apply_hsa_priority_draws(
            c, bal, row,
            year=year, medical_expense_yr=medical_expense_yr,
            hsa_bank_balance=hsa_bank_balance, gap=gap, spend=spend,
        )
        gap = _hsa_priority.gap
        hsa_bank_balance = _hsa_priority.hsa_bank_balance
        cl_hsa_wd = _hsa_priority.cl_hsa_wd
        hsa_wd = _hsa_priority.hsa_wd

        # ── No double benefit: HSA-reimbursed medical is not also deductible ─
        # A qualified medical expense cannot both be reimbursed tax-free from
        # the HSA and deducted on Schedule A. `medical_expense_yr` above was
        # computed from the full medical spend with no reduction for HSA
        # dollars, so every HSA withdrawal was silently taking both benefits.
        # Measured on the frozen fixture before this fix: all 123,301.40 of
        # lifetime HSA withdrawals were also clearing the 7.5%-of-AGI floor.
        #
        # Placed HERE -- after Priority 2, before Priority 3 -- because this
        # correction INCREASES tax, so the gap grows and the REST OF THE
        # CASCADE MUST STILL BE ABLE TO FUND IT IN ORDER.
        #
        # An earlier version sat after Priority 4c, on the reasoning that
        # `hsa_wd` is not final until 4c's gap-fill has run. That was wrong,
        # and `test_recommendations_functional.py::
        # test_fixed_point_taxable_withdrawal_solver_runs_before_roth` caught
        # it: adding tax demand after 3/4b/4c leaves only Roth to fund it, so
        # the plan drew Roth while pre-tax and HSA balances still remained --
        # 10 violations of the cascade's Roth-last invariant. Correctness of
        # the withdrawal ORDER outranks capturing every last netted dollar.
        #
        # The trade that buys: only the draws known by this point are netted --
        # Priority 1b's contingent-liability draw (which exists precisely to
        # pay qualified medical) and Priority 2's scheduled window draw.
        # Priority 4c's gap-fill is excluded. That is defensible on the merits
        # rather than merely convenient: 4c is a last-resort liquidity draw
        # against a general cash shortfall, not a reimbursement of that year's
        # medical spend. It also errs conservative -- it nets less, so the
        # correction is never more aggressive than the evidence supports.
        #
        # (The DAF re-deduction block later in this function is the same shape
        # with the opposite sign. It only ever LOWERS tax, which is why it can
        # safely sit after the draws: a shrinking gap needs no funding.)
        #
        # Only the DEDUCTION is corrected. The medical spend itself is a real
        # cash cost and `total_spend`/`row['wellness_*']` are untouched: this
        # changes what is deductible, not what is spent.
        _hsa_reimbursed = min(max(0.0, hsa_wd), max(0.0, medical_expense_yr))
        if _hsa_reimbursed > 1e-6 and medical_ded > 1e-6:
            # Net the reimbursed dollars out of the DEDUCTION directly rather
            # than re-deriving `max(0, net_medical - 0.075*agi)` here.
            #
            # The two are algebraically identical while the deduction is above
            # the floor AND `agi` is the same at both points -- and on the
            # frozen fixture's own configuration they are: both forms produce
            # byte-identical pins, so no test here distinguishes them. They
            # diverge only where `agi` has been mutated between the deduction
            # (computed early, off first-pass agi) and this correction
            # (post-cascade); measured under a `roth_policy='none'`
            # configuration, re-deriving stripped 18,439 against a 10,168
            # reimbursement in one year.
            #
            # Netting directly is preferred anyway because it inherits
            # whatever floor the engine already applied instead of silently
            # re-basing it. Whether that floor should use first-pass or
            # converged AGI is a real question, and a separate one from the
            # double benefit this block exists to correct.
            _new_medical_ded = max(0.0, medical_ded - _hsa_reimbursed)
            _medical_ded_lost = medical_ded - _new_medical_ded
            if _medical_ded_lost > 1e-6:
                _cand_item_ded = item_ded - _medical_ded_lost
                # std-vs-itemized is re-evaluated: a household pushed below the
                # standard deduction by this correction takes the standard one,
                # which caps the damage at (item_ded - std_ded) rather than the
                # full lost medical deduction.
                _new_ded = max(std_ded, _cand_item_ded + (qbi_ded if c['qbi_elig'] else 0.0))
                _new_taxable_inc = max(0.0, agi - _new_ded)
                _new_fed_tax = _compute_fed_tax_path(_new_taxable_inc, year, filing, c['brk_inf'])
                _fed_tax_extra = max(0.0, _new_fed_tax - fed_tax)
                fed_tax = _new_fed_tax
                taxable_inc = _new_taxable_inc
                # Update the PRE-NIIT subtotal, not `total_tax` directly.
                # `total_tax` is rebuilt from scratch further down
                # (`total_tax_pre_niit + ltcg_tax + niit - tlh_ordinary_credit`),
                # so a direct `total_tax += ...` here is silently discarded
                # while the `fed_tax` change survives -- leaving the two
                # disagreeing. That showed up as a 178.21 cash-flow
                # reconciliation residual in
                # test_cashflow_breakdown_single_source_of_truth.py, with the
                # breakdown's `other` remainder absorbing exactly the gap.
                # Recomputing the subtotal from its own components is the
                # idiom the engine already uses at its other two update sites.
                total_tax_pre_niit = fed_tax + state_tax + payroll_tax + irmaa_yr
                total_tax = total_tax_pre_niit + home_sale_ltcg_tax
                gap += _fed_tax_extra
                item_ded = _cand_item_ded
                ded = _new_ded
                medical_ded = _new_medical_ded
                row['medical_expense_deduction'] = medical_ded
                row['medical_expense_hsa_reimbursed'] = _hsa_reimbursed
                row['taxable_inc'] = taxable_inc
                row['fed_tax'] = fed_tax
                row['total_tax'] = total_tax
                row['net_income'] = row.get('gross_income', agi) - total_tax
                row['total_cash_need'] = total_spend_need + total_tax + other_cash_need_yr

        # ── Priority 3: Pre-tax elective withdrawal (design doc Stage 10, sub-stage #4) ──
        _priority3 = _apply_priority_3_pretax_elective(
            c, bal, row,
            year=year, filing=filing, gap=gap, agi=agi, taxable_inc=taxable_inc,
            fed_tax=fed_tax, state_tax=state_tax, payroll_tax=payroll_tax, irmaa_yr=irmaa_yr,
            total_tax_pre_niit=total_tax_pre_niit, irmaa_magi_current=irmaa_magi_current,
            retirement_dist=retirement_dist, rmd_h=rmd_h, rmd_w=rmd_w, spend=spend,
            ss_taxable=ss_taxable, earned_net=earned_net, note_int_yr=note_int_yr,
            portfolio_ordinary=portfolio_ordinary, portfolio_qualified=portfolio_qualified,
            nonqual_ann=nonqual_ann, roth_conv=roth_conv, h_over_65=h_over_65,
            brk_inf=c['brk_inf'], inflate_brackets_fn=_inflate_brackets_path,
            ira_elective_tax_delta_fn=_ira_elective_ordinary_tax_delta,
        )
        gap = _priority3.gap
        agi = _priority3.agi
        taxable_inc = _priority3.taxable_inc
        fed_tax = _priority3.fed_tax
        state_tax = _priority3.state_tax
        total_tax_pre_niit = _priority3.total_tax_pre_niit
        irmaa_magi_current = _priority3.irmaa_magi_current
        ira_wd = _priority3.ira_wd
        h_ira_elective = _priority3.h_ira_elective
        w_ira_elective = _priority3.w_ira_elective
        pretax_by_account = _priority3.pretax_by_account
        ira_tax_true_up_iterations = _priority3.ira_tax_true_up_iterations
        # Reused unchanged by Priority 4b (sub-stage #7) below -- only ever
        # computed here, when this sub-stage's own `gap > 0` guard fires.
        top_24_yr = _priority3.top_24_yr
        irmaa_thr_yr = _priority3.irmaa_thr_yr
        marg = _priority3.marg
        _ira_taxable_inc_orig = _priority3.ira_taxable_inc_orig
        _ira_retirement_dist_orig = _priority3.ira_retirement_dist_orig

        # ── Priority 4: Taxable/trust withdrawal (design doc Stage 10, sub-stage #5) ──
        _taxable_trust = _apply_taxable_trust_withdrawal(
            c, bal, row, year=year, gap=gap, spend=spend, emit=emit,
        )
        gap = _taxable_trust.gap
        trust_wd = _taxable_trust.trust_wd
        ht_wd = _taxable_trust.ht_wd
        wt_wd = _taxable_trust.wt_wd
        trust_by_account = _taxable_trust.trust_by_account

        # ── LTCG/NIIT fixed-point funding on taxable withdrawals ────────────
        # A taxable draw can create LTCG and NIIT; paying those taxes can in turn
        # require another taxable draw.  Earlier versions added the first LTCG/
        # NIIT result to the gap and let the next bucket fund it, which subtly
        # shifted depletion into pre-tax/Roth.  This bounded loop re-solves the
        # taxable-draw/investment-tax coupling before moving on.
        ltcg_tax = home_sale_ltcg_tax; ltcg_gain = home_sale_ltcg_gain
        investment_tax_iterations = 0
        investment_tax_funded_by_taxable = 0.0

        # ── Tax-loss harvesting (apply mode) ───────────────────────────────
        # Harvest qualifying loss lots in taxable accounts: realize the loss now
        # and reset each lot's basis to market with a current-year acquisition
        # date. That single mutation models buying an equivalent replacement —
        # a lower basis (so a larger future gain), a fresh holding-period clock,
        # and no re-harvesting of the same lot next year. A transaction cost is
        # charged against the account balance. The realized loss offsets this
        # year's gains first, then up to $3k of ordinary income, with the
        # remainder rolling into cap_loss_carryforward for future years.
        harvested_loss = 0.0
        tlh_txn_cost = 0.0
        if str(c.get('tlh_policy', 'off')).lower() == 'apply':
            _tlh_bps = float(c.get('tlh_transaction_cost_bps', 0.0) or 0.0) / 10000.0
            for _cand in _tlh.select_harvest_lots(
                c, year,
                min_loss_dollars=float(c.get('tlh_min_loss_dollars', 500.0) or 0.0),
                min_loss_pct=float(c.get('tlh_min_loss_pct', 0.05) or 0.0),
                annual_ceiling=float(c.get('tlh_annual_ceiling', 0.0) or 0.0),
            ):
                _lot = _cand['lot']
                harvested_loss += _cand['loss']
                _cost = _cand['market_value'] * _tlh_bps
                tlh_txn_cost += _cost
                _lot.cost_basis = _cand['market_value']
                _lot.purchase_date = f'{year}-01-01'
                _acct = _cand['account']
                bal[_acct] = max(0.0, float(bal.get(_acct, 0.0) or 0.0) - _cost)
        row['tlh_harvested_loss'] = harvested_loss
        row['tlh_transaction_cost'] = tlh_txn_cost
        # Loss pool available to offset gains this year: prior-year carryforward
        # plus anything harvested this year.
        available_losses = cap_loss_carryforward + harvested_loss

        # ── 0%-bracket gain harvesting (apply mode) ─────────────────────────
        # Symmetric counterpart to TLH above (system review 2026-07-21, P2):
        # realize appreciated long-term lots up to the remaining 0%-LTCG-
        # bracket headroom, resetting basis to market value tax-free. Same
        # single-mutation technique as TLH (reset cost_basis + purchase_date),
        # but with no replacement-security logic -- wash-sale rules disallow
        # claiming a *loss* on a repurchased "substantially identical"
        # security; they have no counterpart for gains, so the exact same
        # security can be repurchased instantly with no tax consequence.
        # headroom is computed from `taxable_inc` (set above, already
        # reflecting this year's Roth conversion decision), so this can never
        # double-book the same ordinary-income bracket space the Roth
        # conversion guardrail already consumed.
        gain_harvest_realized = 0.0
        gain_harvest_txn_cost = 0.0
        if str(c.get('gain_harvest_policy', 'off')).lower() == 'apply':
            _gh_bps = float(c.get('gain_harvest_transaction_cost_bps', 0.0) or 0.0) / 10000.0
            _gh_bracket_factor = _bracket_factor_for_year(year)
            _gh_headroom = _gh.compute_zero_bracket_headroom(
                c.get('ltcg_0_top', 0.0), _gh_bracket_factor, taxable_inc,
            )
            for _cand in _gh.select_gain_harvest_lots(
                c, year, headroom=_gh_headroom,
                min_gain_dollars=float(c.get('gain_harvest_min_gain_dollars', 500.0) or 0.0),
                min_gain_pct=float(c.get('gain_harvest_min_gain_pct', 0.0) or 0.0),
            ):
                _lot = _cand['lot']
                gain_harvest_realized += _cand['gain']
                _cost = _cand['market_value'] * _gh_bps
                gain_harvest_txn_cost += _cost
                _lot.cost_basis = _cand['market_value']
                _lot.purchase_date = f'{year}-01-01'
                _acct = _cand['account']
                bal[_acct] = max(0.0, float(bal.get(_acct, 0.0) or 0.0) - _cost)
        row['gain_harvest_realized'] = gain_harvest_realized
        row['gain_harvest_transaction_cost'] = gain_harvest_txn_cost

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
            # Capital losses (carryforward + harvested) offset realized gains
            # before any LTCG/NIIT is due.
            net_gain = max(0.0, ltcg_gain - available_losses)
            new_ltcg_tax = _ltcg_tax_on_gain_path(net_gain, max(0, taxable_inc), year) if net_gain > 0 else 0.0
            delta_ltcg = max(0.0, new_ltcg_tax - ltcg_tax)
            ltcg_tax = new_ltcg_tax
            delta_niit = 0.0
            if c['model_niit']:
                # Keep the engine's existing MAGI convention but recompute on
                # cumulative NII as additional taxable withdrawals are made.
                new_niit = niit_tax(base_nii_without_ltcg + net_gain, agi, filing)
                delta_niit = max(0.0, new_niit - niit)
                niit = new_niit
            return delta_ltcg + delta_niit

        if ltcg_gain > 0 or available_losses > 0:
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
            add_res = _legacy_pe.withdraw_taxable_trust(c, bal, year, gap, spend)
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

        # ── Capital-loss waterfall settle-up ───────────────────────────────
        # The gain-offset portion is already reflected in ltcg_tax/niit above.
        # Whatever loss remains offsets up to $3,000 of ordinary income (valued
        # at the federal marginal rate) and the rest rolls forward.
        _used_vs_gain = min(available_losses, max(0.0, ltcg_gain))
        _rem_loss = max(0.0, available_losses - _used_vs_gain)
        _ordinary_offset = min(3000.0, _rem_loss)
        cap_loss_carryforward = _rem_loss - _ordinary_offset
        tlh_ordinary_credit = 0.0
        if _ordinary_offset > 0 and taxable_inc > 0:
            _mtr = (_compute_fed_tax_path(taxable_inc, year, filing)
                    - _compute_fed_tax_path(max(0.0, taxable_inc - _ordinary_offset), year, filing)) / _ordinary_offset
            tlh_ordinary_credit = _ordinary_offset * max(0.0, _mtr)
        row['cap_loss_used'] = _used_vs_gain + _ordinary_offset
        row['cap_loss_carryforward'] = cap_loss_carryforward
        row['tlh_ordinary_credit'] = tlh_ordinary_credit
        # Tax value the gain-offset portion avoided (LTCG that would have been
        # due on the offset gain slice, stacked above ordinary income). Combined
        # with the ordinary-offset credit this is the realized-this-year tax
        # value of harvesting, which the Tax-Loss Harvesting sheet sums to a
        # net-of-transaction-cost lifetime figure.
        tlh_gain_offset_value = _ltcg_tax_on_gain_path(_used_vs_gain, max(0.0, taxable_inc), year) if _used_vs_gain > 0 else 0.0
        row['tlh_gain_offset_value'] = tlh_gain_offset_value
        row['tlh_tax_value'] = tlh_gain_offset_value + tlh_ordinary_credit

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
        total_tax = total_tax_pre_niit + ltcg_tax + niit - tlh_ordinary_credit
        row['total_tax'] = total_tax
        row['net_income'] = row.get('gross_income', agi) - total_tax
        # Refresh total_cash_need now that ltcg_tax/niit reflect the fixed-point
        # investment-tax passes above; the earlier value (used to seed `gap`)
        # predates those passes and would otherwise understate cash need,
        # causing the cashflow sheet's recomputed Cash Bridge Gap to disagree
        # with the true engine gap (Surplus/unfunded_gap).
        row['total_cash_need'] = total_spend_need + total_tax + other_cash_need_yr

        # ── Priority 4b: Final pre-tax draw before any Roth withdrawal ───────
        # (design doc Stage 10, sub-stage #7 -- near-duplicate of sub-stage
        # #4 above; see withdrawal_cascade_ira_true_up.py's
        # apply_priority_4b_final_pretax_draw docstring)
        _priority4b = _apply_priority_4b_final_pretax_draw(
            c, bal, row,
            year=year, filing=filing, gap=gap, agi=agi, taxable_inc=taxable_inc,
            fed_tax=fed_tax, state_tax=state_tax, payroll_tax=payroll_tax, irmaa_yr=irmaa_yr,
            total_tax_pre_niit=total_tax_pre_niit, ltcg_tax=ltcg_tax, niit=niit,
            tlh_ordinary_credit=tlh_ordinary_credit, total_spend_need=total_spend_need,
            other_cash_need_yr=other_cash_need_yr, irmaa_magi_current=irmaa_magi_current,
            retirement_dist=retirement_dist, rmd_h=rmd_h, rmd_w=rmd_w, spend=spend,
            ss_taxable=ss_taxable, earned_net=earned_net, note_int_yr=note_int_yr,
            portfolio_ordinary=portfolio_ordinary, portfolio_qualified=portfolio_qualified,
            nonqual_ann=nonqual_ann, roth_conv=roth_conv, h_over_65=h_over_65,
            ira_wd=ira_wd, h_ira_elective=h_ira_elective, w_ira_elective=w_ira_elective,
            pretax_by_account=pretax_by_account, ira_tax_true_up_iterations=ira_tax_true_up_iterations,
            top_24_yr=top_24_yr, irmaa_thr_yr=irmaa_thr_yr, marg=marg,
            ira_taxable_inc_orig=_ira_taxable_inc_orig, ira_retirement_dist_orig=_ira_retirement_dist_orig,
            ira_elective_tax_delta_fn=_ira_elective_ordinary_tax_delta,
        )
        gap = _priority4b.gap
        agi = _priority4b.agi
        taxable_inc = _priority4b.taxable_inc
        fed_tax = _priority4b.fed_tax
        state_tax = _priority4b.state_tax
        total_tax_pre_niit = _priority4b.total_tax_pre_niit
        total_tax = _priority4b.total_tax
        irmaa_magi_current = _priority4b.irmaa_magi_current
        ira_wd = _priority4b.ira_wd
        h_ira_elective = _priority4b.h_ira_elective
        w_ira_elective = _priority4b.w_ira_elective
        pretax_by_account = _priority4b.pretax_by_account
        ira_tax_true_up_iterations = _priority4b.ira_tax_true_up_iterations

        # ── DAF carryforward make-up (design doc Stage 10, sub-stage #8) ─────
        # `agi` above is a first-pass estimate computed before the elective-
        # withdrawal sizing loop (Priority 3/4b) ran; by this point in the
        # cascade it has converged (Priority 3/4b are the only places agi is
        # still mutated). See withdrawal_cascade_daf_makeup.py's
        # apply_daf_carryforward_makeup docstring for the full rationale.
        _daf_makeup = _apply_daf_carryforward_makeup(
            row, year=year, agi=agi, daf_agi_limit_pct=daf_agi_limit_pct,
            daf_agi_limit=daf_agi_limit, daf_deduction_carryforward=daf_deduction_carryforward,
            item_ded=item_ded, std_ded=std_ded, qbi_ded=qbi_ded, qbi_elig=c['qbi_elig'],
            fed_tax=fed_tax, taxable_inc=taxable_inc, total_tax=total_tax, gap=gap,
            char=char, ded=ded, daf_deduction_yr=daf_deduction_yr,
            total_spend_need=total_spend_need, other_cash_need_yr=other_cash_need_yr,
            filing=filing, brk_inf=c['brk_inf'], compute_fed_tax_fn=_compute_fed_tax_path,
        )
        gap = _daf_makeup.gap
        fed_tax = _daf_makeup.fed_tax
        taxable_inc = _daf_makeup.taxable_inc
        total_tax = _daf_makeup.total_tax
        char = _daf_makeup.char
        item_ded = _daf_makeup.item_ded
        ded = _daf_makeup.ded
        daf_deduction_yr = _daf_makeup.daf_deduction_yr
        daf_deduction_carryforward = _daf_makeup.daf_deduction_carryforward

        # ── Priority 4c, Priority 5, and unfunded-gap/surplus sweep ──────────
        # (design doc Stage 10, sub-stages #9, #10, #11)
        _final_draws = _apply_final_draws(
            c, bal, row, year=year, gap=gap, hsa_bank_balance=hsa_bank_balance,
            hsa_wd=hsa_wd, spend=spend, emit=emit,
        )
        gap = _final_draws.gap
        hsa_bank_balance = _final_draws.hsa_bank_balance
        hsa_wd = _final_draws.hsa_wd
        roth_wd = _final_draws.roth_wd
        h_roth_wd = _final_draws.h_roth_wd
        w_roth_wd = _final_draws.w_roth_wd
        surplus = _final_draws.surplus

        # ── Advanced modules: equity-comp long-term-gain and AMT post-pass ───
        # Extracted to amt_equity_comp_true_up.apply_amt_and_equity_comp_true_up
        # (ticket 3.10 step 6). See that module's docstring for why
        # total_tax/amt_credit_carry come back via Stage11Result rather than
        # propagating through the function boundary on their own, and why
        # the report fields are Optional.
        _stage11 = _apply_amt_and_equity_comp_true_up(
            c,
            year=year,
            filing=filing,
            equity_on=_equity_on,
            equity_events=_equity_events,
            taxable_inc=taxable_inc,
            fed_tax=fed_tax,
            total_tax=total_tax,
            amt_credit_carry=amt_credit_carry,
            bal=bal,
        )
        total_tax = _stage11.total_tax
        amt_credit_carry = _stage11.amt_credit_carry
        if _stage11.equity_comp_ltcg_gain is not None:
            row['equity_comp_ltcg_gain'] = _stage11.equity_comp_ltcg_gain
            row['equity_comp_ltcg_tax'] = _stage11.equity_comp_ltcg_tax
        if _stage11.amt_tax is not None:
            row['amt_tax'] = _stage11.amt_tax
            row['amt_credit_used'] = _stage11.amt_credit_used
            row['amt_credit_carryforward'] = _stage11.amt_credit_carryforward

        # total_tax already includes current-year LTCG and NIIT from the fixed-point pass above.
        row['total_tax'] = total_tax

        # ── Effective marginal rate ─────────────────────────────────────────
        # See `compute_effective_marginal_rate` in effective_marginal_rate.py
        # for the full rationale (SS torpedo, why IRMAA is/isn't perturbed,
        # why both sides of the delta are recomputed through the same calls).
        row['effective_marginal_rate'], row['effective_marginal_rate_irmaa_cliff'] = (
            _compute_effective_marginal_rate(
                c,
                year=year,
                filing=filing,
                agi=agi,
                ded=ded,
                ss_taxable=ss_taxable,
                ss_total=ss_total,
                portfolio_tax_exempt=portfolio_tax_exempt,
                earned_net=earned_net,
                retirement_dist=retirement_dist,
                ira_wd=ira_wd,
                note_int_yr=note_int_yr,
                portfolio_ordinary=portfolio_ordinary,
                portfolio_qualified=portfolio_qualified,
                nonqual_ann=nonqual_ann,
                roth_conv=roth_conv,
                nii=row.get('nii', 0.0),
                n_medicare=n_medicare,
                irmaa_magi_current=irmaa_magi_current,
                h_over_65=h_over_65,
                compute_fed_tax=_compute_fed_tax_path,
                irmaa_tier=_irmaa_tier_path,
            )
        )

        row['net_income'] = row.get('gross_income', agi) - total_tax

        # ── Canonical cash-flow breakdown (single source of truth) ───────────
        # Extracted to cashflow_breakdown.compute_cashflow_breakdown (ticket
        # 3.10 step 4): read-only reshape of fields already finalized on
        # `row` by this point in the cascade. See that module's docstring
        # for the reconciliation guarantees (verified exact in
        # tests/test_cashflow_breakdown_single_source_of_truth.py) and why
        # it takes the whole `row` dict rather than an enumerated param list.
        row['cashflow_breakdown'], row['gross_cash_flow_yr'] = _compute_cashflow_breakdown(row)

        # ── Portfolio growth (EOY) + annuity PV + Net Worth ──────────────────
        # Extracted to portfolio_growth_and_net_worth.apply_portfolio_growth_
        # and_net_worth (ticket 3.10 step: Stage 14, last stage in the loop).
        # Mutates `bal` (growth) and `row` (balances, PVs, net-worth/liability
        # breakdown) in place; nothing it computes is read again this year or
        # carried into the next, so it returns None. See that module's
        # docstring for the full rationale.
        _apply_portfolio_growth_and_net_worth(
            c,
            year=year,
            h_alive=h_alive,
            w_alive=w_alive,
            bal=bal,
            row=row,
            emit=emit,
            home_equity=home_equity,
            home_val=home_val,
            autos_val=autos_val,
            startup=startup,
            note_bal=note_bal,
            cst_balance=cst_balance,
            mort_bal_yr=mort_bal_yr,
        )
        rows.append(row)
    return rows
