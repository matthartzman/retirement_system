"""Test fixture helper for ZIP metrics tests.

Builds a small reference.db containing only zip_metrics table from
tests/fixtures/zip_metrics_sample.csv for testing without accessing
the full reference database.
"""
from __future__ import annotations

import csv
import gzip
import tempfile
from pathlib import Path

from src.stores.ref_data import RefData, build
from src.stores.ref_access import set_reference_for_tests


# Import the row converter from the slice builder
def _opt_float(raw: str | None) -> float | None:
    """Empty cell means 'no data for this metric', which is NOT zero."""
    if raw is None or raw.strip() == '':
        return None
    return float(raw)


# Field groups matching src/housing/zip_screen/table.py
_INT_FIELDS = ('place_population', 'zcta_population')
_FLOAT_FIELDS = ('lat', 'lon', 'land_area_sqmi', 'upi')
_OPTIONAL_FLOAT_FIELDS = (
    'median_home_value', 'state_median_home_value',
    'pctl_owner_occupied', 'pctl_poverty', 'pctl_non_student_poverty',
    'pctl_tenure', 'pctl_tenure_nonstudent', 'pctl_vacancy_deviation',
    'pctl_eviction_execution', 'pctl_eviction_filing', 'pctl_median_income',
)

ZIP_METRICS_HEADER = (
    "zcta", "state", "state_abbrev", "primary_place", "place_population",
    "zcta_population", "land_area_sqmi", "lat", "lon",
    "median_home_value", "state_median_home_value", "upi",
    "pctl_owner_occupied", "pctl_poverty", "pctl_non_student_poverty",
    "pctl_tenure", "pctl_tenure_nonstudent", "pctl_vacancy_deviation",
    "pctl_eviction_execution", "pctl_eviction_filing", "pctl_median_income",
)


def _zip_metrics_row_to_record(row: dict[str, str]) -> tuple:
    """Convert a CSV row to typed values matching ZipRecord structure."""
    values = []
    for field in ZIP_METRICS_HEADER:
        if field in _INT_FIELDS:
            values.append(int(float(row.get(field) or 0)))
        elif field in _FLOAT_FIELDS:
            values.append(float(row.get(field) or 0.0))
        elif field in _OPTIONAL_FLOAT_FIELDS:
            values.append(_opt_float(row.get(field)))
        else:
            values.append(str(row.get(field) or '').strip())
    return tuple(values)


def build_zip_test_db(sample_csv_path: str | Path) -> RefData:
    """Build a reference.db for tests: every shipped table, with zip_metrics replaced by the sample.

    Args:
        sample_csv_path: Path to the sample CSV file (e.g. tests/fixtures/zip_metrics_sample.csv)

    Returns:
        RefData instance pointing to a temporary test database
    """
    sample_path = Path(sample_csv_path)

    # Read the sample CSV and convert to typed rows
    with open(sample_path, 'r', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        rows_sample = [
            (seq, *_zip_metrics_row_to_record(row))
            for seq, row in enumerate(reader or [])
        ]

    # Every shipped table (the engine also reads tax law, CMAs, ...), with the
    # national zip_metrics table swapped for the small sample.
    from src.stores.ref_access import shipped_reference_path
    tables = {}
    with RefData.open(shipped_reference_path(), verify=False) as shipped:
        for name in shipped.tables():
            if name == "zip_metrics":
                continue
            rows = shipped.table(name)
            cols = list(rows[0]) if rows else [c[1] for c in shipped.query(f'PRAGMA table_info("{name}")')]
            tables[name] = (cols, [tuple(r.values()) for r in rows])
    tables["zip_metrics"] = (["seq", *ZIP_METRICS_HEADER], rows_sample)

    # Create a temporary database file
    temp_dir = tempfile.mkdtemp(prefix="zip_test_db_")
    temp_db_path = Path(temp_dir) / "test_reference.db"

    # Build the database
    build(temp_db_path, tables, data_version="test")

    # Open and return the RefData
    return RefData.open(temp_db_path, verify=True)


def use_zip_test_db(sample_csv_path: str | Path) -> None:
    """Set the test reference database for ZIP metrics tests.

    Call this in a test fixture to switch to a small test database.
    Call set_reference_for_tests(None) in cleanup to restore the default.

    Args:
        sample_csv_path: Path to the sample CSV file
    """
    ref = build_zip_test_db(sample_csv_path)
    set_reference_for_tests(ref.path)
