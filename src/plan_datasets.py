"""Flat datasets of the active plan (WP6): holdings, liabilities, HSA schedule, target
allocation, and the spending set (taxonomy, aliases, budget, budget lines, tier overrides:
WP6.3), and the spending recovery copies (WP6.3c). The functions live in ``active_plan`` (the one product module that opens the plan
file); this module is their import point for readers."""
from __future__ import annotations

from .active_plan import (
    active_dataset_rows,
    active_dataset_text,
    dataset_fingerprint,
    dataset_rows_for_input_dir,
    dataset_text_for_input_dir,
    keep_workspace_pre_recovery_copy,
    plan_path_for_workspace,
    restore_workspace_pre_recovery_copy,
    workspace_dataset_rows,
    workspace_recovery_seed_rows,
    write_active_dataset,
    write_workspace_dataset_rows,
    write_workspace_recovery_seed,
)
from .csv_exchange import FLAT_DATASET_FILES

# Legacy file name -> dataset name (``client_holdings.csv`` -> ``holdings``).
DATASET_BY_FILE: dict[str, str] = {file: name for name, file in FLAT_DATASET_FILES.items()}

__all__ = [
    "DATASET_BY_FILE",
    "active_dataset_rows",
    "active_dataset_text",
    "dataset_fingerprint",
    "dataset_rows_for_input_dir",
    "dataset_text_for_input_dir",
    "keep_workspace_pre_recovery_copy",
    "plan_path_for_workspace",
    "restore_workspace_pre_recovery_copy",
    "workspace_dataset_rows",
    "workspace_recovery_seed_rows",
    "write_active_dataset",
    "write_workspace_dataset_rows",
    "write_workspace_recovery_seed",
]
