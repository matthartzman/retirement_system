from __future__ import annotations

from typing import Any, Callable, NamedTuple

from ..planning_engines import FEDERAL_BRACKETS_MFJ, marginal_rate
from .. import planning_engines as _legacy_pe
from .. import tax_kernel as _tk


class Priority3Result(NamedTuple):
    """Everything Priority 3 (sub-stage #4) produces that code outside it
    still needs.

    ``top_24_yr``/``irmaa_thr_yr``/``marg``/``ira_taxable_inc_orig``/
    ``ira_retirement_dist_orig`` are only ever computed when ``gap > 0``
    entering this sub-stage (``None`` otherwise, matching the original
    inline code's ``if gap > 0:`` guard exactly -- the still-inline
    sub-stage #6 and the paired Priority 4b sub-stage (#7, see
    ``apply_priority_4b_final_pretax_draw`` below) both reuse these
    unchanged rather than recomputing them, so they must be threaded
    through the caller rather than dropped.

    ``ira_wd``/``h_ira_elective``/``w_ira_elective``/``pretax_by_account``/
    ``ira_tax_true_up_iterations`` are cumulative across Priority 3 *and*
    Priority 4b (the same locals are reused, not reset, when #7 runs) --
    the caller must pass this result's copies into #7 rather than
    reinitializing them. Python scalar reassignment inside this function
    does not propagate to the caller, so every one of these must come
    back explicitly rather than being assumed to persist.
    """
    gap: float
    agi: float
    taxable_inc: float
    fed_tax: float
    state_tax: float
    total_tax_pre_niit: float
    irmaa_magi_current: float
    ira_wd: float
    h_ira_elective: float
    w_ira_elective: float
    pretax_by_account: dict
    ira_tax_true_up_iterations: int
    top_24_yr: float | None
    irmaa_thr_yr: float | None
    marg: float | None
    ira_taxable_inc_orig: float | None
    ira_retirement_dist_orig: float | None


class Priority4bResult(NamedTuple):
    """Everything Priority 4b (sub-stage #7) produces that code outside it
    still needs -- the still-inline DAF carryforward make-up pass (#8) and
    the already-extracted final-draws sub-stages (#9-#11) read
    ``fed_tax``/``taxable_inc``/``total_tax``/``gap`` afterward.
    """
    gap: float
    agi: float
    taxable_inc: float
    fed_tax: float
    state_tax: float
    total_tax_pre_niit: float
    total_tax: float
    irmaa_magi_current: float
    ira_wd: float
    h_ira_elective: float
    w_ira_elective: float
    pretax_by_account: dict
    ira_tax_true_up_iterations: int


class _TrueUpLoopResult(NamedTuple):
    gap: float
    fed_tax: float
    state_tax: float
    ira_wd: float
    h_ira_elective: float
    w_ira_elective: float
    pretax_by_account: dict
    true_up_iterations: int


