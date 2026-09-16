# Housing financing display + ZIP-first location UX

2026-09-16

## Problem

Two independent gaps in the housing optimizer and the Spending -> Housing
page, discovered while reviewing the optimizer's results table:

1. **Financing display is wrong and inconsistent with the plan's own math.**
   The results table shows one dollar figure per move (`est_price`) that
   looks like a purchase price regardless of whether the move buys or rents.
   For a rent move it is not a rent figure at all -- it is the ZIP-scaled
   home-value estimate from the screening step, which the plan never
   actually pays. For a buy move, that same screening estimate is not
   necessarily the price the engine's own cost math uses either:
   `_purchase_price_for_location()` in `plan_variant.py` prefers the
   move's Price Min/Max midpoint if set, else falls back to a flatter
   state-level estimate -- silently ignoring the ZIP-scaled estimate the
   results table happens to display. There is also no down payment / mortgage
   rate control anywhere in the optimizer panel, even though the API already
   accepts both (`down_payment_pct`, `mortgage_rate_pct`, defaulting to 20%
   and a location-based rate respectively).

2. **The Spending -> Housing page's location entry doesn't match the
   optimizer's, and asks for less than it could.** Each housing step's first
   field is a manual State dropdown. A `zip_code` field already exists in the
   underlying schema (recorded when the optimizer applies a recommendation)
   but the manual page never surfaces it, and Area Type / Population are
   independent manual selects even though the app has the same ZCTA-level
   Census table the optimizer's ZIP screen already uses to derive both. The
   fields also render as separate full-width boxes with generic "text"/"int"
   hints, rather than the optimizer's compact, help-affordance-driven layout.

## Goals

- A move's results row shows the dollar figure that actually matches its
  action: monthly rent for a rent move (no price shown at all), purchase
  price + estimated monthly P&I payment for a buy move -- and the purchase
  price shown is the same one the plan's cost math actually uses.
- A new "Purchase assumptions" section lets the user set down payment % and
  mortgage rate % once, applying to whichever moves end up buying.
- The Spending -> Housing page's per-step location entry becomes ZIP-first,
  resolving to a read-only City/State, with Area Type and Population
  auto-filled (still editable) from the same ZCTA table the optimizer uses,
  laid out compactly like the optimizer's own fields.
- Fields with a genuine single default value show that default in the field
  itself (not a placeholder), editable in place; the field's default is
  never a value the user has to intuit or explicitly ask this app about.

## Non-goals

- No loan-term input. Every mortgage in this app (existing engine code and
  this feature) assumes a fixed 30-year term; introducing a term control
  would not change anything, since nothing downstream reads it yet.
- No change to the manual Housing page's own existing per-step down
  payment / mortgage rate fields -- those already exist independently of the
  optimizer and are out of scope here.
- No per-anchor Area Type in the optimizer (one Area Type per move, as
  today) -- only its position within the existing "Move N -- where" row
  changes.

## Design

### 1. Purchase price now matches the plan's own math

`plan_variant._purchase_price_for_location()` gains a middle tier:

```
target_purchase_price_range midpoint (if set)
  -> Location.est_price (ZIP-scaled screening estimate, if set)  <- NEW
  -> state-level estimate (existing fallback, effectively dead for
     optimizer-generated candidates, since _splice_screen_detail always
     sets est_price -- kept only for a Location built by hand, e.g. in a
     test, with no est_price)
```

This is a real behavior change to the deterministic engine's cost basis for
any buy move without an explicit price range: it now prices the home at the
ZIP's own scaled estimate instead of a flatter state-wide number. Net worth,
lifetime cost, and Monte Carlo success rate for those candidates will shift
accordingly. This is intentional -- it is what "make the engine use the
ZIP-scaled estimate" means -- and should be called out in the PR description
so it doesn't read as a silent recompute drift.

### 2. Results payload gains rent/buy financing fields

New pure helper in `plan_variant.py`, next to `_purchase_price_for_location`
and `_estimate_for_location` (same module, no circular import risk since
`results.py` already imports from `.models` and can import from
`.plan_variant` the same way `optimizer.py` does):

