"""Spending for any date window (Trends Phase 5): the hierarchy, the same window one year
earlier, the annual budget prorated to the window, and the end year's full-year budget.

The date arithmetic here is pure (``window_year_segments``, ``prorate``, ``prior_window``)
so it is unit-tested without a workspace; ``spending_window_payload`` wires it to the
retirement-system workspace through ``src.spending_tracker``.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any, Callable

from src import spending_tracker

# The widest window /api/spending accepts.
MAX_SPAN_YEARS = 20


def same_day_prior_year(d: date) -> date:
    """The same month/day one year earlier; Feb 29 maps to Feb 28."""
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return date(d.year - 1, 2, 28)


def days_in_year(year: int) -> int:
    return (date(year + 1, 1, 1) - date(year, 1, 1)).days


def window_year_segments(start: date, end: date) -> list[tuple[int, int, int]]:
    """``[(year, days of the window in that year, days in that year), ...]`` for every
    calendar year the inclusive window [start, end] touches."""
    if start > end:
        return []
    out = []
    for year in range(start.year, end.year + 1):
        lo, hi = max(start, date(year, 1, 1)), min(end, date(year, 12, 31))
        out.append((year, (hi - lo).days + 1, days_in_year(year)))
    return out


def _scaled_sum(parts: list[tuple[dict, float]]) -> dict:
    """Sum nested ``{key: number | {key: number}}`` maps, each scaled by its factor."""
    out: dict = {}
    for mapping, factor in parts:
        for key, value in (mapping or {}).items():
            if isinstance(value, dict):
                out[key] = _merge_nested(out.get(key, {}), _scaled_sum([(value, factor)]))
            else:
                out[key] = out.get(key, 0.0) + float(value or 0.0) * factor
    return out


def _merge_nested(a: dict, b: dict) -> dict:
    merged = dict(a)
    for key, value in b.items():
        if isinstance(value, dict):
            merged[key] = _merge_nested(merged.get(key, {}), value)
        else:
            merged[key] = merged.get(key, 0.0) + value
    return merged


def _round_nested(mapping: dict) -> dict:
    return {k: (_round_nested(v) if isinstance(v, dict) else round(v, 2)) for k, v in mapping.items()}


def prorate(start: date, end: date, annual_by_year: Callable[[int], dict]) -> dict:
    """An annual budget prorated to [start, end]: the sum, over every year the window touches,
    of that year's annual budget x days of the window in that year / days in that year.
    ``annual_by_year(year)`` returns that year's budget map (flat or nested one level)."""
    parts = [(annual_by_year(year), days / total) for year, days, total in window_year_segments(start, end)]
    return _round_nested(_scaled_sum(parts))


def prior_window(start: date, end: date) -> tuple[date, date]:
    """The same window one year earlier (Feb 29 -> Feb 28)."""
    return same_day_prior_year(start), same_day_prior_year(end)


def tracking_type_totals(tree: dict) -> dict[str, float]:
    """``{tracking type: total}`` of a spending hierarchy (the prior-year bar markers)."""
    return {
        tt: round(sum(v for cats in groups.values() for merchants in cats.values() for v in merchants.values()), 2)
        for tt, groups in tree.items()
    }


def prior_detail(tree: dict) -> dict:
    """``{tt: {group: {category: {prior, merchants}}}}`` of a spending hierarchy (popup markers)."""
    return {
        tt: {
            grp: {cat: {"prior": round(sum(merchants.values()), 2), "merchants": {m: round(v, 2) for m, v in merchants.items()}}
                  for cat, merchants in cats.items()}
            for grp, cats in groups.items()
        }
        for tt, groups in tree.items()
    }


def _spending_type(tracking_type: str) -> bool:
    return tracking_type != "Income" and tracking_type not in spending_tracker._TRANSFER_NAMES


def annual_budgets(base_dir: str | Path, year: int) -> dict[str, dict]:
    """That year's annual budget ``{"by_type": {tt: amount}, "by_category": {tt: {label: amount}}}``
    from the Spending Analysis taxonomy, Income and transfers excluded."""
    taxonomy = spending_tracker.spending_summary_taxonomy(base_dir, year).get("tracking_types", [])
    return {
        "by_type": {
            t["tracking_type"]: t.get("annual_budget", 0.0)
            for t in taxonomy if t.get("annual_budget") and _spending_type(t["tracking_type"])
        },
        "by_category": {
            t["tracking_type"]: {
                c["label"]: c["annual_budget"]
                for g in t.get("groups", []) for c in g.get("categories", []) if c.get("annual_budget")
            }
            for t in taxonomy if _spending_type(t["tracking_type"])
        },
    }


def _annual_budgets_or_empty(base_dir, year: int) -> dict[str, dict]:
    # A year with no budget data counts as absent rather than failing the whole window.
    try:
        return annual_budgets(base_dir, year)
    except Exception:  # noqa: BLE001 - one year's budget must not break the Spending card
        logging.getLogger(__name__).exception("spending window: no budget for %s", year)
        return {"by_type": {}, "by_category": {}}


def first_transaction_year(base_dir: str | Path) -> int | None:
    years = [t["date"].year for t in spending_tracker.load_transactions_extended(base_dir, None)]
    return min(years) if years else None


def spending_window_payload(base_dir: str | Path, start: date, end: date,
                            budgets: Callable[[Any, int], dict] | None = None) -> dict[str, Any]:
    """The /api/spending body for the inclusive window [start, end]."""
    budgets = budgets or _annual_budgets_or_empty
    cache: dict[int, dict] = {}

    def for_year(year: int) -> dict:
        if year not in cache:
            cache[year] = budgets(base_dir, year)
        return cache[year]

    prior = None
    first_year = first_transaction_year(base_dir)
    p_start, p_end = prior_window(start, end)
    if first_year is not None and p_start.year >= first_year:
        tree = spending_tracker.spending_hierarchy_window(base_dir, p_start, p_end)
        prior = {"window": {"from": p_start.isoformat(), "to": p_end.isoformat()},
                 "by_type": tracking_type_totals(tree), "detail": prior_detail(tree)}
    full = for_year(end.year)
    return {
        "window": {"from": start.isoformat(), "to": end.isoformat(), "days": (end - start).days + 1},
        "hierarchy": spending_tracker.spending_hierarchy_window(base_dir, start, end),
        "prior": prior,
        "budget": {
            "by_type": prorate(start, end, lambda y: for_year(y)["by_type"]),
            "by_category": prorate(start, end, lambda y: for_year(y)["by_category"]),
        },
        "full_year_budget": {"year": end.year, "by_type": dict(full["by_type"]), "by_category": dict(full["by_category"])},
    }
