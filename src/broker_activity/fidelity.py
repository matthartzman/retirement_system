"""Fidelity "History for Account" CSV (all-transactions export): rows normalized for the activity import.

Layout (design section 3.1, structure only): blank lines, then the header ``Run Date, Action, Symbol, Description,
Type, Price ($), Quantity, Commission ($), Fees ($), Accrued Interest ($), Amount ($), Cash Balance ($), Settlement
Date``; data rows; a blank line; a legal disclaimer and a "Date downloaded" line. Dates are MM/DD/YYYY, numbers may be
quoted or empty, sold quantities are negative. The account number is only in the file name and is never kept whole.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date
from typing import Any

from .normalized import SWEEP_SYMBOLS, ParsedActivity

BROKER = "fidelity"

_HEADER = ("Run Date", "Action", "Symbol", "Amount ($)")
_FILE_ACCOUNT = re.compile(r"History_for_Account_([A-Za-z0-9]+)", re.I)
# Checked in order; the first prefix/fragment that appears in the upper-cased Action wins.
_KIND_RULES = (
    ("sell", ("YOU SOLD",)),
    ("buy", ("YOU BOUGHT",)),
    ("reinvest", ("REINVESTMENT",)),
    ("cap_gain_short", ("SHORT-TERM CAP GAIN", "SHORT TERM CAP GAIN")),
    ("cap_gain_long", ("LONG-TERM CAP GAIN", "LONG TERM CAP GAIN")),
    ("foreign_tax", ("FOREIGN TAX PAID",)),
    ("return_of_capital", ("RETURN OF CAPITAL",)),
    ("dividend", ("DIVIDEND RECEIVED",)),
    ("interest", ("INTEREST EARNED", "INTEREST")),
)


def account_hint(file_name: str | None) -> str | None:
    """``fidelity:<last 4>`` from a ``History_for_Account_<number>.csv`` name, else ``None``."""
    m = _FILE_ACCOUNT.search(file_name or "")
    return f"{BROKER}:{m.group(1)[-4:]}" if m else None


def detect(text: str, file_name: str | None = None) -> bool:
    return any(all(h in ln for h in _HEADER) for ln in (text or "").lstrip("﻿").splitlines()[:12])


def classify(action: str) -> str:
    text = action.upper()
    for kind, needles in _KIND_RULES:
        if any(n in text for n in needles):
            return kind
    return "other"


def _date(text: str) -> date:
    m, d, y = (int(x) for x in text.strip().split("/"))
    return date(y, m, d)


def _num(text: Any) -> float | None:
    t = str(text or "").strip().replace(",", "").replace("$", "")
    if t in ("", "--"):
        return None
    neg = t.startswith("(") and t.endswith(")")
    value = float(t.strip("()"))
    return -value if neg else value


def parse(text: str, *, file_name: str | None = None) -> ParsedActivity:
    out = ParsedActivity(broker=BROKER, meta={"account_hint": account_hint(file_name)})
    lines = (text or "").lstrip("﻿").splitlines()
    start = next((i for i, ln in enumerate(lines) if all(h in ln for h in _HEADER)), None)
    if start is None:
        out.errors.append({"line": 0, "error": "Not a Fidelity account history file: no 'Run Date, Action, Symbol, "
                                               "... Amount ($)' header found."})
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
            action = row.get("Action", "")
            symbol = row.get("Symbol", "").upper() or None
            kind = classify(action)
            price = _num(row.get("Price ($)"))
            quantity = _num(row.get("Quantity"))
            settle = row.get("Settlement Date", "")
            rec = {
                "run_date": _date(row["Run Date"]).isoformat(),
                "settle_date": _date(settle).isoformat() if settle else None,
                "kind": kind, "action": action, "symbol": symbol,
                "description": row.get("Description", ""),
                "quantity": quantity, "price": price,
                "commission": _num(row.get("Commission ($)")), "fees": _num(row.get("Fees ($)")),
                "accrued_interest": _num(row.get("Accrued Interest ($)")),
                "amount": _num(row.get("Amount ($)")) or 0.0, "line": line,
            }
            rec["sweep"] = bool(symbol in SWEEP_SYMBOLS
                                or (kind in ("buy", "sell", "reinvest") and price == 1.0 and row.get("Type") == "Cash"
                                    and symbol and symbol.endswith("XX")))
            if kind in ("buy", "sell", "reinvest") and not rec["sweep"]:
                if not symbol:
                    raise ValueError("a trade row has no symbol")
                if not quantity:
                    raise ValueError("a trade row has no quantity")
                if rec["price"] is None:
                    rec["price"] = round(abs(rec["amount"] / quantity), 6)
            out.rows.append(rec)
        except (ValueError, KeyError) as exc:
            out.errors.append({"line": line, "error": str(exc) or "unreadable row"})
    if not out.rows and not out.errors:
        out.warnings.append("The file has a header but no transaction rows.")
    out.rows.sort(key=lambda r: (r["run_date"], r["line"]))
    return out
