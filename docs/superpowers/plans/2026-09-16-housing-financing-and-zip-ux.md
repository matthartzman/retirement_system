# Housing Financing Display + ZIP-First UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the housing optimizer's results table show the dollar figure that actually matches a move's action (monthly rent for rent, purchase price + P&I for buy, using the same price the plan's own cost math uses), add a "Purchase assumptions" section for down payment/mortgage rate, and redesign the Spending -> Housing page's location entry to be ZIP-first with auto-filled Area Type/Population, matching the optimizer's layout.

**Architecture:** Backend changes are pure-function additions/corrections in `src/housing/plan_variant.py` (purchase price fallback tier, a new payment-math helper) threaded through `src/housing/results.py`'s existing formatting pipeline, plus one new read-only Flask endpoint reusing the existing ZCTA table. Frontend changes are additive markup/logic in the two existing housing panels (`dashboard_decomp_housing_optimizer.js`, `dashboard_decomp_housing_scenarios.js`), following each file's existing field-rendering and persistence conventions exactly — no new state-management pattern introduced.

**Tech Stack:** Python 3.14 / Flask backend (`src/housing/*`), vanilla JS ES modules loaded as classic scripts (`frontend/js/*`), pytest (backend), Node's built-in test runner (`node --test`, frontend).

## Global Constraints

- No loan-term input anywhere — every mortgage in this app assumes a fixed 30-year term (matches `deterministic_engine.py`'s existing `_mortgage_payment_and_balance` default and the spec's explicit non-goal).
- `down_payment_pct` / `mortgage_rate_pct` are fractions (0.20, 0.0685) on the wire and in every Python function signature; the UI fields collect and display whole percentages (20, 6.85) and divide/multiply by 100 at the JS/Python boundary only.
- A field with one genuine static default (Down payment %: 20) shows that default as a real, editable value in the field — never a placeholder. Mortgage rate % shows the flat fallback constant (6.85) as a real, editable value; clearing it entirely sends `null`, preserving today's per-location rate lookup as an explicit opt-out.
- Every new optimizer-panel field gets a full `HOUSING_OPT_FIELD_HELP` entry (title/meaning/connections/options/impact) — this repo's own functional test (`test_housing_optimizer_panel_functional.py`) asserts every `housing-opt-field` has a help hook.
- Client-side validation in `validateHousingOptForm()` mirrors server-side `validate_request()` rule-for-rule and in the same relative order, per that function's own docstring contract.
- No engine behavior may be duplicated in two places: `_purchase_step()` and the new results-display helper both resolve the effective mortgage rate through the same one function.

---

## File Map

| File | Change |
|---|---|
| `src/housing/models.py` | Update `Location.est_price` docstring (no longer display-only) |
| `src/housing/plan_variant.py` | New fallback tier in `_purchase_price_for_location`; new `_effective_mortgage_rate`, `estimate_monthly_pi_payment`; `_purchase_step` reuses `_effective_mortgage_rate` |
| `src/housing/results.py` | `format_output`/`_format_candidate`/`_format_move` gain `down_payment_pct`/`mortgage_rate_pct` params and a `financing` block per move |
| `src/housing/optimizer.py` | Pass `down_payment_pct`/`mortgage_rate_pct` into its `format_output(...)` call |
| `src/housing/api.py` | New `zip_lookup` function; `validate_request` gains a down-payment/mortgage-rate bounds rule |
| `src/housing/__init__.py` | Export `zip_lookup` |
| `src/server/plan_routes.py` | New `GET /api/housing/zip-lookup` route |
| `frontend/js/dashboard_decomp_housing_optimizer.js` | New Purchase Assumptions row + help entries; `buildHousingOptRequest`/`validateHousingOptForm` updates; `housingOptMoveCellHtml` rent/buy branching; Where-row field reorder |
| `frontend/js/dashboard_decomp_housing_scenarios.js` | ZIP-first location fields, new `resolveHousingStepZip`, layout switch to `.field-list.inline-row`, updated help copy |
| `tests/test_housing_optimizer_unit.py` | New pure-function tests for the three `plan_variant.py` additions |
| `tests/test_housing_results_v2_contract.py` | New tests for the `financing` block |
| `tests/test_housing_zip_lookup_contract.py` | New file: endpoint contract tests |
| `tests/frontend/housing_optimize_panel.test.mjs` | New tests for Purchase Assumptions fields + Where-row order |
| `tests/frontend/housing_optimize_request.test.mjs` | New tests for the new request keys, incl. cleared-field-sends-null |
| `tests/frontend/housing_step_zip_lookup.test.mjs` | New file: Housing page ZIP field behavior |

---

### Task 1: Purchase price uses the ZIP-scaled estimate before falling back to the state-level one

**Files:**
- Modify: `src/housing/plan_variant.py:60-64` (`_purchase_price_for_location`)
- Modify: `src/housing/models.py:71-82` (`Location` docstring comments on `est_price`/`zip_code`)
- Test: `tests/test_housing_optimizer_unit.py`

**Interfaces:**
- Consumes: `Location.est_price` (existing field, `models.py:82`)
- Produces: `_purchase_price_for_location(loc: Location) -> float` — unchanged signature, corrected fallback order, consumed by `_purchase_step` (`plan_variant.py:76-91`) and by Task 3's `_format_move`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_housing_optimizer_unit.py`, in the existing `# plan_variant: candidate -> engine config` section (after its current tests, before the `scoring` section comment):

```python
from src.housing.plan_variant import _purchase_price_for_location


def test_purchase_price_prefers_target_range_midpoint():
    loc = Location(state="Texas", target_purchase_price_range=(400000.0, 500000.0), est_price=999999.0)
    assert _purchase_price_for_location(loc) == 450000.0


def test_purchase_price_falls_back_to_the_zip_scaled_estimate():
    """No price range set: use the ZIP screen's own scaled estimate, not a
    flatter state-wide number."""
    loc = Location(state="Texas", est_price=612345.0)
    assert _purchase_price_for_location(loc) == 612345.0


def test_purchase_price_falls_back_to_state_estimate_when_no_est_price():
    """A hand-built Location with neither a price range nor an est_price
    (never happens for an optimizer-generated candidate, since
    _splice_screen_detail always sets est_price) still returns something
    sane rather than raising."""
    loc = Location(state="Texas", city_type="suburban", population_size=150000)
    price = _purchase_price_for_location(loc)
    assert price > 0
```

- [ ] **Step 2: Run tests to verify the second one fails**

Run: `python -m pytest tests/test_housing_optimizer_unit.py -k purchase_price -v`
Expected: `test_purchase_price_falls_back_to_the_zip_scaled_estimate` FAILS (currently returns the state estimate, not 612345.0); the other two PASS already.

- [ ] **Step 3: Fix `_purchase_price_for_location`**

In `src/housing/plan_variant.py`, replace:

```python
def _purchase_price_for_location(loc: Location) -> float:
    if loc.target_purchase_price_range:
        lo, hi = loc.target_purchase_price_range
        return (float(lo) + float(hi)) / 2.0
    return float(_estimate_for_location(loc, 'purchase')['purchase_price'])
```

with:

```python
def _purchase_price_for_location(loc: Location) -> float:
    """Price range midpoint, else the ZIP-scaled screening estimate
    (Location.est_price), else a flat state-level estimate. The middle tier
    makes a buy move's actual cost basis match the ZIP-specific number the
    results table shows -- see Location.est_price's docstring in models.py."""
    if loc.target_purchase_price_range:
        lo, hi = loc.target_purchase_price_range
        return (float(lo) + float(hi)) / 2.0
    if loc.est_price:
        return float(loc.est_price)
    return float(_estimate_for_location(loc, 'purchase')['purchase_price'])
```

- [ ] **Step 4: Update the stale `Location` docstring in `models.py`**

In `src/housing/models.py`, the comment above `est_price` currently reads:

```python
    # Populated by the ZIP screen (Task 10 splices them via
    # ``dataclasses.replace``). Display/traceability only, like ``zip_code``
    # above -- None for a Location that never came from a screen.
    zip_code: str | None = None
```

Split this into two accurate comments (`zip_code` is still display-only; `est_price` is not, as of this task):

```python
    # Display/traceability only when this Location came from a ZIP search.
    # Nothing downstream reads it -- see src/housing/zip_screen/resolve.py.
    zip_code: str | None = None
    # Populated by the ZIP screen (Task 10 splices them via
    # ``dataclasses.replace``); None for a Location that never came from a
    # screen. ``est_price`` is READ by ``plan_variant._purchase_price_for_location``
    # as the buy-move cost basis when no explicit price range is set -- it is
    # not purely cosmetic. The other four fields below remain
    # display/traceability only.
    city: str | None = None
    nss: float | None = None
    band: str | None = None
    distance_miles: float | None = None
    family_distance_miles: float | None = None
    est_price: float | None = None
```

