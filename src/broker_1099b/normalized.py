"""Shared normalized output of the broker 1099-B parsers (realized-sales ledger plan, step 5.1).

Pure data and number/date helpers; every broker parser returns a ``ParsedStatement`` of rows with ``ROW_FIELDS``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# The columns every parser must fill. ``covered`` is False for noncovered lots (basis not reported to the IRS).
ROW_FIELDS = ("account", "symbol", "date_acquired", "date_sold", "proceeds", "basis", "wash_disallowed", "gain",
              "term", "covered", "quantity", "description", "cusip")
# Control-total columns, in the order the statement summary lists them.
TOTAL_COLUMNS = ("proceeds", "basis", "market_discount", "wash_disallowed", "gain")
TOLERANCE = 0.01  # dollars, per column per bucket: the summary and the lines are both rounded to the cent

_MONEY = re.compile(r"^\(?-?\$?\d[\d,]*(?:\.\d+)?\)?$")


def is_money(token: str) -> bool:
    return bool(_MONEY.match(token))


def parse_money(token: str) -> float:
    """``1,234.50`` -> 1234.5; ``(12.30)`` and ``-12.30`` -> -12.3 (parentheses mean loss)."""
    t = token.strip()
    if not is_money(t):
        raise ValueError(f"not an amount: {token!r}")
    neg = t.startswith("(") or "-" in t
    value = float(t.strip("()").replace("-", "").replace("$", "").replace(",", ""))
    return round(-value if neg else value, 2)


def cents(value: float) -> int:
    return int(round(value * 100))


def two_digit_year(yy: int, *, not_after: int | None = None) -> int:
    """Century for a 2-digit year: 20yy, or 19yy when that would fall after ``not_after`` (an acquisition year)."""
    year = 2000 + yy
    if not_after is not None and year > not_after:
        year -= 100
    return year


@dataclass
class ParsedStatement:
    """What a broker parser returns. ``control`` is the result of ``check_control_totals``."""
    broker: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[tuple[str, bool], dict[str, float]] = field(default_factory=dict)
    control: dict[str, Any] = field(default_factory=lambda: {"status": "missing", "buckets": [], "gaps": []})
    warnings: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def detail_totals(rows: list[dict[str, Any]]) -> dict[tuple[str, bool], dict[str, float]]:
    """Sum the detail lines per (term, covered) bucket, in whole cents so the sums are exact."""
    acc: dict[tuple[str, bool], dict[str, int]] = {}
    for r in rows:
        b = acc.setdefault((r["term"], bool(r["covered"])), {c: 0 for c in TOTAL_COLUMNS})
        for c in TOTAL_COLUMNS:
            b[c] += cents(r.get(c) or 0.0)
    return {k: {c: v / 100 for c, v in b.items()} for k, b in acc.items()}


def check_control_totals(rows: list[dict[str, Any]], summary: dict[tuple[str, bool], dict[str, float]]) -> dict[str, Any]:
    """Compare the statement's 1099-B summary with the sums of the detail lines.

    ``status``: ``ok`` (every bucket and column ties within ``TOLERANCE``), ``mismatch`` (``gaps`` lists each
    difference), or ``missing`` (no summary was found, so nothing was verified).
    """
    if not summary:
        return {"status": "missing", "buckets": [], "gaps": []}
    detail = detail_totals(rows)
    zero = {c: 0.0 for c in TOTAL_COLUMNS}
    gaps, buckets = [], []
    for key in sorted(set(summary) | set(detail), key=lambda k: (k[0], not k[1])):
        s, d = summary.get(key, zero), detail.get(key, zero)
        buckets.append({"term": key[0], "covered": key[1], "statement": s, "detail": d})
        for c in TOTAL_COLUMNS:
            diff = round(s[c] - d[c], 2)  # statement minus lines: positive means the lines fall short
            if abs(diff) > TOLERANCE + 1e-9:
                gaps.append({"term": key[0], "covered": key[1], "column": c, "statement": s[c], "detail": d[c],
                             "difference": diff})
    return {"status": "mismatch" if gaps else "ok", "buckets": buckets, "gaps": gaps}
