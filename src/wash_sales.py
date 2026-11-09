"""Possible wash-sale detection for the realized-sales ledger (plan section 8). Pure, no I/O. Flag only.

A confirmed taxable loss sale is flagged when the household bought the same (or a substantially identical)
security in ANY account within 30 days before or after the sale. Rules (Sales Ledger v3 spec, "Wash sales"):

* W1  shares sold in the same sale are not replacements (a buy that is one of the sold lots' own purchases is skipped);
* W2  sales are processed in date order and each replacement buy's shares serve only one sale, oldest buys first;
* W3  disallowed = loss x replacement shares used / shares sold, spread across the replacement buys in W2 order.

A sale is the grouping key ``account|symbol|sale_date`` (its lots are the ledger rows). The result says what is disallowed
and which replacement buys carry it; the basis add-back itself lives in ``wash_adjustments``.

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
        b = {"date": d.isoformat(), "symbol": symbol, "shares": shares, "account": str(r.get("account") or ""), "source": source}
        price = _num(r.get("price", r.get("purchase_price")))
        if price is not None:
            b["price"] = price
        if r.get("txn_id") is not None:
            b["txn_id"] = r["txn_id"]
        if r.get("is_reinvest") or str(r.get("lot_type") or "").lower() == "reinvest":
            b["is_reinvest"] = True
        out.append(b)
    return out


def dedupe_buys(*groups: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Merge purchase lists from several sources, keeping the first of any purchase seen twice (same account,
    symbol, date and share count), so one buy that shows in the holdings, a broker file and Monarch counts once.
    Pass the sources in order of trust."""
    seen, out = set(), []
    for g in groups:
        for b in g:
            key = (b.get("account"), b["symbol"], b["date"], round(float(b["shares"]), 6))
            if key not in seen:
                seen.add(key)
                out.append(dict(b))
    return out


def _g(x: float) -> str:
    return f"{x:g}"


def sale_key(s: Mapping[str, Any]) -> str:
    """The grouping key shared by the ledger's sale rows, wash reviews and wash adjustments."""
    return f"{s.get('account')}|{str(s.get('symbol')).strip().upper()}|{s.get('sale_date')}"