def apply_priority_3_pretax_elective(
    c: dict[str, Any],
    bal: dict[str, float],
    row: dict[str, Any],
    *,
    year: int,
    filing: str,
    gap: float,
    agi: float,
    taxable_inc: float,
    fed_tax: float,
    state_tax: float,
    payroll_tax: float,
    irmaa_yr: float,
    total_tax_pre_niit: float,
    irmaa_magi_current: float,
    retirement_dist: float,
    rmd_h: float,
    rmd_w: float,
    spend: float,
    ss_taxable: float,
    earned_net: float,
    note_int_yr: float,
    portfolio_ordinary: float,
    portfolio_qualified: float,
    nonqual_ann: float,
    roth_conv: float,
    h_over_65: bool,
    brk_inf: Any,
    inflate_brackets_fn: Callable[[Any, Any, int], Any],
    ira_elective_tax_delta_fn: Callable[..., tuple],
) -> Priority3Result:
    """Withdrawal Cascade sub-stage #4 (design doc addendum): Priority 3,
    the pre-tax elective withdrawal (bracket-capped), lines ~1097-1212.

    Near-duplicate of sub-stage #7 (Priority 4b, ``apply_priority_4b_
    final_pretax_draw`` below); both share the same bounded
    ordinary-tax true-up-loop-plus-unconditional-settle-up pattern, keyed
    on ``c['tax_withdrawal_fixed_point_iterations']`` (default 3), which
    is factored into ``_run_ira_tax_true_up_loop`` and called by both.

    ``bal`` and ``row`` are mutated in place, as elsewhere in this stage
    decomposition.
    """
    h_ira_elective = 0.0
    w_ira_elective = 0.0
    ira_wd = 0.0
    pretax_by_account: dict[str, float] = {}
    ira_tax_true_up_iterations = 0
    # Pristine pre-cascade baselines for the ordinary-tax true-up helper.
    # The helper's contract is new_tax = tax_fn(baseline + cumulative
    # ira_wd); agi/taxable_inc get mutated in place below (Priority 3's
    # settle-up) so LTCG/NIIT bracket lookups see the elective withdrawal,
    # but the true-up helper itself must always work off these untouched
    # originals + the FULL cumulative ira_wd to avoid double-counting.
    ira_taxable_inc_orig = taxable_inc
    ira_retirement_dist_orig = retirement_dist
    top_24_yr = None
    irmaa_thr_yr = None
    marg = None
    if gap > 0:
        brk_yr = inflate_brackets_fn(FEDERAL_BRACKETS_MFJ, brk_inf, year - c['plan_start'])
        # Item 3.4 (F1 Option 2): the Priority-3 elective pre-tax draw
        # caps itself at a bracket ceiling before falling through to
        # taxable/trust -- the withdrawal-order-equivalent CFPs actually
        # implement ("fill ordinary income to the Nth bracket, then draw
        # taxable") without the full cascade reorder F1 Option 1 would
        # require. That ceiling used to be hardcoded to the 24% bracket;
        # withdrawal_bracket_target_rate (data_io.py, default 0.24 --
        # reproduces today's behavior exactly) makes it a real input.
        _wd_target_rate = float(c.get('withdrawal_bracket_target_rate', 0.24) or 0.24)
        top_24_yr = next((hi for _lo, hi, rate in brk_yr if rate == _wd_target_rate), None)
        if top_24_yr is None:
            raise ValueError(
                f"withdrawal_bracket_target_rate={_wd_target_rate!r} matches no federal bracket rate "
                f"in year={year} (available rates: {sorted({rate for _lo, _hi, rate in brk_yr})}) -- "
                "fix withdrawal_bracket_target_rate rather than silently capping pre-tax withdrawals "
                "against a hardcoded $400,000 bracket top"
            )
        irmaa_thr_yr = c['irmaa_base'] * _tk.irmaa_factor_for_year(c, year)
        marg = marginal_rate(taxable_inc, year, filing, c['brk_inf'])
        pretax_res = _legacy_pe.withdraw_pretax_elective(
            c, bal, gap, agi, taxable_inc, year, filing, top_24_yr, irmaa_thr_yr, marg,
            spend_floor_base=spend,
        )
        ira_wd = pretax_res['amount']
        h_ira_elective = pretax_res['h_amount']
        w_ira_elective = pretax_res['w_amount']
        pretax_by_account = dict(pretax_res.get('by_account', {}) or {})
        gap = pretax_res['new_gap']

        # ── True up ordinary-income tax on the elective withdrawal ──────
        # withdraw_pretax_elective sizes itself off a flat federal-marginal-
        # rate gross-up that ignores state tax and bracket integration. Re-
        # solve against the real progressive fed+state tax (same
        # fixed-point pattern as the LTCG/NIIT loop below) so any shortfall
        # pulls a little more pre-tax cash instead of silently turning into
        # a "reinvested surplus" later in the cash bridge.
        max_ira_tax_iters = max(0, int(c.get('tax_withdrawal_fixed_point_iterations', 3) or 0))
        investment_inc = note_int_yr + portfolio_ordinary + portfolio_qualified
        _loop = _run_ira_tax_true_up_loop(
            c, bal,
            year=year, filing=filing, top_24_yr=top_24_yr, irmaa_thr_yr=irmaa_thr_yr, marg=marg,
            spend=spend, gap=gap, agi=agi, taxable_inc=taxable_inc, ira_wd=ira_wd,
            fed_tax=fed_tax, state_tax=state_tax,
            h_ira_elective=h_ira_elective, w_ira_elective=w_ira_elective,
            pretax_by_account=pretax_by_account, true_up_iterations=ira_tax_true_up_iterations,
            respect_tax_caps=True, max_iters=max_ira_tax_iters,
            baseline_taxable_inc=ira_taxable_inc_orig, baseline_retirement_dist=ira_retirement_dist_orig,
            ss_taxable=ss_taxable, earned_net=earned_net, investment_inc=investment_inc,
            nonqual_ann=nonqual_ann, roth_conv=roth_conv, h_over_65=h_over_65,
            tax_delta_fn=ira_elective_tax_delta_fn,
            on_increment=None,
        )
        gap = _loop.gap
        fed_tax = _loop.fed_tax
        state_tax = _loop.state_tax
        ira_wd = _loop.ira_wd
        h_ira_elective = _loop.h_ira_elective
        w_ira_elective = _loop.w_ira_elective
        pretax_by_account = _loop.pretax_by_account
        ira_tax_true_up_iterations = _loop.true_up_iterations

        if ira_wd > 0:
            agi += ira_wd
            taxable_inc += ira_wd
            irmaa_magi_current += ira_wd
            total_tax_pre_niit = fed_tax + state_tax + payroll_tax + irmaa_yr
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
    row['ira_tax_true_up_iterations'] = ira_tax_true_up_iterations
    row['agi'] = agi
    row['taxable_inc'] = taxable_inc
    row['fed_tax'] = fed_tax
    row['state_tax'] = state_tax
    row['irmaa_magi_current'] = irmaa_magi_current
    row['state_retirement'] = retirement_dist + ira_wd

    return Priority3Result(
        gap=gap,
        agi=agi,
        taxable_inc=taxable_inc,
        fed_tax=fed_tax,
        state_tax=state_tax,
        total_tax_pre_niit=total_tax_pre_niit,
        irmaa_magi_current=irmaa_magi_current,
        ira_wd=ira_wd,
        h_ira_elective=h_ira_elective,
        w_ira_elective=w_ira_elective,
        pretax_by_account=pretax_by_account,
        ira_tax_true_up_iterations=ira_tax_true_up_iterations,
        top_24_yr=top_24_yr,
        irmaa_thr_yr=irmaa_thr_yr,
        marg=marg,
        ira_taxable_inc_orig=ira_taxable_inc_orig,
        ira_retirement_dist_orig=ira_retirement_dist_orig,
    )