```python
def _effective_mortgage_rate(loc: Location, mortgage_rate_pct: float | None) -> float:
    """Same fallback _purchase_step already applies: explicit rate wins,
    else the location's own estimate rate, else the flat default."""
    if mortgage_rate_pct is not None:
        return float(mortgage_rate_pct)
    est = _estimate_for_location(loc, 'purchase')
    return float(est.get('mortgage_rate_pct', _DEFAULT_MORTGAGE_RATE) or _DEFAULT_MORTGAGE_RATE)


def estimate_monthly_pi_payment(
    purchase_price: float, down_payment_pct: float, mortgage_rate_pct: float,
    term_years: int = 30,
) -> float:
    """Level-payment fixed-rate monthly P&I. Deliberately mirrors
    deterministic_engine.py's own _mortgage_payment_and_balance formula
    (same principal/rate/term inputs, same standard amortization formula) --
    for DISPLAY only, not called by the engine itself, so a change here
    cannot alter what a run actually charges. Kept as a small pure function
    (no engine coupling) rather than extracting the engine's nested closure,
    which is a larger, riskier refactor of stable, well-tested code that
    this feature does not need."""
    principal = max(0.0, purchase_price * (1.0 - down_payment_pct))
    if principal <= 0:
        return 0.0
    monthly_rate = max(0.0, mortgage_rate_pct) / 12.0
    n = max(1, term_years) * 12
    if monthly_rate <= 1e-9:
        return principal / n
    return principal * monthly_rate / (1 - (1 + monthly_rate) ** (-n))
```

`down_payment_pct` and `mortgage_rate_pct` (already computed in `api.py`)
are threaded through `optimize_housing()` (already has both in scope where
it calls `format_output`) into `format_output` -> `_format_candidate` ->
`_format_move`. `_format_move` computes, per move:

```python
if move.action == 'rent':
    financing = {'monthly_rent': _estimate_for_location(move.location, 'rent')['monthly_rent']}
else:
    price = _purchase_price_for_location(move.location)
    rate = _effective_mortgage_rate(move.location, mortgage_rate_pct)
    financing = {
        'purchase_price': price,
        'monthly_pi_payment': estimate_monthly_pi_payment(price, down_payment_pct, rate),
    }
```

added to the move's dict as `'financing': financing`. `_purchase_step()` in
`plan_variant.py` is updated to call `_effective_mortgage_rate()` for its own
`est_rate` line instead of inlining the same fallback expression, so the
rate-resolution logic exists in exactly one place.

