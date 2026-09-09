from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, NamedTuple

from ..planning_engines import EvTax, EvWithdraw
from .. import planning_engines as _legacy_pe
from .. import tax_kernel as _tk
from .. import tlh as _tlh
from .. import gain_harvest as _gh
from ..core import niit_tax


class WithdrawalCascadeInvestmentTaxResult(NamedTuple):
    """Everything sub-stage #6 (design doc addendum, "step 4") produces
    that code outside it still needs.

    ``cap_loss_carryforward`` is genuine *cross-year* state (seeded once
    before the outer per-year loop in ``deterministic_engine.py``, from
    ``year_state.cap_loss_carryforward``) -- it is never written back into
    ``year_state`` and instead persists only because it is a local variable
    in the caller's enclosing per-year loop, exactly the same mechanism
    ``hsa_bank_balance`` already relies on (see
    ``withdrawal_cascade_final_draws.py``). The caller MUST reassign its own
    local from this field on every call, or next year's capital-loss
    waterfall silently reads a stale (in practice, always-zero) value.

    ``ltcg_tax``/``niit``/``tlh_ordinary_credit`` are returned individually
    rather than only as the recombined ``total_tax`` -- sub-stage #7
    (Priority 4b, ``withdrawal_cascade_ira_true_up.py``) re-runs the same
    ``total_tax = total_tax_pre_niit + ltcg_tax + niit - tlh_ordinary_credit``
    recombination itself after its own true-up changes
    ``total_tax_pre_niit``, so it needs the three addends, not just their
    sum.

    ``trust_wd``/``ht_wd``/``wt_wd``/``trust_by_account`` are both inputs
    (from sub-stage #5, ``withdrawal_cascade_taxable_trust.py``) and
    outputs here -- this sub-stage's fixed-point loop can add to them on
    each iteration.
    """
    gap: float
    ltcg_gain: float
    ltcg_tax: float
    niit: float
    tlh_ordinary_credit: float
    cap_loss_carryforward: float
    trust_wd: float
    ht_wd: float
    wt_wd: float
    trust_by_account: dict[str, float]
    total_tax: float
    investment_tax_iterations: int
    investment_tax_funded_by_taxable: float


@dataclass
class _InvestmentTaxState:
    """Small, block-scoped mutable state shared by ``_refresh_investment_
    taxes`` across every call within a single year's sub-stage #6 run.

    Replaces the original inline code's two ``nonlocal``-closures-over-
    outer-locals with an explicit object passed at each call site --
    same shape (mutate shared state, side-effecting helper), but every
    read/write is now visible at a function boundary instead of hidden
    behind ``nonlocal``. Deliberately narrow: this is the "small, private,
    module-scoped dataclass" the design doc addendum calls for, not the
    engine-wide ``YearState`` (still not needed here) nor a general
    cascade-wide state object (explicitly out of scope for this
    extraction).
    """
    ltcg_tax: float
    ltcg_gain: float
    niit: float
    available_losses: float
    agi: float
    taxable_inc: float
    filing: str
    base_nii_without_ltcg: float


def _apply_tax_loss_harvesting(
    c: dict[str, Any],
    bal: dict[str, float],
    row: dict[str, Any],
    year: int,
) -> tuple[float, float]:
    """Tax-loss harvesting, "apply" mode only. Loops over harvest-lot
    candidates (not years), realizing each qualifying loss and resetting
    that lot's basis to market with a current-year acquisition date -- a
    single mutation on the lot object living inside ``c``'s lot engine,
    not on any local/``row``/``bal`` scalar (easy to miss when inventorying
    what this function writes). A transaction cost is charged against
    ``bal[account]``. Independent of gain-harvesting and of the
    fixed-point loop below -- runs once, produces two scalars, done.

    Sets ``row['tlh_harvested_loss']``/``row['tlh_transaction_cost']`` and
    returns ``(harvested_loss, tlh_txn_cost)``.
    """
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
    return harvested_loss, tlh_txn_cost


