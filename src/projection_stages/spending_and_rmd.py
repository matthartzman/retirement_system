from __future__ import annotations

from typing import Any, Callable, NamedTuple

from .. import core as _ar  # consolidated from account_registry
from .. import planning_engines as _legacy_pe
from ..planning_engines import (
    EvRMD,
    aca_premium_tax_credit,
    rmd_divisor,
    social_security_taxable_amount,
)
from .budget_rollups import category_budget_rollup, housing_budget_rollup


class SpendingAndRMDResult(NamedTuple):
    """Every value this combined stage produces that code outside it still
    needs, returned as one typed bundle.

    Two fields (``lifetime_exemption_used``, ``spend_guardrail_state``) are
    multi-year state: the caller must reassign its own locals from these on
    every call, exactly like Stage 3's ``cst_balance``/``startup`` -- Python
    passes a float or a fresh dict back by value, so an in-place mutation
    here would silently fail to propagate to next year's call. Every other
    field is this-year-only, but still has to come back explicitly because
    it is read by code that runs *after* this function returns: the
    withdrawal cascade (``spend``, ``rec_extra``, ``lump_yr``, RMD amounts,
    HELOC P&I, ...), Stage 9's documented ACA/wellness read-then-patch
    cycle (``aca_ptc_yr``, ``wellness_base_yr`` and its components,
    ``bridge_premium_gross``, ``partb_yr``/``partd_yr``/``partg_yr``,
    ``medicare_fraction_people``/``h_medicare_frac``/``w_medicare_frac``),
    the Roth conversion planner (``portfolio_ordinary``/``portfolio_qualified``/
    ``portfolio_tax_exempt``, ``daf_contrib_yr``/``daf_gift_requested``/
    ``daf_is_inkind``), and spending-tier reporting (``qcd_total_yr``,
    ``daf_grant_yr``, the wellness detail buckets).

    A plain tuple would invite a positional mis-assignment among the ~45
    same-typed (mostly float) fields -- easy to get wrong and, given how
    many of these feed AGI/ACA MAGI/RMD compliance math, potentially
    expensive to miss in review. NamedTuple gives the call site named,
    order-independent unpacking at zero runtime cost, without pulling in
    the full engine-wide YearState this decomposition is deliberately
    deferring (see Stage 3's ``Stage3Result`` docstring for the same
    reasoning in miniature).
    """
    # Cross-year persisted state -- caller must reassign its own locals.
    lifetime_exemption_used: float
    spend_guardrail_state: dict

    # Spending totals consumed by the withdrawal cascade / gap calc.
    total_spend_need: float
    spend: float
    rec_extra: float
    lump_yr: float
    mort_yr: float
    re_tax_yr: float
    rent_yr: float
    housing_operating_yr: float
    ltc_prem_yr: float
    business_expenses_yr: float

    # RMD sizing + application results.
    rmd_h: float
    rmd_w: float
    rmd_taxable_total: float

    # HELOC P&I, read again by the withdrawal cascade's HELOC-draw step.
    heloc_interest_yr: float
    heloc_repayment_principal_yr: float
    heloc_draw_yr: float

    # ACA/wellness inputs Stage 9 revises in place (the documented
    # read-then-patch cycle -- see this module's top-level docstring).
    bridge_people: int
    bridge_premium_gross: float
    bridge_premium_yr: float
    aca_ptc_pre_conversion: float
    aca_ptc_yr: float
    partb_yr: float
    partd_yr: float
    partg_yr: float
    medicare_fraction_people: float
    h_medicare_frac: float
    w_medicare_frac: float
    wellness_shock_yr: float
    wellness_base_yr: float
    wellness_premium_yr: float
    wellness_transaction_premium_yr: float
    wellness_detail_budget_yr: float
    wellness_medical_yr: float
    wellness_dental_yr: float
    wellness_vision_yr: float
    wellness_rx_otc_yr: float
    wellness_other_yr: float

    # Portfolio dividend/interest income, read by the Roth conversion
    # planner's state-tax estimate and by AGI/tax below it.
    portfolio_ordinary: float
    portfolio_qualified: float
    portfolio_tax_exempt: float

    # QCD/DAF results read by the itemized-charitable-deduction calc (Stage 9).
    qcd_total_yr: float
    daf_contrib_yr: float
    daf_gift_requested: float
    daf_is_inkind: bool
    daf_grant_yr: float


