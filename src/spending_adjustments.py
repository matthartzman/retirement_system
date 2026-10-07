"""Spending Adjustments: category step-downs / step-ups by year (#335, spec §5).

Each adjustment is a one-time step applied multiplicatively from its start
year (inclusive) through its end year (inclusive; blank = plan end).
Inflation continues on the stepped base. Several rows on the same category
compound in start-year order (-20% then -10% => 0.72), and an
``ALL:<tracking type>`` row compounds with a specific category's own rows.

Stored in the plan as ``Cashflow / Spending Adjustments`` rows
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


# ── Persistence helpers for /api/spending-adjustments (the Adjustments table) ──

_ADJ_FIELDS = ("category", "start_year", "end_year", "change_pct")


def adjustment_dicts_from_plan_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Raw ``{category, start_year, end_year, change_pct}`` dicts from the ``plan_rows`` of the
    ``Cashflow`` section (rows with ``subsection``, ``label`` and ``value``), in number order."""
    section: dict[str, str] = {}
    for r in rows or ():
        if str(r["subsection"]).strip().lower() == ADJ_SUBSECTION.lower():
            section[str(r["label"]).strip()] = str(r["value"] or "").strip()
    grouped: dict[int, dict[str, str]] = {}
    for label, value in section.items():
        m = _ADJ_RE.match(label)
        if m:
            grouped.setdefault(int(m.group(1)), {f: "" for f in _ADJ_FIELDS})[m.group(2)] = value
    return [grouped[n] for n in sorted(grouped)]


def validate_adjustment_dicts(items: Any) -> tuple[list[dict[str, str]], str | None]:
    """Clean a posted adjustments list; returns (clean, error)."""
    if not isinstance(items, list):
        return [], "adjustments must be a list"
    clean: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        row = {f: str(item.get(f) or "").strip() for f in _ADJ_FIELDS}
        if not any(row.values()):
            continue
        if not row["category"]:
            return [], "Each adjustment needs a category"
        if row["category"].startswith(ALL_PREFIX) and \
                row["category"][len(ALL_PREFIX):] not in ADJUSTABLE_TRACKING_TYPES:
            return [], f"{row['category']} is not an adjustable tracking type"
        if not re.fullmatch(r"(19|20)\d{2}", row["start_year"]):
            return [], f"Start year must be YYYY: {row['start_year'] or '(blank)'}"
        if row["end_year"] and (not re.fullmatch(r"(19|20)\d{2}", row["end_year"])
                                or int(row["end_year"]) < int(row["start_year"])):
            return [], f"End year must be blank or a YYYY no earlier than the start year: {row['end_year']}"
        pct = _num(row["change_pct"])
        if pct is None or pct <= -100:
            return [], f"Change % must be a number above -100: {row['change_pct'] or '(blank)'}"
        row["change_pct"] = f"{pct:g}"
        clean.append(row)
    return clean, None


def adjustment_plan_rows(items: list[dict[str, str]]) -> list[tuple[str, str, str, str, str]]:
    """The ``Cashflow / Spending Adjustments`` rows of ``items`` as
    ``(subsection, label, value, units, notes)``."""
    out: list[tuple[str, str, str, str, str]] = []
    for i, item in enumerate(items, 1):
        out.extend([
            (ADJ_SUBSECTION, f"adj_{i}_category", item.get("category", ""), "",
             "Category id, or ALL:<tracking type>"),
            (ADJ_SUBSECTION, f"adj_{i}_start_year", item.get("start_year", ""), "year",
             "First year the change applies"),
            (ADJ_SUBSECTION, f"adj_{i}_end_year", item.get("end_year", ""), "year",
             "Last year it applies; blank = through plan end"),
            (ADJ_SUBSECTION, f"adj_{i}_change_pct", item.get("change_pct", ""), "%",
             "Negative = decrease, positive = increase; compounds with earlier rows"),
        ])
    return out
