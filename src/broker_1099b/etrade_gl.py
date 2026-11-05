"""E*Trade "Gains & Losses" CSV download (taxable G&L details) as a 1099-B-style statement.

Layout: an account header and search criteria (the first 13 lines are summary, skipped), a ``TAXABLE G&L SUMMARY`` with the
realized totals, then ``TAXABLE G&L DETAILS``: a security line (symbol, quantity, totals) followed by one indented ``Sell``
line per lot: quantity, date acquired, cost/share, total cost, date sold, price/share, proceeds, gain, deferred loss,
term, lot selection. A ``Total`` line ends the file. The summary gains are the control totals.

Mapping to the normalized row: ``wash_disallowed`` is the deferred (disallowed) loss as a positive amount, so
gain = proceeds - basis + wash_disallowed holds exactly as in the 1099-B. A Treasury bill (its "symbol" is the whole
description, ``UNITED STATES TREASURY BILL 0% 10/27/2026``) is recorded as ``CASH (T-BILL)``, the name its holding lot uses.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from typing import Any, Iterable

from .normalized import ParsedStatement, check_control_totals, is_money, parse_money

BROKER = "etrade_gl"
TBILL_SYMBOL = "CASH (T-BILL)"
_ACCOUNT_LAST4 = re.compile(r"-\s*(\d{4})\s*$")


def _date(token: str) -> str | None:
    try:
        return datetime.strptime(token.strip(), "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None


def _money(token: str) -> float | None:
    t = (token or "").strip()
    if t.startswith("."):
        t = "0" + t
    if t.startswith("-."):
        t = "-0" + t[1:]
    return parse_money(t) if is_money(t) else None


def _qty(token: str) -> float | None:
    """Share counts keep their fractional digits (the money helper rounds to cents)."""
    try:
        return float((token or "").replace(",", "").strip())
    except ValueError:
        return None


def _symbol(raw: str) -> tuple[str, str]:
    """(symbol, description). A Treasury bill is known by its description only."""
    raw = raw.strip()
    if re.search(r"\b(treasury|t-bill)\b", raw, re.I) and " " in raw:
        return TBILL_SYMBOL, raw
    return raw.upper(), ""


def parse(text: str, *, known_symbols: Iterable[str] | None = None, account: str | None = None) -> ParsedStatement:
    st = ParsedStatement(broker=BROKER)
    records = list(csv.reader(io.StringIO(text or "")))
    label = None
    summary_gain: dict[str, float] = {}
    section = None
    symbol = description = ""
    for no, rec in enumerate(records, start=1):
        cells = [c.strip() for c in rec]
        if not any(cells):
            continue
        head = cells[0]
        if label is None and _ACCOUNT_LAST4.search(head):
            label = head
            continue
        if head.upper().startswith("TAXABLE G&L SUMMARY"):
            section = "summary"
            continue
        if head.upper().startswith("TAXABLE G&L DETAILS"):
            section = "details"
            continue
        if section == "summary" and len(cells) >= 3 and _money(cells[0]) is not None:
            summary_gain = {"short": _money(cells[1]) or 0.0, "long": _money(cells[2]) or 0.0}
            continue
        if section != "details" or head == "Symbol":
            continue
        if head == "Total":
            continue
        if head == "Sell":
            _lot(st, no, cells, symbol, description)
            continue
        if cells[0] and cells[2:3] == ["--"]:
            symbol, description = _symbol(cells[0])

    acct = account or label
    for r in st.rows:
        r["account"] = acct
    st.meta["account"] = acct
    st.meta["account_label"] = label
    m = _ACCOUNT_LAST4.search(label or "")
    st.meta["account_last4"] = m.group(1) if m else None
    if st.rows:
        st.meta["tax_year"] = int(max(r["date_sold"] for r in st.rows)[:4])
    if not st.rows and not st.errors:
        st.errors.append({"line": 0, "error": "No Sell lines were found in the Gains & Losses download."})
    st.control = _control(st, summary_gain)
    return st


def _lot(st: ParsedStatement, no: int, cells: list[str], symbol: str, description: str) -> None:
    def bad(why: str) -> None:
        st.errors.append({"line": no, "error": f"line {no}: {why}"})

    if len(cells) < 11 or not symbol:
        return bad("cannot read this Sell line (expected 11 columns under a security)")
    qty = _qty(cells[1])
    basis, proceeds, gain, deferred = (_money(cells[i]) for i in (4, 7, 8, 9))
    acquired, sold = _date(cells[2]), _date(cells[5])
    if cells[2] in ("", "--"):    # no acquisition date: the line may stand for several ledger rows (aggregate match)
        acquired = None
    elif not acquired:
        return bad("cannot read this Sell line (acquired date)")
    if None in (qty, basis, proceeds, gain) or not sold:
        return bad("cannot read this Sell line (date or amount)")
    term = cells[10].strip().lower()
    st.rows.append({
        "broker": BROKER, "source": "1099b", "line": no, "account": None, "symbol": symbol, "cusip": None,
        "description": description, "date_acquired": acquired, "date_sold": sold, "proceeds": proceeds, "basis": basis,
        "market_discount": 0.0, "wash_disallowed": abs(deferred or 0.0), "gain": gain, "fed_withheld": 0.0,
        "term": term if term in ("short", "long") else "unknown", "covered": True, "quantity": qty,
    })


def _control(st: ParsedStatement, summary_gain: dict[str, float]) -> dict[str, Any]:
    """The summary's short- and long-term gains are the control; proceeds and basis are not broken out by term in the
    file, so they are taken from the lines and only the gains are checked."""
    if not summary_gain:
        return {"status": "missing", "buckets": [], "gaps": []}
    terms = {r["term"] for r in st.rows}
    summary: dict[tuple[str, bool], dict[str, float]] = {}
    for term in set(summary_gain) | terms:
        mine = [r for r in st.rows if r["term"] == term]
        detail = {c: round(sum(r[c] for r in mine), 2) for c in ("proceeds", "basis", "market_discount", "wash_disallowed")}
        stated = summary_gain.get(term, 0.0)
        summed = round(sum(r["gain"] for r in mine), 2)
        # The summary is worked from unrounded amounts, each line's gain is rounded to the cent: up to half a cent a line.
        if stated != summed and abs(stated - summed) <= 0.005 * len(mine) + 0.01:
            st.warnings.append(f"{term}-term gain {summed:,.2f} from the lines differs from the summary {stated:,.2f} by "
                               f"{abs(stated - summed):.2f}: rounding in the download (each lot's gain is rounded to the cent).")
            stated = summed
        summary[(term, True)] = {**detail, "gain": stated}
    return check_control_totals(st.rows, summary)
