from __future__ import annotations

from typing import Any, NamedTuple

from .. import core as _aa  # consolidated from account_access
from .. import tax_kernel as _tk
from ..core import amt_tax as _amt_tax


class Stage11Result(NamedTuple):
    """Every value this stage updates, returned as one typed bundle.

    ``total_tax`` and ``amt_credit_carry`` are plain floats reassigned
    here as locals -- like Stage 3's ``cst_balance``/``startup``, that
    does nothing to the caller's own locals of the same name (Python
    floats are passed by value). ``amt_credit_carry`` is additionally
    multi-year state: the caller must feed the returned value back in
    as next year's input, or the ISO minimum-tax credit carryforward
    silently resets to whatever was passed in this call.

    The five ``equity_comp_*``/``amt_*`` fields are optional report-only
    values, ``None`` when the legacy block's own gating condition left
    the corresponding ``row`` key unset (e.g. no LTCG event this year).
    They come back as ``Optional[float]`` rather than always as ``0.0``
    so the caller can replicate that exact "leave the key absent, don't
    write a zero" behavior -- flattening the two states to 0.0 would be
    a silent, if usually harmless, behavior change to ``row``'s shape.

    A plain tuple would invite a positional mix-up among several
    same-typed floats; see :class:`Stage3Result` in
    ``appreciation_divorce_qlac.py`` for the fuller rationale.
    """
    total_tax: float
    amt_credit_carry: float
    equity_comp_ltcg_gain: float | None
    equity_comp_ltcg_tax: float | None
    amt_tax: float | None
    amt_credit_used: float | None
    amt_credit_carryforward: float | None


def apply_amt_and_equity_comp_true_up(
    c: dict[str, Any],
    *,
    year: int,
    filing: str,
    equity_on: bool,
    equity_events: dict[str, float],
    taxable_inc: float,
    fed_tax: float,
    total_tax: float,
    amt_credit_carry: float,
    bal: dict[str, float],
) -> Stage11Result:
    """Post-cascade true-up for equity compensation: LTCG on an ISO/RSU
    sale, and AMT from the ISO bargain-element preference (with
    minimum-tax credit carryforward).

    Runs only when the equity-compensation module is enabled
    (``equity_on``). Equity ordinary income and DI benefits already
    flowed through the tax fixed-point earlier in the year's cascade
    (via ``non_ss_income``); this stage adds the two effects that
    fixed-point does not model, after the withdrawal cascade and its
    own tax true-ups have settled ``taxable_inc``/``fed_tax``/
    ``total_tax`` for the year.

    ``bal`` is mutated in place (dict mutation crosses the function
    boundary naturally) to fund the extra tax, or receive the credit
    refund, through the first taxable account. ``total_tax`` and
    ``amt_credit_carry`` do NOT propagate that way -- they are returned
    via :class:`Stage11Result`; see its docstring for why, and for why
    the five report-only fields are ``Optional``.

    Feeds forward into: the caller's ``row['total_tax']`` (read again
    by the effective-marginal-rate stage's re-derivation and by
    ``net_income``), and next year's call to this same function via
    ``amt_credit_carry``.
    """
    if not equity_on:
        return Stage11Result(
            total_tax=total_tax,
            amt_credit_carry=amt_credit_carry,
            equity_comp_ltcg_gain=None,
            equity_comp_ltcg_tax=None,
            amt_tax=None,
            amt_credit_used=None,
            amt_credit_carryforward=None,
        )

    equity_comp_ltcg_gain = None
    equity_comp_ltcg_tax = None
    amt_tax_out = None
    amt_credit_used_out = None
    amt_credit_carryforward_out = None

    _extra_tax = 0.0
    if equity_events['ltcg_gain'] > 0:
        _eq_ltcg_tax = _tk.ltcg_tax_on_gain(c, equity_events['ltcg_gain'], max(0.0, taxable_inc), year)
        _extra_tax += _eq_ltcg_tax
        equity_comp_ltcg_gain = equity_events['ltcg_gain']
        equity_comp_ltcg_tax = _eq_ltcg_tax

    _amt_adj, amt_credit_carry = _amt_tax(
        taxable_inc, fed_tax, equity_events['amt_preference'], filing,
        year, c.get('brk_inf', c.get('inf', 0.0)), amt_credit_carry)
    if abs(_amt_adj) > 1e-9 or equity_events['amt_preference'] > 0:
        _extra_tax += _amt_adj
        amt_tax_out = max(0.0, _amt_adj)
        amt_credit_used_out = max(0.0, -_amt_adj)
        amt_credit_carryforward_out = amt_credit_carry

    if abs(_extra_tax) > 1e-9:
        total_tax += _extra_tax
        # Fund the extra tax (or refund the credit) through a taxable
        # account so net worth reflects the cash paid/received.
        _eq_tax_acct = _aa.first_taxable(c)
        if _eq_tax_acct:
            bal[_eq_tax_acct] = bal.get(_eq_tax_acct, 0.0) - _extra_tax

    return Stage11Result(
        total_tax=total_tax,
        amt_credit_carry=amt_credit_carry,
        equity_comp_ltcg_gain=equity_comp_ltcg_gain,
        equity_comp_ltcg_tax=equity_comp_ltcg_tax,
        amt_tax=amt_tax_out,
        amt_credit_used=amt_credit_used_out,
        amt_credit_carryforward=amt_credit_carryforward_out,
    )
