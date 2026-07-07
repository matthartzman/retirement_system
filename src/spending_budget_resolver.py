"""Resolve the unified spending budget into projection-engine inputs.

The unified spending model is the source of truth for the spending side of
cash flow.  This adapter converts category/group/line budget rows into the
legacy engine keys so the deterministic projection can remain stable while the
UI and data model are consolidated.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

try:  # package import
    from . import spending_tracker as st
except Exception:  # direct script/test import
    import spending_tracker as st  # type: ignore

EXCLUDED_FROM_SPEND_BASE = {"Income", "Transfer", "Transfers", "Business", "Housing", "Wellness"}
TIME_BOUNDED_LINE_TRACKING_TYPES = {"Travel", "Large Discretionary"}


def _num(value: Any) -> float:
    try:
        return float(str(value or "").replace("$", "").replace(",", "").strip() or 0)
    except Exception:
        return 0.0


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value or "").strip()))
    except Exception:
        return default


def _year_range(year_range: Iterable[int] | None, config: dict | None = None) -> list[int]:
    if year_range is not None:
        return [int(y) for y in year_range]
    if config:
        start = _int(config.get("plan_start"), 0)
        end = _int(config.get("plan_end"), 0)
        if start and end and end >= start:
            return list(range(start, end + 1))
    return []


def _line_years(row: dict, years: list[int]) -> list[int]:
    one = _int(row.get("one_time_year"), 0)
    if one:
        return [one] if not years or one in years else []
    if not years:
        start = _int(row.get("start_year"), 0)
        end = _int(row.get("end_year"), start)
        return list(range(start, end + 1)) if start and end >= start else []
    start = _int(row.get("start_year"), min(years)) or min(years)
    end = _int(row.get("end_year"), max(years)) or max(years)
    if end < start:
        end = start
    return [y for y in years if start <= y <= end]


def _is_home_improvement(info: dict, row: dict) -> bool:
    text = " ".join(str(x or "") for x in [
        info.get("tracking_type"), info.get("group"), info.get("label"), row.get("label"), row.get("notes")
    ]).lower()
    return "home improvement" in text or "home projects" in text or "home project" in text


def resolve_spending_inputs(root: str | Path | None = None, year_range: Iterable[int] | None = None,
                            config: dict | None = None) -> dict:
    """Return budget-derived spending drivers for the projection engine.

    Decisions implemented from the design-review answers:
    1. spend_base includes Core Expenses and recurring non-excluded tracking types;
       excludes Income, Transfer, Business, Housing, Wellness, Travel, and Large
       Discretionary at EVERY level (group, category, and line rows). Travel and
       Large Discretionary dollars only ever reach the projection as extras/lumps
       (the Travel/Other columns), never as core spending.
    2. Business remains in the model, but not in spend_base.
    3. Income is left out of this spending-side resolver, but nothing in the
       file format prevents future income-side use.
    4. Group budget mode disables category and line detail for that group.
    """
    r = Path(root) if root is not None else st._root(None)  # type: ignore[attr-defined]
    years = _year_range(year_range, config)
    flat = st.taxonomy_flat(r, include_deleted=False)
    cat_budgets, group_budgets, line_budgets = st._budget_indexes(r)  # type: ignore[attr-defined]

    spend_base = 0.0
    recurring_extras: list[dict] = []
    lump: dict[int, float] = defaultdict(float)
    home_improvement_lump: dict[int, float] = defaultdict(float)
    by_year: dict[int, dict[str, dict[str, float]]] = {y: {} for y in years}
    by_category_year: dict[int, dict[str, float]] = {y: {} for y in years}
    business_reference = 0.0

    # Group budgets win and suppress their category/line detail.
    group_mode_categories: set[str] = set()
    groups_by_key: dict[str, list[str]] = defaultdict(list)
    for cid, info in flat.items():
        groups_by_key[f"{info.get('tracking_type')}::{info.get('group')}"].append(cid)

    for gkey, grow in group_budgets.items():
        amount = _num(grow.get("annual_budget"))
        tt = gkey.split("::", 1)[0] if "::" in gkey else "Core Expenses"
        if tt == "Business":
            business_reference += amount
        # Time-bounded group budgets (Travel, Large Discretionary) are reference
        # amounts for UI display; their projection flows through recurring_extras
        # via explicit line items, so do not add them to spend_base.
        if tt not in EXCLUDED_FROM_SPEND_BASE and tt not in TIME_BOUNDED_LINE_TRACKING_TYPES:
            spend_base += amount
        for cid in groups_by_key.get(gkey, []):
            group_mode_categories.add(cid)
        for y in years:
            tt_map = by_year.setdefault(y, {}).setdefault(tt, {})
            grp = gkey.split("::", 1)[1] if "::" in gkey else gkey
            tt_map[grp] = tt_map.get(grp, 0.0) + amount

    # Category budgets are recurring unless their group is in group mode.
    # When a category also has explicit line (detail) rows, those line rows are
    # the sole budget authority for that category — the same rule the UI applies
    # in spending_tracker._category_budget_for_year (lines win, category row is
    # ignored). This holds for EVERY tracking type, not just the domain-owned
    # time-bounded ones (Housing > Home Improvement, Travel, Large Discretionary):
    # a Core Expenses category such as charitable_donations that carries both a
    # $5,000 category row and a $5,000 detail line must count once, not twice.
    # Skipping only Housing/Travel/Large-Disc here previously double-counted such
    # Core-Expenses/Wellness categories into spend_base (item 141 reconciliation).
    categories_with_projection_lines = {cid for cid, rows in line_budgets.items() if rows}
    for cid, row in cat_budgets.items():
        if cid in group_mode_categories:
            continue
        info = flat.get(cid)
        if not info:
            continue
        tt = info.get("tracking_type") or "Core Expenses"
        if cid in categories_with_projection_lines:
            continue
        amount = _num(row.get("annual_budget"))
        if tt == "Business":
            business_reference += amount
        if tt in TIME_BOUNDED_LINE_TRACKING_TYPES:
            # Core spending must never absorb Travel/Large-Discretionary dollars.
            # A category-level budget with no detail lines still projects — as a
            # recurring extra spanning the plan window (the Travel/Other columns) —
            # instead of leaking into spend_base.
            if amount > 0:
                start = min(years) if years else _int((config or {}).get("plan_start"), 0)
                end = max(years) if years else _int((config or {}).get("plan_end"), start) or start
                recurring_extras.append({
                    "type": info.get("label") or cid,
                    "amount": amount,
                    "start_year": start,
                    "end_year": max(start, end),
                    "comment": row.get("notes", ""),
                    "is_home_improvement": _is_home_improvement(info, row),
                    "source": "unified_budget",
                    "category_id": cid,
                })
        elif tt not in EXCLUDED_FROM_SPEND_BASE:
            spend_base += amount
        for y in years:
            tt_map = by_year.setdefault(y, {}).setdefault(tt, {})
            grp = info.get("group") or "Other"
            tt_map[grp] = tt_map.get(grp, 0.0) + amount
            by_category_year.setdefault(y, {})[cid] = by_category_year.setdefault(y, {}).get(cid, 0.0) + amount

    # Line rows feed extras.  Category-budget entries are ignored when their
    # group is in group mode (the group budget takes precedence).  Pure line
    # items — those with no matching category budget row — are never suppressed:
    # they are explicit, time-bounded projections that must always flow through.
    for cid, rows in line_budgets.items():
        if cid in group_mode_categories and cid in cat_budgets:
            continue
        info = flat.get(cid, {})
        tt = info.get("tracking_type") or "Large Discretionary"
        grp = info.get("group") or "Other"
        for row in rows:
            amount = _num(row.get("annual_budget"))
            if amount <= 0:
                continue
            one_year = _int(row.get("one_time_year"), 0)
            active_years = _line_years(row, years)
            is_home = _is_home_improvement(info, row)
            # Non-excluded non-Travel/Large-Discretionary line rows are recurring
            # budget detail and therefore remain in spend_base per Matt's decision.
            # Time-bounded Travel/Large-Disc lines become projection extras instead.
            if tt not in TIME_BOUNDED_LINE_TRACKING_TYPES and tt not in EXCLUDED_FROM_SPEND_BASE:
                spend_base += amount
                for y in active_years or years:
                    tt_map = by_year.setdefault(y, {}).setdefault(tt, {})
                    tt_map[grp] = tt_map.get(grp, 0.0) + amount
                    by_category_year.setdefault(y, {})[cid] = by_category_year.setdefault(y, {}).get(cid, 0.0) + amount
                continue
            if one_year:
                if is_home:
                    home_improvement_lump[one_year] += amount
                else:
                    lump[one_year] += amount
            else:
                if active_years:
                    start, end = min(active_years), max(active_years)
                else:
                    start = _int(row.get("start_year"), _int((config or {}).get("plan_start"), 0))
                    end = _int(row.get("end_year"), _int((config or {}).get("plan_end"), start)) or start
                recurring_extras.append({
                    "type": row.get("label") or info.get("label") or cid,
                    "amount": amount,
                    "start_year": start,
                    "end_year": max(start, end),
                    "comment": row.get("notes", ""),
                    "is_home_improvement": is_home,
                    "source": "unified_budget",
                    "category_id": cid,
                })
            for y in active_years:
                tt_map = by_year.setdefault(y, {}).setdefault(tt, {})
                tt_map[grp] = tt_map.get(grp, 0.0) + amount
                by_category_year.setdefault(y, {})[cid] = by_category_year.setdefault(y, {}).get(cid, 0.0) + amount

    return {
        "spend_base": round(spend_base, 2),
        "recurring_extras": recurring_extras,
        "lump": dict(lump),
        "home_improvement_lump": dict(home_improvement_lump),
        "business_reference_budget": round(business_reference, 2),
        "spending_rollup_by_year": by_year,
        "spending_category_rollup_by_year": by_category_year,
        "budget_drives_projection": True,
    }


def apply_budget_to_engine_config(config: dict, root: str | Path | None = None) -> dict:
    """Mutate and return an engine config using budget-derived spend drivers.

    If no unified budget dollars exist, the config is left unchanged so tests and
    blank plans keep their previous fallback behavior.
    """
    resolved = resolve_spending_inputs(root=root, config=config)
    if (_num(resolved.get("spend_base")) <= 0
            and not resolved.get("recurring_extras")
            and not resolved.get("lump")
            and not resolved.get("home_improvement_lump")
            and not any((resolved.get("spending_rollup_by_year") or {}).values())
            and not any((resolved.get("spending_category_rollup_by_year") or {}).values())):
        return config
    config["spend_base"] = _num(resolved.get("spend_base"))
    config["recurring_extras"] = list(resolved.get("recurring_extras") or [])
    config["lump"] = dict(resolved.get("lump") or {})
    config["home_improvement_lump"] = dict(resolved.get("home_improvement_lump") or {})
    config["home_proj"] = 0.0
    config["home_proj_end"] = _int(config.get("plan_start"), 0) - 1
    config["vac"] = 0.0
    config["vac_end"] = _int(config.get("plan_start"), 0) - 1
    config["business_reference_budget"] = resolved.get("business_reference_budget", 0.0)
    config["spending_rollup_by_year"] = resolved.get("spending_rollup_by_year", {})
    config["spending_category_rollup_by_year"] = resolved.get("spending_category_rollup_by_year", {})
    config["budget_drives_projection"] = True
    return config
