from __future__ import annotations

"""The ``unmatched_sale`` hint for the Planner's reconcile page (sales ledger plan, step 2.3 / section 11).

When an account's gap between holdings and Monarch is within ``RECONCILE_MATCH_PCT`` of an unmatched sale
candidate (or a confirmed ledger sale) dated after Monarch's balance date, the row says that sale is the
likely reason. ``percent_mode`` fails closed: the hint then carries no dollar amount, share count or price.
"""

from typing import Any

RECONCILE_MATCH_PCT = 0.05  # same tolerance as the Trends reconcile card


def _amount(item: dict[str, Any], amount_key: str) -> float | None:
    amount = item.get(amount_key)
    if amount is None and item.get("shares") is not None and item.get("price") is not None:
        amount = float(item["shares"]) * float(item["price"])
    return abs(float(amount)) if amount is not None else None


def _shares_text(shares: Any) -> str:
    return f"{float(shares):g}"


def _hint(item: dict[str, Any], confirmed: bool, percent_mode: bool) -> dict[str, Any]:
    symbol, when = str(item.get("symbol") or "").upper(), item["sale_date"]
    if percent_mode:
        text = f"A sale of {symbol} is " + ("in the ledger." if confirmed else "waiting to be confirmed.")
        return {"kind": "unmatched_sale", "symbol": symbol, "sale_date": when, "text": text}
    what = f"Sale of ~{_shares_text(item['shares'])} {symbol} on {when}" if item.get("shares") is not None else f"Sale of {symbol} on {when}"
    text = what + (" is in the ledger; holdings or Monarch may not reflect it yet." if confirmed else " is waiting to be confirmed.")
    return {"kind": "unmatched_sale", "symbol": symbol, "sale_date": when, "shares": item.get("shares"), "text": text}


def sale_hints(rows: list[dict[str, Any]], candidates: list[dict[str, Any]], sales: list[dict[str, Any]],
               *, percent_mode: bool = False) -> dict[str, Any]:
    """``{"count": unmatched candidates, "by_row": {row id: hint}}`` for the comparison ``rows``."""
    unmatched = [c for c in candidates if c.get("state") == "unmatched"]
    pool = [(c, "amount", False) for c in unmatched] + [(s, "proceeds", True) for s in sales if s.get("status") == "confirmed"]
    by_row: dict[str, dict[str, Any]] = {}
    for row in rows:
        gap = row.get("difference")
        dates = [a.get("balance_date") for a in row.get("monarch_accounts") or [] if a.get("balance_date")]
        if gap is None or not dates:
            continue
        balance_date, label = max(dates), str(row.get("label") or "").strip().casefold()
        for item, amount_key, confirmed in pool:
            amount = _amount(item, amount_key)
            if (str(item.get("account") or "").strip().casefold() != label or item["sale_date"] <= balance_date
                    or amount is None or abs(abs(gap) - amount) > RECONCILE_MATCH_PCT * amount):
                continue
            by_row[row["id"]] = _hint(item, confirmed, percent_mode)
            break
    return {"count": len(unmatched), "by_row": by_row}
