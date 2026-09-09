from __future__ import annotations

from typing import Any, Callable, NamedTuple

from ..planning_engines import EvWithdraw
from .. import planning_engines as _legacy_pe
from .. import core as _aa  # consolidated from account_access


class FinalDrawsResult(NamedTuple):
    """Everything this sub-stage produces that code outside it still needs.

    ``hsa_bank_balance`` is cross-year state (seeded once in setup,
    threaded through every year) -- the caller must reassign its own
    local from it on every call. ``gap``, ``hsa_wd``, ``roth_wd``,
    ``h_roth_wd``, and ``w_roth_wd`` are this-year-only but read again by
    downstream reporting (the already-extracted cashflow-breakdown and
    spending-tiers stages, and the Roth-ordering regression test that
    reads ``roth_wd``/pretax+HSA net worth from the row). Python scalar
    reassignment inside this function does not propagate to the caller,
    so every one of these must come back explicitly.
    """
    gap: float
    hsa_bank_balance: float
    hsa_wd: float
    roth_wd: float
    h_roth_wd: float
    w_roth_wd: float
    surplus: float


def apply_final_draws(
    c: dict[str, Any],
    bal: dict[str, float],
    row: dict[str, Any],
    *,
    year: int,
    gap: float,
    hsa_bank_balance: float,
    hsa_wd: float,
    spend: float,
    emit: Callable[[Any], None],
) -> FinalDrawsResult:
    """Withdrawal Cascade sub-stages #9, #10, and #11 (design doc
    addendum): Priority 4c (final non-Roth HSA draw before Roth, lines
    ~1700-1716), Priority 5 (Roth withdrawal -- last resort, lines
    ~1718-1732), and the unfunded-gap/surplus sweep (lines ~1733-1748).

    These three are adjacent in the original code with nothing between
    them and no branching sub-stage depends on their individual outputs
    before the next one runs, so they are extracted together as the final
    leg of the cascade. Priority 5 (Roth) is exactly the step the
    ordering-invariant regression test
    (``test_fixed_point_taxable_withdrawal_solver_runs_before_roth``)
    guards: nothing before this point may have left liquid pretax/HSA
    capacity unused while drawing Roth, so this function must run last,
    after every other cascade sub-stage (including the still-inline #3,
    #4, #6, #7, #8) has already reduced ``gap`` as far as it can.

    ``bal`` and ``row`` are mutated in place, as elsewhere in this stage
    decomposition.
    """
    # ── Priority 4c: Final non-Roth HSA draw before any Roth withdrawal ──
    # Roth remains the last liquid source. If the planned HSA window left a
    # remaining HSA balance and all pre-tax/taxable sources are exhausted or
    # unavailable for the cash gap, draw HSA before touching Roth.
    if gap > 0 and sum(max(0.0, float(bal.get(_aid, 0.0) or 0.0)) for _aid in c.get('hsa_ids', [])) > 0:
        # Re-read the bank balance: Priority 1b (and this year's accrual)
        # already ran above, so hsa_bank_balance reflects what remains.
        hsa_res2 = _legacy_pe.withdraw_hsa_gap(
            dict(c, hsa_expense_bank=hsa_bank_balance), bal, gap, year=year, spend_floor_base=spend)
        hsa_bank_balance = max(0.0, hsa_bank_balance - hsa_res2['amount'])
        hsa_wd += hsa_res2['amount']
        gap = hsa_res2['new_gap']
        for _aid, _amt in dict(hsa_res2.get('by_account', {}) or {}).items():
            row['_hsa_by_account'][_aid] = row['_hsa_by_account'].get(_aid, 0.0) + _amt
            _add_account_flow(row['_account_withdrawals'], _aid, _amt)
        row['hsa_wd'] = hsa_wd
    row['hsa_expense_bank_balance'] = hsa_bank_balance

    # ── Priority 5: Roth withdrawal ─────────────────────────────────────
    roth_res = _legacy_pe.withdraw_roth(c, bal, gap, year=year, spend_floor_base=spend)
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

    return FinalDrawsResult(
        gap=gap,
        hsa_bank_balance=hsa_bank_balance,
        hsa_wd=hsa_wd,
        roth_wd=roth_wd,
        h_roth_wd=h_roth_wd,
        w_roth_wd=w_roth_wd,
        surplus=surplus,
    )


def _add_account_flow(target: dict[str, float], acct: str | None, amount: float) -> None:
    amount = float(amount or 0.0)
    if acct and abs(amount) > 1e-9:
        target[acct] = target.get(acct, 0.0) + amount


def _tag_deposit_source(row: dict[str, Any], acct: str | None, source: str, amount: float) -> None:
    """Record a human-readable source label for a deposit, alongside the
    existing flat `_account_deposits` total (which remains unchanged and
    is still the authoritative per-account aggregate for reconciliation).
    """
    amount = float(amount or 0.0)
    if acct and abs(amount) > 1e-9:
        sources = row.setdefault('_account_deposit_sources', {})
        sources.setdefault(acct, []).append({'source': source, 'amount': amount})
