"""Move the checking accounts and credit cards to the year's standard balance (src/working_balances.py).

Run once a year before the cash gap is assembled. Each side is a transfer, so no money is created or lost:

* checking falls by D: D leaves the checking accounts and is deposited into the first taxable account;
* checking rises by D: D is deposited into the checking accounts and added to the year's cash need, which the
  withdrawal order funds;
* credit-card balance rises by D: D is deposited into the first taxable account (spending moved onto the card);
* credit-card balance falls by D: the card is paid down, and D is added to the year's cash need.

Each account (card) keeps its share of the total. A plan with no standard balance and no percent change for a side
leaves that side alone. Cards with a payoff date are paying themselves off and are left out.

Design: documentation/archive/superpowers/plans/2026-11-07-cash-balances-and-art-split-design-and-plan.md 3.2-3.3.
"""
from __future__ import annotations

from typing import Any

from .. import core as _aa
from .. import working_balances as _wb
from .appreciation_divorce_qlac import _add_account_flow, _tag_deposit_source

SOURCE = 'Working Balance Transfer'


def _cards_today(c: dict[str, Any]) -> dict[str, float]:
    """Today's balance of each credit card without a payoff date, keyed as the engine keys ``_liability_balances``."""
    cards = {}
    for i, li in enumerate(c.get('liabilities') or []):
        if str(li.get('type') or '').lower() == 'credit_card' and not int(li.get('payoff_year') or 0):
            cards[li.get('liability_id') or f'liability_{i}'] = max(0.0, float(li.get('balance') or 0.0))
    return cards


def apply_working_balance_transfers(c: dict[str, Any], bal: dict[str, Any], year: int, *,
                                    account_deposits: dict[str, float],
                                    account_deposit_sources: dict[str, list],
                                    account_withdrawals: dict[str, float]) -> float:
    """Apply this year's checking and credit-card targets to ``bal``; return the extra cash need (>= 0).

    ``bal`` and the three account-flow dicts are mutated in place."""
    plan_start = int(c['plan_start'])
    if year <= plan_start:
        return 0.0
    cash_need = 0.0
    taxable = _aa.first_taxable(c)

    # -- checking accounts --
    std, pct = c.get('checking_std_balance'), float(c.get('checking_change_pct') or 0.0)
    ids = list(c.get('cash_ids') or [])
    if ids and (std is not None or pct):
        prior = {a: float(bal.get(a, 0.0) or 0.0) for a in ids}
        balances = c.get('balances') or {}
        today = sum(max(0.0, float(balances.get(a, 0.0) or 0.0)) for a in ids)
        new = _wb.scale_to(prior, _wb.target_total(year, plan_start, today, std, pct))
        for a in ids:
            delta = new[a] - prior[a]
            if abs(delta) <= 1e-9:
                continue
            bal[a] = new[a]
            if delta < 0:  # freed cash goes to the first taxable account
                _add_account_flow(account_withdrawals, a, -delta)
                _aa.deposit(bal, taxable, -delta)
                _add_account_flow(account_deposits, taxable, -delta)
                _tag_deposit_source(account_deposit_sources, taxable, SOURCE, -delta)
            else:  # the withdrawal order funds the increase
                _add_account_flow(account_deposits, a, delta)
                _tag_deposit_source(account_deposit_sources, a, SOURCE, delta)
                cash_need += delta

    # -- credit cards --
    std, pct = c.get('cc_std_balance'), float(c.get('cc_change_pct') or 0.0)
    cards = bal.get('_liability_balances')
    today_by_card = _cards_today(c)
    keys = list(today_by_card)
    if cards is not None and keys and (std is not None or pct):
        prior = {k: float(cards.get(k, 0.0) or 0.0) for k in keys}
        new = _wb.scale_to(prior, _wb.target_total(year, plan_start, sum(today_by_card.values()), std, pct))
        for k in keys:
            delta = new[k] - prior[k]
            if abs(delta) <= 1e-9:
                continue
            cards[k] = new[k]
            if delta > 0:  # borrowing: the cash lands in the first taxable account
                _aa.deposit(bal, taxable, delta)
                _add_account_flow(account_deposits, taxable, delta)
                _tag_deposit_source(account_deposit_sources, taxable, SOURCE, delta)
            else:  # paying down: the withdrawal order funds it
                cash_need += -delta
    return cash_need
