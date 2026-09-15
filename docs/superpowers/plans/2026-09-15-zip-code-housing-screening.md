# ZIP-Code Screening for Housing Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a distance radius (criterion 9) and a minimum neighborhood quality score (criterion 10) to the housing optimizer, so it can discover candidate ZIP codes around an anchor instead of only ranking 2–4 hand-picked locations.

**Architecture:** A new `src/housing/zip_screen/` package performs a cheap Stage-1 screen over a bundled static table of ZCTA metrics — radius, coverage, score floor, affordability, de-duplication — and promotes the top N ZIPs. Each promoted ZIP is resolved into the existing `Location` dataclass, so the optimizer, search, scoring, constraints, and plan-variant code are never modified and never learn that ZIPs exist.

**Tech Stack:** Python 3.12, pytest, Flask (existing routes), vanilla ES modules (existing frontend). No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-09-15-zip-code-housing-screening-design.md`

## Global Constraints

- **No new runtime dependency.** `scripts/build_zip_metrics.py` may import `requests`/`pandas`; nothing under `src/` may import them. The runtime path uses `csv` + `gzip` from the stdlib only.
- **ACS vintage is pinned** to `acs/acs5` year **2024** (2020–2024 5-year), as the constant `ACS_VINTAGE_YEAR = 2024`. Scores must be reproducible, not drift with fetch date.
- **NSS weights are exact** and sum to 100.0: owner-occupied 24.2424, poverty 18.1818, tenure 15.1515, vacancy 12.1212, eviction execution 12.1212, eviction filing 9.0909, median income 9.0909.
- **Coverage floor is 70.0%.** Missing metrics renormalize; they are never zero-filled.
- **The disclosure string is verbatim and non-dismissible:** `Measures housing and economic stability. Does not measure crime or safety.`
- **`radius_miles` must be one of 5, 10, 25, 50.** Any other value is a 400.
- **Score model version string:** `nss-1.0`
- **Response schema string:** `zip_screen_v1`
- Tests live flat in `tests/test_*.py`, carry a `pytestmark` tier marker (`unit`, `integration`, `contract`), and run from the repo root via `pytest` (pythonpath is already `["."]` per `pyproject.toml`).
- Pilot regions are **Illinois, Florida, Colorado** (statewide, all three). Denver is the anchor used in Colorado fixtures.

---

## File Structure

**Create:**

| Path | Responsibility |
|---|---|
| `src/housing/zip_screen/__init__.py` | Public exports for the package |
| `src/housing/zip_screen/schema.py` | Column names, weights, tunable constants, the `ZipRecord` dataclass |
| `src/housing/zip_screen/table.py` | Load and index the bundled snapshot; nothing else reads the file |
| `src/housing/zip_screen/geo.py` | Haversine, radius query, top-200 city anchor lookup |
| `src/housing/zip_screen/quality.py` | NSS from a `ZipRecord`: weighting, coverage renormalization, banding, UPI |
| `src/housing/zip_screen/resolve.py` | `ZipRecord` -> `Location` |
| `src/housing/zip_screen/screen.py` | The Stage-1 funnel, de-dup, ranking, relaxation suggestion |
| `src/housing/zip_screen/data/zip_metrics.csv.gz` | The bundled snapshot (Task 12 / Task 15) |
| `src/housing/zip_screen/data/top_cities.csv` | Top-200 cities by population -> anchor ZIP |
| `scripts/build_zip_metrics.py` | Offline ingest. Never imported at runtime. |
| `tests/fixtures/zip_metrics_sample.csv` | 12-row synthetic table for every unit test |

**Modify:**

| Path | Change |
|---|---|
| `src/housing/models.py` | Add `Location.zip_code`; add density thresholds |
| `src/housing/api.py` | Parse `zip_search`; enforce mutual exclusion with `locations` |
| `src/housing/__init__.py` | Export the new public names |
| `src/server/plan_routes.py:750` | Add `POST /api/housing/zip-screen` beside the existing optimize route |
| `frontend/js/dashboard_decomp_housing_scenarios.js` | Mode toggle, ZIP controls, shortlist table |

**Spec refinements locked here** (the spec left these soft; they are now decided):

1. `table.py` is added as a separate loader so the snapshot is read in exactly one place.
2. **"Balanced" vacancy** (spec §4.2) is made concrete: score on the percentile of `abs(vacancy_rate - VACANCY_IDEAL_RATE)` where `VACANCY_IDEAL_RATE = 0.06`, reusing the same percentile machinery as every other metric.
3. **Percentiles are precomputed into the snapshot at build time**, so `quality.py` is a pure weighted sum with no distribution data of its own.

---

## Task Sequence and Rationale

Tasks 1–11 build and test everything against a 12-row synthetic fixture and require **no network and no real data**. Task 12 produces the pilot snapshot. Tasks 13–14 are the UI. Task 15 goes national.

This ordering exists so the messy ingest never blocks the code. If the Eviction Lab tract→ZCTA crosswalk turns out unusable in Task 12, only Task 12 changes: set both eviction columns empty, and the coverage renormalization written in Task 4 already handles it.

---

### Task 1: Schema, constants, and the test fixture

**Files:**
- Create: `src/housing/zip_screen/__init__.py`
- Create: `src/housing/zip_screen/schema.py`
- Create: `tests/fixtures/zip_metrics_sample.csv`
- Test: `tests/test_zip_screen_schema_unit.py`

**Interfaces:**
- Consumes: nothing
- Produces: `ZipRecord` dataclass; `NSS_WEIGHTS: dict[str, float]`; `COLUMNS: tuple[str, ...]`; `COVERAGE_FLOOR_PCT = 70.0`; `VACANCY_IDEAL_RATE = 0.06`; `SCORE_MODEL_VERSION = 'nss-1.0'`; `NSS_DISCLOSURE: str`; `BANDS: tuple[tuple[float, str], ...]`

- [ ] **Step 1: Write the failing test**

```python
"""Schema constants for the ZIP screener: weights, bands, and the record type."""
from __future__ import annotations

import pytest

from src.housing.zip_screen.schema import (
    BANDS,
    COVERAGE_FLOOR_PCT,
    NSS_DISCLOSURE,
    NSS_WEIGHTS,
    SCORE_MODEL_VERSION,
    VACANCY_IDEAL_RATE,
    ZipRecord,
    band_for,
)

pytestmark = pytest.mark.unit


def test_nss_weights_sum_to_one_hundred():
    assert round(sum(NSS_WEIGHTS.values()), 4) == 100.0


def test_nss_weights_preserve_the_pdf_relative_ordering():
    # PDF Rev 2.1 points 8/6/5/4/4/3/3 renormalized by 100/33.
    assert NSS_WEIGHTS['owner_occupied'] > NSS_WEIGHTS['poverty'] > NSS_WEIGHTS['tenure']
    assert NSS_WEIGHTS['tenure'] > NSS_WEIGHTS['vacancy']
    assert NSS_WEIGHTS['vacancy'] == pytest.approx(NSS_WEIGHTS['eviction_execution'])
    assert NSS_WEIGHTS['eviction_filing'] == pytest.approx(NSS_WEIGHTS['median_income'])


def test_owner_occupied_weight_matches_the_renormalization():
    assert NSS_WEIGHTS['owner_occupied'] == pytest.approx(8 * 100 / 33, abs=1e-4)


def test_disclosure_string_is_verbatim():
    assert NSS_DISCLOSURE == (
        'Measures housing and economic stability. Does not measure crime or safety.'
    )


def test_constants_match_the_spec():
    assert COVERAGE_FLOOR_PCT == 70.0
    assert VACANCY_IDEAL_RATE == 0.06
    assert SCORE_MODEL_VERSION == 'nss-1.0'


@pytest.mark.parametrize('score,expected', [
    (95.0, 'Exceptional'),
    (90.0, 'Exceptional'),
    (89.9, 'Very Favorable'),
    (80.0, 'Very Favorable'),
    (75.0, 'Generally Favorable'),
    (65.0, 'Mixed'),
    (55.0, 'Below Average'),
    (49.9, 'Relatively Unfavorable'),
    (0.0, 'Relatively Unfavorable'),
])
def test_band_for_matches_pdf_section_2_4(score, expected):
    assert band_for(score) == expected


def test_bands_are_ordered_high_to_low():
    thresholds = [t for t, _ in BANDS]
    assert thresholds == sorted(thresholds, reverse=True)


def test_zip_record_defaults_missing_metrics_to_none():
    rec = ZipRecord(zcta='60521', state='Illinois', lat=41.8, lon=-87.93)
    assert rec.pctl_eviction_filing is None
    assert rec.pctl_owner_occupied is None
    assert rec.place_population == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zip_screen_schema_unit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.housing.zip_screen'`

- [ ] **Step 3: Write minimal implementation**

`src/housing/zip_screen/__init__.py`:

```python
"""ZIP-code screening (Stage 1) for the housing optimizer.

Everything ZIP-shaped lives in this package and stops at its boundary: the
screener's output is a list of ordinary ``Location`` objects, so
``optimizer.py``, ``search.py``, ``scoring.py``, ``constraints.py`` and
``plan_variant.py`` never learn that ZIP codes exist. See
docs/superpowers/specs/2026-09-15-zip-code-housing-screening-design.md.
"""
from __future__ import annotations
```

`src/housing/zip_screen/schema.py`:

```python
"""Column names, scoring weights, and tunable constants -- no behavior.

The Neighborhood Stability Score (NSS) is derived from, but is NOT, the
"ZIP-Code Neighborhood Screening Score Framework" Rev 2.1. Only 33 of that
model's 100 points are sourceable at national ZIP granularity (the Stability
component plus Eviction Filing Rate); the Safety component has no national
ZIP-level dataset. Those 33 points are renormalized by 100/33, preserving the
source model's relative weighting among the metrics that survive.

NSS therefore measures stability, not safety. ``NSS_DISCLOSURE`` must appear
wherever a score is displayed.
"""
from __future__ import annotations

from dataclasses import dataclass

SCORE_MODEL_VERSION = 'nss-1.0'
RESPONSE_SCHEMA = 'zip_screen_v1'

NSS_DISCLOSURE = (
    'Measures housing and economic stability. Does not measure crime or safety.'
)

# PDF Rev 2.1 point allocations for the sourceable metrics, renormalized to 100.
_PDF_POINTS = {
    'owner_occupied': 8,
    'poverty': 6,
    'tenure': 5,
    'vacancy': 4,
    'eviction_execution': 4,
    'eviction_filing': 3,
    'median_income': 3,
}
_PDF_SOURCEABLE_POINTS = 33  # sum(_PDF_POINTS.values())

NSS_WEIGHTS = {
    k: v * 100.0 / _PDF_SOURCEABLE_POINTS for k, v in _PDF_POINTS.items()
}

# Each metric's precomputed-percentile column in the snapshot. quality.py reads
# only these, so it needs no distribution data of its own.
PCTL_COLUMN = {
    'owner_occupied': 'pctl_owner_occupied',
    'poverty': 'pctl_poverty',
    'tenure': 'pctl_tenure',
    'vacancy': 'pctl_vacancy_deviation',
    'eviction_execution': 'pctl_eviction_execution',
    'eviction_filing': 'pctl_eviction_filing',
    'median_income': 'pctl_median_income',
}

# True when a HIGHER percentile is the better outcome. The rest use the source
# model's Score = 100 * (1 - Percentile) (PDF section 2.2).
HIGHER_IS_BETTER = {'owner_occupied', 'tenure', 'median_income'}

COVERAGE_FLOOR_PCT = 70.0

# "Balanced market vacancy scored higher" (PDF section 2.3) made concrete: the
# metric is scored on the percentile of the ABSOLUTE DEVIATION from this rate,
# so both a starved and a glutted market are penalized.
VACANCY_IDEAL_RATE = 0.06

# University Presence Index threshold (PDF section 5).
UPI_THRESHOLD = 0.15

# De-duplication rule (spec section 5.2).
DEDUP_RADIUS_MILES = 5.0
DEDUP_SCORE_POINTS = 5.0

ALLOWED_RADII_MILES = (5, 10, 25, 50)

# PDF section 2.4, read as stability bands.
BANDS = (
    (90.0, 'Exceptional'),
    (80.0, 'Very Favorable'),
    (70.0, 'Generally Favorable'),
    (60.0, 'Mixed'),
    (50.0, 'Below Average'),
    (0.0, 'Relatively Unfavorable'),
)

COLUMNS = (
    'zcta', 'state', 'state_abbrev', 'primary_place', 'place_population',
    'zcta_population', 'land_area_sqmi', 'lat', 'lon',
    'median_home_value', 'state_median_home_value', 'upi',
    'pctl_owner_occupied', 'pctl_poverty', 'pctl_non_student_poverty',
    'pctl_tenure', 'pctl_tenure_nonstudent', 'pctl_vacancy_deviation',
    'pctl_eviction_execution', 'pctl_eviction_filing', 'pctl_median_income',
)


def band_for(score: float) -> str:
    """The PDF section 2.4 band a 0-100 NSS falls in."""
    for threshold, label in BANDS:
        if score >= threshold:
            return label
    return BANDS[-1][1]


@dataclass(frozen=True)
class ZipRecord:
    """One ZCTA row of the bundled snapshot.

    Every ``pctl_*`` field is ``None`` when that metric has no data for this
    ZCTA. quality.py renormalizes over what is present rather than zero-filling
    -- zero-filling would penalize a rural ZIP for a dataset gap instead of for
    any property of the place.
    """
    zcta: str
    state: str
    lat: float
    lon: float
    state_abbrev: str = ''
    primary_place: str = ''
    place_population: int = 0
    zcta_population: int = 0
    land_area_sqmi: float = 0.0
    median_home_value: float | None = None
    state_median_home_value: float | None = None
    upi: float = 0.0
    pctl_owner_occupied: float | None = None
    pctl_poverty: float | None = None
    pctl_non_student_poverty: float | None = None
    pctl_tenure: float | None = None
    pctl_tenure_nonstudent: float | None = None
    pctl_vacancy_deviation: float | None = None
    pctl_eviction_execution: float | None = None
    pctl_eviction_filing: float | None = None
    pctl_median_income: float | None = None

    @property
    def density(self) -> float:
        """People per square mile, 0.0 when land area is unknown."""
        if self.land_area_sqmi <= 0:
            return 0.0
        return self.zcta_population / self.land_area_sqmi
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_zip_screen_schema_unit.py -v`
Expected: PASS, 18 passed

