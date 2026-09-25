"""Spending Adjustments: category step-downs / step-ups by year (#335, spec §5).

Each adjustment is a one-time step applied multiplicatively from its start
year (inclusive) through its end year (inclusive; blank = plan end).
Inflation continues on the stepped base. Several rows on the same category
compound in start-year order (-20% then -10% => 0.72), and an
``ALL:<tracking type>`` row compounds with a specific category's own rows.

Stored in ``client_spending.csv`` as ``Cashflow / Spending Adjustments`` rows
``adj_N_category``, ``adj_N_start_year``, ``adj_N_end_year`` and
``adj_N_change_pct`` (a percent: ``-20`` means -20%).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

ADJ_SUBSECTION = "Spending Adjustments"
ALL_PREFIX = "ALL:"

#: Tracking types an adjustment may target (spec §5: not Large
#: Discretionary, Taxes or Business).
ADJUSTABLE_TRACKING_TYPES = ("Core Expenses", "Housing", "Wellness", "Travel")

_ADJ_RE = re.compile(r"adj_(\d+)_(category|start_year|end_year|change_pct)$")


@dataclass(frozen=True)
class Adjustment:
    category: str
    start: int
    end: int | None
    pct: float


def _applies(adj: Adjustment, category_id: str, tracking_type: str) -> bool:
    if adj.category.startswith(ALL_PREFIX):
        return adj.category[len(ALL_PREFIX):] == (tracking_type or "")
    return adj.category == (category_id or "")


def adjustment_factor(adjs: Iterable[Adjustment], category_id: str, tracking_type: str, year: int) -> float:
    """Compounded multiplier for one category in one year (1.0 = unchanged)."""
    factor = 1.0
    for adj in sorted((a for a in adjs or () if _applies(a, category_id, tracking_type)),
                      key=lambda a: a.start):
        if adj.start <= year and (adj.end is None or year <= adj.end):
            factor *= 1.0 + adj.pct
    return factor


def _num(value: Any) -> float | None:
    text = str(value if value is not None else "").replace("%", "").replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_adjustments(sectioned: Mapping[str, Any]) -> list[Adjustment]:
    """Read ``adj_N_*`` rows from a ``{subsection: {label: value}}`` mapping."""
    section: Mapping[str, Any] = {}
    for key, val in (sectioned or {}).items():
        if str(key).strip().lower() == ADJ_SUBSECTION.lower() and isinstance(val, Mapping):
            section = val
            break
    grouped: dict[int, dict[str, str]] = {}
    for label, value in section.items():
        m = _ADJ_RE.match(str(label).strip())
        if m:
            grouped.setdefault(int(m.group(1)), {})[m.group(2)] = str(value or "")
    out: list[Adjustment] = []
    for n in sorted(grouped):
        row = grouped[n]
        category = row.get("category", "").strip()
        start = _num(row.get("start_year"))
        pct = _num(row.get("change_pct"))
        if not category or not start or pct is None:
            continue
        end = _num(row.get("end_year"))
        out.append(Adjustment(category, int(start), int(end) if end else None, pct / 100.0))
    return out
