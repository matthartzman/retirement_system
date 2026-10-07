from __future__ import annotations
"""Single authoritative registry for the legacy plan CSV part-file names.

``CLIENT_DATA_PART_FILES`` lists the sectioned client CSVs that merge into
client_data.csv (client_household.csv, client_income.csv, ...). Since WP4.5 the plan data
lives in the plan file's ``plan_rows``; the list remains for the code that still reads that
legacy layout: ``data_io.load_csv`` (the golden tool and tests), the schema registry's
coverage and ``csv_exchange`` (``PLAN_CSV_FILES`` equals it).

This module intentionally has NO imports beyond the stdlib (just ``pathlib``)
so it is safe to import from any layer -- data_io, config_backend,
schema_registry, server/*, server_services/* -- without
risking a circular import.
"""

from pathlib import Path

# The sectioned client CSVs that get merged into client_data.csv.
# Add a new sectioned CSV here ONCE; every consumer below picks it up.
CLIENT_DATA_PART_FILES: list[str] = [
    "client_household.csv",
    "client_income.csv",
    "client_spending.csv",
    "client_assets.csv",
    "client_policy.csv",
    "client_insurance_estate.csv",
    "client_business.csv",
    "client_optional_functions.csv",
    "asset_class_optimizer_controls.csv",
]


def client_data_csv_files(*, include_client_data: bool = True) -> list[str]:
    """['client_data.csv', *CLIENT_DATA_PART_FILES] (or just the parts)."""
    head = ["client_data.csv"] if include_client_data else []
    return [*head, *CLIENT_DATA_PART_FILES]


# System/reference CSVs (not per-client plan data). Defined here -- rather than
# in server/plan_data_files.py -- so that server_services/admin_service can
# import it without pulling in the src.server package (importing a submodule
# of a package always runs that package's __init__.py first, which registers
# admin_routes, which reads admin_service back -- a
# circular import if admin_service ever depended on src.server.*).
# Shipped reference data now lives in the read-only reference.db (WP3), so there are no
# editable reference files left. The admin "reference files" editor (frontend/js/admin.js)
# is retired with the csv_exchange work package, which adds override screens instead.
SYSTEM_REFERENCE_FILES: list[str] = []


# The flat datasets (not sectioned plan rows): still files / ``client_files`` text until WP6 moves
# them into the plan file. ``materialize_workspace_files`` restores them for the build.
FLAT_PLAN_DATA_CSV_FILES: list[str] = [
    "client_holdings.csv",
    "client_liabilities.csv",
    "client_hsa_schedule.csv",
    "target_allocation.csv",
    "client_spending_taxonomy.csv",
    "client_spending_aliases.csv",
    "client_spending_budget.csv",
    "client_spending_budget_lines.csv",
]
# The flat datasets that live in the plan file's tables since WP6 (they travel with the plan
# file: Save As, Load, restore, the demo swap), so nothing materializes or swaps them as files.
PLAN_TABLE_DATASET_FILES: frozenset[str] = frozenset({
    "client_holdings.csv",
    "client_liabilities.csv",
    "client_hsa_schedule.csv",
    "target_allocation.csv",
    "client_spending_taxonomy.csv",
    "client_spending_aliases.csv",
})
YTD_PLAN_DATA_FILES: list[str] = [
    "ytd_transactions.csv",
    "ytd_account_setup.csv",
    "ytd_import_history.csv",
]


class RetiredPlanDataFile(ValueError):
    """A request for one of the sectioned plan CSV files (or its JSON/YAML mirror): that data
    is the plan file's rows now (WP4.5); CSV import and export return with WP9."""
