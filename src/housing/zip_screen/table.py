"""Load the bundled ZCTA snapshot. The only module that touches the file.

The snapshot is a build-time artifact (scripts/build_zip_metrics.py): every
percentile it carries was computed against the full national distribution, so
nothing at runtime needs distribution data. Reading it is a stdlib csv+gzip
parse -- no pandas, no network, consistent with the rest of the planner.
"""
from __future__ import annotations

import csv
import gzip
import os

from .schema import ZipRecord

_CACHE: dict[str, dict[str, ZipRecord]] = {}

_INT_FIELDS = ('place_population', 'zcta_population')
_FLOAT_FIELDS = ('lat', 'lon', 'land_area_sqmi', 'upi')
_OPTIONAL_FLOAT_FIELDS = (
    'median_home_value', 'state_median_home_value',
    'pctl_owner_occupied', 'pctl_poverty', 'pctl_non_student_poverty',
    'pctl_tenure', 'pctl_tenure_nonstudent', 'pctl_vacancy_deviation',
    'pctl_eviction_execution', 'pctl_eviction_filing', 'pctl_median_income',
)


def default_table_path() -> str:
    """The bundled snapshot shipped with the package."""
    return os.path.join(os.path.dirname(__file__), 'data', 'zip_metrics.csv.gz')


def clear_cache() -> None:
    """Drop the in-process table cache (tests, and snapshot refreshes)."""
    _CACHE.clear()


def _opt_float(raw: str | None) -> float | None:
    """Empty cell means "no data for this metric", which is NOT zero -- see
    quality.py's coverage renormalization."""
    if raw is None or raw.strip() == '':
        return None
    return float(raw)


def _row_to_record(row: dict[str, str]) -> ZipRecord:
    kwargs: dict[str, object] = {
        'zcta': str(row['zcta']).strip(),
        'state': str(row.get('state', '') or '').strip(),
        'state_abbrev': str(row.get('state_abbrev', '') or '').strip(),
        'primary_place': str(row.get('primary_place', '') or '').strip(),
    }
    for f in _INT_FIELDS:
        kwargs[f] = int(float(row.get(f) or 0))
    for f in _FLOAT_FIELDS:
        kwargs[f] = float(row.get(f) or 0.0)
    for f in _OPTIONAL_FLOAT_FIELDS:
        kwargs[f] = _opt_float(row.get(f))
    return ZipRecord(**kwargs)  # type: ignore[arg-type]


def load_table(path: str | None = None) -> dict[str, ZipRecord]:
    """Every ZCTA in the snapshot, keyed by ZCTA string. Cached per path."""
    resolved = path or default_table_path()
    if resolved in _CACHE:
        return _CACHE[resolved]
    if not os.path.exists(resolved):
        raise FileNotFoundError(
            f'zip_metrics snapshot not found at {resolved!r}; '
            'run scripts/build_zip_metrics.py to create it'
        )
    opener = gzip.open if resolved.endswith('.gz') else open
    with opener(resolved, 'rt', encoding='utf-8', newline='') as fh:
        table = {r.zcta: r for r in (_row_to_record(row) for row in csv.DictReader(fh))}
    _CACHE[resolved] = table
    return table
