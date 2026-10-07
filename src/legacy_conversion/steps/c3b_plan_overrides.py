"""Conversion step C3b: the legacy custom reference files -> plan override tables.

Until WP3 a plan could point at expert files over the shipped reference data:
``capital_market_assumptions.csv`` (``custom_capital_market_file``) and
``asset_correlations.csv`` (``custom_correlations_file``), read only when
``use_custom_capital_market_file`` / ``use_custom_correlations_file`` was YES. WP3 moved the
shipped data into ``reference.db`` and left the custom files as plan-side override rows;
WP4.5 stores those rows in ``plan_rows`` (``plan_overrides``: sections ``Custom Capital
Market`` and ``Custom Correlations``, one ``row_N`` subsection per CSV row, one plan row per
column). The custom real-loss curve file never existed as a file option (the curves were
always a shipped table), so there is nothing to convert for it.

``convert(kind, rows)`` is pure: the file's rows (``csv_exchange.parse_csv_dicts``) restricted
to the known columns and validated by ``plan_overrides.validate_rows`` (invalid rows raise
``plan_overrides.OverrideRowsError``; the converter reports them rather than storing a table the
engine would half-read). ``run(store, files)`` writes the tables of the files given
(``{kind: csv text}``; a kind whose text is missing or has no data rows is left out) into the open
plan in one transaction and stamps ``plan_meta['legacy_conversion.c3b']``; a plan that already has
the marker is left untouched. The originals are only read by the caller.

Only the file *contents* are converted. The ``use_custom_*`` switches are system-config rows
(WP8.1 moves them into the plan) and keep their meaning: the override rows apply only when
the capital-market config selects custom assumptions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ...csv_exchange import parse_csv_dicts
from ...plan_overrides import COLUMNS, CMA, CORRELATIONS, replace_rows, validate_rows

STEP_ID = "C3b"
MARKER_KEY = "legacy_conversion.c3b"
# The legacy file each table came from (by its default name).
LEGACY_FILES = {CMA: "capital_market_assumptions.csv", CORRELATIONS: "asset_correlations.csv"}


@dataclass
class C3bReport:
    step: str
    skipped: bool
    rows_written: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"step": self.step, "skipped": self.skipped, "rows_written": dict(self.rows_written)}


def convert(kind: str, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Pure: the legacy file's rows (any extra column, such as ``notes``, dropped) as the
    validated override table rows of ``kind``."""
    known = set(COLUMNS[kind])
    return validate_rows(kind, [{k: v for k, v in row.items() if k in known} for row in rows])


def run(store: Any, files: Mapping[str, str]) -> C3bReport:
    """Write the override tables for the legacy file texts in ``files`` (``{kind: text}``)
    into the open, writable plan ``store``."""
    if store.get_meta(MARKER_KEY) is not None:
        return C3bReport(STEP_ID, skipped=True)
    tables = {kind: convert(kind, parse_csv_dicts(text)) for kind, text in files.items() if kind in LEGACY_FILES and text}
    written: dict[str, int] = {}
    with store.transaction():
        for kind, rows in tables.items():
            if rows:
                written[kind] = replace_rows(store, kind, rows)
        store.set_meta(MARKER_KEY, "rows=" + ",".join(f"{k}:{n}" for k, n in sorted(written.items())))
    return C3bReport(STEP_ID, skipped=False, rows_written=written)