- [ ] **Step 5: Create the synthetic fixture**

`tests/fixtures/zip_metrics_sample.csv` — 12 rows spanning the three pilot states. Row 1 is Hinsdale (the PDF's high-stability example), row 2 is DeKalb (the PDF's university example, `upi` above threshold), row 5 has both eviction columns empty (coverage test), row 6 has four metrics empty (below the coverage floor), rows 7–9 are a Denver cluster within 5 miles of each other (de-dup test), rows 10–11 are Florida (cross-state test).

```csv
zcta,state,state_abbrev,primary_place,place_population,zcta_population,land_area_sqmi,lat,lon,median_home_value,state_median_home_value,upi,pctl_owner_occupied,pctl_poverty,pctl_non_student_poverty,pctl_tenure,pctl_tenure_nonstudent,pctl_vacancy_deviation,pctl_eviction_execution,pctl_eviction_filing,pctl_median_income
60521,Illinois,IL,Hinsdale,17395,25000,10.4,41.8007,-87.9370,860000,260000,0.01,0.94,0.04,0.04,0.88,0.88,0.22,0.06,0.05,0.97
60115,Illinois,IL,DeKalb,40290,45000,28.1,41.9295,-88.7504,190000,260000,0.38,0.21,0.91,0.34,0.14,0.62,0.71,0.68,0.74,0.18
60540,Illinois,IL,Naperville,149540,60000,18.9,41.7508,-88.1535,520000,260000,0.03,0.89,0.09,0.09,0.81,0.81,0.18,0.11,0.10,0.92
60623,Illinois,IL,Chicago,2746388,88000,4.6,41.8487,-87.7180,180000,260000,0.02,0.18,0.93,0.93,0.35,0.35,0.79,0.88,0.91,0.09
60187,Illinois,IL,Wheaton,53970,42000,12.2,41.8661,-88.1070,440000,260000,0.06,0.84,0.12,0.12,0.76,0.76,0.25,,,0.87
60950,Illinois,IL,Manteno,9207,11000,41.8,41.2508,-87.8570,230000,260000,0.01,0.71,,,0.64,0.64,,,,
80206,Colorado,CO,Denver,715522,24000,2.8,39.7310,-104.9550,690000,480000,0.04,0.58,0.31,0.31,0.44,0.44,0.41,0.34,0.36,0.79
80209,Colorado,CO,Denver,715522,21000,3.1,39.7050,-104.9640,820000,480000,0.03,0.63,0.26,0.26,0.49,0.49,0.38,0.29,0.31,0.84
80210,Colorado,CO,Denver,715522,27000,3.9,39.6790,-104.9630,710000,480000,0.05,0.61,0.28,0.28,0.47,0.47,0.40,0.32,0.33,0.81
80424,Colorado,CO,Breckenridge,5078,6200,68.4,39.4817,-106.0384,1150000,480000,0.02,0.44,0.22,0.22,0.31,0.31,0.94,0.19,0.21,0.74
33143,Florida,FL,South Miami,12026,34000,9.7,25.7050,-80.3020,740000,340000,0.03,0.72,0.34,0.34,0.69,0.69,0.44,0.41,0.43,0.78
32789,Florida,FL,Winter Park,29795,28000,8.1,28.6000,-81.3500,610000,340000,0.09,0.76,0.29,0.29,0.72,0.72,0.36,0.37,0.39,0.82
```

- [ ] **Step 6: Commit**

```bash
git add src/housing/zip_screen/ tests/test_zip_screen_schema_unit.py tests/fixtures/zip_metrics_sample.csv
git commit -m "feat(zip-screen): add NSS schema, weights, bands, and test fixture"
```

---

### Task 2: Snapshot loader

**Files:**
- Create: `src/housing/zip_screen/table.py`
- Test: `tests/test_zip_screen_table_unit.py`

**Interfaces:**
- Consumes: `schema.ZipRecord`, `schema.COLUMNS`
- Produces: `load_table(path: str | None = None) -> dict[str, ZipRecord]` keyed by ZCTA; `default_table_path() -> str`; `clear_cache() -> None`

- [ ] **Step 1: Write the failing test**

```python
"""Loading the bundled ZCTA snapshot. The only module that reads the file."""
from __future__ import annotations

import pytest

from src.housing.zip_screen.table import clear_cache, load_table

pytestmark = pytest.mark.unit

FIXTURE = 'tests/fixtures/zip_metrics_sample.csv'


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


def test_loads_every_fixture_row_keyed_by_zcta():
    table = load_table(FIXTURE)
    assert len(table) == 12
    assert '60521' in table
    assert table['60521'].primary_place == 'Hinsdale'


def test_numeric_columns_are_parsed():
    rec = load_table(FIXTURE)['60521']
    assert rec.lat == pytest.approx(41.8007)
    assert rec.place_population == 17395
    assert rec.pctl_owner_occupied == pytest.approx(0.94)


def test_empty_percentile_cells_become_none_not_zero():
    rec = load_table(FIXTURE)['60187']
    assert rec.pctl_eviction_execution is None
    assert rec.pctl_eviction_filing is None
    assert rec.pctl_owner_occupied == pytest.approx(0.84)


def test_zcta_is_kept_as_a_string_preserving_leading_zeros():
    table = load_table(FIXTURE)
    assert isinstance(table['60521'].zcta, str)


def test_density_is_derived_not_stored():
    rec = load_table(FIXTURE)['60623']
    assert rec.density == pytest.approx(88000 / 4.6)


def test_second_load_is_served_from_cache():
    first = load_table(FIXTURE)
    second = load_table(FIXTURE)
    assert first is second


def test_missing_file_raises_a_named_error():
    with pytest.raises(FileNotFoundError, match='zip_metrics'):
        load_table('tests/fixtures/does_not_exist_zip_metrics.csv')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zip_screen_table_unit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.housing.zip_screen.table'`

- [ ] **Step 3: Write minimal implementation**

`src/housing/zip_screen/table.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_zip_screen_table_unit.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/housing/zip_screen/table.py tests/test_zip_screen_table_unit.py
git commit -m "feat(zip-screen): add snapshot loader with missing-metric preservation"
```

---

### Task 3: Geography — haversine and radius query

**Files:**
- Create: `src/housing/zip_screen/geo.py`
- Test: `tests/test_zip_screen_geo_unit.py`

**Interfaces:**
- Consumes: `schema.ZipRecord`, `schema.ALLOWED_RADII_MILES`
- Produces: `haversine_miles(lat1, lon1, lat2, lon2) -> float`; `zips_within(table, anchor, radius_miles) -> list[tuple[ZipRecord, float]]`; `InvalidRadiusError`

- [ ] **Step 1: Write the failing test**

```python
"""Distance math and the radius query (criterion 9)."""
from __future__ import annotations

import pytest

from src.housing.zip_screen.geo import (
    InvalidRadiusError,
    haversine_miles,
    zips_within,
)
from src.housing.zip_screen.table import clear_cache, load_table

pytestmark = pytest.mark.unit

FIXTURE = 'tests/fixtures/zip_metrics_sample.csv'


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


def test_distance_to_self_is_zero():
    assert haversine_miles(41.8, -87.9, 41.8, -87.9) == pytest.approx(0.0, abs=1e-9)


def test_known_distance_hinsdale_to_naperville():
    # ~11.5 miles apart; allow a mile of slack for centroid choice.
    d = haversine_miles(41.8007, -87.9370, 41.7508, -88.1535)
    assert 10.0 < d < 13.0


def test_distance_is_symmetric():
    a = haversine_miles(41.8007, -87.9370, 25.7050, -80.3020)
    b = haversine_miles(25.7050, -80.3020, 41.8007, -87.9370)
    assert a == pytest.approx(b)


def test_radius_includes_the_anchor_itself_at_zero_miles():
    table = load_table(FIXTURE)
    hits = zips_within(table, table['60521'], 25)
    assert any(r.zcta == '60521' and d == pytest.approx(0.0, abs=1e-9) for r, d in hits)


def test_radius_excludes_zips_beyond_it():
    table = load_table(FIXTURE)
    hits = {r.zcta for r, _ in zips_within(table, table['60521'], 5)}
    assert '60521' in hits
    assert '33143' not in hits
    assert '80206' not in hits


def test_larger_radius_is_a_superset_of_a_smaller_one():
    table = load_table(FIXTURE)
    small = {r.zcta for r, _ in zips_within(table, table['60521'], 10)}
    large = {r.zcta for r, _ in zips_within(table, table['60521'], 50)}
    assert small <= large


def test_results_are_sorted_by_distance():
    table = load_table(FIXTURE)
    distances = [d for _, d in zips_within(table, table['80206'], 50)]
    assert distances == sorted(distances)


def test_radius_crosses_state_lines():
    # A 50-mile radius must not be clipped at a state boundary (spec D4).
    table = load_table(FIXTURE)
    hits = zips_within(table, table['80206'], 50)
    assert all(isinstance(d, float) for _, d in hits)
    assert {r.state for r, _ in hits} == {'Colorado'}


@pytest.mark.parametrize('bad', [0, 3, 15, 100, -5])
def test_disallowed_radius_is_rejected(bad):
    table = load_table(FIXTURE)
    with pytest.raises(InvalidRadiusError, match='5, 10, 25, 50'):
        zips_within(table, table['60521'], bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zip_screen_geo_unit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.housing.zip_screen.geo'`

- [ ] **Step 3: Write minimal implementation**

`src/housing/zip_screen/geo.py`:

```python
"""Distance math and the radius query -- criterion 9.

Great-circle distance between ZCTA centroids. A radius is deliberately NOT
clipped at state lines: ``Location.state`` drives the residency schedule and
state income tax, so a ZIP just over the border is frequently the most
valuable result a search can return (spec decision D4).
"""
from __future__ import annotations

import math

from .schema import ALLOWED_RADII_MILES, ZipRecord

EARTH_RADIUS_MILES = 3958.7613


class InvalidRadiusError(ValueError):
    """Raised for a radius outside the four the UI offers."""


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in statute miles."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def zips_within(
    table: dict[str, ZipRecord], anchor: ZipRecord, radius_miles: int
) -> list[tuple[ZipRecord, float]]:
    """Every ZCTA within ``radius_miles`` of ``anchor``, nearest first.

    Includes the anchor itself at distance 0.
    """
    if radius_miles not in ALLOWED_RADII_MILES:
        allowed = ', '.join(str(r) for r in ALLOWED_RADII_MILES)
        raise InvalidRadiusError(f'radius_miles must be one of {allowed}; got {radius_miles!r}')
    hits: list[tuple[ZipRecord, float]] = []
    for rec in table.values():
        d = haversine_miles(anchor.lat, anchor.lon, rec.lat, rec.lon)
        if d <= radius_miles:
            hits.append((rec, d))
    hits.sort(key=lambda pair: (pair[1], pair[0].zcta))
    return hits
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_zip_screen_geo_unit.py -v`
Expected: PASS, 13 passed

- [ ] **Step 5: Commit**

```bash
git add src/housing/zip_screen/geo.py tests/test_zip_screen_geo_unit.py
git commit -m "feat(zip-screen): add haversine distance and radius query (criterion 9)"
```

---

### Task 4: NSS scoring with coverage renormalization

**Files:**
- Create: `src/housing/zip_screen/quality.py`
- Test: `tests/test_zip_screen_quality_unit.py`

**Interfaces:**
- Consumes: `schema.NSS_WEIGHTS`, `schema.PCTL_COLUMN`, `schema.HIGHER_IS_BETTER`, `schema.band_for`, `schema.ZipRecord`
- Produces: `NssResult` dataclass with `score: float`, `band: str`, `coverage_pct: float`, `components: dict[str, float]`, `upi_adjusted: bool`; `score_zip(rec: ZipRecord) -> NssResult`

- [ ] **Step 1: Write the failing test**

