from __future__ import annotations

from typing import Any, Callable, NamedTuple

from .. import planning_engines as _legacy_pe
from ..planning_engines import (
    EvConversion,
    EvTax,
    EvTransfer,
    FEDERAL_BRACKETS_BASE_YEAR,
    FEDERAL_BRACKETS_MFJ,
    STATE_TAX_RULES,
    aca_premium_tax_credit,
    annuity_cash_income,
    irmaa_lookback_magi,
    salt_cap,
    senior_bonus_deduction,
    social_security_taxable_amount,
    state_income_tax,
)
from ..core import state_for_year
from .home_sale import resolve_home_sale_gain_tax as _resolve_home_sale_gain_tax
from .spending_tiers import compute_spend_by_tier as _compute_spend_by_tier


def _add_account_flow(target: dict[str, float], acct: str | None, amount: float) -> None:
    amount = float(amount or 0.0)
    if acct and abs(amount) > 1e-9:
        target[acct] = target.get(acct, 0.0) + amount


def _qualified_and_nonqualified_annuity_income(c: dict[str, Any], year: int) -> tuple[float, float]:
    """Split this year's annuity cash income into its qualified and
    non-qualified (basis-excluded) taxable pieces.

    Both the Roth-sizing state-tax pre-estimate and the real AGI/tax stage's
    state-tax call need exactly this split, computed with the identical
    account-key list and the identical ``qualified``/``exclusion_ratio``
    rules -- this was two copies of the same six-line formula in the legacy
    engine (one inline in each stage's block) before this extraction. There
    is nothing else duplicated between the two call sites (see
    :func:`_state_tax_estimate_for_conversion`'s docstring for why the rest
    of the two state-tax computations must stay genuinely separate), so this
    is the one piece it is safe to collapse into a single shared function.
    """
    qual_ann = sum(
        annuity_cash_income(c[k], year)
        for k in ('wife_pension', 'wife_joint', 'h_joint')
        if c[k].get('qualified', True)
    )
    nonqual_ann = sum(
        annuity_cash_income(c[k], year) * c[k].get('exclusion_ratio', 1.0)
        for k in ('wife_single', 'h_single')
        if not c[k].get('qualified', True)
    )
    return qual_ann, nonqual_ann


def _state_tax_estimate_for_conversion(
    c: dict[str, Any],
    *,
    year: int,
    filing: str,
    h_age: float,
    w_age: float,
    wife_single_ann: float,
    h_single_ann: float,
    h_ss: float,
    w_ss: float,
    net_earned_taxable: float,
    half_se_ded: float,
    sehi_ded: float,
    rmd_taxable_total: float,
    pension: float,
    wife_joint_ann: float,
    h_joint_ann: float,
    note_int_yr: float,
    portfolio_ordinary: float,
    portfolio_qualified: float,
) -> Callable[[float, int], float]:
    """Build the Roth-sizing planner's pre-conversion state-tax estimator.

    This is a **deliberate simplified estimate**, not a stand-in for the
    real AGI/tax stage's state-tax computation below -- and the two must
    stay separate rather than collapse into one call, for a structural
    reason, not just historical accident: :func:`apply_roth_conversion_stage`
    runs *before* the conversion amount (and therefore this year's real
    ``roth_conv``-inclusive Social Security taxability and AGI) is known.
    The Roth conversion planner needs a state-tax marginal-cost estimate to
    decide how large a conversion to make in the first place, so it cannot
    call forward into a computation that depends on its own output.

    Concretely, this estimate differs from the real one in two ways, both
    intentional:

    1. It always assumes ``roth_conv=0.0`` and computes Social Security
       taxability (``_ss_taxable_est``) on that pre-conversion income
       picture, via the same :func:`social_security_taxable_amount` the
       real stage uses -- but with a different provisional-income input,
       since the real stage's includes the actual conversion amount and
       this one cannot.
    2. It omits equity-comp ordinary income and disability taxable income
       (``_equity_events['ordinary_income']``, ``_di_taxable``) that the
       real AGI/tax stage's Social Security provisional-income calculation
       includes -- the Roth conversion planner is never given those inputs
       (see the call site in :func:`apply_roth_conversion_stage`), so this
       estimate is knowingly narrower, not a bug.

    The one piece of true duplication between this and the real
    computation -- the qualified/non-qualified annuity income split -- is
    factored out into :func:`_qualified_and_nonqualified_annuity_income`
    and shared by both, rather than each keeping its own copy.

    Returns a ``(agi_est, tax_year) -> state_tax`` closure matching the
    ``state_tax_estimate_fn`` shape ``planning_engines.plan_roth_conversion``
    expects. ``agi_est`` is accepted (and, exactly as in the legacy engine,
    unused in the body) purely to match that call shape.
    """

    def _estimate(_agi_est: float, _tax_year: int) -> float:
        _ws_taxable_est = wife_single_ann * c['wife_single'].get('exclusion_ratio', 1.0)
        _hs_taxable_est = h_single_ann * c['h_single'].get('exclusion_ratio', 1.0)
        _ss_total_est = h_ss + w_ss
        _non_ss_est = (
            net_earned_taxable - half_se_ded - sehi_ded + rmd_taxable_total + pension
            + _ws_taxable_est + wife_joint_ann + _hs_taxable_est
            + h_joint_ann + note_int_yr + portfolio_ordinary + portfolio_qualified
        )
        _ss_taxable_est = social_security_taxable_amount(_ss_total_est, _non_ss_est, filing)
        _qual_ann_est, _nonqual_ann_est = _qualified_and_nonqualified_annuity_income(c, year)
        return state_income_tax(
            state_for_year(c, _tax_year), max(0, net_earned_taxable - half_se_ded - sehi_ded),
            rmd_taxable_total + _qual_ann_est, _ss_taxable_est, note_int_yr + portfolio_ordinary + portfolio_qualified,
            _nonqual_ann_est, 0.0, _tax_year, h_age >= 65 or w_age >= 65, filing=filing,
            brk_inf=c['brk_inf'],
        )

    return _estimate


