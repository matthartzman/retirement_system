"""QLAC (Qualified Longevity Annuity Contract) premium recommendation (#295).

Recommends the largest QLAC premium a given household member can fund
without exceeding the IRS aggregate dollar cap (IRC Sec. 401(a)(9)(H),
indexed annually -- see core.qlac_premium_limit) or that person's available
pre-tax (traditional IRA/401k/403b/SEP) balance, and surfaces the latest
permitted income-start year (age-85 deadline) and the account it would draw
from, so the advisor can judge whether -- and how much -- QLAC funding makes
sense this year.

This is a recommendation only: it never mutates the plan. The UI applies it
by writing to the existing h_qlac/wife_qlac fields (enabled/premium/
source_account/purchase_year), which the projection engine already reads
(deterministic_engine.py) and the RMD calculation already excludes
(planning_engines.compute_rmds via core.qlac_excluded_rmd_balance).
"""
from __future__ import annotations

from typing import Any, Mapping

from . import core as _core


def _pre_tax_accounts_for_owner(c: Mapping[str, Any], owner_idx: int) -> list[dict]:
    registry = c.get('account_registry', []) or []
    return [
        a for a in registry
        if a.get('tax') == 'pre_tax' and int(a.get('owner_idx', -1)) == int(owner_idx)
    ]


def recommend_qlac_premium(c: Mapping[str, Any], owner_idx: int = 0,
                            *, year: int | None = None) -> dict[str, Any]:
    """Return a recommended QLAC premium for household member ``owner_idx``
    (0 = first member/"husband" slot, 1 = second member/"wife" slot in this
    engine's existing naming) for ``year`` (default: plan_start).

    Maximizes within min(statutory dollar cap, that person's available
    pre-tax balance) -- already-committed QLAC premium (if any) is
    subtracted from the statutory headroom first, since the cap is an
    aggregate lifetime limit, not a per-purchase limit.
    """
    plan_start = int(c.get('plan_start', 2024) or 2024)
    year = int(year or plan_start)
    brk_inf = float(c.get('brk_inf', c.get('inf', 0.02)) or 0.02)

    accounts = _pre_tax_accounts_for_owner(c, owner_idx)
    balances = {a['id']: float(a.get('balance', 0.0) or 0.0) for a in accounts}
    available_balance = sum(balances.values())
    source_account = max(balances, key=balances.get) if balances else ''

    cap = _core.qlac_premium_limit(year, brk_inf)
    existing_key = 'h_qlac' if owner_idx == 0 else 'wife_qlac'
    already_committed = float((c.get(existing_key) or {}).get('premium', 0.0) or 0.0)
    remaining_cap = max(0.0, cap - already_committed)

    recommended = round(min(remaining_cap, available_balance) / 100.0) * 100.0
    recommended = max(0.0, recommended)

    dob_key = 'h_dob_yr' if owner_idx == 0 else 'w_dob_yr'
    dob_year = c.get(dob_key)
    latest_income_start_year = (
        _core.qlac_income_start_year_cap(dob_year) if dob_year else None
    )

    notes = [
        f"Statutory aggregate QLAC premium cap for {year}: ${cap:,.0f} (indexed annually; not a per-account limit).",
    ]
    if already_committed > 0:
        notes.append(f"${already_committed:,.0f} already committed to this person's QLAC, leaving ${remaining_cap:,.0f} of statutory headroom.")
    if not accounts:
        notes.append("No traditional IRA/401(k)/403(b)/SEP-IRA account found for this person -- a QLAC can only be funded from a pre-tax retirement account.")
    elif available_balance < remaining_cap:
        notes.append(f"Limited by available pre-tax balance (${available_balance:,.0f}) rather than the statutory cap.")
    if latest_income_start_year is not None:
        notes.append(f"Income must begin no later than the year this person turns 85 (plan year {latest_income_start_year}).")
    notes.append("The premium is excluded from this person's RMD-divisor balance once the contract is purchased -- RMDs shrink immediately, even though QLAC income itself is deferred.")

    return {
        "year": year,
        "owner_idx": owner_idx,
        "recommended_premium": recommended,
        "statutory_cap": cap,
        "already_committed": already_committed,
        "available_pre_tax_balance": available_balance,
        "source_account": source_account,
        "latest_income_start_year": latest_income_start_year,
        "notes": notes,
    }


__all__ = ["recommend_qlac_premium"]
