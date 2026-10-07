"""ZIP metrics and top cities from ``reference.db`` (WP3.8).

Tables: ``zip_metrics`` and ``top_cities`` (built by ``tools/reference_slices/zip_data.py``).

``zip_table(ref=None)`` returns ``dict[str, ZipRecord]`` (ZCTA string -> ZipRecord),
matching the old ``src.housing.zip_screen.table.load_table()`` exactly.

``top_cities_rows(ref=None)`` returns ``list[dict[str, str]]`` (str dicts, the old
CSV shape); callers normalize population to int as they always did.
"""
from __future__ import annotations

from typing import Any

from src.housing.zip_screen.schema import ZipRecord

from ..ref_access import reference
from ..ref_data import RefData

ZIP_METRICS_COLUMNS = (
    "zcta", "state", "state_abbrev", "primary_place", "place_population",
    "zcta_population", "land_area_sqmi", "lat", "lon",
    "median_home_value", "state_median_home_value", "upi",
    "pctl_owner_occupied", "pctl_poverty", "pctl_non_student_poverty",
    "pctl_tenure", "pctl_tenure_nonstudent", "pctl_vacancy_deviation",
    "pctl_eviction_execution", "pctl_eviction_filing", "pctl_median_income",
)

TOP_CITIES_COLUMNS = ("city_id", "city", "state", "state_abbrev", "population", "anchor_zip")


def zip_table(ref: RefData | None = None) -> dict[str, ZipRecord]:
    """Every ZCTA in the snapshot, keyed by ZCTA string.

    Returns the same dict[zcta string -> ZipRecord] structure as the old
    src.housing.zip_screen.table.load_table(), fresh on every call.
    """
    ref = reference() if ref is None else ref
    sel = ", ".join(f'"{c}"' for c in ZIP_METRICS_COLUMNS)
    rows = ref.query(f'SELECT {sel} FROM "zip_metrics" ORDER BY seq')

    result = {}
    for row in rows:
        record = ZipRecord(
            zcta=row["zcta"],
            state=row["state"],
            lat=row["lat"],
            lon=row["lon"],
            state_abbrev=row["state_abbrev"],
            primary_place=row["primary_place"],
            place_population=row["place_population"],
            zcta_population=row["zcta_population"],
            land_area_sqmi=row["land_area_sqmi"],
            median_home_value=row["median_home_value"],
            state_median_home_value=row["state_median_home_value"],
            upi=row["upi"],
            pctl_owner_occupied=row["pctl_owner_occupied"],
            pctl_poverty=row["pctl_poverty"],
            pctl_non_student_poverty=row["pctl_non_student_poverty"],
            pctl_tenure=row["pctl_tenure"],
            pctl_tenure_nonstudent=row["pctl_tenure_nonstudent"],
            pctl_vacancy_deviation=row["pctl_vacancy_deviation"],
            pctl_eviction_execution=row["pctl_eviction_execution"],
            pctl_eviction_filing=row["pctl_eviction_filing"],
            pctl_median_income=row["pctl_median_income"],
        )
        result[record.zcta] = record

    return result


def top_cities_rows(ref: RefData | None = None) -> list[dict[str, Any]]:
    """Top cities list from bundled snapshot, in file order.

    Returns list of dicts with str values (matching the old CSV DictReader shape);
    callers cast population to int as they always did.
    """
    ref = reference() if ref is None else ref
    sel = ", ".join(f'"{c}"' for c in TOP_CITIES_COLUMNS)
    return [{c: row[c] for c in TOP_CITIES_COLUMNS} for row in ref.query(f'SELECT {sel} FROM "top_cities" ORDER BY seq')]
