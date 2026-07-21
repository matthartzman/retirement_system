from __future__ import annotations
"""Single authoritative registry for plan-data file name lists.

``CLIENT_DATA_PART_FILES`` is the one place that lists the sectioned client
CSVs that merge into client_data.csv/json/yaml (client_household.csv,
client_income.csv, ...). Historically this exact list was copy-pasted into
~8 modules (config_backend, data_io, server/plan_data_files,
local_plan_data_sync, schema_registry, server_services/admin_service, ...),
so adding one new sectioned CSV meant editing every one of them.

Every consumer below imports the core list (and/or the small helpers that
derive the .csv/.json/.yaml mirror names from it) and composes its own
effective set locally -- each site's effective membership is unchanged, only
the shared CORE is defined once.

This module intentionally has NO imports beyond the stdlib (just ``pathlib``)
so it is safe to import from any layer -- data_io, config_backend,
schema_registry, local_plan_data_sync, server/*, server_services/* -- without
risking a circular import.
"""

from pathlib import Path

# The sectioned client CSVs that get merged into client_data.csv/json/yaml.
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


def client_data_part_stems() -> list[str]:
    """CLIENT_DATA_PART_FILES with the .csv suffix stripped."""
    return [Path(name).stem for name in CLIENT_DATA_PART_FILES]


def client_data_csv_files(*, include_client_data: bool = True) -> list[str]:
    """['client_data.csv', *CLIENT_DATA_PART_FILES] (or just the parts)."""
    head = ["client_data.csv"] if include_client_data else []
    return [*head, *CLIENT_DATA_PART_FILES]


def client_data_suffixed_files(suffix: str, *, include_client_data: bool = True) -> list[str]:
    """['client_data<suffix>', *part_stem<suffix> for each part], e.g. suffix='.json'."""
    head = [f"client_data{suffix}"] if include_client_data else []
    return [*head, *[f"{stem}{suffix}" for stem in client_data_part_stems()]]


def client_data_derived_files() -> list[str]:
    """[client_data.json, client_data.yaml, *each part's .json, *each part's .yaml]."""
    stems = client_data_part_stems()
    return [
        "client_data.json",
        "client_data.yaml",
        *[f"{stem}.json" for stem in stems],
        *[f"{stem}.yaml" for stem in stems],
    ]


# System/reference CSVs (not per-client plan data). Defined here -- rather than
# in server/plan_data_files.py -- so that server_services/admin_service can
# import it without pulling in the src.server package (importing a submodule
# of a package always runs that package's __init__.py first, which registers
# admin_routes, which reads admin_service.ADMIN_PLAN_DATA_FILES back -- a
# circular import if admin_service ever depended on src.server.*).
SYSTEM_REFERENCE_FILES: list[str] = [
    "security_master.csv",
    "capital_market_assumptions.csv",
    "asset_correlations.csv",
    "schema.csv",
    "state_tax.csv",
    "tax_constants.csv",
    "tax_update_dashboard.csv",
]
