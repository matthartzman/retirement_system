"""Vanguard "OfxDownload" transaction CSV: rows normalized for the activity import.

Layout (design section 3.1, structure only): the header is on line 1, ``Account Number, Trade Date, Settlement Date,
Transaction Type, Transaction Description, Investment Name, Symbol, Shares, Share Price, Principal Amount, Commissions
and Fees, Net Amount, Accrued Interest, Account Type``, then data rows. One file holds every account of the owner, with
the account number on each row, so each row carries its own ``account_hint`` (``vanguard:<last 4>``) and the number is
never kept whole. Sold shares are negative; Net Amount is net of fees (a sale's is positive, a purchase's negative).
Money-market sweeps (VMFXX and similar) are ``sweep`` rows: "Sweep in/out" is the cash moving to or from the fund.
"""
from __future__ import annotations

import csv
import io
import re

from .normalized import ParsedActivity, number, us_date

BROKER = "vanguard"

_HEADER = ("Account Number", "Transaction Type", "Net Amount")
VANGUARD_SWEEP_SYMBOLS = frozenset({"VMFXX", "VMRXX", "VUSXX", "VMSXX", "VCTXX", "VYFXX", "VMMXX"})
_MONEY_MARKET = re.compile(r"MONEY\s*MARKET|\bMON(EY)?\b.*\bMKT\b|FEDERAL MON", re.I)
# Transaction Type (lower case) -> (kind, sweep). Unlisted types are "other": conversions, transfers, withdrawals,
# partnership distributions and corporate-action redemptions are only counted until reviewed.
_KINDS = {
    "sell": "sell", "buy": "buy", "reinvestment": "reinvest", "dividend": "dividend", "interest": "interest",
    "sweep in": "buy", "sweep out": "sell",
}


def account_hint(file_name: str | None) -> str | None:
    """The file name carries no account; every row has its own hint (see ``parse``)."""
    return None


def detect(text: str, file_name: str | None = None) -> bool:
    head = (text or "").lstrip("﻿").lstrip()[:600]
    return all(h in head for h in _HEADER) and "Principal Amount" in head


def _kind(tx_type: str, description: str) -> str:
    t = tx_type.strip().lower()
    if t in _KINDS:
        return _KINDS[t]
    text = f"{t} {description.lower()}"
    if "capital gain" in text:
        return "cap_gain_long" if re.search(r"\blt\b|long", text) else "cap_gain_short" if re.search(r"\bst\b|short", text) else "other"
    return "other"


def parse(text: str, *, file_name: str | None = None) -> ParsedActivity:
    out = ParsedActivity(broker=BROKER)
    lines = [ln for ln in (text or "").lstrip("﻿").splitlines()]
    start = next((i for i, ln in enumerate(lines) if ln.strip()), None)
    if start is None or not all(h in lines[start] for h in _HEADER):
        out.errors.append({"line": 0, "error": "Not a Vanguard transaction file: no 'Account Number, ... Transaction "
                                               "Type ... Net Amount' header found on the first line."})
        return out
    body = []
    for ln in lines[start + 1:]:
        if not ln.strip():
            break
        body.append(ln)
    reader = csv.DictReader(io.StringIO("\n".join([lines[start]] + body)))
    reader.fieldnames = [str(h or "").strip() for h in reader.fieldnames or []]
    for offset, raw in enumerate(reader):
        line = start + 2 + offset
        row = {k: (v or "").strip() for k, v in raw.items() if k}
        try:
            number_text = row.get("Account Number", "")
            if not number_text:
                raise ValueError("the row has no account number")
            tx_type = row.get("Transaction Type", "")
            desc = row.get("Transaction Description", "")
            symbol = row.get("Symbol", "").upper() or None
            kind = _kind(tx_type, desc)
            quantity = number(row.get("Shares"))
            price = number(row.get("Share Price"))
            net = number(row.get("Net Amount")) or 0.0
            fees = abs(number(row.get("Commissions and Fees")) or 0.0)
            sweep = bool(symbol in VANGUARD_SWEEP_SYMBOLS or tx_type.lower() in ("sweep in", "sweep out") or (symbol and _MONEY_MARKET.search(row.get("Investment Name", ""))
                                                              and kind in ("buy", "sell", "reinvest", "dividend")))
            rec = {
                "run_date": us_date(row["Trade Date"]).isoformat(),
                "settle_date": us_date(row["Settlement Date"]).isoformat() if row.get("Settlement Date") else None,
                "kind": kind, "action": tx_type, "symbol": symbol, "description": desc,
                "quantity": quantity, "price": price, "commission": None, "fees": fees or None,
                "accrued_interest": number(row.get("Accrued Interest")) or None, "amount": net, "line": line,
                "sweep": sweep, "account_hint": f"{BROKER}:{number_text[-4:]}",
            }
            if kind in ("buy", "sell", "reinvest") and not sweep:
                if not symbol:
                    raise ValueError("a trade row has no symbol")
                if not quantity:
                    raise ValueError("a trade row has no quantity")
                if kind == "sell" and quantity > 0 or kind in ("buy", "reinvest") and quantity < 0:
                    raise ValueError(f"a {tx_type.lower()} row has a {'positive' if quantity > 0 else 'negative'} quantity")
                if not price:
                    rec["price"] = round((abs(net) + (fees if kind == "sell" else -fees)) / abs(quantity), 6)
            out.rows.append(rec)
        except (ValueError, KeyError) as exc:
            out.errors.append({"line": line, "error": str(exc) or "unreadable row"})
    if not out.rows and not out.errors:
        out.warnings.append("The file has a header but no transaction rows.")
    out.rows.sort(key=lambda r: (r["run_date"], r["line"]))
    return out
