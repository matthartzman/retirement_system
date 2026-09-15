# Housing Optimizer Panel Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the housing optimizer panel: state dropdowns instead of free text, the five housing criteria (bedrooms/bathrooms/property type/sqft/age) wired into both places a home is priced, a correct move-label rendering, per-move buy/rent constraints, and a new "concurrent" move-2 mode so the optimizer can recommend buy-here-rent-there in parallel for dual-location family presence.

**Architecture:** Backend changes live in `src/server_services/strategy_asset_service.py` (pricing model) and `src/housing_optimizer.py` (candidate generation/scoring/formatting), reached via the existing `/api/housing/state-estimate` and `/api/housing/optimize` routes (`src/server/plan_routes.py`, unchanged) and documented in `src/api_contracts.py`. Frontend changes live entirely in `frontend/js/dashboard_decomp_housing_scenarios.js` (the optimizer panel) and `frontend/js/dashboard.js`'s housing-step editor fields, sourced from `src/server_services/strategy_asset_service.py`'s `HOUSING_SEED_ROWS`.

**Tech Stack:** Python 3 (Flask backend, pytest), vanilla JS ES modules (Node `node:test` via `tests/frontend/load_dashboard.mjs`'s `vm`-sandbox loader).

## Global Constraints

- Every new `Location`/`HousingCandidate` field ships with a default that reproduces today's behavior exactly — no existing caller, test, or saved plan changes result. (Design doc §2, §4.)
- `move2_mode='concurrent'` ships for `search_mode='full'` only this pass; `search_mode='narrowed'` rejects it with a `ValueError` (design doc "Out of scope" addendum).
- The five housing-criteria multiplier tables and values are copied verbatim from `documentation/archive/superpowers/plans/2026-09-09-housing-estimate-realism-and-dollar-convention-design.md` §3.3 — do not invent different numbers.
- State dropdowns reuse the existing `_stateNameChoiceOptions()` from `frontend/js/dashboard_decomp_state_inputs.js` — do not create a second state list.
- Every backend behavior change needs a `tests/test_housing_optimizer_unit.py` (or `_functional.py`) / `tests/test_pricing_housing_service_extraction_functional.py` case; every frontend behavior change needs a `tests/frontend/housing_optimize_panel.test.mjs` (or `estimate_housing_from_state.test.mjs`) case, following the existing `freshSandbox()`/`document.getElementById` mocking pattern already in those files.

---

## Task 1: State fields become dropdowns

**Files:**
- Modify: `frontend/js/dashboard_decomp_housing_scenarios.js:1171` (candidate-location state input), `:1224` (family-presence region input)
- Test: `tests/frontend/housing_optimize_panel.test.mjs`

**Interfaces:**
- Consumes: `_stateNameChoiceOptions()` from `frontend/js/dashboard_decomp_state_inputs.js:24-26` (returns `[{value, label}, ...]`, both full state names) — available as a bare global in this sandbox/runtime, no import needed (see that file's module docstring on the window-bridge convention).
- Produces: no change to `runHousingOptimization()`'s read of `housingOptLocState${i}`/`housingOptPresenceRegion` — both remain `.value` reads, now sourced from a `<select>` instead of an `<input>`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/frontend/housing_optimize_panel.test.mjs`, inside the existing `describe("renderHousingOptimizePanelHtml", ...)` block:

```js
  test("renders state fields as dropdowns of the canonical state list, not free text", () => {
    const sandbox = freshSandbox();
    const html = sandbox.renderHousingOptimizePanelHtml();
    assert.doesNotMatch(html, /id="housingOptLocState0" type="text"/);
    assert.match(html, /<select id="housingOptLocState0">[\s\S]*?<\/select>/);
    assert.match(html, /<option value="Illinois">Illinois<\/option>/);
    assert.doesNotMatch(html, /id="housingOptPresenceRegion" type="text"/);
    assert.match(html, /<select id="housingOptPresenceRegion">[\s\S]*?<\/select>/);
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/frontend/housing_optimize_panel.test.mjs`
Expected: FAIL — the current markup has `<input type="text" id="housingOptLocState0" ...>`, not a `<select>`.

- [ ] **Step 3: Replace the two free-text inputs with dropdowns**

In `frontend/js/dashboard_decomp_housing_scenarios.js`, add a small helper right above `housingOptLocationRowHtml` (which starts at line 1169):

```js
function housingOptStateSelectHtml(id, selectedValue) {
  const options = _stateNameChoiceOptions()
    .map(
      (o) =>
        `<option value="${esc(o.value)}"${o.value === selectedValue ? " selected" : ""}>${esc(o.label)}</option>`,
    )
    .join("");
  return `<select id="${id}"><option value="">Select a state</option>${options}</select>`;
}
```

Replace line 1171:

```js
    <input type="text" id="housingOptLocState${i}" placeholder="State (e.g. Texas)" style="width:10em">
```

with:

```js
    ${housingOptStateSelectHtml(`housingOptLocState${i}`, "")}
```

Replace line 1224:

```js
    <label>Region (state) <input type="text" id="housingOptPresenceRegion" placeholder="e.g. Illinois"></label>
```

with:

```js
    <label>Region (state) ${housingOptStateSelectHtml("housingOptPresenceRegion", "")}</label>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test tests/frontend/housing_optimize_panel.test.mjs`
Expected: PASS, all tests in the file (this one and the pre-existing ones, since `runHousingOptimization()`'s `.value` reads are untouched).

- [ ] **Step 5: Commit**

```bash
git add frontend/js/dashboard_decomp_housing_scenarios.js tests/frontend/housing_optimize_panel.test.mjs
git commit -m "$(cat <<'EOF'
Housing optimizer: state fields are dropdowns, not free text

Reuses the existing site-wide canonical state list
(_stateNameChoiceOptions, #260) for both the candidate-location and
family-presence-region state fields, instead of free-text inputs that
the backend had to fuzzily map.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Five housing-criteria multipliers in the pricing model

**Files:**
- Modify: `src/server_services/strategy_asset_service.py:94-202`
- Test: `tests/test_pricing_housing_service_extraction_functional.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `housing_state_estimate_payload(data)` now accepts five new optional keys on `data`: `bedrooms` (int, default `3`), `bathrooms` (float, default `2.0`), `property_type` (str, default `'single_family'`), `sqft_band` (str, default `'1800_2500'`), `built_within_years` (int or `None`, default `None`). Module-level constants `BEDROOM_MULT`, `BATHROOM_MULT`, `PROPERTY_TYPE_MULT`, `SQFT_BAND_MULT` (dicts) and function `built_within_years_mult(years)` are new public names Task 3 and later tasks do not need, but tests do.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pricing_housing_service_extraction_functional.py`:

```python
def test_housing_state_estimate_default_characteristics_match_todays_baseline():
    # Omitting all five characteristics must reproduce today's numbers
    # exactly -- the defaults (3BR/2BA/single_family/1800-2500sqft/no
    # preference) are the same implicit assumption already baked into
    # STATE_ESTIMATES.
    from src.server_services.strategy_asset_service import housing_state_estimate_payload

    base = {"state": "TX", "type": "purchase", "city_type": "suburban", "population_size": 20000}
    without, _ = housing_state_estimate_payload(dict(base))
    with_defaults, _ = housing_state_estimate_payload(dict(
        base, bedrooms=3, bathrooms=2, property_type="single_family",
        sqft_band="1800_2500", built_within_years=None,
    ))
    assert without["estimate"] == with_defaults["estimate"]


def test_housing_state_estimate_bedroom_and_sqft_multipliers_move_price():
    from src.server_services.strategy_asset_service import housing_state_estimate_payload

    base = {"state": "TX", "type": "purchase", "city_type": "suburban", "population_size": 20000}
    baseline, _ = housing_state_estimate_payload(dict(base))
    smaller, _ = housing_state_estimate_payload(dict(base, bedrooms=2, sqft_band="under_1200"))
    bigger, _ = housing_state_estimate_payload(dict(base, bedrooms=5, sqft_band="over_3500"))
    assert smaller["estimate"]["purchase_price"] < baseline["estimate"]["purchase_price"] < bigger["estimate"]["purchase_price"]


def test_housing_state_estimate_condo_floors_hoa_and_cuts_maintenance():
    from src.server_services.strategy_asset_service import housing_state_estimate_payload

    base = {"state": "TX", "type": "purchase", "city_type": "suburban", "population_size": 20000}
    single_family, _ = housing_state_estimate_payload(dict(base, property_type="single_family"))
    condo, _ = housing_state_estimate_payload(dict(base, property_type="condo"))
    assert condo["estimate"]["hoa_pct"] >= 0.004
    assert condo["estimate"]["maintenance_annual"] < single_family["estimate"]["maintenance_annual"]


def test_housing_state_estimate_built_within_years_multiplier():
    from src.server_services.strategy_asset_service import housing_state_estimate_payload

    base = {"state": "TX", "type": "purchase", "city_type": "suburban", "population_size": 20000}
    no_pref, _ = housing_state_estimate_payload(dict(base))
    new_construction, _ = housing_state_estimate_payload(dict(base, built_within_years=1))
    old_home, _ = housing_state_estimate_payload(dict(base, built_within_years=50))
    assert old_home["estimate"]["purchase_price"] < no_pref["estimate"]["purchase_price"] < new_construction["estimate"]["purchase_price"]


def test_housing_state_estimate_note_states_actual_characteristics():
    from src.server_services.strategy_asset_service import housing_state_estimate_payload

    payload, _ = housing_state_estimate_payload({
        "state": "IL", "type": "purchase", "city_type": "suburban", "population_size": 20000,
        "bedrooms": 4, "bathrooms": 2.5, "property_type": "townhome", "sqft_band": "2500_3500",
    })
    note = payload["estimate"]["note"]
    assert "4BR" in note
    assert "2.5BA" in note
    assert "townhome" in note
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_pricing_housing_service_extraction_functional.py -k characteristics -v`
Expected: FAIL — `housing_state_estimate_payload` doesn't read these keys yet, and `note` doesn't mention bedrooms/bathrooms/property type.

- [ ] **Step 3: Add the multiplier tables and wire them in**

In `src/server_services/strategy_asset_service.py`, insert directly after `STATE_ESTIMATES` (currently ending at line 99):

```python
# Five housing characteristics (documentation/archive/superpowers/plans/
# 2026-09-09-housing-estimate-realism-and-dollar-convention-design.md §3.3):
# multiplicative factors on the state base price, same mechanism as
# city_type/population_size above, applied uniformly to purchase and rent.
# All defaults reproduce today's implicit fixed assumption (3BR/2BA/
# single_family/1800-2500 sqft/no preference) -- multiplier 1.00 each.
BEDROOM_MULT = {2: 0.85, 3: 1.00, 4: 1.15, 5: 1.30}
BATHROOM_MULT = {1: 0.90, 1.5: 0.95, 2: 1.00, 2.5: 1.05, 3: 1.12, 3.5: 1.18}
PROPERTY_TYPE_MULT = {"single_family": 1.00, "townhome": 0.85, "condo": 0.75, "duplex": 0.90}
SQFT_BAND_MULT = {
    "under_1200": 0.75, "1200_1800": 0.90, "1800_2500": 1.00,
    "2500_3500": 1.20, "over_3500": 1.45,
}
_SQFT_BAND_LABELS = {
    "under_1200": "under 1,200", "1200_1800": "1,200-1,800", "1800_2500": "1,800-2,500",
    "2500_3500": "2,500-3,500", "over_3500": "over 3,500",
}


def built_within_years_mult(years: int | None) -> float:
    if years is None:
        return 1.00
    if years <= 2:
        return 1.15
    if years <= 10:
        return 1.05
    if years <= 30:
        return 1.00
    return 0.90


def _clamp_bedrooms(raw: Any) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return 3
    return min(5, max(2, n))


def _clamp_bathrooms(raw: Any) -> float:
    try:
        b = float(raw)
    except (TypeError, ValueError):
        return 2.0
    return b if b in BATHROOM_MULT else 2.0


def _clamp_property_type(raw: Any) -> str:
    p = str(raw or "single_family").strip().lower()
    return p if p in PROPERTY_TYPE_MULT else "single_family"


def _clamp_sqft_band(raw: Any) -> str:
    s = str(raw or "1800_2500").strip().lower()
    return s if s in SQFT_BAND_MULT else "1800_2500"


def _clamp_built_within_years(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
```

Then, inside `housing_state_estimate_payload`, replace lines 106-137 (from `city_type = ...` through the `estimate["hoa_pct"] = ...` line) with:

```python
    city_type = str((data or {}).get("city_type", "suburban")).strip().lower()
    try:
        population_size = int((data or {}).get("population_size", 20000) or 20000)
    except (ValueError, TypeError):
        population_size = 20000
    bedrooms = _clamp_bedrooms((data or {}).get("bedrooms", 3))
    bathrooms = _clamp_bathrooms((data or {}).get("bathrooms", 2.0))
    property_type = _clamp_property_type((data or {}).get("property_type", "single_family"))
    sqft_band = _clamp_sqft_band((data or {}).get("sqft_band", "1800_2500"))
    built_within_years = _clamp_built_within_years((data or {}).get("built_within_years"))

    estimate = dict(STATE_ESTIMATES.get(state) or dict(purchase_price=350000, monthly_rent=1600, insurance_annual=1600, utilities_annual=2800, maintenance_annual=3500, re_tax_pct=0.0100, hoa_pct=0.001))
    city_multipliers = {"urban": 1.30, "city": 1.30, "suburban": 1.00, "exurban": 0.85, "rural": 0.75}
    city_mult = city_multipliers.get(city_type, 1.00)
    if population_size > 500_000:
        pop_mult = 1.20
    elif population_size > 200_000:
        pop_mult = 1.12
    elif population_size > 100_000:
        pop_mult = 1.06
    elif population_size > 50_000:
        pop_mult = 1.02
    elif population_size > 20_000:
        pop_mult = 1.00
    elif population_size > 10_000:
        pop_mult = 0.92
    else:
        pop_mult = 0.85
    characteristic_mult = (
        BEDROOM_MULT[bedrooms] * BATHROOM_MULT[bathrooms] * PROPERTY_TYPE_MULT[property_type]
        * SQFT_BAND_MULT[sqft_band] * built_within_years_mult(built_within_years)
    )

    combined = city_mult * pop_mult * characteristic_mult
    estimate["purchase_price"] = round(float(estimate["purchase_price"]) * combined / 1000) * 1000
    estimate["monthly_rent"] = round(float(estimate["monthly_rent"]) * combined / 10) * 10
    estimate["maintenance_annual"] = round(float(estimate["purchase_price"]) * 0.01 / 100) * 100
    # HOA fee prevalence/size tracks density (condos/townhomes cluster in
    # urban, denser areas), so scale it the same way as the other purchase-side
    # estimated fields rather than leaving it a flat per-state constant.
    estimate["hoa_pct"] = round(float(estimate.get("hoa_pct", 0) or 0) * combined, 4)
    if property_type in ("condo", "townhome"):
        estimate["hoa_pct"] = max(estimate["hoa_pct"], 0.004)
        estimate["maintenance_annual"] = round(estimate["maintenance_annual"] * 0.4)
```

Finally, replace the `estimate.update({...})` block near the end (currently lines 194-201) with:

```python
    bedrooms_label = "5+BR" if bedrooms >= 5 else f"{bedrooms}BR"
    bathrooms_label = f"{bathrooms:g}BA"
    property_type_label = property_type.replace("_", " ")
    sqft_label = _SQFT_BAND_LABELS[sqft_band]
    estimate.update({
        "mortgage_rate_pct": estimate.get("mortgage_rate_pct", 0.0685),
        "type": "rent" if is_rent else "purchase",
        "city_type": city_type or "suburban",
        "population_size": population_size,
        "state": state,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "property_type": property_type,
        "sqft_band": sqft_band,
        "built_within_years": built_within_years,
        "note": (
            f"Estimated costs for a {bedrooms_label}/{bathrooms_label} {property_type_label}, "
            f"{sqft_label} sqft, in a {city_type or 'suburban'} area (~{population_size:,} population) "
            f"in {state}.{basis_note} All values are editable."
        ),
    })
    return {"success": True, "schema": "housing_state_estimate_v1", "estimate": estimate}, 200
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_pricing_housing_service_extraction_functional.py -v`
Expected: PASS — all tests in the file, including the pre-existing ones (defaults reproduce identical output) and the five new ones.

- [ ] **Step 5: Commit**

```bash
git add src/server_services/strategy_asset_service.py tests/test_pricing_housing_service_extraction_functional.py
git commit -m "$(cat <<'EOF'
Wire the five housing characteristics into the pricing model

bedrooms/bathrooms/property_type/sqft_band/built_within_years were
specced in the 2026-09-09 housing-estimate design doc but never
implemented. Adds the multiplier tables and folds them into
housing_state_estimate_payload's existing city_type/population_size
multiplier pipeline, with defaults that exactly reproduce today's
numbers when omitted.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Thread the five criteria through `Location` / the optimizer, and the API contract

**Files:**
- Modify: `src/housing_optimizer.py:124-129` (`Location`), `:190-197` (`_estimate_for_location`), `:889-899` (`_parse_location`)
- Modify: `src/api_contracts.py:120-124`
- Test: `tests/test_housing_optimizer_unit.py`, `tests/test_housing_optimizer_integration.py`

**Interfaces:**
- Consumes: `housing_state_estimate_payload` from Task 2 (now accepts `bedrooms`/`bathrooms`/`property_type`/`sqft_band`/`built_within_years`).
- Produces: `Location(state, city_type='suburban', population_size=20000, target_purchase_price_range=None, bedrooms=3, bathrooms=2.0, property_type='single_family', sqft_band='1800_2500', built_within_years=None)`. `_parse_location(raw)` reads the same five keys from a request dict.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_housing_optimizer_unit.py`:

```python
def test_location_defaults_match_todays_implicit_assumption():
    loc = Location(state="Texas")
    assert loc.bedrooms == 3
    assert loc.bathrooms == 2.0
    assert loc.property_type == "single_family"
    assert loc.sqft_band == "1800_2500"
    assert loc.built_within_years is None


def test_parse_location_reads_the_five_characteristics():
    from src.housing_optimizer import _parse_location

    loc = _parse_location({
        "state": "Texas", "bedrooms": "4", "bathrooms": 2.5,
        "property_type": "Condo", "sqft_band": "2500_3500", "built_within_years": "3",
    })
    assert loc.bedrooms == 4
    assert loc.bathrooms == 2.5
    assert loc.property_type == "condo"
    assert loc.sqft_band == "2500_3500"
    assert loc.built_within_years == 3


def test_parse_location_blank_built_within_years_is_none():
    from src.housing_optimizer import _parse_location

    loc = _parse_location({"state": "Texas", "built_within_years": ""})
    assert loc.built_within_years is None
```

Add to `tests/test_housing_optimizer_integration.py` (near existing `_estimate_for_location`/`_purchase_step` coverage — grep the file first for the exact existing test names to place this alongside them):

```python
def test_estimate_for_location_passes_characteristics_through_to_pricing():
    from src.housing_optimizer import Location, _estimate_for_location

    baseline = _estimate_for_location(Location(state="Texas"), "purchase")
    bigger = _estimate_for_location(
        Location(state="Texas", bedrooms=5, sqft_band="over_3500"), "purchase",
    )
    assert bigger["purchase_price"] > baseline["purchase_price"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_housing_optimizer_unit.py -k characteristics -v tests/test_housing_optimizer_integration.py -k characteristics -v`
Expected: FAIL — `Location` has no such fields yet; `TypeError: __init__() got an unexpected keyword argument 'bedrooms'`.

- [ ] **Step 3: Add the fields**

In `src/housing_optimizer.py`, replace the `Location` dataclass (lines 124-129):

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
```

Replace `_estimate_for_location` (lines 190-197):

```python
def _estimate_for_location(loc: Location, housing_type: str) -> dict[str, Any]:
    payload, _status = housing_state_estimate_payload({
        'state': _STATE_ABBREV.get(loc.state, loc.state),
        'type': housing_type,
        'city_type': loc.city_type,
        'population_size': loc.population_size,
        'bedrooms': loc.bedrooms,
        'bathrooms': loc.bathrooms,
        'property_type': loc.property_type,
        'sqft_band': loc.sqft_band,
        'built_within_years': loc.built_within_years,
    })
    return payload['estimate']
```

Replace `_parse_location` (lines 889-899):

```python
def _parse_location(raw: dict[str, Any]) -> Location:
    price_range = raw.get('target_purchase_price_range')
    parsed_range = None
    if isinstance(price_range, (list, tuple)) and len(price_range) == 2:
        parsed_range = (float(price_range[0]), float(price_range[1]))
    built_within_years_raw = raw.get('built_within_years')
    try:
        built_within_years = int(built_within_years_raw) if built_within_years_raw not in (None, '') else None
    except (TypeError, ValueError):
        built_within_years = None
    return Location(
        state=str(raw.get('state', '') or '').strip(),
        city_type=str(raw.get('city_type', 'suburban') or 'suburban').strip().lower(),
        population_size=int(raw.get('population_size', 20000) or 20000),
        target_purchase_price_range=parsed_range,
        bedrooms=int(raw.get('bedrooms', 3) or 3),
        bathrooms=float(raw.get('bathrooms', 2.0) or 2.0),
        property_type=str(raw.get('property_type', 'single_family') or 'single_family').strip().lower(),
        sqft_band=str(raw.get('sqft_band', '1800_2500') or '1800_2500').strip().lower(),
        built_within_years=built_within_years,
    )
```

In `src/api_contracts.py`, replace line 122:

```python
        request_fields=(_f("state", "str", True), _f("type", "str"), _f("city_type", "str"), _f("population_size", "int")),
```

with:

```python
        request_fields=(
            _f("state", "str", True), _f("type", "str"), _f("city_type", "str"), _f("population_size", "int"),
            _f("bedrooms", "int"), _f("bathrooms", "float"), _f("property_type", "str"), _f("sqft_band", "str"),
            _f("built_within_years", "int"),
        ),
```

No change is needed to the `/api/housing/optimize` contract's `locations` field (line 128) — it's declared `_f("locations", "list", True)`, and `list`-typed fields in this contract system aren't further broken down by sub-key, so the five new `Location` fields need no separate declaration there.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_housing_optimizer_unit.py tests/test_housing_optimizer_integration.py -v`
Expected: PASS — full files, not just the new tests (confirms no existing `Location(...)` call site broke).

- [ ] **Step 5: Commit**

```bash
git add src/housing_optimizer.py src/api_contracts.py tests/test_housing_optimizer_unit.py tests/test_housing_optimizer_integration.py
git commit -m "$(cat <<'EOF'
Thread the five housing characteristics through Location

Location, _estimate_for_location, and the /api/housing/optimize
request parser now carry bedrooms/bathrooms/property_type/sqft_band/
built_within_years through to the pricing model from Task 2, with
defaults matching today's behavior exactly.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Five-criteria UI in the optimizer's candidate-location rows

**Files:**
- Modify: `frontend/js/dashboard_decomp_housing_scenarios.js:1169-1180` (`housingOptLocationRowHtml`), `:1285-1299` (`runHousingOptimization`'s `locations` payload build)
- Test: `tests/frontend/housing_optimize_panel.test.mjs`

**Interfaces:**
- Consumes: nothing new.
- Produces: each entry in `runHousingOptimization()`'s `locations[]` array gains `bedrooms` (number), `bathrooms` (number), `property_type` (string), `sqft_band` (string), `built_within_years` (number or `null`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/frontend/housing_optimize_panel.test.mjs`:

```js
describe("housingOptLocationRowHtml five-criteria fields", () => {
  test("renders bedrooms/bathrooms/property type/sqft band/built-within-years inputs", () => {
    const sandbox = freshSandbox();
    const html = sandbox.renderHousingOptimizePanelHtml();
    assert.match(html, /id="housingOptLocBedrooms0"/);
    assert.match(html, /id="housingOptLocBathrooms0"/);
    assert.match(html, /id="housingOptLocPropertyType0"/);
    assert.match(html, /id="housingOptLocSqftBand0"/);
    assert.match(html, /id="housingOptLocBuiltWithinYears0"/);
  });
});
```

Add a new assertion inside the existing `"posts the gathered form values to /api/housing/optimize and renders the response"` test in the same file, right after `assert.equal(capturedBody.locations[0].state, "Texas");`:

```js
    assert.equal(capturedBody.locations[0].bedrooms, 3);
    assert.equal(capturedBody.locations[0].property_type, "single_family");
```

(and add `housingOptLocBedrooms0: "3"`, `housingOptLocPropertyType0: "single_family"` to that test's `values` object so the read has something to find — or rely on the new fields' own defaults if the element is missing, per Step 3 below; either is fine as long as the assertion holds.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tests/frontend/housing_optimize_panel.test.mjs`
Expected: FAIL — no such elements/payload keys exist yet.

- [ ] **Step 3: Add the five inputs**

Replace `housingOptLocationRowHtml` (lines 1169-1180) with:

```js
function housingOptLocationRowHtml(i) {
  return `<div class="housing-opt-location-row" id="housingOptLocRow${i}" ${i >= 2 ? "hidden" : ""}>
    ${housingOptStateSelectHtml(`housingOptLocState${i}`, "")}
    <select id="housingOptLocCity${i}">
      <option value="urban">Urban</option>
      <option value="suburban" selected>Suburban</option>
      <option value="exurban">Exurban</option>
      <option value="rural">Rural</option>
    </select>
    <input type="number" id="housingOptLocPop${i}" value="20000" min="0" style="width:8em" placeholder="Population">
    <select id="housingOptLocBedrooms${i}" title="Bedrooms">
      <option value="2">2BR</option>
      <option value="3" selected>3BR</option>
      <option value="4">4BR</option>
      <option value="5">5+BR</option>
    </select>
    <select id="housingOptLocBathrooms${i}" title="Bathrooms">
      <option value="1">1BA</option>
      <option value="1.5">1.5BA</option>
      <option value="2" selected>2BA</option>
      <option value="2.5">2.5BA</option>
      <option value="3">3BA</option>
      <option value="3.5">3.5+BA</option>
    </select>
    <select id="housingOptLocPropertyType${i}" title="Property type">
      <option value="single_family" selected>Single family</option>
      <option value="townhome">Townhome</option>
      <option value="condo">Condo</option>
      <option value="duplex">Duplex</option>
    </select>
    <select id="housingOptLocSqftBand${i}" title="Square footage">
      <option value="under_1200">Under 1,200 sqft</option>
      <option value="1200_1800">1,200-1,800 sqft</option>
      <option value="1800_2500" selected>1,800-2,500 sqft</option>
      <option value="2500_3500">2,500-3,500 sqft</option>
      <option value="over_3500">Over 3,500 sqft</option>
    </select>
    <input type="number" id="housingOptLocBuiltWithinYears${i}" min="0" style="width:8em" placeholder="Built within N yrs (optional)">
  </div>`;
}
```

Replace the `locations.push({...})` block inside `runHousingOptimization` (lines 1294-1298):

```js
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test tests/frontend/housing_optimize_panel.test.mjs`
Expected: PASS — all tests in the file.

- [ ] **Step 5: Commit**

```bash
git add frontend/js/dashboard_decomp_housing_scenarios.js tests/frontend/housing_optimize_panel.test.mjs
git commit -m "$(cat <<'EOF'
Housing optimizer: add the five housing-criteria inputs per candidate

Mirrors the existing city_type/population_size pattern -- bedrooms,
bathrooms, property type, sqft band, and built-within-years now flow
into runHousingOptimization()'s locations[] payload alongside the
existing fields.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Five-criteria UI in the regular housing-step editor

**Files:**
- Modify: `src/server_services/strategy_asset_service.py:48-77` (`HOUSING_SEED_ROWS`, both `next_step_1` and `next_step_2`)
- Modify: `frontend/js/dashboard_decomp_housing_scenarios.js:140-234` (`estimateHousingFromState`)
- Test: `tests/frontend/estimate_housing_from_state.test.mjs`, a `test_workbook_housing_wellness_cashflow_functional.py`-style seed-row count check if one exists (grep first)

**Interfaces:**
- Consumes: `housing_state_estimate_payload` from Task 2.
- Produces: five new `Housing`/`next_step_N` CSV rows (`bedrooms`, `bathrooms`, `property_type`, `sqft_band`, `built_within_years`), read by `estimateHousingFromState` and included in its POST body to `/api/housing/state-estimate`.

- [ ] **Step 1: Write the failing tests**

First, grep for how many seed rows existing tests expect:

```bash
grep -rn "HOUSING_SEED_ROWS" tests/ src/
```

Read whichever test asserts a row count or specific label set, and update its expectation to include the 10 new rows (5 per step) — write down the exact assertion you're changing before editing it, since the "No Placeholders" rule requires this plan to show real code, and the current file layout of that test wasn't known at plan-writing time. If no such count-asserting test exists, skip this.

Add to `tests/frontend/estimate_housing_from_state.test.mjs` (read the file first to match its exact row-mocking helper — it builds a `rows` array of `{section, subsection, label, ...}` objects the same shape as `dashboard_decomp_housing_scenarios.js`'s module-level `rows` binding expects):

```js
test("posts bedrooms/bathrooms/property_type/sqft_band/built_within_years when present on the step", async () => {
  const sandbox = freshSandbox();
  sandbox.rows = [
    { section: "Housing", subsection: "next_step_1", label: "state", row_index: 0, value: "IL" },
    { section: "Housing", subsection: "next_step_1", label: "type", row_index: 1, value: "purchase" },
    { section: "Housing", subsection: "next_step_1", label: "city_type", row_index: 2, value: "suburban" },
    { section: "Housing", subsection: "next_step_1", label: "population_size", row_index: 3, value: "20000" },
    { section: "Housing", subsection: "next_step_1", label: "bedrooms", row_index: 4, value: "4" },
    { section: "Housing", subsection: "next_step_1", label: "bathrooms", row_index: 5, value: "2.5" },
    { section: "Housing", subsection: "next_step_1", label: "property_type", row_index: 6, value: "condo" },
    { section: "Housing", subsection: "next_step_1", label: "sqft_band", row_index: 7, value: "2500_3500" },
    { section: "Housing", subsection: "next_step_1", label: "built_within_years", row_index: 8, value: "2" },
  ];
  let capturedBody = null;
  sandbox.api = async (url, opts) => {
    capturedBody = JSON.parse(opts.body);
    return { estimate: {} };
  };
  sandbox.window.applyHousingEstimateField = () => false;
  await sandbox.estimateHousingFromState(1);
  assert.equal(capturedBody.bedrooms, 4);
  assert.equal(capturedBody.bathrooms, 2.5);
  assert.equal(capturedBody.property_type, "condo");
  assert.equal(capturedBody.sqft_band, "2500_3500");
  assert.equal(capturedBody.built_within_years, 2);
});
```

(Adjust the mock shape to match whatever `estimate_housing_from_state.test.mjs` already does for its passing tests — read that file's existing tests before writing this one, since `rows`/`valOf`/`norm` mocking conventions live there, not in this plan.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/frontend/estimate_housing_from_state.test.mjs`
Expected: FAIL — `capturedBody.bedrooms` is `undefined`.

- [ ] **Step 3: Add the seed rows**

In `src/server_services/strategy_asset_service.py`, insert five rows after line 53 (`["Housing","next_step_1","population_size",...]`) and before line 54 (`["Housing","next_step_1","purchase_price",...]`):

```python
    ["Housing","next_step_1","bedrooms","3","int","Bedrooms (used to refine the price estimate)"],
    ["Housing","next_step_1","bathrooms","2","choice","Bathrooms: 1|1.5|2|2.5|3|3.5+ (used to refine the price estimate)"],
    ["Housing","next_step_1","property_type","single_family","choice","single_family|townhome|condo|duplex (used to refine the price estimate)"],
    ["Housing","next_step_1","sqft_band","1800_2500","choice","Square footage band (used to refine the price estimate)"],
    ["Housing","next_step_1","built_within_years","","int","Built within the last N years, optional (used to refine the price estimate)"],
```

And the same five rows with `next_step_2` in place of `next_step_1`, inserted after the (now-shifted) `next_step_2`/`population_size` row and before `next_step_2`/`purchase_price`.

- [ ] **Step 4: Add the reads and the POST-body fields**

In `frontend/js/dashboard_decomp_housing_scenarios.js`, inside `estimateHousingFromState` (starting line 140), add four more row finders right after `popRow` (line 165, before `startYearRow`):

```js
  const bedroomsRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "bedrooms",
  );
  const bathroomsRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "bathrooms",
  );
  const propertyTypeRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "property_type",
  );
  const sqftBandRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "sqft_band",
  );
  const builtWithinYearsRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "built_within_years",
  );
```

Then, in the `api("/api/housing/state-estimate", ...)` call body (lines 224-233), add five keys:

```js
      body: JSON.stringify({
        state: stateVal,
        step: sub,
        type: typeVal,
        city_type: cityTypeVal,
        population_size: parseInt(popVal) || 20000,
        bedrooms: bedroomsRow ? parseInt(String(valOf(bedroomsRow) || "3"), 10) || 3 : 3,
        bathrooms: bathroomsRow ? parseFloat(String(valOf(bathroomsRow) || "2")) || 2 : 2,
        property_type: propertyTypeRow ? String(valOf(propertyTypeRow) || "single_family") : "single_family",
        sqft_band: sqftBandRow ? String(valOf(sqftBandRow) || "1800_2500") : "1800_2500",
        built_within_years: builtWithinYearsRow && String(valOf(builtWithinYearsRow) || "").trim()
          ? parseInt(String(valOf(builtWithinYearsRow)), 10)
          : null,
        start_year: Number.isFinite(startYearVal) ? startYearVal : "",
        home_appr: homeApprVal,
        inflation_general: inflationVal,
      }),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `node --test tests/frontend/estimate_housing_from_state.test.mjs && pytest tests/test_workbook_housing_wellness_cashflow_functional.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/server_services/strategy_asset_service.py frontend/js/dashboard_decomp_housing_scenarios.js tests/frontend/estimate_housing_from_state.test.mjs
git commit -m "$(cat <<'EOF'
Add the five housing-criteria fields to the regular housing-step editor

Seeds bedrooms/bathrooms/property_type/sqft_band/built_within_years on
both next_step_1 and next_step_2, and has the Estimate flow read and
post them to /api/housing/state-estimate -- this was the original
design doc's actual target and had never been built.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Fix the move-label rendering

**Files:**
- Modify: `frontend/js/dashboard_decomp_housing_scenarios.js:1232-1239` (`housingOptMoveText`)
- Test: `tests/frontend/housing_optimize_panel.test.mjs`

**Interfaces:**
- Consumes: a `move` object shaped `{sale_year, purchase_year, rent_indefinitely, location, sec121_exclusion_lost}` (Task 9 adds `mode`/`start_year` keys, handled there — this task only fixes ordering/labeling for the existing sequential shape).
- Produces: `housingOptMoveText(move)` still returns a single HTML string, now chronologically ordered and home-labeled.

- [ ] **Step 1: Write the failing tests**

Add to `tests/frontend/housing_optimize_panel.test.mjs`, inside `describe("renderHousingOptimizeResultsHtml", ...)`:

```js
  test("orders a bridge-purchase move chronologically (buy before sell) instead of always 'Sell -> Buy'", () => {
    const sandbox = freshSandbox();
    const payload = samplePayload();
    payload.recommendation.moves[0] = {
      sale_year: 2035,
      purchase_year: 2032,
      rent_indefinitely: false,
      location: { state: "Illinois", city_type: "suburban", population_size: 20000 },
      sec121_exclusion_lost: false,
    };
    const html = sandbox.renderHousingOptimizeResultsHtml(payload);
    const buyIdx = html.indexOf("Buy in Illinois (2032)");
    const sellIdx = html.indexOf("Sell original home (2035)");
    assert.ok(buyIdx >= 0, "expected a 'Buy in Illinois (2032)' label");
    assert.ok(sellIdx >= 0, "expected a 'Sell original home (2035)' label");
    assert.ok(buyIdx < sellIdx, "buy year (2032) precedes sell year (2035), should render first");
    assert.match(html, /own both homes 2032.{0,3}2035/i);
  });

  test("labels move 2's sale as the move-1 home, not the original home", () => {
    const sandbox = freshSandbox();
    const payload = samplePayload();
    payload.recommendation.moves = [
      {
        sale_year: 2030, purchase_year: 2030, rent_indefinitely: false,
        location: { state: "Texas", city_type: "suburban", population_size: 150000 },
        sec121_exclusion_lost: false,
      },
      {
        sale_year: 2032, purchase_year: 2038, rent_indefinitely: false,
        location: { state: "Florida", city_type: "urban", population_size: 300000 },
        sec121_exclusion_lost: false,
      },
    ];
    const html = sandbox.renderHousingOptimizeResultsHtml(payload);
    assert.match(html, /Sell Texas home \(2032\)/);
    assert.match(html, /Buy in Florida \(2038\)/);
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tests/frontend/housing_optimize_panel.test.mjs`
Expected: FAIL — current output is `"Sell 2035 → Buy 2032 in Illinois"` and `"Sell 2032 → Buy 2038 in Florida"` (no "original home"/"Texas home" distinction).

- [ ] **Step 3: Rewrite `housingOptMoveText`**

`housingOptMoveText` is called once per move with no positional context today. Move 2's "sold home" label needs move 1's *location* (not just a first/second flag), so give it a `soldHomeLabel` string parameter supplied by a new small wrapper, `housingOptMovesText`, that knows both moves' locations. Replace lines 1232-1239:

```js
function housingOptMoveText(move, soldHomeLabel) {
  if (!move) return "";
  const flag = move.sec121_exclusion_lost
    ? ' <span class="small warning">(likely loses §121 exclusion)</span>'
    : "";
  if (move.rent_indefinitely) {
    return `Sell ${esc(soldHomeLabel)} (${move.sale_year}) then Rent in ${esc(move.location.state)}${flag}`;
  }
  const buyText = `Buy in ${esc(move.location.state)} (${move.purchase_year})`;
  const sellText = `Sell ${esc(soldHomeLabel)} (${move.sale_year})`;
  const overlapNote =
    move.purchase_year < move.sale_year
      ? ` <span class="small">(own both homes ${move.purchase_year}-${move.sale_year})</span>`
      : "";
  const ordered = move.purchase_year < move.sale_year ? [buyText, sellText] : [sellText, buyText];
  return ordered.join(" then ") + overlapNote + flag;
}
```

Update both call sites in `renderHousingOptimizeResultsHtml` (the `head` line and the `altRows` map, currently lines 1272 and 1275-1277) to pass the right label per move index — move 0 sells "original home", move 1 sells "`${location_1 state} home`":

```js
function housingOptMovesText(moves) {
  return (moves || [])
    .map((m, idx) => housingOptMoveText(m, idx === 0 ? "original home" : `${moves[0].location.state} home`))
    .join(" then ");
}
```

Replace `rec.moves.map(housingOptMoveText).join(" then ")` (line 1272) with `housingOptMovesText(rec.moves)`, and `row.moves.map(housingOptMoveText).join("<br>")` (line 1276) with `housingOptMovesText(row.moves).replace(/ then /g, "<br>")`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test tests/frontend/housing_optimize_panel.test.mjs`
Expected: PASS — all tests in the file, including the two pre-existing ones that match `/Sell 2027/` and `/Buy 2028/` (still true: for that fixture `purchase_year=2028 > sale_year=2027`, so `sellText` renders first — `"Sell original home (2027) then Buy in Texas (2028)"` still contains both substrings).

- [ ] **Step 5: Commit**

```bash
git add frontend/js/dashboard_decomp_housing_scenarios.js tests/frontend/housing_optimize_panel.test.mjs
git commit -m "$(cat <<'EOF'
Fix housing optimizer move-label rendering

housingOptMoveText always rendered "Sell X -> Buy Y" regardless of
which year was earlier, and never said which home was being sold.
The underlying numbers were already correct (a legitimate bridge-buy
or immediate-flip) -- only the label was misleading. Now orders each
move's transactions chronologically, names which home is sold, and
notes the overlap period when purchase precedes sale.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Per-move buy/rent action constraint (backend)

**Files:**
- Modify: `src/housing_optimizer.py`: `optimize_housing` (`:732-829`), `generate_move1_candidates`/loop in `optimize_housing` (`:302-313`, `:763-774`), `_score_move1_point`/`generate_move1_candidates_narrowed` (`:621-670`), `generate_move2_candidates`/loop (`:316-344`, `:801-811`), `_score_move2_point`/`generate_move2_candidates_narrowed` (`:673-725`), `optimize_housing_from_request` (`:926-977`)
- Modify: `src/api_contracts.py:125-137`
- Test: `tests/test_housing_optimizer_unit.py`, `tests/test_housing_optimizer_integration.py`

**Interfaces:**
- Consumes: nothing new from earlier tasks.
- Produces: `optimize_housing(..., move1_action: Literal['auto','buy','rent'] = 'auto', move2_action: Literal['auto','buy','rent'] = 'auto')`. `optimize_housing_from_request` reads `body.get('move1_action', 'auto')` / `body.get('move2_action', 'auto')`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_housing_optimizer_unit.py`:

```python
def test_move1_action_buy_only_excludes_rent_indefinitely_candidates():
    window = SearchWindow(earliest_sale_year=2027, latest_sale_year=2027,
                           earliest_purchase_year=2027, latest_purchase_year=2028)
    from src.housing_optimizer import filter_candidates_by_action
    cands = generate_move1_candidates([TX], window, no_dual_ownership=False)
    buy_only = filter_candidates_by_action(cands, "buy", purchase_year_attr="purchase_year")
    assert buy_only
    assert all(c.purchase_year is not None for c in buy_only)


def test_move1_action_rent_only_excludes_purchase_candidates():
    window = SearchWindow(earliest_sale_year=2027, latest_sale_year=2027,
                           earliest_purchase_year=2027, latest_purchase_year=2028)
    from src.housing_optimizer import filter_candidates_by_action
    cands = generate_move1_candidates([TX], window, no_dual_ownership=False)
    rent_only = filter_candidates_by_action(cands, "rent", purchase_year_attr="purchase_year")
    assert rent_only
    assert all(c.purchase_year is None for c in rent_only)


def test_move1_action_auto_keeps_everything():
    window = SearchWindow(earliest_sale_year=2027, latest_sale_year=2027,
                           earliest_purchase_year=2027, latest_purchase_year=2028)
    from src.housing_optimizer import filter_candidates_by_action
    cands = generate_move1_candidates([TX], window, no_dual_ownership=False)
    auto = filter_candidates_by_action(cands, "auto", purchase_year_attr="purchase_year")
    assert len(auto) == len(cands)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_housing_optimizer_unit.py -k move1_action -v`
Expected: FAIL — `ImportError: cannot import name 'filter_candidates_by_action'`.

- [ ] **Step 3: Add the filter helper and wire it into both search modes**

Add near `sec121_exclusion_flag` (after line 507) in `src/housing_optimizer.py`:

```python
def filter_candidates_by_action(
    candidates: list[HousingCandidate], action: str, purchase_year_attr: str,
) -> list[HousingCandidate]:
    """Drops candidates inconsistent with a 'buy only'/'rent only' move
    constraint. ``purchase_year_attr`` is ``'purchase_year'`` for move 1,
    ``'purchase_year_2'`` for move 2 -- both fields use the same None-means-
    rent convention (module docstring)."""
    if action == 'auto':
        return candidates
    if action == 'buy':
        return [c for c in candidates if getattr(c, purchase_year_attr) is not None]
    if action == 'rent':
        return [c for c in candidates if getattr(c, purchase_year_attr) is None]
    raise ValueError(f"Unknown action: {action!r}")
```

In `optimize_housing`'s signature (line 732-745), add two parameters after `move2_strategy`:

```python
    move2_strategy: Literal['anchored', 'cross_product'] = 'anchored',
    move1_action: Literal['auto', 'buy', 'rent'] = 'auto',
    move2_action: Literal['auto', 'buy', 'rent'] = 'auto',
```

Right after the existing `move2_strategy` validation (`if move2_strategy not in MOVE2_STRATEGIES: raise ValueError(...)`, line 750-751), add:

```python
    if move1_action not in ('auto', 'buy', 'rent'):
        raise ValueError(f"Unknown move1_action: {move1_action!r}")
    if move2_action not in ('auto', 'buy', 'rent'):
        raise ValueError(f"Unknown move2_action: {move2_action!r}")
```

For the full-grid move-1 loop (lines 763-774), filter right after generation:

```python
    else:
        move1_scored = []
        move1_cands = filter_candidates_by_action(
            generate_move1_candidates(locations, move1_window, no_dual_ownership), move1_action, 'purchase_year',
        )
        for cand in move1_cands:
            ok, via_rental = family_presence_ok(base_state, cand, family_presence)
            if not ok:
                continue
            c2, rows = _run_engine(c0, cand)
            if not rows:
                continue
            sc = score_candidate(c2, cand, rows)
            sc.family_presence_via_rental = via_rental
            move1_scored.append(sc)
```

For the narrowed move-1 path, `generate_move1_candidates_narrowed` (lines 641-670) and its `_score_move1_point` (lines 621-638) gain the constraint as an early-return, the same way `no_dual_ownership` already works. Replace `_score_move1_point`'s signature and first line:

```python
def _score_move1_point(
    c0: dict[str, Any], base_state: str, loc: Location, family_presence: FamilyPresence | None,
    no_dual_ownership: bool, move1_action: str, pass1_objective: str, sink: list[ScoredCandidate],
    sale_year: int, purchase_year: int | None,
) -> float | None:
    if no_dual_ownership and purchase_year is not None and purchase_year < sale_year:
        return None
    if move1_action == 'buy' and purchase_year is None:
        return None
    if move1_action == 'rent' and purchase_year is not None:
        return None
```

(keep the rest of the function body unchanged). Update `generate_move1_candidates_narrowed`'s signature to accept and thread `move1_action` through both `lambda` calls (lines 641-670):

```python
def generate_move1_candidates_narrowed(
    c0: dict[str, Any], base_state: str, locations: list[Location], window: SearchWindow,
    no_dual_ownership: bool, move1_action: str, family_presence: FamilyPresence | None, pass1_objective: str,
) -> list[ScoredCandidate]:
    scored: list[ScoredCandidate] = []
    for loc in locations:
        _coordinate_search_2d(
            (window.earliest_sale_year, window.latest_sale_year),
            (window.earliest_purchase_year, window.latest_purchase_year),
            lambda sy, py: _score_move1_point(
                c0, base_state, loc, family_presence, no_dual_ownership, move1_action, pass1_objective, scored, sy, py,
            ),
        )
        if move1_action != 'buy':
            _coordinate_search_1d(
                (window.earliest_sale_year, window.latest_sale_year),
                lambda sy: _score_move1_point(
                    c0, base_state, loc, family_presence, no_dual_ownership, move1_action, pass1_objective, scored, sy, None,
                ),
            )
    return scored
```

(The rent-indefinitely 1D search is skipped outright when `move1_action == 'buy'`, since every point it would evaluate is rejected anyway — an optimization, not a behavior change vs. relying on `_score_move1_point`'s guard alone.)

Apply the identical treatment to move 2: `_score_move2_point` (lines 673-693) gains the same two-line guard using `move2_action`/`purchase_year_2`; `generate_move2_candidates_narrowed` (lines 696-725) gains a `move2_action` parameter threaded the same way, skipping its 1D rent search when `move2_action == 'buy'`. For the full-grid move-2 loop (lines 801-811):

```python
        else:
            move2_cands = filter_candidates_by_action(
                generate_move2_candidates(anchors, locations, move2_window, no_dual_ownership),
                move2_action, 'purchase_year_2',
            )
            for cand in move2_cands:
                ok, via_rental = family_presence_ok(base_state, cand, family_presence)
                if not ok:
                    continue
                c2, rows = _run_engine(c0, cand)
                if not rows:
                    continue
                sc = score_candidate(c2, cand, rows)
                sc.family_presence_via_rental = via_rental
                move2_scored.append(sc)
```

Update the two call sites that invoke the narrowed generators (`optimize_housing`, lines 759-762 and 796-800) to pass `move1_action`/`move2_action` through:

```python
    if narrowed:
        move1_scored = generate_move1_candidates_narrowed(
            c0, base_state, locations, move1_window, no_dual_ownership, move1_action, family_presence, pass1_objective,
        )
```

```python
        if narrowed:
            move2_scored = generate_move2_candidates_narrowed(
                c0, base_state, anchors, locations, move2_window, no_dual_ownership, move2_action, family_presence,
                pass1_objective,
            )
```

Finally, in `optimize_housing_from_request` (around line 964-970), pass the two new fields through, reading them the same way `no_dual_ownership` is read:

```python
        result = optimize_housing(
            c0,
            locations=locations,
            move1_window=move1_window,
            move2_window=move2_window,
            anchor_count=int(body.get('anchor_count', 5) or 5),
            no_dual_ownership=bool(body.get('no_dual_ownership', True)),
            family_presence=family_presence,
            objective=objective,
            search_mode=search_mode,
            move2_strategy=move2_strategy,
            move1_action=str(body.get('move1_action', 'auto') or 'auto'),
            move2_action=str(body.get('move2_action', 'auto') or 'auto'),
        )
```

In `src/api_contracts.py`, add the two fields to the `/api/housing/optimize` contract's `request_fields` tuple (line 127-131):

```python
        request_fields=(
            _f("locations", "list", True), _f("move1_window", "dict", True), _f("move2_window", "dict"),
            _f("anchor_count", "int"), _f("no_dual_ownership", "bool"), _f("family_presence", "dict"),
            _f("objective", "str"), _f("move1_action", "str"), _f("move2_action", "str"),
        ),
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_housing_optimizer_unit.py tests/test_housing_optimizer_integration.py -v`
Expected: PASS — full files.

- [ ] **Step 5: Add integration-level coverage that both search modes honor the constraint**

Add to `tests/test_housing_optimizer_integration.py` (find the existing engine-backed fixture/config helper used by other tests in that file, e.g. a `_base_config()`-style helper, and reuse it rather than hand-building a plan config here):

```python
def test_move1_action_rent_only_is_honored_in_both_search_modes(base_plan_config):
    from src.housing_optimizer import Location, SearchWindow, optimize_housing

    locations = [Location(state="Texas"), Location(state="Florida")]
    window = SearchWindow(earliest_sale_year=2027, latest_sale_year=2027,
                           earliest_purchase_year=2027, latest_purchase_year=2028)
    for mode in ("full", "narrowed"):
        result = optimize_housing(
            base_plan_config, locations=locations, move1_window=window,
            move1_action="rent", search_mode=mode, shortlist_size=1,
        )
        for cand in [result["recommendation"], *result["alternatives"]]:
            if cand is None:
                continue
            assert cand["moves"][0]["rent_indefinitely"] is True
```

(Replace `base_plan_config` with whatever fixture name `tests/test_housing_optimizer_integration.py` actually uses — read its existing tests first; this plan cannot see a fixture name that doesn't yet exist in isolation from that file.)

- [ ] **Step 6: Run and commit**

Run: `pytest tests/test_housing_optimizer_integration.py -v`
Expected: PASS.

```bash
git add src/housing_optimizer.py src/api_contracts.py tests/test_housing_optimizer_unit.py tests/test_housing_optimizer_integration.py
git commit -m "$(cat <<'EOF'
Add per-move buy/rent action constraint to the housing optimizer

move1_action/move2_action ('auto'|'buy'|'rent', default 'auto'
preserving today's full-auto-search behavior) let a caller force a
move to be evaluated as purchase-only or rent-only, in both the full
grid and narrowed search paths.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Per-move action constraint UI (frontend)

**Files:**
- Modify: `frontend/js/dashboard_decomp_housing_scenarios.js:1191-1201` (move-1/move-2 window sections), `:1300-1319` (`runHousingOptimization` body build)
- Test: `tests/frontend/housing_optimize_panel.test.mjs`

**Interfaces:**
- Consumes: nothing new.
- Produces: `runHousingOptimization()`'s POST body gains `move1_action`/`move2_action` (default `"auto"`).

- [ ] **Step 1: Write the failing test**

Add to `tests/frontend/housing_optimize_panel.test.mjs`:

```js
  test("defaults move1_action/move2_action to auto and reads the selects when present", async () => {
    const sandbox = freshSandbox();
    const values = {
      housingOptLocCount: "2", housingOptLocState0: "Texas", housingOptLocState1: "Florida",
      housingOptEarliestSale: "2027", housingOptLatestSale: "2028",
      housingOptEarliestPurchase: "2027", housingOptLatestPurchase: "2028",
      housingOptObjective: "net_worth", housingOptSearchMode: "full",
      housingOptMove2Strategy: "anchored", housingOptMove1Action: "rent",
    };
    const resultsEl = { innerHTML: "" };
    sandbox.document.getElementById = (id) => {
      if (id === "housingOptimizeResults") return resultsEl;
      if (id in values) return { value: values[id] };
      return { value: "" };
    };
    let capturedBody = null;
    sandbox.api = async (url, opts) => {
      capturedBody = JSON.parse(opts.body);
      return { success: true, recommendation: null, alternatives: [] };
    };
    await sandbox.runHousingOptimization();
    assert.equal(capturedBody.move1_action, "rent");
    assert.equal(capturedBody.move2_action, "auto");
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/frontend/housing_optimize_panel.test.mjs`
Expected: FAIL — `capturedBody.move1_action` is `undefined`.

- [ ] **Step 3: Add the selects and wire them into the payload**

In `frontend/js/dashboard_decomp_housing_scenarios.js`, add an action select right after the "Move 1 search window" label block (after line 1195, before the "Consider a second move" checkbox line 1196):

```js
    <label>Move 1 action
      <select id="housingOptMove1Action">
        <option value="auto" selected>Auto (search buy &amp; rent)</option>
        <option value="buy">Buy only</option>
        <option value="rent">Rent only</option>
      </select>
    </label>
```

Add the move-2 equivalent inside the `housingOptMove2Fields` div (after line 1200, `Anchor count`):

```js
      <label>Move 2 action
        <select id="housingOptMove2Action">
          <option value="auto" selected>Auto (search buy &amp; rent)</option>
          <option value="buy">Buy only</option>
          <option value="rent">Rent only</option>
        </select>
      </label>
```

In `runHousingOptimization`'s `body` object (lines 1300-1313), add two keys after `move2_strategy`:

```js
    move2_strategy: String(document.getElementById("housingOptMove2Strategy")?.value || "anchored"),
    move1_action: String(document.getElementById("housingOptMove1Action")?.value || "auto"),
    move2_action: String(document.getElementById("housingOptMove2Action")?.value || "auto"),
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test tests/frontend/housing_optimize_panel.test.mjs`
Expected: PASS — all tests in the file.

- [ ] **Step 5: Commit**

```bash
git add frontend/js/dashboard_decomp_housing_scenarios.js tests/frontend/housing_optimize_panel.test.mjs
git commit -m "$(cat <<'EOF'
Housing optimizer: add per-move buy/rent action selects to the UI

Wires the move1_action/move2_action backend fields from the previous
commit into the panel, defaulting to Auto so nothing changes unless
the user opts into constraining a move.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Concurrent move-2 mode (backend)

**Files:**
- Modify: `src/housing_optimizer.py`: `HousingCandidate` (`:153-171`), `_apply_candidate` (`:255-291`), `_location_timeline` (`:462-475`), `family_presence_ok` (`:478-495`), `score_candidate` (`:537-552`), `_format_move`/`_format_candidate` (`:832-867`), `optimize_housing` (`:732-829`), `optimize_housing_from_request` (`:926-977`)
- Modify: `src/api_contracts.py:125-137`
- Test: `tests/test_housing_optimizer_unit.py`, `tests/test_housing_optimizer_integration.py`

**Interfaces:**
- Consumes: `filter_candidates_by_action` from Task 7 (concurrent candidates get the same move2_action filter).
- Produces: `HousingCandidate.move2_mode: Literal['sequential', 'concurrent'] = 'sequential'`, `HousingCandidate.concurrent_start_year_2: int | None = None`. New function `generate_move2_concurrent_candidates(anchors, locations, move2_window) -> list[HousingCandidate]`. `optimize_housing(..., move2_concurrent: bool = False)` raises `ValueError` if combined with `search_mode='narrowed'`. Each formatted move dict gains `mode: 'sequential' | 'concurrent'` and `start_year: int | None`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_housing_optimizer_unit.py`:

```python
def test_generate_move2_concurrent_candidates_keeps_move1_home_and_adds_location_2():
    from src.housing_optimizer import generate_move2_concurrent_candidates

    anchor = HousingCandidate(location_1=TX, sale_year=2027, purchase_year=2028)
    move2_window = Move2Window(latest_sale_year_2=9999, latest_purchase_year_2=2032)
    cands = generate_move2_concurrent_candidates([anchor], [FL], move2_window)
    assert cands
    assert all(c.move2_mode == "concurrent" for c in cands)
    assert all(c.sale_year_2 is None for c in cands)  # nothing is ever sold in concurrent mode
    assert all(c.location_1.state == "Texas" and c.location_2.state == "Florida" for c in cands)
    assert any(c.purchase_year_2 is not None for c in cands)  # buy variant
    assert any(c.purchase_year_2 is None for c in cands)      # rent variant
    assert all(c.concurrent_start_year_2 >= anchor.purchase_year for c in cands)


def test_generate_move2_concurrent_candidates_skips_rent_indefinitely_move1_anchor():
    from src.housing_optimizer import generate_move2_concurrent_candidates

    rent_forever = HousingCandidate(location_1=TX, sale_year=2027, purchase_year=None)
    move2_window = Move2Window(latest_sale_year_2=9999, latest_purchase_year_2=2032)
    assert generate_move2_concurrent_candidates([rent_forever], [FL], move2_window) == []


def test_family_presence_ok_concurrent_mode_covers_either_location():
    cand = HousingCandidate(
        location_1=TX, sale_year=2027, purchase_year=2027,
        location_2=FL, sale_year_2=None, purchase_year_2=2030,
        move2_mode="concurrent", concurrent_start_year_2=2030,
    )
    presence_matches_location_2_only = FamilyPresence(region="Florida", start_year=2031, end_year=2032)
    ok, via_rental = family_presence_ok("Texas", cand, presence_matches_location_2_only)
    assert ok is True
    assert via_rental is False

    presence_before_location_2_exists = FamilyPresence(region="Florida", start_year=2028, end_year=2029)
    ok2, _ = family_presence_ok("Texas", cand, presence_before_location_2_exists)
    assert ok2 is False


def test_family_presence_ok_concurrent_mode_via_rental_when_location_2_is_rented():
    cand = HousingCandidate(
        location_1=TX, sale_year=2027, purchase_year=2027,
        location_2=FL, sale_year_2=None, purchase_year_2=None,
        move2_mode="concurrent", concurrent_start_year_2=2030,
    )
    presence = FamilyPresence(region="Florida", start_year=2031, end_year=2031)
    ok, via_rental = family_presence_ok("Texas", cand, presence)
    assert ok is True
    assert via_rental is True


def test_score_candidate_concurrent_mode_never_flags_sec121_for_move_2():
    cand = HousingCandidate(
        location_1=TX, sale_year=2027, purchase_year=2027,
        location_2=FL, sale_year_2=None, purchase_year_2=2028,
        move2_mode="concurrent", concurrent_start_year_2=2028,
    )
    sc = score_candidate({}, cand, [{"total_nw": 100.0}])
    assert sc.sec121_exclusion_lost == [False, False]


def test_format_candidate_concurrent_move_carries_mode_and_start_year():
    from src.housing_optimizer import _format_candidate

    cand = HousingCandidate(
        location_1=TX, sale_year=2027, purchase_year=2027,
        location_2=FL, sale_year_2=None, purchase_year_2=None,
        move2_mode="concurrent", concurrent_start_year_2=2030,
    )
    sc = ScoredCandidate(candidate=cand, net_worth=1.0, lifetime_cost=1.0, mc_success_rate=None,
                          sec121_exclusion_lost=[False, False])
    formatted = _format_candidate(sc, "net_worth")
    move2 = formatted["moves"][1]
    assert move2["mode"] == "concurrent"
    assert move2["start_year"] == 2030
    assert move2["sale_year"] is None
    assert move2["rent_indefinitely"] is True


def test_optimize_housing_rejects_concurrent_with_narrowed_search():
    with pytest.raises(ValueError, match="narrowed"):
        optimize_housing_from_request({}, {
            "locations": [{"state": "Texas"}, {"state": "Florida"}],
            "move1_window": {"earliest_sale_year": 2027, "latest_sale_year": 2027,
                              "earliest_purchase_year": 2027, "latest_purchase_year": 2027},
            "move2_window": {"latest_sale_year_2": 9999, "latest_purchase_year_2": 2030},
            "move2_concurrent": True, "search_mode": "narrowed",
        })
```

(The last test calls `optimize_housing_from_request`, which returns `(payload, status)` rather than raising — adjust to match Step 3's actual error-surfacing choice: either it raises inside `optimize_housing` and `optimize_housing_from_request`'s existing `except ValueError` catches it into a 400 response, in which case assert `status == 400` and `"narrowed" in payload["error"]` instead of `pytest.raises`. Use that response-based assertion, not `pytest.raises`, since every other validation error in this module already goes through that path — see `optimize_housing_from_request`'s existing `except ValueError as exc: return {'success': False, 'error': str(exc)}, 400`.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_housing_optimizer_unit.py -k concurrent -v`
Expected: FAIL — `move2_mode`/`concurrent_start_year_2` don't exist, `generate_move2_concurrent_candidates` doesn't exist.

- [ ] **Step 3: Implement concurrent mode**

Replace the `HousingCandidate` dataclass (lines 153-171):

```python
@dataclass
class HousingCandidate:
    """One fully-specified plan variant: move 1, and optionally move 2.

    ``purchase_year is None`` means "rent indefinitely" after ``sale_year``
    (move 1) or after ``sale_year_2``/``concurrent_start_year_2`` (move 2,
    when ``purchase_year_2`` is also ``None``).

    ``move2_mode='sequential'`` (default): move 2 sells the move-1 home
    (``sale_year_2``) and relocates to ``location_2``, exactly as before this
    field existed. ``move2_mode='concurrent'``: the move-1 home is never sold
    -- ``location_2`` becomes a second, simultaneous residence starting at
    ``concurrent_start_year_2``. ``sale_year_2`` is always ``None`` in
    concurrent mode (nothing is ever sold under it).
    """
    location_1: Location
    sale_year: int
    purchase_year: int | None
    location_2: Location | None = None
    sale_year_2: int | None = None
    purchase_year_2: int | None = None
    move2_mode: Literal['sequential', 'concurrent'] = 'sequential'
    concurrent_start_year_2: int | None = None
    anchor_of: "HousingCandidate | None" = None

    @property
    def is_two_move(self) -> bool:
        return self.location_2 is not None
```

Replace `_apply_candidate` (lines 255-291):

```python
def _apply_candidate(c: dict[str, Any], cand: HousingCandidate) -> None:
    """Mutate engine config ``c`` in place to reflect ``cand`` -- rewrites
    ``next_housing_steps`` and ``residency_schedule`` only (§3.1/§3.2 of the
    design doc), plus the existing ``home_sale_yr`` field for move 1's sale
    of the current home. Intended as the ``mutate`` callback to
    ``planning_engines.run_scenario`` (deep-copies the base config first).
    """
    base_state = str(c.get('state', '') or '')
    c['home_sale_yr'] = cand.sale_year
    concurrent = cand.is_two_move and cand.move2_mode == 'concurrent'

    move1_start = cand.sale_year if cand.purchase_year is None else cand.purchase_year
    move1_end = None if concurrent else ((cand.sale_year_2 - 1) if cand.is_two_move else None)
    steps = []
    transitions: list[tuple[int, str]] = [(move1_start, cand.location_1.state)]
    if cand.purchase_year is None:
        steps.append(_rent_step('opt_move1', cand.location_1, cand.sale_year, move1_end))
    else:
        move1_step = _purchase_step('opt_move1', cand.location_1, cand.purchase_year, move1_end)
        if cand.is_two_move and not concurrent:
            # Real second-sale pathway (design doc §8.2 P0): the engine sells
            # this step itself -- see home_sale.py's apply_next_housing_sale
            # -- instead of this module estimating move 2's gain/tax
            # out-of-loop. `move1_end` above is already `sale_year_2 - 1`, so
            # the step also stops accruing ongoing cash flow the year before.
            # Concurrent mode never sets this: the move-1 home is never sold.
            move1_step['sale_year'] = cand.sale_year_2
        steps.append(move1_step)

    if cand.is_two_move:
        if concurrent:
            # location_2 is a second, ongoing residence alongside location_1
            # -- no residency_schedule transition (tax residency stays with
            # location_1; concurrent mode is a second home, not a move).
            move2_start = cand.concurrent_start_year_2
            if cand.purchase_year_2 is None:
                steps.append(_rent_step('opt_move2', cand.location_2, move2_start, None))
            else:
                steps.append(_purchase_step('opt_move2', cand.location_2, cand.purchase_year_2, None))
        else:
            move2_start = cand.sale_year_2 if cand.purchase_year_2 is None else cand.purchase_year_2
            transitions.append((move2_start, cand.location_2.state))
            if cand.purchase_year_2 is None:
                steps.append(_rent_step('opt_move2', cand.location_2, cand.sale_year_2, None))
            else:
                steps.append(_purchase_step('opt_move2', cand.location_2, cand.purchase_year_2, None))

    c['next_housing_steps'] = steps
    c['residency_schedule'] = _residency_schedule(base_state, transitions)
```

Replace `_location_timeline` (lines 462-475) — concurrent mode's second residence is handled separately by `family_presence_ok` below, so this function keeps returning only the single active-residence timeline (location_1 continuing indefinitely when concurrent):

```python
def _location_timeline(base_state: str, cand: HousingCandidate) -> list[tuple[int, int, str, bool]]:
    """Ordered ``(start_year, end_year_inclusive, state, is_rental)`` legs
    covering the whole plan horizon for the household's PRIMARY residence.
    For ``move2_mode='concurrent'``, this deliberately excludes location_2
    (a second, simultaneous residence, not a relocation) -- see
    ``family_presence_ok``, which checks location_2 separately for that case.
    """
    move1_start = cand.sale_year if cand.purchase_year is None else cand.purchase_year
    move1_is_rental = cand.purchase_year is None
    legs = [(1, move1_start - 1, base_state, False)]
    if cand.is_two_move and cand.move2_mode != 'concurrent':
        move2_start = cand.sale_year_2 if cand.purchase_year_2 is None else cand.purchase_year_2
        move2_is_rental = cand.purchase_year_2 is None
        legs.append((move1_start, move2_start - 1, cand.location_1.state, move1_is_rental))
        legs.append((move2_start, 9999, cand.location_2.state, move2_is_rental))
    else:
        legs.append((move1_start, 9999, cand.location_1.state, move1_is_rental))
    return legs
```

Replace `family_presence_ok` (lines 478-495):

```python
def family_presence_ok(base_state: str, cand: HousingCandidate, presence: FamilyPresence | None) -> tuple[bool, bool]:
    """Hard filter (§3.1.2/§3.2.2): returns ``(covered, via_rental)``.
    ``covered`` is False if any year in the presence window lacks an
    owned-or-rented residence in ``presence.region``. ``via_rental`` is True
    when a rent leg is what satisfies coverage for at least one of those
    years. For ``move2_mode='concurrent'``, coverage in a given year is
    satisfied by EITHER the primary residence (``_location_timeline``) or
    the concurrent second residence (location_2, active from
    ``concurrent_start_year_2`` onward) -- the whole point of concurrent mode
    is representing family presence in two places at once.
    """
    if presence is None:
        return True, False
    legs = _location_timeline(base_state, cand)
    concurrent = cand.is_two_move and cand.move2_mode == 'concurrent'
    via_rental = False
    for year in range(presence.start_year, presence.end_year + 1):
        leg = next((l for l in legs if l[0] <= year <= l[1]), None)
        primary_match = leg is not None and leg[2] == presence.region
        primary_rental = bool(leg and leg[3])
        concurrent_match = (
            concurrent and cand.concurrent_start_year_2 is not None
            and year >= cand.concurrent_start_year_2 and cand.location_2.state == presence.region
        )
        concurrent_rental = concurrent_match and cand.purchase_year_2 is None
        if not (primary_match or concurrent_match):
            return False, False
        if (primary_match and primary_rental) or (concurrent_match and concurrent_rental):
            via_rental = True
    return True, via_rental
```

Replace `score_candidate`'s sec121 handling (lines 537-552):

```python
def score_candidate(c: dict[str, Any], cand: HousingCandidate, rows: list[dict[str, Any]]) -> ScoredCandidate:
    """Score one engine run. Both moves' sale proceeds are already real
    deposits the engine's own run reflects in ``rows[-1]['total_nw']`` (see
    home_sale.py's ``apply_next_housing_sale`` and this module's docstring),
    so -- unlike the out-of-loop estimate this replaced -- no post-hoc net
    worth/lifetime cost adjustment is needed for move 2.
    """
    net_worth = float(rows[-1].get('total_nw', 0.0) or 0.0) if rows else 0.0
    lifetime_cost = _lifetime_cost(rows)
    sec121_flags = [False]  # move 1 sells the current/original home -- ownership start isn't tracked, assume met
    if cand.is_two_move:
        if cand.move2_mode == 'concurrent':
            sec121_flags.append(False)  # concurrent mode never sells anything -- nothing to flag
        else:
            sec121_flags.append(sec121_exclusion_flag(cand.purchase_year, cand.sale_year_2))
    return ScoredCandidate(
        candidate=cand, net_worth=net_worth, lifetime_cost=lifetime_cost,
        mc_success_rate=None, sec121_exclusion_lost=sec121_flags,
    )
```

Add `generate_move2_concurrent_candidates` right after `generate_move2_candidates` (after line 344):

```python
def generate_move2_concurrent_candidates(
    anchors: list[HousingCandidate], locations: list[Location], move2_window: Move2Window,
) -> list[HousingCandidate]:
    """Concurrent-mode move-2 candidates: the anchor's move-1 home
    (``location_1``) is kept as an ongoing residence and never sold;
    ``location_2`` is added as a second, simultaneous residence starting
    anywhere in ``[anchor.purchase_year, move2_window.latest_purchase_year_2]``
    (``latest_sale_year_2`` is not meaningful here -- nothing is ever sold,
    so it's not used). Both a purchase and a rent-indefinitely variant of
    location_2 are generated per (anchor, location, start_year) point,
    mirroring ``generate_move2_candidates``'s purchase/rent split. Anchors
    that ended move 1 in rent-indefinitely-forever are skipped -- same rule
    ``generate_move2_candidates`` applies (nothing to add a concurrent
    second home to).
    """
    out: list[HousingCandidate] = []
    for anchor in anchors:
        if anchor.purchase_year is None:
            continue
        earliest_start = anchor.purchase_year
        for loc in locations:
            for start_year in range(earliest_start, move2_window.latest_purchase_year_2 + 1):
                out.append(HousingCandidate(
                    location_1=anchor.location_1, sale_year=anchor.sale_year, purchase_year=anchor.purchase_year,
                    location_2=loc, sale_year_2=None, purchase_year_2=start_year,
                    move2_mode='concurrent', concurrent_start_year_2=start_year, anchor_of=anchor,
                ))
                out.append(HousingCandidate(
                    location_1=anchor.location_1, sale_year=anchor.sale_year, purchase_year=anchor.purchase_year,
                    location_2=loc, sale_year_2=None, purchase_year_2=None,
                    move2_mode='concurrent', concurrent_start_year_2=start_year, anchor_of=anchor,
                ))
    return out
```

Replace `_format_move`/`_format_candidate` (lines 832-867):

```python
def _format_move(location: Location | None, sale_year: int | None, purchase_year: int | None,
                  sec121_lost: bool, mode: str = 'sequential', start_year: int | None = None) -> dict[str, Any] | None:
    if location is None:
        return None
    return {
        'sale_year': sale_year,
        'purchase_year': purchase_year,
        'start_year': start_year,
        'mode': mode,
        'rent_indefinitely': purchase_year is None,
        'location': {
            'state': location.state,
            'city_type': location.city_type,
            'population_size': location.population_size,
        },
        'sec121_exclusion_lost': sec121_lost,
    }


def _format_candidate(sc: ScoredCandidate, objective: str) -> dict[str, Any]:
    cand = sc.candidate
    moves = [_format_move(cand.location_1, cand.sale_year, cand.purchase_year,
                           sc.sec121_exclusion_lost[0] if sc.sec121_exclusion_lost else False)]
    if cand.is_two_move:
        sec121_2 = sc.sec121_exclusion_lost[1] if len(sc.sec121_exclusion_lost) > 1 else False
        if cand.move2_mode == 'concurrent':
            moves.append(_format_move(cand.location_2, None, cand.purchase_year_2, sec121_2,
                                       mode='concurrent', start_year=cand.concurrent_start_year_2))
        else:
            moves.append(_format_move(cand.location_2, cand.sale_year_2, cand.purchase_year_2, sec121_2))
    return {
        'moves': moves,
        'net_worth': sc.net_worth,
        'lifetime_cost': sc.lifetime_cost,
        'mc_success_rate': sc.mc_success_rate,
        'objective_value': {
            'net_worth': sc.net_worth,
            'lifetime_cost': sc.lifetime_cost,
            'mc_success_rate': sc.mc_success_rate,
        }[objective],
        'family_presence_via_rental': sc.family_presence_via_rental,
    }
```

Wire it into `optimize_housing`: add `move2_concurrent: bool = False` to the signature (alongside `move1_action`/`move2_action` from Task 7), validate it right after the `move2_action` check:

```python
    if move2_concurrent and search_mode == 'narrowed':
        raise ValueError("move2_concurrent is only supported with search_mode='full'.")
```

Then, inside the `if move2_window is not None:` block (lines 778-812), after the existing sequential `move2_scored` is built and ranked (right after the line `move2_scored = rank_candidates(move2_scored, pass1_objective)`, still inside the `if move2_window is not None:` block), add:

```python
        if move2_concurrent:
            concurrent_cands = filter_candidates_by_action(
                generate_move2_concurrent_candidates(anchors, locations, move2_window),
                move2_action, 'purchase_year_2',
            )
            concurrent_scored = []
            for cand in concurrent_cands:
                ok, via_rental = family_presence_ok(base_state, cand, family_presence)
                if not ok:
                    continue
                c2, rows = _run_engine(c0, cand)
                if not rows:
                    continue
                sc = score_candidate(c2, cand, rows)
                sc.family_presence_via_rental = via_rental
                concurrent_scored.append(sc)
            move2_scored = rank_candidates(move2_scored + concurrent_scored, pass1_objective)
```

(`anchors` here is whatever the existing code above already selected -- `select_anchors(...)` or `select_all_eligible_move1_candidates(...)` — reuse it, don't reselect.)

Update `optimize_housing_from_request` to read and pass `move2_concurrent`:

```python
            move1_action=str(body.get('move1_action', 'auto') or 'auto'),
            move2_action=str(body.get('move2_action', 'auto') or 'auto'),
            move2_concurrent=bool(body.get('move2_concurrent', False)),
```

In `src/api_contracts.py`, add `_f("move2_concurrent", "bool")` to the `/api/housing/optimize` `request_fields` tuple built in Task 7.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_housing_optimizer_unit.py tests/test_housing_optimizer_integration.py -v`
Expected: PASS — full files.

- [ ] **Step 5: Add one engine-backed integration test proving concurrent mode changes the actual run**

Add to `tests/test_housing_optimizer_integration.py`, reusing whatever base-config fixture the file already has (see Task 7 Step 5 note):

```python
def test_move2_concurrent_produces_two_simultaneous_housing_steps(base_plan_config):
    from src.housing_optimizer import (
        FamilyPresence, Location, Move2Window, SearchWindow, optimize_housing,
    )

    result = optimize_housing(
        base_plan_config,
        locations=[Location(state="Texas")],
        move1_window=SearchWindow(2027, 2027, 2027, 2027),
        move2_window=Move2Window(latest_sale_year_2=9999, latest_purchase_year_2=2029),
        move2_concurrent=True,
        family_presence=FamilyPresence(region="Texas", start_year=2029, end_year=2030),
        shortlist_size=1,
    )
    assert result["recommendation"] is not None
    move2 = result["recommendation"]["moves"][1]
    assert move2["mode"] == "concurrent"
```

(Adjust `Location`'s state to whichever candidate the shortlist actually recommends if `"Texas"` alone doesn't produce a two-move recommendation against the real engine — run it once locally and inspect `result` to confirm, per Step 6 below, rather than guessing blind.)

- [ ] **Step 6: Run and commit**

Run: `pytest tests/test_housing_optimizer_integration.py -v`
Expected: PASS. If the new integration test's assumption about what the optimizer recommends doesn't hold against the real engine, adjust the test's inputs (locations, windows, family_presence) until it does — the assertion (`move2["mode"] == "concurrent"`) is the fixed target, not the specific years/states used to reach it.

```bash
git add src/housing_optimizer.py src/api_contracts.py tests/test_housing_optimizer_unit.py tests/test_housing_optimizer_integration.py
git commit -m "$(cat <<'EOF'
Add concurrent (non-sequential) move-2 mode to the housing optimizer

move2_mode='concurrent' keeps the move-1 home as an ongoing residence
and adds location_2 as a second, simultaneous residence (buy or rent)
instead of selling and relocating -- lets the optimizer recommend
buy-here-rent-there in parallel when family presence is needed in two
regions at once, which no existing mode could represent.
search_mode='full' only this pass; 'narrowed' rejects the combination.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Concurrent move-2 UI (frontend)

**Files:**
- Modify: `frontend/js/dashboard_decomp_housing_scenarios.js`: move-2 fields section (`:1197-1201`), `runHousingOptimization` body (`:1300-1319`), `housingOptMoveText`/`housingOptMovesText` (Task 6's version)
- Test: `tests/frontend/housing_optimize_panel.test.mjs`

**Interfaces:**
- Consumes: `move2["mode"]`/`move2["start_year"]` from Task 9's `_format_candidate`.
- Produces: `runHousingOptimization()`'s POST body gains `move2_concurrent: boolean`. `housingOptMovesText` renders a concurrent move 2 distinctly from a sequential one.

- [ ] **Step 1: Write the failing tests**

Add to `tests/frontend/housing_optimize_panel.test.mjs`:

```js
  test("disables the concurrent checkbox when narrowed search is selected, with an inline note", () => {
    const sandbox = freshSandbox();
    const html = sandbox.renderHousingOptimizePanelHtml();
    assert.match(html, /id="housingOptMove2Concurrent"/);
    assert.match(html, /concurrent[\s\S]{0,200}narrowed/i);
  });

  test("posts move2_concurrent to the API", async () => {
    const sandbox = freshSandbox();
    const values = {
      housingOptLocCount: "2", housingOptLocState0: "Texas", housingOptLocState1: "Florida",
      housingOptEarliestSale: "2027", housingOptLatestSale: "2028",
      housingOptEarliestPurchase: "2027", housingOptLatestPurchase: "2028",
      housingOptObjective: "net_worth", housingOptSearchMode: "full",
      housingOptMove2Strategy: "anchored",
    };
    const resultsEl = { innerHTML: "" };
    const move2Concurrent = { checked: true };
    sandbox.document.getElementById = (id) => {
      if (id === "housingOptimizeResults") return resultsEl;
      if (id === "housingOptMove2Concurrent") return move2Concurrent;
      if (id in values) return { value: values[id] };
      return { value: "" };
    };
    let capturedBody = null;
    sandbox.api = async (url, opts) => {
      capturedBody = JSON.parse(opts.body);
      return { success: true, recommendation: null, alternatives: [] };
    };
    await sandbox.runHousingOptimization();
    assert.equal(capturedBody.move2_concurrent, true);
  });

  test("renders a concurrent move 2 distinctly from a sequential one", () => {
    const sandbox = freshSandbox();
    const payload = samplePayload();
    payload.recommendation.moves.push({
      sale_year: null, purchase_year: 2030, start_year: 2030, mode: "concurrent",
      rent_indefinitely: false,
      location: { state: "Illinois", city_type: "suburban", population_size: 20000 },
      sec121_exclusion_lost: false,
    });
    const html = sandbox.renderHousingOptimizeResultsHtml(payload);
    assert.match(html, /concurrent/i);
    assert.match(html, /Illinois/);
    assert.doesNotMatch(html, /Sell.*Illinois/);
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tests/frontend/housing_optimize_panel.test.mjs`
Expected: FAIL — no `housingOptMove2Concurrent` element, no `move2_concurrent` in the payload, and `housingOptMoveText`/`housingOptMovesText` don't understand `mode: "concurrent"`.

- [ ] **Step 3: Add the UI**

Add the concurrent checkbox inside `housingOptMove2Fields` (after the "Move 2 action" select added in Task 8), and gate it on search mode:

```js
      <label><input type="checkbox" id="housingOptMove2Concurrent" onchange="toggleHousingOptMove2ConcurrentAvailability()"> Concurrent with move 1 (keep move-1 home, add this as a second residence)</label>
      <div id="housingOptMove2ConcurrentNarrowedNote" class="small" hidden>Concurrent mode is only available with Full grid search mode; switch Search mode above to enable it.</div>
```

Add a small toggler function near `toggleHousingOptMove2Fields` (line 1163-1167):

```js
export function toggleHousingOptMove2ConcurrentAvailability() {
  const searchMode = String(document.getElementById("housingOptSearchMode")?.value || "full");
  const concurrentCb = document.getElementById("housingOptMove2Concurrent");
  const note = document.getElementById("housingOptMove2ConcurrentNarrowedNote");
  const narrowed = searchMode === "narrowed";
  if (concurrentCb) {
    if (narrowed) concurrentCb.checked = false;
    concurrentCb.disabled = narrowed;
  }
  if (note) note.hidden = !narrowed;
}
```

Wire it to also run when search mode changes — add `onchange="toggleHousingOptMove2ConcurrentAvailability()"` to the existing `housingOptSearchMode` select (currently plain, lines 1211-1216):

```js
    <label>Search mode
      <select id="housingOptSearchMode" onchange="toggleHousingOptMove2ConcurrentAvailability()">
```

Add `toggleHousingOptMove2ConcurrentAvailability` to the `Object.assign(window, {...})` bridge at the bottom of the file (alongside `toggleHousingOptMove2Fields`).

In `runHousingOptimization`'s `body` object, add after `move2_action`:

```js
    move2_concurrent: !!document.getElementById("housingOptMove2Concurrent")?.checked,
```

- [ ] **Step 4: Update move rendering for concurrent moves**

Replace `housingOptMoveText`/`housingOptMovesText` from Task 6 with a version that branches on `move.mode`:

```js
function housingOptMoveText(move, soldHomeLabel) {
  if (!move) return "";
  const flag = move.sec121_exclusion_lost
    ? ' <span class="small warning">(likely loses §121 exclusion)</span>'
    : "";
  if (move.mode === "concurrent") {
    const action = move.rent_indefinitely
      ? `Also rent in ${esc(move.location.state)} from ${move.start_year}`
      : `Also buy in ${esc(move.location.state)} (${move.start_year})`;
    return `${action} (concurrent with move 1, home 1 kept)${flag}`;
  }
  if (move.rent_indefinitely) {
    return `Sell ${esc(soldHomeLabel)} (${move.sale_year}) then Rent in ${esc(move.location.state)}${flag}`;
  }
  const buyText = `Buy in ${esc(move.location.state)} (${move.purchase_year})`;
  const sellText = `Sell ${esc(soldHomeLabel)} (${move.sale_year})`;
  const overlapNote =
    move.purchase_year < move.sale_year
      ? ` <span class="small">(own both homes ${move.purchase_year}-${move.sale_year})</span>`
      : "";
  const ordered = move.purchase_year < move.sale_year ? [buyText, sellText] : [sellText, buyText];
  return ordered.join(" then ") + overlapNote + flag;
}

function housingOptMovesText(moves) {
  return (moves || [])
    .map((m, idx) => housingOptMoveText(m, idx === 0 ? "original home" : `${moves[0].location.state} home`))
    .join(" then ");
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `node --test tests/frontend/housing_optimize_panel.test.mjs`
Expected: PASS — all tests in the file.

- [ ] **Step 6: Commit**

```bash
git add frontend/js/dashboard_decomp_housing_scenarios.js tests/frontend/housing_optimize_panel.test.mjs
git commit -m "$(cat <<'EOF'
Housing optimizer: add concurrent move-2 UI

"Concurrent with move 1" lets the panel ask the optimizer to consider
keeping the move-1 home and adding a second, simultaneous residence
instead of always selling and relocating -- disabled (with an inline
note) under Narrowed search mode, which the backend doesn't support
for this yet. Move rendering now distinguishes a concurrent move 2
from a sequential one.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend housing test surface**

Run: `pytest tests/test_housing_optimizer_unit.py tests/test_housing_optimizer_integration.py tests/test_pricing_housing_service_extraction_functional.py tests/test_workbook_housing_wellness_cashflow_functional.py -v`
Expected: PASS, no failures, no unexpected skips.

- [ ] **Step 2: Run the full frontend housing test surface**

Run: `node --test tests/frontend/housing_optimize_panel.test.mjs tests/frontend/estimate_housing_from_state.test.mjs tests/frontend/housing_cost_reestimate.test.mjs tests/frontend/housing_price_field_focus_preservation.test.mjs`
Expected: PASS, no failures.

- [ ] **Step 3: Run the full project test suite to catch any cross-module regression**

Run: `pytest -q` and `node --test tests/frontend/`
Expected: PASS. If anything outside the housing surface fails, investigate before considering this plan done — likely candidates are `api_contracts.py`'s contract-consistency self-check (if one exists; grep `tests/` for `api_contracts` to find it) or a `HOUSING_SEED_ROWS` row-count assertion elsewhere in the suite.

- [ ] **Step 4: Manual smoke test in the browser**

Start the app's dev server (whatever this project's `run` skill/launch.json defines), open the housing optimization panel, and:
- Confirm both state fields are dropdowns.
- Fill in the five criteria for two candidate locations and confirm the payload includes them (check the network request body).
- Run an optimization with "Consider a second move" + "Concurrent with move 1" checked, confirm the recommendation renders with "concurrent with move 1" wording rather than "Sell → Buy".
- Toggle Search mode to Narrowed and confirm the concurrent checkbox disables itself with the inline note.
- Reproduce the original bug report's scenario (uncheck "Never own two homes at once", search a window where a bridge-purchase or immediate-flip candidate wins) and confirm the recommendation text now reads sensibly (buy/sell in chronological order, correct home labels).

No commit for this task — it's verification only.
