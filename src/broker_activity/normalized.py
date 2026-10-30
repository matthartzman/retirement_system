"""Shared normalized output of the broker activity (all-transactions history) parsers.

Pure data and helpers; every broker parser returns a ``ParsedActivity`` of rows with ``ROW_FIELDS``. See
``documentation/future/superpowers/plans/2026-10-30-broker-activity-bulk-import-design-and-plan.md`` section 3.1.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Mapping

ROW_FIELDS = ("run_date", "settle_date", "kind", "sweep", "action", "symbol", "description", "quantity", "price",
              "commission", "fees", "accrued_interest", "amount", "line")
KINDS = ("sell", "buy", "reinvest", "dividend", "interest", "cap_gain_short", "cap_gain_long", "foreign_tax",
         "return_of_capital", "other")
TRADE_KINDS = ("sell", "buy", "reinvest")
INCOME_KINDS = ("dividend", "interest", "cap_gain_short", "cap_gain_long", "foreign_tax", "return_of_capital")
# Money-market sweep funds held at par: they make no lot and no sale (their dividends are still income).
SWEEP_SYMBOLS = frozenset({"FDRXX", "SPAXX", "FZFXX", "SPRXX", "FCASH", "CORE", "FTEXX", "FZDXX"})


def us_date(text: str) -> date:
    """``M/D/YYYY`` (zero padded or not)."""
    m, d, y = (int(x) for x in text.strip().split("/"))
    return date(y, m, d)


def number(text: Any) -> float | None:
    """A cell as a float: ``None`` for empty or ``--``, ``(1.5)`` is negative, ``$`` and ``,`` are dropped."""
    t = str(text or "").strip().replace(",", "").replace("$", "")
    if t in ("", "--"):
        return None
    neg = t.startswith("(") and t.endswith(")")
    value = float(t.strip("()"))
    return -value if neg else value


@dataclass
class ParsedActivity:
    broker: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def date_range(rows: Iterable[Mapping[str, Any]]) -> tuple[str | None, str | None]:
    dates = sorted(r["run_date"] for r in rows)
    return (dates[0], dates[-1]) if dates else (None, None)


def _q(value: Any) -> str:
    return "" if value is None else ("%.6f" % value if isinstance(value, float) else str(value))


def row_hints(rows: Iterable[Mapping[str, Any]], default: str | None = None) -> list[str]:
    """The distinct account hints of ``rows`` in first-seen order. A row without its own ``account_hint`` takes
    ``default`` (the file-level hint); ``""`` stands for "no hint known"."""
    out: list[str] = []
    for r in rows:
        h = r.get("account_hint") or default or ""
        if h not in out:
            out.append(h)
    return out


def assign_row_keys(rows: list[dict[str, Any]], *, broker: str, account: str) -> None:
    """Give each row a ``row_key``: a hash of broker, account, run date, action, symbol, quantity and amount, then
    ``#n`` for the n-th identical row in the file, so two identical same-day fills are both kept and a re-import of
    the same file produces the same keys."""
    seen: dict[str, int] = {}
    for r in rows:
        ident = "|".join(_q(x) for x in (broker, account.strip().lower(), r["run_date"], r["action"], r["symbol"],
                                         r["quantity"], r["amount"]))
        digest = hashlib.sha1(ident.encode("utf-8")).hexdigest()[:20]
        n = seen.get(digest, 0)
        seen[digest] = n + 1
        r["row_key"] = f"{digest}#{n}"


def group_orders(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Combine non-sweep sell rows into orders by (symbol, run date, price): one order can arrive as a whole-share row
    plus a fractional row. Shares are positive; proceeds are the summed Amount (already net of fees)."""
    orders: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        if r["kind"] != "sell" or r["sweep"] or not r["symbol"]:
            continue
        key = (r["symbol"], r["run_date"], round(r["price"] or 0.0, 6))
        o = orders.setdefault(key, {"symbol": r["symbol"], "trade_date": r["run_date"], "settle_date": r["settle_date"],
                                    "price": r["price"], "shares": 0.0, "proceeds": 0.0, "fees": 0.0, "row_keys": []})
        o["shares"] += abs(r["quantity"] or 0.0)
        o["proceeds"] += r["amount"] or 0.0
        o["fees"] += (r["fees"] or 0.0) + (r["commission"] or 0.0)
        o["row_keys"].append(r["row_key"])
        o["settle_date"] = o["settle_date"] or r["settle_date"]
    out = []
    for o in sorted(orders.values(), key=lambda o: (o["trade_date"], o["symbol"])):
        o.update(shares=round(o["shares"], 6), proceeds=round(o["proceeds"], 2), fees=round(o["fees"], 2))
        out.append(o)
    return out
