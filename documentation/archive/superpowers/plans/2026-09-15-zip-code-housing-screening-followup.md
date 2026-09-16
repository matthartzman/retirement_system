# ZIP-Code Screening Follow-Up: Anchor Data, City Dropdown, Property Controls

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three deferred findings from PR #119's final whole-branch review — fix `build_top_cities`'s wrong-anchor bug, serve `top_cities.csv` to the frontend so the city dropdown actually works, and add property-spec/price-range controls to the ZIP-radius panel so the affordability filter is reachable.

**Architecture:** Task 1 fixes the anchor-selection algorithm in the already-built ingest script and regenerates `top_cities.csv` from the already-shipped national snapshot (no re-run of the expensive ACS/Gazetteer ingest needed — only the place/REL/population lookups `build_top_cities` itself uses). Task 2 adds a `GET /api/housing/top-cities` route and wires the frontend to fetch it and populate the existing (currently permanently-empty) `HOUSING_OPT_TOP_CITIES` array. Task 3 adds visible property-spec and price-range controls to the ZIP-radius panel and updates the request body builder to read from them instead of silently reusing hidden manual-entry fields.

**Tech Stack:** Python 3.12 (ingest script, pytest), Flask (existing routes), vanilla ES modules (existing frontend).

**Base:** this branch is built on top of PR #119 (`worktree-zip-code-housing-screening`, merged into this worktree at commit `8b7ff52`) — not on `main`. `src/housing/zip_screen/` and everything else from that feature already exists here.

## Global Constraints