def _apply_gain_harvesting(
    c: dict[str, Any],
    bal: dict[str, float],
    row: dict[str, Any],
    year: int,
    taxable_inc: float,
    bracket_factor_fn: Callable[[int], float],
) -> tuple[float, float]:
    """0%-bracket gain harvesting, "apply" mode only. Symmetric counterpart
    to ``_apply_tax_loss_harvesting`` above (system review 2026-07-21, P2):
    realizes appreciated long-term lots up to the remaining 0%-LTCG-bracket
    headroom, resetting basis to market value tax-free. Same single-
    mutation technique as TLH, but no replacement-security logic --
    wash-sale rules disallow claiming a *loss* on a repurchased
    "substantially identical" security; they have no counterpart for
    gains. Headroom is computed from ``taxable_inc`` (already reflecting
    this year's Roth conversion decision), so this can never double-book
    the same ordinary-income bracket space the Roth conversion guardrail
    already consumed. Independent of TLH and of the fixed-point loop below.

    Sets ``row['gain_harvest_realized']``/
    ``row['gain_harvest_transaction_cost']`` and returns
    ``(gain_harvest_realized, gain_harvest_txn_cost)``.
    """
    gain_harvest_realized = 0.0
    gain_harvest_txn_cost = 0.0
    if str(c.get('gain_harvest_policy', 'off')).lower() == 'apply':
        _gh_bps = float(c.get('gain_harvest_transaction_cost_bps', 0.0) or 0.0) / 10000.0
        _gh_bracket_factor = bracket_factor_fn(year)
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
    return gain_harvest_realized, gain_harvest_txn_cost


def _realize_taxable_gain(
    c: dict[str, Any],
    bal_basis_free: dict[str, float],
    year: int,
    draws_by_account: dict[str, float],
) -> float:
    """Consumes basis-free dollars first, then computes the taxable gain on
    the remainder via the lot engine (or the flat ``trust_gain_fraction``
    when lots aren't in use). ``bal_basis_free`` is mutated in place, like
    ``bal``/``row`` elsewhere in this stage decomposition. Was an inline
    closure (``_realize_taxable_gain``) closing over ``bal_basis_free``,
    ``year``, ``c``; now an ordinary function taking them explicitly.
    """
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


def _refresh_investment_taxes(
    c: dict[str, Any],
    state: _InvestmentTaxState,
    model_niit: bool,
    year: int,
) -> float:
    """Recomputes LTCG tax net of losses and NIIT off ``state``'s current
    ``ltcg_gain``/``available_losses``, mutating ``state.ltcg_tax``/
    ``state.niit`` in place and returning the *incremental* tax delta
    since the last call. Was an inline closure (``_refresh_investment_
    taxes``) using ``nonlocal ltcg_tax, niit, total_tax``; ``total_tax``
    was named in that ``nonlocal`` statement but never actually assigned
    inside the closure body (dead -- ``total_tax`` is rebuilt once,
    explicitly, by the recombination after the fixed-point loop and
    capital-loss waterfall, not incrementally here). Dropped at extraction
    time: an unused ``nonlocal`` target invites a future edit to believe
    this closure is expected to set ``total_tax`` directly, which is
    exactly the class of mistake that produced this file's documented
    $178.21 recombination-bypass regression once already, in the
    neighboring sub-stage #3.
    """
    # Capital losses (carryforward + harvested) offset realized gains
    # before any LTCG/NIIT is due.
    net_gain = max(0.0, state.ltcg_gain - state.available_losses)
    new_ltcg_tax = _tk.ltcg_tax_on_gain(c, net_gain, max(0, state.taxable_inc), year) if net_gain > 0 else 0.0
    delta_ltcg = max(0.0, new_ltcg_tax - state.ltcg_tax)
    state.ltcg_tax = new_ltcg_tax
    delta_niit = 0.0
    if model_niit:
        # Keep the engine's existing MAGI convention but recompute on
        # cumulative NII as additional taxable withdrawals are made.
        new_niit = niit_tax(state.base_nii_without_ltcg + net_gain, state.agi, state.filing)
        delta_niit = max(0.0, new_niit - state.niit)
        state.niit = new_niit
    return delta_ltcg + delta_niit