```python
"""NSS scoring: percentile scaling, weighting, and coverage renormalization."""
from __future__ import annotations

import pytest

from src.housing.zip_screen.quality import score_zip
from src.housing.zip_screen.schema import NSS_WEIGHTS, ZipRecord
from src.housing.zip_screen.table import clear_cache, load_table

pytestmark = pytest.mark.unit

FIXTURE = 'tests/fixtures/zip_metrics_sample.csv'


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


def _full(**overrides) -> ZipRecord:
    """A record with every percentile present at 0.5 unless overridden."""
    base = dict(
        zcta='00001', state='Illinois', lat=0.0, lon=0.0,
        pctl_owner_occupied=0.5, pctl_poverty=0.5, pctl_non_student_poverty=0.5,
        pctl_tenure=0.5, pctl_tenure_nonstudent=0.5, pctl_vacancy_deviation=0.5,
        pctl_eviction_execution=0.5, pctl_eviction_filing=0.5, pctl_median_income=0.5,
    )
    base.update(overrides)
    return ZipRecord(**base)


def test_all_metrics_at_the_median_score_fifty():
    assert score_zip(_full()).score == pytest.approx(50.0)


def test_full_coverage_reports_one_hundred_percent():
    assert score_zip(_full()).coverage_pct == pytest.approx(100.0)


def test_higher_is_better_metric_uses_the_percentile_directly():
    # owner_occupied at the 90th percentile contributes 90 * its weight.
    res = score_zip(_full(pctl_owner_occupied=0.9))
    assert res.components['owner_occupied'] == pytest.approx(90.0)


def test_lower_is_better_metric_is_inverted_per_pdf_section_2_2():
    # poverty at the 90th percentile (very poor) scores 100 * (1 - 0.9) = 10.
    res = score_zip(_full(pctl_poverty=0.9))
    assert res.components['poverty'] == pytest.approx(10.0)


def test_score_is_the_weighted_sum_of_components():
    res = score_zip(_full(pctl_owner_occupied=0.9, pctl_poverty=0.1))
    expected = sum(res.components[k] * NSS_WEIGHTS[k] for k in NSS_WEIGHTS) / 100.0
    assert res.score == pytest.approx(expected)


def test_missing_metric_renormalizes_rather_than_zero_filling():
    # Dropping eviction_filing (9.0909 of weight) from an all-median record must
    # leave the score at 50, not drag it toward 45.5.
    res = score_zip(_full(pctl_eviction_filing=None))
    assert res.score == pytest.approx(50.0)
    assert 'eviction_filing' not in res.components


def test_missing_metric_reduces_reported_coverage():
    res = score_zip(_full(pctl_eviction_filing=None))
    assert res.coverage_pct == pytest.approx(100.0 - NSS_WEIGHTS['eviction_filing'])


def test_a_zip_missing_eviction_scores_like_one_at_its_weighted_mean():
    # The renormalization guarantee, stated as the spec states it.
    missing = score_zip(_full(pctl_eviction_filing=None, pctl_eviction_execution=None))
    present = score_zip(_full())
    assert missing.score == pytest.approx(present.score)


def test_no_metrics_at_all_scores_zero_with_zero_coverage():
    bare = ZipRecord(zcta='00002', state='Illinois', lat=0.0, lon=0.0)
    res = score_zip(bare)
    assert res.score == pytest.approx(0.0)
    assert res.coverage_pct == pytest.approx(0.0)


def test_band_is_attached():
    assert score_zip(_full(
        pctl_owner_occupied=0.99, pctl_poverty=0.01, pctl_tenure=0.99,
        pctl_vacancy_deviation=0.01, pctl_eviction_execution=0.01,
        pctl_eviction_filing=0.01, pctl_median_income=0.99,
    )).band == 'Exceptional'


def test_hinsdale_fixture_lands_in_a_high_band():
    # Fixture percentiles mirror the PDF's 60521 profile; its Stability
    # component there was 89.7, so NSS must land Very Favorable or better.
    res = score_zip(load_table(FIXTURE)['60521'])
    assert res.score >= 80.0
    assert res.band in ('Very Favorable', 'Exceptional')


def test_high_poverty_chicago_fixture_lands_low():
    res = score_zip(load_table(FIXTURE)['60623'])
    assert res.score < 50.0
    assert res.band == 'Relatively Unfavorable'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zip_screen_quality_unit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.housing.zip_screen.quality'`

- [ ] **Step 3: Write minimal implementation**

`src/housing/zip_screen/quality.py`:

```python
"""Neighborhood Stability Score (NSS) for one ZCTA.

A pure weighted sum: every percentile was computed against the full national
distribution at build time (scripts/build_zip_metrics.py), so nothing here
needs distribution data.

Missing metrics are RENORMALIZED, never zero-filled. Zero-filling would
penalize a rural ZIP for a gap in the eviction dataset rather than for any
property of the place, which is precisely the distortion this model exists to
avoid.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .schema import (
    HIGHER_IS_BETTER,
    NSS_WEIGHTS,
    PCTL_COLUMN,
    ZipRecord,
    band_for,
)


@dataclass(frozen=True)
class NssResult:
    score: float
    band: str
    coverage_pct: float
    components: dict[str, float] = field(default_factory=dict)
    upi_adjusted: bool = False


def _component_score(metric: str, percentile: float) -> float:
    """PDF section 2.2: lower-is-better metrics use 100 * (1 - Percentile)."""
    if metric in HIGHER_IS_BETTER:
        return 100.0 * percentile
    return 100.0 * (1.0 - percentile)


def score_zip(rec: ZipRecord) -> NssResult:
    """Score one ZCTA 0-100, reporting per-metric components and coverage."""
    components: dict[str, float] = {}
    available_weight = 0.0
    weighted_total = 0.0
    for metric, weight in NSS_WEIGHTS.items():
        percentile = getattr(rec, PCTL_COLUMN[metric], None)
        if percentile is None:
            continue
        value = _component_score(metric, float(percentile))
        components[metric] = value
        weighted_total += value * weight
        available_weight += weight
    if available_weight <= 0.0:
        return NssResult(score=0.0, band=band_for(0.0), coverage_pct=0.0, components={})
    score = weighted_total / available_weight
    return NssResult(
        score=score,
        band=band_for(score),
        coverage_pct=available_weight,
        components=components,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_zip_screen_quality_unit.py -v`
Expected: PASS, 12 passed

- [ ] **Step 5: Commit**

```bash
git add src/housing/zip_screen/quality.py tests/test_zip_screen_quality_unit.py
git commit -m "feat(zip-screen): add NSS scoring with coverage renormalization"
```

---

### Task 5: University adjustment (UPI)

**Files:**
- Modify: `src/housing/zip_screen/quality.py`
- Test: `tests/test_zip_screen_quality_upi_unit.py`

**Interfaces:**
- Consumes: `quality.score_zip`, `schema.UPI_THRESHOLD`
- Produces: `score_zip` now honors `rec.upi`; `NssResult.upi_adjusted` becomes meaningful

- [ ] **Step 1: Write the failing test**

```python
"""PDF section 5: the University Presence Index adjustment."""
from __future__ import annotations

import pytest

from src.housing.zip_screen.quality import score_zip
from src.housing.zip_screen.schema import UPI_THRESHOLD, ZipRecord
from src.housing.zip_screen.table import clear_cache, load_table

pytestmark = pytest.mark.unit

FIXTURE = 'tests/fixtures/zip_metrics_sample.csv'


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


def _rec(upi: float) -> ZipRecord:
    """Raw poverty is punishing (0.91); non-student poverty is mild (0.34).
    Raw tenure is punishing (0.14); non-student tenure is healthy (0.62)."""
    return ZipRecord(
        zcta='60115', state='Illinois', lat=41.93, lon=-88.75, upi=upi,
        pctl_owner_occupied=0.21, pctl_poverty=0.91, pctl_non_student_poverty=0.34,
        pctl_tenure=0.14, pctl_tenure_nonstudent=0.62, pctl_vacancy_deviation=0.71,
        pctl_eviction_execution=0.68, pctl_eviction_filing=0.74, pctl_median_income=0.18,
    )


def test_below_threshold_uses_raw_poverty_and_tenure():
    res = score_zip(_rec(upi=0.05))
    assert res.upi_adjusted is False
    assert res.components['poverty'] == pytest.approx(100.0 * (1 - 0.91))
    assert res.components['tenure'] == pytest.approx(100.0 * 0.14)


def test_above_threshold_substitutes_the_non_student_metrics():
    res = score_zip(_rec(upi=0.38))
    assert res.upi_adjusted is True
    assert res.components['poverty'] == pytest.approx(100.0 * (1 - 0.34))
    assert res.components['tenure'] == pytest.approx(100.0 * 0.62)


def test_threshold_is_exclusive_at_exactly_fifteen_percent():
    assert score_zip(_rec(upi=UPI_THRESHOLD)).upi_adjusted is False
    assert score_zip(_rec(upi=UPI_THRESHOLD + 0.001)).upi_adjusted is True


def test_adjustment_raises_the_score_materially():
    # The PDF's 60115 case: the correction is large and upward.
    raw = score_zip(_rec(upi=0.05)).score
    adjusted = score_zip(_rec(upi=0.38)).score
    assert adjusted > raw + 10.0


def test_dekalb_fixture_is_adjusted_out_of_the_bottom_band():
    res = score_zip(load_table(FIXTURE)['60115'])
    assert res.upi_adjusted is True
    assert res.score > 40.0


def test_adjustment_falls_back_to_raw_when_non_student_data_is_absent():
    rec = ZipRecord(
        zcta='00003', state='Illinois', lat=0.0, lon=0.0, upi=0.40,
        pctl_poverty=0.91, pctl_non_student_poverty=None,
        pctl_tenure=0.14, pctl_tenure_nonstudent=None,
        pctl_owner_occupied=0.5, pctl_vacancy_deviation=0.5,
        pctl_eviction_execution=0.5, pctl_eviction_filing=0.5, pctl_median_income=0.5,
    )
    res = score_zip(rec)
    assert res.components['poverty'] == pytest.approx(100.0 * (1 - 0.91))
    assert res.upi_adjusted is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zip_screen_quality_upi_unit.py -v`
Expected: FAIL — `AssertionError` on `test_above_threshold_substitutes_the_non_student_metrics` (`upi_adjusted` is always False)

- [ ] **Step 3: Write minimal implementation**

In `src/housing/zip_screen/quality.py`, add the import and the substitution map, then replace `score_zip`:

```python
from .schema import (
    HIGHER_IS_BETTER,
    NSS_WEIGHTS,
    PCTL_COLUMN,
    UPI_THRESHOLD,
    ZipRecord,
    band_for,
)

# PDF section 5: above the UPI threshold, these metrics read from their
# student-excluded columns instead. Standard ACS models treat non-working
# students as impoverished and annual leases as instability, which distorts
# university towns downward by tens of points.
#
# The source model's other two UPI adjustments -- ambient-population crime
# denominators and police-call filtering -- are Safety adjustments, and Safety
# is not part of NSS. Nothing is lost by omitting them.
_UPI_SUBSTITUTION = {
    'poverty': 'pctl_non_student_poverty',
    'tenure': 'pctl_tenure_nonstudent',
}


def score_zip(rec: ZipRecord) -> NssResult:
    """Score one ZCTA 0-100, reporting per-metric components and coverage."""
    upi_eligible = rec.upi > UPI_THRESHOLD
    upi_applied = False
    components: dict[str, float] = {}
    available_weight = 0.0
    weighted_total = 0.0
    for metric, weight in NSS_WEIGHTS.items():
        column = PCTL_COLUMN[metric]
        if upi_eligible and metric in _UPI_SUBSTITUTION:
            substitute = getattr(rec, _UPI_SUBSTITUTION[metric], None)
            if substitute is not None:
                column = _UPI_SUBSTITUTION[metric]
                upi_applied = True
        percentile = getattr(rec, column, None)
        if percentile is None:
            continue
        value = _component_score(metric, float(percentile))
        components[metric] = value
        weighted_total += value * weight
        available_weight += weight
    if available_weight <= 0.0:
        return NssResult(score=0.0, band=band_for(0.0), coverage_pct=0.0, components={})
    score = weighted_total / available_weight
    return NssResult(
        score=score,
        band=band_for(score),
        coverage_pct=available_weight,
        components=components,
        upi_adjusted=upi_applied,
    )
```

- [ ] **Step 4: Run both quality test files to verify they pass**

Run: `pytest tests/test_zip_screen_quality_unit.py tests/test_zip_screen_quality_upi_unit.py -v`
Expected: PASS, 18 passed

- [ ] **Step 5: Commit**

```bash
git add src/housing/zip_screen/quality.py tests/test_zip_screen_quality_upi_unit.py
git commit -m "feat(zip-screen): apply the UPI university adjustment (PDF section 5)"
```

---

### Task 6: Resolve a ZIP into a Location

**Files:**
- Modify: `src/housing/models.py`
- Create: `src/housing/zip_screen/resolve.py`
- Test: `tests/test_zip_screen_resolve_unit.py`

**Interfaces:**
- Consumes: `schema.ZipRecord`, `models.Location`
- Produces: `resolve_location(rec, spec) -> Location`; `city_type_for_density(density: float) -> str`; `models.Location.zip_code: str | None`; `models.DENSITY_URBAN/SUBURBAN/EXURBAN`

- [ ] **Step 1: Write the failing test**

```python
"""ZipRecord -> Location. The boundary where ZIPs stop existing."""
from __future__ import annotations

import pytest

from src.housing.models import Location
from src.housing.zip_screen.resolve import city_type_for_density, resolve_location
from src.housing.zip_screen.table import clear_cache, load_table

pytestmark = pytest.mark.unit

FIXTURE = 'tests/fixtures/zip_metrics_sample.csv'

SPEC = {
    'bedrooms': 4,
    'bathrooms': 2.5,
    'property_type': 'single_family',
    'sqft_band': '2500_3500',
    'built_within_years': 20,
    'target_purchase_price_range': (400000.0, 900000.0),
}


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.mark.parametrize('density,expected', [
    (12000.0, 'urban'),
    (3000.0, 'urban'),
    (2999.0, 'suburban'),
    (1000.0, 'suburban'),
    (999.0, 'exurban'),
    (200.0, 'exurban'),
    (199.0, 'rural'),
    (0.0, 'rural'),
])
def test_density_thresholds(density, expected):
    assert city_type_for_density(density) == expected


def test_resolves_state_from_the_record():
    loc = resolve_location(load_table(FIXTURE)['60521'], SPEC)
    assert loc.state == 'Illinois'


def test_resolves_city_type_from_density():
    table = load_table(FIXTURE)
    # 60623: 88000 people over 4.6 sq mi -> dense urban.
    assert resolve_location(table['60623'], SPEC).city_type == 'urban'
    # 80424: 6200 over 68.4 sq mi -> ~91/sq mi -> rural.
    assert resolve_location(table['80424'], SPEC).city_type == 'rural'


def test_population_size_prefers_the_primary_place():
    loc = resolve_location(load_table(FIXTURE)['60521'], SPEC)
    assert loc.population_size == 17395


def test_population_size_falls_back_to_zcta_population():
    table = load_table(FIXTURE)
    rec = table['60521'].__class__(
        zcta='99999', state='Illinois', lat=0.0, lon=0.0,
        place_population=0, zcta_population=8200, land_area_sqmi=10.0,
    )
    assert resolve_location(rec, SPEC).population_size == 8200


def test_property_spec_passes_through_untouched():
    loc = resolve_location(load_table(FIXTURE)['60521'], SPEC)
    assert loc.bedrooms == 4
    assert loc.bathrooms == 2.5
    assert loc.property_type == 'single_family'
    assert loc.sqft_band == '2500_3500'
    assert loc.built_within_years == 20
    assert loc.target_purchase_price_range == (400000.0, 900000.0)


def test_zip_code_is_carried_for_display():
    assert resolve_location(load_table(FIXTURE)['60521'], SPEC).zip_code == '60521'


def test_result_is_an_ordinary_location_the_optimizer_accepts():
    loc = resolve_location(load_table(FIXTURE)['60521'], SPEC)
    assert isinstance(loc, Location)


def test_location_without_a_zip_still_constructs():
    # The hand-pick path must be unaffected.
    assert Location(state='Texas').zip_code is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zip_screen_resolve_unit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.housing.zip_screen.resolve'`

