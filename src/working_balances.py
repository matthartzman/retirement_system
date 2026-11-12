"""Standard checking and credit-card balances for the forecast years.

The plan used to hold today's checking balance and today's credit-card liabilities flat for every year. It now
takes a *standard balance* for all checking accounts together and for all credit cards together, used from the
year after the current one, each with its own annual percent change (rows under Other Assets > Cash). The current
year keeps today's balances. A blank standard balance holds today's balance; blank inputs change nothing.

Design: documentation/archive/superpowers/plans/2026-11-07-cash-balances-and-art-split-design-and-plan.md 3.1-3.3.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Other Assets", "Cash", "checking_standard_balance", "", "USD",
     "Standard balance for all checking accounts together, used for every year after the current one. The current "
     "year keeps today's balances. Blank = hold today's balance. A change from the prior year moves between "
     "checking and your first taxable account."],
    ["Other Assets", "Cash", "checking_annual_change_pct", "", "pct",
     "Yearly percent change in the standard checking balance, applied from the year after the first forecast year "
     "(1.5% grows it, -1.5% shrinks it). Blank = 0%."],
    ["Other Assets", "Cash", "credit_card_standard_balance", "", "USD",
     "Standard balance for all credit cards together, used for every year after the current one. The current year "
     "keeps today's balances. Blank = hold today's balance. A card with a payoff date is left out."],
    ["Other Assets", "Cash", "credit_card_annual_change_pct", "", "pct",
     "Yearly percent change in the standard credit-card balance, applied from the year after the first forecast "
     "year. Blank = 0%."],
]

_KEYS = {"checking_standard_balance": "checking_std_balance", "checking_annual_change_pct": "checking_change_pct",
         "credit_card_standard_balance": "cc_std_balance", "credit_card_annual_change_pct": "cc_change_pct"}


def _num(raw: Any) -> float | None:
    text = str(raw if raw is not None else "").strip()
    if not text:
        return None
    pct = "%" in text
    try:
        value = float(re.sub(r"[^0-9eE.+-]", "", text))
    except ValueError:
        return None
    return value / 100.0 if pct else value


def parse(data: Mapping[str, Any]) -> dict[str, Any]:
    """The four inputs from the sectioned plan data: balances as dollars (None when blank), percents as fractions
    (0.0 when blank). Keys: ``checking_std_balance``, ``checking_change_pct``, ``cc_std_balance``, ``cc_change_pct``."""
    rows = ((data.get("Other Assets") or {}).get("Cash") or {})
    out: dict[str, Any] = {}
    for label, key in _KEYS.items():
        value = _num(rows.get(label))
        out[key] = value if key.endswith("std_balance") else (value or 0.0)
    return out


def target_total(year: int, plan_start: int, today: float, standard: float | None, change_pct: float) -> float:
    """The household's checking (or credit-card) total in ``year``.

    The plan-start year is today's total. The first year after it is the standard balance, and each later year is the
    previous one grown by ``change_pct``. With no standard balance, today's total stands in for it and the percent
    applies from the first year after plan start."""
    if year <= plan_start:
        return float(today)
    if standard is None:
        return float(today) * (1.0 + change_pct) ** (year - plan_start)
    return float(standard) * (1.0 + change_pct) ** (year - plan_start - 1)


def scale_to(balances: Mapping[str, float], total: float) -> dict[str, float]:
    """``balances`` scaled so they add up to ``total``, each keeping its share; split evenly when they are all 0."""
    if not balances:
        return {}
    current = sum(max(0.0, float(v or 0.0)) for v in balances.values())
    total = max(0.0, float(total))
    if current <= 0:
        return {k: total / len(balances) for k in balances}
    return {k: max(0.0, float(v or 0.0)) * total / current for k, v in balances.items()}