`location.est_price`
stays in the payload unchanged (still useful context -- "what this ZIP's
homes typically cost" -- separate from "what this candidate's plan pays"),
but the results table will read `financing.purchase_price` /
`financing.monthly_pi_payment` / `financing.monthly_rent`, not
`location.est_price`, for the numbers it renders.

### 3. Results table rendering

`housingOptMoveCellHtml()` in `dashboard_decomp_housing_optimizer.js`
branches on `move.action`:

- **rent**: `{year} · Rent · {zip} {city}, {state} · {distance} mi ·
  ${monthly_rent}/mo rent [· {family distance} mi from family]`
  -- no price field at all.
- **buy**: `{year} · Buy · {zip} {city}, {state} · {distance} mi ·
  ${purchase_price} purchase · ${monthly_pi}/mo P&I [· {family distance} mi
  from family]`

### 4. "Purchase assumptions" section (optimizer panel)

New `housingOptRow("Purchase assumptions", ...)` inserted between the
existing "Current home" row and "Move 1 -- where" in
`renderHousingOptimizePanelHtml()`:

- **Down payment %** -- `<input type="number" id="housingOptDownPaymentPct"
  value="20" min="0" max="100">`. Shows its real default (20) in the field,
  per the "defaults are shown, not hidden behind a placeholder" preference.
- **Mortgage rate %** -- `<input type="number" id="housingOptMortgageRatePct"
  value="6.85" min="0" max="100" step="0.01">`. Pre-filled with the app's
  existing flat fallback constant (`_DEFAULT_MORTGAGE_RATE = 0.0685`), shown
  as a real, editable value rather than a placeholder. Left untouched, this
  flat rate is sent explicitly for every buy move. If the user clears the
  field entirely, `buildHousingOptRequest()` sends `null` for
  `mortgage_rate_pct`, which still resolves server-side to each candidate's
  own location-based rate (today's behavior, preserved as an intentional
  opt-out rather than removed).

Both fields get full `HOUSING_OPT_FIELD_HELP` entries (title / meaning /
connections / options / impact, matching every other field's help content)
and are included in `buildHousingOptRequest()` as top-level
`down_payment_pct` / `mortgage_rate_pct`. No persistence code needed --
`saveHousingOptInputs()` already persists every element with an `id` under
the panel root generically. One new validation rule (§8, rule 10) bounds
both fields to 0-100.

### 5. Move N -- where row: Area Type reordering

Correction to an earlier assumption in this design's discussion: Area Type
already lives in the same `housingOptRow("Move N -- where", ...)` as the
anchors block (it is Max Population's row-mate there, not Lot Size's, which
lives in the separate "what" row with Bedrooms/Bathrooms). There is no
relocation to make. The only change here is reordering that row's fields so
Area Type renders immediately after Anchors (before Radius / Min score),
for closer visual adjacency to the location controls it conceptually
belongs with -- purely a field-order change in `housingOptMoveWhereRowHtml()`,
no new markup.

### 6. Spending -> Housing page: ZIP-first location entry

**New endpoint** `GET /api/housing/zip-lookup?zip=NNNNN` in `src/housing/api.py`,
reusing the existing ZCTA table (`zip_screen/table.py: load_table()`) and
`zip_screen/resolve.py: city_type_for_density()`:

```python
def zip_lookup(zip_code: str) -> tuple[dict, int]:
    if len(zip_code) != 5 or not zip_code.isdigit():
        return {'success': False, 'error': 'ZIP must be 5 digits.'}, 400
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

(malformed-ZIP shape matches the existing family-ZIP validation in `api.py`
line 141: `len(zip_code) != 5 or not zip_code.isdigit()`)

**Field behavior** in `dashboard_decomp_housing_scenarios.js`'s per-step
renderer (currently `PURCHASE_FIRST`/`RENT_FIRST` = `["state", "city_type",
"population_size", "zip_code"]`):

- `zip_code` becomes the one editable location input (5-digit text,
  `class="zip"`, same convention as the family-ZIP / anchor-ZIP inputs).
- On a valid ZIP (lookup succeeds): City/State render as read-only derived
  text; Area Type and Population pre-fill from the lookup but stay editable
  selects/inputs afterward (fill-then-override, matching the optimizer's
  "Estimate fields" pattern already on this same page).
  Editing them after the auto-fill does not re-trigger the lookup or get
  overwritten by it.
- On an invalid/unrecognized ZIP: inline error message; the step's
  currently-stored `state` / `city_type` / `population_size` values are
  left exactly as they were (read-only display of the old values) rather
  than being cleared -- so an existing configured plan does not go blank
  just because this code shipped without the user touching that step.
- The `state` dropdown itself is removed from manual editing entirely; it
  is now written only by a successful ZIP lookup or inherited unchanged
  from a plan's prior saved value.

**Layout**: switch this field group from the current one-per-full-width-row
`.field` boxes to the existing `.field-list.inline-row` class (already used
elsewhere for exactly this compact side-by-side grouping), rendering ZIP /
City,State / Area Type / Population as one visually grouped cluster --
equivalent effect to the optimizer's `.housing-opt-row`, via an existing
shared class rather than a new one. Real help copy (adapted from the
optimizer's own Area Type / anchor-ZIP help text) replaces today's generic
"text"/"int" hints under these fields.

## Testing

- **Backend**: unit tests for `_purchase_price_for_location`'s new fallback
  tier, `estimate_monthly_pi_payment` (hand-checked principal/rate/term
  cases, including the zero-rate edge case), `_effective_mortgage_rate`'s
  three-way fallback, and `_format_move`'s rent-vs-buy branching in
  `results.py`. A test for `/api/housing/zip-lookup` (found ZIP, unrecognized
  ZIP, malformed input).
- **Frontend**: extend `housing_optimize_panel.test.mjs` for the new
  Purchase Assumptions fields (presence, default values, help entries,
  0-100 validation) and `housing_optimize_request.test.mjs` for the new
  request keys (including the "cleared field sends null" case). New/extended
  test coverage for the Housing page's ZIP field behavior (valid/invalid
  ZIP, auto-fill-then-editable, old-value preservation on invalid ZIP).
- **Manual**: browser-verify both pages after implementation, same as prior
  housing-optimizer changes in this repo (dev server via `.claude/launch.json`,
  screenshot the new sections, exercise a full run in each mode).
