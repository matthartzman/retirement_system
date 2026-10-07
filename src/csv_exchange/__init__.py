"""csv_exchange: the one product package that reads or writes CSV (design F section 6).

WP4.1 lands the minimal plan-CSV-set importer (used by the test fixture helper and by
conversion step C3). WP4.2 adds ``sync_plan_rows``, which carries the CSV set the legacy
writers still edit into an existing plan (``src/active_plan.py``) until WP4.3-4.5. WP9 grows this package into the full import/export surface
(preview, diff, per-dataset adapters, export); the static file-I/O audit allowlists it.
"""
from ..plan_label_rules import canonical_label
from .plan_csv import (
    ANCHOR_FILE,
    PART_FILE_SECTIONS,
    PLAN_CSV_FILES,
    ImportReport,
    PlanCsvError,
    PlanCsvRow,
    PlanCsvSet,
    SkippedRecord,
    collapse_duplicate_keys,
    import_plan_csv_set,
    parse_plan_csv,
    part_file_for_section,
    read_plan_csv_set,
    sync_plan_rows,
    write_plan_rows,
)

__all__ = [
    "ANCHOR_FILE",
    "ImportReport",
    "PART_FILE_SECTIONS",
    "PLAN_CSV_FILES",
    "PlanCsvError",
    "PlanCsvRow",
    "PlanCsvSet",
    "SkippedRecord",
    "canonical_label",
    "collapse_duplicate_keys",
    "import_plan_csv_set",
    "parse_plan_csv",
    "part_file_for_section",
    "read_plan_csv_set",
    "sync_plan_rows",
    "write_plan_rows",
]
