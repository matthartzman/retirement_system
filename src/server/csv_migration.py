from __future__ import annotations
"""Plan Data CSV row migration/purge helpers.

Extracted from app_core.py (see documentation/SYSTEM_REVIEW_AND_REFACTOR_PLAN.md
Phase 2 "Gap 2"). Each migration below drops rows matching a retired/deprecated
key from either an in-memory row list, a raw CSV string, or every on-disk Plan
Data file, sharing the same `_strip_rows_matching` primitive.

Imports `app_core` as a module (not specific names) so this file can be
imported by app_core.py itself (`from .csv_migration import *`) without a
circular-import failure at load time — the same pattern already used by
src/projection_stages/deterministic_engine.py for planning_engines.py. Names
referenced via `_app_core.X` are only ever resolved inside function bodies
(at call time, once both modules have finished loading), never at this
module's own top level.
"""

import csv
import io

from . import app_core as _app_core

DEPRECATED_ALLOCATION_COUNT_LABELS = {
    "_".join(parts)
    for parts in [
        ("count", "social", "security", "toward", "fixed", "income", "target"),
        ("count", "pension", "toward", "fixed", "income", "target"),
        ("count", "annuity", "toward", "fixed", "income", "target"),
        ("count", "note", "receivable", "toward", "fixed", "income", "target"),
        ("count", "home", "equity", "toward", "reit", "target"),
    ]
}

RETIRED_SCENARIO_HOME_ROW_KEYS = {
    ("Scenarios", "Sell Home", "home_sale_price"),
    ("Scenarios", "Sell Home", "home_basis"),
    ("Scenarios", "Sell Home", "home_value"),
    ("Scenarios", "Sell Home", "house_value"),
    ("Scenarios", "Sell Home", "value_as_of_plan_start"),
    ("Scenarios", "Sell Home", "current_home_value"),
    ("Scenarios", "Sell Home", "current_value"),
    ("Scenarios", "Sell Home", "market_value"),
}


# Generic "drop rows matching a predicate" primitives shared by every
# retired/deprecated Plan Data row migration below. Each migration only
# needs to supply its own row-matching predicate.
def _strip_rows_matching(rows: list[list[str]], predicate) -> tuple[list[list[str]], int]:
    kept: list[list[str]] = []
    removed = 0
    for row in rows:
        if predicate(row):
            removed += 1
            continue
        kept.append(row)
    return kept, removed


def _strip_csv_rows_matching(content: str, predicate) -> tuple[str, int]:
    source = io.StringIO(content or "")
    rows = list(csv.reader(source))
    kept, removed = _strip_rows_matching(rows, predicate)
    if not removed:
        return content, 0
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(kept)
    return out.getvalue(), removed


def _purge_rows_matching_from_plan_data(predicate) -> int:
    removed_total = 0
    for name in _app_core.CLIENT_DATA_CSV_FILES:
        path = _app_core._plan_data_path(name, prefer_existing=True)
        if not path.exists():
            continue
        rows = _app_core._csv_read_rows(path)
        kept, removed = _strip_rows_matching(rows, predicate)
        if removed:
            _app_core._csv_write_rows(path, kept)
            removed_total += removed
    return removed_total


def _is_retired_scenario_home_row(row: list[str]) -> bool:
    cols = list(row) + [""] * 3
    key = (str(cols[0]).strip(), str(cols[1]).strip(), str(cols[2]).strip())
    return key in RETIRED_SCENARIO_HOME_ROW_KEYS


def _strip_retired_scenario_home_rows(rows: list[list[str]]) -> tuple[list[list[str]], int]:
    return _strip_rows_matching(rows, _is_retired_scenario_home_row)


def _strip_retired_scenario_home_csv(content: str) -> tuple[str, int]:
    return _strip_csv_rows_matching(content, _is_retired_scenario_home_row)


def _purge_retired_scenario_home_rows_from_plan_data() -> int:
    return _purge_rows_matching_from_plan_data(_is_retired_scenario_home_row)


def _is_deprecated_allocation_count_row(row: list[str]) -> bool:
    cols = list(row) + [""] * 3
    return (
        str(cols[0]).strip() == "Model Constants"
        and str(cols[1]).strip() == "Allocation"
        and str(cols[2]).strip() in DEPRECATED_ALLOCATION_COUNT_LABELS
    )


def _strip_deprecated_allocation_count_rows(rows: list[list[str]]) -> tuple[list[list[str]], int]:
    return _strip_rows_matching(rows, _is_deprecated_allocation_count_row)


def _strip_deprecated_allocation_count_csv(content: str) -> tuple[str, int]:
    return _strip_csv_rows_matching(content, _is_deprecated_allocation_count_row)


def _purge_deprecated_allocation_count_rows_from_plan_data() -> int:
    return _purge_rows_matching_from_plan_data(_is_deprecated_allocation_count_row)


# Python's default `from X import *` skips underscore-prefixed names; every
# function here is underscore-prefixed by this codebase's convention, and
# app_core.py needs all of them via `from .csv_migration import *` to
# preserve its own `from .app_core import *` contract with plan_routes.py /
# workbook_routes.py / admin_routes.py / base_routes.py unchanged. Matches
# the same override app_core.py itself uses at its own end.
__all__ = [name for name in globals() if not name.startswith("__")]