class RothConversionResult(NamedTuple):
    """Everything Stage 8 (Roth Conversions, plus the DAF in-kind gift that
    the legacy engine runs immediately after it -- see this module's
    ``apply_roth_conversion_stage`` docstring for why the two are one
    function) produces that code outside it still needs.

    ``bal`` and ``row`` are mutated in place, matching every other extracted
    stage. ``roth_conv`` and ``daf_contrib_yr`` are read as bare locals both
    by the AGI/tax stage right after this one and again, much later, by the
    still-inline withdrawal cascade -- they come back here rather than being
    left for callers to re-read off ``row``, exactly like Stage 5/6's
    equivalent this-year outputs.
    """
    roth_conv: float
    daf_contrib_yr: float


def apply_roth_conversion_stage(
    c: dict[str, Any],
    bal: dict[str, float],
    bal_basis_free: dict[str, float],
    row: dict[str, Any],
    *,
    year: int,
    filing: str,
    h_age: float,
    w_age: float,
    earned_base: float,
    net_earned_taxable: float,
    half_se_ded: float,
    sehi_ded: float,
    h_ss: float,
    w_ss: float,
    rmd_taxable_total: float,
    pension: float,
    wife_single_ann: float,
    wife_joint_ann: float,
    h_single_ann: float,
    h_joint_ann: float,
    note_int_yr: float,
    note_princ_yr: float,
    total_spend_need: float,
    spend: float,
    portfolio_ordinary: float,
    portfolio_qualified: float,
    portfolio_tax_exempt: float,
    bridge_people: int,
    daf_is_inkind: bool,
    daf_gift_requested: float,
    daf_contrib_yr: float,
    inflate_brackets_fn: Callable[[Any, Any, int], Any],
    standard_deduction_fn: Callable[[int, str, Any, int], float],
    compute_fed_tax_fn: Callable[[float, int, str, Any], float],
    emit: Callable[[Any], None],
) -> RothConversionResult:
    """Design doc Stage 8 (Roth Conversions), plus the DAF in-kind
    (appreciated-securities) gift the legacy engine applies immediately
    after it and before the AGI/tax stage.

    The two are kept in one function because the legacy engine's ordering
    is load-bearing, not incidental: the DAF in-kind gift must run after
    the conversion (so a conversion-driven cash need cannot accidentally
    compete with it for taxable-account liquidity in a way the legacy
    engine didn't) and before the AGI/tax stage (whose itemized-deduction
    stack reads ``daf_contrib_yr``, which the in-kind branch can overwrite).
    Splitting them into two functions would just relocate that ordering
    dependency into the caller instead of removing it.

    Sizes and applies the voluntary Roth conversion via the existing
    ``planning_engines.plan_roth_conversion``/``apply_roth_conversion``
    (unchanged -- this stage's contribution is the surrounding wiring and
    the pre-conversion state-tax estimate, not the sizing policy itself),
    then, if the plan calls for an in-kind DAF gift this year, donates
    appreciated shares directly out of the taxable accounts.

    Mutates ``bal``, ``bal_basis_free``, and ``row`` in place. Returns
    :class:`RothConversionResult` for the two locals read as bare names by
    both the AGI/tax stage right after this one and the still-inline
    withdrawal cascade far below.
    """
    # ── Roth Conversions ─────────────────────────────────────────────────
    _state_tax_estimate = _state_tax_estimate_for_conversion(
        c, year=year, filing=filing, h_age=h_age, w_age=w_age,
        wife_single_ann=wife_single_ann, h_single_ann=h_single_ann,
        h_ss=h_ss, w_ss=w_ss, net_earned_taxable=net_earned_taxable,
        half_se_ded=half_se_ded, sehi_ded=sehi_ded, rmd_taxable_total=rmd_taxable_total,
        pension=pension, wife_joint_ann=wife_joint_ann, h_joint_ann=h_joint_ann,
        note_int_yr=note_int_yr, portfolio_ordinary=portfolio_ordinary,
        portfolio_qualified=portfolio_qualified,
    )

    conv_plan = _legacy_pe.plan_roth_conversion(
        c, bal, year=year, filing=filing, earned_base=earned_base,
        half_se_ded=half_se_ded, sehi_ded=sehi_ded, h_ss=h_ss, w_ss=w_ss,
        rmd_total=rmd_taxable_total, pension=pension, wife_single_ann=wife_single_ann,
        wife_joint_ann=wife_joint_ann, h_single_ann=h_single_ann,
        h_joint_ann=h_joint_ann, note_int_yr=note_int_yr, note_princ_yr=note_princ_yr,
        total_spend_need=total_spend_need, spend=spend, h_age=h_age, w_age=w_age,
        portfolio_ordinary=portfolio_ordinary, portfolio_qualified=portfolio_qualified,
        portfolio_tax_exempt=portfolio_tax_exempt,
        aca_bridge_people=bridge_people,
        brackets_by_status=FEDERAL_BRACKETS_BASE_YEAR, brackets_mfj=FEDERAL_BRACKETS_MFJ,
        inflate_brackets_fn=inflate_brackets_fn, standard_deduction_fn=standard_deduction_fn,
        compute_fed_tax_fn=compute_fed_tax_fn, state_tax_estimate_fn=_state_tax_estimate,
    )
    moved = _legacy_pe.apply_roth_conversion(c, bal, conv_plan.amount, forced=conv_plan.forced, source_account=getattr(conv_plan, "source_account", ""), forced_sources=getattr(conv_plan, "forced_sources", []))
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

    # ── DAF in-kind contribution (appreciated securities) ────────────────
    # The shares leave the taxable accounts without being sold, so this is
    # a balance transfer, not a withdrawal: no cash proceeds, no gap
    # relief, and -- the whole point -- no realized capital gain. Reuse
    # withdraw_taxable_trust purely for its account selection: same
    # pro-rata ordering and same liquidity-reserve floor a cash draw would
    # honor, so a gift can't push the taxable bucket below its reserve.
    # Runs here, before the deduction stack below reads daf_contrib_yr, so
    # a gift the taxable accounts can't fully fund deducts only what was
    # actually given. ``daf_contrib_yr`` starts at whatever Stage 6 (spending/
    # RMD) already sized for a CASH DAF contribution -- this branch only
    # overwrites it for an in-kind (appreciated-securities) gift; a cash
    # contribution reaches here unchanged and flows straight through to the
    # AGI/tax stage's DAF deduction stack below.
    if daf_is_inkind and daf_gift_requested > 0:
        _daf_res = _legacy_pe.donate_taxable_in_kind(c, bal, year, daf_gift_requested, spend)
        _daf_by_account = dict(_daf_res.get('by_account', {}) or {})
        daf_contrib_yr = float(_daf_res.get('amount', 0.0) or 0.0)
        row['daf_inkind_yr'] = daf_contrib_yr
        row['daf_contrib_yr'] = daf_contrib_yr
        row['_daf_inkind_by_account'] = dict(_daf_by_account)
        # Reporting only: the tax the household never paid because the
        # embedded gain went to the charity instead of through a sale.
        row['daf_inkind_gain_avoided'] = float(_daf_res.get('gain_avoided', 0.0) or 0.0)
        # Never let a capped gift look like a full one. shortfall is the
        # reserve floor or thin long-term holdings biting; long_term_capped
        # says which, so the advisor can act on it.
        row['daf_inkind_shortfall'] = float(_daf_res.get('shortfall', 0.0) or 0.0)
        row['daf_inkind_long_term_capped'] = bool(_daf_res.get('long_term_capped', False))
        for _daf_aid, _daf_amt in _daf_by_account.items():
            _daf_amt = float(_daf_amt or 0.0)
            if _daf_amt <= 0:
                continue
            # Books as a transfer out, not a withdrawal: the account
            # roll-forward in sheets_qc_reference has to foot (Opening +
            # ... - Transfers Out - Withdrawals + Growth = Ending) and
            # _account_withdrawals stays reserved for cash withdrawals,
            # which is what the cash bridge and trust_wd both mean by it.
            _add_account_flow(row['_account_transfers_out'], _daf_aid, _daf_amt)
            # Deliberately do NOT spend bal_basis_free here: a donor gifts
            # the low-basis shares and keeps the stepped-up ones. Clamp
            # instead, so the tracked basis-free amount can never exceed
            # what is left in the account.
            if _daf_aid in bal_basis_free:
                bal_basis_free[_daf_aid] = min(bal_basis_free[_daf_aid],
                                               max(0.0, float(bal.get(_daf_aid, 0.0) or 0.0)))
        if daf_contrib_yr > 0:
            emit(EvTransfer(year, 'Taxable', 'DAF', daf_contrib_yr,
                            'DAF in-kind contribution (appreciated securities)'))

    return RothConversionResult(roth_conv=roth_conv, daf_contrib_yr=daf_contrib_yr)


