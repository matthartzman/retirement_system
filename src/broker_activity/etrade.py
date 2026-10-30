"""E*Trade "Transaction History" CSV (``DownloadTxnHistory``): rows normalized for the activity import.

Layout (design section 3.1, structure only): line 1 "All Transactions Activity Types", line 3 "Account Activity for <type>
-<last digits> from <date> to <date>", a ``Total:`` line, then the header ``Activity/Trade Date, Transaction Date,
Settlement Date, Activity Type, Description, Symbol, Cusip, Quantity #, Price $, Amount $, Commission, Category, Note``,
data rows, a blank line and a Bank Deposit Program disclaimer. Empty values are ``--`` or blank. Sold quantities are
negative; Amount is net of commission (a sale's amount is positive, a purchase's negative). Treasury and corporate
bonds are quoted per 100 face: the quantity is face value and the price is a percentage of it, so the price is
rescaled to a per-unit price here.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Any

from .normalized import SWEEP_SYMBOLS, ParsedActivity, number, us_date

BROKER = "etrade"

_HEADER = ("Activity/Trade Date", "Activity Type", "Quantity #", "Amount $")
_ACCOUNT_LINE = re.compile(r"Account Activity for .*?-\s*([A-Za-z0-9]+)\s+from\b", re.I)
_BANK_SWEEP_SYMBOLS = SWEEP_SYMBOLS | {"MSPBNA"}
# Activity Type (lower case) -> kind; anything else (Contribution, Transfer, Distribution, Service Fee, Redemption,
# Misc Income, Online Transfer, ...) is "other" and is only counted.
_KINDS = {"sold": "sell", "bought": "buy", "dividend": "dividend", "interest income": "interest"}


def account_hint(file_name: str | None) -> str | None:
    """The file name carries no account; the hint comes from the file's third line (see ``parse``)."""
    return None


def detect(text: str, file_name: str | None = None) -> bool:
    head = (text or "").lstrip("﻿")[:4000]
    return "Activity/Trade Date" in head and "Activity Type" in head and "Quantity #" in head


def _per_unit_price(price: float | None, quantity: float | None, amount: float, commission: float) -> float | None:
    """Bonds quote per 100 face: if quantity x price is ~100x the cash moved, divide the price by 100."""
    if not price or not quantity:
        return price
    gross = abs(quantity) * price
    cash = abs(amount) + (commission if amount > 0 else 0.0)
    if cash and abs(gross - cash) > 0.05 * cash and abs(gross / 100.0 - cash) <= 0.05 * cash:
        return price / 100.0
    return price


def parse(text: str, *, file_name: str | None = None) -> ParsedActivity:
    out = ParsedActivity(broker=BROKER)
    lines = (text or "").lstrip("﻿").splitlines()
    start = next((i for i, ln in enumerate(lines) if all(h in ln for h in _HEADER)), None)
    if start is None:
        out.errors.append({"line": 0, "error": "Not an E*Trade transaction history file: no 'Activity/Trade Date, ... "
                                               "Activity Type ... Amount $' header found."})
        return out
    for ln in lines[:start]:
        m = _ACCOUNT_LINE.search(ln)
        if m:
            out.meta["account_hint"] = f"{BROKER}:{m.group(1)[-4:]}"
            break
    else:
        out.warnings.append("The file has no 'Account Activity for ... -<digits>' line, so the account cannot be "
                            "recognized; choose it by hand.")
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
            action = row.get("Activity Type", "")
            kind = _KINDS.get(action.lower(), "other")
            symbol = next((s.upper() for s in (row.get("Symbol"), row.get("Cusip")) if s and s != "--"), None)
            quantity = number(row.get("Quantity #"))
            amount = number(row.get("Amount $")) or 0.0
            commission = number(row.get("Commission")) or 0.0
            settle = row.get("Settlement Date", "")
            desc = row.get("Description", "")
            if kind == "dividend" and quantity and "REINVEST" in desc.upper():
                kind = "reinvest"   # filed as a Dividend with shares and a negative amount: it is the purchase, not income
            rec = {
                "run_date": us_date(row["Activity/Trade Date"]).isoformat(),
                "settle_date": us_date(settle).isoformat() if settle and settle != "--" else None,
                "kind": kind, "action": action, "symbol": symbol, "description": desc,
                "quantity": quantity, "price": _per_unit_price(number(row.get("Price $")), quantity, amount, commission),
                "commission": commission or None, "fees": None, "accrued_interest": None,
                "amount": amount, "line": line,
            }
            rec["sweep"] = bool(symbol in _BANK_SWEEP_SYMBOLS or "BANK DEPOSIT" in desc.upper()
                                or "PROGRAM BANK" in desc.upper())
            if kind in ("buy", "sell", "reinvest") and not rec["sweep"]:
                if not symbol:
                    raise ValueError("a trade row has no symbol")
                if not quantity:
                    raise ValueError("a trade row has no quantity")
                if kind == "sell" and quantity > 0 or kind in ("buy", "reinvest") and quantity < 0:
                    raise ValueError(f"a {action.lower()} row has a {'positive' if quantity > 0 else 'negative'} quantity")
                if rec["price"] is None:
                    gross = abs(amount) - commission if kind != "sell" else abs(amount) + commission
                    rec["price"] = round(gross / abs(quantity), 6)
            out.rows.append(rec)
        except (ValueError, KeyError) as exc:
            out.errors.append({"line": line, "error": str(exc) or "unreadable row"})
    if not out.rows and not out.errors:
        out.warnings.append("The file has a header but no transaction rows.")
    out.rows.sort(key=lambda r: (r["run_date"], r["line"]))
    return out