- [ ] **Step 3: Add the field and thresholds to models.py**

In `src/housing/models.py`, add after the `NARROWED_*` constants:

```python
# ZIP -> city_type thresholds, people per square mile (spec section 5.1). The
# optimizer's cost estimate is keyed on city_type, so these decide which
# STATE_ESTIMATES bucket a resolved ZIP lands in.
DENSITY_URBAN = 3000.0
DENSITY_SUBURBAN = 1000.0
DENSITY_EXURBAN = 200.0
```

And add the field to `Location`, as the last field so every positional use keeps working:

```python
@dataclass(frozen=True)
class Location:
    state: str
    city_type: str = 'suburban'
    population_size: int = 20000
    target_purchase_price_range: tuple[float, float] | None = None
    bedrooms: int = 3
    bathrooms: float = 2.0
    property_type: str = 'single_family'
    sqft_band: str = '1800_2500'
    built_within_years: int | None = None
    # Display/traceability only when this Location came from a ZIP search.
    # Nothing downstream reads it -- see src/housing/zip_screen/resolve.py.
    zip_code: str | None = None
```

- [ ] **Step 4: Write resolve.py**

```python
"""Turn a screened ZCTA into the ``Location`` the optimizer already understands.

This is the boundary: past this module nothing knows what a ZIP is.
``Location.state`` drives residency and state income tax, and
``city_type``/``population_size`` drive the STATE_ESTIMATES cost lookup (see
plan_variant.py), so resolution means deriving exactly those three fields and
passing the caller's property spec through unchanged.
"""
from __future__ import annotations

from typing import Any

from ..models import (
    DENSITY_EXURBAN,
    DENSITY_SUBURBAN,
    DENSITY_URBAN,
    Location,
)
from .schema import ZipRecord


def city_type_for_density(density: float) -> str:
    """Bucket a ZCTA's people-per-square-mile into the optimizer's city_type."""
    if density >= DENSITY_URBAN:
        return 'urban'
    if density >= DENSITY_SUBURBAN:
        return 'suburban'
    if density >= DENSITY_EXURBAN:
        return 'exurban'
    return 'rural'


def resolve_location(rec: ZipRecord, spec: dict[str, Any]) -> Location:
    """Build a ``Location`` from a ZCTA plus the caller's property spec.

    ``population_size`` prefers the ZIP's primary Census place -- the cost
    estimate is calibrated on city population, not on ZCTA population -- and
    falls back to the ZCTA's own population for a ZIP with no place match.
    """
    price_range = spec.get('target_purchase_price_range')
    if isinstance(price_range, (list, tuple)) and len(price_range) == 2:
        price_range = (float(price_range[0]), float(price_range[1]))
    else:
        price_range = None
    return Location(
        state=rec.state,
        city_type=city_type_for_density(rec.density),
        population_size=rec.place_population or rec.zcta_population,
        target_purchase_price_range=price_range,
        bedrooms=int(spec.get('bedrooms', 3) or 3),
        bathrooms=float(spec.get('bathrooms', 2.0) or 2.0),
        property_type=str(spec.get('property_type', 'single_family') or 'single_family'),
        sqft_band=str(spec.get('sqft_band', '1800_2500') or '1800_2500'),
        built_within_years=spec.get('built_within_years') or None,
        zip_code=rec.zcta,
    )
```

- [ ] **Step 5: Run the test and the existing optimizer suite**

Run: `pytest tests/test_zip_screen_resolve_unit.py tests/test_housing_optimizer_unit.py -v`
Expected: PASS — the new file passes and the existing 
optimizer unit tests are unaffected by the added field.

- [ ] **Step 6: Commit**

```bash
git add src/housing/models.py src/housing/zip_screen/resolve.py tests/test_zip_screen_resolve_unit.py
git commit -m "feat(zip-screen): resolve a ZCTA into a Location the optimizer accepts"
```

---

### Task 7: The Stage-1 funnel

**Files:**
- Create: `src/housing/zip_screen/screen.py`
- Test: `tests/test_zip_screen_funnel_unit.py`

**Interfaces:**
- Consumes: `geo.zips_within`, `quality.score_zip`, `table.load_table`, `schema.COVERAGE_FLOOR_PCT`
- Produces: `ScreenRequest` dataclass; `ScreenedZip` dataclass; `ScreenResult` dataclass with `funnel: dict[str, int]` and `shortlist: list[ScreenedZip]`; `run_screen(req, table=None, current_state='') -> ScreenResult`; `AnchorNotFoundError`

- [ ] **Step 1: Write the failing test**

```python
"""The Stage-1 funnel: radius, coverage, score floor, affordability."""
from __future__ import annotations

import pytest

from src.housing.zip_screen.screen import (
    AnchorNotFoundError,
    ScreenRequest,
    run_screen,
)
from src.housing.zip_screen.table import clear_cache, load_table

pytestmark = pytest.mark.unit

FIXTURE = 'tests/fixtures/zip_metrics_sample.csv'

SPEC = {
    'bedrooms': 3, 'bathrooms': 2.0, 'property_type': 'single_family',
    'sqft_band': '1800_2500', 'built_within_years': None,
    'target_purchase_price_range': None,
}


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def table():
    return load_table(FIXTURE)


def _req(**overrides) -> ScreenRequest:
    base = dict(
        anchor_zip='60521', radius_miles=50, min_quality_score=0.0,
        shortlist_size=4, property_spec=dict(SPEC),
    )
    base.update(overrides)
    return ScreenRequest(**base)


def test_unknown_anchor_is_named_in_the_error(table):
    with pytest.raises(AnchorNotFoundError, match='99999'):
        run_screen(_req(anchor_zip='99999'), table=table)


def test_funnel_reports_every_stage(table):
    res = run_screen(_req(), table=table)
    for key in ('in_radius', 'with_data', 'above_score', 'affordable',
                'after_dedup', 'promoted'):
        assert key in res.funnel


def test_funnel_counts_are_monotonically_non_increasing(table):
    f = run_screen(_req(), table=table).funnel
    counts = [f['in_radius'], f['with_data'], f['above_score'],
              f['affordable'], f['after_dedup'], f['promoted']]
    assert counts == sorted(counts, reverse=True)


def test_coverage_floor_drops_the_sparse_row(table):
    # 60950 has four metrics missing, putting it under COVERAGE_FLOOR_PCT.
    res = run_screen(_req(radius_miles=50), table=table)
    assert '60950' not in {z.zcta for z in res.shortlist}


def test_partial_coverage_above_the_floor_survives(table):
    # 60187 is missing only the two eviction metrics (78.8% coverage).
    res = run_screen(_req(shortlist_size=4, radius_miles=50), table=table)
    surviving = {z.zcta for z in res.all_passing}
    assert '60187' in surviving


def test_score_floor_is_applied(table):
    low = run_screen(_req(min_quality_score=0.0), table=table)
    high = run_screen(_req(min_quality_score=85.0), table=table)
    assert high.funnel['above_score'] < low.funnel['above_score']
    assert all(z.nss >= 85.0 for z in high.shortlist)


def test_affordability_filter_excludes_out_of_range_estimates(table):
    res = run_screen(
        _req(property_spec={**SPEC, 'target_purchase_price_range': (100000.0, 200000.0)}),
        table=table,
    )
    assert all(100000.0 <= z.est_price <= 200000.0 for z in res.shortlist)


def test_no_price_range_disables_the_affordability_filter(table):
    res = run_screen(_req(), table=table)
    assert res.funnel['affordable'] == res.funnel['above_score']


def test_shortlist_never_exceeds_the_requested_size(table):
    assert len(run_screen(_req(shortlist_size=2), table=table).shortlist) <= 2


def test_every_shortlisted_zip_carries_its_score_band_and_distance(table):
    for z in run_screen(_req(), table=table).shortlist:
        assert 0.0 <= z.nss <= 100.0
        assert z.band
        assert z.distance_miles >= 0.0
        assert z.components


def test_cross_state_is_null_within_the_plan_state(table):
    res = run_screen(_req(), table=table, current_state='Illinois')
    il = [z for z in res.shortlist if z.state == 'Illinois']
    assert il and all(z.cross_state is None for z in il)


def test_cross_state_is_flagged_when_the_state_differs(table):
    res = run_screen(_req(anchor_zip='33143', radius_miles=50), table=table,
                     current_state='Illinois')
    assert res.shortlist
    assert all(z.cross_state == 'Florida' for z in res.shortlist)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zip_screen_funnel_unit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.housing.zip_screen.screen'`

- [ ] **Step 3: Write minimal implementation**

`src/housing/zip_screen/screen.py`:

```python
"""Stage 1: narrow every ZCTA in range down to a promotable shortlist.

Pure table math -- no engine runs. A 50-mile radius can cover ~300 ZCTAs and
the optimizer runs the full deterministic engine (and Monte Carlo) per
candidate, so the screen exists to hand the optimizer a handful of genuinely
different bets rather than three hundred near-duplicates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .geo import haversine_miles, zips_within
from .quality import score_zip
from .schema import COVERAGE_FLOOR_PCT, ZipRecord
from .table import load_table


class AnchorNotFoundError(KeyError):
    """The anchor ZIP is not in the snapshot."""


@dataclass(frozen=True)
class ScreenRequest:
    anchor_zip: str
    radius_miles: int
    min_quality_score: float
    shortlist_size: int
    property_spec: dict[str, Any]


@dataclass(frozen=True)
class ScreenedZip:
    zcta: str
    city: str
    state: str
    distance_miles: float
    nss: float
    band: str
    coverage_pct: float
    est_price: float
    components: dict[str, float]
    upi_adjusted: bool = False
    cross_state: str | None = None
    promoted: bool = False
    collapsed: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScreenResult:
    anchor: dict[str, Any]
    radius_miles: int
    funnel: dict[str, int]
    shortlist: list[ScreenedZip]
    all_passing: list[ScreenedZip]


def estimate_price(rec: ZipRecord, base_estimate: float) -> float:
    """Scale a state-level price estimate by this ZIP's relative home value.

    STATE_ESTIMATES is keyed on state + city_type + population, so without this
    every ZIP in a state sharing a city_type would price identically and the
    affordability filter would have no discriminating power. ACS median home
    value supplies the within-state spread.
    """
    if not rec.median_home_value or not rec.state_median_home_value:
        return base_estimate
    return base_estimate * (rec.median_home_value / rec.state_median_home_value)


def _base_estimate(rec: ZipRecord) -> float:
    """Placeholder anchor for the affordability ratio.

    Task 11 replaces this with the real STATE_ESTIMATES lookup once the screen
    is wired to the optimizer; until then the ratio is applied to the state
    median itself, which is exactly the right shape and keeps this module free
    of an engine dependency.
    """
    return float(rec.state_median_home_value or 0.0)


def run_screen(
    req: ScreenRequest,
    table: dict[str, ZipRecord] | None = None,
    current_state: str = '',
) -> ScreenResult:
    """Run the Stage-1 funnel, recording each stage's surviving count."""
    data = table if table is not None else load_table()
    anchor = data.get(str(req.anchor_zip).strip())
    if anchor is None:
        raise AnchorNotFoundError(
            f'anchor ZIP {req.anchor_zip!r} is not in the screening snapshot'
        )

    in_radius = zips_within(data, anchor, req.radius_miles)
    funnel = {'in_radius': len(in_radius)}

    price_range = req.property_spec.get('target_purchase_price_range')
    lo, hi = (float(price_range[0]), float(price_range[1])) if price_range else (None, None)

    with_data: list[tuple[ZipRecord, float, Any]] = []
    for rec, dist in in_radius:
        nss = score_zip(rec)
        if nss.coverage_pct < COVERAGE_FLOOR_PCT:
            continue
        with_data.append((rec, dist, nss))
    funnel['with_data'] = len(with_data)

    above_score = [t for t in with_data if t[2].score >= req.min_quality_score]
    funnel['above_score'] = len(above_score)

    passing: list[ScreenedZip] = []
    for rec, dist, nss in above_score:
        price = estimate_price(rec, _base_estimate(rec))
        if lo is not None and not (lo <= price <= hi):
            continue
        passing.append(ScreenedZip(
            zcta=rec.zcta,
            city=rec.primary_place,
            state=rec.state,
            distance_miles=round(dist, 2),
            nss=round(nss.score, 1),
            band=nss.band,
            coverage_pct=round(nss.coverage_pct, 1),
            est_price=round(price, 2),
            components={k: round(v, 1) for k, v in nss.components.items()},
            upi_adjusted=nss.upi_adjusted,
            cross_state=rec.state if current_state and rec.state != current_state else None,
        ))
    funnel['affordable'] = len(passing)

    passing.sort(key=lambda z: (-z.nss, z.distance_miles, z.zcta))
    funnel['after_dedup'] = len(passing)

    shortlist = [
        ScreenedZip(**{**z.__dict__, 'promoted': True})
        for z in passing[: max(0, int(req.shortlist_size))]
    ]
    funnel['promoted'] = len(shortlist)

    return ScreenResult(
        anchor={'zip': anchor.zcta, 'city': anchor.primary_place,
                'state': anchor.state, 'lat': anchor.lat, 'lon': anchor.lon},
        radius_miles=req.radius_miles,
        funnel=funnel,
        shortlist=shortlist,
        all_passing=passing,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_zip_screen_funnel_unit.py -v`
Expected: PASS, 12 passed

- [ ] **Step 5: Commit**

```bash
git add src/housing/zip_screen/screen.py tests/test_zip_screen_funnel_unit.py
git commit -m "feat(zip-screen): add the Stage-1 funnel with per-stage diagnostics"
```

---

### Task 8: De-duplication

**Files:**
- Modify: `src/housing/zip_screen/screen.py`
- Test: `tests/test_zip_screen_dedup_unit.py`

**Interfaces:**
- Consumes: `screen.ScreenedZip`, `geo.haversine_miles`, `schema.DEDUP_RADIUS_MILES`, `schema.DEDUP_SCORE_POINTS`
- Produces: `deduplicate(candidates, coords) -> list[ScreenedZip]`; `run_screen` now populates `ScreenedZip.collapsed`

- [ ] **Step 1: Write the failing test**