def apply_priority_4b_final_pretax_draw(
    c: dict[str, Any],
    bal: dict[str, float],
    row: dict[str, Any],
    *,
    year: int,
    filing: str,
    gap: float,
    agi: float,
    taxable_inc: float,
    fed_tax: float,
    state_tax: float,
    payroll_tax: float,
    irmaa_yr: float,
    total_tax_pre_niit: float,
    ltcg_tax: float,
    niit: float,
    tlh_ordinary_credit: float,
    total_spend_need: float,
    other_cash_need_yr: float,
    irmaa_magi_current: float,
    retirement_dist: float,
    rmd_h: float,
    rmd_w: float,
    spend: float,
    ss_taxable: float,
    earned_net: float,
    note_int_yr: float,
    portfolio_ordinary: float,
    portfolio_qualified: float,
    nonqual_ann: float,
    roth_conv: float,
    h_over_65: bool,
    ira_wd: float,
    h_ira_elective: float,
    w_ira_elective: float,
    pretax_by_account: dict,
    ira_tax_true_up_iterations: int,
    top_24_yr: float | None,
    irmaa_thr_yr: float | None,
    marg: float | None,
    ira_taxable_inc_orig: float | None,
    ira_retirement_dist_orig: float | None,
    ira_elective_tax_delta_fn: Callable[..., tuple],
) -> Priority4bResult:
    """Withdrawal Cascade sub-stage #7 (design doc addendum): Priority 4b,
    the final pre-tax draw before any Roth withdrawal (cap override),
    lines ~1420-1518.

    Structurally identical to sub-stage #4 (Priority 3,
    ``apply_priority_3_pretax_elective`` above) -- reuses that call's
    ``ira_wd``/``h_ira_elective``/``w_ira_elective``/``pretax_by_account``/
    ``ira_tax_true_up_iterations`` (cumulative across both sub-stages, not
    reset here) and its ``top_24_yr``/``irmaa_thr_yr``/``marg``/
    ``ira_taxable_inc_orig``/``ira_retirement_dist_orig``, which are only
    ever computed by sub-stage #4 and never recomputed here. ``respect_tax_
    caps=False`` is the one behavioral difference: Priority 3 respects the
    bracket/IRMAA cap and can stop short of the full gap; this pass is the
    explicit last-resort override so Roth (Priority 5) is never tapped
    while pre-tax capacity remains -- the exact invariant
    ``test_fixed_point_taxable_withdrawal_solver_runs_before_roth`` checks.

    Unlike sub-stage #4 (which defers every ``_add_account_flow`` call to
    one bulk pass after its own block, covering both its initial draw and
    any true-up-loop increments), this sub-stage adds each account flow to
    ``row['_account_withdrawals']`` immediately as it occurs -- the initial
    draw right after it is sized, then each true-up-loop increment inside
    the loop itself. Preserved exactly as in the original inline code
    rather than unified with sub-stage #4's timing, since floating-point
    addition is not perfectly associative and the verification bar here is
    zero pinned-value drift, not just an equivalent total.

    ``bal`` and ``row`` are mutated in place, as elsewhere in this stage
    decomposition. Returns ``total_tax_pre_niit``/``total_tax`` and every
    other field unchanged (pass-through) when this sub-stage's guard
    (``gap > 0`` and pre-tax balances remain) does not fire, matching the
    original inline code's ``if`` gate exactly.
    """
    if gap > 0 and sum(max(0.0, float(bal.get(_aid, 0.0) or 0.0)) for _aid in c.get('pre_tax_ids', [])) > 0:
        pretax_res2 = _legacy_pe.withdraw_pretax_elective(
            c, bal, gap, agi, taxable_inc, year, filing, top_24_yr, irmaa_thr_yr, marg,
            respect_tax_caps=False, spend_floor_base=spend,
        )
        ira_wd_before_p4b = ira_wd
        ira_wd += pretax_res2['amount']
        h_ira_elective += pretax_res2['h_amount']
        w_ira_elective += pretax_res2['w_amount']
        for _aid, _amt in dict(pretax_res2.get('by_account', {}) or {}).items():
            pretax_by_account[_aid] = pretax_by_account.get(_aid, 0.0) + _amt
            _add_account_flow(row['_account_withdrawals'], _aid, _amt)
        gap = pretax_res2['new_gap']

        # ── True up ordinary-income tax on this final pre-tax pass ──────
        # Same fixed-point correction as Priority 3, applied against the
        # full cumulative `ira_wd` (agi/taxable_inc/fed_tax/state_tax
        # already reflect Priority 3's elective withdrawal at this point,
        # so the delta here is just the incremental tax of this pass).
        max_ira_tax_iters = max(0, int(c.get('tax_withdrawal_fixed_point_iterations', 3) or 0))
        investment_inc = note_int_yr + portfolio_ordinary + portfolio_qualified
        _loop = _run_ira_tax_true_up_loop(
            c, bal,
            year=year, filing=filing, top_24_yr=top_24_yr, irmaa_thr_yr=irmaa_thr_yr, marg=marg,
            spend=spend, gap=gap, agi=agi, taxable_inc=taxable_inc, ira_wd=ira_wd,
            fed_tax=fed_tax, state_tax=state_tax,
            h_ira_elective=h_ira_elective, w_ira_elective=w_ira_elective,
            pretax_by_account=pretax_by_account, true_up_iterations=ira_tax_true_up_iterations,
            respect_tax_caps=False, max_iters=max_ira_tax_iters,
            baseline_taxable_inc=ira_taxable_inc_orig, baseline_retirement_dist=ira_retirement_dist_orig,
            ss_taxable=ss_taxable, earned_net=earned_net, investment_inc=investment_inc,
            nonqual_ann=nonqual_ann, roth_conv=roth_conv, h_over_65=h_over_65,
            tax_delta_fn=ira_elective_tax_delta_fn,
            on_increment=lambda by_account: [
                _add_account_flow(row['_account_withdrawals'], _aid, _amt)
                for _aid, _amt in by_account.items()
            ],
        )
        gap = _loop.gap
        fed_tax = _loop.fed_tax
        state_tax = _loop.state_tax
        ira_wd = _loop.ira_wd
        h_ira_elective = _loop.h_ira_elective
        w_ira_elective = _loop.w_ira_elective
        pretax_by_account = _loop.pretax_by_account
        ira_tax_true_up_iterations = _loop.true_up_iterations

        if ira_wd > ira_wd_before_p4b:
            p4b_wd = ira_wd - ira_wd_before_p4b
            agi += p4b_wd
            taxable_inc += p4b_wd
            irmaa_magi_current += p4b_wd
            total_tax_pre_niit = fed_tax + state_tax + payroll_tax + irmaa_yr

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
        row['ira_tax_true_up_iterations'] = ira_tax_true_up_iterations
        row['agi'] = agi
        row['taxable_inc'] = taxable_inc
        row['fed_tax'] = fed_tax
        row['state_tax'] = state_tax
        row['irmaa_magi_current'] = irmaa_magi_current
        row['state_retirement'] = retirement_dist + ira_wd
        # Re-recombine total_tax/total_cash_need: the recombination right
        # after the LTCG/NIIT block (above, before this Priority 4b block
        # runs) can't see total_tax_pre_niit's update from this pass, and
        # would otherwise leave total_cash_need understating the true cost
        # of cash actually withdrawn here.
        total_tax = total_tax_pre_niit + ltcg_tax + niit - tlh_ordinary_credit
        row['total_tax'] = total_tax
        row['net_income'] = row.get('gross_income', agi) - total_tax
        row['total_cash_need'] = total_spend_need + total_tax + other_cash_need_yr
    else:
        total_tax = total_tax_pre_niit + ltcg_tax + niit - tlh_ordinary_credit

    return Priority4bResult(
        gap=gap,
        agi=agi,
        taxable_inc=taxable_inc,
        fed_tax=fed_tax,
        state_tax=state_tax,
        total_tax_pre_niit=total_tax_pre_niit,
        total_tax=total_tax,
        irmaa_magi_current=irmaa_magi_current,
        ira_wd=ira_wd,
        h_ira_elective=h_ira_elective,
        w_ira_elective=w_ira_elective,
        pretax_by_account=pretax_by_account,
        ira_tax_true_up_iterations=ira_tax_true_up_iterations,
    )


