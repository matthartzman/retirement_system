"""Flat datasets of the active plan (WP6): holdings, liabilities, HSA schedule, target
allocation. The functions live in ``active_plan`` (the one product module that opens the plan
file); this module is their import point for readers."""
from __future__ import annotations

from .active_plan import (
    active_dataset_text,
    dataset_fingerprint,
    dataset_text_for_input_dir,
    write_active_dataset,
)
from .csv_exchange import FLAT_DATASET_FILES

# Legacy file name -> dataset name (``client_holdings.csv`` -> ``holdings``).
DATASET_BY_FILE: dict[str, str] = {file: name for name, file in FLAT_DATASET_FILES.items()}

__all__ = [
    "DATASET_BY_FILE",
    "active_dataset_text",
    "dataset_fingerprint",
    "dataset_text_for_input_dir",
    "write_active_dataset",
]