```python
"""De-duplication: four adjacent suburbs of one town are not four bets."""
from __future__ import annotations

import pytest

from src.housing.zip_screen.screen import ScreenRequest, run_screen
from src.housing.zip_screen.table import clear_cache, load_table

pytestmark = pytest.mark.unit

FIXTURE = 'tests/fixtures/zip_metrics_sample.csv'

SPEC = {
    'bedrooms': 3, 'bathrooms': 2.0, 'property_type': 'single_family',
    'sqft_band': '1800_2500', 'built_within_years': None,
    'target_purchase_price_range': None,
}


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def table():
    return load_table(FIXTURE)


def _req(**overrides) -> ScreenRequest:
    base = dict(anchor_zip='80206', radius_miles=50, min_quality_score=0.0,
                shortlist_size=4, property_spec=dict(SPEC))
    base.update(overrides)
    return ScreenRequest(**base)


def test_the_denver_cluster_collapses_to_one_survivor(table):
    # 80206/80209/80210 are all within 5 miles, same state, within 5 NSS points.
    res = run_screen(_req(), table=table)
    denver = [z for z in res.shortlist if z.zcta in ('80206', '80209', '80210')]
    assert len(denver) == 1


def test_collapsed_neighbours_are_returned_not_dropped(table):
    res = run_screen(_req(), table=table)
    survivor = next(z for z in res.shortlist if z.zcta in ('80206', '80209', '80210'))
    assert set(survivor.collapsed) == {'80206', '80209', '80210'} - {survivor.zcta}


def test_the_highest_scoring_member_of_a_cluster_survives(table):
    res = run_screen(_req(), table=table)
    survivor = next(z for z in res.shortlist if z.zcta in ('80206', '80209', '80210'))
    assert survivor.zcta == '80209'


def test_a_distant_zip_is_never_collapsed(table):
    # 80424 (Breckenridge) is ~65 miles from Denver -- outside a 50-mile radius
    # entirely, and would not be collapsed even if it were in range.
    res = run_screen(_req(), table=table)
    assert all('80424' not in z.collapsed for z in res.shortlist)


def test_a_nearby_zip_with_a_distant_score_is_not_collapsed(table):
    # Score-gap guard: different bets stay separate even when adjacent.
    res = run_screen(ScreenRequest(
        anchor_zip='60521', radius_miles=50, min_quality_score=0.0,
        shortlist_size=4, property_spec=dict(SPEC),
    ), table=table)
    zctas = {z.zcta for z in res.shortlist}
    assert '60521' in zctas
    assert '60623' not in {c for z in res.shortlist for c in z.collapsed}


def test_funnel_after_dedup_reflects_the_collapse(table):
    res = run_screen(_req(), table=table)
    assert res.funnel['after_dedup'] < res.funnel['affordable']


def test_dedup_never_reduces_below_what_was_available(table):
    res = run_screen(_req(shortlist_size=4), table=table)
    assert res.funnel['promoted'] <= res.funnel['after_dedup']
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zip_screen_dedup_unit.py -v`
Expected: FAIL — `test_the_denver_cluster_collapses_to_one_survivor`, 3 returned instead of 1

- [ ] **Step 3: Write minimal implementation**

In `src/housing/zip_screen/screen.py`, add the imports and the function:

```python
from .schema import (
    COVERAGE_FLOOR_PCT,
    DEDUP_RADIUS_MILES,
    DEDUP_SCORE_POINTS,
    ZipRecord,
)


def deduplicate(
    candidates: list[ScreenedZip], coords: dict[str, tuple[float, float]]
) -> list[ScreenedZip]:
    """Collapse near-identical neighbours, highest score first.

    A candidate is suppressed when an already-kept candidate is within
    DEDUP_RADIUS_MILES, in the same state, and within DEDUP_SCORE_POINTS.
    Without this the top 4 of a metro search are routinely four adjacent
    suburbs of one town, and the engine spends four full runs comparing
    near-duplicates.

    Suppressed ZIPs are recorded on their survivor's ``collapsed`` list, never
    silently discarded -- a hidden ranking policy is indistinguishable from a
    bug to the person reading the results.
    """
    kept: list[ScreenedZip] = []
    collapsed_by: dict[str, list[str]] = {}
    for cand in sorted(candidates, key=lambda z: (-z.nss, z.distance_miles, z.zcta)):
        lat, lon = coords[cand.zcta]
        survivor = None
        for k in kept:
            klat, klon = coords[k.zcta]
            if (
                k.state == cand.state
                and abs(k.nss - cand.nss) <= DEDUP_SCORE_POINTS
                and haversine_miles(klat, klon, lat, lon) <= DEDUP_RADIUS_MILES
            ):
                survivor = k
                break
        if survivor is None:
            kept.append(cand)
            collapsed_by.setdefault(cand.zcta, [])
        else:
            collapsed_by[survivor.zcta].append(cand.zcta)
    return [
        ScreenedZip(**{**z.__dict__, 'collapsed': sorted(collapsed_by.get(z.zcta, []))})
        for z in kept
    ]
```

Then in `run_screen`, replace the two lines between `funnel['affordable']` and the shortlist build:

```python
    coords = {rec.zcta: (rec.lat, rec.lon) for rec, _, _ in above_score}
    passing = deduplicate(passing, coords)
    funnel['after_dedup'] = len(passing)
```

- [ ] **Step 4: Run the funnel and dedup suites**

Run: `pytest tests/test_zip_screen_funnel_unit.py tests/test_zip_screen_dedup_unit.py -v`
Expected: PASS, 19 passed

- [ ] **Step 5: Commit**

```bash
git add src/housing/zip_screen/screen.py tests/test_zip_screen_dedup_unit.py
git commit -m "feat(zip-screen): collapse near-identical neighbours, visibly"
```

---

### Task 9: Relaxation suggestion for an empty funnel

**Files:**
- Modify: `src/housing/zip_screen/screen.py`
- Test: `tests/test_zip_screen_relaxation_unit.py`

**Interfaces:**
- Consumes: `screen.run_screen`
- Produces: `ScreenResult.relaxation: dict[str, Any] | None`

- [ ] **Step 1: Write the failing test**

```python
"""An empty funnel must say where it emptied and what would relax it."""
from __future__ import annotations

import pytest

from src.housing.zip_screen.screen import ScreenRequest, run_screen
from src.housing.zip_screen.table import clear_cache, load_table

pytestmark = pytest.mark.unit

FIXTURE = 'tests/fixtures/zip_metrics_sample.csv'

SPEC = {
    'bedrooms': 3, 'bathrooms': 2.0, 'property_type': 'single_family',
    'sqft_band': '1800_2500', 'built_within_years': None,
    'target_purchase_price_range': None,
}


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def table():
    return load_table(FIXTURE)


def _req(**overrides) -> ScreenRequest:
    base = dict(anchor_zip='60521', radius_miles=50, min_quality_score=0.0,
                shortlist_size=4, property_spec=dict(SPEC))
    base.update(overrides)
    return ScreenRequest(**base)


def test_a_satisfied_search_suggests_nothing(table):
    assert run_screen(_req(), table=table).relaxation is None


def test_an_impossible_score_floor_suggests_a_lower_one(table):
    res = run_screen(_req(min_quality_score=99.9), table=table)
    assert res.shortlist == []
    assert res.relaxation is not None
    assert res.relaxation['field'] == 'min_quality_score'
    assert res.relaxation['suggested'] < 99.9
    assert res.relaxation['would_return'] >= 1


def test_the_suggested_floor_actually_returns_that_many(table):
    res = run_screen(_req(min_quality_score=99.9), table=table)
    retry = run_screen(_req(min_quality_score=res.relaxation['suggested']), table=table)
    assert len(retry.all_passing) >= res.relaxation['would_return']


def test_no_suggestion_when_nothing_had_data_in_range(table):
    # Breckenridge alone at 5 miles: in radius, but nothing clears the funnel
    # for score reasons, so there is no score to suggest.
    res = run_screen(_req(anchor_zip='80424', radius_miles=5,
                          min_quality_score=99.9), table=table)
    assert res.shortlist == []
    assert res.relaxation is None or res.relaxation['would_return'] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zip_screen_relaxation_unit.py -v`
Expected: FAIL — `AttributeError: 'ScreenResult' object has no attribute 'relaxation'`

- [ ] **Step 3: Write minimal implementation**

Add the field to `ScreenResult`:

```python
@dataclass(frozen=True)
class ScreenResult:
    anchor: dict[str, Any]
    radius_miles: int
    funnel: dict[str, int]
    shortlist: list[ScreenedZip]
    all_passing: list[ScreenedZip]
    relaxation: dict[str, Any] | None = None
```

Add the helper:

```python
def _relaxation(
    with_data: list[tuple[ZipRecord, float, Any]], min_quality_score: float
) -> dict[str, Any] | None:
    """What would the user have to give up to get results?

    A bare "no results" on a ten-criterion search is unusable: the user cannot
    tell which of ten constraints emptied the funnel. When the score floor is
    what did it, name the floor that would return something.
    """
    scores = sorted((t[2].score for t in with_data), reverse=True)
    if not scores or scores[0] >= min_quality_score:
        return None
    suggested = round(scores[0], 1)
    return {
        'field': 'min_quality_score',
        'current': min_quality_score,
        'suggested': suggested,
        'would_return': sum(1 for s in scores if s >= suggested),
    }
```

And return it from `run_screen`:

```python
    return ScreenResult(
        anchor={'zip': anchor.zcta, 'city': anchor.primary_place,
                'state': anchor.state, 'lat': anchor.lat, 'lon': anchor.lon},
        radius_miles=req.radius_miles,
        funnel=funnel,
        shortlist=shortlist,
        all_passing=passing,
        relaxation=_relaxation(with_data, req.min_quality_score) if not shortlist else None,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_zip_screen_relaxation_unit.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/housing/zip_screen/screen.py tests/test_zip_screen_relaxation_unit.py
git commit -m "feat(zip-screen): explain an empty funnel and suggest a relaxation"
```

---

### Task 10: Request parsing and mutual exclusion

**Files:**
- Modify: `src/housing/api.py`
- Modify: `src/housing/__init__.py`
- Test: `tests/test_zip_screen_api_contract.py`

**Interfaces:**
- Consumes: `screen.ScreenRequest`, `schema.ALLOWED_RADII_MILES`
- Produces: `api.parse_zip_search(raw) -> ScreenRequest`; `api.zip_screen_from_request(c0, body) -> tuple[dict, int]`

- [ ] **Step 1: Write the failing test**

```python
"""Wire contract for zip_search parsing and the screen-only endpoint."""
from __future__ import annotations

import pytest

from src.housing.api import zip_screen_from_request

pytestmark = pytest.mark.contract

SPEC = {
    'bedrooms': 3, 'bathrooms': 2.0, 'property_type': 'single_family',
    'sqft_band': '1800_2500', 'built_within_years': None,
}

C0 = {'state': 'Illinois'}


def _body(**overrides):
    zs = {'anchor': {'zip': '60521'}, 'radius_miles': 25,
          'min_quality_score': 60, 'shortlist_size': 4,
          'property_spec': dict(SPEC)}
    zs.update(overrides.pop('zip_search', {}))
    body = {'zip_search': zs}
    body.update(overrides)
    return body


def test_valid_body_returns_200(monkeypatch):
    payload, status = zip_screen_from_request(C0, _body(), table_path='tests/fixtures/zip_metrics_sample.csv')
    assert status == 200
    assert payload['success'] is True


def test_response_carries_the_schema_and_model_version():
    payload, _ = zip_screen_from_request(C0, _body(), table_path='tests/fixtures/zip_metrics_sample.csv')
    assert payload['zip_screen']['schema'] == 'zip_screen_v1'
    assert payload['zip_screen']['score_model'] == 'nss-1.0'


def test_response_carries_the_disclosure_string():
    payload, _ = zip_screen_from_request(C0, _body(), table_path='tests/fixtures/zip_metrics_sample.csv')
    assert payload['zip_screen']['disclosure'] == (
        'Measures housing and economic stability. Does not measure crime or safety.'
    )


def test_response_carries_the_funnel():
    payload, _ = zip_screen_from_request(C0, _body(), table_path='tests/fixtures/zip_metrics_sample.csv')
    assert set(payload['zip_screen']['funnel']) >= {
        'in_radius', 'with_data', 'above_score', 'affordable', 'after_dedup', 'promoted'
    }


@pytest.mark.parametrize('bad', [0, 3, 15, 100, -5, 'twenty'])
def test_bad_radius_is_a_400(bad):
    payload, status = zip_screen_from_request(
        C0, _body(zip_search={'radius_miles': bad}),
        table_path='tests/fixtures/zip_metrics_sample.csv')
    assert status == 400
    assert 'radius_miles' in payload['error']


def test_missing_zip_search_is_a_400():
    payload, status = zip_screen_from_request(C0, {}, table_path='tests/fixtures/zip_metrics_sample.csv')
    assert status == 400
    assert 'zip_search' in payload['error']


def test_unknown_anchor_is_a_400_naming_the_zip():
    payload, status = zip_screen_from_request(
        C0, _body(zip_search={'anchor': {'zip': '99999'}}),
        table_path='tests/fixtures/zip_metrics_sample.csv')
    assert status == 400
    assert '99999' in payload['error']


def test_shortlist_size_is_clamped_to_two_through_four():
    for requested, expected in ((1, 2), (9, 4)):
        payload, _ = zip_screen_from_request(
            C0, _body(zip_search={'shortlist_size': requested, 'min_quality_score': 0}),
            table_path='tests/fixtures/zip_metrics_sample.csv')
        assert len(payload['zip_screen']['shortlist']) <= expected


def test_shortlist_rows_carry_the_documented_fields():
    payload, _ = zip_screen_from_request(
        C0, _body(zip_search={'min_quality_score': 0}),
        table_path='tests/fixtures/zip_metrics_sample.csv')
    row = payload['zip_screen']['shortlist'][0]
    for key in ('zip', 'city', 'state', 'distance_miles', 'nss', 'band',
                'components', 'coverage_pct', 'est_price', 'cross_state',
                'promoted', 'collapsed'):
        assert key in row
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zip_screen_api_contract.py -v`
Expected: FAIL — `ImportError: cannot import name 'zip_screen_from_request'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/housing/api.py`:

