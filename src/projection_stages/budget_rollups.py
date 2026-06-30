from __future__ import annotations

from typing import Any, Callable


def housing_budget_rollup(c: dict[str, Any], year: int, infl_ratio: Callable[[int, int], float]) -> dict[str, float]:
    """Return non-engine Housing budget groups for a projection year."""
    roll = c.get("spending_rollup_by_year") or {}
    year_map = roll.get(year) or roll.get(str(year)) or {}
    housing = year_map.get("Housing") or year_map.get("housing") or {}
    out: dict[str, float] = {}
    try:
        items = housing.items()
    except AttributeError:
        items = []
    for group, raw_amount in items:
        g_raw = str(group or "Other").strip() or "Other"
        g_norm = g_raw.lower().replace("&", "and")
        if g_norm in {"bills and utilities", "utilities"}:
            g = "Utilities"
        elif g_norm in {"mortgage", "mortgage p&i", "mortgage pi"}:
            g = "Mortgage"
        elif g_norm in {"real estate taxes", "property tax", "property taxes", "re taxes"}:
            g = "Real Estate Taxes"
        elif g_norm in {"home improvement", "home improvements", "home improvement projects", "home projects"}:
            g = "Home Improvement"
        elif g_norm in {"maintenance", "home maintenance"}:
            g = "Maintenance"
        elif g_norm in {"rent"}:
            g = "Rent"
        elif g_norm in {"housing", "homeowners insurance", "homeowner insurance", "insurance", "other"}:
            g = "Other"
        else:
            g = "Other"
        try:
            amount = float(raw_amount or 0.0)
        except Exception:
            amount = 0.0
        if amount:
            out[g] = out.get(g, 0.0) + amount
    factor = infl_ratio(year, int(c.get("plan_start", year) or year))
    for group in list(out.keys()):
        if group in {"Utilities", "Maintenance", "Other"}:
            out[group] *= factor
    return out


def category_budget_rollup(
    c: dict[str, Any],
    year: int,
    category_ids: list[str],
    path_factor: Callable[[str, float, int], float],
    inflator_key: str = "inflation_index_by_year",
    annual_rate_key: str = "inf",
) -> float:
    """Return inflated category-budget dollars for selected canonical categories."""
    roll = c.get("spending_category_rollup_by_year") or {}
    year_map = roll.get(year) or roll.get(str(year)) or {}
    total = 0.0
    for cid in category_ids:
        try:
            total += float(year_map.get(cid, 0.0) or 0.0)
        except Exception:
            pass
    if not total:
        return 0.0
    return total * path_factor(inflator_key, c.get(annual_rate_key, c.get("inf", 0.0)), year)
