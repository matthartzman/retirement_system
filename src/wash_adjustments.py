"""Wash-sale basis add-back (Sales Ledger v3, rule W4/W5): where a disallowed loss goes when the replacement shares sit in a taxable
account. Stored as ``wash_adjustments`` records, never as edits to log rows: ``open_lots`` and the holdings rewrite apply them,
so a later Void or Edit of either side simply recomputes them.

``recompute_adjustments`` rebuilds every record from ``wash_sales.detect_wash_sales`` over the log's own purchases (a replacement
has to be a log lot to carry the add-back). Sales are processed in date order inside the detector, and a lot sold later takes its
add-back into the sale's basis through ``open_lots`` (pro rata by shares), so a chain (W5) falls out of recording each sale with the
adjusted cost. A replacement in an IRA, Roth or HSA gets no add-back: that part of the loss is lost for good.
"""
from __future__ import annotations

from typing import Any

from .wash_sales import buys_from_rows, detect_wash_sales


def _log_buys(store) -> list[dict[str, Any]]:
    rows = [{"date": r["txn_date"], "symbol": r["symbol"], "shares": r["shares"], "account": r["account"], "price": r["price"],
             "txn_id": r["txn_id"], "is_reinvest": r["type"] == "reinvest"}
            for r in store.transactions.list() if r["type"] in ("buy", "reinvest")]
    return buys_from_rows(rows, source="log")


def compute(store) -> list[dict[str, Any]]:
    """The adjustment records the current ledger, log and reviews imply (nothing is written)."""
    from .sales_tax_year import _account_classes
    sales = store.sales.list_sales()
    if not any(s["status"] == "confirmed" and s["gain"] is not None and s["gain"] < 0 for s in sales):
        return []
    buys = _log_buys(store)
    reviews = store.sales.reviews()
    detected = detect_wash_sales(sales, buys, accounts=_account_classes(sales, {b["account"] for b in buys}), reviews=reviews)
    by_id = {s["sale_id"]: s for s in sales}
    out = []
    for key, d in detected.items():
        lots = [by_id[i] for i in d["sale_ids"]]
        tacked = max(str(l["purchase_date"]) for l in lots if l.get("purchase_date")) if any(l.get("purchase_date") for l in lots) else None
        sale_account = key.split("|")[0]
        broker_reported = (reviews.get(key) or {}).get("outcome") == "broker_reported"
        for m in d["matches"]:
            if not m["taxable"] or m["txn_id"] is None or (broker_reported and m["account"] == sale_account):
                continue          # IRA-type: lost; broker-reported: the broker adjusted its own account's lot
            out.append({"sale_key": key, "replacement_txn_id": int(m["txn_id"]), "shares": m["used_shares"], "amount": m["amount"],
                        "tacked_purchase_date": tacked})
    return out


def recompute_adjustments(store) -> int:
    """Rebuild every stored adjustment (call inside the caller's write transaction); returns how many records there are."""
    rows = compute(store)
    store.transactions.replace_wash_adjustments(rows)
    return len(rows)


def by_lot(store) -> dict[int, dict[str, Any]]:
    """``{replacement lot txn_id: {amount, tacked}}`` summed over its adjustment records (the latest tacked date wins)."""
    out: dict[int, dict[str, Any]] = {}
    for a in store.transactions.wash_adjustments():
        slot = out.setdefault(a["replacement_txn_id"], {"amount": 0.0, "tacked": None})
        slot["amount"] += float(a["amount"])
        if a["tacked_purchase_date"] and (slot["tacked"] is None or a["tacked_purchase_date"] > slot["tacked"]):
            slot["tacked"] = a["tacked_purchase_date"]
    return out
