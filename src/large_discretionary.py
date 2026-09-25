"""Large Discretionary spending: one-time items only (#336, spec §4).

Each Large Discretionary row is one amount in one year. It is never
annualized:

* the **budget** for a year counts a row only when the row's year equals
  that year (:func:`ld_budget_for_year`);
* the **projection** lands every row in its own year
  (:func:`ld_cashflow_by_year`).

Legacy repeatable rows (``extra_N_start_year`` / ``extra_N_end_year`` with an
annual amount, or a budget line with a start/end range) are migrated on load
by expanding them into one dated row per year; :func:`migrate_repeatable`
returns an import notice for each expansion, recommending a Core category
when a row expands to more than :data:`CORE_RECOMMENDATION_THRESHOLD` rows.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

LD_TRACKING_TYPE = "Large Discretionary"
LD_SUBSECTION = "Large Discretionary Expenses"

LD_CATEGORIES = ("Weddings", "Large Gifts", "Education", "Auto", "Other")

#: Taxonomy category id backing each Large Discretionary category.
LD_CATEGORY_IDS = {
    "Weddings": "weddings",
    "Large Gifts": "significant_gifts",
    "Education": "ld_education",
    "Auto": "ld_auto",
    "Other": "other_large_discretionary",
}

#: A repeatable row that expands to more than this many one-time rows is
#: really recurring spending; the import notice recommends a Core category.
CORE_RECOMMENDATION_THRESHOLD = 10

_EXTRA_RE = re.compile(r"extra_(\d+)_(type|amount|year|start_year|end_year|comment)$")


@dataclass(frozen=True)
class LdItem:
    category: str
    amount: float
    year: int
    note: str = ""


def ld_category_for_legacy_type(value: Any) -> str:
    """Map a legacy ``extra_N_type`` (or line label) onto :data:`LD_CATEGORIES`."""
    text = str(value or "").strip().lower()
    if not text:
        return "Other"
    if "wedding" in text:
        return "Weddings"
    if "gift" in text:
        return "Large Gifts"
    if "education" in text or "tuition" in text:
        return "Education"
    if "vehicle" in text or "auto" in text or text == "car":
        return "Auto"
    return "Other"


def ld_category_for_id(category_id: Any, label: Any = "") -> str:
    """LD category for a taxonomy category id (falls back to the label)."""
    cid = str(category_id or "").strip().lower()
    for cat, known in LD_CATEGORY_IDS.items():
        if cid == known:
            return cat
    return ld_category_for_legacy_type(f"{cid} {label or ''}")


def _money(value: Any) -> float:
    try:
        return float(str(value or "").replace("$", "").replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def _year(value: Any) -> int:
    try:
        return int(float(str(value or "").strip()))
    except ValueError:
        return 0


def _ld_rows(sectioned: Mapping[str, Any]) -> list[dict[str, str]]:
    """Group ``extra_N_*`` labels of the Large Discretionary subsection by N."""
    section: Mapping[str, Any] = {}
    for key, val in (sectioned or {}).items():
        if str(key).strip().lower() == LD_SUBSECTION.lower() and isinstance(val, Mapping):
            section = val
            break
    grouped: dict[int, dict[str, str]] = {}
    for label, value in section.items():
        m = _EXTRA_RE.match(str(label).strip())
        if m:
            grouped.setdefault(int(m.group(1)), {})[m.group(2)] = str(value or "")
    return [grouped[n] for n in sorted(grouped)]


def expand_repeatable(category: str, amount: float, start: int, end: int, note: str = "",
                      source: str = "") -> tuple[list[LdItem], str]:
    """Expand one repeatable row into one dated item per year, with its notice."""
    end = max(start, end)
    items = [LdItem(category, amount, y, note) for y in range(start, end + 1)]
    name = source or category
    notice = (f"Large Discretionary row '{name}' (${amount:,.0f}/yr, {start}-{end}) "
              f"was converted to {len(items)} one-time rows.")
    if len(items) > CORE_RECOMMENDATION_THRESHOLD:
        notice += (" It repeats for more than "
                   f"{CORE_RECOMMENDATION_THRESHOLD} years; consider moving it to a Core category.")
    return items, notice


def migrate_repeatable(sectioned: Mapping[str, Any], plan_end: int | None = None
                       ) -> tuple[list[LdItem], list[str]]:
    """Expand legacy repeatable ``extra_N`` rows into one-time items.

    One-time rows (``extra_N_year`` set) are not returned here; see
    :func:`load_ld_items`. A repeatable row with no end year runs through
    ``plan_end`` when given, otherwise it covers its start year only.
    """
    items: list[LdItem] = []
    notices: list[str] = []
    for row in _ld_rows(sectioned):
        amount = _money(row.get("amount"))
        if amount <= 0 or _year(row.get("year")):
            continue
        start = _year(row.get("start_year"))
        end = _year(row.get("end_year"))
        if not start and not end:
            continue
        start = start or end
        end = end or (plan_end if plan_end and plan_end >= start else start)
        category = ld_category_for_legacy_type(row.get("type"))
        expanded, notice = expand_repeatable(
            category, amount, start, end, row.get("comment", "").strip(),
            source=row.get("type", "").strip() or category)
        items.extend(expanded)
        notices.append(notice)
    return items, notices


def load_ld_items(sectioned: Mapping[str, Any], plan_end: int | None = None) -> list[LdItem]:
    """All Large Discretionary items: one-time rows plus migrated repeatable rows."""
    items: list[LdItem] = []
    for row in _ld_rows(sectioned):
        amount = _money(row.get("amount"))
        year = _year(row.get("year"))
        if amount > 0 and year:
            items.append(LdItem(ld_category_for_legacy_type(row.get("type")), amount, year,
                                row.get("comment", "").strip()))
    migrated, _notices = migrate_repeatable(sectioned, plan_end=plan_end)
    return items + migrated


def ld_budget_for_year(items: Iterable[LdItem], year: int) -> float:
    """Budget for ``year``: only rows dated in that year count."""
    return float(sum(i.amount for i in items if i.year == year))


def ld_cashflow_by_year(items: Iterable[LdItem]) -> dict[int, float]:
    """Projection cash flow: every row lands in its own year."""
    out: dict[int, float] = {}
    for i in items:
        out[i.year] = out.get(i.year, 0.0) + i.amount
    return out
