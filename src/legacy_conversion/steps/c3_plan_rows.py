"""Conversion step C3: the legacy sectioned plan CSV set -> ``plan_rows``.

Design F section 8 / 13.3 (P3), written in WP4.1; WP10 assembles it with the other steps
(source precedence, markers in app.db, verification, first-launch UI). Not wired into
startup.

``run(input_dir, store)``:

1. reads the plan CSV set from ``input_dir`` through ``csv_exchange`` (same parse rules as
   every plan import: columns by header name, cells stripped, year-stamped labels canonical,
   ``#`` comments attached to the row below them become its notes, free-floating comments
   dropped, duplicate keys collapsed last-wins at the first position);
2. applies the legacy row renames once (``plan_data_migration.migrate_rows`` over the whole
   set: member_1/member_2, wellness -> healthcare, the state-generic estate subsection and
   auto-insurance label; when the current key already exists the legacy row is dropped) and
   drops the retired ``Scenarios / Sell Home`` home-value labels that the old loader
   (``config_backend``) discarded at every load;
3. writes the rows and the step marker (``plan_meta['legacy_conversion.c3']``) into the
   empty target plan in one transaction.

The originals are only read. Running again on a plan that carries the marker is a no-op;
a plan that has rows but no marker is refused (nothing is overwritten). The sectioned view
of the result equals what the old engine path saw: ``migrate_sectioned_data`` applied to
the loaded CSV set.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ...csv_exchange import ImportReport, PlanCsvRow, collapse_duplicate_keys, read_plan_csv_set, write_plan_rows
from ...plan_data_migration import migrate_rows
from ...plan_label_rules import is_retired_scenario_home_row

STEP_ID = "C3"
MARKER_KEY = "legacy_conversion.c3"

class ConversionError(ValueError):
    """The step cannot run against this source or target; nothing was written."""


@dataclass
class C3Report:
    step: str
    skipped: bool
    rows_written: int = 0
    legacy_renamed: int = 0
    retired_dropped: int = 0
    source: ImportReport | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "skipped": self.skipped,
            "rows_written": self.rows_written,
            "legacy_renamed": self.legacy_renamed,
            "retired_dropped": self.retired_dropped,
            "source": self.source.as_dict() if self.source else None,
        }


def _is_retired(row: PlanCsvRow) -> bool:
    return is_retired_scenario_home_row(row.section, row.subsection, row.label)


def convert_rows(rows: list[PlanCsvRow]) -> tuple[list[PlanCsvRow], int, int]:
    """Pure: ``(converted rows, legacy rows renamed or dropped, retired rows dropped)``.

    Duplicate keys collapse first, last row wins (the old loader's order: ``load_csv`` then
    ``migrate_sectioned_data``), so two legacy rows of one key yield the LAST one's value
    under the renamed key; ``migrate_rows`` alone keeps the first. A legacy row whose
    current key exists is still dropped (the current key wins)."""
    rows, _ = collapse_duplicate_keys(rows)
    migrated, renamed = migrate_rows([[r.section, r.subsection, r.label, r] for r in rows])
    out: list[PlanCsvRow] = []
    retired = 0
    for section, subsection, label, row in migrated:
        new = row if (subsection, label) == (row.subsection, row.label) else replace(row, subsection=subsection, label=label)
        if _is_retired(new):
            retired += 1
            continue
        out.append(new)
    return out, renamed, retired


def run(input_dir: str | Path, store: Any) -> C3Report:
    """Convert the plan CSV set in ``input_dir`` into the open, writable plan ``store``."""
    if store.get_meta(MARKER_KEY) is not None:
        return C3Report(STEP_ID, skipped=True)
    parsed = read_plan_csv_set(input_dir)
    if not parsed.report.files_read:
        raise ConversionError(f"no plan CSV files in {input_dir}")
    rows, renamed, retired = convert_rows(parsed.rows)
    with store.transaction():
        written = write_plan_rows(store, rows)
        store.set_meta(MARKER_KEY, f"rows={written} legacy_renamed={renamed} retired_dropped={retired}")
    parsed.report.rows = written
    return C3Report(STEP_ID, skipped=False, rows_written=written, legacy_renamed=renamed,
                    retired_dropped=retired, source=parsed.report)
