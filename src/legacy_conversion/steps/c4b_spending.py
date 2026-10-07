"""Conversion step C4b: the spending set's CSV files -> ``plan.db`` spending tables (WP6.3).

WP6.3a covers the taxonomy and the aliases, WP6.3b the budget, budget lines and tier
overrides, WP6.3c the rules, the category map, the group budget (``spending_budget.csv``) and the
recovery copies (the budget recovery seed and the ``.pre_recovery_backup`` copy become plan
revisions, ``store.spending.set_recovery_seed`` / ``keep_pre_recovery_copy``).

``run(input_dir, store)`` reads each dataset's legacy file from ``input_dir`` (an absent file
leaves its table empty) and writes ``store.spending.<name>`` plus the step markers in one
transaction. Cells are kept exactly as typed (columns beyond the known ones are kept per row as
extra columns). Every dataset has its own marker (``plan_meta['legacy_conversion.c4b.<name>']``,
its row count) next to the step marker (``plan_meta['legacy_conversion.c4b']``); a dataset with
a marker is not converted again, so running on a converted plan is a no-op, and a plan converted
by the WP6.3a version of this step (step marker only, no dataset markers: taxonomy and aliases
done) is completed with the datasets added since, without touching the done ones. A dataset
whose table already holds rows is never overwritten by a late conversion. The originals are only
read; the step is not wired into startup (WP10 assembles it).

Legacy layouts, converted the way the old file readers read them:

* a taxonomy file in the pre-2026-06 layout (``section, subsection, label, value, notes``, no
  ``tracking_type/group/category_id/label`` header) becomes ``tracking_type = section``,
  ``group = subsection``, ``category_id = label``, ``label = value``, ``notes``,
  ``origin = template``, ``status = active`` (other columns kept as extra columns);
* a budget file in the pre-unified layout (no ``kind``/``key`` columns: one row per
  ``category_id`` with ``annual_budget`` and ``notes``) becomes ``kind = category`` rows, the
  amounts of a category summed and written as whole numbers (this is what the retired
  ``tools/migrate_spending_model.py`` did to it); its budget-lines file is kept as it is (the
  budget-lines table is the dataset the build reads, so the lines are not duplicated as
  ``kind = line`` rows). The same tool's other duties are not repeated here: the aliases the
  tool derived from the rules and the category map are derived the same way, at read time, by
  ``spending_tracker.load_aliases`` whenever the plan has no aliases, from the ``rules`` and
  ``category_map`` tables this step fills; category ids are renamed by the at-rest migration
  (``plan_data_migration``);
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
DATASET_MARKER_PREFIX = MARKER_KEY + "."
# Spending dataset (``store.spending.<name>``) -> legacy file, in conversion order.
FILES: dict[str, str] = {
    "taxonomy": "client_spending_taxonomy.csv",
    "aliases": "client_spending_aliases.csv",
    "budget": "client_spending_budget.csv",
    "budget_lines": "client_spending_budget_lines.csv",
    "tier_overrides": "client_spending_tier_overrides.csv",
    "rules": "client_spending_rules.csv",
    "category_map": "spending_category_map.csv",
    "group_budget": "spending_budget.csv",
}
# The recovery copies (plan revisions, not tables), converted after the datasets.
RECOVERY_FILES: dict[str, str] = {
    "recovery_seed": "client_spending_budget.recovery_seed.csv",
    "pre_recovery_backup": "client_spending_budget.csv.pre_recovery_backup",
}
_ALL_UNITS = (*FILES, *RECOVERY_FILES)
# The datasets the WP6.3a version of this step converted (it wrote no dataset markers).
_CONVERTED_BY_6_3A = ("taxonomy", "aliases")
_TAXONOMY_CURRENT = {"tracking_type", "group", "category_id", "label"}
_ALIASES_REQUIRED = {"match_value", "category_id"}
_LEGACY_TAXONOMY_MAP = {"section": "tracking_type", "subsection": "group", "label": "category_id", "value": "label"}


@dataclass
class C4bReport:
    step: str
    skipped: bool
    rows_written: dict[str, int] = field(default_factory=dict)
    legacy_taxonomy_layout: bool = False
    legacy_budget_layout: bool = False
    aliases_ignored: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "skipped": self.skipped,
            "rows_written": dict(self.rows_written),
            "legacy_taxonomy_layout": self.legacy_taxonomy_layout,
            "legacy_budget_layout": self.legacy_budget_layout,
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


_BUDGET_CURRENT = {"kind", "key"}


def _legacy_budget_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """A pre-unified budget file (one row per ``category_id``) as ``kind = category`` rows."""
    totals: dict[str, float] = {}
    notes: dict[str, str] = {}
    for r in rows:
        cid = (r.get("category_id") or "").strip()
        if not cid:
            continue
        try:
            amount = float(str(r.get("annual_budget") or "").replace("$", "").replace(",", "").strip() or 0)
        except ValueError:
            amount = 0.0
        totals[cid] = totals.get(cid, 0.0) + amount
        notes.setdefault(cid, r.get("notes", ""))
    return [
        {"kind": "category", "key": cid, "label": cid, "annual_budget": "%d" % round(t) if t else "",
         "start_year": "", "end_year": "", "one_time_year": "", "notes": notes.get(cid, "")}
        for cid, t in sorted(totals.items())
    ]


def _done_datasets(store: Any) -> set[str]:
    done = {n for n in _ALL_UNITS if store.get_meta(DATASET_MARKER_PREFIX + n) is not None}
    if store.get_meta(MARKER_KEY) is not None:
        done |= {n for n in _CONVERTED_BY_6_3A}
    return done


def _previous_rows(store: Any) -> dict[str, int]:
    value = store.get_meta(MARKER_KEY) or ""
    out: dict[str, int] = {}
    for part in value.removeprefix("rows=").split(","):
        name, _, n = part.partition(":")
        if name and n.isdigit():
            out[name] = int(n)
    return out


def run(input_dir: str | Path, store: Any) -> C4bReport:
    done = _done_datasets(store)
    todo = [n for n in _ALL_UNITS if n not in done]
    if not todo:
        return C4bReport(STEP_ID, skipped=True)
    report = C4bReport(STEP_ID, skipped=False)
    with store.transaction():
        for name in todo:
            if name in RECOVERY_FILES:
                path = Path(input_dir) / RECOVERY_FILES[name]
                if path.is_file():
                    _, rows = read_dataset_csv_file(path)
                    if name == "recovery_seed" and not store.spending.recovery_seed():
                        report.rows_written[name] = store.spending.set_recovery_seed(rows)
                    elif name == "pre_recovery_backup" and store.spending.keep_pre_recovery_copy(rows):
                        report.rows_written[name] = len(rows)
                store.set_meta(DATASET_MARKER_PREFIX + name, str(report.rows_written.get(name, 0)))
                continue
            path = Path(input_dir) / FILES[name]
            if path.is_file():
                header, rows = read_dataset_csv_file(path)  # decoded as the old readers did
                if name == "taxonomy" and not _TAXONOMY_CURRENT.issubset(header):
                    rows = [_legacy_taxonomy_row(r) for r in rows]
                    report.legacy_taxonomy_layout = True
                if name == "budget" and not _BUDGET_CURRENT.issubset(header):
                    rows = _legacy_budget_rows(rows)
                    report.legacy_budget_layout = True
                if name == "aliases" and not _ALIASES_REQUIRED.issubset(header):
                    report.aliases_ignored = True
                elif store.spending.dataset(name).count() == 0:
                    report.rows_written[name] = store.spending.dataset(name).replace_all(rows)
            store.set_meta(DATASET_MARKER_PREFIX + name, str(report.rows_written.get(name, 0)))
        rows_total = {**_previous_rows(store), **report.rows_written}
        store.set_meta(MARKER_KEY, "rows=" + ",".join(f"{k}:{n}" for k, n in sorted(rows_total.items())))
    return report
