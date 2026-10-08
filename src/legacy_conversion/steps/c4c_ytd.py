"""Conversion step C4c: the YTD files -> ``plan.db`` YTD tables (WP6.4).

``run(input_dir, store)`` reads ``ytd_transactions.csv``, ``ytd_account_setup.csv`` and
``ytd_import_history.csv`` from ``input_dir`` (a file that is absent leaves its table empty)
and writes ``ytd_transactions``, ``ytd_account_setup`` and ``ytd_import_history`` plus the step
marker (``plan_meta['legacy_conversion.c4c']``) in one transaction. Cells are kept exactly as
typed, in file order (columns beyond the known ones are kept per row as extra columns). Running
again on a plan that carries the marker is a no-op. The originals are only read; the step is not
wired into startup (WP10 assembles it).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...csv_exchange import import_flat_datasets

STEP_ID = "C4c"
MARKER_KEY = "legacy_conversion.c4c"
# The datasets this step converts (``store.dataset(name)``).
DATASETS = ("ytd_transactions", "ytd_account_setup", "ytd_import_history")


@dataclass
class C4cReport:
    step: str
    skipped: bool
    rows_written: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"step": self.step, "skipped": self.skipped, "rows_written": dict(self.rows_written)}


def run(input_dir: str | Path, store: Any) -> C4cReport:
    if store.get_meta(MARKER_KEY) is not None:
        return C4cReport(STEP_ID, skipped=True)
    with store.transaction():
        written = import_flat_datasets(input_dir, store, DATASETS)
        store.set_meta(MARKER_KEY, "rows=" + ",".join(f"{k}:{n}" for k, n in sorted(written.items())))
    return C4cReport(STEP_ID, skipped=False, rows_written=written)
