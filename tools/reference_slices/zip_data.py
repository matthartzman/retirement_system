"""Slice: ZIP metrics + top cities -> tables ``zip_metrics``, ``top_cities`` (WP3.8).

Source: ``reference_src/zip_metrics.csv.gz`` (gzip CSV, 33,640 rows) and
``reference_src/top_cities.csv``. ZIP metrics are stored with typed floats/ints
(matching the ZipRecord schema); top cities are stored as strings (the getter
casts population to int). Both tables preserve file order via ``seq`` column.

Getters: ``src/stores/ref_getters/zip_data.py``.
"""
from __future__ import annotations

import csv
import gzip
from pathlib import Path

from ._source import read_csv

SOURCES = ("zip_metrics.csv.gz", "top_cities.csv")

# Columns from zip_metrics.csv.gz per src/housing/zip_screen/schema.py::COLUMNS
ZIP_METRICS_HEADER = (
    "zcta", "state", "state_abbrev", "primary_place", "place_population",
    "zcta_population", "land_area_sqmi", "lat", "lon",
    "median_home_value", "state_median_home_value", "upi",
    "pctl_owner_occupied", "pctl_poverty", "pctl_non_student_poverty",
    "pctl_tenure", "pctl_tenure_nonstudent", "pctl_vacancy_deviation",
    "pctl_eviction_execution", "pctl_eviction_filing", "pctl_median_income",
)

TOP_CITIES_HEADER = ("city_id", "city", "state", "state_abbrev", "population", "anchor_zip")

# Field groups matching src/housing/zip_screen/table.py::_row_to_record
_INT_FIELDS = ('place_population', 'zcta_population')
_FLOAT_FIELDS = ('lat', 'lon', 'land_area_sqmi', 'upi')
_OPTIONAL_FLOAT_FIELDS = (
    'median_home_value', 'state_median_home_value',
    'pctl_owner_occupied', 'pctl_poverty', 'pctl_non_student_poverty',
    'pctl_tenure', 'pctl_tenure_nonstudent', 'pctl_vacancy_deviation',
    'pctl_eviction_execution', 'pctl_eviction_filing', 'pctl_median_income',
)


def _opt_float(raw: str | None) -> float | None:
    """Empty cell means 'no data for this metric', which is NOT zero."""
    if raw is None or raw.strip() == '':
        return None
    return float(raw)


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


def build(src: Path) -> dict[str, tuple[list[str], list[tuple]]]:
    """Build zip_metrics and top_cities tables from gzipped CSV and CSV sources."""
    tables = {}

    # ZIP metrics from gzipped CSV
    with gzip.open(src / "zip_metrics.csv.gz", 'rt', encoding='utf-8', newline='') as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames is not None
        # Verify header matches expected columns
        expected_cols = set(ZIP_METRICS_HEADER)
        actual_cols = set(reader.fieldnames)
        if actual_cols != expected_cols:
            raise ValueError(f"zip_metrics.csv header mismatch. Expected {expected_cols}, got {actual_cols}")

        rows = [
            (seq, *_zip_metrics_row_to_record(row))
            for seq, row in enumerate(reader)
        ]

    tables["zip_metrics"] = (["seq", *ZIP_METRICS_HEADER], rows)

    # Top cities from CSV
    rows = [
        (seq, *(str(r.get(c) or '').strip() for c in TOP_CITIES_HEADER))
        for seq, r in enumerate(read_csv(src / "top_cities.csv", TOP_CITIES_HEADER))
    ]

    tables["top_cities"] = (["seq", *TOP_CITIES_HEADER], rows)

    return tables
