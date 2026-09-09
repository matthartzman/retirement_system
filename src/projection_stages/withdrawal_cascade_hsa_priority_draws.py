from __future__ import annotations

from typing import Any, NamedTuple

from .. import planning_engines as _legacy_pe


class HsaPriorityDrawsResult(NamedTuple):
    """Everything this sub-stage produces that code outside it still needs.

    ``gap`` and ``hsa_bank_balance`` are read and further mutated by the
    still-inline sub-stage #3 (HSA-reimbursement medical-deduction
    correction) and by sub-stage #9 (final HSA draw before Roth) later in
    the same year's cascade -- ``hsa_bank_balance`` is also cross-year
    state, seeded once in setup and threaded through every year. ``cl_hsa_wd``
    and ``hsa_wd`` are read by sub-stage #3's netting calculation
    immediately after this returns. Python scalar reassignment inside this
    function does not propagate to the caller, so every one of these must
    come back explicitly.
    """
    gap: float
    hsa_bank_balance: float
    cl_hsa_wd: float
    hsa_wd: float


def apply_hsa_priority_draws(
    c: dict[str, Any],
    bal: dict[str, float],
    row: dict[str, Any],
    *,
    year: int,
    medical_expense_yr: float,
    hsa_bank_balance: float,
    gap: float,
    spend: float,
) -> HsaPriorityDrawsResult:
    """Withdrawal Cascade sub-stages #1 and #2 (design doc addendum):
    Priority 1b (contingent-liability spend draws HSA first, lines
    ~1061-1094) and Priority 2 (HSA scheduled window draw, lines
    ~1096-1103).

    These two run back-to-back with no other sub-stage between them in the
    original code and share ``hsa_bank_balance`` state directly (Priority
    1b's accrual/draw must settle before Priority 2 sizes itself against
    what remains), so they are extracted together rather than split.

    ``bal`` and ``row`` are mutated in place, as elsewhere in this stage
    decomposition.
    """
    # ── Priority 1b: contingent-liability spend draws HSA first ───────────
    # Optimization refactor: the contingent_liability spending tier
    # (ltc_prem_yr + wellness_shock_yr) is qualified medical expense, so
    # the HSA -- the one account whose dollars come out tax-free for
    # exactly this -- funds it ahead of the ordinary cascade. Runs BEFORE
    # Priority 2 so the scheduled window draw sizes itself against
    # whatever remains rather than double-counting the same balance.
    # Gated on hsa_withdrawal_mode (see hsa_unscheduled_draw_allowed): a
    # household that configured a scheduled drawdown keeps that schedule
    # as the sole authority, so under those modes this is a no-op and
    # Priority 2 behaves exactly as before.
    #
    # HSA expense-bank accumulation (Option B): this year's qualified
    # medical spend accrues to the running bank BEFORE either draw this
    # year is sized, so a receipt generated this year can justify a
    # reimbursement this year. Only Priority 1b (here) and Priority 4c
    # below enforce the bank -- Priority 2's scheduled/window draw is
    # deliberately left uncapped; see the spec's "Implementation note".
    hsa_bank_balance += medical_expense_yr
    _hsa_bank_c = dict(c, hsa_expense_bank=hsa_bank_balance)
    cl_res = _legacy_pe.fund_contingent_liability_from_hsa(
        _hsa_bank_c, bal,
        ltc_prem_yr=row.get('ltc_prem_yr', 0.0),
        wellness_shock_yr=row.get('wellness_shock_yr', 0.0),
        year=year, spend_floor_base=spend)
    cl_hsa_wd = cl_res['amount']
    hsa_bank_balance = max(0.0, hsa_bank_balance - cl_hsa_wd)
    gap -= cl_hsa_wd
    row['contingent_liability_hsa_wd'] = cl_hsa_wd
    row['contingent_liability_unfunded_by_hsa'] = cl_res['residual']
    cl_by_account = dict(cl_res.get('by_account', {}) or {})
    row['_hsa_by_account'] = dict(cl_by_account)
    for _aid, _amt in cl_by_account.items():
        _add_account_flow(row['_account_withdrawals'], _aid, _amt)

    # ── Priority 2: HSA (scheduled, not gap-driven) ────────────────────────
    hsa_res = _legacy_pe.withdraw_hsa_window(c, bal, year, wellness_cost=row.get('wellness_base_yr', 0.0))
    hsa_wd = cl_hsa_wd + hsa_res['amount']
    gap -= hsa_res['amount']
    row['hsa_wd'] = hsa_wd
    for _aid, _amt in dict(hsa_res.get('by_account', {}) or {}).items():
        row['_hsa_by_account'][_aid] = row['_hsa_by_account'].get(_aid, 0.0) + _amt
        _add_account_flow(row['_account_withdrawals'], _aid, _amt)

    return HsaPriorityDrawsResult(
        gap=gap,
        hsa_bank_balance=hsa_bank_balance,
        cl_hsa_wd=cl_hsa_wd,
        hsa_wd=hsa_wd,
    )


def _add_account_flow(target: dict[str, float], acct: str | None, amount: float) -> None:
    amount = float(amount or 0.0)
    if acct and abs(amount) > 1e-9:
        target[acct] = target.get(acct, 0.0) + amount