(This only reorders/rewrites comments and is a no-op on the dataclass fields themselves — `zip_code`'s own line was already correct and stays; check the surrounding lines still read correctly after the edit.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_housing_optimizer_unit.py -k purchase_price -v`
Expected: all 3 PASS

- [ ] **Step 6: Run the full existing housing test suite to check for regressions**

Run: `python -m pytest tests/test_housing_optimizer_unit.py tests/test_housing_optimizer_integration.py tests/test_housing_results_v2_contract.py tests/test_housing_api_validation_contract.py -v`
Expected: all PASS. (Integration tests may show different net-worth/lifetime-cost numbers for buy candidates without a price range — that's the intended effect of this task; if any assert an exact prior value, note it in the commit message rather than silently "fixing" the assertion.)

- [ ] **Step 7: Commit**

```bash
git add src/housing/plan_variant.py src/housing/models.py tests/test_housing_optimizer_unit.py
git commit -m "fix(housing): buy-move cost basis prefers the ZIP-scaled price estimate"
```

---

### Task 2: Shared mortgage-rate resolution + monthly P&I helper

**Files:**
- Modify: `src/housing/plan_variant.py:67-91` (`_purchase_step`)
- Test: `tests/test_housing_optimizer_unit.py`

**Interfaces:**
- Consumes: `Location`, `_estimate_for_location` (existing), `_DEFAULT_MORTGAGE_RATE` (existing constant, `plan_variant.py:16`)
- Produces:
  - `_effective_mortgage_rate(loc: Location, mortgage_rate_pct: float | None) -> float`
  - `estimate_monthly_pi_payment(purchase_price: float, down_payment_pct: float, mortgage_rate_pct: float, term_years: int = 30) -> float`
  Both consumed by Task 3's `_format_move`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_housing_optimizer_unit.py`:

```python
from src.housing.plan_variant import (
    _DEFAULT_MORTGAGE_RATE,
    _effective_mortgage_rate,
    estimate_monthly_pi_payment,
)


def test_effective_mortgage_rate_prefers_the_explicit_value():
    assert _effective_mortgage_rate(TX, 0.05) == 0.05


def test_effective_mortgage_rate_falls_back_to_the_location_estimate():
    rate = _effective_mortgage_rate(TX, None)
    assert rate > 0


def test_monthly_pi_payment_matches_a_hand_computed_amortization():
    # $400,000 price, 20% down -> $320,000 principal, 6% annual rate, 30yr.
    # Standard level-payment formula: 320000 * 0.005 / (1 - 1.005**-360)
    payment = estimate_monthly_pi_payment(400000.0, 0.20, 0.06)
    assert round(payment, 2) == 1918.56


def test_monthly_pi_payment_is_zero_rate_safe():
    # 0% rate: straight-line principal / n_payments, no division by zero.
    payment = estimate_monthly_pi_payment(360000.0, 0.20, 0.0)
    assert round(payment, 2) == round(288000.0 / 360, 2)


def test_monthly_pi_payment_is_zero_when_fully_down():
    assert estimate_monthly_pi_payment(400000.0, 1.0, 0.06) == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_housing_optimizer_unit.py -k "effective_mortgage_rate or monthly_pi" -v`
Expected: FAIL with `ImportError: cannot import name '_effective_mortgage_rate'`

- [ ] **Step 3: Add both functions to `plan_variant.py`**

Insert immediately after `_purchase_price_for_location` (which Task 1 just edited) and before `_purchase_step`:

```python
def _effective_mortgage_rate(loc: Location, mortgage_rate_pct: float | None) -> float:
    """Same three-way fallback _purchase_step already applies: an explicit
    rate wins, else the location's own cost-estimate rate, else the flat
    default. Extracted so results.py's display-only payment estimate and
    the engine's actual cost basis can never disagree about which rate a
    given location uses."""
    if mortgage_rate_pct is not None:
        return float(mortgage_rate_pct)
    est = _estimate_for_location(loc, 'purchase')
    return float(est.get('mortgage_rate_pct', _DEFAULT_MORTGAGE_RATE) or _DEFAULT_MORTGAGE_RATE)


def estimate_monthly_pi_payment(
    purchase_price: float, down_payment_pct: float, mortgage_rate_pct: float,
    term_years: int = 30,
) -> float:
    """Level-payment fixed-rate monthly principal+interest.

    For DISPLAY only (results.py) -- deliberately mirrors
    deterministic_engine.py's own ``_mortgage_payment_and_balance`` formula
    (same principal/rate/term inputs, same standard amortization formula)
    without calling it, so a bug here cannot alter what a plan run actually
    charges. A fixed-rate, fully-amortizing mortgage's payment is constant
    for the life of the loan (only the principal/interest split changes
    year to year), so there is no year-index parameter -- this is the
    payment for any year before payoff.
    """
    principal = max(0.0, purchase_price * (1.0 - down_payment_pct))
    if principal <= 0.0:
        return 0.0
    monthly_rate = max(0.0, mortgage_rate_pct) / 12.0
    n = max(1, term_years) * 12
    if monthly_rate <= 1e-9:
        return principal / n
    return principal * monthly_rate / (1 - (1 + monthly_rate) ** (-n))
```

- [ ] **Step 4: Update `_purchase_step` to use `_effective_mortgage_rate`**

Replace, in `_purchase_step`:

```python
    est = _estimate_for_location(loc, 'purchase')
    est_rate = float(est.get('mortgage_rate_pct', _DEFAULT_MORTGAGE_RATE) or _DEFAULT_MORTGAGE_RATE)
    return {
        'id': step_id, 'type': 'purchase',
        'start_year': start_year, 'end_year': end_year or 0,
        'state': loc.state, 'city_type': loc.city_type, 'population_size': loc.population_size,
        'purchase_price': _purchase_price_for_location(loc),
        'down_payment_pct': float(DEFAULT_DOWN_PAYMENT_PCT if down_payment_pct is None else down_payment_pct),
        'mortgage_rate_pct': est_rate if mortgage_rate_pct is None else float(mortgage_rate_pct),
```

with:

```python
    est = _estimate_for_location(loc, 'purchase')
    return {
        'id': step_id, 'type': 'purchase',
        'start_year': start_year, 'end_year': end_year or 0,
        'state': loc.state, 'city_type': loc.city_type, 'population_size': loc.population_size,
        'purchase_price': _purchase_price_for_location(loc),
        'down_payment_pct': float(DEFAULT_DOWN_PAYMENT_PCT if down_payment_pct is None else down_payment_pct),
        'mortgage_rate_pct': _effective_mortgage_rate(loc, mortgage_rate_pct),
```

(the rest of the returned dict, `insurance_annual` onward, is unchanged — only the two lines above move)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_housing_optimizer_unit.py -k "effective_mortgage_rate or monthly_pi or purchase_price" -v`
Expected: all PASS

- [ ] **Step 6: Run the full existing housing test suite**

Run: `python -m pytest tests/test_housing_optimizer_unit.py tests/test_housing_optimizer_integration.py -v`
Expected: all PASS (this step is a pure refactor of `_purchase_step`'s rate line — behavior is unchanged, only the fallback logic's *location* moved)

- [ ] **Step 7: Commit**

```bash
git add src/housing/plan_variant.py tests/test_housing_optimizer_unit.py
git commit -m "refactor(housing): extract mortgage-rate fallback, add monthly P&I helper"
```

---

### Task 3: Results payload gains a `financing` block per move

**Files:**
- Modify: `src/housing/results.py` (`_format_move`, `_format_candidate`, `format_output`)
- Modify: `src/housing/optimizer.py:273-277` (the `format_output(...)` call)
- Test: `tests/test_housing_results_v2_contract.py`

**Interfaces:**
- Consumes: `_purchase_price_for_location`, `_effective_mortgage_rate`, `estimate_monthly_pi_payment` (Tasks 1-2), `_estimate_for_location` — all from `src.housing.plan_variant`
- Produces: `format_output(ranked, *, objective, search_mode, move2_strategy, zip_screens, rejections, message=None, down_payment_pct=0.20, mortgage_rate_pct=None)` — two new **optional, keyword-only-by-convention** params with defaults matching `api.py`'s own request defaults, so every existing caller/test keeps working unchanged. Each move dict in the payload gains a `'financing'` key: `{'monthly_rent': float}` for a rent move, `{'purchase_price': float, 'monthly_pi_payment': float}` for a buy move.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_housing_results_v2_contract.py`:

```python
def test_a_rent_move_reports_monthly_rent_and_no_purchase_price():
    move = _out([_scored(two_move=True)])['candidates'][0]['moves'][1]
    assert move['action'] == 'rent'
    assert 'monthly_rent' in move['financing']
    assert move['financing']['monthly_rent'] > 0
    assert 'purchase_price' not in move['financing']
    assert 'monthly_pi_payment' not in move['financing']


def test_a_buy_move_reports_purchase_price_and_monthly_pi():
    move = _out([_scored()])['candidates'][0]['moves'][0]
    assert move['action'] == 'buy'
    assert move['financing']['purchase_price'] > 0
    assert move['financing']['monthly_pi_payment'] > 0
    assert 'monthly_rent' not in move['financing']


def test_purchase_price_matches_the_plan_variant_helper_directly():
    """The results payload's purchase_price must be the SAME number the
    engine's own cost basis uses -- not a separately-computed estimate."""
    from src.housing.plan_variant import _purchase_price_for_location
    sc = _scored()
    loc = sc.candidate.moves[0].location
    expected = _purchase_price_for_location(loc)
    move = _out([sc])['candidates'][0]['moves'][0]
    assert move['financing']['purchase_price'] == expected


def test_down_payment_and_mortgage_rate_change_the_monthly_pi():
    sc = _scored()
    low_down = _out([sc], down_payment_pct=0.05, mortgage_rate_pct=0.04)
    high_down = _out([sc], down_payment_pct=0.50, mortgage_rate_pct=0.04)
    pi_low = low_down['candidates'][0]['moves'][0]['financing']['monthly_pi_payment']
    pi_high = high_down['candidates'][0]['moves'][0]['financing']['monthly_pi_payment']
    assert pi_low > pi_high


def test_format_output_defaults_match_the_api_defaults_when_omitted():
    """Every existing call to format_output() (including every other test in
    this file) omits these two params -- they must still produce a sane
    financing block, matching api.py's own 20%/location-rate defaults."""
    move = _out([_scored()])['candidates'][0]['moves'][0]
    assert move['financing']['purchase_price'] > 0
    assert move['financing']['monthly_pi_payment'] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_housing_results_v2_contract.py -k financing -v`
Expected: FAIL with `KeyError: 'financing'`

- [ ] **Step 3: Implement the `financing` block in `results.py`**

In `src/housing/results.py`, add the import and update the three functions:

```python
from .plan_variant import (
    _effective_mortgage_rate,
    _estimate_for_location,
    _purchase_price_for_location,
    estimate_monthly_pi_payment,
)
```

Replace `_format_move`:

```python
def _format_move(
    move: Move, sec121_lost: bool, *,
    down_payment_pct: float, mortgage_rate_pct: float | None,
) -> dict[str, Any]:
    if move.action == 'rent':
        financing = {
            'monthly_rent': float(_estimate_for_location(move.location, 'rent')['monthly_rent']),
        }
    else:
        price = _purchase_price_for_location(move.location)
        rate = _effective_mortgage_rate(move.location, mortgage_rate_pct)
        financing = {
            'purchase_price': price,
            'monthly_pi_payment': estimate_monthly_pi_payment(price, down_payment_pct, rate),
        }
    return {
        'index': move.index,
        'acquisition_year': move.acquisition_year,
        'action': move.action,
        'mode': move.mode,
        'location': _format_location(move.location),
        'sec121_exclusion_lost': sec121_lost,
        'financing': financing,
    }
```

Replace `_format_candidate`:

```python
def _format_candidate(
    sc: ScoredCandidate, objective: str, rank: int, *,
    down_payment_pct: float, mortgage_rate_pct: float | None,
) -> dict[str, Any]:
    cand = sc.candidate
    lost = list(sc.sec121_exclusion_lost)
    return {
        'rank': rank,
        'original_home': {
            'disposition': cand.original_home.disposition,
            'sale_year': cand.original_home.sale_year,
        },
        'moves': [
            _format_move(
                m, lost[i] if i < len(lost) else False,
                down_payment_pct=down_payment_pct, mortgage_rate_pct=mortgage_rate_pct,
            )
            for i, m in enumerate(cand.moves)
        ],
        'net_worth': sc.net_worth,
        'lifetime_cost': sc.lifetime_cost,
        'mc_success_rate': sc.mc_success_rate,
        'objective_value': {
            'net_worth': sc.net_worth,
            'lifetime_cost': sc.lifetime_cost,
            'mc_success_rate': sc.mc_success_rate,
        }[objective],
        'notes': list(sc.notes),
    }
```

Replace `format_output`'s signature and the `formatted` line:

```python
def format_output(
    ranked: list[ScoredCandidate], *, objective: str, search_mode: str,
    move2_strategy: str, zip_screens: dict[str, Any],
    rejections: dict[str, int], message: str | None = None,
    down_payment_pct: float = 0.20, mortgage_rate_pct: float | None = None,
) -> dict[str, Any]:
    """One ranked ``candidates`` list, not a recommendation plus a disjoint
    alternatives list -- v1 duplicated the rank-1 candidate across both and
    forced the frontend to render it two different ways. ``recommendation``
    remains as an alias of ``candidates[0]``. ``candidates`` is capped at
    ``MAX_CANDIDATES``, but ``candidates_evaluated`` reports the full count.

    ``down_payment_pct``/``mortgage_rate_pct`` default to the same values
    api.py itself defaults to (20%, location-based rate) so every existing
    caller that omits them keeps working unchanged.
    """
    formatted = [
        _format_candidate(
            sc, objective, i + 1,
            down_payment_pct=down_payment_pct, mortgage_rate_pct=mortgage_rate_pct,
        )
        for i, sc in enumerate(ranked[:MAX_CANDIDATES])
    ]
```

(the rest of `format_output`'s body, building `payload` and returning it, is unchanged)

- [ ] **Step 4: Thread the two params through `optimizer.py`**

In `src/housing/optimizer.py`, the `format_output(...)` call (around line 273):

```python
    return format_output(
        final_ranked, objective=objective, search_mode=search_mode,
        move2_strategy=move2_strategy, zip_screens=zip_screens,
        rejections=rejections,
    )
```

becomes:

```python
    return format_output(
        final_ranked, objective=objective, search_mode=search_mode,
        move2_strategy=move2_strategy, zip_screens=zip_screens,
        rejections=rejections,
        down_payment_pct=down_payment_pct, mortgage_rate_pct=mortgage_rate_pct,
    )
```

(`down_payment_pct`/`mortgage_rate_pct` are already `optimize_housing`'s own parameters, already in scope at this call site — see `optimizer.py:95-96`)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_housing_results_v2_contract.py -v`
Expected: all PASS, including every pre-existing test in the file (they call `_out()` without the two new kwargs, which now default correctly)

- [ ] **Step 6: Run the full housing suite**

Run: `python -m pytest tests/test_housing_optimizer_unit.py tests/test_housing_optimizer_integration.py tests/test_housing_results_v2_contract.py tests/test_housing_api_validation_contract.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add src/housing/results.py src/housing/optimizer.py tests/test_housing_results_v2_contract.py
git commit -m "feat(housing): results payload reports rent/buy-specific financing per move"
```

---

### Task 4: New `/api/housing/zip-lookup` endpoint

**Files:**
- Modify: `src/housing/api.py` (new `zip_lookup` function)
- Modify: `src/housing/__init__.py:155-158` (export)
- Modify: `src/server/plan_routes.py` (new route, after `housing_top_cities`)
- Test: `tests/test_housing_zip_lookup_contract.py` (new file)

**Interfaces:**
- Consumes: `zip_screen.table.load_table`, `zip_screen.resolve.city_type_for_density` (both already imported in `api.py`)
- Produces: `zip_lookup(zip_code: str, table_path: str | None = None) -> tuple[dict, int]`, exported as `src.housing.zip_lookup`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_housing_zip_lookup_contract.py`:

```python
"""GET /api/housing/zip-lookup contract: ZIP -> city/state/area_type/population,
for the Spending -> Housing page's ZIP-first location entry (design
2026-09-16-housing-financing-and-zip-ux)."""
import pytest

from src.housing.api import zip_lookup

pytestmark = pytest.mark.contract


def test_a_recognized_zip_resolves():
    payload, status = zip_lookup('60521')
    assert status == 200
    assert payload['success'] is True
    assert payload['state']
    assert payload['city']
    assert payload['area_type'] in ('urban', 'suburban', 'exurban', 'rural')
    assert payload['population'] >= 0


def test_an_unrecognized_zip_is_a_404():
    payload, status = zip_lookup('00000')
    assert status == 404
    assert payload['success'] is False
    assert 'not recognized' in payload['error'].lower()


def test_a_malformed_zip_is_a_400():
    for bad in ('123', 'abcde', '', '123456'):
        payload, status = zip_lookup(bad)
        assert status == 400, f'{bad!r} should be rejected'
        assert payload['success'] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_housing_zip_lookup_contract.py -v`
Expected: FAIL with `ImportError: cannot import name 'zip_lookup'`

- [ ] **Step 3: Implement `zip_lookup` in `api.py`**

Add near `top_cities_payload` in `src/housing/api.py` (after its closing, before the `def screen_payload` block is fine, or anywhere below the existing `load_table`/`city_type_for_density` imports at the top of the file):

```python
def zip_lookup(zip_code: str, table_path: str | None = None) -> tuple[dict[str, Any], int]:
    """ZIP -> city/state/area_type/population, for the Spending -> Housing
    page's ZIP-first location entry. Reuses the same ZCTA table the
    optimizer's ZIP screen uses, so a manually-entered ZIP resolves to the
    same city_type/population the optimizer would have derived for it.
    """
    zip_code = str(zip_code or '').strip()
    if len(zip_code) != 5 or not zip_code.isdigit():
        return {'success': False, 'error': 'ZIP must be 5 digits.'}, 400
    table = load_table(table_path) if table_path else load_table()
    rec = table.get(zip_code)
    if not rec:
        return {'success': False, 'error': f'ZIP {zip_code} not recognized.'}, 404
    return {
        'success': True,
        'city': rec.primary_place,
        'state': rec.state,
        'area_type': city_type_for_density(rec.density),
        'population': rec.place_population or rec.zcta_population or 0,
    }, 200
```

Confirm `city_type_for_density` is already imported at the top of `api.py` (it is — `from .zip_screen.resolve import resolve_location`; add `city_type_for_density` to that same import line: `from .zip_screen.resolve import city_type_for_density, resolve_location`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_housing_zip_lookup_contract.py -v`
Expected: all PASS

- [ ] **Step 5: Export it from the package**

In `src/housing/__init__.py`, add one line to the `_EXPORTS` dict (alphabetical-ish position next to the other `api`-sourced entries):

```python
    'optimize_housing_from_request': 'api',
    'top_cities_payload': 'api',
    'zip_lookup': 'api',
    'zip_screen_from_request': 'api',
```

- [ ] **Step 6: Add the Flask route**

In `src/server/plan_routes.py`, after the existing `housing_top_cities` route (around line 778):

```python
@app.route("/api/housing/zip-lookup", methods=["GET"])
def housing_zip_lookup():
    denied = _require("read_config")
    if denied:
        return denied
    from ..housing import zip_lookup
    return _service_json(zip_lookup(request.args.get("zip", "")))
```

- [ ] **Step 7: Verify the route wiring with a quick manual check**

Run: `python -m pytest tests/test_housing_zip_lookup_contract.py -v` (confirms the pure function still passes)

Then start the dev server and hit it directly to confirm the Flask layer wires through correctly:

```bash
python main.py --mode server &
sleep 3
curl "http://localhost:5050/api/housing/zip-lookup?zip=60521"
curl "http://localhost:5050/api/housing/zip-lookup?zip=00000"
kill %1
```

Expected: first call returns `{"success": true, "city": ..., "state": ..., "area_type": ..., "population": ...}`; second returns `{"success": false, "error": "ZIP 00000 not recognized."}` with a 404 status (check with `curl -i` if the body alone doesn't make the status clear).

- [ ] **Step 8: Commit**

```bash
git add src/housing/api.py src/housing/__init__.py src/server/plan_routes.py tests/test_housing_zip_lookup_contract.py
git commit -m "feat(housing): add GET /api/housing/zip-lookup endpoint"
```

---

### Task 5: Server-side bounds validation for down payment % / mortgage rate %

**Files:**
- Modify: `src/housing/api.py:138-149` (`validate_request`, after the `family_presence` block)
- Test: `tests/test_housing_api_validation_contract.py`

**Interfaces:**
- Consumes: `body.get('down_payment_pct')`, `body.get('mortgage_rate_pct')` — both fractions (0-1) if present, `None` if absent
- Produces: no new function; `validate_request` gains one more checked rule before its final `return None`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_housing_api_validation_contract.py`:

```python
def test_rule10_down_payment_pct_must_be_a_fraction_between_0_and_1():
    msg = validate_request(_body(down_payment_pct=1.5))
    assert msg is not None
    assert 'down payment' in msg.lower()


def test_rule10_mortgage_rate_pct_must_be_a_fraction_between_0_and_1():
    msg = validate_request(_body(mortgage_rate_pct=-0.01))
    assert msg is not None
    assert 'mortgage rate' in msg.lower()


def test_rule10_omitted_financing_fields_are_fine():
    assert validate_request(_body()) is None
```

- [ ] **Step 2: Run tests to verify the first two fail**

Run: `python -m pytest tests/test_housing_api_validation_contract.py -k rule10 -v`
Expected: the first two FAIL (currently `validate_request` accepts any value); the third already PASSES

- [ ] **Step 3: Add the rule**

In `src/housing/api.py`'s `validate_request`, insert right before the final `return None` (after the `family_presence` block, `fp = body.get('family_presence') ...`):

```python
    dp_raw = body.get('down_payment_pct')
    if dp_raw is not None and not (0.0 <= float(dp_raw) <= 1.0):
        return 'Down payment % must be between 0 and 100.'
    mr_raw = body.get('mortgage_rate_pct')
    if mr_raw is not None and not (0.0 <= float(mr_raw) <= 1.0):
        return 'Mortgage rate % must be between 0 and 100.'
    return None
```

(replacing the bare `return None` that currently ends the function)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_housing_api_validation_contract.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/housing/api.py tests/test_housing_api_validation_contract.py
git commit -m "feat(housing): validate down payment %/mortgage rate % bounds server-side"
```

---

### Task 6: Optimizer panel — "Purchase assumptions" section

**Files:**
- Modify: `frontend/js/dashboard_decomp_housing_optimizer.js`:
  - `HOUSING_OPT_FIELD_HELP` block (after line ~358, alongside `housingOptDisposition`)
  - `renderHousingOptimizePanelHtml` (lines 1199-1266): new row between `currentHomeRow` and the Move-1 rows
  - `buildHousingOptRequest` (lines 1614-1664): two new top-level keys
  - `validateHousingOptForm` (lines 1670-1775): one new bounds rule, mirroring Task 5
- Test: `tests/frontend/housing_optimize_panel.test.mjs`, `tests/frontend/housing_optimize_request.test.mjs`

**Interfaces:**
- Consumes: `housingOptRow`, `housingOptField` (existing, `plan_variant.js:463-469` — same file)
- Produces: two new DOM ids, `housingOptDownPaymentPct` and `housingOptMortgageRatePct`; `buildHousingOptRequest()`'s returned body gains `down_payment_pct: number` (fraction) and `mortgage_rate_pct: number | null` (fraction or null)

- [ ] **Step 1: Write the failing panel-markup tests**

Add to `tests/frontend/housing_optimize_panel.test.mjs`, in the top-level `describe("renderHousingOptimizePanelHtml", ...)` block:

```javascript
  test("a Purchase assumptions section sits between Current home and Move 1", () => {
    const html = panelHtml();
    assert.match(html, /id="housingOptDownPaymentPct"/);
    assert.match(html, /id="housingOptMortgageRatePct"/);
    const currentHomeIdx = html.indexOf("housingOptDisposition");
    const purchaseAssumptionsIdx = html.indexOf("housingOptDownPaymentPct");
    const move1Idx = html.indexOf("housingOptMove1Earliest");
    assert.ok(currentHomeIdx < purchaseAssumptionsIdx, "assumptions come after Current home");
    assert.ok(purchaseAssumptionsIdx < move1Idx, "assumptions come before Move 1");
  });

  test("down payment and mortgage rate show real editable defaults, not placeholders", () => {
    const html = panelHtml();
    assert.match(html, /id="housingOptDownPaymentPct"[^>]*value="20"/);
    assert.match(html, /id="housingOptMortgageRatePct"[^>]*value="6\.85"/);
  });
```

Add a new test in the `describe("anchors control (§9.3)", ...)` block (or a new adjacent `describe`) for the Where-row reorder:

```javascript
describe("Move N -- where row field order", () => {
  test("Area type renders immediately after the anchors block", () => {
    const html = panelHtml();
    const anchorsIdx = html.indexOf('id="housingOptMove1Anchors"');
    const areaTypeIdx = html.indexOf('id="housingOptMove1AreaType"');
    const radiusIdx = html.indexOf('id="housingOptMove1Radius"');
    assert.ok(anchorsIdx < areaTypeIdx, "area type comes after anchors");
    assert.ok(areaTypeIdx < radiusIdx, "area type comes before radius");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/frontend/housing_optimize_panel.test.mjs`
Expected: FAIL — none of the new ids/order exist yet

- [ ] **Step 3: Add the two help entries**

In `dashboard_decomp_housing_optimizer.js`, inside the `Object.assign(HOUSING_OPT_FIELD_HELP, { ... })` block (the one starting around line 273, right after `housingOptDisposition`'s entry), add:

```javascript
  housingOptDownPaymentPct: {
    title: "Down payment %",
    meaning: "The share of the purchase price paid up front, as a percentage. Applies to every move that ends up buying in this search.",
    connections:
      "Feeds the buy-move cost basis the same way api.py's own default (20%) does when this field is left at its default -- the principal financed is purchase price x (1 - down payment %).",
    options: "Raise it to shrink the financed principal and the monthly P&I payment shown in the results table; lower it to keep more cash available for other goals.",
    impact: "A higher down payment lowers the monthly P&I payment and total interest paid, at the cost of more cash committed up front -- it does not change the purchase price itself.",
  },
  housingOptMortgageRatePct: {
    title: "Mortgage rate %",
    meaning: "The fixed annual mortgage interest rate used for every move that ends up buying. Pre-filled with the app's own flat default rate.",
    connections:
      "Feeds the same monthly P&I calculation as Down payment %, using a fixed 30-year term (there is no loan-term input anywhere in this app). Clearing this field entirely reverts to each candidate ZIP's own location-based rate instead of one flat rate for every candidate.",
    options: "Leave the pre-filled default if unsure; set a specific rate for a rate lock already in hand; clear the field to let each location use its own typical rate instead.",
    impact: "A higher rate raises the monthly P&I payment shown in results without changing the purchase price; clearing the field can make different candidates use different rates, which changes their relative ranking on lifetime cost.",
  },
```

- [ ] **Step 4: Add the Purchase assumptions row and insert it into the panel**

In `renderHousingOptimizePanelHtml`, add a new row definition right after `currentHomeRow` (after its closing `);` around line 1228) and before `const move2Row = ...`:

```javascript
  const purchaseAssumptionsRow = housingOptRow(
    "Purchase assumptions",
    housingOptField(
      "housingOptDownPaymentPct",
      "Down payment %",
      `<input type="number" id="housingOptDownPaymentPct" class="count" value="20" min="0" max="100" oninput="debouncedRefreshHousingOptValidation()">`,
      "Share of the purchase price paid up front. Applies to every move that ends up buying.",
    ) +
      housingOptField(
        "housingOptMortgageRatePct",
        "Mortgage rate %",
        `<input type="number" id="housingOptMortgageRatePct" class="count" value="6.85" min="0" max="100" step="0.01" oninput="debouncedRefreshHousingOptValidation()">`,
        "Fixed annual rate for every buy move. Clear this field to use each candidate's own location-based rate instead.",
      ),
  );
```

Then update the panel's template literal (around line 1255-1266) to insert it:

```javascript
    ${currentHomeRow}
    ${purchaseAssumptionsRow}
    ${housingOptMoveWhereRowHtml(1)}
```

(replacing the current `${currentHomeRow}` immediately followed by `${housingOptMoveWhereRowHtml(1)}`)

- [ ] **Step 5: Reorder the Where row's fields**

In `housingOptMoveWhereRowHtml` (lines 978-1019), move the `AreaType` field block to render right after `Anchors` and before `Radius`. Change:

```javascript
function housingOptMoveWhereRowHtml(n) {
  const p = `housingOptMove${n}`;
  return housingOptRow(
    `Move ${n} — where`,
    housingOptField(
      `${p}Anchors`,
      "Anchors (2-5)",
      renderHousingOptAnchorsHtml(n),
      "The search screens ZIPs around each anchor and unions the results before dedup.",
    ) +
      housingOptField(
        `${p}Radius`,
        "Within",
        housingOptSelect(`${p}Radius`, HOUSING_OPT_MOVE_RADII, 'onchange="debouncedRefreshHousingOptValidation()"'),
        "How far from each anchor a candidate ZIP may be.",
      ) +
      housingOptField(
        `${p}MinScore`,
        "Min score",
        `<input type="number" id="${p}MinScore" class="count" value="60" min="0" max="100">`,
        "Neighborhood stability score floor. Measures housing and economic stability, not crime or safety.",
      ) +
      housingOptField(
        `${p}AreaType`,
        "Area type",
        housingOptSelect(`${p}AreaType`, HOUSING_OPT_AREA_TYPES, 'onchange="debouncedRefreshHousingOptValidation()"'),
        "Compared against the ZIP's density-derived area type. Any skips the filter.",
      ) +
      housingOptField(
        `${p}MaxPopulation`,
```

to:

```javascript
function housingOptMoveWhereRowHtml(n) {
  const p = `housingOptMove${n}`;
  return housingOptRow(
    `Move ${n} — where`,
    housingOptField(
      `${p}Anchors`,
      "Anchors (2-5)",
      renderHousingOptAnchorsHtml(n),
      "The search screens ZIPs around each anchor and unions the results before dedup.",
    ) +
      housingOptField(
        `${p}AreaType`,
        "Area type",
        housingOptSelect(`${p}AreaType`, HOUSING_OPT_AREA_TYPES, 'onchange="debouncedRefreshHousingOptValidation()"'),
        "Compared against the ZIP's density-derived area type. Any skips the filter.",
      ) +
      housingOptField(
        `${p}Radius`,
        "Within",
        housingOptSelect(`${p}Radius`, HOUSING_OPT_MOVE_RADII, 'onchange="debouncedRefreshHousingOptValidation()"'),
        "How far from each anchor a candidate ZIP may be.",
      ) +
      housingOptField(
        `${p}MinScore`,
        "Min score",
        `<input type="number" id="${p}MinScore" class="count" value="60" min="0" max="100">`,
        "Neighborhood stability score floor. Measures housing and economic stability, not crime or safety.",
      ) +
      housingOptField(
        `${p}MaxPopulation`,
```

(the rest of the function — `MaxPopulation` through `ShortlistSize` and the closing `);`/`}` — is unchanged)

- [ ] **Step 6: Run the panel tests to verify they pass**

Run: `node --test tests/frontend/housing_optimize_panel.test.mjs`
Expected: all PASS, including the pre-existing "labels are stacked above their control" and "every field carries a help affordance" tests (the new fields follow the same `housingOptField` pattern, so both keep passing automatically)

- [ ] **Step 7: Write the failing request-building tests**

Add to `tests/frontend/housing_optimize_request.test.mjs`'s `defaultElements()`, alongside the other top-level fields (e.g. right after `housingOptNoDualOwnership`):

```javascript
    housingOptDownPaymentPct: { value: "20" },
    housingOptMortgageRatePct: { value: "6.85" },
```

Then add new tests in the `describe("buildHousingOptRequest", ...)` block:

```javascript
  test("down payment % is sent as a fraction", () => {
    const { sandbox } = mountHousingOptPanel({ housingOptDownPaymentPct: { value: "15" } });
    assert.equal(sandbox.buildHousingOptRequest().down_payment_pct, 0.15);
  });

  test("an empty down payment field defaults to 20%", () => {
    const { sandbox } = mountHousingOptPanel({ housingOptDownPaymentPct: { value: "" } });
    assert.equal(sandbox.buildHousingOptRequest().down_payment_pct, 0.20);
  });

  test("mortgage rate % is sent as a fraction", () => {
    const { sandbox } = mountHousingOptPanel({ housingOptMortgageRatePct: { value: "5" } });
    assert.equal(sandbox.buildHousingOptRequest().mortgage_rate_pct, 0.05);
  });

  test("clearing the mortgage rate field sends null, not zero", () => {
    const { sandbox } = mountHousingOptPanel({ housingOptMortgageRatePct: { value: "" } });
    assert.equal(sandbox.buildHousingOptRequest().mortgage_rate_pct, null);
  });
```

- [ ] **Step 8: Run tests to verify they fail**

Run: `node --test tests/frontend/housing_optimize_request.test.mjs`
Expected: FAIL — `down_payment_pct`/`mortgage_rate_pct` are `undefined` on the request body

- [ ] **Step 9: Wire the two fields into `buildHousingOptRequest`**

In `buildHousingOptRequest` (around line 1634-1641), change:

```javascript
  const body = {
    objective,
    search_mode,
    move2_strategy,
    no_dual_ownership,
    original_home,
    move1,
  };
```

to:

```javascript
  const downPaymentRaw = housingOptDomVal("housingOptDownPaymentPct");
  const down_payment_pct = (downPaymentRaw === "" ? 20 : Number(downPaymentRaw)) / 100;
  const mortgageRaw = housingOptDomVal("housingOptMortgageRatePct");
  const mortgage_rate_pct = mortgageRaw === "" ? null : Number(mortgageRaw) / 100;

  const body = {
    objective,
    search_mode,
    move2_strategy,
    no_dual_ownership,
    original_home,
    move1,
    down_payment_pct,
    mortgage_rate_pct,
  };
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `node --test tests/frontend/housing_optimize_request.test.mjs`
Expected: all PASS

- [ ] **Step 11: Add and wire the client-side validation rule (mirrors Task 5)**

Add a test first, in the same file's validation-focused tests (search for an existing `describe("validateHousingOptForm"` block, or add one if the file groups validation tests separately — if none exists, add near the bottom of the file):

```javascript
describe("validateHousingOptForm -- purchase assumptions bounds", () => {
  test("down payment over 100 is rejected", () => {
    const { sandbox } = mountHousingOptPanel({ housingOptDownPaymentPct: { value: "150" } });
    assert.match(sandbox.validateHousingOptForm(), /down payment/i);
  });

  test("a negative mortgage rate is rejected", () => {
    const { sandbox } = mountHousingOptPanel({ housingOptMortgageRatePct: { value: "-1" } });
    assert.match(sandbox.validateHousingOptForm(), /mortgage rate/i);
  });

  test("the pre-filled defaults are valid", () => {
    const { sandbox } = mountHousingOptPanel();
    assert.equal(sandbox.validateHousingOptForm(), null);
  });
});
```

Run: `node --test tests/frontend/housing_optimize_request.test.mjs` — expect the first two to FAIL.

Then add the rule to `validateHousingOptForm` (in `dashboard_decomp_housing_optimizer.js`), right before its final `return null;`:

```javascript
  const downPaymentRaw = housingOptDomVal("housingOptDownPaymentPct");
  if (downPaymentRaw !== "" && !(Number(downPaymentRaw) >= 0 && Number(downPaymentRaw) <= 100)) {
    return "Down payment % must be between 0 and 100.";
  }
  const mortgageRaw = housingOptDomVal("housingOptMortgageRatePct");
  if (mortgageRaw !== "" && !(Number(mortgageRaw) >= 0 && Number(mortgageRaw) <= 100)) {
    return "Mortgage rate % must be between 0 and 100.";
  }

  return null;
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `node --test tests/frontend/housing_optimize_request.test.mjs`
Expected: all PASS

- [ ] **Step 13: Run the full frontend suite**

Run: `node --test tests/frontend/*.test.mjs`
Expected: all PASS (349+ tests, no regressions)

- [ ] **Step 14: Commit**

```bash
git add frontend/js/dashboard_decomp_housing_optimizer.js tests/frontend/housing_optimize_panel.test.mjs tests/frontend/housing_optimize_request.test.mjs
git commit -m "feat(housing-optimizer): add Purchase assumptions section, reorder Where row"
```

---

### Task 7: Results table shows rent-only or buy-only figures

**Files:**
- Modify: `frontend/js/dashboard_decomp_housing_optimizer.js:1477-1489` (`housingOptMoveCellHtml`)
- Test: `tests/frontend/housing_optimize_panel.test.mjs` (or a small new focused test — see Step 1)

**Interfaces:**
- Consumes: `move.financing` (new field from Task 3's backend payload: `{monthly_rent}` or `{purchase_price, monthly_pi_payment}`)
- Produces: `housingOptMoveCellHtml(move)` — same signature, different rendered text depending on `move.action`

- [ ] **Step 1: Write the failing tests**

Since `housingOptMoveCellHtml` is a pure function of a plain object (no DOM), test it directly. Add to `tests/frontend/housing_optimize_panel.test.mjs`:

```javascript
describe("housingOptMoveCellHtml", () => {
  function moveFixture(overrides = {}) {
    return {
      acquisition_year: 2033,
      action: "buy",
      location: { zip_code: "80014", city: "Aurora", state: "Colorado", distance_miles: 3.2 },
      financing: { purchase_price: 450000, monthly_pi_payment: 1918.56 },
      ...overrides,
    };
  }

  test("a rent move shows monthly rent and no price", () => {
    const html = panelHtml() && sandbox.housingOptMoveCellHtml(moveFixture({
      action: "rent",
      financing: { monthly_rent: 1850 },
    }));
    assert.match(html, /\$1,850\/mo rent/);
    assert.ok(!/purchase/i.test(html));
    assert.ok(!/P&I/i.test(html));
  });

  test("a buy move shows purchase price and monthly P&I", () => {
    const html = sandbox.housingOptMoveCellHtml(moveFixture());
    assert.match(html, /\$450,000 purchase/);
    assert.match(html, /\$1,919\/mo P&I/);
    assert.ok(!/rent/i.test(html));
  });
});
```

(`sandbox` here refers to the module-level `sandbox` from `loadDashboardSandbox()` already declared at the top of this test file — reuse it rather than creating a new one, since `housingOptMoveCellHtml` takes no DOM-backed arguments)

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/frontend/housing_optimize_panel.test.mjs`
Expected: FAIL — current output still uses `loc.est_price`, format differs

- [ ] **Step 3: Rewrite `housingOptMoveCellHtml`**

Replace the current function (lines 1473-1489):

```javascript
function housingOptMoveCellHtml(move) {
  if (!move) return "—";
  const loc = move.location || {};
  const price = loc.est_price != null ? `$${Math.round(loc.est_price).toLocaleString()}` : "—";
  const distance = loc.distance_miles != null ? `${Number(loc.distance_miles).toFixed(1)} mi` : "—";
  let text =
    `${move.acquisition_year} · ${housingOptActionLabel(move.action)} · ` +
    `${loc.zip_code || ""} ${loc.city || ""}, ${loc.state || ""} · ${price} · ${distance}`;
  if (loc.family_distance_miles != null) {
    text += ` · ${loc.family_distance_miles} mi from family`;
  }
  return esc(text);
}
```

with:

```javascript
function housingOptMoveCellHtml(move) {
  if (!move) return "—";
  const loc = move.location || {};
  const financing = move.financing || {};
  const distance = loc.distance_miles != null ? `${Number(loc.distance_miles).toFixed(1)} mi` : "—";
  let money;
  if (move.action === "rent") {
    money =
      financing.monthly_rent != null
        ? `$${Math.round(financing.monthly_rent).toLocaleString()}/mo rent`
        : "—";
  } else {
    const price =
      financing.purchase_price != null
        ? `$${Math.round(financing.purchase_price).toLocaleString()} purchase`
        : "—";
    const pi =
      financing.monthly_pi_payment != null
        ? `$${Math.round(financing.monthly_pi_payment).toLocaleString()}/mo P&I`
        : "—";
    money = `${price} · ${pi}`;
  }
  let text =
    `${move.acquisition_year} · ${housingOptActionLabel(move.action)} · ` +
    `${loc.zip_code || ""} ${loc.city || ""}, ${loc.state || ""} · ${distance} · ${money}`;
  if (loc.family_distance_miles != null) {
    text += ` · ${loc.family_distance_miles} mi from family`;
  }
  return esc(text);
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test tests/frontend/housing_optimize_panel.test.mjs`
Expected: all PASS

- [ ] **Step 5: Run the full frontend suite**

Run: `node --test tests/frontend/*.test.mjs`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/js/dashboard_decomp_housing_optimizer.js tests/frontend/housing_optimize_panel.test.mjs
git commit -m "feat(housing-optimizer): results table shows rent-only or buy+P&I figures"
```

---

### Task 8: Spending -> Housing page — ZIP-first location entry

**Files:**
- Modify: `frontend/js/dashboard_decomp_housing_scenarios.js`:
  - `PURCHASE_FIRST`/`RENT_FIRST` field-order arrays (lines 510, 529)
  - `renderNextHousingStepSection`'s `firstRows.map(...)` special-case branch (lines 617-624)
  - New function `resolveHousingStepZip(stepNum, rawZip)`
  - New module-level cache `window.housingStepZipLookup`
- Test: `tests/frontend/housing_step_zip_lookup.test.mjs` (new file)

**Interfaces:**
- Consumes: `GET /api/housing/zip-lookup?zip=...` (Task 4), existing bare globals `rows`, `dirty`, `editValue`, `valOf`, `renderMain`, `api`, `esc`, `norm` (already used elsewhere in this file, no import needed)
- Produces: `resolveHousingStepZip(stepNum: number, rawZip: string): Promise<void>` — attached to `window` alongside this file's other exports, so the rendered markup's `oninput`/`onchange` handlers can call it

- [ ] **Step 1: Write the failing tests**

Create `tests/frontend/housing_step_zip_lookup.test.mjs`. This follows the same sandbox-stubbing pattern as `housing_optimize_request.test.mjs`, but stubs the generic row-model globals (`rows`, `dirty`, `editValue`, `renderMain`, `api`) instead of `document.getElementById`, since this file's fields are driven by the CSV-backed row model, not raw DOM ids:

```javascript
// ZIP-first location entry for a Spending -> Housing "next step" (design
// 2026-09-16-housing-financing-and-zip-ux). Stubs the row-model globals
// (rows/dirty/editValue/renderMain/api) the same way
// housing_optimize_request.test.mjs stubs document.getElementById --
// dashboard_decomp_housing_scenarios.js is not a standalone ES module either.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

function rowFixtures() {
  return [
    { row_index: 1, section: "Housing", subsection: "next_step_1", label: "state", value: "" },
    { row_index: 2, section: "Housing", subsection: "next_step_1", label: "city_type", value: "" },
    { row_index: 3, section: "Housing", subsection: "next_step_1", label: "population_size", value: "" },
    { row_index: 4, section: "Housing", subsection: "next_step_1", label: "zip_code", value: "" },
  ];
}

function mountWithZipApi(apiResponse) {
  const sandbox = loadDashboardSandbox();
  sandbox.rows.length = 0;
  sandbox.rows.push(...rowFixtures());
  sandbox.dirty.clear();
  let renderCount = 0;
  sandbox.renderMain = () => {
    renderCount++;
  };
  let calledUrl = null;
  sandbox.api = async (url) => {
    calledUrl = url;
    return apiResponse;
  };
  return { sandbox, getRenderCount: () => renderCount, getCalledUrl: () => calledUrl };
}

describe("resolveHousingStepZip", () => {
  test("a valid ZIP fills state, city_type, and population_size", async () => {
    const { sandbox, getCalledUrl } = mountWithZipApi({
      success: true, city: "Hinsdale", state: "Illinois", area_type: "suburban", population: 17349,
    });
    await sandbox.resolveHousingStepZip(1, "60521");
    assert.match(getCalledUrl(), /zip-lookup\?zip=60521/);
    const stateRow = sandbox.rows.find((r) => r.row_index === 1);
    const cityTypeRow = sandbox.rows.find((r) => r.row_index === 2);
    const popRow = sandbox.rows.find((r) => r.row_index === 3);
    assert.equal(sandbox.dirty.get(stateRow.row_index), "Illinois");
    assert.equal(sandbox.dirty.get(cityTypeRow.row_index), "suburban");
    assert.equal(sandbox.dirty.get(popRow.row_index), "17349");
  });

  test("a valid ZIP is cached for the read-only City/State display", async () => {
    const { sandbox } = mountWithZipApi({
      success: true, city: "Hinsdale", state: "Illinois", area_type: "suburban", population: 17349,
    });
    await sandbox.resolveHousingStepZip(1, "60521");
    assert.equal(sandbox.window.housingStepZipLookup[1].city, "Hinsdale");
    assert.equal(sandbox.window.housingStepZipLookup[1].state, "Illinois");
    assert.ok(!sandbox.window.housingStepZipLookup[1].error);
  });

  test("an invalid ZIP records an error and leaves existing state alone", async () => {
    const { sandbox } = mountWithZipApi({ success: false, error: "ZIP 00000 not recognized." });
    sandbox.dirty.clear();
    const stateRow = sandbox.rows.find((r) => r.row_index === 1);
    stateRow.value = "Colorado";
    await sandbox.resolveHousingStepZip(1, "00000");
    assert.equal(sandbox.dirty.has(stateRow.row_index), false, "state must not be touched");
    assert.equal(sandbox.window.housingStepZipLookup[1].error, "ZIP 00000 not recognized.");
  });

  test("re-renders after a lookup so the read-only display and auto-filled selects update", async () => {
    const { sandbox, getRenderCount } = mountWithZipApi({
      success: true, city: "Hinsdale", state: "Illinois", area_type: "suburban", population: 17349,
    });
    await sandbox.resolveHousingStepZip(1, "60521");
    assert.equal(getRenderCount(), 1);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/frontend/housing_step_zip_lookup.test.mjs`
Expected: FAIL with `sandbox.resolveHousingStepZip is not a function`

- [ ] **Step 3: Implement `resolveHousingStepZip`**

Add to `dashboard_decomp_housing_scenarios.js`, near `clearHousingNextStep` (both are per-step action handlers):

```javascript
// Cache for the read-only City/State display and any lookup error, keyed by
// step number -- mirrors window.housingLastEstimate's existing pattern for
// the "Estimate fields" button's cached result. Not persisted: a fresh page
// load simply shows nothing until the user (re-)enters a ZIP, same as that
// existing cache.
window.housingStepZipLookup = window.housingStepZipLookup || {};

export async function resolveHousingStepZip(stepNum, rawZip) {
  var zip = String(rawZip || "").trim();
  if (zip.length !== 5 || !/^\d{5}$/.test(zip)) {
    window.housingStepZipLookup[stepNum] = { error: "ZIP must be 5 digits." };
    renderMain();
    return;
  }
  var sub = "next_step_" + stepNum;
  var stepRows = rows.filter(function (r) {
    return r.section === "Housing" && norm(r.subsection || "") === sub;
  });
  var stateRow = stepRows.find(function (r) { return norm(r.label) === "state"; });
  var cityTypeRow = stepRows.find(function (r) { return norm(r.label) === "city_type"; });
  var popRow = stepRows.find(function (r) { return norm(r.label) === "population_size"; });

  var payload;
  try {
    payload = await api("/api/housing/zip-lookup?zip=" + encodeURIComponent(zip));
  } catch (e) {
    window.housingStepZipLookup[stepNum] = { error: "Error looking up ZIP: " + e.message };
    renderMain();
    return;
  }
  if (!payload || !payload.success) {
    // Leave state/city_type/population_size exactly as they were -- an
    // existing configured plan must not go blank on an unresolved ZIP.
    window.housingStepZipLookup[stepNum] = { error: (payload && payload.error) || "ZIP not recognized." };
    renderMain();
    return;
  }
  window.housingStepZipLookup[stepNum] = { city: payload.city, state: payload.state };
  if (stateRow) editValue(stateRow.row_index, payload.state, null);
  if (cityTypeRow) editValue(cityTypeRow.row_index, payload.area_type, null);
  if (popRow) editValue(popRow.row_index, String(payload.population), null);
  renderMain();
}
```

Add it to this file's `Object.assign(window, {...})` bridge block (find the existing one near the bottom of the file, alongside `renderScenarioManagementPanel` and friends) so the rendered `onchange="resolveHousingStepZip(...)"` markup can reach it:

```javascript
  resolveHousingStepZip,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test tests/frontend/housing_step_zip_lookup.test.mjs`
Expected: all PASS

- [ ] **Step 5: Write the failing render-order/markup test**

Add to the same new test file:

```javascript
describe("renderNextHousingStepSection -- ZIP-first field order", () => {
  test("ZIP is the first field, State renders read-only", () => {
    const sandbox = loadDashboardSandbox();
    const stepRows = [
      { row_index: 10, section: "Housing", subsection: "next_step_1", label: "type", value: "purchase" },
      { row_index: 11, section: "Housing", subsection: "next_step_1", label: "state", value: "Colorado" },
      { row_index: 12, section: "Housing", subsection: "next_step_1", label: "city_type", value: "suburban" },
      { row_index: 13, section: "Housing", subsection: "next_step_1", label: "population_size", value: "20000" },
      { row_index: 14, section: "Housing", subsection: "next_step_1", label: "zip_code", value: "" },
    ];
    const html = sandbox.renderNextHousingStepSection(stepRows, "Next Housing Step 1", 1);
    const zipIdx = html.indexOf("resolveHousingStepZip(1");
    const stateIdx = html.indexOf('data-row="11"');
    assert.ok(zipIdx >= 0, "ZIP input with a resolve handler must be present");
    assert.ok(zipIdx < stateIdx, "ZIP renders before State");
    // State is read-only display, not an editable <select>/<input data-row>:
    assert.ok(!/<select[^>]*data-row="11"/.test(html), "State must not be an editable select");
  });
});
```

- [ ] **Step 6: Run test to verify it fails**

Run: `node --test tests/frontend/housing_step_zip_lookup.test.mjs`
Expected: FAIL — current markup still renders State as an editable field first, no ZIP input

- [ ] **Step 7: Reorder the field lists and add the special-case rendering**

In `dashboard_decomp_housing_scenarios.js`, change:

```javascript
  var PURCHASE_FIRST = ["state", "city_type", "population_size", "zip_code"];
```

and

```javascript
  var RENT_FIRST = ["state", "city_type", "population_size", "zip_code"];
```

to (both identical, ZIP first):

```javascript
  var PURCHASE_FIRST = ["zip_code", "state", "city_type", "population_size"];
```

```javascript
  var RENT_FIRST = ["zip_code", "state", "city_type", "population_size"];
```

Then update the `firstRows` rendering (currently just the `city_type` special-case):

```javascript
  if (firstRows.length)
    html +=
      '<div class="field-list inline-row">' +
      firstRows
        .map(function (r) {
          if (norm(r.label) === "zip_code") {
            var cached = window.housingStepZipLookup[stepNum];
            var errorHtml =
              cached && cached.error
                ? '<div class="small warning">' + esc(cached.error) + "</div>"
                : "";
            return (
              '<div class="field"><div class="field-label">ZIP</div>' +
              '<input type="text" class="zip" maxlength="5" inputmode="numeric" ' +
              'data-row="' + r.row_index + '" value="' + esc(valOf(r) || "") + '" ' +
              'oninput="editValue(' + r.row_index + ',this.value,this)" ' +
              'onchange="resolveHousingStepZip(' + stepNum + ',this.value)">' +
              errorHtml +
              "</div>"
            );
          }
          if (norm(r.label) === "state") {
            var cachedCity = window.housingStepZipLookup[stepNum];
            var display = cachedCity && cachedCity.city
              ? cachedCity.city + ", " + esc(valOf(r) || "")
              : esc(valOf(r) || "Enter a ZIP above");
            return (
              '<div class="field"><div class="field-label">City, State</div>' +
              '<div class="field-readonly" data-row="' + r.row_index + '">' + display + "</div>" +
              "</div>"
            );
          }
          return norm(r.label) === "city_type"
            ? '<div class="field"><div class="field-label">Area Type</div>' +
                housingAreaTypeSelect(r) +
                "</div>"
            : fieldHtml(r);
        })
        .join("") +
      "</div>";
```

(this replaces the existing `if (firstRows.length) html += ...` block entirely — the `.field-list.inline-row` class switch is the layout change from the design's Section 4)

- [ ] **Step 8: Run tests to verify they pass**

Run: `node --test tests/frontend/housing_step_zip_lookup.test.mjs`
Expected: all PASS

- [ ] **Step 9: Update the section-note help copy**

Replace the generic "text"/"int" hints' surrounding note text is out of scope for a mechanical field-help rewrite in this task (that copy comes from each row's own CSV-driven description field, not this file) — skip any change there; the `field-readonly` display and inline error message added in Step 7 are the user-facing help this task adds.

- [ ] **Step 10: Run the full frontend suite**

Run: `node --test tests/frontend/*.test.mjs`
Expected: all PASS

- [ ] **Step 11: Add the `.field-readonly` CSS rule**

Check `frontend/css/dashboard.css` for whether `.field-readonly` already exists (it may, from another read-only display elsewhere in the app):

```bash
grep -n "field-readonly" "frontend/css/dashboard.css"
```

If it does not exist, add a minimal rule near the existing `.field` rules (around dashboard.css line 35-55):

```css
.field-readonly{padding:8px 10px;color:var(--muted);background:var(--bg-subtle,#f5f5f5);border-radius:4px;font-size:14px}
```

(If `--bg-subtle` is not a defined CSS variable in this file, check the top of `dashboard.css` for the actual subtle-background variable name in use and substitute it — do not introduce an undefined variable.)

- [ ] **Step 12: Commit**

```bash
git add frontend/js/dashboard_decomp_housing_scenarios.js frontend/css/dashboard.css tests/frontend/housing_step_zip_lookup.test.mjs
git commit -m "feat(housing): ZIP-first location entry on the Spending -> Housing page"
```

---

### Task 9: Full-suite regression check and manual browser verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `python -m pytest tests/ -m "not slow and not nightly" -q`
Expected: all PASS (aside from any pre-existing `requires_live_input`-gated test that depends on this machine's local, gitignored plan data — see the prior housing-optimizer-progress-popup PR's note on that if one appears)

- [ ] **Step 2: Run the full frontend test suite**

Run: `node --test tests/frontend/*.test.mjs`
Expected: all PASS

- [ ] **Step 3: Run ruff**

Run: `ruff check src/ tests/`
Expected: `All checks passed!`

- [ ] **Step 4: Check the frontend size ratchet**

Run: `python -m pytest tests/test_frontend_size_ratchet.py -v`
Expected: PASS, or FAIL with a specific over-budget line count — if it fails, raise `TOTAL_JS_MAX_LINES` in `tests/test_frontend_size_ratchet.py` to the new measured size with a dated justification comment, following the exact precedent already in that file (see the 2026-09-16 entries above `TOTAL_JS_MAX_LINES`'s current value).

- [ ] **Step 5: Manual browser verification — optimizer panel**

Start the dev server via the project's `.claude/launch.json` (`retirement-planner-verify` or equivalent) and, in the browser:
- Open Strategy -> Scenario Change Sets -> Optimize next housing move.
- Confirm "Purchase assumptions" renders between "Current home" and "Move 1 — where", with Down payment % showing `20` and Mortgage rate % showing `6.85`.
- Confirm Move 1's "where" row shows Area Type immediately after the anchors block.
- Run an optimization with at least one buy candidate and one rent candidate (e.g. force Move 1 action = Rent, enable Move 2 with action = Buy) and confirm the results table's Move 1 cell shows `.../mo rent` with no purchase price, and Move 2's cell shows both `... purchase` and `.../mo P&I`.
- Clear the Mortgage rate % field, re-run, and confirm the run still succeeds (server-side falls back to per-location rate).

- [ ] **Step 6: Manual browser verification — Spending -> Housing page**

- Navigate to Spending -> Housing, find a "Next Housing Step" section (seed it via "Seed Housing Fields" if needed).
- Enter a real 5-digit ZIP (e.g. `60521`) in the new ZIP field and confirm City/State updates to a read-only display, and Area Type/Population auto-fill.
- Change Area Type manually afterward and confirm it stays changed (not overwritten).
- Enter an unrecognized ZIP (e.g. `00000`) and confirm an inline error appears while the previously-resolved City/State/Area Type/Population remain displayed unchanged.

- [ ] **Step 7: Stop the dev server**

```bash
# stop however the launch config was started (Ctrl+C in its terminal, or the corresponding preview_stop if run via the Browser pane tooling)
```

No commit for this task — it is verification only. If any step surfaces a bug, fix it as a small addendum to the task whose code owns the bug, re-run that task's tests, and commit the fix under that task's own commit message convention (`fix(housing...): ...`).

---

## Self-Review Notes

- **Spec coverage:** Section 1 (purchase price fallback) -> Task 1. Section 2 (financing payload/helpers) -> Tasks 2-3. Section 3 (Area Type reorder, with the design's own correction) -> Task 6 Step 5. Section 4 (Purchase assumptions section) -> Task 6 Steps 1-4, 7-12. Results-table rendering -> Task 7. Section 6 (ZIP-first Housing page) -> Tasks 4 (endpoint) and 8 (frontend). Testing section -> covered per-task plus Task 9's full-suite pass.
- **Placeholder scan:** no TBD/TODO; every step has complete, pasteable code.
- **Type/name consistency checked:** `_purchase_price_for_location`, `_effective_mortgage_rate`, `estimate_monthly_pi_payment`, `zip_lookup`, `resolveHousingStepZip`, `housingOptDownPaymentPct`/`housingOptMortgageRatePct` ids, and the `financing` payload key are spelled identically everywhere they're consumed across tasks.