class AgiTaxResult(NamedTuple):
    """Every value design-doc Stage 9 (AGI/Tax) produces that code outside
    it -- the still-inline withdrawal cascade, the already-extracted
    Stage 11 (AMT/equity-comp true-up) and Stage 12 (effective marginal
    rate), and the still-inline DAF-carryforward make-up pass that runs
    after the cascade -- reads as a bare local afterward.

    ``total_tax``/``fed_tax``/``taxable_inc``/``agi``/``state_tax`` are all
    provisional here: the withdrawal cascade (design doc Stage 10, out of
    scope for this extraction) further mutates ``agi``/``taxable_inc`` as
    its elective-withdrawal sizing loop runs, and finalizes ``total_tax``
    only after its own internal LTCG/NIIT fixed point converges. This
    function computes exactly the same provisional values the legacy
    engine did at this point in the year -- it does not attempt to move or
    resolve that finalization step.

    ``daf_deduction_carryforward`` is cross-year state, exactly like
    Stage 3's ``cst_balance``/``startup`` or Stage 6's
    ``spend_guardrail_state``: the caller must reassign its own local from
    this field on every call, or next year's carryforward-aging logic will
    not see this year's update.

    ``row`` is mutated in place, as elsewhere in this decomposition.
    """
    # Cross-year persisted state -- caller must reassign its own local.
    daf_deduction_carryforward: list

    # ACA/wellness fields Stage 9 revises in place after actual Roth
    # conversions are known (the documented read-then-patch cycle also
    # described in spending_and_rmd.py's ``SpendingAndRMDResult`` docstring).
    # Read again by the withdrawal cascade's total_cash_need calc.
    total_spend_need: float

    # AGI/tax core outputs, all provisional (see class docstring).
    ss_taxable: float
    ss_total: float
    agi: float
    taxable_inc: float
    fed_tax: float
    state_tax: float
    niit: float
    irmaa_yr: float
    irmaa_magi: float
    irmaa_magi_current: float
    n_medicare: float
    total_tax_pre_niit: float
    total_tax: float

    # Deduction-stack intermediates the withdrawal cascade's elective-IRA
    # sizing loop, the already-extracted Stage 12 (effective marginal rate),
    # and the later DAF carryforward make-up pass re-derive taxable_inc/
    # fed_tax from, or reuse directly.
    std_ded: float
    item_ded: float
    medical_ded: float
    medical_expense_yr: float
    ded: float
    char: float
    daf_agi_limit_pct: float
    daf_agi_limit: float
    daf_deduction_yr: float

    # State-tax income classification, read again by Stage 12 (effective
    # marginal rate).
    retirement_dist: float
    earned_net: float
    nonqual_ann: float
    h_over_65: bool

    # Home-sale LTCG resolution (already-extracted stage, called from here
    # in its original position) -- seeds the withdrawal cascade's LTCG
    # fixed point.
    home_sale_ltcg_gain: float
    home_sale_ltcg_tax: float

    # Gross/net income.
    gross_income: float
    net_income: float