- No new runtime dependency under `src/` (matches the parent feature's constraint).
- The `GET /api/housing/top-cities` route follows the EXACT auth/response pattern of the existing `/api/housing/optimize` and `/api/housing/zip-screen` routes in `src/server/plan_routes.py:750-769` (`_require("read_config")`, `_service_json(...)`).
- The disclosure string (`Measures housing and economic stability. Does not measure crime or safety.`) is unaffected by this plan — no task touches it.
- Tests live flat in `tests/test_*.py`, carry a `pytestmark` tier marker, run via `pytest` from the repo root.
- The anchor-selection fix must not require re-running the national ACS ingest (Task 12/15's multi-minute network pull) — it operates only on already-cached lookups plus the already-committed `zip_metrics.csv.gz`.

---

## File Structure

**Modify:**

| Path | Change |
|---|---|
| `scripts/build_zip_metrics.py` | Rewrite `build_top_cities`'s anchor selection from nearest-centroid to largest-land-overlap (reusing the ZCTA↔place relationship file `build()` already fetches); add a `--top-cities-only` CLI flag so this can be re-run without a full ingest |
| `src/housing/zip_screen/data/top_cities.csv` | Regenerated with corrected anchors |
| `src/housing/api.py` | Add `top_cities_payload()` |
| `src/housing/__init__.py` | Export `top_cities_payload` |
| `src/server/plan_routes.py` | Add `GET /api/housing/top-cities` |
| `frontend/js/dashboard_decomp_housing_scenarios.js` | Fetch and populate `HOUSING_OPT_TOP_CITIES` on first render of the ZIP panel; add property-spec/price-range controls to `#housingOptZipFields`; update `housingOptZipSearchBody()` to read from them |

---

### Task 1: Fix the anchor heuristic and regenerate top_cities.csv

**Files:**
- Modify: `scripts/build_zip_metrics.py:505-568` (`build_top_cities`, `main`)
- Modify: `src/housing/zip_screen/data/top_cities.csv` (regenerated output)
- Test: `tests/test_zip_screen_top_cities_anchor_unit.py`

**Interfaces:**
- Consumes: `_relationship`, `_gazetteer`, `_acs_table`, `_place_name`, `STATE_FIPS`, `ABBREV_TO_FIPS`, `P_PLACE`, `REL_ZCTA_PLACE`, `GAZETTEER_PLACE_URL` (all already defined in `scripts/build_zip_metrics.py`)
- Produces: `build_top_cities(out_path, snapshot_path, limit=200)` keeps its existing signature and return type (row count written); its INTERNAL anchor-selection algorithm changes

**The bug:** the current implementation picks each city's anchor ZCTA by nearest Gazetteer centroid to the Census place's `INTPTLAT`/`INTPTLONG`. This is wrong two ways: (1) a place's legal boundary can pull its internal point somewhere unrepresentative — San Francisco's city limits include the Farallon Islands 27 miles offshore, which skews `INTPTLAT`/`INTPTLONG` enough that the nearest ZCTA centroid is `94924` (Bolinas, Marin County, population 1,372 — across the Golden Gate); (2) nothing filters on population, so a city like Jacksonville can anchor on a PO-box-only ZIP with zero residents.

**The fix:** reuse the ZCTA↔place relationship file (`REL_ZCTA_PLACE`, already fetched by `build()` at line 326 via `_relationship(REL_ZCTA_PLACE, 'rel_zcta_place.txt')` to build a ZCTA→best-place lookup) but invert it: for each PLACE, find the ZCTA with the largest `AREALAND_PART` (land-area overlap) that also has nonzero population in the snapshot. Land-area overlap directly answers "is this ZIP really part of the city," which nearest-centroid does not.

- [ ] **Step 1: Write the failing test**

```python
"""build_top_cities anchors on land-overlap, not centroid distance."""
from __future__ import annotations

import csv
import gzip
import io
import os
import tempfile

import pytest

from scripts.build_zip_metrics import build_top_cities

pytestmark = pytest.mark.unit


def _write_snapshot(path, rows):
    """A minimal gzipped CSV matching the real snapshot's column set, for
    just the fields build_top_cities actually reads."""
    fieldnames = ['zcta', 'state', 'state_abbrev', 'lat', 'lon',
                  'zcta_population', 'place_gid', 'place_area_m2']
    with gzip.open(path, 'wt', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Isolate the REL/Gazetteer/ACS fetch helpers this test stubs out."""
    d = tmp_path
    monkeypatch.chdir(d)
    return d


def test_anchor_prefers_largest_land_overlap_over_nearest_centroid(workdir, monkeypatch):
    # Two ZCTAs "near" a fictional city's centroid: 00001 is geographically
    # nearer to the place's INTPTLAT/INTPTLONG but has almost no land overlap
    # with the place (e.g. it's a neighboring town's ZIP that happens to be
    # close by); 00002 is farther from the raw centroid but has the large
    # land-overlap that actually makes it "the city's ZIP."
    import scripts.build_zip_metrics as bzm

    snapshot_path = os.path.join(workdir, 'zip_metrics.csv.gz')
    _write_snapshot(snapshot_path, [
        {'zcta': '00001', 'state': 'Illinois', 'state_abbrev': 'IL',
         'lat': '41.900', 'lon': '-87.900', 'zcta_population': '500'},
        {'zcta': '00002', 'state': 'Illinois', 'state_abbrev': 'IL',
         'lat': '41.700', 'lon': '-87.700', 'zcta_population': '40000'},
    ])

    monkeypatch.setattr(bzm, '_gazetteer', lambda url, name: [
        {'GEOID': '1729000', 'USPS': 'IL', 'NAME': 'Faketown city, Illinois',
         'INTPTLAT': '41.905', 'INTPTLONG': '-87.905'},
    ])
    monkeypatch.setattr(bzm, '_acs_table', lambda table, prefixes: {
        f'{bzm.P_PLACE}1729000': {'001': 45000.0},
    })
    # 00001: tiny overlap with the place. 00002: dominant overlap.
    monkeypatch.setattr(bzm, '_relationship', lambda url, name: (
        ['GEOID_ZCTA5_20', 'GEOID_PLACE_20', 'NAMELSAD_PLACE_20', 'AREALAND_PART'],
        [
            ['00001', '00001', '1729000', 'Faketown city', '5000'],
            ['00002', '00002', '1729000', 'Faketown city', '5000000'],
        ],
    ))

    out_path = os.path.join(workdir, 'top_cities.csv')
    n = build_top_cities(out_path, snapshot_path, limit=10)

    assert n == 1
    with open(out_path, newline='', encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]['anchor_zip'] == '00002'
    assert rows[0]['city'] == 'Faketown'


def test_anchor_never_selects_a_zero_population_zcta(workdir, monkeypatch):
    import scripts.build_zip_metrics as bzm

    snapshot_path = os.path.join(workdir, 'zip_metrics.csv.gz')
    _write_snapshot(snapshot_path, [
        {'zcta': '00003', 'state': 'Illinois', 'state_abbrev': 'IL',
         'lat': '41.900', 'lon': '-87.900', 'zcta_population': '0'},
        {'zcta': '00004', 'state': 'Illinois', 'state_abbrev': 'IL',
         'lat': '41.910', 'lon': '-87.910', 'zcta_population': '12000'},
    ])
    monkeypatch.setattr(bzm, '_gazetteer', lambda url, name: [
        {'GEOID': '1729000', 'USPS': 'IL', 'NAME': 'Faketown city, Illinois',
         'INTPTLAT': '41.900', 'INTPTLONG': '-87.900'},
    ])
    monkeypatch.setattr(bzm, '_acs_table', lambda table, prefixes: {
        f'{bzm.P_PLACE}1729000': {'001': 45000.0},
    })
    # 00003 (zero population) has the largest raw overlap; 00004 is second.
    monkeypatch.setattr(bzm, '_relationship', lambda url, name: (
        ['GEOID_ZCTA5_20', 'GEOID_PLACE_20', 'NAMELSAD_PLACE_20', 'AREALAND_PART'],
        [
            ['00003', '00003', '1729000', 'Faketown city', '9000000'],
            ['00004', '00004', '1729000', 'Faketown city', '3000000'],
        ],
    ))

    out_path = os.path.join(workdir, 'top_cities.csv')
    build_top_cities(out_path, snapshot_path, limit=10)

    with open(out_path, newline='', encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]['anchor_zip'] == '00004'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zip_screen_top_cities_anchor_unit.py -v`
Expected: FAIL — the current implementation ignores `_relationship` entirely for anchor selection and would pick `00001`/`00003` (nearest centroid) instead of `00002`/`00004`.

- [ ] **Step 3: Rewrite `build_top_cities`**

Replace the function body (lines 505-549 in the current file — read the file first to confirm exact current line numbers, they may have shifted) with:

```python
def build_top_cities(out_path: str, snapshot_path: str, limit: int = 200) -> int:
    """Largest places in the snapshot's states, each anchored to a ZCTA.

    The anchor is the ZCTA with the LARGEST LAND-AREA OVERLAP with the
    place (from the same ZCTA<->place relationship file `build()` uses for
    state/place assignment), restricted to ZCTAs with nonzero population
    that are present in the snapshot.

    This is deliberately NOT nearest-centroid-to-the-place's-internal-point:
    a place's legal boundary can pull its internal point somewhere
    unrepresentative (San Francisco's city limits include the Farallon
    Islands 27 miles offshore, which used to anchor "San Francisco" on
    Bolinas, a Marin County ZIP across the Golden Gate) and nearest-centroid
    has no population floor (which used to anchor "Jacksonville" on a
    PO-box-only ZIP with zero residents). Land-area overlap directly answers
    "is this ZIP really part of the city," and the population floor rules
    out non-residential ZIPs outright.
    """
    with gzip.open(snapshot_path, 'rt', encoding='utf-8', newline='') as fh:
        snap = list(csv.DictReader(fh))
    zcta_pop = {r['zcta']: int(float(r['zcta_population'] or 0)) for r in snap}
    zcta_state = {r['zcta']: r['state_abbrev'] for r in snap}
    states = set(zcta_state.values())

    places = _gazetteer(GAZETTEER_PLACE_URL, 'gaz_place.zip')
    pop = {
        gid[len(P_PLACE):]: (row.get('001') or 0.0)
        for gid, row in _acs_table('B01003', (P_PLACE,)).items()
    }

    # Invert the ZCTA->place relationship into place->[(zcta, area)], kept to
    # only ZCTAs the snapshot actually carries with nonzero population.
    _, place_rows = _relationship(REL_ZCTA_PLACE, 'rel_zcta_place.txt')
    overlaps_by_place: dict[str, list[tuple[str, float]]] = {}
    for r in place_rows:
        zcta, place, area = r[1], r[9], r[16]
        if not zcta or not place:
            continue
        if zcta not in zcta_pop or zcta_pop[zcta] <= 0:
            continue
        try:
            a = float(area or 0)
        except ValueError:
            a = 0.0
        overlaps_by_place.setdefault(place, []).append((zcta, a))

    ranked = []
    for p in places:
        abbrev = p.get('USPS', '')
        if abbrev not in states:
            continue
        population = pop.get(p['GEOID'])
        if not population:
            continue
        if p['GEOID'] not in overlaps_by_place:
            continue  # no snapshot ZCTA overlaps this place at all
        ranked.append((population, p, abbrev))
    ranked.sort(key=lambda t: -t[0])
    ranked = ranked[:limit]

    with open(out_path, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['city_id', 'city', 'state', 'state_abbrev',
                         'population', 'anchor_zip'])
        for population, p, abbrev in ranked:
            anchor = max(overlaps_by_place[p['GEOID']], key=lambda t: t[1])[0]
            writer.writerow([p['GEOID'], _place_name(p['NAME']),
                             STATE_FIPS[ABBREV_TO_FIPS[abbrev]][1], abbrev,
                             int(population), anchor])
    return len(ranked)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_zip_screen_top_cities_anchor_unit.py -v`
Expected: PASS, 2 passed

- [ ] **Step 5: Add a `--top-cities-only` CLI flag**

In `main()`, add the flag and branch before the full `build()` call:

```python
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--states', default=','.join(PILOT_STATES),
                    help='comma-separated USPS state codes')
    ap.add_argument('--all-states', action='store_true')
    ap.add_argument('--out', default=OUT_PATH)
    ap.add_argument('--cities', type=int, default=200,
                    help='rows to write into top_cities.csv')
    ap.add_argument('--top-cities-only', action='store_true',
                    help='regenerate top_cities.csv from the existing snapshot '
                         'at --out, without re-running the full ACS ingest')
    args = ap.parse_args(argv)
    cities_path = os.path.join(os.path.dirname(args.out), 'top_cities.csv')
    if args.top_cities_only:
        n = build_top_cities(cities_path, args.out, args.cities)
        print(f'wrote {n} cities to {cities_path}')
        return 0
    states = () if args.all_states else tuple(s.strip().upper()
                                              for s in args.states.split(',') if s.strip())
    rows = build(states, args.out)
    print(f'wrote {rows} rows to {args.out}')
    n = build_top_cities(cities_path, args.out, args.cities)
    print(f'wrote {n} cities to {cities_path}')
    return 0
```

- [ ] **Step 6: Regenerate the real top_cities.csv**

```bash
python scripts/build_zip_metrics.py --top-cities-only --out src/housing/zip_screen/data/zip_metrics.csv.gz
```

This reuses the already-committed national snapshot and the OS-temp-dir caches Task 12/15 already warmed (Gazetteer place file, `B01003` place-population table, the ZCTA↔place relationship file) — expect a fast run, cache hits only, no multi-minute ACS pull. If the cache is cold (a different machine/session), this will re-fetch those three specific sources only, not the full multi-table ACS ingest `build()` does.

Spot-check the fix:

```bash
python -c "
import csv
with open('src/housing/zip_screen/data/top_cities.csv', encoding='utf-8') as f:
    rows = {r['city']: r for r in csv.DictReader(f)}
print('San Francisco ->', rows.get('San Francisco', {}).get('anchor_zip'))
print('Jacksonville ->', rows.get('Jacksonville', {}).get('anchor_zip'))
"
```

Expected: San Francisco's anchor is a real SF ZIP (94100s range), not `94924`; Jacksonville's anchor is a populated ZIP, not `32203`.

- [ ] **Step 7: Run the full zip_screen test suite to confirm no regression**

Run: `pytest tests/ -k "zip_screen" -v -m "not nightly"`
Expected: PASS, no regressions — `test_top_cities_file_resolves_anchors` (from the original feature) should still pass since it only checks that anchors resolve as keys in the snapshot table, which remains true.

- [ ] **Step 8: Commit**

```bash
git add scripts/build_zip_metrics.py src/housing/zip_screen/data/top_cities.csv tests/test_zip_screen_top_cities_anchor_unit.py
git commit -m "fix(zip-screen): anchor top_cities on land-overlap, not nearest centroid

Final whole-branch review finding: nearest-centroid-to-place-internal-point
anchored San Francisco on 94924 (Bolinas, Marin County -- SF's legal limits
include the Farallon Islands 27mi offshore, skewing the internal point) and
had no population floor, so Jacksonville anchored on a PO-box-only ZIP.
Anchor is now the ZCTA with the largest land-area overlap with the place
(from the same ZCTA<->place relationship file build() already uses for
state/place assignment), restricted to ZCTAs with nonzero population."
```

---

### Task 2: Serve top_cities.csv and wire the frontend dropdown

**Files:**
- Modify: `src/housing/api.py`
- Modify: `src/housing/__init__.py`
- Modify: `src/server/plan_routes.py:769` (after the existing `housing_zip_screen` route)
- Modify: `frontend/js/dashboard_decomp_housing_scenarios.js`
- Test: `tests/test_zip_screen_top_cities_api_contract.py`, `tests/test_zip_screen_top_cities_panel_functional.py`

**Interfaces:**
- Consumes: nothing new from earlier tasks in THIS plan; reads the corrected `src/housing/zip_screen/data/top_cities.csv` from Task 1
- Produces: `top_cities_payload() -> tuple[dict, int]`; route `GET /api/housing/top-cities`; frontend `loadHousingOptTopCities()` (populates `HOUSING_OPT_TOP_CITIES` and re-renders the select)

- [ ] **Step 1: Write the failing backend test**

```python
"""Wire contract for the top-cities listing endpoint."""
from __future__ import annotations

import pytest

from src.housing.api import top_cities_payload

pytestmark = pytest.mark.contract


def test_returns_success_and_a_city_list():
    payload, status = top_cities_payload()
    assert status == 200
    assert payload['success'] is True
    assert isinstance(payload['cities'], list)
    assert len(payload['cities']) > 0


def test_each_city_carries_the_documented_fields():
    payload, _ = top_cities_payload()
    row = payload['cities'][0]
    for key in ('city_id', 'city', 'state', 'state_abbrev', 'population', 'anchor_zip'):
        assert key in row


def test_cities_are_sorted_by_population_descending():
    payload, _ = top_cities_payload()
    pops = [c['population'] for c in payload['cities']]
    assert pops == sorted(pops, reverse=True)


def test_new_york_is_present_as_the_largest_city():
    payload, _ = top_cities_payload()
    assert payload['cities'][0]['city'] == 'New York'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zip_screen_top_cities_api_contract.py -v`
Expected: FAIL — `ImportError: cannot import name 'top_cities_payload'`

- [ ] **Step 3: Add `top_cities_payload` to `src/housing/api.py`**

Append (near the other `zip_screen`-related functions):

```python
import csv as _csv
import os as _os


def _top_cities_path() -> str:
    return _os.path.join(
        _os.path.dirname(_os.path.abspath(__file__)),
        'zip_screen', 'data', 'top_cities.csv',
    )


def top_cities_payload() -> tuple[dict[str, Any], int]:
    """The bundled top-cities list, for the ZIP-radius panel's anchor dropdown.

    Static, bundled data (built by scripts/build_zip_metrics.py) -- this is
    a read of a committed file, not a live query, matching the rest of the
    zip_screen package's offline-first design.
    """
    path = _top_cities_path()
    if not _os.path.exists(path):
        return {'success': False, 'error': 'top_cities.csv not found; run scripts/build_zip_metrics.py'}, 500
    with open(path, newline='', encoding='utf-8') as fh:
        rows = list(_csv.DictReader(fh))
    cities = [
        {
            'city_id': r['city_id'], 'city': r['city'], 'state': r['state'],
            'state_abbrev': r['state_abbrev'], 'population': int(r['population']),
            'anchor_zip': r['anchor_zip'],
        }
        for r in rows
    ]
    cities.sort(key=lambda c: -c['population'])
    return {'success': True, 'cities': cities}, 200
```

- [ ] **Step 4: Export it from `src/housing/__init__.py`**

Add to the existing `from .api import ...` line and `__all__` list:

```python
from .api import optimize_housing_from_request, top_cities_payload, zip_screen_from_request
```

```python
    'top_cities_payload',
```

- [ ] **Step 5: Run the backend test to verify it passes**

Run: `pytest tests/test_zip_screen_top_cities_api_contract.py -v`
Expected: PASS, 4 passed

- [ ] **Step 6: Add the route**

In `src/server/plan_routes.py`, immediately after the existing `housing_zip_screen` route (around line 769):

```python
@app.route("/api/housing/top-cities", methods=["GET"])
def housing_top_cities():
    denied = _require("read_config")
    if denied:
        return denied
    from ..housing import top_cities_payload
    return _service_json(top_cities_payload())
```

- [ ] **Step 7: Write the failing frontend test**

```python
"""The ZIP-radius panel fetches and renders the top-cities dropdown."""
from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.unit

PANEL = pathlib.Path('frontend/js/dashboard_decomp_housing_scenarios.js')


@pytest.fixture(scope='module')
def source() -> str:
    return PANEL.read_text(encoding='utf-8')


def test_a_loader_function_exists(source):
    assert 'function loadHousingOptTopCities' in source or \
           'export async function loadHousingOptTopCities' in source


def test_the_loader_calls_the_top_cities_endpoint(source):
    block = source.split('loadHousingOptTopCities')[1][:2000]
    assert '/api/housing/top-cities' in block


def test_the_loader_populates_the_shared_array(source):
    block = source.split('loadHousingOptTopCities')[1][:2000]
    assert 'HOUSING_OPT_TOP_CITIES' in block


def test_the_loader_is_invoked_when_the_panel_renders(source):
    # Called from renderHousingOptimizePanelHtml's caller path or from the
    # mode-toggle handler -- either is acceptable, but SOME call site must
    # exist besides the function's own definition.
    occurrences = source.count('loadHousingOptTopCities')
    assert occurrences >= 2
```

- [ ] **Step 8: Run test to verify it fails**

Run: `pytest tests/test_zip_screen_top_cities_panel_functional.py -v`
Expected: FAIL — no `loadHousingOptTopCities` in source

- [ ] **Step 9: Add the loader and wire it in**

Near `housingOptAnchorCitySelectHtml` (search for it — it's a few lines above `toggleHousingOptSearchMode`), add:

```javascript
let housingOptTopCitiesLoaded = false;

export async function loadHousingOptTopCities() {
  if (housingOptTopCitiesLoaded) return;
  try {
    const payload = await api("/api/housing/top-cities", { method: "GET" });
    if (payload && payload.success && Array.isArray(payload.cities)) {
      HOUSING_OPT_TOP_CITIES = payload.cities;
      housingOptTopCitiesLoaded = true;
      const select = document.getElementById("housingOptAnchorCity");
      if (select) {
        const current = select.value;
        select.innerHTML =
          `<option value="">Select a city</option>` +
          HOUSING_OPT_TOP_CITIES.map(
            (c) => `<option value="${esc(c.anchor_zip)}">${esc(c.city)}, ${esc(c.state_abbrev)}</option>`,
          ).join("");
        select.value = current;
      }
    }
  } catch (e) {
    // Non-fatal: the free-text ZIP field remains usable either way.
  }
}
```

In `toggleHousingOptSearchMode` (already exists — added in the parent feature's Task 13), call the loader when switching into ZIP mode so the dropdown populates lazily rather than on every panel render:

```javascript
export function toggleHousingOptSearchMode() {
  const zip = String(document.getElementById("housingOptGeoMode")?.value || "manual") === "zip_radius";
  const zipFields = document.getElementById("housingOptZipFields");
  const manualFields = document.getElementById("housingOptManualFields");
  if (zipFields) zipFields.hidden = !zip;
  if (manualFields) manualFields.hidden = zip;
  if (zip) loadHousingOptTopCities();
}
```

Register the new export on `window` alongside the others (search for the `Object.assign(window, {...})` block used throughout this file):

```javascript
  loadHousingOptTopCities,
```

- [ ] **Step 10: Run both frontend tests plus the existing panel test suite**

Run: `pytest tests/test_zip_screen_top_cities_panel_functional.py tests/test_zip_screen_panel_functional.py -v`
Expected: PASS, all green — including the existing panel tests from the parent feature, confirming `toggleHousingOptSearchMode`'s prior behavior (show/hide) still works.

- [ ] **Step 11: Verify against the real running app**

Start the app, open the housing panel, switch to "Search by ZIP radius," confirm the city dropdown populates with real cities (e.g. "New York, NY" as the first option) instead of staying empty, and confirm selecting a city, then clicking "Preview shortlist," produces results anchored on that city.

- [ ] **Step 12: Commit**

```bash
git add src/housing/api.py src/housing/__init__.py src/server/plan_routes.py frontend/js/dashboard_decomp_housing_scenarios.js tests/test_zip_screen_top_cities_api_contract.py tests/test_zip_screen_top_cities_panel_functional.py
git commit -m "feat(zip-screen): serve top_cities.csv and populate the anchor dropdown

Final whole-branch review finding: HOUSING_OPT_TOP_CITIES was declared but
never populated -- no route served top_cities.csv, so the city dropdown
added in the parent feature was a permanently dead control. Adds
GET /api/housing/top-cities (same auth/response pattern as the existing
housing routes) and a frontend loader invoked when switching into ZIP mode."
```

---

### Task 3: Add property-spec and price-range controls to the ZIP panel

**Files:**
- Modify: `frontend/js/dashboard_decomp_housing_scenarios.js`
- Test: `tests/test_zip_screen_property_controls_functional.py`

**Interfaces:**
- Consumes: none new
- Produces: new element IDs `housingOptZipBedrooms`, `housingOptZipBathrooms`, `housingOptZipPropertyType`, `housingOptZipSqftBand`, `housingOptZipBuiltWithinYears`, `housingOptZipPriceMin`, `housingOptZipPriceMax`; `housingOptZipSearchBody()` reads from these instead of the hidden manual-row-0 fields

**The bug:** `#housingOptZipFields` has anchor, radius, min-score, and shortlist-size controls, but no property-spec or price-range controls. `housingOptZipSearchBody()` currently reads `housingOptLocBedrooms0` etc. — fields that live inside `#housingOptManualFields`, which is `hidden` in ZIP mode. The user in ZIP mode is silently sending property-spec DEFAULTS they cannot see or change, and `target_purchase_price_range` is never sent at all in either mode from the ZIP path, so the screen's affordability filter (built and tested in the parent feature) is unreachable from the UI — the funnel diagnostic line always reports an affordability stage that did nothing.

- [ ] **Step 1: Write the failing test**

```python
"""The ZIP panel exposes its own property-spec and price-range controls,
rather than silently reusing the hidden manual-entry row's fields."""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.unit

PANEL = pathlib.Path('frontend/js/dashboard_decomp_housing_scenarios.js')


@pytest.fixture(scope='module')
def source() -> str:
    return PANEL.read_text(encoding='utf-8')


def test_zip_panel_has_its_own_bedroom_bathroom_controls(source):
    zip_block = source.split('id="housingOptZipFields"')[1].split('id="housingOptManualFields"')[0]
    assert 'housingOptZipBedrooms' in zip_block
    assert 'housingOptZipBathrooms' in zip_block


def test_zip_panel_has_its_own_property_type_and_sqft_controls(source):
    zip_block = source.split('id="housingOptZipFields"')[1].split('id="housingOptManualFields"')[0]
    assert 'housingOptZipPropertyType' in zip_block
    assert 'housingOptZipSqftBand' in zip_block


def test_zip_panel_has_price_range_controls(source):
    zip_block = source.split('id="housingOptZipFields"')[1].split('id="housingOptManualFields"')[0]
    assert 'housingOptZipPriceMin' in zip_block
    assert 'housingOptZipPriceMax' in zip_block


def test_zip_search_body_reads_the_zip_panels_own_fields_not_row_zero(source):
    block = source.split('function housingOptZipSearchBody')[1][:2000]
    assert 'housingOptZipBedrooms' in block
    assert 'housingOptLocBedrooms0' not in block


def test_zip_search_body_sends_a_price_range_when_provided(source):
    block = source.split('function housingOptZipSearchBody')[1][:2000]
    assert 'target_purchase_price_range' in block
    assert 'housingOptZipPriceMin' in block
    assert 'housingOptZipPriceMax' in block
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zip_screen_property_controls_functional.py -v`
Expected: FAIL — none of the new element IDs exist yet

- [ ] **Step 3: Add the controls to `#housingOptZipFields`**

In `renderHousingOptimizePanelHtml`, insert a new block inside `#housingOptZipFields`, immediately before the "Candidates to send to the optimizer" `<label>` (after the minimum-quality-score label and its disclosure div, before the shortlist-size label):

```javascript
      <div class="subsection-label">What you're looking for</div>
      <select id="housingOptZipBedrooms" title="Bedrooms">
        <option value="2">2BR</option>
        <option value="3" selected>3BR</option>
        <option value="4">4BR</option>
        <option value="5">5+BR</option>
      </select>
      <select id="housingOptZipBathrooms" title="Bathrooms">
        <option value="1">1BA</option>
        <option value="1.5">1.5BA</option>
        <option value="2" selected>2BA</option>
        <option value="2.5">2.5BA</option>
        <option value="3">3BA</option>
        <option value="3.5">3.5+BA</option>
      </select>
      <select id="housingOptZipPropertyType" title="Property type">
        <option value="single_family" selected>Single family</option>
        <option value="townhome">Townhome</option>
        <option value="condo">Condo</option>
        <option value="duplex">Duplex</option>
      </select>
      <select id="housingOptZipSqftBand" title="Square footage">
        <option value="under_1200">Under 1,200 sqft</option>
        <option value="1200_1800">1,200-1,800 sqft</option>
        <option value="1800_2500" selected>1,800-2,500 sqft</option>
        <option value="2500_3500">2,500-3,500 sqft</option>
        <option value="over_3500">Over 3,500 sqft</option>
      </select>
      <input type="number" id="housingOptZipBuiltWithinYears" min="0" style="width:8em" placeholder="Built within N yrs (optional)">
      <label>Target price, min <input type="number" id="housingOptZipPriceMin" min="0" style="width:9em" placeholder="e.g. 400000"></label>
      <label>Target price, max <input type="number" id="housingOptZipPriceMax" min="0" style="width:9em" placeholder="e.g. 700000"></label>
```

- [ ] **Step 4: Update `housingOptZipSearchBody`**

Replace the whole function:

```javascript
function housingOptZipSearchBody() {
  const anchorZip =
    String(document.getElementById("housingOptAnchorZip")?.value || "").trim() ||
    String(document.getElementById("housingOptAnchorCity")?.value || "").trim();
  const priceMinRaw = document.getElementById("housingOptZipPriceMin")?.value;
  const priceMaxRaw = document.getElementById("housingOptZipPriceMax")?.value;
  const priceMin = priceMinRaw ? Number(priceMinRaw) : null;
  const priceMax = priceMaxRaw ? Number(priceMaxRaw) : null;
  const propertySpec = {
    bedrooms: Number(document.getElementById("housingOptZipBedrooms")?.value || 3),
    bathrooms: Number(document.getElementById("housingOptZipBathrooms")?.value || 2),
    property_type: String(document.getElementById("housingOptZipPropertyType")?.value || "single_family"),
    sqft_band: String(document.getElementById("housingOptZipSqftBand")?.value || "1800_2500"),
    built_within_years: Number(document.getElementById("housingOptZipBuiltWithinYears")?.value) || null,
  };
  if (priceMin !== null && priceMax !== null) {
    propertySpec.target_purchase_price_range = [priceMin, priceMax];
  }
  return {
    anchor: { zip: anchorZip },
    radius_miles: Number(document.getElementById("housingOptRadius")?.value || 25),
    min_quality_score: Number(document.getElementById("housingOptMinScore")?.value || 60),
    shortlist_size: Number(document.getElementById("housingOptShortlistSize")?.value || 4),
    property_spec: propertySpec,
  };
}
```

Note: only send `target_purchase_price_range` when BOTH min and max are provided — the backend's `screen.py` already treats an absent range as "affordability filter disabled" (built and tested in the parent feature), so a partial range (only one bound filled in) is safer left unsent than guessed at with a made-up other bound.

- [ ] **Step 5: Run the new test to verify it passes**

Run: `pytest tests/test_zip_screen_property_controls_functional.py -v`
Expected: PASS, 5 passed

- [ ] **Step 6: Run the full panel/shortlist/funnel test suites to confirm no regression**

Run: `pytest tests/ -k "zip_screen" -v -m "not nightly"`
Expected: PASS, no regressions — `housingOptZipSearchBody`'s call sites (`previewHousingZipShortlist`, `runHousingOptimization`) are unchanged callers of the same function name/shape, so nothing else needs to change.

- [ ] **Step 7: Verify against the real running app**

Start the app, switch to ZIP-radius mode, set bedrooms/bathrooms/property type/price range to something other than the defaults, click "Preview shortlist," and confirm (via the funnel diagnostic line, or by checking the network request body) that the affordability stage's count now differs from the above-score count when a narrow price range is set — proving the filter is genuinely reachable.

- [ ] **Step 8: Commit**

```bash
git add frontend/js/dashboard_decomp_housing_scenarios.js tests/test_zip_screen_property_controls_functional.py
git commit -m "feat(zip-screen): give the ZIP panel its own property-spec and price controls

Final whole-branch review finding: the ZIP-radius panel had no property-spec
or price-range controls of its own -- housingOptZipSearchBody() silently
read the hidden manual-entry row's fields (defaults the user in ZIP mode
could not see or change) and never sent target_purchase_price_range at all,
making the screen's affordability filter unreachable from the UI."
```

---

## Self-Review

**Spec coverage:**

| Follow-up finding | Task |
|---|---|
| #6 — `build_top_cities` anchor heuristic mis-anchors real cities | Task 1 |
| #3 — top_cities dropdown never populated, no serving route | Task 2 |
| #4 — ZIP panel missing property-spec/price controls, affordability unreachable | Task 3 |

All three deferred findings from PR #119's final review are covered. No spec section is unimplemented.

**Ordering rationale:** Task 1 before Task 2, matching the final reviewer's own recommendation ("fix the anchor heuristic before wiring the dropdown... shipping a wrong-but-present anchor is worse than an absent one"). Task 3 is independent of 1/2 but sequenced last since it touches the same frontend file as Task 2 and subagent-driven-development never dispatches two implementers against the same file concurrently.

**Placeholder scan:** none found — every step has complete code.

**Type consistency:** `top_cities_payload()`'s return shape (`{'success': bool, 'cities': [...]}` or `{'success': False, 'error': str}`, `(dict, int)` tuple) matches the existing `zip_screen_from_request`/`optimize_housing_from_request` convention in the same file. `housingOptZipSearchBody()`'s return shape (`{anchor, radius_miles, min_quality_score, shortlist_size, property_spec}`, with `property_spec` optionally carrying `target_purchase_price_range`) matches exactly what `screen.py`'s `parse_zip_search` (parent feature, unmodified here) already expects — no backend change needed for Task 3, confirmed by re-reading `src/housing/api.py`'s `parse_zip_search` before writing this task.
