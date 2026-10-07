"""Conversion step C4a: holdings, liabilities, HSA schedule and target allocation CSVs ->
``plan.db`` dataset tables (WP6.1 / WP6.2).

``run(input_dir, store)`` reads ``client_holdings.csv``, ``client_liabilities.csv``,
``client_hsa_schedule.csv`` and ``target_allocation.csv`` from ``input_dir`` (a file that is
absent leaves its table empty) and writes the tables plus the step marker
(``plan_meta['legacy_conversion.c4a']``) in one transaction. Cells are kept exactly as typed.
Running again on a plan that carries the marker is a no-op. The originals are only read; the
step is not wired into startup (WP10 assembles it).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...csv_exchange import import_flat_datasets

STEP_ID = "C4a"
MARKER_KEY = "legacy_conversion.c4a"


@dataclass
class C4aReport:
    step: str
    skipped: bool
    rows_written: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"step": self.step, "skipped": self.skipped, "rows_written": dict(self.rows_written)}


def run(input_dir: str | Path, store: Any) -> C4aReport:
    if store.get_meta(MARKER_KEY) is not None:
        return C4aReport(STEP_ID, skipped=True)
    with store.transaction():
        written = import_flat_datasets(input_dir, store)
        store.set_meta(MARKER_KEY, "rows=" + ",".join(f"{k}:{n}" for k, n in sorted(written.items())))
    return C4aReport(STEP_ID, skipped=False, rows_written=written)