def apply_agi_and_tax(
    c: dict[str, Any],
    bal: dict[str, float],
    row: dict[str, Any],
    rows: list,
    *,
    year: int,
    filing: str,
    h_age: float,
    w_age: float,
    n_alive: int,
    home_val: float,
    payroll_tax: float,
    net_earned_taxable: float,
    half_se_ded: float,
    sehi_ded: float,
    rmd_taxable_total: float,
    roth_conv: float,
    pension: float,
    wife_single_ann: float,
    wife_joint_ann: float,
    h_single_ann: float,
    h_joint_ann: float,
    h_ss: float,
    w_ss: float,
    note_int_yr: float,
    portfolio_ordinary: float,
    portfolio_qualified: float,
    portfolio_tax_exempt: float,
    equity_events: dict,
    di_taxable: float,
    qbi_ded: float,
    bridge_people: int,
    aca_ptc_pre_conversion: float,
    aca_ptc_yr: float,
    bridge_premium_gross: float,
    partb_yr: float,
    partd_yr: float,
    partg_yr: float,
    wellness_transaction_premium_yr: float,
    wellness_detail_budget_yr: float,
    wellness_premium_yr: float,
    wellness_base_yr: float,
    total_spend_need: float,
    spend: float,
    rec_extra: float,
    lump_yr: float,
    mort_yr: float,
    rent_yr: float,
    housing_operating_yr: float,
    re_tax_yr: float,
    ltc_prem_yr: float,
    wellness_shock_yr: float,
    heloc_interest_yr: float,
    heloc_repayment_principal_yr: float,
    business_expenses_yr: float,
    wellness_medical_yr: float,
    wellness_dental_yr: float,
    wellness_vision_yr: float,
    wellness_rx_otc_yr: float,
    wellness_other_yr: float,
    qcd_total_yr: float,
    daf_grant_yr: float,
    daf_contrib_yr: float,
    daf_deduction_carryforward: list,
    medicare_fraction_people: float,
    h_medicare_frac: float,
    w_medicare_frac: float,
    standard_deduction_fn: Callable[[int, str, Any, int], float],
    compute_fed_tax_fn: Callable[[float, int, str, Any], float],
    irmaa_surcharge_fn: Callable[[float, int, float, str], float],
    irmaa_tier_fn: Callable[[float, int, str], Any],
    emit: Callable[[Any], None],
) -> AgiTaxResult:
    """Design doc Stage 9 (AGI/Tax): computes ``agi``, ``taxable_inc``,
    ``fed_tax``, ``state_tax``, ``irmaa_yr``, re-derives ACA PTC after
    actual Roth conversions and patches Stage 6's spending fields in place,
    resolves the deferred home-sale LTCG tax (via the already-extracted
    :func:`resolve_home_sale_gain_tax`, called from here in its original
    relative position), and computes the spending-tier report (via the
    already-extracted :func:`compute_spend_by_tier`, likewise called from
    its original position).

    ``total_tax`` (and the ``agi``/``taxable_inc``/``fed_tax``/``state_tax``
    it is built from) is provisional: the still-inline withdrawal cascade
    (design doc Stage 10, a separate follow-up sub-project) both mutates
    ``agi``/``taxable_inc`` further as its elective-withdrawal sizing loop
    runs, and finalizes ``total_tax`` only after its own LTCG/NIIT fixed
    point converges. This function is unchanged in that regard from the
    legacy inline code -- it computes the same provisional values at the
    same point in the year, nothing more.

    Mutates ``row`` in place. Returns :class:`AgiTaxResult` for every value
    read as a bare local afterward -- see its docstring for the full
    inventory and why a named tuple.
    """
    # ── AGI / Tax ────────────────────────────────────────────────────────
    # Social Security taxation uses the statutory provisional-income phase-in,
    # not a flat 85% inclusion. High-income plans will still usually land at
    # the 85% cap, but lower-income gap years now calculate correctly.
    ws_taxable = wife_single_ann * c['wife_single'].get('exclusion_ratio', 1.0)
    hs_taxable = h_single_ann * c['h_single'].get('exclusion_ratio', 1.0)
    ss_total = h_ss + w_ss
    non_ss_income = (net_earned_taxable - half_se_ded - sehi_ded + rmd_taxable_total + roth_conv +
                     pension + ws_taxable + wife_joint_ann +
                     hs_taxable + h_joint_ann + note_int_yr +
                     portfolio_ordinary + portfolio_qualified +
                     equity_events['ordinary_income'] + di_taxable)
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
    # n_alive guard: the ACA recompute rebuilds wellness_base_yr and
    # total_spend_need from premium components, which would resurrect
    # spending the estate-mode block above just zeroed.
    if n_alive > 0 and abs(aca_ptc_final - aca_ptc_yr) > 1e-9:
        aca_ptc_yr = aca_ptc_final
        bridge_premium_yr = max(0.0, bridge_premium_gross - aca_ptc_yr)
        wellness_premium_yr = bridge_premium_yr + partb_yr + partd_yr + partg_yr
        if wellness_premium_yr <= 0:
            wellness_premium_yr = wellness_transaction_premium_yr
        wellness_base_yr = wellness_premium_yr + wellness_detail_budget_yr
        total_spend_need = (spend + rec_extra + lump_yr + mort_yr + row.get('home_improvement_yr', 0.0)
                            + rent_yr + housing_operating_yr + re_tax_yr + ltc_prem_yr
                            + wellness_base_yr + wellness_shock_yr
                            + heloc_interest_yr + heloc_repayment_principal_yr
                            + business_expenses_yr)
        row['aca_premium_tax_credit'] = aca_ptc_yr
        row['aca_ptc_loss_from_conversion'] = max(0.0, aca_ptc_pre_conversion - aca_ptc_yr)
        row['wellness_bridge_premium'] = bridge_premium_yr
        row['wellness_premiums_yr'] = wellness_premium_yr
        row['wellness_base_yr'] = wellness_base_yr
        row['total_spend'] = total_spend_need

    # ── Spending tiers (optimization-refactor Phase 0) ─────────────────
    # See compute_spend_by_tier's docstring (spending_tiers.py) for the
    # tier-split rules: purely additive reporting, never feeds back into
    # total_spend_need, withdrawals, or taxes.
    row['spend_by_tier'] = _compute_spend_by_tier(
        c,
        spend=spend,
        rec_extra=rec_extra,
        lump_yr=lump_yr,
        home_improvement_yr=row.get('home_improvement_yr', 0.0),
        mort_yr=mort_yr,
        re_tax_yr=re_tax_yr,
        rent_yr=rent_yr,
        housing_operating_yr=housing_operating_yr,
        heloc_interest_yr=heloc_interest_yr,
        heloc_repayment_principal_yr=heloc_repayment_principal_yr,
        wellness_premium_yr=wellness_premium_yr,
        wellness_medical_yr=wellness_medical_yr,
        wellness_dental_yr=wellness_dental_yr,
        wellness_vision_yr=wellness_vision_yr,
        wellness_rx_otc_yr=wellness_rx_otc_yr,
        wellness_other_yr=wellness_other_yr,
        wellness_base_yr=wellness_base_yr,
        ltc_prem_yr=ltc_prem_yr,
        wellness_shock_yr=wellness_shock_yr,
        business_expenses_yr=business_expenses_yr,
    )

    # SALT
    # Preliminary state tax estimate for SALT deduction (computed before final state_tax)
    # SALT estimate: use residence state rate (not hardcoded IL). Item 291
    # (2026-08-19): a Step 7.7 sweep flagged this fallback and neutralized
    # it, then reverted after a scope conflict with Class 1's own
    # deliberate, tested leniency design at this exact defensive layer --
    # see src.core.state_income_tax's matching revert and its comment for
    # the full reasoning. A real build can no longer reach this with an
    # unrecognized/blank state (require_residence_state_for_build, Class
    # 1); this fallback exists only for lower-level/defensive callers this
    # repo deliberately keeps lenient, out of scope for this ticket.
    _state_rules = STATE_TAX_RULES.get(state_for_year(c, year), STATE_TAX_RULES['Illinois'])
    il_tax_est = agi * _state_rules.get('rate', 0.0495)
    configured_prop_tax_yr = float(row.get('real_estate_tax_yr', 0.0) or 0.0)
    estimated_prop_tax_yr = (home_val * _state_rules.get('prop_rate', 0.0)) if home_val > 0 else 0.0
    prop_tax_yr = configured_prop_tax_yr if configured_prop_tax_yr > 0 else estimated_prop_tax_yr
    mort_interest_yr = float((c.get('mort_interest_schedule') or {}).get(year, 0.0) or 0.0)
    salt_gross = il_tax_est + prop_tax_yr
    salt = min(salt_gross, salt_cap(year, agi))
    # Item 4.1: QCD dollars already left AGI above (never a deduction);
    # treat char_low as the household's total giving intent and net the
    # QCD portion out of the itemizable cash-gift component so the same
    # dollars aren't counted twice.
    #
    # DAF grants get the identical treatment: a grant paid out of the DAF
    # balance satisfies part of the same char_low giving intent, but those
    # dollars were already deducted in the contribution year (and a grant
    # out of a DAF is never itself deductible), so leaving them in the
    # itemizable cash-gift component double-deducted them across the whole
    # grant window. Netting here, not in the cash bridge -- char_low is a
    # deduction input only and is not a cash-flow line, so a grant moves
    # no cash in this model.
    char = max(0, (c['char_low'] - qcd_total_yr - daf_grant_yr) - 0.005*agi)

    # Item 4.2 (P4): DAF contribution deduction, AGI-limited with a
    # 5-year carryforward (IRC 170(b)(1)(G)/(d)(1)) — replaces treating
    # daf_contrib_yr as an unlimited, un-tracked deduction. 60% of AGI
    # for a cash contribution, 30% for an appreciated-asset contribution
    # (daf_contribution_is_appreciated); recurring cash giving (char
    # above) is assumed too small relative to AGI to itself bump against
    # this limit, so the cap applies only to the DAF-specific dollars.
    # Expired carryforward entries (older than 5 succeeding tax years)
    # are dropped, not deducted — a lapsed deduction, not a client error.
    #
    # Known limitation shared with every deduction computed at this point
    # in the year (salt/char/mort_interest_yr are all in the same boat):
    # `agi` here is the *first-pass* estimate, before the elective-IRA-
    # withdrawal sizing loop further down runs. For a retiree with no
    # guaranteed income yet (pre-SS, pre-RMD, living entirely off
    # discretionary portfolio withdrawals), that first-pass AGI can be
    # near zero even though their real, final-year AGI (after the engine
    # sizes the withdrawal actually needed to cover spending) is
    # substantial — understating the 60%/30% limit and potentially
    # letting real carryforward capacity lapse unused. char/salt/mortgage
    # interest absorb this as a one-year approximation error with no
    # lasting consequence; DAF's carryforward is the one place it can
    # cost a taxpayer a permanent deduction, so — unlike salt/char/
    # mortgage interest, which are left as a one-year approximation —
    # a narrow make-up pass re-evaluates unused DAF carryforward against
    # the converged AGI once the elective-withdrawal cascade settles (see
    # "Item 4.2 follow-up" below, after Priority 4b). It only recognizes
    # additional deduction (agi rises monotonically across the cascade,
    # never falls) and never touches salt or mort_interest_yr (both stay
    # at their first-pass values) — the full fix of recomputing this
    # entire block after AGI converges would touch the same iterative
    # pass A2/A3 already treat as high-risk, and is not done here.
    daf_deduction_carryforward = [
        entry for entry in daf_deduction_carryforward if entry[0] + 5 >= year
    ]
    daf_pool = list(daf_deduction_carryforward)
    if daf_contrib_yr > 1e-6:
        daf_pool.append([year, daf_contrib_yr])
    daf_available_this_year = sum(amt for _yr, amt in daf_pool)
    daf_agi_limit_pct = 0.30 if c.get('daf_contribution_is_appreciated', False) else 0.60
    daf_agi_limit = max(0.0, agi) * daf_agi_limit_pct
    daf_deduction_yr = min(daf_available_this_year, daf_agi_limit)
    # Consume oldest-origin dollars first (they expire soonest); whatever
    # of each entry the cap doesn't reach keeps its original origin year.
    remaining_budget = daf_deduction_yr
    new_carryforward = []
    for origin_year, amt in daf_pool:
        used = min(amt, remaining_budget)
        remaining_budget -= used
        leftover = amt - used
        if leftover > 1e-6:
            new_carryforward.append([origin_year, leftover])
    daf_deduction_carryforward = new_carryforward
    row['daf_deduction_yr'] = daf_deduction_yr
    row['daf_deduction_carryforward'] = sum(amt for _yr, amt in daf_deduction_carryforward)
    # Split reporting so the recurring cash-gift component stays visible
    # separately from the DAF slice -- without it the grant netting above
    # is invisible to callers and untestable except through taxable_inc.
    row['charitable_cash_deduction_yr'] = char
    char += daf_deduction_yr
    row['charitable_deduction_yr'] = char

    # Standard vs itemized
    n65 = (1 if h_age >= 65 else 0) + (1 if w_age >= 65 else 0)
    senior_bonus = senior_bonus_deduction(year, filing, agi, n65)
    std_ded = standard_deduction_fn(year, filing, c['brk_inf'], n65) + senior_bonus
    # Sec 213 medical expense deduction: Medicare/bridge premiums, wellness
    # detail spend (medical/dental/vision/Rx), LTC insurance premiums, and
    # any LTC cost shock are all qualifying medical expenses; only the
    # amount above 7.5% of AGI is deductible. wellness_shock_yr already
    # flows into total_spend_need as a cash cost (line ~1376/1527) -- this
    # is the first place it also counts toward the tax deduction it can
    # legitimately generate.
    medical_expense_yr = wellness_premium_yr + wellness_detail_budget_yr + wellness_shock_yr + ltc_prem_yr
    medical_ded = max(0.0, medical_expense_yr - 0.075 * max(0.0, agi))
    item_ded = salt + char + mort_interest_yr + medical_ded
    row['property_tax_for_salt'] = prop_tax_yr
    row['salt_gross'] = salt_gross
    row['mortgage_interest_deduction'] = mort_interest_yr
    row['senior_bonus_deduction'] = senior_bonus
    row['medical_expense_deduction'] = medical_ded
    ded = max(std_ded, item_ded)
    if c['qbi_elig']:
        ded += qbi_ded

    taxable_inc = max(0, agi - ded)
    fed_tax = compute_fed_tax_fn(taxable_inc, year, filing, c['brk_inf'])
    # Classify income for state taxation (retirement income may be exempt)
    qual_ann, nonqual_ann = _qualified_and_nonqualified_annuity_income(c, year)
    retirement_dist = rmd_taxable_total + qual_ann  # pension already included in qual_ann if qualified
    earned_net = max(0, net_earned_taxable - half_se_ded - sehi_ded)
    h_over_65 = h_age >= 65 or w_age >= 65
    state_tax = state_income_tax(state_for_year(c, year), earned_net, retirement_dist,
                                 ss_taxable, note_int_yr + portfolio_ordinary + portfolio_qualified, nonqual_ann,
                                 roth_conv, year, h_over_65, filing=filing, brk_inf=c['brk_inf'])

    # NIIT placeholder — computed after trust draws where ltcg_gain is available
    niit = 0.0
    row['_niit_ws_taxable'] = ws_taxable  # stash for later NIIT calc
    row['_niit_hs_taxable'] = hs_taxable

    # IRMAA uses the statutory two-year MAGI lookback when prior rows exist.
    # The surcharge is billed monthly alongside Medicare enrollment, so it
    # is prorated in the transition year with the same fraction used for
    # Part B/D/G premiums above (medicare_fraction_people).
    n_medicare = medicare_fraction_people
    # P12 second half (item 4.5): an approved Form SSA-44 life-changing-event
    # appeal suppresses the IRMAA *surcharge* only (the base Part B/D/G
    # premiums above are still owed) for that member from the stated year
    # onward. Modeled per-member since one spouse's appeal doesn't excuse
    # the other's surcharge.
    h_ssa44_relief_yr = c.get('h_ssa44_relief_year')
    w_ssa44_relief_yr = c.get('w_ssa44_relief_year')
    h_ssa44_active = h_ssa44_relief_yr is not None and year >= int(h_ssa44_relief_yr)
    w_ssa44_active = w_ssa44_relief_yr is not None and year >= int(w_ssa44_relief_yr)
    if h_ssa44_active or w_ssa44_active:
        n_medicare = (0.0 if h_ssa44_active else h_medicare_frac) + (0.0 if w_ssa44_active else w_medicare_frac)
    row['irmaa_ssa44_relief_active'] = h_ssa44_active or w_ssa44_active
    # Seed plan years 1-2 (no projected AGI row exists yet for their
    # lookback target year) with the household's actual historical MAGI
    # when provided (item 2.6), instead of always falling back to this
    # year's own AGI. Blank/absent inputs (e.g. a saved plan predating
    # these fields) leave the entry out of the dict, so
    # irmaa_lookback_magi() falls back to current-year AGI unchanged.
    _irmaa_historical_magi = {
        2: c.get('irmaa_actual_magi_2yr_prior'),
        1: c.get('irmaa_actual_magi_1yr_prior'),
    }
    irmaa_magi = irmaa_lookback_magi(rows, irmaa_magi_current, c.get('irmaa_lookback_years', 2),
                                      historical_magi=_irmaa_historical_magi)
    row['irmaa_magi_used'] = irmaa_magi
    irmaa_yr = irmaa_surcharge_fn(irmaa_magi, year, n_medicare, filing) if n_medicare > 0 else 0.0
    row['irmaa_tier'] = irmaa_tier_fn(irmaa_magi, year, filing)

    # Resolve the deferred home-sale taxable-gain tax (extracted stage):
    # apply_home_sale() (earlier this same year) computed the gain but
    # could not tax it without taxable_inc, which only exists here.
    # See home_sale.py's resolve_home_sale_gain_tax() docstring.
    _stage9_home_sale = _resolve_home_sale_gain_tax(c, row, year=year, taxable_inc=taxable_inc)
    home_sale_ltcg_gain = _stage9_home_sale.gain
    home_sale_ltcg_tax = _stage9_home_sale.tax
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

    return AgiTaxResult(
        daf_deduction_carryforward=daf_deduction_carryforward,
        total_spend_need=total_spend_need,
        ss_taxable=ss_taxable,
        ss_total=ss_total,
        agi=agi,
        taxable_inc=taxable_inc,
        fed_tax=fed_tax,
        state_tax=state_tax,
        niit=niit,
        irmaa_yr=irmaa_yr,
        irmaa_magi=irmaa_magi,
        irmaa_magi_current=irmaa_magi_current,
        n_medicare=n_medicare,
        total_tax_pre_niit=total_tax_pre_niit,
        total_tax=total_tax,
        std_ded=std_ded,
        item_ded=item_ded,
        medical_ded=medical_ded,
        medical_expense_yr=medical_expense_yr,
        ded=ded,
        char=char,
        daf_agi_limit_pct=daf_agi_limit_pct,
        daf_agi_limit=daf_agi_limit,
        daf_deduction_yr=daf_deduction_yr,
        retirement_dist=retirement_dist,
        earned_net=earned_net,
        nonqual_ann=nonqual_ann,
        h_over_65=h_over_65,
        home_sale_ltcg_gain=home_sale_ltcg_gain,
        home_sale_ltcg_tax=home_sale_ltcg_tax,
        gross_income=gross_income,
        net_income=net_income,
    )
