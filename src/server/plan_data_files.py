from __future__ import annotations

from pathlib import Path

UI_NAMES = ["index.html", "retirement_dashboard.html"]
CLIENT_DATA_PART_FILES = [
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
CLIENT_DATA_CSV_FILES = ["client_data.csv", *CLIENT_DATA_PART_FILES]
CLIENT_DATA_CSV_FILE_SET = set(CLIENT_DATA_CSV_FILES)
CLIENT_DATA_DERIVED_FILES = [
    "client_data.json",
    "client_data.yaml",
    *[f"{Path(name).stem}.json" for name in CLIENT_DATA_PART_FILES],
    *[f"{Path(name).stem}.yaml" for name in CLIENT_DATA_PART_FILES],
]
CLIENT_DATA_DERIVED_FILE_SET = set(CLIENT_DATA_DERIVED_FILES)
PLAN_DATA_CSV_FILES = [
    *CLIENT_DATA_CSV_FILES,
    "client_holdings.csv",
    "client_liabilities.csv",
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
SYSTEM_REFERENCE_FILES = [
    "security_master.csv",
    "capital_market_assumptions.csv",
    "asset_correlations.csv",
    "schema.csv",
    "state_tax.csv",
    "tax_constants.csv",
    "tax_update_dashboard.csv",
]
PLAN_DATA_DERIVED_FILES = CLIENT_DATA_DERIVED_FILES
PLAN_DATA_FILES = [*PLAN_DATA_CSV_FILES, *YTD_PLAN_DATA_FILES, *PLAN_DATA_DERIVED_FILES]
PLAN_DATA_FILE_SET = set(PLAN_DATA_FILES)
PLAN_DATA_CSV_FILE_SET = set(PLAN_DATA_CSV_FILES)