def _run_ira_tax_true_up_loop(
    c: dict[str, Any],
    bal: dict[str, float],
    *,
    year: int,
    filing: str,
    top_24_yr: float,
    irmaa_thr_yr: float,
    marg: float,
    spend: float,
    gap: float,
    agi: float,
    taxable_inc: float,
    ira_wd: float,
    fed_tax: float,
    state_tax: float,
    h_ira_elective: float,
    w_ira_elective: float,
    pretax_by_account: dict,
    true_up_iterations: int,
    respect_tax_caps: bool,
    max_iters: int,
    baseline_taxable_inc: float,
    baseline_retirement_dist: float,
    ss_taxable: float,
    earned_net: float,
    investment_inc: float,
    nonqual_ann: float,
    roth_conv: float,
    h_over_65: bool,
    tax_delta_fn: Callable[..., tuple],
    on_increment: Callable[[dict], None] | None,
) -> _TrueUpLoopResult:
    """Shared fixed-point loop used by both Priority 3 (#4) and Priority 4b
    (#7): bounded by ``max_iters``, early ``break`` on a negligible delta,
    then an *unconditional* one-shot settle-up after the loop (even if it
    hit its iteration cap) so the final increment's tax is never left
    untrued-up. Both sub-stages have this identical shape and share this
    one config key, ``c['tax_withdrawal_fixed_point_iterations']``
    (default 3) -- see the design doc addendum's "Fixed-point loops"
    section.

    ``pretax_by_account`` is mutated in place (accumulating each
    increment's per-account draw), matching ``bal``/``row`` elsewhere in
    this stage decomposition. ``on_increment``, when given, is called with
    each successful increment's own ``by_account`` dict immediately as it
    occurs -- Priority 4b uses this to add each increment's account flows
    to ``row['_account_withdrawals']`` right away, while Priority 3 passes
    ``None`` and instead adds its (larger) accumulated total once, after
    its own block ends -- preserving each sub-stage's original timing
    exactly rather than unifying it, since floating-point addition is not
    perfectly associative and the verification bar is zero pinned-value
    drift.
    """
    for _ in range(max_iters):
        delta_tax, new_fed_tax, new_state_tax = tax_delta_fn(
            fed_tax, state_tax, baseline_taxable_inc, baseline_retirement_dist, ira_wd, year, filing,
            ss_taxable, earned_net, investment_inc, nonqual_ann, roth_conv, h_over_65,
        )
        if delta_tax <= 1e-6:
            break
        true_up_iterations += 1
        fed_tax, state_tax = new_fed_tax, new_state_tax
        gap += delta_tax
        add_res = _legacy_pe.withdraw_pretax_elective(
            c, bal, gap, agi + ira_wd, taxable_inc + ira_wd, year, filing,
            top_24_yr, irmaa_thr_yr, marg, respect_tax_caps=respect_tax_caps,
            spend_floor_base=spend,
        )
        add_wd = float(add_res.get('amount', 0.0) or 0.0)
        gap = add_res['new_gap']
        if add_wd <= 1e-6:
            break
        ira_wd += add_wd
        h_ira_elective += float(add_res.get('h_amount', 0.0) or 0.0)
        w_ira_elective += float(add_res.get('w_amount', 0.0) or 0.0)
        by_account = dict(add_res.get('by_account', {}) or {})
        for _aid, _amt in by_account.items():
            pretax_by_account[_aid] = pretax_by_account.get(_aid, 0.0) + _amt
        if on_increment is not None:
            on_increment(by_account)

    # ── Final settle-up (unconditional, no further withdrawal) ──────────
    # The bounded loop above caps how many extra withdrawal rounds it
    # will attempt; if it exhausts that cap right after drawing one
    # more top-off increment, that increment's own tax would never get
    # trued up, leaving fed_tax/state_tax (and total_cash_need) short
    # of the true cost of cash actually withdrawn. Settle the books
    # against the final ira_wd every time, with no withdrawal attempt
    # attached -- any residual tax just flows through `gap` to the next
    # cascade priority like any other cost, instead of quietly reading
    # as a "reinvested surplus" later in the cash bridge.
    settle_delta, settle_fed_tax, settle_state_tax = tax_delta_fn(
        fed_tax, state_tax, baseline_taxable_inc, baseline_retirement_dist, ira_wd, year, filing,
        ss_taxable, earned_net, investment_inc, nonqual_ann, roth_conv, h_over_65,
    )
    if settle_delta > 1e-6:
        fed_tax, state_tax = settle_fed_tax, settle_state_tax
        gap += settle_delta

    return _TrueUpLoopResult(
        gap=gap,
        fed_tax=fed_tax,
        state_tax=state_tax,
        ira_wd=ira_wd,
        h_ira_elective=h_ira_elective,
        w_ira_elective=w_ira_elective,
        pretax_by_account=pretax_by_account,
        true_up_iterations=true_up_iterations,
    )


def _add_account_flow(target: dict[str, float], acct: str | None, amount: float) -> None:
    amount = float(amount or 0.0)
    if acct and abs(amount) > 1e-9:
        target[acct] = target.get(acct, 0.0) + amount
