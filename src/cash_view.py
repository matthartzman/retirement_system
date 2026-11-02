"""Read-only view for the "Cash in investment accounts" panel (cash tracking Phase 5): nothing is stored.

Per account with a broker import: balance and its anchor (cash design 4.5), the account's ``CASH`` lot and the difference,
the last cash flow, unpaired transfers; cash income of the year grouped by the account's tax class (design 4.6); and one
account's ledger rows with their pairing status. Ledgers come from ``cash_ledger``, pairing from ``cash_pairing``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from . import active_plan
from .platform_runtime import today
from .cash_ledger import account_ledger
from .cash_pairing import pair_transfers
from .sales_confirm import default_tax_class

_EPS = 0.005


def _num(x: Any) -> float:
    try:
        return float(str(x).replace(",", "") or 0)
    except ValueError:
        return 0.0


def _accounts(store: Any) -> list[str]:
    return sorted({i["account"] for i in store.broker.list_imports() if i["status"] == "applied"})


def _monarch_names(store: Any, account: str) -> set[str]:
    return {str(r.get("Account") or "").strip().lower() for r in store.dataset("ytd_account_setup").rows()
            if str(r.get("Mapped Investment Account") or "").strip().lower() == account.strip().lower()}


def _flow(r: Mapping[str, Any]) -> float:
    return 0.0 if (r["in_kind"] or not r["counts"]) else float(r["amount"])


def anchor(ledger: list[Mapping[str, Any]], lot: Mapping[str, Any] | None) -> dict[str, Any]:
    """``{type, balance, as_of}``: the file's latest running balance, else the confirmed CASH lot, else unanchored.
    Counted flows dated after the anchor (rows no broker file covers) are added. Within one day the first stored
    row is the latest (the files list newest first)."""
    dated = [r for r in ledger if r.get("cash_balance") is not None]
    if dated:
        last = max(r["date"] for r in dated)
        base = next(r["cash_balance"] for r in dated if r["date"] == last)
        kind, when = "broker balance", last
    elif lot is not None and str(lot.get("purchase_date") or ""):
        base, kind, when = _num(lot.get("shares")), "confirmed CASH lot", str(lot["purchase_date"])
    else:
        return {"type": "unanchored", "balance": None, "as_of": None}
    after = sum(_flow(r) for r in ledger if r["date"] > when)
    return {"type": kind, "balance": round(base + after, 2), "as_of": max([when] + [r["date"] for r in ledger if r["date"] > when])}


def _ledgers(store: Any, accounts: list[str]) -> dict[str, list[dict[str, Any]]]:
    return pair_transfers({a: account_ledger(store, a, _monarch_names(store, a)) for a in accounts})


def _cash_lot(store: Any, account: str) -> dict[str, Any] | None:
    lots = [l for l in store.dataset("holdings").rows()
            if str(l.get("account") or "").strip().casefold() == account.casefold()
            and str(l.get("symbol") or "").strip().upper() == "CASH"]
    return lots[0] if len(lots) == 1 else None


def build_view(store: Any, *, year: int | None = None) -> dict[str, Any]:
    year = year or today().year
    accounts = _accounts(store)
    ledgers = _ledgers(store, accounts)
    rows, income = [], {}
    for a in accounts:
        led, lot = ledgers[a], _cash_lot(store, a)
        an = anchor(led, lot)
        lot_shares = _num(lot.get("shares")) if lot else None
        flows = [r for r in led if r["counts"] and not r["in_kind"]]
        rows.append({"account": a, "balance": an["balance"], "as_of": an["as_of"], "anchor": an["type"],
                     "cash_lot": lot_shares, "lot_date": (lot or {}).get("purchase_date") or "",
                     "difference": None if an["balance"] is None or lot_shares is None else round(an["balance"] - lot_shares, 2),
                     "last_flow": max((r["date"] for r in flows), default=None),
                     "unmatched": sum(1 for r in led if r["pair_status"] == "unmatched"),
                     "review": sum(1 for r in led if r["needs_review"])})
        cls = default_tax_class(store, a)
        for r in led:
            if r["class"] == "income" and r["counts"] and r["date"][:4] == f"{year:04d}":
                income[cls] = round(income.get(cls, 0.0) + float(r["amount"]), 2)
    return {"year": year, "accounts": rows, "income_by_tax_class": income}


def ledger_view(store: Any, account: str) -> dict[str, Any]:
    accounts = _accounts(store)
    if account not in accounts:
        return {"account": account, "rows": []}
    out = [{k: r[k] for k in ("date", "class", "amount", "cash_balance", "pair_status", "partner_account", "source",
                              "description", "counts", "in_kind", "needs_review")} for r in _ledgers(store, accounts)[account]]
    return {"account": account, "rows": out}


def view(input_dir: str | Path, *, account: str | None = None, year: int | None = None) -> dict[str, Any]:
    with active_plan.workspace_store(Path(input_dir).parent) as store:
        return ledger_view(store, account) if account else build_view(store, year=year)
