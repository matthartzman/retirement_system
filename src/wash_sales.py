"""Possible wash-sale detection for the realized-sales ledger (plan section 8). Pure, no I/O. Flag only.

A confirmed taxable loss sale is flagged when the household bought the same (or a substantially identical)
security in ANY account within 30 days before or after the sale. Nothing is disallowed or adjusted here.

"Substantially identical" is the same symbol, plus any grouping the caller passes as ``identical_groups``
(symbol -> group key). The security master is deliberately not read: its asset-class/sleeve groups are the
*replacement* universe ``tlh.suggest_replacement`` uses to pick securities that are NOT substantially
identical, so treating them as identical would flag nearly every swap.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping

WINDOW_DAYS = 30
NON_TAXABLE = ("pre_tax", "roth", "hsa")
# Money-market sweep lots sit at par and are not purchases for this scan (plan sections 5.2b, 13).
DEFAULT_IGNORE_SYMBOLS = frozenset({"CASH"})


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def buys_from_rows(rows: Iterable[Mapping[str, Any]], *, source: str,
                   ignore_symbols: Iterable[str] = DEFAULT_IGNORE_SYMBOLS) -> list[dict[str, Any]]:
    """Normalize purchase-like rows (holdings lots, Monarch Buy rows, broker buys and reinvestments) to
    ``{date, symbol, shares, account, source}``. Rows with no usable date, symbol or positive shares and
    ignored symbols (money-market sweep) are dropped."""
    skip = {str(s).strip().upper() for s in ignore_symbols}
    out = []
    for r in rows:
        d = _day(r.get("purchase_date") or r.get("date"))
        symbol = str(r.get("symbol") or "").strip().upper()
        shares = _num(r.get("shares", r.get("quantity")))
        if d is None or not symbol or symbol in skip or shares is None or shares <= 0:
            continue
        out.append({"date": d.isoformat(), "symbol": symbol, "shares": shares,
                    "account": str(r.get("account") or ""), "source": source})
    return out


def _g(x: float) -> str:
    return f"{x:g}"


def detect_wash_sales(sales: Iterable[Mapping[str, Any]], buys: Iterable[Mapping[str, Any]], *,
                      identical_groups: Mapping[str, str] | None = None,
                      accounts: Mapping[str, Mapping[str, Any]] | None = None) -> dict[int, dict[str, Any]]:
    """Return ``{sale_id: {flag, note, repurchased_shares, ira, matches}}`` for each flagged loss sale.

    ``sales`` are ledger rows; ``buys`` come from ``buys_from_rows``; ``accounts`` maps an account name to
    ``{label, tax_class}`` (label defaults to the account name; a non-taxable class marks the repurchase as
    an IRA-type one, the worst case because the loss is lost with no basis add-back). The purchase that
    created the sold lot is never counted as its own repurchase.
    """
    groups = {str(k).strip().upper(): v for k, v in (identical_groups or {}).items()}
    accounts = accounts or {}
    buy_list = [dict(b, symbol=str(b["symbol"]).strip().upper(), _d=_day(b["date"])) for b in buys]
    out: dict[int, dict[str, Any]] = {}
    for s in sales:
        gain = s.get("gain")
        if (s.get("status", "confirmed") != "confirmed" or s.get("tax_class", "taxable") != "taxable"
                or gain is None or gain >= 0):
            continue
        sold_on, symbol = _day(s["sale_date"]), str(s["symbol"]).strip().upper()
        if sold_on is None:
            continue
        group = groups.get(symbol)
        own = (s.get("account"), symbol, _day(s.get("purchase_date")))
        matches = []
        for b in buy_list:
            if b["_d"] is None or (b["account"], b["symbol"], b["_d"]) == own:
                continue
            days = (b["_d"] - sold_on).days
            if abs(days) > WINDOW_DAYS:
                continue
            if b["symbol"] == symbol:
                reason = "same symbol"
            elif group is not None and groups.get(b["symbol"]) == group:
                reason = f"same group {group}"
            else:
                continue
            info = accounts.get(b["account"], {})
            matches.append({"date": b["date"], "days": days, "symbol": b["symbol"], "shares": float(b["shares"]),
                            "account": b["account"], "label": info.get("label") or b["account"],
                            "ira": info.get("tax_class") in NON_TAXABLE, "source": b.get("source", ""),
                            "reason": reason})
        if not matches:
            continue
        matches.sort(key=lambda m: (abs(m["days"]), m["date"], m["account"]))
        first = matches[0]
        n = abs(first["days"])
        bought = (f"bought {first['symbol']} the same day" if n == 0 else
                  f"bought {first['symbol']} {n} days {'later' if first['days'] > 0 else 'earlier'}")
        note = f"Loss on {symbol}; {bought} in {first['label']}"
        if len(matches) > 1:
            note += f" (and {len(matches) - 1} more)"
        repurchased = sum(m["shares"] for m in matches)
        sold = float(s.get("shares") or 0.0)
        if sold and repurchased < sold:
            note += f"; {_g(repurchased)} of {_g(sold)} shares repurchased"
        ira = any(m["ira"] for m in matches)
        if ira:
            note += ". Repurchase in an IRA-type account: the loss is disallowed with no basis add-back"
        out[int(s["sale_id"])] = {"flag": "possible", "note": note, "repurchased_shares": repurchased,
                                  "ira": ira, "matches": matches}
    return out


def plan_flag_updates(sales: Iterable[Mapping[str, Any]],
                      detected: Mapping[int, Mapping[str, Any]]) -> list[tuple[int, str, str]]:
    """The ``(sale_id, wash_flag, wash_note)`` writes that bring ledger rows in line with ``detected``.

    A row the user confirmed (``confirmed_by_user``) is never touched; a stale ``possible`` row that no
    longer matches goes back to ``none``; rows already correct produce no write.
    """
    updates = []
    for s in sales:
        sid, current = int(s["sale_id"]), s.get("wash_flag", "none")
        if current == "confirmed_by_user":
            continue
        hit = detected.get(sid)
        want = (hit["flag"], hit["note"]) if hit else ("none", "")
        if (current, s.get("wash_note", "")) != want:
            updates.append((sid, want[0], want[1]))
    return updates