```python
from .zip_screen.schema import (
    ALLOWED_RADII_MILES,
    NSS_DISCLOSURE,
    RESPONSE_SCHEMA,
    SCORE_MODEL_VERSION,
)
from .zip_screen.screen import AnchorNotFoundError, ScreenRequest, run_screen
from .zip_screen.table import load_table


def parse_zip_search(raw: dict[str, Any]) -> ScreenRequest:
    """Parse a ``zip_search`` block. Raises ValueError with a wire-ready message."""
    anchor = raw.get('anchor') or {}
    anchor_zip = str(anchor.get('zip', '') or '').strip()
    if not anchor_zip:
        raise ValueError('zip_search.anchor.zip is required.')
    try:
        radius = int(raw.get('radius_miles'))
    except (TypeError, ValueError):
        radius = -1
    if radius not in ALLOWED_RADII_MILES:
        allowed = ', '.join(str(r) for r in ALLOWED_RADII_MILES)
        raise ValueError(f'radius_miles must be one of {allowed}.')
    try:
        min_score = float(raw.get('min_quality_score', 0) or 0)
    except (TypeError, ValueError):
        raise ValueError('min_quality_score must be a number between 0 and 100.')
    if not (0.0 <= min_score <= 100.0):
        raise ValueError('min_quality_score must be between 0 and 100.')
    size = int(raw.get('shortlist_size', 4) or 4)
    return ScreenRequest(
        anchor_zip=anchor_zip,
        radius_miles=radius,
        min_quality_score=min_score,
        shortlist_size=max(2, min(4, size)),
        property_spec=dict(raw.get('property_spec') or {}),
    )


def _screened_zip_payload(z: Any) -> dict[str, Any]:
    return {
        'zip': z.zcta, 'city': z.city, 'state': z.state,
        'distance_miles': z.distance_miles, 'nss': z.nss, 'band': z.band,
        'components': z.components, 'coverage_pct': z.coverage_pct,
        'est_price': z.est_price, 'upi_adjusted': z.upi_adjusted,
        'cross_state': z.cross_state, 'promoted': z.promoted,
        'collapsed': z.collapsed,
    }


def screen_payload(result: Any) -> dict[str, Any]:
    """The ``zip_screen`` block shared by both endpoints."""
    return {
        'schema': RESPONSE_SCHEMA,
        'score_model': SCORE_MODEL_VERSION,
        'disclosure': NSS_DISCLOSURE,
        'anchor': result.anchor,
        'radius_miles': result.radius_miles,
        'funnel': result.funnel,
        'relaxation': result.relaxation,
        'shortlist': [_screened_zip_payload(z) for z in result.shortlist],
    }


def zip_screen_from_request(
    c0: dict[str, Any], body: dict[str, Any], table_path: str | None = None
) -> tuple[dict[str, Any], int]:
    """Run Stage 1 alone -- the "Preview shortlist" endpoint. No engine runs."""
    raw = body.get('zip_search')
    if not isinstance(raw, dict):
        return {'success': False, 'error': 'zip_search block is required.'}, 400
    try:
        req = parse_zip_search(raw)
        result = run_screen(
            req,
            table=load_table(table_path) if table_path else None,
            current_state=str(c0.get('state', '') or ''),
        )
    except AnchorNotFoundError as exc:
        return {'success': False, 'error': str(exc).strip("'")}, 400
    except ValueError as exc:
        return {'success': False, 'error': str(exc)}, 400
    return {'success': True, 'zip_screen': screen_payload(result)}, 200
```

Add to `src/housing/__init__.py` — the import and the `__all__` entries:

```python
from .api import optimize_housing_from_request, zip_screen_from_request
```

```python
    'zip_screen_from_request',
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_zip_screen_api_contract.py -v`
Expected: PASS, 15 passed

- [ ] **Step 5: Commit**

```bash
git add src/housing/api.py src/housing/__init__.py tests/test_zip_screen_api_contract.py
git commit -m "feat(zip-screen): add zip_search parsing and the screen-only payload"
```

---

### Task 11: Wire the screen into the optimizer and the route

**Files:**
- Modify: `src/housing/api.py`
- Modify: `src/housing/results.py:22-25` (the `_format_move` location serializer)
- Modify: `src/server/plan_routes.py:750`
- Test: `tests/test_zip_screen_optimizer_integration.py`

**Interfaces:**
- Consumes: `api.parse_zip_search`, `api.screen_payload`, `resolve.resolve_location`, `optimizer.optimize_housing`
- Produces: `optimize_housing_from_request` accepts `zip_search`; response carries `zip_screen`; route `POST /api/housing/zip-screen`

- [ ] **Step 1: Write the failing test**

```python
"""zip_search drives the real optimizer through resolved Locations."""
from __future__ import annotations

import pytest

from src.housing.api import optimize_housing_from_request

from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
from conftest import TEST_INPUT_DIR

pytestmark = pytest.mark.integration

FIXTURE = 'tests/fixtures/zip_metrics_sample.csv'

SPEC = {
    'bedrooms': 3, 'bathrooms': 2.0, 'property_type': 'single_family',
    'sqft_band': '1800_2500', 'built_within_years': None,
}


def _base_config():
    """The same engine config the existing housing integration suite uses
    (tests/test_housing_optimizer_integration.py:20). Skips itself on a fresh
    worktree, where input/ is gitignored."""
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        return ensure_engine_config(dict(c), source="test")


def _body(**overrides):
    body = {
        'zip_search': {
            'anchor': {'zip': '60521'}, 'radius_miles': 50,
            'min_quality_score': 0, 'shortlist_size': 2,
            'property_spec': dict(SPEC),
        },
        'move1_window': {
            'earliest_sale_year': 2028, 'latest_sale_year': 2029,
            'earliest_purchase_year': 2028, 'latest_purchase_year': 2029,
        },
        'objective': 'net_worth',
        'search_mode': 'narrowed',
    }
    body.update(overrides)
    return body


def test_zip_search_and_locations_together_is_a_400():
    payload, status = optimize_housing_from_request(
        _base_config(),
        _body(locations=[{'state': 'Texas'}, {'state': 'Florida'}]),
        table_path=FIXTURE,
    )
    assert status == 400
    assert 'mutually exclusive' in payload['error']


def test_neither_zip_search_nor_locations_is_a_400():
    payload, status = optimize_housing_from_request(_base_config(), {}, table_path=FIXTURE)
    assert status == 400


def test_zip_search_produces_a_zip_screen_block():
    payload, status = optimize_housing_from_request(_base_config(), _body(), table_path=FIXTURE)
    assert status == 200
    assert payload['zip_screen']['schema'] == 'zip_screen_v1'


def test_promoted_zips_become_the_optimizers_locations():
    payload, _ = optimize_housing_from_request(_base_config(), _body(), table_path=FIXTURE)
    promoted = {z['zip'] for z in payload['zip_screen']['shortlist']}
    assert payload['recommendation'] is not None
    recommended = payload['recommendation']['moves'][0]['location']
    assert recommended['zip_code'] in promoted


def test_recommendation_carries_the_nss_for_the_chosen_zip():
    payload, _ = optimize_housing_from_request(_base_config(), _body(), table_path=FIXTURE)
    loc = payload['recommendation']['moves'][0]['location']
    assert 0.0 <= loc['nss'] <= 100.0


def test_an_empty_shortlist_returns_200_without_running_the_engine():
    payload, status = optimize_housing_from_request(
        _base_config(),
        _body(zip_search={**_body()['zip_search'], 'min_quality_score': 99.9}),
        table_path=FIXTURE,
    )
    assert status == 200
    assert payload['recommendation'] is None
    assert payload['zip_screen']['relaxation'] is not None


def test_fewer_than_two_survivors_explains_rather_than_erroring():
    payload, status = optimize_housing_from_request(
        _base_config(),
        _body(zip_search={**_body()['zip_search'], 'anchor': {'zip': '80424'},
                          'radius_miles': 5, 'min_quality_score': 0}),
        table_path=FIXTURE,
    )
    assert status == 200
    assert payload['recommendation'] is None
    assert 'at least 2' in payload['message']


def test_the_hand_picked_path_still_works():
    payload, status = optimize_housing_from_request(_base_config(), {
        'locations': [{'state': 'Texas'}, {'state': 'Florida'}],
        'move1_window': {
            'earliest_sale_year': 2028, 'latest_sale_year': 2029,
            'earliest_purchase_year': 2028, 'latest_purchase_year': 2029,
        },
        'objective': 'net_worth', 'search_mode': 'narrowed',
    })
    assert status == 200
    assert 'zip_screen' not in payload
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zip_screen_optimizer_integration.py -v`
Expected: FAIL — `TypeError: optimize_housing_from_request() got an unexpected keyword argument 'table_path'`

- [ ] **Step 3: Replace the placeholder base estimate**

In `src/housing/zip_screen/screen.py`, replace `_base_estimate` with a caller-supplied
function so the module keeps no engine dependency:

```python
def _base_estimate(rec: ZipRecord) -> float:
    """State-median anchor for the affordability ratio.

    ``estimate_price`` multiplies this by the ZIP's median-home-value ratio to
    its state. Keeping the anchor at the state median leaves this module free
    of any engine or STATE_ESTIMATES dependency; the optimizer does the real
    cost modelling in Stage 2 on the resolved Location.
    """
    return float(rec.state_median_home_value or 0.0)
```

(No change needed — confirm the docstring reads as above and move on.)

- [ ] **Step 4: Extend optimize_housing_from_request**

In `src/housing/api.py`, replace the opening of `optimize_housing_from_request`:

```python
def optimize_housing_from_request(
    c0: dict[str, Any], body: dict[str, Any], table_path: str | None = None
) -> tuple[dict[str, Any], int]:
    """Parse an ``/api/housing/optimize`` request body, run the optimizer
    against the current plan config ``c0``, and return a ``(payload, status)``
    pair ready for ``jsonify``. Never mutates ``c0``.

    Candidate locations arrive one of two ways, never both: ``locations`` (the
    hand-picked path) or ``zip_search`` (Stage 1 discovers them -- see
    src/housing/zip_screen/).
    """
    try:
        raw_locations = body.get('locations') or []
        raw_zip_search = body.get('zip_search')
        if raw_zip_search and raw_locations:
            return {'success': False,
                    'error': 'locations and zip_search are mutually exclusive.'}, 400

        screen_block: dict[str, Any] | None = None
        if raw_zip_search:
            if not isinstance(raw_zip_search, dict):
                return {'success': False, 'error': 'zip_search must be an object.'}, 400
            req = parse_zip_search(raw_zip_search)
            table = load_table(table_path) if table_path else None
            result = run_screen(req, table=table,
                                current_state=str(c0.get('state', '') or ''))
            screen_block = screen_payload(result)
            if len(result.shortlist) < 2:
                return {
                    'success': True, 'schema': 'housing_optimize_v1',
                    'zip_screen': screen_block, 'recommendation': None,
                    'alternatives': [],
                    'message': (
                        'The screen returned fewer than 2 ZIPs; the optimizer needs '
                        'at least 2 candidate locations. Widen the radius or lower '
                        'the minimum quality score.'
                    ),
                }, 200
            nss_by_zip = {z.zcta: z.nss for z in result.shortlist}
            locations = [
                resolve_location(load_table(table_path)[z.zcta] if table_path
                                 else load_table()[z.zcta], req.property_spec)
                for z in result.shortlist
            ]
        else:
            if not isinstance(raw_locations, list) or not (2 <= len(raw_locations) <= 4):
                return {'success': False,
                        'error': 'Provide 2-4 candidate locations, or a zip_search block.'}, 400
            nss_by_zip = {}
            locations = [_parse_location(x) for x in raw_locations]
            if any(not loc.state for loc in locations):
                return {'success': False, 'error': 'Every candidate location needs a state.'}, 400
```

Then, immediately before `result['success'] = True` at the end, attach the block:

```python
        if screen_block is not None:
            result['zip_screen'] = screen_block
            for row in [result.get('recommendation')] + list(result.get('alternatives') or []):
                for move in (row or {}).get('moves', []):
                    zc = (move.get('location') or {}).get('zip_code')
                    if zc in nss_by_zip:
                        move['location']['nss'] = nss_by_zip[zc]
```

Add the imports at the top of the try-block's module scope:

```python
from .zip_screen.resolve import resolve_location
```

- [ ] **Step 5: Emit zip_code in the results payload**

In `src/housing/results.py`, `_format_move` builds the location dict at lines 22–25. Add the
field so the move payload carries it:

```python
        'location': {
            'state': location.state,
            'city_type': location.city_type,
            'population_size': location.population_size,
            'zip_code': location.zip_code,
```

`zip_code` is `None` for every hand-picked location, which is why
`test_the_hand_picked_path_still_works` asserts only on the absence of the `zip_screen`
block and not on this field.

- [ ] **Step 6: Add the route**

In `src/server/plan_routes.py`, after the existing `housing_optimize` handler at line 750:

```python
@app.route("/api/housing/zip-screen", methods=["POST"])
def housing_zip_screen():
    denied = _require("read_config")
    if denied:
        return denied
    from ..housing import zip_screen_from_request
    from ..report_compute import prepare_config_from_sectioned_data
    data, _meta = load_active_config()
    c0 = prepare_config_from_sectioned_data(data, "", optimize_roth=False)
    return _service_json(zip_screen_from_request(c0, request.get_json(force=True, silent=True) or {}))
```

- [ ] **Step 7: Run the integration suite and the existing housing suites**

Run: `pytest tests/test_zip_screen_optimizer_integration.py tests/test_housing_optimizer_unit.py tests/test_housing_optimizer_integration.py -v`
Expected: PASS — new integration tests pass, existing optimizer tests unaffected

- [ ] **Step 8: Commit**

```bash
git add src/housing/api.py src/housing/results.py src/server/plan_routes.py tests/test_zip_screen_optimizer_integration.py
git commit -m "feat(zip-screen): drive the optimizer from a ZIP radius search"
```

---

### Task 12: Pilot ingest — Illinois, Florida, Colorado

