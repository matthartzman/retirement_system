"""Pair-status tax floor (cash plan section 10 item 3, owner choice 2026-11-03: "floor"). DEFAULT OFF.

When ``cash_pair_status_tax`` is TRUE, cash already reported as an ``external_withdrawal`` from a PRE-TAX account in the
plan's first year (``plan_start``) is forced out of that account in that year, and taxed as ordinary income exactly like
an RMD: it is added to ``rmd_taxable_total`` (which both taxes it and credits it as cash toward spending, so the cascade
draws that much less elsewhere). Actual money taken can therefore never be taxed less than it really was.
Internal pairs, unmatched rows and ``excess_return`` add nothing (cash plan 9.4, 9.5). Later years are untouched.

Taxable, Roth and HSA accounts are NOT wired: their tax needs lots/basis or the qualified-withdrawal rules; they are
reported by ``worked_example`` for the owner but add no tax. With the setting OFF nothing here runs.
"""
from __future__ import annotations

from typing import Any, Mapping


def enabled(c: Mapping[str, Any]) -> bool:
    return bool(c.get("cash_pair_status_tax"))


def floor_draws(c: Mapping[str, Any], bal: Mapping[str, float], year: int) -> dict[str, float]:
    """``{account: dollars}`` to force out of pre-tax accounts this year; ``{}`` when off or not the first year.
    Capped at each account's balance. ``c['cash_pair_floor_draws']`` is the reported amounts, set by ``feed``."""
    if not enabled(c) or year != c.get("plan_start"):
        return {}
    out = {}
    for acct, amt in (c.get("cash_pair_floor_draws") or {}).items():
        d = min(max(0.0, float(amt)), max(0.0, float(bal.get(acct, 0.0))))
        if d > 0:
            out[acct] = d
    return out


def reported_draws(store: Any, year: int) -> dict[str, float]:
    """Year-to-date reported ``external_withdrawal`` by pre-tax account, from the cash ledgers (read only)."""
    from . import cash_view
    from .sales_confirm import default_tax_class
    accounts = cash_view._accounts(store)
    ledgers = cash_view._ledgers(store, accounts)
    out = {}
    for a in accounts:
        if default_tax_class(store, a) == "pre_tax":
            amt = cash_view.withdrawals_by_status(ledgers[a], year)["external_withdrawal"]
            if amt > 0:
                out[a] = amt
    return out


def feed(cfg: dict[str, Any]) -> None:
    """Put the reported draws into the engine config when the setting is on. Read only; failure leaves the plan unchanged."""
    if not enabled(cfg):
        return
    from . import active_plan, workspace_context
    from pathlib import Path
    try:
        root = Path(workspace_context.workspace_input_dir()).parent
        with active_plan.workspace_store(root) as store:
            cfg["cash_pair_floor_draws"] = reported_draws(store, int(cfg["plan_start"]))
    except Exception as exc:          # a missing cash store must never break a plan run
        cfg["cash_pair_floor_draws"] = {}
        cfg["cash_pair_floor_error"] = str(exc)
