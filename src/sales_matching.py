"""Monarch ``Sell`` rows as realized-sales inputs (ledger plan 5.2): extractor, parser, queue loader, suggestions.

Read-only over the YTD transaction rows: Sell rows stay excluded from spending by ``ytd_tracking`` and are not
reclassified here. The loader queues unmatched ``sale_candidates`` through ``SalesRepo.add_candidate`` (a repo is
passed in; this module imports no store). Nothing here confirms a sale: a suggestion only pairs a Monarch
candidate with one holdings-import event, and the user still chooses the lots.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Iterable, Mapping

from .ytd_tracking import parse_date, parse_money

SELL_CATEGORY = "sell"
MATCH_DAY_TOLERANCE = 3
MATCH_SHARE_TOLERANCE = 1e-4

# "Sold <shares> <TICKER> @ <price>". The ticker must be upper case (a fund name is not a ticker), so only the
# word "Sold" is case-insensitive. Tickers may carry a class suffix (BRK.B, BRK-B).
_SOLD = re.compile(
    r"(?i:\bsold)\s+(?P<shares>\d[\d,]*(?:\.\d+)?|\.\d+)\s+(?P<symbol>[A-Z][A-Z0-9]{0,5}(?:[.\-][A-Z0-9]{1,2})?)\s*@\s*\$?\s*(?P<price>\d[\d,]*(?:\.\d+)?|\.\d+)(?![\w.])")


def _number(text: str) -> float:
    return float(text.replace(",", ""))


def parse_sell_text(text: Any) -> dict[str, Any] | None:
    """``{symbol, shares, price}`` from a Monarch description, or ``None`` when it is not clearly a sale line."""
    m = _SOLD.search(str(text or ""))
    if m is None:
        return None
    shares, price = _number(m["shares"]), _number(m["price"])
    if shares <= 0 or price < 0:
        return None
    return {"symbol": m["symbol"], "shares": shares, "price": price}


def sell_rows(ytd_rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The rows whose Category is Sell, as given (not copied, not changed)."""
    return [r for r in ytd_rows if re.sub(r"\s+", " ", str(r.get("Category") or "").strip().lower()) == SELL_CATEGORY]


def parse_sell_row(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """One candidate dict from a Sell row; symbol/shares/price stay ``None`` for a bare row (never guessed).
    ``None`` when the date is unreadable. Proceeds are the row's Amount."""
    d = parse_date(row.get("Date"))
    if d is None:
        return None
    parsed = parse_sell_text(row.get("Original Statement")) or parse_sell_text(row.get("Merchant")) or {}
    return {
        "monarch_id": str(row.get("Monarch Id") or "").strip() or None,
        "sale_date": d.isoformat(),
        "account": str(row.get("Account") or "").strip(),
        "amount": parse_money(row.get("Amount")),
        "symbol": parsed.get("symbol"),
        "shares": parsed.get("shares"),
        "price": parsed.get("price"),
    }


def count_parseable(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"parseable": 0, "bare": 0, "unreadable": 0}
    for r in rows:
        c = parse_sell_row(r)
        counts["unreadable" if c is None else "parseable" if c["symbol"] else "bare"] += 1
    return counts


def load_sell_candidates(repo: Any, ytd_rows: Iterable[Mapping[str, Any]], *, ledger_start: date) -> dict[str, int]:
    """Queue the Sell rows dated on or after ``ledger_start`` as unmatched candidates, once per Monarch Id.

    A row already queued (in any state) is counted as ``existing`` and left alone, so a re-import never
    re-queues a confirmed or dismissed sale. A row with no Monarch Id cannot be made idempotent and is skipped."""
    out = {"added": 0, "existing": 0, "before_start": 0, "no_monarch_id": 0, "unreadable": 0, "parseable": 0, "bare": 0}
    for r in sell_rows(ytd_rows):
        c = parse_sell_row(r)
        if c is None:
            out["unreadable"] += 1
        elif c["monarch_id"] is None:
            out["no_monarch_id"] += 1
        elif c["sale_date"] < ledger_start.isoformat():
            out["before_start"] += 1
        else:
            _, created = repo.add_candidate(source="monarch", sale_date=c["sale_date"], account=c["account"], symbol=c["symbol"],
                                            shares=c["shares"], price=c["price"], amount=c["amount"], monarch_id=c["monarch_id"])
            if not created:
                out["existing"] += 1
                continue
            out["added"] += 1
            out["parseable" if c["symbol"] else "bare"] += 1
    return out


def _fits(sale: Mapping[str, Any], event: Mapping[str, Any]) -> bool:
    if str(sale["account"]).strip().lower() != str(event["account"]).strip().lower():
        return False
    if str(sale["symbol"]).upper() != str(event["symbol"] or "").upper():
        return False
    if abs(float(sale["shares"]) - float(event["shares"] or 0.0)) > MATCH_SHARE_TOLERANCE:
        return False
    return abs(date.fromisoformat(sale["sale_date"]) - date.fromisoformat(event["sale_date"])) <= timedelta(days=MATCH_DAY_TOLERANCE)


def suggest_matches(repo: Any) -> list[dict[str, Any]]:
    """Pair each unmatched, parsed Monarch candidate with the holdings-import event (a lot that disappeared or
    shrank) it appears to be: same account and symbol, shares within rounding, dates within 3 days.

    Only an exact one-to-one fit is returned; an ambiguous sale or an event two sales could claim is left out.
    A suggestion changes nothing."""
    waiting = repo.list_candidates(state="unmatched")
    sales = [c for c in waiting if c["source"] == "monarch" and c["symbol"] and c["shares"]]
    events = [c for c in waiting if c["source"] == "holdings_diff" and c["symbol"] and c["shares"]]
    options = {s["candidate_id"]: [e for e in events if _fits(s, e)] for s in sales}
    claims: dict[int, int] = {}
    for found in options.values():
        for e in found:
            claims[e["candidate_id"]] = claims.get(e["candidate_id"], 0) + 1
    out = []
    for s in sales:
        found = options[s["candidate_id"]]
        if len(found) == 1 and claims[found[0]["candidate_id"]] == 1:
            out.append({"candidate_id": s["candidate_id"], "monarch_id": s["monarch_id"],
                        "holdings_candidate_id": found[0]["candidate_id"]})
    return out
