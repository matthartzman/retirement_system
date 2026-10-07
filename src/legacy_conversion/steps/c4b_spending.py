"""Conversion step C4b: the spending set's CSV files -> ``plan.db`` spending tables (WP6.3).

WP6.3a covers the taxonomy and the aliases; WP6.3b (budget, budget lines, tier overrides) and
WP6.3c (rules, category map, recovery seed -> plan revisions) extend this step.

``run(input_dir, store)`` reads ``client_spending_taxonomy.csv`` and
``client_spending_aliases.csv`` from ``input_dir`` (an absent file leaves its table empty) and
writes ``store.spending.taxonomy`` / ``store.spending.aliases`` plus the step marker
(``plan_meta['legacy_conversion.c4b']``) in one transaction. Cells are kept exactly as typed
(columns beyond the known ones are kept per row as extra columns). Running again on a plan that
carries the marker is a no-op. The originals are only read; the step is not wired into
startup (WP10 assembles it).

Legacy layouts, converted the way the old file readers read them:

* a taxonomy file in the pre-2026-06 layout (``section, subsection, label, value, notes``, no
  ``tracking_type/group/category_id/label`` header) becomes ``tracking_type = section``,
  ``group = subsection``, ``category_id = label``, ``label = value``, ``notes``,
  ``origin = template``, ``status = active`` (other columns kept as extra columns);
* an aliases file without the ``match_value`` and ``category_id`` columns was ignored by the
  reader (which then seeded aliases from the rules and category-map files); it is not imported
  (``aliases_ignored``), so the plan keeps that behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...csv_exchange import read_dataset_csv_file

STEP_ID = "C4b"
MARKER_KEY = "legacy_conversion.c4b"
# Spending dataset (``store.spending.<name>``) -> legacy file, in conversion order.
FILES: dict[str, str] = {
    "taxonomy": "client_spending_taxonomy.csv",
    "aliases": "client_spending_aliases.csv",
}
_TAXONOMY_CURRENT = {"tracking_type", "group", "category_id", "label"}
_ALIASES_REQUIRED = {"match_value", "category_id"}
_LEGACY_TAXONOMY_MAP = {"section": "tracking_type", "subsection": "group", "label": "category_id", "value": "label"}


@dataclass
class C4bReport:
    step: str
    skipped: bool
    rows_written: dict[str, int] = field(default_factory=dict)
    legacy_taxonomy_layout: bool = False
    aliases_ignored: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "skipped": self.skipped,
            "rows_written": dict(self.rows_written),
            "legacy_taxonomy_layout": self.legacy_taxonomy_layout,
            "aliases_ignored": self.aliases_ignored,
        }


def _legacy_taxonomy_row(row: dict[str, str]) -> dict[str, str]:
    out = {k: v for k, v in row.items() if k not in _LEGACY_TAXONOMY_MAP}
    for old, new in _LEGACY_TAXONOMY_MAP.items():
        out[new] = row.get(old, "")
    out["origin"] = "template"
    out["status"] = "active"
    out.setdefault("notes", "")
    return out


def run(input_dir: str | Path, store: Any) -> C4bReport:
    if store.get_meta(MARKER_KEY) is not None:
        return C4bReport(STEP_ID, skipped=True)
    report = C4bReport(STEP_ID, skipped=False)
    with store.transaction():
        for name, file in FILES.items():
            path = Path(input_dir) / file
            if not path.is_file():
                continue
            header, rows = read_dataset_csv_file(path)  # decoded as the old readers did
            if name == "taxonomy" and not _TAXONOMY_CURRENT.issubset(header):
                rows = [_legacy_taxonomy_row(r) for r in rows]
                report.legacy_taxonomy_layout = True
            if name == "aliases" and not _ALIASES_REQUIRED.issubset(header):
                report.aliases_ignored = True
                continue
            report.rows_written[name] = store.spending.dataset(name).replace_all(rows)
        store.set_meta(MARKER_KEY, "rows=" + ",".join(f"{k}:{n}" for k, n in sorted(report.rows_written.items())))
    return report
