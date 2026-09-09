from __future__ import annotations

from typing import Any, Callable, NamedTuple

from ..planning_engines import EvWithdraw
from .. import planning_engines as _legacy_pe


class TaxableTrustWithdrawalResult(NamedTuple):
    """Everything this sub-stage produces that code outside it still needs.

    All four fields are read again by the still-inline sub-stage #6
    (LTCG/NIIT fixed point + TLH + gain-harvest + cap-loss waterfall,
    lines ~1334-1528), which can add to ``trust_wd``/``ht_wd``/``wt_wd``/
    ``trust_by_account`` on each fixed-point iteration and realizes gain
    against ``trust_by_account``. Python scalar reassignment inside this
    function does not propagate to the caller, so every one of these must
    come back explicitly rather than being assumed to persist.
    """
    gap: float
    trust_wd: float
    ht_wd: float
    wt_wd: float
    trust_by_account: dict[str, float]


def apply_taxable_trust_withdrawal(
    c: dict[str, Any],
    bal: dict[str, float],
    row: dict[str, Any],
    *,
    year: int,
    gap: float,
    spend: float,
    emit: Callable[[Any], None],
) -> TaxableTrustWithdrawalResult:
    """Withdrawal Cascade sub-stage #5 (design doc addendum): Priority 4,
    taxable/trust withdrawal (lines ~1318-1332).

    ``bal`` and ``row`` are mutated in place, as elsewhere in this stage
    decomposition.
    """
    # ── Priority 4: Taxable/trust withdrawal ─────────────────────────────
    trust_res = _legacy_pe.withdraw_taxable_trust(c, bal, year, gap, spend)
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

    return TaxableTrustWithdrawalResult(
        gap=gap,
        trust_wd=trust_wd,
        ht_wd=ht_wd,
        wt_wd=wt_wd,
        trust_by_account=trust_by_account,
    )


def _add_account_flow(target: dict[str, float], acct: str | None, amount: float) -> None:
    amount = float(amount or 0.0)
    if acct and abs(amount) > 1e-9:
        target[acct] = target.get(acct, 0.0) + amount
