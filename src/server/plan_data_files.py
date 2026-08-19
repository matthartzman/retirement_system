from __future__ import annotations

try:
    from ..plan_data_registry import (
        CLIENT_DATA_PART_FILES,
        SYSTEM_REFERENCE_FILES,
        client_data_csv_files,
        client_data_derived_files,
    )
except ImportError:  # pragma: no cover - direct execution fallback
    from src.plan_data_registry import (
        CLIENT_DATA_PART_FILES,
        SYSTEM_REFERENCE_FILES,
        client_data_csv_files,
        client_data_derived_files,
    )

UI_NAMES = ["index.html", "retirement_dashboard.html"]
CLIENT_DATA_CSV_FILES = client_data_csv_files()
CLIENT_DATA_CSV_FILE_SET = set(CLIENT_DATA_CSV_FILES)
CLIENT_DATA_DERIVED_FILES = client_data_derived_files()
CLIENT_DATA_DERIVED_FILE_SET = set(CLIENT_DATA_DERIVED_FILES)
PLAN_DATA_CSV_FILES = [
    *CLIENT_DATA_CSV_FILES,
    "client_holdings.csv",
    "client_liabilities.csv",
    "client_hsa_schedule.csv",
    "target_allocation.csv",
    "client_spending_taxonomy.csv",
    "client_spending_aliases.csv",
    "client_spending_budget.csv",
    "client_spending_budget_lines.csv",
]
YTD_PLAN_DATA_FILES = [
    "ytd_transactions.csv",
    "ytd_account_setup.csv",
    "ytd_import_history.csv",
]
PLAN_DATA_DERIVED_FILES = CLIENT_DATA_DERIVED_FILES
PLAN_DATA_FILES = [*PLAN_DATA_CSV_FILES, *YTD_PLAN_DATA_FILES, *PLAN_DATA_DERIVED_FILES]
# Read/written through _read_plan_data_file/_write_plan_data_file by
# demo_plan_service.TEXT_BACKUP_FILES (see that module's docstring) but
# deliberately excluded from PLAN_DATA_CSV_FILES -- they are not part of the
# regular materialize()/folder-sync sweep, only demo mode's own backup/apply/
# restore. They still need to pass _normalize_plan_data_file_name's
# allowlist, or Open Demo Plan raises "Unsupported Plan Data file" the
# moment it tries to write the first one.
DEMO_TEXT_BACKUP_FILES = [
    "client_spending_budget.recovery_seed.csv",
    "client_spending_rules.csv",
    "spending_category_map.csv",
    "spending_budget.csv",
]
PLAN_DATA_FILE_SET = set(PLAN_DATA_FILES) | set(DEMO_TEXT_BACKUP_FILES)
PLAN_DATA_CSV_FILE_SET = set(PLAN_DATA_CSV_FILES)
