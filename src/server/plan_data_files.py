from __future__ import annotations

"""The Plan Data files the server still reads and writes as files (WP4.5).

The sectioned plan data (the ``client_data.csv`` anchor and its nine part files) lives in the
plan file's ``plan_rows`` and has no file form here any more; the part files' names and their
JSON/YAML mirrors are only in ``RETIRED_PLAN_PART_FILES``, so a request for one is refused with
a clear message (CSV import and export return with WP9). What is left is the flat datasets,
which move into the plan file with WP6: holdings, liabilities, HSA schedule, target allocation,
the spending set and the YTD files.
"""

from ..plan_data_registry import (
    CLIENT_DATA_PART_FILES,
    FLAT_PLAN_DATA_CSV_FILES,
    SYSTEM_REFERENCE_FILES,
    YTD_PLAN_DATA_FILES as _YTD_PLAN_DATA_FILES,
)

UI_NAMES = ["index.html", "retirement_dashboard.html"]
PLAN_DATA_CSV_FILES = list(FLAT_PLAN_DATA_CSV_FILES)
YTD_PLAN_DATA_FILES = list(_YTD_PLAN_DATA_FILES)
PLAN_DATA_FILES = [*PLAN_DATA_CSV_FILES, *YTD_PLAN_DATA_FILES]
# Read/written through _read_plan_data_file/_write_plan_data_file by
# demo_plan_service.TEXT_BACKUP_FILES (see that module's docstring) but
# deliberately excluded from PLAN_DATA_CSV_FILES -- they are not part of the
# regular materialize() sweep, only demo mode's own backup/apply/restore. They
# still need to pass _normalize_plan_data_file_name's allowlist, or Open Demo
# Plan raises "Unsupported Plan Data file" the moment it tries to write the
# first one.
DEMO_TEXT_BACKUP_FILES = [
    "client_spending_budget.recovery_seed.csv",
    "client_spending_rules.csv",
    "spending_category_map.csv",
    "spending_budget.csv",
]
PLAN_DATA_FILE_SET = set(PLAN_DATA_FILES) | set(DEMO_TEXT_BACKUP_FILES)
PLAN_DATA_CSV_FILE_SET = set(PLAN_DATA_CSV_FILES)
# The sectioned part files (and the derived JSON/YAML mirrors of each) that used to be served
# and written as files. Their data is plan_rows now.
RETIRED_PLAN_PART_FILES = frozenset({
    "client_data.csv",
    *CLIENT_DATA_PART_FILES,
    *(f"{name[:-4]}{suffix}" for name in ("client_data.csv", *CLIENT_DATA_PART_FILES) for suffix in (".json", ".yaml")),
})