def apply_spending_and_rmd(
    c: dict[str, Any],
    *,
    year: int,
    h_age: float,
    w_age: float,
    h_alive: bool,
    w_alive: bool,
    n_alive: int,
    filing: str,
    bal: dict[str, float],
    row: dict[str, Any],
    net_earned_taxable: float,
    half_se_ded: float,
    sehi_ded: float,
    pension: float,
    wife_single_ann: float,
    wife_joint_ann: float,
    h_single_ann: float,
    h_joint_ann: float,
    note_int_yr: float,
    h_ss: float,
    w_ss: float,
    business_expenses_yr: float,
    lifetime_exemption_used: float,
    spend_guardrail_state: dict,
    recent_gift_totals: list,
    spending_factor: Callable[[int], float],
    survivor_factor: Callable[[int], float],
    infl_factor: Callable[[int], float],
    infl_ratio: Callable[[int, int], float],
    path_factor: Callable[[str, float, int], float],
    next_housing_for_year: Callable[[int], dict],
    medicare_month_fraction: Callable[[int, Any, int], float],
    taxable_portfolio_income_for_year: Callable[[], tuple],
    emit: Callable[[Any], None],
) -> SpendingAndRMDResult:
    """Compute this year's total spending need (including RMD *sizing*) and
    then withdraw the sized RMD from the household's accounts (RMD
    *application*) -- the design doc's Stage 6 and Stage 7, combined.

    In the legacy engine these were split by ~270 lines of intervening
    code: QCD sizing (itself dependent on the RMD sizing output --
    ``rmd_h``/``rmd_w``), the gifting schedule, portfolio dividend/interest
    income, ACA/wellness/Medicare premium math, and HELOC P&I, all on the
    way to computing ``total_spend_need``, before RMD application finally
    ran. That intervening code is not unrelated filler that can be
    reordered away: the gifting schedule mutates ``bal`` on a
    user-configured ``funding_account`` that is not restricted to
    non-RMD-eligible accounts, so it touches the same balances RMD
    application does, and the QCD calculation directly consumes the RMD
    sizing output. Reordering RMD application to run immediately after
    sizing (before gifting) would risk changing computed cash available to
    a gift in a plan where the funding account happens to be RMD-eligible
    -- a real behavior change, not just a textual move. So this function
    preserves the legacy statement order exactly (sizing, then the same
    intervening spending computation, then application at the end).

    What *is* solved by this extraction: the "270 lines apart" problem was
    fundamentally that sizing and application were separated by dozens of
    *other* stages' worth of code inside one 3,283-line function, not that
    the spending computation itself was unrelated. Bringing the whole
    Stage-6/Stage-7 range together into this single, dedicated module
    means sizing and application are now adjacent in the codebase --
    nothing sits between them but the spending computation that
    conceptually always belonged with Stage 6 anyway. A reader (or future
    editor) of RMD logic now finds both halves in the same ~350-line file
    instead of ~270 lines and several unrelated headers apart in the
    monolith.

    ``bal`` and ``row`` are mutated in place, as elsewhere in this stage
    decomposition. Everything else this stage produces that outside code
    still needs comes back via :class:`SpendingAndRMDResult` -- see its
    docstring for the full inventory and why a named tuple.

    The seven ``*_factor``/``*_for_year`` callables (``spending_factor``
    through ``taxable_portfolio_income_for_year``) are the same closures
    the legacy engine defines once in setup, capturing ``c`` (and, for
    ``taxable_portfolio_income_for_year``, ``bal``) -- passed in here by
    reference rather than re-implemented, so there is exactly one
    definition of each and no risk of the two copies drifting apart.
    """
    # ── Spending ─────────────────────────────────────────────────────────
    # Base spending (inflated until freeze year)
    if year <= c['spending_freeze_yr']:
        spend = c['spend_base'] * spending_factor(year)
    else:
        spend = c['spend_base'] * spending_factor(c['spending_freeze_yr'])
    spend = c.get('ytd_blend_spend_override', {}).get(year, spend)
    # Survivor scaling is applied last, after the YTD blend override, so a
    # blended current-year figure is scaled too if that year ever became a
    # survivor year.
    survivor_factor_yr = survivor_factor(n_alive)
    row['survivor_spend_factor_yr'] = survivor_factor_yr
    spend *= survivor_factor_yr

    # ── Item 3.5 (F6): age-phased real spending curve (Option 2, always
    # independently available) then the adoptable spending guardrail
    # policy (fixed_real/guyton_klinger/floor_ceiling_band). Both are
    # no-ops (factor 1.0 / policy passthrough) for every plan that
    # hasn't configured them, so this is byte-identical to the prior
    # unconditional `spend_base_yr = spend` for the shipped default.
    _phase_age = max(h_age if h_alive else -1, w_age if w_alive else -1)
    if _phase_age >= 0:
        spend *= _legacy_pe.age_phased_spending_factor(
            _phase_age, c.get('spending_phase_decline_pct', 0.0),
            c.get('spending_phase_start_age', 0), c.get('spending_phase_end_age', 0),
        )
    _spend_policy = str(c.get('spending_policy', 'fixed_real') or 'fixed_real')
    if _spend_policy in ('guyton_klinger', 'floor_ceiling_band') and spend > 0:
        _portfolio_value_yr = sum(
            max(0.0, float(bal.get(_aid, 0.0) or 0.0))
            for _aid in (c.get('pre_tax_ids', []) + c.get('roth_ids', []) + c.get('taxable_ids', [])
                         + c.get('hsa_ids', []) + c.get('cash_ids', []))
        )
        spend, spend_guardrail_state, _spend_cut, _spend_raised = _legacy_pe.spending_guardrail_year(
            _spend_policy, spend, _portfolio_value_yr, spend_guardrail_state,
            inflation_rate=c.get('inf', 0.025),
            prior_return=None,  # documented no-op: single flat c['ret'], no year-to-year variation
            years_remaining=c['plan_end'] - year,
        )
        row['spending_policy_cut_applied'] = bool(_spend_cut)
        row['spending_policy_raise_applied'] = bool(_spend_raised)
    row['spend_base_yr'] = spend

    # Recurring extras — Home Improvement items route to housing costs; all others to rec_extra
    rec_extra = 0.0
    home_improvement_extra = 0.0
    if year <= c.get('home_proj_end', c['plan_start'] - 1):
        rec_extra += c.get('home_proj', 0.0) * infl_factor(year)
    if year <= c.get('vac_end', c['plan_start'] - 1):
        rec_extra += c.get('vac', 0.0) * infl_factor(year)
    _travel_end_year = int(c.get('travel_end_year', 0) or 0)
    for ev in c.get('recurring_extras', []):
        start_yr = int(ev.get('start_year') or c['plan_start'])
        end_yr = int(ev.get('end_year') or start_yr)
        # Skip Travel group items after travel_end_year if configured
        if _travel_end_year > 0 and year > _travel_end_year:
            _ev_type = str(ev.get('type') or '').lower()
            if _ev_type == 'travel':
                continue
        if start_yr <= year <= end_yr:
            base_yr = max(c['plan_start'], start_yr)
            _ev_amt = float(ev.get('amount') or 0.0) * infl_ratio(year, base_yr)
            if ev.get('is_home_improvement'):
                home_improvement_extra += _ev_amt
            else:
                rec_extra += _ev_amt
    # Higher-of floor for Travel / Large Discretionary: a current-year top-up
    # (annualized actual minus budget, when positive) computed by the YTD blend
    # so the discretionary spend never projects below the client's run rate.
    # Respect travel_end_year for the higher-of floor as well.
    _topup = c.get('ytd_blend_extra_topup', {}).get(year, 0.0)
    if _travel_end_year > 0 and year > _travel_end_year:
        # ytd_blend_extra_topup is a Travel-only floor by construction
        # (ytd_projection_blend._DISCRETIONARY_FLOOR_TRACKING_TYPES == ("Travel",);
        # Large Discretionary is deliberately excluded), so zeroing the whole
        # top-up after travel ends drops exactly the travel run-rate floor and
        # nothing else.
        _topup = 0.0
    rec_extra += _topup
    # Same survivor scaling as core spending. home_improvement_extra is
    # deliberately excluded — it has already been routed to housing above.
    rec_extra *= survivor_factor_yr
    row['rec_extra'] = rec_extra
    row['home_improvement_extra'] = home_improvement_extra

    # Lump events (including a cash DAF contribution as a deductible lump)
    lump_yr = c['lump'].get(year, 0)
    # DAF contribution. A *cash* gift is a real cash outflow: it joins the
    # lump line, lands in total_spend_need, and the withdrawal waterfall
    # funds it like any other spending need.
    #
    # An *appreciated-securities* gift is not a cash transaction at all --
    # the shares move in kind from a taxable account straight to the DAF.
    # Routing it through the spending bridge forced a taxable draw that
    # realized the embedded capital gain, which is precisely the tax the
    # strategy exists to avoid. It is handled instead as a direct in-kind
    # transfer below (search: daf_inkind_yr), after RMDs and the Roth
    # conversion have settled this year's balances.
    daf_contrib_yr = 0.0
    daf_is_inkind = bool(c.get('daf_contribution_is_appreciated', False))
    daf_gift_requested = 0.0
    if c.get('daf_enabled', False) and year == c.get('daf_year', 0):
        daf_gift_requested = float(c.get('daf_amount', 0) or 0.0)
        if not daf_is_inkind:
            daf_contrib_yr = daf_gift_requested
            lump_yr += daf_contrib_yr
    row['lump']          = lump_yr
    row['daf_contrib_yr']= daf_contrib_yr
    row['daf_inkind_yr'] = 0.0
    # DAF grants (reduces annual charitable giving from the DAF balance, not new cash)
    daf_grant_yr = 0.0
    if (c.get('daf_enabled', False) and
            c.get('daf_use_start', 9999) <= year <= c.get('daf_use_end', 9999)):
        daf_grant_yr = c.get('daf_use_amount', 0)
    row['daf_grant_yr'] = daf_grant_yr

    # Mortgage, real-estate taxes, home improvement, and Housing Budget Detail.
    # Current-year Housing budgets seed projection rows when the dedicated
    # model inputs are blank. Dedicated inputs still win when configured.
    housing_budget_groups = housing_budget_rollup(c, year, infl_ratio)
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
        home_improvement_budget_yr *= infl_ratio(year, int(c.get('plan_start', year) or year))
    home_improvement_yr = home_improvement_override_yr if home_improvement_override_yr > 0 else home_improvement_budget_yr
    # Next Housing Step rows are authoritative future rent/buy events.
    # They add ongoing Housing cash flow and, for purchases, home equity /
    # mortgage liability.  Start-year down payment is a separate cash need.
    next_housing_yr = next_housing_for_year(year)
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
    rmd_result = _legacy_pe.compute_rmds(c, bal, year, h_age, w_age, h_alive, w_alive, rmd_divisor)
    rmd_h = rmd_result['h']; rmd_w = rmd_result['w']; rmd_total = rmd_result['total']

    # Item 4.1 (P3): Qualified Charitable Distributions. Modeled as
    # satisfying up to that year's own RMD (apply_rmds below draws the
    # full rmd_h/rmd_w from the IRA either way — QCD doesn't change how
    # much must leave the account), but the QCD portion goes straight to
    # charity rather than becoming household income: it must be excluded
    # from AGI (never claimed as a second deduction — see the itemized
    # charitable component below) *and* from the cash the household has
    # available to fund spending. rmd_taxable_total (not rmd_total) is
    # therefore what feeds AGI, ACA MAGI, Roth-conversion headroom, and
    # income_from_streams below; rmd_h/rmd_w/rmd_total keep reporting the
    # true gross RMD for compliance/satisfaction purposes.
    #
    # Scope simplification (phase 1): a QCD larger than the current
    # year's RMD, or a QCD taken in the age-70 1/2-to-RMD-start gap (no
    # RMD due yet), is capped at that year's actual RMD rather than
    # modeled as an independent extra IRA withdrawal — real but less
    # common uses of QCD that would require their own account-balance
    # draw outside the RMD mechanic. h_qcd_yr/w_qcd_yr below report the
    # amount actually modeled, so a configured amount above the RMD is
    # visibly capped, not silently accepted.
    def _qcd_amount_for_member(owner_prefix, dob_yr, dob_month, alive, rmd_amount):
        if not c.get('qcd_enabled', False) or not alive or rmd_amount <= 0:
            return 0.0
        annual = float(c.get(f'{owner_prefix}_qcd_annual_amount', 0.0) or 0.0)
        if annual <= 0:
            return 0.0
        eligible_from = _ar.qcd_eligible_from_year(dob_yr, dob_month)
        if eligible_from is None:
            return 0.0
        start_override = c.get(f'{owner_prefix}_qcd_start_year')
        start_year = int(start_override) if start_override is not None else eligible_from
        start_year = max(start_year, eligible_from)
        if year < start_year:
            return 0.0
        end_override = c.get(f'{owner_prefix}_qcd_end_year')
        if end_override is not None and year > int(end_override):
            return 0.0
        limit = _ar.qcd_annual_limit(year, c['brk_inf'])
        return max(0.0, min(annual, limit, rmd_amount))

    qcd_h_yr = _qcd_amount_for_member('h', c['h_dob_yr'], c.get('h_dob_month'), h_alive, rmd_h)
    qcd_w_yr = _qcd_amount_for_member('w', c['w_dob_yr'], c.get('w_dob_month'), w_alive, rmd_w)
    qcd_total_yr = qcd_h_yr + qcd_w_yr
    rmd_taxable_total = max(0.0, rmd_total - qcd_total_yr)
    row['h_qcd_yr'] = qcd_h_yr
    row['w_qcd_yr'] = qcd_w_yr
    row['qcd_total_yr'] = qcd_total_yr

    # Item 4.8 (P11): gifting schedule. A genuinely new balance-mutating
    # path outside the withdrawal cascade: gifted dollars leave the
    # funding account directly (reducing the estate base as a natural
    # consequence of touching `bal`) and never fund household spending,
    # so they are not routed through income_from_streams/the withdrawal
    # cascade at all -- unlike QCD/DAF, which only change tax treatment
    # of money that still ends up funding the household.
    gift_total_yr = 0.0
    gift_excess_over_exclusion_yr = 0.0
    for _gift in (c.get('gifting_schedule') or []):
        _start = int(_gift.get('start_year', 0) or 0)
        if not _start or year < _start:
            continue
        _end = int(_gift.get('end_year', 0) or 0)
        if _end and year > _end:
            continue
        _per_donee = float(_gift.get('annual_amount_per_donee', 0.0) or 0.0)
        _donees = max(1, int(_gift.get('donee_count', 1) or 1))
        _requested = _per_donee * _donees
        if _requested <= 0:
            continue
        _acct_id = _gift.get('funding_account')
        _available = max(0.0, float(bal.get(_acct_id, 0.0) or 0.0))
        _drawn = min(_requested, _available)
        if _drawn <= 0:
            continue
        bal[_acct_id] = _available - _drawn
        gift_total_yr += _drawn
        # If the funding account couldn't cover the full requested gift,
        # scale the exclusion-exceeding portion down by the same ratio
        # actually delivered, rather than crediting exemption use for
        # dollars that were never actually gifted.
        _excess_requested = max(0.0, _per_donee - float(c.get('gift_excl', 19000.0) or 19000.0)) * _donees
        gift_excess_over_exclusion_yr += _excess_requested * (_drawn / _requested)
    lifetime_exemption_used += gift_excess_over_exclusion_yr
    row['gift_total_yr'] = gift_total_yr
    row['gift_excess_over_exclusion_yr'] = gift_excess_over_exclusion_yr
    row['lifetime_exemption_used_cumulative'] = lifetime_exemption_used
    recent_gift_totals.append(gift_total_yr)
    if len(recent_gift_totals) > 3:
        recent_gift_totals.pop(0)
    row['gift_total_last_3yr'] = sum(recent_gift_totals)

    portfolio_ordinary, portfolio_qualified, portfolio_tax_exempt = taxable_portfolio_income_for_year()
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
    # Item 182: the pre-65 bridge premium is the cost of health coverage
    # (marketplace/COBRA/retiree) owed by anyone who is pre-65, whether or
    # not they have retired yet — so it is NOT gated on the retirement year.
    h_bridge = (1 if h_alive and h_age < 65 else 0)
    w_bridge = (1 if w_alive and w_age < 65 else 0)
    bridge_people = h_bridge + w_bridge  # integer count for ACA PTC eligibility/benchmark scaling
    # Month-level proration of the actual premium dollars billed. In the
    # calendar year someone turns 65, Medicare Part B/D eligibility begins
    # the 1st of their birth month (standard CMS rule), so the pre-65
    # bridge premium is only owed for the fraction of the year before that
    # date, and Medicare Part B/D/G premiums only for the fraction after.
    # Outside the transition year the fractions collapse to the prior
    # binary 1.0/0.0 behavior exactly.
    h_medicare_frac = medicare_month_fraction(c['h_dob_yr'], c.get('h_dob_month'), year) if h_alive else 0.0
    w_medicare_frac = medicare_month_fraction(c['w_dob_yr'], c.get('w_dob_month'), year) if w_alive else 0.0
    h_pre65_frac = (1.0 - h_medicare_frac) if h_alive else 0.0
    w_pre65_frac = (1.0 - w_medicare_frac) if w_alive else 0.0
    bridge_fraction_people = h_pre65_frac + w_pre65_frac
    medicare_fraction_people = h_medicare_frac + w_medicare_frac
    bridge_premium_gross = bridge_fraction_people * float(c.get('bridge_premium', 0.0) or 0.0) * path_factor('medical_index_by_year', c.get('med_inf', c['inf']), year)
    # Preliminary ACA PTC estimate before Roth conversions; the conversion
    # planner receives bridge_people to constrain avoidable MAGI spikes.
    # The final PTC is recomputed after the actual Roth conversion and
    # Social Security taxable amount are known, so conversion-driven MAGI
    # changes reduce the subsidy before the withdrawal cascade runs.
    _aca_pre_non_ss = (net_earned_taxable - half_se_ded - sehi_ded + rmd_taxable_total + pension + wife_single_ann + wife_joint_ann + h_single_ann + h_joint_ann + note_int_yr + portfolio_ordinary + portfolio_qualified)
    _aca_pre_ss_tax = social_security_taxable_amount(h_ss + w_ss, _aca_pre_non_ss + portfolio_tax_exempt, filing)
    aca_ptc_pre_conversion = aca_premium_tax_credit(c, year=year, magi=_aca_pre_non_ss + _aca_pre_ss_tax + portfolio_tax_exempt, bridge_people=bridge_people)
    aca_ptc_yr = aca_ptc_pre_conversion
    bridge_premium_yr = max(0.0, bridge_premium_gross - aca_ptc_yr)
    partb_yr = medicare_fraction_people * float(c.get('partb', 0.0) or 0.0) * 12 * path_factor('medical_index_by_year', c.get('med_inf', c['inf']), year)
    partd_yr = medicare_fraction_people * float(c.get('partd', 0.0) or 0.0) * 12 * path_factor('partd_index_by_year', c.get('partd_inf', c.get('med_inf', c['inf'])), year)
    partg_yr = medicare_fraction_people * float(c.get('partg', 0.0) or 0.0) * 12 * path_factor('medical_index_by_year', c.get('med_inf', c['inf']), year)
    alive_count = (1 if h_alive else 0) + (1 if w_alive else 0)
    oop_yr = (float(c.get('oop', 0.0) or 0.0) * float(c.get('oop_utilization_pct', 1.0) or 1.0)
              * (1.0 if alive_count >= 2 else (0.5 if alive_count == 1 else 0.0))
              * path_factor('medical_index_by_year', c.get('med_inf', c['inf']), year))
    wellness_premium_yr = bridge_premium_yr + partb_yr + partd_yr + partg_yr
    wellness_transaction_premium_yr = category_budget_rollup(c, year, [
        'wellness_premium', 'pre65_wellness_premium', 'medicare_part_b',
        'medicare_part_d', 'medigap_premium'
    ], path_factor, 'medical_index_by_year', 'med_inf')
    if wellness_premium_yr <= 0:
        wellness_premium_yr = wellness_transaction_premium_yr

    # Wellness detail budgets (Medical, Dental, Vision, Rx/OTC and other
    # Wellness categories) are the workbook/UI detail expansion. The household
    # Medical OOP Cap is a cap/reference for non-premium medical spending, not a
    # standalone expense. When detail rows exist, cap non-premium detail at
    # the modeled Medical OOP Cap; when detail rows are absent, do not create a
    # duplicate OOP expense.
    wellness_medical_yr = category_budget_rollup(c, year, ['medical', 'dermatologist'], path_factor, 'medical_index_by_year', 'med_inf')
    wellness_dental_yr = category_budget_rollup(c, year, ['dentist', 'dental'], path_factor, 'medical_index_by_year', 'med_inf')
    wellness_vision_yr = category_budget_rollup(c, year, ['vision', 'eye_exams', 'glasses_contacts'], path_factor, 'medical_index_by_year', 'med_inf')
    wellness_rx_otc_yr = category_budget_rollup(c, year, ['drugs_rx_and_otc', 'prescription_drugs', 'otc_meds'], path_factor, 'partd_index_by_year', 'partd_inf')
    wellness_other_yr = category_budget_rollup(c, year, [
        'health_club', 'exercise_health_equipment', 'vitamins_supplements',
        'supplements', 'wellness_other'
    ], path_factor, 'medical_index_by_year', 'med_inf')
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
    # Item 184: real-estate tax is a real annual cash outflow (it is the sole
    # representation of property tax — not in mort_yr or housing_operating_yr),
    # so it must be funded from the portfolio. Previously it was used only for
    # the SALT deduction and was missing here, understating cash need and
    # overstating net worth by the property-tax amount each year.
    # ── Estate mode: nobody is alive ─────────────────────────────────
    # Past the second death there are no living expenses of any kind. The
    # plan used to keep charging core spending and housing indefinitely --
    # and kept inflating them -- so a household that no longer existed
    # accumulated an unfunded gap. Taxes on estate income still apply and
    # are computed elsewhere; this zeroes CONSUMPTION only.
    #
    # Latent on a default horizon: plan_end == the second death year, so a
    # normal plan has no both-dead rows for this to touch.
    if n_alive == 0:
        spend = rec_extra = lump_yr = 0.0
        mort_yr = rent_yr = housing_operating_yr = re_tax_yr = 0.0
        ltc_prem_yr = wellness_base_yr = wellness_shock_yr = 0.0
        heloc_interest_yr = heloc_repayment_principal_yr = 0.0
        business_expenses_yr = 0.0
        row['home_improvement_yr'] = 0.0
        row['spend_base_yr'] = 0.0
        row['rec_extra'] = 0.0
        row['lump'] = 0.0
        row['ltc_prem_yr'] = 0.0
        row['wellness_base_yr'] = 0.0
        row['wellness_shock_yr'] = 0.0
        row['business_expenses_yr'] = 0.0
        row['mortgage_payment_yr'] = 0.0
        row['rent_yr'] = 0.0
        row['real_estate_tax_yr'] = 0.0
        row['housing_operating_yr'] = 0.0
        row['housing_utilities_yr'] = 0.0
        row['housing_maintenance_yr'] = 0.0
        row['housing_other_yr'] = 0.0
        row['housing_total_yr'] = 0.0

    total_spend_need = (spend + rec_extra + lump_yr + mort_yr + row['home_improvement_yr']
                        + rent_yr + housing_operating_yr + re_tax_yr + ltc_prem_yr
                        + wellness_base_yr + wellness_shock_yr
                        + heloc_interest_yr + heloc_repayment_principal_yr
                        + business_expenses_yr)
    row['total_spend'] = total_spend_need

    # ── RMDs ─────────────────────────────────────────────────────────────
    _rmd_draws = _legacy_pe.apply_rmds(bal, rmd_result)
    row['_rmd_by_account'] = dict(_rmd_draws)
    for _aid, _amt in _rmd_draws.items():
        emit(EvRMD(year, _aid, 0, 0, _amt))
        _add_account_flow(row['_account_withdrawals'], _aid, _amt)

    row['rmd_h'] = rmd_h
    row['rmd_w'] = rmd_w
    row['rmd_total'] = rmd_total

    return SpendingAndRMDResult(
        lifetime_exemption_used=lifetime_exemption_used,
        spend_guardrail_state=spend_guardrail_state,
        total_spend_need=total_spend_need,
        spend=spend,
        rec_extra=rec_extra,
        lump_yr=lump_yr,
        mort_yr=mort_yr,
        re_tax_yr=re_tax_yr,
        rent_yr=rent_yr,
        housing_operating_yr=housing_operating_yr,
        ltc_prem_yr=ltc_prem_yr,
        business_expenses_yr=business_expenses_yr,
        rmd_h=rmd_h,
        rmd_w=rmd_w,
        rmd_taxable_total=rmd_taxable_total,
        heloc_interest_yr=heloc_interest_yr,
        heloc_repayment_principal_yr=heloc_repayment_principal_yr,
        heloc_draw_yr=heloc_draw_yr,
        bridge_people=bridge_people,
        bridge_premium_gross=bridge_premium_gross,
        bridge_premium_yr=bridge_premium_yr,
        aca_ptc_pre_conversion=aca_ptc_pre_conversion,
        aca_ptc_yr=aca_ptc_yr,
        partb_yr=partb_yr,
        partd_yr=partd_yr,
        partg_yr=partg_yr,
        medicare_fraction_people=medicare_fraction_people,
        h_medicare_frac=h_medicare_frac,
        w_medicare_frac=w_medicare_frac,
        wellness_shock_yr=wellness_shock_yr,
        wellness_base_yr=wellness_base_yr,
        wellness_premium_yr=wellness_premium_yr,
        wellness_transaction_premium_yr=wellness_transaction_premium_yr,
        wellness_detail_budget_yr=wellness_detail_budget_yr,
        wellness_medical_yr=wellness_medical_yr,
        wellness_dental_yr=wellness_dental_yr,
        wellness_vision_yr=wellness_vision_yr,
        wellness_rx_otc_yr=wellness_rx_otc_yr,
        wellness_other_yr=wellness_other_yr,
        portfolio_ordinary=portfolio_ordinary,
        portfolio_qualified=portfolio_qualified,
        portfolio_tax_exempt=portfolio_tax_exempt,
        qcd_total_yr=qcd_total_yr,
        daf_contrib_yr=daf_contrib_yr,
        daf_gift_requested=daf_gift_requested,
        daf_is_inkind=daf_is_inkind,
        daf_grant_yr=daf_grant_yr,
    )


def _add_account_flow(target: dict[str, float], acct: str | None, amount: float) -> None:
    amount = float(amount or 0.0)
    if acct and abs(amount) > 1e-9:
        target[acct] = target.get(acct, 0.0) + amount
