"""Verified-account gate for the pair-status floor (year-end transition Phase 4, owner decisions 2026-11-03).

Reported withdrawals reach the engine (``cash_tax_floor``, setting ``cash_pair_status_tax``, default OFF) only for an account
the owner has VERIFIED against a closed year (the account is in a ``cash_year_close`` record, so its plan-minus-reported
difference has been reviewed) and that has no ``unmatched`` row dated in the current year. The mark is a ``plan_meta`` key
``cash.verified_account.<account>``: per account, reversible, audited by the route. Half-pairs stay ``unmatched`` and so
keep their account out. Nothing here changes an engine number by itself.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from . import cash_view, cash_year_close
from .platform_runtime import today

KEY = "cash.verified_account.%s"


class VerifyError(ValueError):
    """A verification the rules do not allow; the message is shown to the owner."""


def is_verified(store: Any, account: str) -> bool:
    return store.get_meta(KEY % account.casefold()) is not None


def _closed_covering(store: Any, account: str, ledgers: Mapping[str, list[Mapping[str, Any]]]) -> int | None:
    """Newest closed year whose record includes ``account``, else ``None``."""
    years = sorted({int(r["date"][:4]) for led in ledgers.values() for r in led if r["date"][:4].isdigit()}, reverse=True)
    for y in years:
        rec = cash_year_close.record(store, y)
        if rec and account.casefold() in {a.casefold() for a in rec["reported"]}:
            return y
    return None


def set_verified(store: Any, account: str, verified: bool, *, ledgers: Mapping[str, list[Mapping[str, Any]]]) -> None:
    if not verified:
        store.delete_meta(KEY % account.casefold())
        return
    year = _closed_covering(store, account, ledgers)
    if year is None:
        raise VerifyError(f"{account} is not in any closed year. Close a year that includes it and review its difference first.")
    store.set_meta(KEY % account.casefold(), json.dumps({"verified": True, "closed_year": year, "at": today().isoformat()}))


def eligibility(store: Any, year: int, ledgers: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, dict[str, Any]]:
    out = {}
    for a, led in sorted(ledgers.items()):
        ver = is_verified(store, a)
        unm = sum(1 for r in led if r["pair_status"] == "unmatched" and r["date"][:4] == f"{year:04d}")
        reason = "" if ver and not unm else "not verified against a closed year" if not ver else f"{unm} unmatched row(s) dated {year}"
        out[a] = {"verified": ver, "eligible": ver and not unm, "reason": reason}
    return out


def gate(store: Any, year: int, ledgers: Mapping[str, list[Mapping[str, Any]]],
         reported: Mapping[str, float]) -> tuple[dict[str, float], dict[str, str]]:
    """``(kept, skipped)``: reported withdrawals of eligible accounts, and ``{account: reason}`` for the rest."""
    elig = eligibility(store, year, ledgers)
    kept, skipped = {}, {}
    for a, amt in reported.items():
        e = elig.get(a)
        if e and e["eligible"]:
            kept[a] = amt
        else:
            skipped[a] = e["reason"] if e else "not verified against a closed year"
    return kept, skipped


def service(input_dir: Any, account: str, verified: bool) -> dict[str, Any]:
    """Route body: set or clear the mark, return the account's gate state. Raises ``VerifyError`` when not allowed."""
    from pathlib import Path
    from . import active_plan
    root = Path(input_dir).parent
    with active_plan.workspace_store(root, write=True) as store:
        ledgers = cash_view._ledgers(store, cash_view._accounts(store))
        if account not in ledgers:
            raise VerifyError(f"{account} has no broker import.")
        set_verified(store, account, verified, ledgers=ledgers)
        return {"account": account, **eligibility(store, today().year, ledgers)[account]}