def apply_investment_tax_cascade(
    c: dict[str, Any],
    bal: dict[str, float],
    bal_basis_free: dict[str, float],
    row: dict[str, Any],
    *,
    year: int,
    gap: float,
    agi: float,
    taxable_inc: float,
    filing: str,
    total_tax_pre_niit: float,
    total_spend_need: float,
    other_cash_need_yr: float,
    home_sale_ltcg_tax: float,
    home_sale_ltcg_gain: float,
    niit: float,
    cap_loss_carryforward: float,
    trust_wd: float,
    ht_wd: float,
    wt_wd: float,
    trust_by_account: dict[str, float],
    note_int_yr: float,
    portfolio_ordinary: float,
    portfolio_qualified: float,
    spend: float,
    emit: Callable[[Any], None],
    bracket_factor_fn: Callable[[int], float],
    compute_fed_tax_fn: Callable[[float, int, str], float],
) -> WithdrawalCascadeInvestmentTaxResult:
    """Withdrawal Cascade sub-stage #6 (design doc addendum, "step 4"):
    the LTCG/NIIT fixed point + tax-loss harvesting + 0%-bracket gain
    harvesting + capital-loss waterfall, originally lines ~1074-1268.
    Runs after sub-stage #5 (Priority 4, taxable/trust withdrawal --
    ``withdrawal_cascade_taxable_trust.py``, whose ``trust_wd``/``ht_wd``/
    ``wt_wd``/``trust_by_account`` this sub-stage reads and can add to on
    each fixed-point iteration) and before sub-stage #7 (Priority 4b --
    ``withdrawal_cascade_ira_true_up.py``, which reads back ``ltcg_tax``/
    ``niit``/``tlh_ordinary_credit`` to re-run this sub-stage's own
    ``total_tax`` recombination after its own true-up).

    ``cap_loss_carryforward`` is cross-year state -- see
    ``WithdrawalCascadeInvestmentTaxResult``'s docstring; the caller must
    reassign its own local from the returned field every year.

    ``bal``, ``bal_basis_free``, and ``row`` are mutated in place, as
    elsewhere in this stage decomposition. TLH and gain-harvesting
    (``_apply_tax_loss_harvesting``/``_apply_gain_harvesting``) run once,
    before the fixed-point loop, and do not interact with each other or
    with the loop directly -- only through the ``available_losses``/
    ``ltcg_gain`` values they seed. The capital-loss waterfall runs once,
    unconditionally, after the loop's last iteration (never per-iteration),
    reading whatever ``ltcg_gain``/``available_losses`` the loop left
    behind.
    """
    ltcg_tax = home_sale_ltcg_tax
    ltcg_gain = home_sale_ltcg_gain
    investment_tax_iterations = 0
    investment_tax_funded_by_taxable = 0.0

    # ── Tax-loss harvesting (apply mode) ────────────────────────────────
    harvested_loss, _tlh_txn_cost = _apply_tax_loss_harvesting(c, bal, row, year)
    # Loss pool available to offset gains this year: prior-year carryforward
    # plus anything harvested this year.
    available_losses = cap_loss_carryforward + harvested_loss

    # ── 0%-bracket gain harvesting (apply mode) ──────────────────────────
    _apply_gain_harvesting(c, bal, row, year, taxable_inc, bracket_factor_fn)

    base_nii_without_ltcg = (note_int_yr + portfolio_ordinary + portfolio_qualified +
                             row.get('_niit_ws_taxable', 0) +
                             row.get('_niit_hs_taxable', 0))

    state = _InvestmentTaxState(
        ltcg_tax=ltcg_tax,
        ltcg_gain=ltcg_gain,
        niit=niit,
        available_losses=available_losses,
        agi=agi,
        taxable_inc=taxable_inc,
        filing=filing,
        base_nii_without_ltcg=base_nii_without_ltcg,
    )

    model_niit = c['model_niit']

    if state.ltcg_gain > 0 or state.available_losses > 0:
        inv_tax_delta = _refresh_investment_taxes(c, state, model_niit, year)
        gap += inv_tax_delta
    if trust_wd > 0:
        state.ltcg_gain += _realize_taxable_gain(c, bal_basis_free, year, trust_by_account)
        inv_tax_delta = _refresh_investment_taxes(c, state, model_niit, year)
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
        state.ltcg_gain += _realize_taxable_gain(c, bal_basis_free, year, add_by_account)
        inv_tax_delta = _refresh_investment_taxes(c, state, model_niit, year)
        gap += inv_tax_delta

    # ── Capital-loss waterfall settle-up ─────────────────────────────────
    # The gain-offset portion is already reflected in ltcg_tax/niit above.
    # Whatever loss remains offsets up to $3,000 of ordinary income (valued
    # at the federal marginal rate) and the rest rolls forward.
    _used_vs_gain = min(state.available_losses, max(0.0, state.ltcg_gain))
    _rem_loss = max(0.0, state.available_losses - _used_vs_gain)
    _ordinary_offset = min(3000.0, _rem_loss)
    cap_loss_carryforward = _rem_loss - _ordinary_offset
    tlh_ordinary_credit = 0.0
    if _ordinary_offset > 0 and taxable_inc > 0:
        _mtr = (compute_fed_tax_fn(taxable_inc, year, filing)
                - compute_fed_tax_fn(max(0.0, taxable_inc - _ordinary_offset), year, filing)) / _ordinary_offset
        tlh_ordinary_credit = _ordinary_offset * max(0.0, _mtr)
    row['cap_loss_used'] = _used_vs_gain + _ordinary_offset
    row['cap_loss_carryforward'] = cap_loss_carryforward
    row['tlh_ordinary_credit'] = tlh_ordinary_credit
    # Tax value the gain-offset portion avoided (LTCG that would have been
    # due on the offset gain slice, stacked above ordinary income). Combined
    # with the ordinary-offset credit this is the realized-this-year tax
    # value of harvesting, which the Tax-Loss Harvesting sheet sums to a
    # net-of-transaction-cost lifetime figure.
    tlh_gain_offset_value = _tk.ltcg_tax_on_gain(c, _used_vs_gain, max(0.0, taxable_inc), year) if _used_vs_gain > 0 else 0.0
    row['tlh_gain_offset_value'] = tlh_gain_offset_value
    row['tlh_tax_value'] = tlh_gain_offset_value + tlh_ordinary_credit

    row['trust_wd'] = trust_wd
    row['h_trust_wd'] = ht_wd
    row['w_trust_wd'] = wt_wd
    row['ltcg_gain'] = state.ltcg_gain
    row['ltcg_tax'] = state.ltcg_tax
    row['niit'] = state.niit
    row['investment_tax_iterations'] = investment_tax_iterations
    row['investment_tax_funded_by_taxable'] = investment_tax_funded_by_taxable
    if state.niit > 0:
        emit(EvTax(year, 'niit', state.niit, 0))
    total_tax = total_tax_pre_niit + state.ltcg_tax + state.niit - tlh_ordinary_credit
    row['total_tax'] = total_tax
    row['net_income'] = row.get('gross_income', agi) - total_tax
    # Refresh total_cash_need now that ltcg_tax/niit reflect the fixed-point
    # investment-tax passes above; the earlier value (used to seed `gap`)
    # predates those passes and would otherwise understate cash need,
    # causing the cashflow sheet's recomputed Cash Bridge Gap to disagree
    # with the true engine gap (Surplus/unfunded_gap).
    row['total_cash_need'] = total_spend_need + total_tax + other_cash_need_yr

    return WithdrawalCascadeInvestmentTaxResult(
        gap=gap,
        ltcg_gain=state.ltcg_gain,
        ltcg_tax=state.ltcg_tax,
        niit=state.niit,
        tlh_ordinary_credit=tlh_ordinary_credit,
        cap_loss_carryforward=cap_loss_carryforward,
        trust_wd=trust_wd,
        ht_wd=ht_wd,
        wt_wd=wt_wd,
        trust_by_account=trust_by_account,
        total_tax=total_tax,
        investment_tax_iterations=investment_tax_iterations,
        investment_tax_funded_by_taxable=investment_tax_funded_by_taxable,
    )


def _add_account_flow(target: dict[str, float], acct: str | None, amount: float) -> None:
    amount = float(amount or 0.0)
    if acct and abs(amount) > 1e-9:
        target[acct] = target.get(acct, 0.0) + amount
