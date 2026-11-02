"""Read-only Transactions view: purchases, reinvestments and sales per account, with the lots still held.

Phase 1 of ``documentation/future/superpowers/plans/2026-10-31-transaction-log-design-and-plan.md``. Built from data
that already exists (``broker_activity``, manual ``realized_sales`` rows, the holdings dataset); nothing is written.
Monarch-sourced sales are never listed (they stay in the sales queue). A broker redemption is a ``sell`` row.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from . import active_plan

TYPES = ("buy", "reinvest", "sell")
_LOT_KEYS = ("account", "symbol", "purchase_date", "purchase_price", "lot_type")


def _num(value: Any) -> float:
    try:
        return float(str(value).replace(",", "") or 0)
    except ValueError:
        return 0.0


def _lot_id(ref: dict[str, Any]) -> tuple:
    return tuple(str(ref.get(k, "")).strip().lower() for k in _LOT_KEYS)


def build_view(store: Any, *, account: str | None = None, symbol: str | None = None, year: int | None = None,
               types: Iterable[str] | None = None, held_only: bool = False) -> dict[str, Any]:
    wanted = {t for t in (types or ()) if t}
    holdings = [dict(r) for r in store.dataset("holdings").rows()]
    remaining: dict[tuple, float] = {}
    for h in holdings:
        remaining[_lot_id(h)] = remaining.get(_lot_id(h), 0.0) + _num(h.get("shares"))
    states = {c["candidate_id"]: c["state"] for c in store.sales.list_candidates()}

    rows: list[dict[str, Any]] = []
    for a in store.broker.activity(kinds=TYPES):
        if a["sweep"] or not a["symbol"]:
            continue
        row = {"date": a["run_date"], "account": a["account"], "type": a["kind"], "symbol": a["symbol"],
               "shares": abs(a["quantity"] or 0.0), "price": a["price"], "amount": a["amount"],
               "remaining": None, "linked": None, "source": "broker"}
        if a["kind"] == "sell":
            row["linked"] = states.get(a["candidate_id"]) if a["candidate_id"] else None
        elif a["lot_ref"]:
            row["remaining"] = remaining.get(_lot_id(a["lot_ref"]), 0.0)
        rows.append(row)
    for s in store.sales.list_sales():
        if s["source"] != "manual":
            continue
        rows.append({"date": s["sale_date"], "account": s["account"], "type": "sell", "symbol": s["symbol"],
                     "shares": s["shares"], "price": (s["proceeds"] / s["shares"]) if s["shares"] else None,
                     "amount": s["proceeds"], "remaining": None, "linked": f"sale {s['sale_id']}", "source": "manual"})

    def keep(r: dict[str, Any]) -> bool:
        return ((account is None or r["account"] == account) and (symbol is None or r["symbol"].upper() == symbol.upper())
                and (year is None or r["date"][:4] == f"{int(year):04d}") and (not wanted or r["type"] in wanted)
                and (not held_only or (r["type"] != "sell" and (r["remaining"] or 0.0) > 1e-6)))

    rows = sorted((r for r in rows if keep(r)), key=lambda r: (r["date"], r["account"], r["symbol"]))
    held = [{"account": h["account"], "symbol": h["symbol"], "purchase_date": h.get("purchase_date", ""),
             "price": _num(h.get("purchase_price")), "shares": _num(h.get("shares"))}
            for h in holdings if _num(h.get("shares")) > 1e-6
            and (account is None or h["account"] == account)
            and (symbol is None or str(h["symbol"]).upper() == symbol.upper())]
    held.sort(key=lambda h: (h["account"], h["symbol"], h["purchase_date"]))
    return {"rows": rows, "held": held}


def view(input_dir: str | Path, **filters: Any) -> dict[str, Any]:
    with active_plan.workspace_store(Path(input_dir).parent) as store:
        return build_view(store, **filters)