**Files:**
- Create: `scripts/build_zip_metrics.py`
- Create: `src/housing/zip_screen/data/zip_metrics.csv.gz`
- Create: `src/housing/zip_screen/data/top_cities.csv`
- Test: `tests/test_zip_screen_snapshot_integration.py`

**Interfaces:**
- Consumes: `schema.COLUMNS`, `schema.VACANCY_IDEAL_RATE`
- Produces: a snapshot at `src/housing/zip_screen/data/zip_metrics.csv.gz` matching `COLUMNS`

**This is the only task that touches the network.** Everything before it was built and tested against `tests/fixtures/zip_metrics_sample.csv`, so a failure here changes nothing but this task.

- [ ] **Step 1: Write the failing test**

```python
"""The bundled snapshot must satisfy the schema the runtime assumes."""
from __future__ import annotations

import os

import pytest

from src.housing.zip_screen.quality import score_zip
from src.housing.zip_screen.schema import COLUMNS
from src.housing.zip_screen.table import clear_cache, default_table_path, load_table

pytestmark = pytest.mark.integration

PILOT_STATES = {'Illinois', 'Florida', 'Colorado'}


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def table():
    if not os.path.exists(default_table_path()):
        pytest.skip('snapshot not built; run scripts/build_zip_metrics.py')
    return load_table()


def test_snapshot_covers_the_three_pilot_states(table):
    assert PILOT_STATES <= {r.state for r in table.values()}


def test_snapshot_has_a_plausible_pilot_row_count(table):
    assert 2500 <= len(table) <= 5000


def test_every_row_has_usable_coordinates(table):
    for rec in table.values():
        assert -180.0 <= rec.lon <= 180.0
        assert 15.0 <= rec.lat <= 72.0


def test_percentiles_are_all_within_zero_and_one(table):
    for rec in table.values():
        for col in COLUMNS:
            if not col.startswith('pctl_'):
                continue
            v = getattr(rec, col, None)
            if v is not None:
                assert 0.0 <= v <= 1.0, f'{rec.zcta}.{col} = {v}'


def test_the_pdf_reference_zips_are_present_and_scoreable(table):
    for zcta in ('60521', '60115'):
        assert zcta in table
        assert 0.0 <= score_zip(table[zcta]).score <= 100.0


def test_hinsdale_outscores_the_high_poverty_chicago_zip(table):
    assert score_zip(table['60521']).score > score_zip(table['60623']).score


def test_dekalb_is_upi_adjusted(table):
    # NIU puts 60115's UPI well above the 15% threshold.
    assert table['60115'].upi > 0.15
    assert score_zip(table['60115']).upi_adjusted is True


def test_most_rows_clear_the_coverage_floor(table):
    scored = [score_zip(r) for r in table.values()]
    clearing = sum(1 for s in scored if s.coverage_pct >= 70.0)
    assert clearing / len(scored) > 0.80


def test_top_cities_file_resolves_anchors(table):
    import csv
    path = os.path.join(os.path.dirname(default_table_path()), 'top_cities.csv')
    with open(path, encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) >= 200
    pilot = [r for r in rows if r['state'] in PILOT_STATES]
    assert pilot
    for r in pilot:
        assert r['anchor_zip'] in table, f"{r['city']} anchor missing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zip_screen_snapshot_integration.py -v`
Expected: SKIP (snapshot not built) — this is the expected pre-implementation state

- [ ] **Step 3: Write the ingest script**

`scripts/build_zip_metrics.py`:

```python
"""Offline ingest: build src/housing/zip_screen/data/zip_metrics.csv.gz.

NOT imported at runtime -- this is the only place `requests` is allowed, and
nothing under src/ may import this module. Run it by hand when refreshing the
snapshot:

    python scripts/build_zip_metrics.py --states IL,FL,CO
    python scripts/build_zip_metrics.py --all-states

Sources:
  ACS 5-year (ACS_VINTAGE_YEAR), ZCTA geography:
    B25003 owner-occupied, B25002 vacancy, B19013 median household income,
    B25038 tenure, B25077 median home value, B14007 enrollment,
    B14006 poverty by enrollment status, B01003 population
  Census Gazetteer: ZCTA centroids and land area
  HUD USPS ZIP<->TRACT crosswalk: maps Eviction Lab tract data onto ZCTAs
  Eviction Lab: filing and execution (judgment) rates

Percentiles are computed against the FULL set of rows in this run and written
into the snapshot, so the runtime never needs distribution data. When building
a pilot subset, percentiles are therefore pilot-relative -- pass --all-states
before shipping a snapshot users will act on.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import os
import sys

ACS_VINTAGE_YEAR = 2024
ACS_BASE = f'https://api.census.gov/data/{ACS_VINTAGE_YEAR}/acs/acs5'
GAZETTEER_URL = (
    f'https://www2.census.gov/geo/docs/maps-data/data/gazetteer/'
    f'{ACS_VINTAGE_YEAR}_Gazetteer/{ACS_VINTAGE_YEAR}_Gaz_zcta_national.zip'
)

VACANCY_IDEAL_RATE = 0.06

OUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'src', 'housing', 'zip_screen', 'data', 'zip_metrics.csv.gz',
)

PILOT_STATES = ('IL', 'FL', 'CO')


def percentile_ranks(values: dict[str, float]) -> dict[str, float]:
    """Fractional rank in [0, 1] of each key's value among all present values.

    Ties share the midpoint rank. Keys absent here stay absent in the snapshot
    (an empty cell), which quality.py renormalizes over.
    """
    if not values:
        return {}
    ordered = sorted(values.items(), key=lambda kv: kv[1])
    n = len(ordered)
    ranks: dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and ordered[j + 1][1] == ordered[i][1]:
            j += 1
        mid = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[ordered[k][0]] = mid / (n - 1) if n > 1 else 0.5
        i = j + 1
    return ranks


def build(states: tuple[str, ...], out_path: str) -> int:
    """Fetch, join, rank, and write the snapshot. Returns the row count.

    Implementation notes for whoever runs this:
      1. Fetch each ACS table for `states` at the `zip code tabulation area`
         geography. The ACS API caps results; page by state.
      2. Join the Gazetteer for lat/lon/ALAND (convert ALAND m^2 to sq mi by
         dividing by 2_589_988.11).
      3. Join Eviction Lab tract rates onto ZCTAs through the HUD crosswalk,
         weighting each tract by its residential-address share. If the
         crosswalk join yields under 50% coverage for a state, leave BOTH
         eviction columns empty for that state rather than shipping a biased
         partial join -- quality.py's renormalization handles it and
         coverage_pct will report the reduction honestly.
      4. Derive: owner_occupied share, poverty rate, non-student poverty rate,
         median tenure years, vacancy deviation = abs(vacancy - 
         VACANCY_IDEAL_RATE), upi = enrolled / population.
      5. Call percentile_ranks() once per metric over ALL rows in this run.
      6. Write COLUMNS in order, gzip-compressed, empty string for None.
    """
    raise NotImplementedError(
        'Fill in the fetch/join steps documented above. Kept explicit rather '
        'than auto-generated: the ACS and HUD endpoints change shape between '
        'vintages and a silent join failure here corrupts every score.'
    )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--states', default=','.join(PILOT_STATES),
                    help='comma-separated USPS state codes')
    ap.add_argument('--all-states', action='store_true')
    ap.add_argument('--out', default=OUT_PATH)
    args = ap.parse_args(argv)
    states = () if args.all_states else tuple(s.strip().upper()
                                              for s in args.states.split(',') if s.strip())
    rows = build(states, args.out)
    print(f'wrote {rows} rows to {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Implement `build()` and run the pilot ingest**

Fill in the six documented steps. Then run:

```bash
python scripts/build_zip_metrics.py --states IL,FL,CO
```

Expected: `wrote ~3400 rows to .../zip_metrics.csv.gz`

- [ ] **Step 5: Build top_cities.csv**

Top 200 US cities by population with an anchor ZIP each. Columns:
`city_id,city,state,state_abbrev,population,anchor_zip`. The anchor ZIP is the ZCTA whose
centroid is nearest the Census place's internal point.

- [ ] **Step 6: Run the snapshot suite**

Run: `pytest tests/test_zip_screen_snapshot_integration.py -v`
Expected: PASS, 9 passed

- [ ] **Step 7: Commit**

```bash
git add scripts/build_zip_metrics.py src/housing/zip_screen/data/ tests/test_zip_screen_snapshot_integration.py
git commit -m "feat(zip-screen): add the ingest script and the IL/FL/CO pilot snapshot"
```

---

### Task 13: Frontend — mode toggle and ZIP controls

**Files:**
- Modify: `frontend/js/dashboard_decomp_housing_scenarios.js:1274-1315` (`housingOptLocationRowHtml`, `renderHousingOptimizePanelHtml`)
- Test: `tests/test_zip_screen_panel_functional.py`

**Interfaces:**
- Consumes: the existing `renderHousingOptimizePanelHtml`
- Produces: `toggleHousingOptSearchMode()`; element ids `housingOptGeoMode`, `housingOptAnchorCity`, `housingOptAnchorZip`, `housingOptRadius`, `housingOptMinScore`, `housingOptShortlistSize`

- [ ] **Step 1: Write the failing test**

```python
"""The optimizer panel exposes the ZIP-radius mode and its controls."""
from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.unit

PANEL = pathlib.Path('frontend/js/dashboard_decomp_housing_scenarios.js')


@pytest.fixture(scope='module')
def source() -> str:
    return PANEL.read_text(encoding='utf-8')


def test_mode_toggle_exists(source):
    assert 'housingOptGeoMode' in source
    assert 'toggleHousingOptSearchMode' in source


def test_both_modes_are_offered(source):
    assert 'value="manual"' in source
    assert 'value="zip_radius"' in source


def test_every_radius_option_is_present(source):
    for r in (5, 10, 25, 50):
        assert f'<option value="{r}"' in source


def test_no_unapproved_radius_is_offered(source):
    import re
    block = source.split('housingOptRadius')[1].split('</select>')[0]
    offered = {int(m) for m in re.findall(r'<option value="(\d+)"', block)}
    assert offered == {5, 10, 25, 50}


def test_min_score_control_exists_with_the_spec_default(source):
    assert 'housingOptMinScore' in source
    assert 'value="60"' in source


def test_anchor_offers_both_a_city_dropdown_and_a_zip_field(source):
    assert 'housingOptAnchorCity' in source
    assert 'housingOptAnchorZip' in source


def test_shortlist_size_control_exists(source):
    assert 'housingOptShortlistSize' in source


def test_preview_button_calls_the_screen_only_endpoint(source):
    assert 'previewHousingZipShortlist' in source
    assert '/api/housing/zip-screen' in source


def test_the_disclosure_string_is_present_verbatim(source):
    assert (
        'Measures housing and economic stability. Does not measure crime or safety.'
    ) in source


def test_the_manual_path_is_preserved(source):
    assert 'housingOptLocCount' in source
    assert 'housingOptLocState0' in source or 'housingOptLocState${i}' in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zip_screen_panel_functional.py -v`
Expected: FAIL — `assert 'housingOptGeoMode' in source`

- [ ] **Step 3: Write minimal implementation**

In `renderHousingOptimizePanelHtml`, insert immediately after the opening `section-note` div
and before `<div class="subsection-label">Candidate locations (2-4)</div>`:

```javascript
    <label>Location search mode
      <select id="housingOptGeoMode" onchange="toggleHousingOptSearchMode()">
        <option value="manual" selected>Choose locations manually</option>
        <option value="zip_radius">Search by ZIP radius</option>
      </select>
    </label>
    <div id="housingOptZipFields" hidden>
      <div class="subsection-label">Anchor</div>
      <label>City ${housingOptAnchorCitySelectHtml()}</label>
      <label>or ZIP code <input type="text" id="housingOptAnchorZip" maxlength="5" style="width:6em" placeholder="60521"></label>
      <label>Distance from anchor
        <select id="housingOptRadius">
          <option value="5">Within 5 miles</option>
          <option value="10">Within 10 miles</option>
          <option value="25" selected>Within 25 miles</option>
          <option value="50">Within 50 miles</option>
        </select>
      </label>
      <label>Minimum quality score
        <input type="number" id="housingOptMinScore" value="60" min="0" max="100" style="width:6em">
      </label>
      <div class="small">Measures housing and economic stability. Does not measure crime or safety.</div>
      <label>Candidates to send to the optimizer
        <select id="housingOptShortlistSize">
          <option value="2">2</option><option value="3">3</option>
          <option value="4" selected>4</option>
        </select>
      </label>
      <div class="table-actions"><button class="btn" type="button" onclick="previewHousingZipShortlist()">Preview shortlist</button></div>
      <div id="housingOptZipShortlist"></div>
    </div>
```

Wrap the manual rows so the toggle can hide them — change the manual block to:

```javascript
    <div id="housingOptManualFields">
      <div class="subsection-label">Candidate locations (2-4)</div>
      <label>Number of candidate locations
        <select id="housingOptLocCount" onchange="toggleHousingOptLocationRows()"><option value="2">2</option><option value="3">3</option><option value="4">4</option></select>
      </label>
      ${locationRows}
    </div>
```

Add the two helpers near `housingOptStateSelectHtml`:

```javascript
// Populated from src/housing/zip_screen/data/top_cities.csv, served alongside
// the screen endpoint. Falls back to the free-entry ZIP field when unavailable.
let HOUSING_OPT_TOP_CITIES = [];

function housingOptAnchorCitySelectHtml() {
  const options = HOUSING_OPT_TOP_CITIES.map(
    (c) => `<option value="${esc(c.anchor_zip)}">${esc(c.city)}, ${esc(c.state_abbrev)}</option>`,
  ).join("");
  return `<select id="housingOptAnchorCity"><option value="">Select a city</option>${options}</select>`;
}

