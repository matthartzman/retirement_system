from __future__ import annotations

from typing import Any, Callable, NamedTuple

from .. import core as _aa  # consolidated from account_access
from ..equity_comp import equity_comp_year_events as _equity_comp_year_events
from ..planning_engines import EvIncome, annuity_cash_income


class IncomeResult(NamedTuple):
    """Every value this stage produces that later stages (same iteration)
    read as a bare local variable, returned as one typed bundle.

    ``bal`` and ``row`` are dicts mutated in place through the reference,
    the same way Stage 3 (``appreciation_divorce_qlac``) mutates ``bal``
    and the ``account_*`` flow dicts: every row key this stage writes
    (``row['earned']``, ``row['payroll_tax']``, ``row['h_ss']``,
    ``row['k401_contrib']``, the annuity fields via ``row.update(...)``,
    etc. -- about twenty keys, several only written when a condition
    fires) is written directly onto the passed-in ``row`` inside this
    function, so none of them need to travel back through the return
    value. Only the values genuinely consumed as bare Python locals by
    later stages *in the same year* -- spending, Roth conversion sizing,
    AGI/tax, the withdrawal cascade, the equity-comp/AMT post-pass --
    need to come back explicitly, because Python does not propagate a
    reassigned scalar parameter back to the caller.

    A plain tuple would invite a positional mix-up among fields that are
    all floats and easy to transpose (e.g. ``h_ss``/``w_ss``,
    ``half_se_ded``/``sehi_ded``) with real tax consequences that a
    snapshot/golden-master test might not surface for years. NamedTuple
    keeps the seventeen fields named and order-independent at zero
    runtime cost, without introducing the engine-wide ``YearState`` this
    decomposition is deliberately deferring.
    """
    earned_base: float
    net_earned_taxable: float
    half_se_ded: float
    sehi_ded: float
    qbi_ded: float
    payroll_tax: float
    business_expenses_yr: float
    h_ss: float
    w_ss: float
    pension: float
    wife_single_ann: float
    wife_joint_ann: float
    h_single_ann: float
    h_joint_ann: float
    equity_events: dict
    di_taxable: float
    di_cash: float