def detect_wash_sales(sales: Iterable[Mapping[str, Any]], buys: Iterable[Mapping[str, Any]], *,
                      identical_groups: Mapping[str, str] | None = None,
                      accounts: Mapping[str, Mapping[str, Any]] | None = None,
                      reviews: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    """Return ``{sale_key: {flag, note, loss, shares_sold, replacement_shares, disallowed, deductible, repurchased_shares,
    ira, matches, sale_ids}}`` for each flagged loss sale.

    ``sales`` are ledger rows; only confirmed taxable loss lots are considered, and a sale's loss and shares are those of its
    loss lots. ``buys`` come from ``buys_from_rows``; ``accounts`` maps an account name to ``{label, tax_class}`` (a non-taxable
    class marks that replacement as lost permanently: no basis add-back). A sale the user reviewed as ``not_wash`` is skipped.
    """
    groups = {str(k).strip().upper(): v for k, v in (identical_groups or {}).items()}
    accounts, reviews = accounts or {}, reviews or {}
    buy_list = [dict(b, symbol=str(b["symbol"]).strip().upper(), _d=_day(b["date"]), _left=float(b["shares"])) for b in buys]
    buy_list.sort(key=lambda b: (b["_d"] or date.max, str(b.get("account")), b["symbol"]))
    sales = list(sales)
    sold_in_sale: dict[str, set[tuple]] = {}          # W1: every lot of a sale (gain or loss), by its own purchase
    for s in sales:
        if s.get("status", "confirmed") == "confirmed":
            sold_in_sale.setdefault(sale_key(s), set()).add((s.get("account"), str(s["symbol"]).strip().upper(), _day(s.get("purchase_date"))))
    sales_by_key: dict[str, list[Mapping[str, Any]]] = {}
    for s in sales:
        gain = s.get("gain")
        if (s.get("status", "confirmed") != "confirmed" or s.get("tax_class", "taxable") != "taxable"
                or gain is None or gain >= 0 or _day(s["sale_date"]) is None):
            continue
        sales_by_key.setdefault(sale_key(s), []).append(s)
    out: dict[str, dict[str, Any]] = {}
    for key, lots in sorted(sales_by_key.items(), key=lambda kv: (kv[1][0]["sale_date"], kv[0])):
        if (reviews.get(key) or {}).get("outcome") == "not_wash":
            continue
        sold_on, symbol = _day(lots[0]["sale_date"]), str(lots[0]["symbol"]).strip().upper()
        loss = -sum(float(l["gain"]) for l in lots)
        shares_sold = sum(float(l.get("shares") or 0.0) for l in lots)
        group = groups.get(symbol)
        own = sold_in_sale.get(key, set())                                                         # W1
        matches, room = [], shares_sold
        for b in buy_list:
            if b["_d"] is None or b["_left"] <= 1e-9 or (b["account"], b["symbol"], b["_d"]) in own:
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
            used = min(b["_left"], room) if shares_sold else 0.0                                   # W2: one sale per share
            if used <= 1e-9:
                continue
            b["_left"] -= used
            room -= used
            info = accounts.get(b["account"], {})
            ira = info.get("tax_class") in NON_TAXABLE
            price = b.get("price")
            matches.append({"txn_id": b.get("txn_id"), "date": b["date"], "days": days, "symbol": b["symbol"], "shares": float(b["shares"]),
                            "account": b["account"], "label": info.get("label") or b["account"], "ira": ira, "taxable": not ira,
                            "is_reinvest": bool(b.get("is_reinvest")), "value": None if price is None else round(float(b["shares"]) * float(price), 2),
                            "source": b.get("source", ""), "reason": reason, "used_shares": used,
                            "amount": round(loss * used / shares_sold, 2)})                            # W3
        if not matches:
            continue
        matches.sort(key=lambda m: (abs(m["days"]), m["date"], m["account"]))
        used_total = sum(m["used_shares"] for m in matches)
        disallowed = round(loss * used_total / shares_sold, 2)
        review = reviews.get(key) or {}
        if review.get("outcome") == "broker_reported" and review.get("broker_amount") is not None:
            disallowed = round(min(float(review["broker_amount"]), loss), 2)                       # the broker's figure replaces ours
        first = matches[0]
        n = abs(first["days"])
        bought = (f"bought {first['symbol']} the same day" if n == 0 else
                  f"bought {first['symbol']} {n} days {'later' if first['days'] > 0 else 'earlier'}")
        note = f"Loss on {symbol}; {bought} in {first['label']}"
        if len(matches) > 1:
            note += f" (and {len(matches) - 1} more)"
        if shares_sold and used_total < shares_sold:
            note += f"; {_g(used_total)} of {_g(shares_sold)} shares repurchased"
        ira = any(m["ira"] for m in matches)
        if ira:
            note += ". Repurchase in an IRA-type account: the loss is disallowed with no basis add-back"
        out[key] = {"flag": "possible", "note": note, "loss": round(loss, 2), "shares_sold": shares_sold, "replacement_shares": used_total,
                    "repurchased_shares": used_total, "disallowed": disallowed, "deductible": round(loss - disallowed, 2), "ira": ira,
                    "matches": matches, "sale_ids": [int(l["sale_id"]) for l in lots]}
    return out


def plan_flag_updates(sales: Iterable[Mapping[str, Any]], detected: Mapping[str, Mapping[str, Any]]) -> list[tuple[int, str, str]]:
    """The ``(sale_id, wash_flag, wash_note)`` writes that bring ledger rows in line with ``detected`` (keyed by sale key).

    A row the user confirmed (``confirmed_by_user``) is never touched; a stale ``possible`` row that no longer matches
    (including a sale reviewed as not a wash sale, which detection skips) goes back to ``none``; rows already correct
    produce no write. Only a sale's loss lots carry the flag.
    """
    updates = []
    for s in sales:
        sid, current = int(s["sale_id"]), s.get("wash_flag", "none")
        if current == "confirmed_by_user":
            continue
        live = s.get("status", "confirmed") == "confirmed" and s.get("tax_class", "taxable") == "taxable" and s.get("gain") is not None and s["gain"] < 0
        hit = detected.get(sale_key(s)) if live else None
        want = (hit["flag"], hit["note"]) if hit else ("none", "")
        if (current, s.get("wash_note", "")) != want:
            updates.append((sid, want[0], want[1]))
    return updates


def open_windows(store, today: date, *, label=lambda a: a, identical_groups: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    """Prevention: for every confirmed taxable loss sale less than 31 days old, the household accounts that hold the same fund and
    have reinvested it in the last 12 months (they would buy replacement shares before the window closes), and those that hold it
    without a recent reinvest (a 401(k) can buy through payroll). The window closes on the sale date plus 30 days. The app cannot see a
    broker's DRIP setting, so this only ever says an account "has reinvested"."""
    groups = {str(k).strip().upper(): v for k, v in (identical_groups or {}).items()}

    def alike(symbol: str, target: str) -> bool:
        s, t = str(symbol).strip().upper(), str(target).strip().upper()
        return s == t or (groups.get(t) is not None and groups.get(s) == groups.get(t))

    since = date.fromordinal(today.toordinal() - 365).isoformat()
    log = store.transactions.list()
    holders: dict[str, set[str]] = {}
    for r in store.dataset("holdings").rows():
        if _num(r.get("shares")) and (_num(r.get("shares")) or 0) > 0:
            holders.setdefault(str(r.get("symbol") or "").strip().upper(), set()).add(str(r.get("account") or ""))
    out, seen = [], set()
    for s in store.sales.list_sales():
        gain, sold_on = s.get("gain"), _day(s["sale_date"])
        if s["status"] != "confirmed" or s["tax_class"] != "taxable" or gain is None or gain >= 0 or sold_on is None:
            continue
        key = sale_key(s)
        age = (today - sold_on).days
        if key in seen or age < 0 or age > WINDOW_DAYS:
            continue
        seen.add(key)
        symbol = str(s["symbol"]).strip().upper()
        reinvesting = sorted({r["account"] for r in log if r["type"] == "reinvest" and r["txn_date"] >= since and alike(r["symbol"], symbol)})
        holding = sorted({a for sym, accts in holders.items() if alike(sym, symbol) for a in accts} - set(reinvesting))
        out.append({"sale_key": key, "symbol": symbol, "closes_on": date.fromordinal(sold_on.toordinal() + WINDOW_DAYS).isoformat(),
                    "reinvesting": [label(a) for a in reinvesting], "also_holds": [label(a) for a in holding]})
    return sorted(out, key=lambda w: (w["closes_on"], w["sale_key"]))