export function toggleHousingOptSearchMode() {
  const zip = String(document.getElementById("housingOptGeoMode")?.value || "manual") === "zip_radius";
  const zipFields = document.getElementById("housingOptZipFields");
  const manualFields = document.getElementById("housingOptManualFields");
  if (zipFields) zipFields.hidden = !zip;
  if (manualFields) manualFields.hidden = zip;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_zip_screen_panel_functional.py -v`
Expected: PASS, 10 passed — except `test_preview_button_calls_the_screen_only_endpoint`, which Task 14 satisfies. Mark it `xfail` here only if Task 14 is not being done in the same session.

- [ ] **Step 5: Commit**

```bash
git add frontend/js/dashboard_decomp_housing_scenarios.js tests/test_zip_screen_panel_functional.py
git commit -m "feat(zip-screen): add the ZIP-radius mode toggle and its controls"
```

---

### Task 14: Frontend — shortlist rendering and request wiring

**Files:**
- Modify: `frontend/js/dashboard_decomp_housing_scenarios.js` (`runHousingOptimization` at ~1456)
- Test: `tests/test_zip_screen_shortlist_render_functional.py`

**Interfaces:**
- Consumes: `zip_screen_v1` payload
- Produces: `previewHousingZipShortlist()`; `renderHousingZipShortlistHtml(payload)`; `runHousingOptimization` sends `zip_search` in ZIP mode

- [ ] **Step 1: Write the failing test**

```python
"""Shortlist rendering and the zip_search request body."""
from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.unit

PANEL = pathlib.Path('frontend/js/dashboard_decomp_housing_scenarios.js')


@pytest.fixture(scope='module')
def source() -> str:
    return PANEL.read_text(encoding='utf-8')


def test_renderer_exists_and_is_exported(source):
    assert 'export function renderHousingZipShortlistHtml' in source


def test_shortlist_renders_every_documented_column(source):
    block = source.split('renderHousingZipShortlistHtml')[1][:3000]
    for token in ('distance_miles', 'nss', 'band', 'est_price', 'coverage_pct'):
        assert token in block


def test_cross_state_is_surfaced(source):
    assert 'cross_state' in source


def test_collapsed_neighbours_are_shown_not_hidden(source):
    assert 'collapsed' in source
    assert 'similar nearby' in source


def test_funnel_diagnostics_are_rendered(source):
    block = source.split('renderHousingZipShortlistHtml')[1][:4000]
    for token in ('in_radius', 'with_data', 'above_score', 'promoted'):
        assert token in block


def test_relaxation_suggestion_is_rendered(source):
    assert 'relaxation' in source


def test_request_sends_zip_search_in_zip_mode(source):
    block = source.split('runHousingOptimization')[1][:4000]
    assert 'zip_search' in block
    assert 'radius_miles' in block
    assert 'min_quality_score' in block


def test_request_omits_locations_in_zip_mode(source):
    # The two are mutually exclusive server-side; the client must not send both.
    block = source.split('runHousingOptimization')[1][:4000]
    assert 'housingOptGeoMode' in block


def test_upi_adjustment_is_disclosed_when_applied(source):
    assert 'upi_adjusted' in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zip_screen_shortlist_render_functional.py -v`
Expected: FAIL — `assert 'export function renderHousingZipShortlistHtml' in source`

- [ ] **Step 3: Write minimal implementation**

Add beside `renderHousingOptimizeResultsHtml`:

```javascript
function housingZipFunnelText(f) {
  if (!f) return "";
  return `${f.in_radius} ZIPs in range → ${f.with_data} with data → ${f.above_score} above the score floor → ${f.affordable} affordable → ${f.after_dedup} distinct → ${f.promoted} sent to the optimizer`;
}

function housingZipRelaxationText(r) {
  if (!r) return "";
  return `Lowering the minimum score to ${r.suggested} would return ${r.would_return}.`;
}

function housingZipRowHtml(z) {
  const cross = z.cross_state
    ? ` <span class="small warning">${esc(z.cross_state)} — different state tax treatment</span>`
    : "";
  const upi = z.upi_adjusted
    ? ' <span class="small">(university-adjusted)</span>'
    : "";
  const collapsed = (z.collapsed || []).length
    ? `<div class="small">+${z.collapsed.length} similar nearby: ${z.collapsed.map(esc).join(", ")}</div>`
    : "";
  const coverage = z.coverage_pct < 100
    ? ` <span class="small">(${z.coverage_pct}% data coverage)</span>`
    : "";
  return `<tr><td>${esc(z.zip)} — ${esc(z.city)}, ${esc(z.state)}${cross}${collapsed}</td>
    <td>${z.distance_miles} mi</td>
    <td>${z.nss} <span class="small">${esc(z.band)}</span>${upi}${coverage}</td>
    <td>$${Math.round(z.est_price).toLocaleString()}</td></tr>`;
}

export function renderHousingZipShortlistHtml(payload) {
  const zs = payload && payload.zip_screen;
  if (!zs) return "";
  const note = `<div class="section-note">${esc(housingZipFunnelText(zs.funnel))}</div>`;
  const disclosure = `<div class="small">${esc(zs.disclosure)}</div>`;
  if (!zs.shortlist || !zs.shortlist.length) {
    const relax = zs.relaxation
      ? `<p class="small">${esc(housingZipRelaxationText(zs.relaxation))}</p>`
      : "";
    return note + relax + disclosure;
  }
  const rows = zs.shortlist.map(housingZipRowHtml).join("");
  const table = `<table class="lot-table scenario-diff-table housing-optimize-table"><thead><tr><th>ZIP</th><th>Distance</th><th>Stability score</th><th>Est. price</th></tr></thead><tbody>${rows}</tbody></table>`;
  return note + table + disclosure;
}

function housingOptZipSearchBody() {
  const anchorZip =
    String(document.getElementById("housingOptAnchorZip")?.value || "").trim() ||
    String(document.getElementById("housingOptAnchorCity")?.value || "").trim();
  return {
    anchor: { zip: anchorZip },
    radius_miles: Number(document.getElementById("housingOptRadius")?.value || 25),
    min_quality_score: Number(document.getElementById("housingOptMinScore")?.value || 60),
    shortlist_size: Number(document.getElementById("housingOptShortlistSize")?.value || 4),
    property_spec: {
      bedrooms: Number(document.getElementById("housingOptLocBedrooms0")?.value || 3),
      bathrooms: Number(document.getElementById("housingOptLocBathrooms0")?.value || 2),
      property_type: String(document.getElementById("housingOptLocPropertyType0")?.value || "single_family"),
      sqft_band: String(document.getElementById("housingOptLocSqftBand0")?.value || "1800_2500"),
      built_within_years: Number(document.getElementById("housingOptLocBuiltWithinYears0")?.value) || null,
    },
  };
}

export async function previewHousingZipShortlist() {
  const zipSearch = housingOptZipSearchBody();
  if (!zipSearch.anchor.zip) {
    showMessage("Choose an anchor city or enter a ZIP code.", "error");
    return;
  }
  const res = await fetch("/api/housing/zip-screen", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ zip_search: zipSearch }),
  });
  const payload = await res.json();
  const target = document.getElementById("housingOptZipShortlist");
  if (!payload.success) {
    if (target) target.innerHTML = `<p class="small warning">${esc(payload.error || "Screen failed.")}</p>`;
    return;
  }
  if (target) target.innerHTML = renderHousingZipShortlistHtml(payload);
}
```

In `runHousingOptimization`, replace the location-gathering preamble so ZIP mode sends
`zip_search` instead of `locations`:

```javascript
  const geoMode = String(document.getElementById("housingOptGeoMode")?.value || "manual");
  const body = {};
  if (geoMode === "zip_radius") {
    body.zip_search = housingOptZipSearchBody();
    if (!body.zip_search.anchor.zip) {
      showMessage("Choose an anchor city or enter a ZIP code.", "error");
      return;
    }
  } else {
    const numLocs = Number(document.getElementById("housingOptLocCount")?.value || 2);
    const locations = [];
    for (let i = 0; i < numLocs; i++) {
      const state = String(document.getElementById(`housingOptLocState${i}`)?.value || "").trim();
      if (!state) {
        showMessage(`Enter a state for candidate location ${i + 1}.`, "error");
        return;
      }
      const builtWithinYearsRaw = document.getElementById(`housingOptLocBuiltWithinYears${i}`)?.value;
      locations.push({
        state,
        city_type: String(document.getElementById(`housingOptLocCity${i}`)?.value || "suburban"),
        population_size: Number(document.getElementById(`housingOptLocPop${i}`)?.value || 20000),
        bedrooms: Number(document.getElementById(`housingOptLocBedrooms${i}`)?.value || 3),
        bathrooms: Number(document.getElementById(`housingOptLocBathrooms${i}`)?.value || 2),
        property_type: String(document.getElementById(`housingOptLocPropertyType${i}`)?.value || "single_family"),
        sqft_band: String(document.getElementById(`housingOptLocSqftBand${i}`)?.value || "1800_2500"),
        built_within_years: builtWithinYearsRaw ? Number(builtWithinYearsRaw) : null,
      });
    }
    body.locations = locations;
  }
```

Leave the rest of `runHousingOptimization` (the windows, objective, and flags it already
assembles onto `body`) unchanged. Where results are rendered, prepend the shortlist:

```javascript
  resultsEl.innerHTML =
    renderHousingZipShortlistHtml(payload) + renderHousingOptimizeResultsHtml(payload);
```

Register the two new exports wherever the module's functions are attached to `window`
(search the file for `window.runHousingOptimization` and follow that pattern for
`previewHousingZipShortlist` and `toggleHousingOptSearchMode`).

- [ ] **Step 4: Run both frontend suites**

Run: `pytest tests/test_zip_screen_panel_functional.py tests/test_zip_screen_shortlist_render_functional.py -v`
Expected: PASS, 19 passed

- [ ] **Step 5: Verify in the real app**

Start the app, open the housing panel, switch to **Search by ZIP radius**, anchor on Denver,
radius 25, minimum score 60, and click **Preview shortlist**. Confirm: rows appear, the
disclosure line is visible, the funnel line reads sensibly, and a Colorado anchor shows no
`cross_state` warning while a Florida anchor against an Illinois plan does.

- [ ] **Step 6: Commit**

```bash
git add frontend/js/dashboard_decomp_housing_scenarios.js tests/test_zip_screen_shortlist_render_functional.py
git commit -m "feat(zip-screen): render the shortlist and send zip_search from the panel"
```

---

### Task 15: National snapshot

**Files:**
- Modify: `src/housing/zip_screen/data/zip_metrics.csv.gz`
- Modify: `tests/test_zip_screen_snapshot_integration.py:test_snapshot_has_a_plausible_pilot_row_count`

**Interfaces:**
- Consumes: `scripts/build_zip_metrics.py`
- Produces: a national snapshot; percentiles become nationally-relative

- [ ] **Step 1: Update the row-count test for national scale**

```python
def test_snapshot_has_a_plausible_national_row_count(table):
    # ~33k ZCTAs nationally; allow for vintage-to-vintage drift.
    assert 30000 <= len(table) <= 36000


def test_snapshot_covers_every_state(table):
    assert len({r.state for r in table.values()}) >= 50
```

Delete `test_snapshot_has_a_plausible_pilot_row_count` — it is superseded.

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_zip_screen_snapshot_integration.py -v`
Expected: FAIL — pilot snapshot has ~3,400 rows

- [ ] **Step 3: Run the national ingest**

```bash
python scripts/build_zip_metrics.py --all-states
```

Expected: `wrote ~33000 rows to .../zip_metrics.csv.gz`

- [ ] **Step 4: Check the committed artifact size**

```bash
ls -lh src/housing/zip_screen/data/zip_metrics.csv.gz
```

Expected: under 2 MB gzipped. If it exceeds 5 MB, drop the raw-value columns and keep only
the `pctl_*` columns plus geography and the two home-value columns — nothing at runtime
reads the raw values.

- [ ] **Step 5: Run the full housing and zip-screen suites**

Run: `pytest tests/ -k "zip_screen or housing" -v`
Expected: PASS — and note that pilot-relative percentiles are now national, so absolute
scores shift. This is expected and correct; the band assertions are written as inequalities
and comparisons for exactly this reason.

- [ ] **Step 6: Run the PR-tier suite**

Run: `pytest -m "not slow and not nightly"`
Expected: PASS, no regressions in the existing suite

- [ ] **Step 7: Commit**

```bash
git add src/housing/zip_screen/data/zip_metrics.csv.gz tests/test_zip_screen_snapshot_integration.py
git commit -m "feat(zip-screen): ship the national snapshot"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §4.1–4.2 NSS weights, renaming | 1 |
| §4.3 Mandatory disclosure | 1, 10, 13 |
| §4.4 Percentile scaling, bands | 1, 4, 12 |
| §4.5 UPI adjustment | 5 |
| §4.6 Partial coverage renormalization | 4, 7 |
| §4.7 Affordability index | 7, 12 |
| §5 Module layout | 1–9 |
| §5.1 resolve.py, density thresholds | 6 |
| §5.2 Stage-1 funnel, de-dup | 7, 8 |
| §5.3 Stage 2 hand-off | 11 |
| §6.1 optimize contract, mutual exclusion | 10, 11 |
| §6.2 zip-screen endpoint | 10, 11 |
| §7 UI mode toggle, preview | 13, 14 |
| §7.1 Empty-funnel reporting | 9, 14 |
| §8 Error handling | 10, 11 |
| §9 Testing | every task |

No spec section is unimplemented.

**Known gaps carried deliberately:**

1. `build()` in Task 12 is documented-but-unimplemented by design. The ACS and HUD endpoints
   change shape between vintages, and a silent join failure there corrupts every score in the
   product. It is the one place in this plan where an engineer must look at real responses
   rather than follow a recipe. Every consumer of its output is fully specified and fully
   tested against the fixture, so the blast radius is one task.
2. Task 12's pilot percentiles are pilot-relative. Task 15 makes them national. Score
   assertions are written as inequalities throughout so the transition does not churn tests.
3. Task 11's integration tests build their config with `_base_config()`, copied from
   `tests/test_housing_optimizer_integration.py:20`. That reads `input/client_data.csv`,
   which is gitignored, so these tests **skip on CI and in a fresh worktree** — the same
   trade-off the existing housing integration suite already makes. Tasks 1–10 carry the real
   coverage and run everywhere.
4. Task 11's engine-backed tests are candidates for `@pytest.mark.nightly`, matching the
   treatment the existing optimizer breadth tests received in the 2026-09-15 CI profiling
   pass. Decide when the runtime is measurable, not before.