def apply_income(
    c: dict[str, Any],
    *,
    year: int,
    h_age: int,
    w_age: int,
    h_alive: bool,
    w_alive: bool,
    bal: dict[str, float],
    row: dict[str, Any],
    note_princ_yr: float,
    note_int_yr: float,
    equity_on: bool,
    disability_on: bool,
    sehi_deduction_source_amount: Callable[..., float],
    ss_ratio: Callable[[int, int], float],
    ss_first_claim_year_month_fraction: Callable[[int, int, Any], float],
    ss_claim_factor: Callable[..., float],
    ss_spousal_excess_factor: Callable[..., float],
    ss_funding_factor: Callable[[int], float],
) -> IncomeResult:
    """Earned income, payroll/SE tax, 401(k)/HSA contributions, Social
    Security (incl. survivor benefit), annuity income, and note income --
    the largest single block in the legacy per-year loop, in original
    order:

    1. **Earned income** -- wages/SE/S-corp income, with scenario overrides
       for extension years and a live-plan YTD blend override, then halted
       and replaced by disability-insurance benefit income if a configured
       disability event is active for this year (an advanced-module,
       per-year event embedded here rather than a genuinely separable
       stage -- see the module-level note below).
    2. **Payroll / self-employment tax** -- sole-prop SE tax or S-corp
       payroll (employee + employer FICA), Additional Medicare tax, and
       the half-SE-tax / SEHI / QBI deductions, producing
       ``net_earned_taxable`` -- the earned-income figure (net of real
       Schedule C business expenses) that actually drives AGI, not the
       gross ``earned_base``.
    3. **401(k) contribution** -- deposited to the first owner-0 401(k)/
       pre-tax account, plus the one-time workplace-plan rollover to an
       IRA in the configured rollover year.
    4. **HSA contribution** -- deposited to the first owner-0 HSA account.
    5. **Social Security** -- each spouse's claimed benefit (direct
       SSA-quoted table lookup, or reduction/delayed-credit factor off
       PIA), the dual-entitlement excess-spousal top-up, the survivor
       benefit take-over after a death, and the SS funding-cut haircut.
    6. **Annuity income** -- pension, single-life, joint-life, and QLAC
       annuity cash flows, death-governed (folded into the existing
       single/joint annuity slots per #295, not tracked separately).
    7. **Note income** -- this year's note principal/interest, already
       computed by the home-sale stage just before this one; passed in
       read-only and written straight onto ``row`` here, matching the
       original code's placement of those two lines inside this section.

    ``bal`` (401k/HSA deposits) and ``row`` (every per-year reporting
    field this stage owns, including the account-flow sub-dicts hanging
    off it) are mutated in place -- dict mutation crosses the function
    boundary naturally in Python, exactly as with Stage 3's ``bal`` and
    ``account_*`` dicts. The seventeen values later stages read as bare
    locals in the same iteration come back via :class:`IncomeResult`;
    see its docstring for why a named tuple.

    The Social Security age-factor/date-math helpers (``ss_claim_factor``,
    ``ss_spousal_excess_factor``, ``ss_ratio``,
    ``ss_first_claim_year_month_fraction``, ``ss_funding_factor``) and the
    SEHI-source helper (``sehi_deduction_source_amount``) are passed in
    rather than reimplemented here: in the legacy engine they are nested
    closures over ``c`` (and, transitively, over sibling closures like
    ``_wellness_premium_for_age``/``_path_ratio``) with no dependency on
    any loop-mutable state, so injecting them keeps this a pure move --
    duplicating tax/SSA date-math into a second implementation would risk
    silent drift that a golden-master test pinning only aggregate scalars
    might not catch.

    Equity-comp and disability-insurance per-year events are genuinely
    embedded here, not bolted on: disability directly zeroes
    ``earned_base`` and substitutes benefit income for the rest of this
    stage's SE/payroll-tax math to run against, so there is no clean seam
    to split it into its own function without threading that same
    zeroed-``earned_base`` handoff back out and in again. Both still call
    the existing, separately-owned helpers (``equity_comp_year_events``,
    imported here unchanged; the disability math was never a standalone
    helper in the legacy engine, only inline per-year logic) exactly as
    before -- this only relocates the orchestration.
    """
    # ── Earned income ──────────────────────────────────────────────────
    if c['earn_start'] <= year <= c['earn_end']:
        base_earn_end = c.get('base_earn_end', c['earn_end'])
        if year > base_earn_end:
            ext_growth  = c.get('scen_retire_inc_growth', c['earn_inc'])
            ext_base    = c['earned'] * (1 + c['earn_inc']) ** (base_earn_end - c['earn_start'])
            earned_base = ext_base * (1 + ext_growth) ** (year - base_earn_end)
        else:
            earned_base = c['earned'] * (1 + c['earn_inc']) ** (year - c['earn_start'])
    else:
        earned_base = 0.0
    earned_base = c.get('ytd_blend_earned_override', {}).get(year, earned_base)

    # ── Advanced modules: per-year tax events (all zero unless enabled) ───
    equity_events = {'ordinary_income': 0.0, 'amt_preference': 0.0, 'ltcg_gain': 0.0, 'cash_proceeds': 0.0}
    if equity_on:
        equity_events = _equity_comp_year_events(c.get('equity_comp', []), year, c['plan_start'])
    di_taxable = 0.0
    di_cash = 0.0
    if disability_on:
        _di = c.get('disability', {}) or {}
        _sim = int(_di.get('simulate_year', 0) or 0)
        _pols = _di.get('policies', []) or []
        if _sim and _pols:
            _bp = max((int(p.get('benefit_period_years', 0) or 0) for p in _pols), default=0)
            if _sim <= year < _sim + max(1, _bp):
                # Disability halts earned income; the DI benefit replaces it.
                earned_base = 0.0
                _annual = sum(float(p.get('monthly_benefit', 0.0) or 0.0) for p in _pols) * 12.0
                if year == _sim:
                    _elim = max((int(p.get('elimination_days', 0) or 0) for p in _pols), default=0)
                    _annual *= max(0.0, 365.0 - _elim) / 365.0
                di_cash = _annual
                # Benefit is taxable ordinary income when funded with pre-tax premium.
                if any(p.get('premium_pre_tax') for p in _pols):
                    di_taxable = _annual
                row['disability_benefit'] = _annual
                row['disability_benefit_taxable'] = di_taxable

    row['earned'] = earned_base
    if equity_events['ordinary_income'] > 0:
        row['equity_comp_ordinary_income'] = equity_events['ordinary_income']
    if equity_events['amt_preference'] > 0:
        row['equity_comp_amt_preference'] = equity_events['amt_preference']

    # ── Payroll / self-employment tax ───────────────────────────────────
    se_tax = 0.0; half_se_ded = 0.0; sehi_ded = 0.0; qbi_ded = 0.0
    payroll_tax = 0.0
    # net_earned_taxable is the earned-income figure that should actually
    # drive AGI/ordinary-income-tax and cash flow -- gross earned_base net
    # of the real Schedule C business expenses / home office deduction
    # (biz_exp/home_off), which previously only reduced the SE-tax and QBI
    # bases and never reduced AGI or appeared as a cash outflow anywhere.
    net_earned_taxable = 0.0
    business_expenses_yr = 0.0
    if earned_base > 0:
        if c['entity'] == 'sole_prop':
            net_se   = earned_base - c['biz_exp'] - c['home_off']
            se_base  = net_se * c['se_factor']
            ss_se    = min(se_base, c['ss_wage_base']) * c['ss_se_rate']
            med_se   = se_base * c['med_se_rate']
            se_tax   = ss_se + med_se
            if c['se_half_ded']:
                half_se_ded = se_tax / 2
            sehi_source = sehi_deduction_source_amount(year, h_age, w_age, h_alive, w_alive)
            sehi_ded = min(sehi_source, net_se)
            if c['qbi_elig']:
                qbi_base = net_se - half_se_ded - sehi_ded
                qbi_ded  = qbi_base * 0.20
            payroll_tax = se_tax
            net_earned_taxable = net_se
            business_expenses_yr = c['biz_exp'] + c['home_off']
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
            # SEHI: deducted via W-2 box 1 treatment. Real law requires the
            # premium to actually be added to the shareholder-employee's W-2
            # Box 1 wages for the personal SEHI deduction to be allowed at
            # all; when sehi_added_to_w2 is off, no deduction is allowed.
            sehi_source = sehi_deduction_source_amount(year, h_age, w_age, h_alive, w_alive)
            sehi_ded = min(sehi_source, salary + distribution) if c.get('scorp_sehi_on_w2', True) else 0.0
            # QBI on distribution (salary excluded from QBI base)
            if c['qbi_elig']:
                qbi_base = distribution - sehi_ded
                qbi_ded  = max(0, qbi_base * 0.20)
            # IL corporate surcharge on distributable income
            # (already captured in state_tax via AGI; no separate payroll item)
            net_earned_taxable = salary + distribution
            business_expenses_yr = c['biz_exp'] + c['home_off']

        # Additional Medicare tax applies to Medicare wages / SE earnings,
        # not to S-corp distributions.
        add_med_base = se_base if c['entity'] == 'sole_prop' else salary
        if add_med_base > c['add_med_thr']:
            payroll_tax += (add_med_base - c['add_med_thr']) * c['add_med_rate']

    row['sehi_deduction_source'] = sehi_deduction_source_amount(year, h_age, w_age, h_alive, w_alive) if earned_base > 0 else 0.0
    row['payroll_tax'] = payroll_tax
    row['business_expenses_yr'] = business_expenses_yr

    # Remaining-year proration for the current calendar year (see
    # ytd_projection_blend.py) — today's live balance already reflects
    # whatever contributions have actually happened so far this year, so
    # only the remaining fraction of the year's contribution is added.
    _contrib_proration = c.get('ytd_blend_contrib_proration', {}).get(year, 1.0)

    # ── 401k contribution ───────────────────────────────────────────────
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
    # Both sides are resolved with accounts() rather than first_account():
    # first_account() falls back to all_acct_ids[0] when nothing matches, so
    # a household with no owner-0 401(k) — or no owner-0 traditional IRA —
    # would silently resolve to an arbitrary account of any tax type, and
    # this block would move a whole balance into (or out of) e.g. checking.
    # The destination also excludes the source: with a 401(k) and no IRA the
    # pre-tax fallback used to resolve back to the source account, and
    # crediting then zeroing the same account destroyed the balance outright.
    _k401_ids = _aa.accounts(c, owner_idx=0, acct_type='401k')
    _k401_id = _k401_ids[0] if _k401_ids else None
    _dest_ids = list(_aa.accounts(c, owner_idx=0, acct_type='traditional_ira')) or [
        _a for _a in _aa.accounts(c, owner_idx=0, tax='pre_tax') if _a != _k401_id]
    _ira_dest = _dest_ids[0] if _dest_ids else None
    _rolled = False
    if year == ROLLOVER_401K_YEAR and _k401_id and _ira_dest and bal.get(_k401_id, 0) > 0:
        amt = bal.get(_k401_id, 0)
        bal[_ira_dest] = bal.get(_ira_dest, 0) + amt
        bal[_k401_id] = 0.0
        _add_account_flow(row['_account_transfers_out'], _k401_id, amt)
        _add_account_flow(row['_account_transfers_in'], _ira_dest, amt)
        _rolled = True
    row['k401_rollover'] = 1.0 if _rolled else 0.0

    # ── HSA contribution ─────────────────────────────────────────────────
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

    # ── Social Security ──────────────────────────────────────────────────
    # Each spouse's benefit table (ss_benefit_age_62..70) holds the actual
    # SSA-quoted monthly amount for every claim age - real government
    # figures, not back-solved estimates. The claimed amount is a direct
    # table lookup at the configured claim age, so it always moves the
    # correct direction (lower before FRA, higher after) by construction.
    h_claim_age = max(62, min(70, int(c.get('h_ss_claim_age', c.get('ss_claim_age', 70)) or 70)))
    w_claim_age = max(62, min(70, int(c.get('w_ss_claim_age', c.get('ss_claim_age', 70)) or 70)))
    # System review 2026-09-07 N2: h_ss_claim_year/w_ss_claim_year are
    # already the precise year derived from claim_date (when present) --
    # deriving h_ss_yr as h_dob_yr + h_claim_age instead threw that
    # precision away by round-tripping back through a whole-year age.
    # Falls back to the age-derived year for callers that never ran
    # through data_io._ss_claim_from_date_or_age (e.g. a bare synthetic
    # config dict in a unit test).
    h_ss_yr = int(c.get('h_ss_claim_year') or (c['h_dob_yr'] + h_claim_age))
    w_ss_yr = int(c.get('w_ss_claim_year') or (c['w_dob_yr'] + w_claim_age))
    # Fractional claim age (e.g. 66.33), used only for the SSA
    # reduction/delayed-credit factor below, which already interpolates
    # by month -- it was simply never given anything but a whole-year
    # age before. The whole-year h_claim_age/w_claim_age above is kept
    # for the benefit-table lookup, which is genuinely keyed on whole
    # SSA-quoted ages.
    h_claim_age_precise = float(c.get('h_ss_claim_age_precise', h_claim_age) or h_claim_age)
    w_claim_age_precise = float(c.get('w_ss_claim_age_precise', w_claim_age) or w_claim_age)
    h_benefit_table = c.get('h_ss_benefit_table', {}) or {}
    w_benefit_table = c.get('w_ss_benefit_table', {}) or {}
    h_pia = float(c.get('h_ss_pia', 0.0) or 0.0) or h_benefit_table.get(67, 0.0)
    w_pia = float(c.get('w_ss_pia', 0.0) or 0.0) or w_benefit_table.get(67, 0.0)
    h_fra_override = c.get('h_fra_age')
    w_fra_override = c.get('w_fra_age')
    # Prefer the real SSA-quoted table entry for the chosen claim age. If
    # that specific age wasn't entered, derive it from the FRA/PIA amount
    # via the SSA reduction/delayed-credit factor instead of defaulting
    # flatly to the FRA amount (which is only correct when claiming at FRA).
    # h_monthly_claim / w_monthly_claim are each spouse's OWN reduced (or
    # delayed-credited) retirement benefit — the record used both for the
    # living benefit below and, unchanged, for the survivor benefit further
    # down.  The spousal excess is added only to the living benefit; it is
    # deliberately NOT baked into these records (a survivor benefit derives
    # from the deceased's own retirement record, never their spousal top-up).
    h_monthly_claim = h_benefit_table.get(h_claim_age) or (h_pia * ss_claim_factor(h_claim_age_precise, c['h_dob_yr'], h_fra_override))
    w_monthly_claim = w_benefit_table.get(w_claim_age) or (w_pia * ss_claim_factor(w_claim_age_precise, c['w_dob_yr'], w_fra_override))
    spousal_on = bool(c.get('spousal_benefits_enabled', True))

    # Excess-spousal benefit (SSA dual-entitlement method).  A claimant who is
    # also entitled to their own retirement benefit receives their own reduced
    # benefit PLUS the excess spousal amount:
    #     own_reduced + max(0, 0.5*worker_PIA - own_PIA) * excess_factor
    # This is NOT max(own, 0.5*worker_PIA): the greater-of form would discard
    # the claimant's permanent early-claim reduction on their own record and
    # overstate the benefit for life.  The excess is computed off PIAs (full,
    # unreduced benefits), floored at zero when the claimant's own PIA already
    # meets/exceeds half the worker's PIA, and only THEN reduced on the
    # spousal schedule (ss_spousal_excess_factor, no delayed credits).  Two
    # gates apply: (1) the WORKER must have actually filed — the spousal
    # amount cannot be paid until the year the worker claims — and (2) both
    # spouses must be alive (once a spouse dies the survivor logic below
    # governs).  The reduction factor is set by the claimant's age when the
    # spousal benefit first becomes payable, i.e. the later of their own
    # filing year and the worker's filing year.
    h_ss = 0.0
    if h_alive and year >= h_ss_yr:
        h_monthly = h_monthly_claim
        if spousal_on and w_alive and year >= w_ss_yr:
            _h_sp_start_age = max(h_ss_yr, w_ss_yr) - c['h_dob_yr']
            _h_sp_factor = ss_spousal_excess_factor(_h_sp_start_age, c['h_dob_yr'], h_fra_override)
            h_monthly += max(0.0, 0.5 * w_pia - h_pia) * _h_sp_factor
        h_ss = h_monthly * 12 * ss_ratio(year, h_ss_yr) * ss_first_claim_year_month_fraction(year, h_ss_yr, c.get('h_ss_claim_month', c.get('h_dob_month')))
    w_ss = 0.0
    if w_alive and year >= w_ss_yr:
        w_monthly = w_monthly_claim
        if spousal_on and h_alive and year >= h_ss_yr:
            _w_sp_start_age = max(w_ss_yr, h_ss_yr) - c['w_dob_yr']
            _w_sp_factor = ss_spousal_excess_factor(_w_sp_start_age, c['w_dob_yr'], w_fra_override)
            w_monthly += max(0.0, 0.5 * h_pia - w_pia) * _w_sp_factor
        w_ss = w_monthly * 12 * ss_ratio(year, w_ss_yr) * ss_first_claim_year_month_fraction(year, w_ss_yr, c.get('w_ss_claim_month', c.get('w_dob_month')))

    # SS survivor benefit is symmetrical: survivor receives the larger
    # claimed benefit record (subject to survivor percentage), regardless of
    # which spouse dies first.
    if not h_alive and w_alive and year > c['h_death_yr']:
        if c.get('survivor_benefit_uses_deceased_claim_age', True):
            h_record = h_monthly_claim
        else:
            h_record = h_benefit_table.get(70, h_pia)
        h_ss_at_death = h_record * 12 * ss_ratio(c['h_death_yr'], h_ss_yr) if c['h_death_yr'] >= h_ss_yr else 0
        w_ss_at_death = w_monthly_claim * 12 * ss_ratio(c['h_death_yr'], w_ss_yr) if c['h_death_yr'] >= w_ss_yr else 0
        w_ss = max(w_ss, h_ss_at_death * c['ss_surv'], w_ss_at_death)
        h_ss = 0
    if not w_alive and h_alive and year > c['w_death_yr']:
        if c.get('survivor_benefit_uses_deceased_claim_age', True):
            w_record = w_monthly_claim
        else:
            w_record = w_benefit_table.get(70, w_pia)
        w_ss_at_death = w_record * 12 * ss_ratio(c['w_death_yr'], w_ss_yr) if c['w_death_yr'] >= w_ss_yr else 0
        h_ss_at_death = h_monthly_claim * 12 * ss_ratio(c['w_death_yr'], h_ss_yr) if c['w_death_yr'] >= h_ss_yr else 0
        h_ss = max(h_ss, w_ss_at_death * c['ss_surv'], h_ss_at_death)
        w_ss = 0

    row['h_ss_claim_age_used'] = h_claim_age
    row['w_ss_claim_age_used'] = w_claim_age

    _ss_funding_factor_yr = ss_funding_factor(year)
    if _ss_funding_factor_yr != 1.0:
        h_ss *= _ss_funding_factor_yr
        w_ss *= _ss_funding_factor_yr
    row['ss_funding_factor'] = _ss_funding_factor_yr
    row['ss_funding_discount_pct'] = max(0.0, 1.0 - _ss_funding_factor_yr)
    row['h_ss'] = h_ss
    row['w_ss'] = w_ss

    # ── Annuity income (death-governed) ─────────────────────────────────
    pension = annuity_cash_income(c['wife_pension'], year) if w_alive else 0
    # #295: a QLAC is a deferred single-life annuity purchased with
    # qualified (pre-tax) dollars -- same shape and tax treatment
    # (100% taxable, no cash/dividend component) as this household's
    # existing Single Annuity slot, so its income is folded directly
    # into wife_single_ann/h_single_ann: every downstream consumer of
    # that value (AGI, ACA premium credit, federal/state tax, terminal
    # net worth's annuity PV) already treats it as "this person's fully
    # taxable single-life annuity income for the year" and needs no
    # separate wiring. wife_qlac_ann/h_qlac_ann are still tracked
    # separately on the row for reporting visibility.
    wife_qlac_ann = annuity_cash_income(c['wife_qlac'], year) if (w_alive and c['wife_qlac'].get('enabled')) else 0
    h_qlac_ann = annuity_cash_income(c['h_qlac'], year) if (h_alive and c['h_qlac'].get('enabled')) else 0
    wife_single_ann = (annuity_cash_income(c['wife_single'], year) if w_alive else 0) + wife_qlac_ann
    wife_joint_ann  = (annuity_cash_income(c['wife_joint'], year)
                      if (w_alive or h_alive) else 0)
    if not w_alive and h_alive:
        wife_joint_ann *= c['js_pct']
    h_single_ann    = (annuity_cash_income(c['h_single'], year) if h_alive else 0) + h_qlac_ann
    h_joint_ann     = (annuity_cash_income(c['h_joint'], year)
                      if (h_alive or w_alive) else 0)
    if not h_alive and w_alive:
        h_joint_ann *= c['js_pct']

    row.update({'pension': pension,
                'wife_single_ann': wife_single_ann,
                'wife_joint_ann': wife_joint_ann,
                'h_single_ann': h_single_ann,
                'h_joint_ann': h_joint_ann,
                'wife_qlac_ann': wife_qlac_ann,
                'h_qlac_ann': h_qlac_ann})

    # ── Note income ──────────────────────────────────────────────────────
    row['note_princ'] = note_princ_yr
    row['note_int']   = note_int_yr

    return IncomeResult(
        earned_base=earned_base,
        net_earned_taxable=net_earned_taxable,
        half_se_ded=half_se_ded,
        sehi_ded=sehi_ded,
        qbi_ded=qbi_ded,
        payroll_tax=payroll_tax,
        business_expenses_yr=business_expenses_yr,
        h_ss=h_ss,
        w_ss=w_ss,
        pension=pension,
        wife_single_ann=wife_single_ann,
        wife_joint_ann=wife_joint_ann,
        h_single_ann=h_single_ann,
        h_joint_ann=h_joint_ann,
        equity_events=equity_events,
        di_taxable=di_taxable,
        di_cash=di_cash,
    )


def _add_account_flow(target: dict[str, float], acct: str | None, amount: float) -> None:
    amount = float(amount or 0.0)
    if acct and abs(amount) > 1e-9:
        target[acct] = target.get(acct, 0.0) + amount


def _tag_deposit_source(target: dict[str, Any], acct: str | None, source: str, amount: float) -> None:
    """Record a human-readable source label for a deposit, alongside the
    existing flat account-deposits total (which remains unchanged and is
    still the authoritative per-account aggregate for reconciliation).
    """
    amount = float(amount or 0.0)
    if acct and abs(amount) > 1e-9:
        sources = target.setdefault('_account_deposit_sources', {}).setdefault(acct, [])
        sources.append({'source': source, 'amount': amount})
