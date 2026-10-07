"""csv_exchange: the one product package that reads or writes CSV (design F section 6).

WP4.1 lands the minimal plan-CSV-set importer (used by the test fixture helper, the demo seed
and conversion step C3). WP4.5 deleted the transition bridge (``sync_plan_rows``,
``write_back_rows``, the set fingerprint): the plan rows are the only store, and nothing
writes a plan CSV any more. WP9 grows this package into the full import/export surface
(preview, diff, per-dataset adapters, export); the static file-I/O audit allowlists it.
"""
from ..plan_label_rules import canonical_label
from .flat_csv import dataset_csv_text, parse_csv_dicts, replace_dataset_from_csv_text
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
    "dataset_csv_text",
    "import_plan_csv_set",
    "parse_csv_dicts",
    "parse_plan_csv",
    "part_file_for_section",
    "read_plan_csv_set",
    "replace_dataset_from_csv_text",
    "write_plan_rows",
]
