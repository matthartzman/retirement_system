"""Load the bundled ZCTA snapshot from the reference database.

The snapshot is a reference dataset (built by tools/build_reference_db.py from
reference_src/zip_metrics.csv.gz): every percentile it carries was computed
against the full national distribution, so nothing at runtime needs distribution
data. The getter (src/stores/ref_getters/zip_data.py) loads from reference.db.
"""
from __future__ import annotations

from .schema import ZipRecord

from src.stores.ref_getters.zip_data import zip_table

_CACHE: dict[str, dict[str, ZipRecord]] = {}


def clear_cache() -> None:
    """Drop the in-process table cache (tests, and snapshot refreshes)."""
    _CACHE.clear()


def load_table() -> dict[str, ZipRecord]:
    """Every ZCTA in the snapshot, keyed by ZCTA string. Cached per process.

    Data is loaded from the reference database via the getter.
    """
    cache_key = "__default__"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    # Load from the reference database through the getter
    table = zip_table()
    _CACHE[cache_key] = table
    return table
