# Housing Optimizer Refinement — Design

Date: 2026-09-16
Status: Approved for planning
Supersedes parts of: `documentation/archive/superpowers/specs/2026-09-09-housing-optimization-design.md`,
`docs/superpowers/specs/2026-09-15-zip-code-housing-screening-design.md`

## 1. Problem

The "Optimize next housing move" panel produces results that cannot be acted on and
accepts inputs that cannot produce results.

Observed failure (user screenshot, 2026-09-16): move-1 purchase window 2031–2046 with
move-2 latest sale year 2030. Because `generate_move2_candidates` forces
`earliest_sale_2 = anchor.purchase_year` (`src/housing/candidates.py:37-65`), no move-2
candidate can exist. The panel ran a full search and returned the generic string
"No candidates satisfied the search windows and constraints", naming neither the
conflicting fields nor a fix.

Five further problems:

1. **Output is not actionable.** `renderHousingOptimizeResultsHtml`
   (`frontend/js/dashboard_decomp_housing_scenarios.js:1613-1631`) renders one prose
   sentence plus a table whose only location detail is a state abbreviation. The
   screened ZIP, its estimated price, and its distance from the anchor — all present in
   the screening payload — are dropped before display.
2. **The model welds selling to moving.** A `HousingCandidate` pairs one `sale_year`
   with one `purchase_year` (`src/housing/models.py:87-114`). A household that rents
   for two years while its old home sits on the market, or that keeps the old home,
   is not representable.
3. **Two competing location modes.** "Choose locations manually" (state + city_type +
   population, `:1319-1358`) and "Search by ZIP radius" coexist. The manual mode
   predates screening and produces candidates with no ZIP, no score, and no distance.
4. **Screening under-constrains.** Radius, minimum score, and price range filter the
   funnel; area type and population do not, though both are derivable from the shipped
   ZIP snapshot.
5. **The form is unusable at length.** ~40 one-per-line `<label>` elements, no helper
   text, no persistence between visits, no validation.

## 2. Goals

- Model the disposition of the current home independently of where and when the
  household moves.
- Make every recommendation row contain enough detail to act on without a second lookup.
- Screen candidates on the constraints a person actually shops with: distance, quality,
  area type, population, price, dwelling size.
- Never spend a search on an impossible window.
- Reduce the form to horizontal rows of compact fields, each field labelled *above* its
  control rather than to the left of it. A left-hand label adds its own width to every
  field, which is what forces horizontal scrolling once a row holds more than three or
  four controls; stacking the label costs a little height instead and lets each field
  occupy only the width its control actually needs. Help goes in the existing right-hand
  panel, not inline, for the same reason.

## 3. Non-goals

- No change to the deterministic engine or Monte Carlo runner. The optimizer continues
  to score candidates by running the real plan, not a separate model.
- No new ZIP data build. Area type and population come from the existing
  `src/housing/zip_screen/data/zip_metrics.csv.gz` snapshot.
- No per-ZIP lot-size data. Lot size is a price input only (§6.3).
- No change to §121 mechanics in Phase 1. `home_sale.py` continues to grant the full
  statutory exclusion regardless of ownership duration, and
  `sec121_exclusion_flag` stays an informational display flag.

## 4. Phasing

**Phase 1 — this spec's implementation.** Everything in §5–§12. The original home's
disposition offers `Sell` and `Keep`, where `Keep` means `home_sale_yr = 0`: carrying
costs continue to accrue and no income is received. The UI states plainly that rental
income is not modelled, so a `Keep` candidate is scored as a pure cost centre.

**Phase 2 — keep-and-rent-out, specified in §13, implemented separately.** Turning
`Keep` into an income property requires a new subsystem in the tax engine. It is scoped
here so Phase 1's data structures do not have to be rewritten to accommodate it, but it
ships on its own plan.

The phase boundary is chosen because `Keep` is already a legitimate Phase 1 outcome even
without rental income: keeping avoids selling costs and capital-gains tax while the home
continues to appreciate, so a `Keep` + rent-your-residence candidate can genuinely beat
selling. Phase 2 changes how well `Keep` scores, not whether it is representable.

## 5. Domain model

### 5.1 Three independent decisions

`HousingCandidate` (`src/housing/models.py:87-114`) is replaced by:

```python
@dataclass(frozen=True)
class OriginalHome:
    disposition: str          # 'sell' | 'keep'  (resolved per candidate)
    sale_year: int | None     # searched when disposition == 'sell'; None when 'keep'

@dataclass(frozen=True)
class Move:
    index: int                # 1 or 2
    acquisition_year: int
    action: str               # 'buy' | 'rent'
    mode: str                 # 'sequential' | 'concurrent'  (concurrent only for index 2)
    location: Location

@dataclass(frozen=True)
class HousingCandidate:
    original_home: OriginalHome
    moves: tuple[Move, ...]   # 1 or 2 entries
```

`purchase_year` is renamed `acquisition_year` everywhere. For a rental it is the lease
start year; for a purchase it is the closing year. The rename is mechanical but total —
no field named `purchase_year` survives in `src/housing/`.

### 5.2 Derived, not searched

If move 1 bought and move 2 acquires elsewhere in `sequential` mode, the move-1 home is
sold in the move-2 acquisition year. This is not a search variable; it is written into
`next_housing_steps` and handled by the existing `apply_next_housing_sale`
(`src/projection_stages/home_sale.py:263-336`). In `concurrent` mode the move-1 home is
kept and never sold, unchanged from today.

### 5.3 Dual ownership

`no_dual_ownership` constrains *ownership* only. Renting a residence while still owning
the previous home is always permitted and is the intended way to bridge a gap. When the
checkbox is on, these are rejected at candidate generation:

- `disposition == 'keep'` combined with any `action == 'buy'` move — the household would
  own two homes with no rental income to offset the second. In Phase 2 this combination
  becomes legal (§13).
- A `buy` move whose `acquisition_year` precedes `original_home.sale_year`.
- In `concurrent` mode the flag is ignored and the checkbox is disabled, with the
  existing explanatory note (`:1251-1262`). Unchanged.

When the checkbox is off, both overlaps are generated and the objective decides. An
overlapping candidate carries a `dual_ownership_years` note in its result row.

### 5.4 Candidate generation

`src/housing/candidates.py` is rewritten around the product of three ranges rather than
the current nested sale/purchase loop:

The request's `original_home.disposition` is `sell`, `keep`, or `auto`. `auto` searches
both and lets the objective decide, mirroring the `auto` action on each move; it is the
default. A candidate always resolves to one concrete disposition.

```
for disposition in dispositions:                  # ['sell'], ['keep'], or both under 'auto'
  for sale_year in sale_years(disposition):       # window, or [None] when 'keep'
    for loc1, acq1, action1 in move1_space:
      if not dual_ownership_ok(...): continue
      yield candidate
      for loc2, acq2, action2, mode2 in move2_space(acq1):
        if acq2 <= acq1 and mode2 == 'sequential': continue
        yield candidate
```

`move2_space` no longer derives its lower bound from move 1; it uses move 2's own
declared window, intersected with `acq2 > acq1` for sequential moves. The
`MOVE2_CROSS_PRODUCT_CAP` pre-flight (`src/housing/optimizer.py:134-159`) is retained and
recalculated against the new space.

Narrowed search (`src/housing/search.py`) keeps coordinate descent but its coordinates
change: the 2-D search over (sale year, purchase year) becomes a 3-D search over
(sale year, move-1 acquisition year, move-2 acquisition year), with the sale-year axis
collapsed when disposition is `keep`. `NARROWED_2D_MAX_EVALS` is renamed
`NARROWED_MAX_EVALS_PER_AXIS` and applied per axis.

## 6. Screening

### 6.1 Multi-anchor search

Each move carries its own independent search spec: 2–5 anchors, one shared radius, and
one shared set of filters. An anchor is either a city selected from
`top_cities.csv` or a hand-entered 5-digit ZIP; both resolve to a ZIP before screening.

Screening runs once per anchor and the results are unioned before dedup, so overlapping
radii do not produce duplicate candidates. `distance_miles` on a surviving ZIP is the
distance to its *nearest* anchor, and the payload records which anchor that was.

Move 2 has its own anchor list, radius, and filters. It is not required to overlap
move 1's.

### 6.2 Funnel

`run_screen` (`src/housing/zip_screen/screen.py:150-218`) gains three stages. The full
sequence, and the string rendered under the shortlist:

```
in_radius → with_data → above_score → matching_area_type → under_population_cap
          → affordable → distinct → near_family → promoted
```

- **matching_area_type** — a single area-type choice (`any` | `urban` | `suburban` |
  `exurban` | `rural`) compared against the ZIP's density-derived `city_type`
  (`src/housing/zip_screen/resolve.py:22-30`, thresholds in `models.py:41-43`).
  `any` is the default and skips the stage without hiding it from the funnel.
- **under_population_cap** — an optional maximum on the ZIP's `place_population`,
  falling back to `zcta_population` when the place population is absent. There is no
  minimum; a small town is never excluded for being small.
- **near_family** — §6.4.

Each stage that removes every remaining candidate produces a targeted relaxation hint,
extending the existing `_relaxation()` (`screen.py:129-147`) from min-score only to
whichever stage emptied the funnel.

### 6.3 Dwelling spec

Per move: bedrooms, bathrooms, property type, square-footage band, **lot-size band**,
built-within-N-years, and a target price range. All feed `estimate_housing_cost`
(`src/server_services/strategy_asset_service.py:189-321`) as multiplicative factors,
exactly as the existing five do.

New in `strategy_asset_service.py` alongside `SQFT_BAND_MULT` (`:120-126`):

```python
LOT_SIZE_BAND_MULT = {
    "under_quarter": 0.92,   # under 1/4 acre
    "quarter_half":  1.00,   # 1/4 to 1/2 acre   (default)
    "half_one":      1.08,   # 1/2 to 1 acre
    "one_three":     1.20,   # 1 to 3 acres
    "over_three":    1.35,   # over 3 acres
}
LOT_SIZE_BAND_LABELS = { ... }   # human strings, same shape as SQFT_BAND_LABELS
```

Values are illustrative starting points on the same footing as the existing bedroom,
bathroom, property-type and sqft multipliers, which are documented as not sourced from a
dataset (`strategy_asset_service.py:111-116`). Lot size does **not** filter ZIPs: the
snapshot has no lot-area column. The field's help text says so explicitly, so a user does
not read a shortlist as having been screened on lot size.

Only `target_purchase_price_range` filters the funnel (the existing `affordable` stage).
The rest shape the estimated price that the range is tested against.

### 6.4 Family presence

Family presence is redefined from a state-level timeline check to a ZIP-proximity filter.

Inputs: a 5-digit **family ZIP**, a **proximity radius** of 10/25/50/100 miles, and
**from**/**through** years.

It is a hard filter and the last screen before scoring. A candidate is dropped if, in any
year of the presence window, the household's residence is farther than the radius from
the family ZIP. Residence for a given year is derived from the candidate's timeline the
way `_location_timeline` derives it today (`src/housing/constraints.py:9-26`), extended
to the decoupled model. A `concurrent` second residence satisfies presence for the years
it is held, preserving today's `family_presence_via_rental` behaviour and its result-row
note.

Distance uses the existing haversine helper (`src/housing/zip_screen/geo.py:21-27`).

Because an over-tight radius can empty the result set in a way that is hard to diagnose,
each shortlist row is also annotated with its distance to the family ZIP, and the
`near_family` funnel stage reports how many candidates it removed.

`family_presence_ok` (`constraints.py:29-58`) is rewritten; the state-based form is
removed rather than kept alongside.

## 7. API

Both schemas are version-bumped: `housing_optimize_v1` → `housing_optimize_v2`,
`zip_screen_v1` → `zip_screen_v2`. Registered in `src/api_contracts.py:130`. There is no
v1 compatibility shim — the panel is the only consumer, and `tools/housing_lab.py` is
updated in the same change.

### 7.1 Request — `POST /api/housing/optimize`

```jsonc
{
  "objective":      "net_worth",          // | lifetime_cost | mc_success_rate
  "search_mode":    "full",               // | narrowed
  "move2_strategy": "anchored",           // | cross_product
  "no_dual_ownership": true,

  "family_presence": {                     // omitted when disabled
    "zip": "60521",
    "radius_miles": 25,                    // 10 | 25 | 50 | 100
    "from_year": 2026,
    "through_year": 2050
  },

  "original_home": {
    "disposition": "auto",                 // sell | keep | auto (default)
    "earliest_sale_year": 2030,            // required unless disposition == 'keep'
    "latest_sale_year": 2045
  },

  "move1": {
    "earliest_acquisition_year": 2031,
    "latest_acquisition_year": 2046,
    "action": "auto",                      // | buy | rent
    "search": {
      "anchors": [                          // 2-5
        { "kind": "city", "anchor_zip": "80014" },
        { "kind": "zip",  "anchor_zip": "60521" }
      ],
      "radius_miles": 25,                   // 5 | 10 | 25 | 50
      "min_quality_score": 60,              // 0-100
      "area_type": "any",                   // any|urban|suburban|exurban|rural
      "max_population": 250000,             // optional, null = no cap
      "shortlist_size": 4,                  // 2-5
      "dwelling": {
        "bedrooms": 3,
        "bathrooms": 2,
        "property_type": "single_family",
        "sqft_band": "1800_2500",
        "lot_size_band": "quarter_half",
        "built_within_years": null,
        "target_purchase_price_range": [400000, 700000]   // optional
      }
    }
  },

  "move2": {                                 // omitted when the second move is off
    "earliest_acquisition_year": 2040,
    "latest_acquisition_year": 2050,
    "action": "auto",
    "concurrent": false,
    "anchor_count": 5,
    "search": { /* same shape as move1.search */ }
  }
}
```

`locations` is removed from the request. `parse_zip_search` (`src/housing/api.py:183-209`)
becomes `parse_move_search`, called once per move.

### 7.2 Response

```jsonc
{
  "success": true,
  "schema": "housing_optimize_v2",
  "objective": "net_worth",
  "search_mode": "full",
  "move2_strategy": "anchored",
  "candidates_evaluated": 1284,

  "zip_screens": {                           // one per searched move
    "move1": { "schema": "zip_screen_v2", "...": "as today, plus:",
               "funnel": { "in_radius": 0, "with_data": 0, "above_score": 0,
                           "matching_area_type": 0, "under_population_cap": 0,
                           "affordable": 0, "distinct": 0, "near_family": 0,
                           "promoted": 0 },
               "anchors": [ { "anchor_zip": "80014", "city": "Aurora", "state": "CO" } ],
               "shortlist": [ { "...": "as today, plus:",
                                "nearest_anchor_zip": "80014",
                                "area_type": "suburban",
                                "population": 386261,
                                "family_distance_miles": 18.4 } ] },
    "move2": { "...": "same shape, present only when move 2 is searched" }
  },

  "recommendation": { "...": "the rank-1 candidate, also present in candidates[0]" },
  "candidates": [ /* ranked, up to 10 */ ],
  "rejections": {                            // why the search produced what it did
    "dual_ownership": 40,
    "family_presence": 12,
    "move_order": 8
  },
  "message": "..."                           // present only when the run yields nothing
}
```

`alternatives` is replaced by `candidates`, a single ranked list whose first entry is the
recommendation. This removes the current duplication between `recommendation` and
`alternatives[0]` and lets the frontend render one uniform table.

Each candidate:

```jsonc
{
  "rank": 1,
  "original_home": { "disposition": "sell", "sale_year": 2032 },
  "moves": [
    {
      "index": 1,
      "acquisition_year": 2033,
      "action": "buy",
      "mode": "sequential",
      "location": {
        "zip_code": "80024", "city": "Derby", "state": "CO",
        "area_type": "suburban", "population": 12480,
        "nss": 89.1, "band": "Very Favorable",
        "distance_miles": 11.83, "family_distance_miles": 18.4,
        "est_price": 539400
      },
      "sec121_exclusion_lost": false
    }
  ],
  "net_worth": 4210000,
  "lifetime_cost": 1180000,
  "mc_success_rate": 0.912,
  "objective_value": 4210000,
  "notes": ["family presence via rental"]
}
```

`est_price`, `distance_miles`, `area_type`, `population` and `family_distance_miles` are
spliced onto each move's location from the screening result, extending the mechanism that
already splices `nss` (`src/housing/api.py:156-162`).

`notes` replaces the ad-hoc `family_presence_via_rental` boolean and carries
dual-ownership overlap, §121, and family-presence notes as a list of strings the
frontend joins.

### 7.3 `POST /api/housing/zip-screen`

Accepts a single `{ "search": { ... } }` object of the same shape as `move1.search`, so
the "Preview shortlist" button works identically for move 1 and move 2 without the
endpoint knowing which move it serves.

## 8. Validation

Impossible inputs are blocked in the form before a run is spent. Validation runs on
every input event, renders messages next to the offending group, and disables the
Run button while any rule fails.

| # | Rule | Message |
|---|---|---|
| 1 | `earliest_sale_year <= latest_sale_year` | "Earliest sale year must not be after the latest sale year." |
| 2 | `move1.earliest_acquisition_year <= move1.latest_acquisition_year` | "Earliest move-1 year must not be after the latest." |
| 3 | `move2.latest_acquisition_year > move1.earliest_acquisition_year` (sequential move 2) | "Move 2 must be able to happen after move 1. Raise the move-2 latest year above {n}." |
| 4 | `no_dual_ownership` and `disposition == 'keep'` and every move action is `buy` | "Keeping the current home and buying another means owning two homes. Choose Rent, sell the current home, or turn off 'Never own two homes at once'." |
| 5 | `no_dual_ownership` and `disposition == 'sell'` and `move1.action == 'buy'` and `move1.latest_acquisition_year < earliest_sale_year` | "With no dual ownership, move 1 cannot be bought before the home is sold. Raise the move-1 latest year to at least {n}." |
| 6 | 2–5 anchors per searched move, each non-empty and resolvable | "Choose between 2 and 5 anchors for move {n}." |
| 7 | `family_presence.from_year <= through_year`, ZIP is 5 digits | "Family presence needs a 5-digit ZIP and a from-year no later than the through-year." |
| 8 | `concurrent` requires `search_mode == 'full'` | existing note (`:1458`), retained |
| 9 | price range min ≤ max when both given | "Minimum target price must not exceed the maximum." |

Rule 3 is the one that would have caught the screenshot.

Rules 4 and 5 fire only when the disposition is explicitly `sell` or `keep`. Under `auto`
the impossible combination is simply not generated, because the other disposition still
yields candidates — blocking the run there would be wrong.

Validation is duplicated server-side in `src/housing/api.py` and returns
`{"success": false, "error": ...}` — the client checks are for speed of feedback, not
trust.

When a run completes with zero candidates despite passing validation, the result area
renders the `rejections` breakdown and the emptying funnel stage instead of the current
generic sentence.

## 9. UI

### 9.1 Structure

The optimizer moves out of `frontend/js/dashboard_decomp_housing_scenarios.js` into a new
module `frontend/js/dashboard_decomp_housing_optimizer.js`. The host file is 1,841 lines
and also owns the spending/housing screen; the optimizer block is ~640 lines today and
roughly doubles under this design. `renderScenarioManagementPanel` continues to embed the
panel via an imported `renderHousingOptimizePanelHtml()`, so the panel's position in
Strategy → Scenarios is unchanged.

### 9.2 Layout

Global settings first, then the decisions in the order they happen:

| Row | Contents |
|---|---|
| **Objective & constraints** | Objective · Search mode · Move-2 strategy · Never own two homes at once |
| **Family presence** | Enable · Family ZIP · Within (10/25/50/100 mi) · From year · Through year |
| **Current home** | Sell / Keep / Auto · Earliest sale year · Latest sale year |
| **Move 1 — where** | Anchors (2–5) · Within (mi) · Min score · Area type · Max population · Shortlist size |
| **Move 1 — what** | BR · BA · Property type · Sqft · Lot size · Built within · Price min · Price max · *Preview shortlist* |
| **Move 1 — when** | Earliest year · Latest year · Action (Auto/Buy/Rent) |
| **Consider a second move** | checkbox; when on, three Move-2 rows mirroring the above, plus Concurrent and Anchor count |
| | **Run optimization** |

Each field is a vertical cell — label above, control below — laid out in a horizontal
flex row that wraps. Labels are never placed to the left of their control: that would add
label width to every field and push a six- or seven-field row into horizontal scrolling,
whereas a stacked label lets the cell be exactly as wide as its control. This replaces
today's one-`<label>`-per-line markup (`:1433-1485`), where the label sits inline before
the input.

Sizing rules, applied as CSS in `frontend/css/dashboard.css` under a
`.housing-optimize-panel` scope rather than inline `style=` attributes:

- Year inputs: `width: 5em`. Population and price inputs: `width: 8em`. ZIP inputs:
  `width: 5em`.
- Selects: `width: auto` so each is as wide as its longest option, with the existing
  fixed widths on `:1328`, `:1356`, `:1414` removed.
- Rows that wrap keep their group label on the first line and indent continuation lines.

The sale-year fields are disabled and dimmed when the disposition is `Keep`, with the
adjacent note: "Keeping the current home means its costs keep accruing. Rental income
from a kept home is not modelled — see the help panel."

### 9.3 Anchors control

Per move, a horizontal list of up to five compact anchor entries. Each is a two-part
control: a City/ZIP mode toggle and either the `top_cities` select or a 5-character ZIP
input. "+ Add anchor" appends up to five; each row past the second has a remove control.
Two are shown by default.

### 9.4 Results

One table row per recommendation, ranked, with the columns:

`Rank · Current home · Move 1 · Move 2 · Objective · MC success · Notes`

- **Rank** — a badge; rank 1 also carries a "Recommended" label.
- **Current home** — `Sell 2032` or `Keep`.
- **Move 1 / Move 2** — `2033 · Buy · 80024 Derby, CO · $539,400 · 11.8 mi`, with the
  family distance appended when family presence is enabled. `—` when there is no move 2.
- **Notes** — joined `notes` strings.

A row is one visual line where the viewport allows. When a row wraps, result boundaries
stay obvious through three cues used together: alternating row background shading, a
heavy horizontal rule between results, and the persistent rank badge in the first cell.
Rank-1 gets its own accent so the recommendation is findable after scrolling.

The shortlist preview table gains **Area type** and **Population** columns and, when
family presence is on, a **From family** column.

### 9.5 Help

No inline helper text — it would widen every row. Instead the panel uses the app's
existing right-hand Context Help pane (`frontend/index.html:79`, `#helpPanel`), the same
surface used by `showStepHelp` (`dashboard.js:3994-3998`) and `showFieldHelp`
(`dashboard_decomp_row_model.js:4292-4325`).

- Every optimizer field carries the standard `<sup class="field-info-i" title="…">i</sup>`
  affordance produced by `fieldTooltipHtml()` (`dashboard.js:2216-2228`), giving a short
  hover hint with no layout cost.
- Focusing or clicking a field calls a new `showHousingOptFieldHelp(key)`, which calls
  `ensureHelpPanelVisible()` (`dashboard_decomp_row_model.js:4288`) and writes the full
  entry into `#helpPanel`.
- Content lives in a new `HOUSING_OPT_FIELD_HELP` registry in the optimizer module,
  keyed by field id and built with the existing `pageHelp()` formatter
  (`dashboard.js:963-972`) so headings match the rest of the app: *What this value means
  / Value options and how to choose / How it relates to this page / Likely impact of
  changing it*.
- The panel's summary row gets a "Help" button that calls
  `showHousingOptFieldHelp('_panel')` for screen-level help covering the objective
  choices, the funnel, and the rental-income limitation.

Every field in §9.2 has an entry. Entries with real content to carry — area type, max
population, lot size, min quality score, disposition, dual ownership, family presence
radius, search mode, move-2 strategy, concurrent — are written as full four-section
entries; simple year fields get a one-paragraph *What this value means* plus the
validation rule that governs them.

### 9.6 Persistence

All panel inputs are written to `localStorage` under `retirement.housing_optimizer.v1` on
change (debounced) and restored by `renderHousingOptimizePanelHtml()`. This follows the
`SCENARIO_SET_STORAGE_KEY` pattern in the same area of the codebase
(`dashboard.js:2840`, written by `scenarioWriteSets`,
`dashboard_decomp_housing_scenarios.js:936-947`): a single JSON object, wrapped in
try/catch, silently ignored when unavailable or unparseable.

Stored: every input's value, the anchor lists, the move-2 enabled flag, and the
`<details>` open state. Not stored: results, shortlists, or anything derived from a run —
a restored form always starts with an empty result area, so a stale recommendation can
never be mistaken for a fresh one. Unknown keys in a stored payload are ignored and
missing keys fall back to defaults, so the shape can grow without a migration.

## 10. Spending / housing screen parity

`renderSpendingHousing` and `renderNextHousingStepSection`
(`dashboard_decomp_housing_scenarios.js:606-730`, `:453-599`) and the seed rows
(`strategy_asset_service.py:48-88`) are brought into full agreement with the optimizer, so
a recommendation can be transcribed field-for-field.

Changes to the `next_step_1` / `next_step_2` seed rows and their rendering:

| Field | Change |
|---|---|
| `city_type` | Option list becomes `urban\|suburban\|exurban\|rural`, matching the optimizer. `housingAreaTypeSelect` (`:426-432`) and the three seed descriptions are updated together. Existing saved values are unaffected; `exurban` is added, nothing is removed. |
| `lot_size_band` | **New**, default `quarter_half`, purchase-only, feeding the Estimate button like `sqft_band`. |
| `zip_code` | **New**, optional, both types. Records the ZIP a recommendation came from so the screen and the optimizer refer to the same place. |
| `bedrooms`, `bathrooms`, `property_type`, `sqft_band`, `built_within_years` | Already present. Option lists, ordering, labels and help text are made identical to the optimizer's — today they agree by coincidence, not by construction. |

The optimizer gains **down payment %** and **mortgage rate %** inputs in its
Objective & constraints row, replacing the hardcoded `_DEFAULT_DOWN_PAYMENT_PCT = 0.20`
(`src/housing/plan_variant.py:16-17`). Without them the optimizer scores every purchase at
20% down at an implied rate while the spending screen uses the user's own figures, so the
two screens disagree on the cost of the same house. Both values are passed through
`_apply_candidate` into the generated `next_housing_steps`.

The cross-link copy at `:692` is rewritten to name the fields that carry across and to
state that ZIP, price and distance now appear in the optimizer's results.

Not in scope: an "Apply this recommendation" button that writes a winning candidate into
the next-step rows. It is a natural follow-up once the field sets match, but field
alignment is the requested scope.

## 11. Testing

Python:
- `tests/test_housing_candidates_decoupled.py` — new. Sale/acquisition independence,
  `keep` producing `sale_year is None`, dual-ownership rejection for each of the two
  cases in §5.3, and `acq2 > acq1` enforcement for sequential move 2.
- `tests/test_zip_screen_filters.py` — new. Area type, population cap, and the funnel
  counts each stage reports, including the stage-specific relaxation hints.
- `tests/test_housing_family_presence_radius.py` — new. ZIP-radius filter including the
  concurrent-residence case and the `family_distance_miles` annotation.
- `tests/test_housing_multi_anchor_screen.py` — new. Union-then-dedup across overlapping
  anchors, and `distance_miles` resolving to the nearest anchor.
- `tests/test_housing_api_validation.py` — new. Each numbered rule in §8 rejected
  server-side, including the exact screenshot inputs for rule 3.
- Existing `tests/test_housing_optimizer_unit.py`,
  `test_housing_optimizer_integration.py`, `test_housing_coordinate_descent_unit.py` and
  the 14 `test_zip_screen_*.py` files are updated for the renamed fields and v2 schema.

JavaScript — `tests/frontend/housing_optimize_panel.test.mjs`, extended:
- Request body shape for the v2 contract, single-anchor and multi-anchor.
- Each validation rule disabling Run with its message.
- Result-row rendering: ZIP, price, distance and family distance all present; `—` for a
  missing move 2; rank-1 flagged.
- `localStorage` round-trip, including that results are not restored and that an
  unparseable payload falls back to defaults.

Functional — a new `tests/test_housing_optimizer_panel_functional.py` following the
existing `test_zip_screen_*_functional.py` pattern, asserting the row-oriented layout,
the help affordance on every field, and the wrapped-result separation cues.

`tools/housing_lab.py` is updated to emit `housing_optimize_v2` payloads.

## 12. File change map

| File | Change |
|---|---|
| `src/housing/models.py` | `OriginalHome`, `Move`; rewrite `HousingCandidate`; rename purchase→acquisition; `AREA_TYPES`, `FAMILY_RADII_MILES` |
| `src/housing/candidates.py` | Rewrite generation around §5.4 |
| `src/housing/search.py` | Coordinate descent over the new axes |
| `src/housing/constraints.py` | Rewrite `family_presence_ok` as ZIP-radius; dual-ownership predicate |
| `src/housing/optimizer.py` | New request shape, per-move screening, `rejections` tally |
| `src/housing/results.py` | v2 payload; `candidates` replaces `recommendation`+`alternatives`; `notes` |
| `src/housing/api.py` | `parse_move_search`, per-move parsing, server-side §8 validation, splice location detail |
| `src/housing/plan_variant.py` | Honour `keep`; down payment and mortgage rate from the request |
| `src/housing/zip_screen/screen.py` | Multi-anchor union, three new funnel stages, per-stage relaxation |
| `src/housing/zip_screen/schema.py` | `LOT_SIZE_*`; `FAMILY_RADII_MILES`; `ScreenedZip` new fields |
| `src/server_services/strategy_asset_service.py` | `LOT_SIZE_BAND_MULT/LABELS`; seed-row changes from §10 |
| `src/api_contracts.py` | v2 schema ids |
| `frontend/js/dashboard_decomp_housing_optimizer.js` | **New** — the whole panel |
| `frontend/js/dashboard_decomp_housing_scenarios.js` | Remove the optimizer block; §10 parity changes |
| `frontend/css/dashboard.css` | `.housing-optimize-panel` layout, result shading, rank badge |
| `tools/housing_lab.py` | v2 payloads |

## 13. Phase 2 — keep and rent out

Out of scope for implementation here; specified so Phase 1 does not foreclose it.

Turning `Keep` into an income property requires, at minimum:

1. **A rental-income channel.** No generic income line exists today — income streams are
   wages, Social Security, and pensions/annuities (`src/data_io.py:1319, 2218-2228`).
   Rent received needs to reach AGI.
2. **Schedule E netting.** The kept home's carrying costs are already computed in
   `src/projection_stages/spending_and_rmd.py:347-355` as household outflows; as a rental
   they become deductible expenses netted against rent, not spending. Mortgage interest
   moves with them.
3. **Depreciation.** A new accumulated-depreciation field alongside `home_basis`
   (`data_io.py:1014`), with 27.5-year straight-line on the building portion.
4. **§1250 recapture at sale.** `_compute_home_sale_economics`
   (`src/projection_stages/home_sale.py:53-72`) taxes recaptured depreciation at 25%
   before the remaining gain is treated as LTCG.
5. **§121 with teeth.** The exclusion is currently granted in full regardless of
   ownership duration or use. A rented former residence needs the two-of-five-year test
   and the non-qualified-use ratio, which turns `sec121_exclusion_flag`
   (`constraints.py:61-70`) from a display flag into a dollar adjustment. This affects
   every sale in the plan, not only rented ones, so it is the riskiest of the five.
6. **Passive-activity loss limits.** A rental that runs at a loss cannot always offset
   other income.

Phase 1 changes that make Phase 2 additive rather than a rewrite:

- `OriginalHome.disposition` is a string, not a boolean, so `rent_out` joins `sell`,
  `keep` and `auto` without changing the field's type or the stored `localStorage` shape.
- The dual-ownership predicate is a single function (§5.3), so admitting `keep` + `buy`
  when the kept home is rented is a change in one place.
- Candidate `notes` is a list, so a recapture or passive-loss note needs no schema change.

Phase 2 also revisits the Phase 1 disclosure text, which exists only to be removed.

## 14. Decision log

| Decision | Choice | Rationale |
|---|---|---|
| Manual location mode | Removed | Produced candidates with no ZIP, score, or distance — the very detail the new output requires. |
| Anchors | 2–5 per move, independent lists | A household compares metros, not one metro; move 2 is often a different region entirely. |
| Radius | One per move, shared across its anchors | Per-anchor radii add a control per anchor for a distinction users did not ask for. |
| Population | Maximum only | Stated requirement. A small town is never excluded for being small. |
| Area type | Single choice, not multi-select | Stated requirement, and matches the single `city_type` the spending screen stores. |
| Lot size | Price multiplier, no ZIP filter | No lot-area column exists in the snapshot; a filter would be a fiction. |
| Family presence | Hard filter, candidate level | Stated requirement: the final screen. Soft ranking would let the optimizer recommend a move away from family on a small dollar edge. |
| `recommendation` + `alternatives` | Merged into `candidates` | They duplicated the rank-1 candidate and forced two rendering paths. |
| Schema versioning | v2, no v1 shim | The panel is the only consumer and ships in the same change. |
| Label placement | Above the control, never left of it | A left label adds its width to every field and forces horizontal scrolling in a multi-field row; stacking costs height instead. |
| Helper text | Right-hand Context Help pane, not inline | Inline text widens every row; the app already has this surface and its heading conventions. |
| Down payment / mortgage rate | Added to the optimizer | Otherwise the two screens price the same house differently. |
| Keep-and-rent-out | Phase 2 | Needs a tax subsystem that does not exist; `Keep` is still a valid Phase 1 outcome without it. |

---

# Part II — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the housing-move optimizer so the current home's disposition is searched
independently of the moves, candidates are screened on the constraints people actually
shop with, and every recommendation row carries the ZIP, price and distance needed to act
on it.

**Architecture:** Three layers, changed bottom-up. The value types in `src/housing/models.py`
replace the sale/purchase-welded `HousingCandidate` with an `OriginalHome` plus a tuple of
`Move`s; `candidates.py` and `search.py` enumerate over that shape; `zip_screen/` gains
three funnel stages and multi-anchor union; `results.py`/`api.py` publish a v2 payload; and
the panel moves to its own frontend module. Each layer is landed with its own tests before
the next depends on it, so a half-finished plan still leaves the suite green.

**Tech Stack:** Python 3.11+, pytest (`pythonpath=["."]`, run from the repo root). Frontend
is ES modules with no framework, tested by `node --test` and by Python functional tests that
assert on rendered markup. No new dependencies.

## Global Constraints

- Python ≥ 3.11. No new runtime dependencies in `requirements.txt`.
- Run Python tests as `pytest` from the repo root; run JS tests as `npm test`.
- New test files carry a tier marker from `pyproject.toml`: `unit`, `integration`,
  `contract`, `golden_master`, or `e2e`.
- No engine changes. `src/projection_stages/` is not modified in Phase 1.
- Schema ids are exactly `housing_optimize_v2` and `zip_screen_v2`. No v1 shim.
- `purchase_year` → `acquisition_year` is total within `src/housing/`; no field of the old
  name survives.
- Labels sit above their control, never to the left (§2, §9.2).
- No inline helper text in the panel; help goes to `#helpPanel` (§9.5).
- Area-type values are exactly `any|urban|suburban|exurban|rural`.
- Lot-size band values are exactly `under_quarter|quarter_half|half_one|one_three|over_three`.
- Family radii are exactly `10|25|50|100`; search radii are exactly `5|10|25|50`.
- Commit after every task. Never commit with a failing suite.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/server_services/strategy_asset_service.py` | Lot-size multipliers; seed-row parity | 1, 16 |
| `src/housing/models.py` | Value types and tunables only, no behaviour | 2 |
| `src/housing/candidates.py` | Full-grid enumeration over the decoupled shape | 3 |
| `src/housing/search.py` | Bounded coordinate descent over the same axes | 4 |
| `src/housing/zip_screen/screen.py` | Funnel stages, multi-anchor union, dedup | 5, 6 |
| `src/housing/zip_screen/schema.py` | Screening constants and `ScreenedZip` shape | 5, 6 |
| `src/housing/constraints.py` | Hard candidate filters: dual ownership, family radius | 7 |
| `src/housing/results.py` | v2 payload shaping, presentation only | 8 |
| `src/housing/optimizer.py` | Orchestration, two-pass scoring, rejection tally | 9 |
| `src/housing/plan_variant.py` | Candidate → engine config | 9 |
| `src/housing/api.py` | Wire parsing and server-side validation | 10 |
| `frontend/js/dashboard_decomp_housing_optimizer.js` | **New.** The whole panel | 11–15 |
| `frontend/js/dashboard_decomp_housing_scenarios.js` | Spending screen; optimizer removed | 11, 16 |
| `frontend/css/dashboard.css` | Panel layout, result shading, rank badge | 14 |

---

### Task 1: Lot-size band as a price multiplier

Self-contained and depends on nothing. Landing it first means every later task that builds
a `Location` already has the field to populate.

**Files:**
- Modify: `src/server_services/strategy_asset_service.py:120-133` (beside `SQFT_BAND_MULT`)
- Modify: `src/housing/models.py:50-63` (`Location`)
- Modify: `src/housing/zip_screen/resolve.py:45-56` (`resolve_location`)
- Test: `tests/test_housing_lot_size_multiplier.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `LOT_SIZE_BAND_MULT: dict[str, float]`, `LOT_SIZE_BAND_LABELS: dict[str, str]`,
  `Location.lot_size_band: str = 'quarter_half'`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_housing_lot_size_multiplier.py
"""Lot-size band as a price multiplier (design 2026-09-16 §6.3)."""
import pytest

from src.housing.models import Location
from src.server_services.strategy_asset_service import (
    LOT_SIZE_BAND_LABELS,
    LOT_SIZE_BAND_MULT,
    estimate_housing_cost,
)

pytestmark = pytest.mark.unit


def test_bands_and_labels_cover_the_same_five_keys():
    expected = {'under_quarter', 'quarter_half', 'half_one', 'one_three', 'over_three'}
    assert set(LOT_SIZE_BAND_MULT) == expected
    assert set(LOT_SIZE_BAND_LABELS) == expected


def test_quarter_half_is_the_neutral_default():
    assert LOT_SIZE_BAND_MULT['quarter_half'] == 1.00
    assert Location(state='IL').lot_size_band == 'quarter_half'


def test_multiplier_increases_monotonically_with_lot_size():
    order = ['under_quarter', 'quarter_half', 'half_one', 'one_three', 'over_three']
    values = [LOT_SIZE_BAND_MULT[k] for k in order]
    assert values == sorted(values)
    assert len(set(values)) == len(values)


def test_a_bigger_lot_raises_the_estimated_purchase_price():
    base = estimate_housing_cost({'state': 'IL', 'city_type': 'suburban',
                                  'population_size': 20000, 'lot_size_band': 'quarter_half'})
    big = estimate_housing_cost({'state': 'IL', 'city_type': 'suburban',
                                 'population_size': 20000, 'lot_size_band': 'one_three'})
    assert big['purchase_price'] > base['purchase_price']


def test_an_unknown_band_falls_back_to_neutral_rather_than_raising():
    neutral = estimate_housing_cost({'state': 'IL', 'city_type': 'suburban',
                                     'population_size': 20000, 'lot_size_band': 'quarter_half'})
    junk = estimate_housing_cost({'state': 'IL', 'city_type': 'suburban',
                                  'population_size': 20000, 'lot_size_band': 'not_a_band'})
    assert junk['purchase_price'] == neutral['purchase_price']
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_housing_lot_size_multiplier.py -v`
Expected: FAIL with `ImportError: cannot import name 'LOT_SIZE_BAND_MULT'`

- [ ] **Step 3: Add the multipliers**

In `src/server_services/strategy_asset_service.py`, immediately after `SQFT_BAND_LABELS`
(currently ending line 133):

```python
# Lot-size band, added 2026-09-16 (design §6.3). Same footing as the bedroom,
# bathroom, property-type and sqft multipliers above: illustrative starting
# points, not sourced from a dataset. Lot size deliberately does NOT filter
# ZIPs -- the screening snapshot has no lot-area column -- so this is the only
# place it has any effect.
LOT_SIZE_BAND_MULT = {
    "under_quarter": 0.92,
    "quarter_half": 1.00,
    "half_one": 1.08,
    "one_three": 1.20,
    "over_three": 1.35,
}
LOT_SIZE_BAND_LABELS = {
    "under_quarter": "under 1/4 acre",
    "quarter_half": "1/4 to 1/2 acre",
    "half_one": "1/2 to 1 acre",
    "one_three": "1 to 3 acres",
    "over_three": "over 3 acres",
}
```

- [ ] **Step 4: Apply the multiplier in `estimate_housing_cost`**

In `estimate_housing_cost` (`:189-321`), find where `SQFT_BAND_MULT` is applied to the
price and multiply by the lot factor in the same expression. Read the surrounding lines
first and match the existing style; the lookup itself is:

```python
lot_mult = LOT_SIZE_BAND_MULT.get(
    str(data.get('lot_size_band', 'quarter_half') or 'quarter_half').strip().lower(), 1.00
)
```

`.get(..., 1.00)` is what makes the unknown-band test pass: an unrecognised value is
neutral, not an error, because this value arrives from a stored config row that may predate
the field.

- [ ] **Step 5: Add the field to `Location` and `resolve_location`**

`src/housing/models.py`, in `Location` after `sqft_band` (`:59`):

```python
    lot_size_band: str = 'quarter_half'
```

`src/housing/zip_screen/resolve.py`, in the `Location(...)` call after `sqft_band` (`:53`):

```python
        lot_size_band=str(spec.get('lot_size_band', 'quarter_half') or 'quarter_half'),
```

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_housing_lot_size_multiplier.py -v`
Expected: 5 passed

Run: `pytest tests/ -m "not slow and not nightly" -q`
Expected: no new failures — `Location` gained a defaulted field, so existing construction
sites are unaffected.

- [ ] **Step 7: Commit**

```bash
git add src/server_services/strategy_asset_service.py src/housing/models.py \
        src/housing/zip_screen/resolve.py tests/test_housing_lot_size_multiplier.py
git commit -m "feat(housing): add lot-size band as a purchase-price multiplier"
```

---

### Task 2: Decoupled value types

Introduces the new shape without yet using it, so the rewrite in Task 3 has something to
build against and the suite stays green in between.

**Files:**
- Modify: `src/housing/models.py`
- Test: `tests/test_housing_models_decoupled.py` (create)

**Interfaces:**
- Consumes: `Location` from Task 1.
- Produces:
  - `OriginalHome(disposition: str, sale_year: int | None)`
  - `Move(index: int, acquisition_year: int, action: str, location: Location, mode: str = 'sequential')`
  - `HousingCandidate(original_home: OriginalHome, moves: tuple[Move, ...], anchor_of=None)`
    with properties `.is_two_move`, `.move1`, `.move2`
  - `MoveWindow(earliest_acquisition_year: int, latest_acquisition_year: int)`
  - `SaleWindow(earliest_sale_year: int, latest_sale_year: int)`
  - `FamilyPresence(zip_code: str, radius_miles: int, from_year: int, through_year: int)`
  - `DISPOSITIONS = ('sell', 'keep', 'auto')`, `AREA_TYPES = ('any', 'urban', 'suburban',
    'exurban', 'rural')`, `FAMILY_RADII_MILES = (10, 25, 50, 100)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_housing_models_decoupled.py
"""The sale/acquisition-decoupled value types (design 2026-09-16 §5.1)."""
import dataclasses

import pytest

from src.housing.models import (
    AREA_TYPES,
    DISPOSITIONS,
    FAMILY_RADII_MILES,
    FamilyPresence,
    HousingCandidate,
    Location,
    Move,
    MoveWindow,
    OriginalHome,
    SaleWindow,
)

pytestmark = pytest.mark.unit


def _cand(*moves, disposition='sell', sale_year=2032):
    return HousingCandidate(
        original_home=OriginalHome(disposition=disposition, sale_year=sale_year),
        moves=tuple(moves),
    )


def _move(index=1, year=2033, action='buy', state='CO', mode='sequential'):
    return Move(index=index, acquisition_year=year, action=action,
                location=Location(state=state), mode=mode)


def test_keep_carries_no_sale_year():
    home = OriginalHome(disposition='keep', sale_year=None)
    assert home.sale_year is None


def test_a_move_has_an_acquisition_year_not_a_purchase_year():
    field_names = {f.name for f in dataclasses.fields(Move)}
    assert 'acquisition_year' in field_names
    assert 'purchase_year' not in field_names


def test_candidate_exposes_move1_and_move2():
    one = _cand(_move(index=1))
    assert one.move1.index == 1
    assert one.move2 is None
    assert one.is_two_move is False

    two = _cand(_move(index=1), _move(index=2, year=2041))
    assert two.move2.acquisition_year == 2041
    assert two.is_two_move is True


def test_rent_is_an_action_not_a_missing_year():
    """The old model encoded 'rent' as purchase_year=None, which made a rental
    indistinguishable from an unset field. A rental now has a real year."""
    m = _move(action='rent', year=2035)
    assert m.action == 'rent'
    assert m.acquisition_year == 2035


def test_family_presence_is_a_zip_and_a_radius():
    fp = FamilyPresence(zip_code='60521', radius_miles=25,
                        from_year=2026, through_year=2050)
    assert fp.zip_code == '60521'
    assert fp.radius_miles in FAMILY_RADII_MILES
    assert not hasattr(fp, 'region')


def test_windows_are_separate_types():
    assert SaleWindow(2030, 2045).latest_sale_year == 2045
    assert MoveWindow(2031, 2046).earliest_acquisition_year == 2031


def test_enumerations_match_the_spec_exactly():
    assert DISPOSITIONS == ('sell', 'keep', 'auto')
    assert AREA_TYPES == ('any', 'urban', 'suburban', 'exurban', 'rural')
    assert FAMILY_RADII_MILES == (10, 25, 50, 100)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_housing_models_decoupled.py -v`
Expected: FAIL with `ImportError: cannot import name 'OriginalHome'`

- [ ] **Step 3: Replace the input types in `models.py`**

Replace `SearchWindow` (`:66-71`), `Move2Window` (`:74-77`), `FamilyPresence` (`:80-85`),
`HousingCandidate` (`:87-114`) and `ScoredCandidate` (`:117-124`) with:

```python
DISPOSITIONS = ('sell', 'keep', 'auto')
AREA_TYPES = ('any', 'urban', 'suburban', 'exurban', 'rural')
FAMILY_RADII_MILES = (10, 25, 50, 100)
MOVE_ACTIONS = ('auto', 'buy', 'rent')


@dataclass(frozen=True)
class SaleWindow:
    earliest_sale_year: int
    latest_sale_year: int


@dataclass(frozen=True)
class MoveWindow:
    earliest_acquisition_year: int
    latest_acquisition_year: int


@dataclass(frozen=True)
class FamilyPresence:
    """Proximity to a fixed ZIP, not residence in a state (design §6.4)."""
    zip_code: str
    radius_miles: int
    from_year: int
    through_year: int


@dataclass(frozen=True)
class OriginalHome:
    """What happens to the home the household owns today.

    ``disposition`` is resolved per candidate: 'sell' carries a searched
    ``sale_year``; 'keep' carries ``None`` and leaves ``home_sale_yr`` at 0.
    'auto' is a request-level value only -- it never reaches a candidate,
    because generation expands it into both concrete dispositions.
    """
    disposition: str
    sale_year: int | None = None


@dataclass(frozen=True)
class Move:
    """One acquisition. Independent of any sale (design §5.1).

    ``action`` is 'buy' or 'rent' -- never 'auto', which is a request-level
    value expanded during generation. ``acquisition_year`` is the closing year
    for a purchase and the lease-start year for a rental; the old model's
    ``purchase_year=None``-means-rent convention is gone, so a rental now has
    a real year and an explicit action.
    """
    index: int
    acquisition_year: int
    action: str
    location: Location
    mode: str = 'sequential'   # 'sequential' | 'concurrent' (index 2 only)


@dataclass
class HousingCandidate:
    original_home: OriginalHome
    moves: tuple[Move, ...]
    anchor_of: "HousingCandidate | None" = None

    @property
    def move1(self) -> Move:
        return self.moves[0]

    @property
    def move2(self) -> Move | None:
        return self.moves[1] if len(self.moves) > 1 else None

    @property
    def is_two_move(self) -> bool:
        return len(self.moves) > 1


@dataclass
class ScoredCandidate:
    candidate: HousingCandidate
    net_worth: float
    lifetime_cost: float
    mc_success_rate: float | None
    sec121_exclusion_lost: list[bool]
    notes: list[str] = field(default_factory=list)
```

Add `field` to the `dataclasses` import at `:10`:

```python
from dataclasses import dataclass, field
```

Rename the narrowed-search budgets (`:29-36`) — the axes change in Task 4, so the old
2D/1D names stop describing anything:

```python
NARROWED_MAX_EVALS_PER_AXIS = 25
_NARROWED_EVALS_PER_ANCHOR_LOCATION = NARROWED_MAX_EVALS_PER_AXIS * 2
```

- [ ] **Step 4: Run the new test**

Run: `pytest tests/test_housing_models_decoupled.py -v`
Expected: 7 passed

- [ ] **Step 5: Confirm the expected breakage and its extent**

Run: `pytest tests/ -m "not slow and not nightly" -q 2>&1 | tail -40`

Expected: failures across `test_housing_optimizer_unit.py`,
`test_housing_optimizer_integration.py`, `test_housing_coordinate_descent_unit.py` and the
`test_zip_screen_*.py` files. This is intended — Tasks 3–10 repair them in order. Record
the failing count in the commit message so the next task can confirm it is shrinking, and
do not attempt to fix them here.

- [ ] **Step 6: Commit**

```bash
git add src/housing/models.py tests/test_housing_models_decoupled.py
git commit -m "feat(housing)!: decoupled OriginalHome/Move value types

Sale and acquisition become independent. Downstream modules are repaired in
the following tasks; the housing suite is red between this commit and the
api.py rewrite."
```

---

### Task 3: Candidate generation over the new shape

**Files:**
- Rewrite: `src/housing/candidates.py`
- Test: `tests/test_housing_candidates_decoupled.py` (create)

**Interfaces:**
- Consumes: Task 2's types.
- Produces:
  - `generate_candidates(*, locations1, move1_window, sale_window, dispositions, move1_action, no_dual_ownership) -> list[HousingCandidate]`
  - `extend_with_move2(anchors, *, locations2, move2_window, move2_action, concurrent, no_dual_ownership) -> list[HousingCandidate]`
  - `select_anchors(ranked, anchor_count) -> list[HousingCandidate]`
  - `select_all_eligible(scored) -> list[HousingCandidate]`
  - `estimate_move2_candidate_count(eligible, locations2, move2_window, move2_action, concurrent, no_dual_ownership, narrowed) -> int`
  - `dual_ownership_ok(candidate) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_housing_candidates_decoupled.py
"""Generation over decoupled sale/acquisition (design 2026-09-16 §5.3, §5.4)."""
import pytest

from src.housing.candidates import (
    dual_ownership_ok,
    extend_with_move2,
    generate_candidates,
)
from src.housing.models import Location, MoveWindow, SaleWindow

pytestmark = pytest.mark.unit

LOCS = [Location(state='CO'), Location(state='AZ')]


def _gen(**kw):
    kw.setdefault('locations1', LOCS)
    kw.setdefault('sale_window', SaleWindow(2030, 2031))
    kw.setdefault('move1_window', MoveWindow(2030, 2032))
    kw.setdefault('dispositions', ('sell',))
    kw.setdefault('move1_action', 'auto')
    kw.setdefault('no_dual_ownership', True)
    return generate_candidates(**kw)


def test_acquisition_year_is_not_forced_to_follow_the_sale_year_for_a_rental():
    """The whole point of decoupling: rent at the new place in 2030 while the
    old home is still on the market until 2031."""
    cands = _gen(move1_action='rent')
    assert any(c.original_home.sale_year == 2031 and c.move1.acquisition_year == 2030
               for c in cands)


def test_no_dual_ownership_blocks_buying_before_the_sale_but_not_renting():
    bought_early = [c for c in _gen(move1_action='buy')
                    if c.move1.acquisition_year < c.original_home.sale_year]
    assert bought_early == []

    rented_early = [c for c in _gen(move1_action='rent')
                    if c.move1.acquisition_year < c.original_home.sale_year]
    assert rented_early != []


def test_dual_ownership_off_allows_the_overlap():
    cands = _gen(move1_action='buy', no_dual_ownership=False)
    assert any(c.move1.acquisition_year < c.original_home.sale_year for c in cands)


def test_keep_produces_a_null_sale_year_and_ignores_the_sale_window():
    cands = _gen(dispositions=('keep',), move1_action='rent')
    assert cands
    assert all(c.original_home.sale_year is None for c in cands)
    assert all(c.original_home.disposition == 'keep' for c in cands)


def test_keep_plus_buy_is_rejected_under_no_dual_ownership():
    assert _gen(dispositions=('keep',), move1_action='buy', no_dual_ownership=True) == []
    assert _gen(dispositions=('keep',), move1_action='buy', no_dual_ownership=False) != []


def test_auto_expands_into_both_dispositions():
    cands = _gen(dispositions=('sell', 'keep'), move1_action='rent')
    assert {c.original_home.disposition for c in cands} == {'sell', 'keep'}


def test_auto_action_generates_both_buy_and_rent():
    assert {c.move1.action for c in _gen(move1_action='auto')} == {'buy', 'rent'}


def test_move2_uses_its_own_window_not_the_move1_acquisition_year():
    """The screenshot bug: move 2's lower bound used to be derived from move 1's
    purchase year, so a declared move-2 window was silently overridden."""
    anchors = _gen(move1_action='buy')
    out = extend_with_move2(anchors, locations2=LOCS,
                            move2_window=MoveWindow(2035, 2036),
                            move2_action='buy', concurrent=False,
                            no_dual_ownership=True)
    assert out
    assert {c.move2.acquisition_year for c in out} == {2035, 2036}


def test_move2_must_come_after_move1_when_sequential():
    anchors = _gen(move1_action='buy', move1_window=MoveWindow(2035, 2035))
    out = extend_with_move2(anchors, locations2=LOCS,
                            move2_window=MoveWindow(2030, 2036),
                            move2_action='buy', concurrent=False,
                            no_dual_ownership=True)
    assert out
    assert all(c.move2.acquisition_year > c.move1.acquisition_year for c in out)


def test_an_impossible_move2_window_yields_nothing_rather_than_being_coerced():
    anchors = _gen(move1_action='buy', move1_window=MoveWindow(2040, 2040))
    out = extend_with_move2(anchors, locations2=LOCS,
                            move2_window=MoveWindow(2030, 2035),
                            move2_action='buy', concurrent=False,
                            no_dual_ownership=True)
    assert out == []


def test_concurrent_move2_may_share_a_year_with_move1():
    """A second simultaneous residence is not a relocation, so the
    strictly-after rule does not apply to it."""
    anchors = _gen(move1_action='buy', move1_window=MoveWindow(2035, 2035))
    out = extend_with_move2(anchors, locations2=LOCS,
                            move2_window=MoveWindow(2035, 2035),
                            move2_action='rent', concurrent=True,
                            no_dual_ownership=True)
    assert out
    assert all(c.move2.mode == 'concurrent' for c in out)


def test_dual_ownership_ok_is_the_single_predicate():
    sell_then_buy = _gen(move1_action='buy')[0]
    assert dual_ownership_ok(sell_then_buy) is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_housing_candidates_decoupled.py -v`
Expected: FAIL with `ImportError: cannot import name 'generate_candidates'`

- [ ] **Step 3: Rewrite `candidates.py`**

Replace the whole file body below the docstring:

```python
from __future__ import annotations

from .models import (
    HousingCandidate,
    Location,
    Move,
    MoveWindow,
    OriginalHome,
    SaleWindow,
    ScoredCandidate,
    _NARROWED_EVALS_PER_ANCHOR_LOCATION,
)


def _actions(action: str) -> tuple[str, ...]:
    if action == 'auto':
        return ('buy', 'rent')
    if action in ('buy', 'rent'):
        return (action,)
    raise ValueError(f"Unknown action: {action!r}")


def dual_ownership_ok(cand: HousingCandidate) -> bool:
    """The single place the 'never own two homes' rule is decided (§5.3).

    Two ways a candidate can own two homes at once:
      1. The original home is kept and something else is bought. With no
         rental-income model (Phase 2), a kept home is a pure cost centre, so
         this is refused outright rather than scored.
      2. A home is bought before the original one is sold.

    Concurrent mode is exempt: it always keeps two homes by construction, so
    the flag does not apply and the UI disables it.
    """
    home = cand.original_home
    buys = [m for m in cand.moves if m.action == 'buy' and m.mode != 'concurrent']
    if home.disposition == 'keep':
        return not buys
    if home.sale_year is None:
        return True
    return all(m.acquisition_year >= home.sale_year for m in buys)


def generate_candidates(
    *,
    locations1: list[Location],
    move1_window: MoveWindow,
    sale_window: SaleWindow,
    dispositions: tuple[str, ...],
    move1_action: str,
    no_dual_ownership: bool,
) -> list[HousingCandidate]:
    """Every (disposition, sale year, location, acquisition year, action) point.

    The three axes are independent -- that is the whole change from the old
    nested sale/purchase loop. ``no_dual_ownership`` prunes at the end via the
    single predicate rather than by clamping a loop bound, so the rule lives in
    one readable place.
    """
    out: list[HousingCandidate] = []
    for disposition in dispositions:
        if disposition == 'keep':
            sale_years: list[int | None] = [None]
        else:
            sale_years = list(range(sale_window.earliest_sale_year,
                                    sale_window.latest_sale_year + 1))
        for sale_year in sale_years:
            home = OriginalHome(disposition=disposition, sale_year=sale_year)
            for loc in locations1:
                for year in range(move1_window.earliest_acquisition_year,
                                  move1_window.latest_acquisition_year + 1):
                    for action in _actions(move1_action):
                        cand = HousingCandidate(
                            original_home=home,
                            moves=(Move(index=1, acquisition_year=year,
                                        action=action, location=loc),),
                        )
                        if no_dual_ownership and not dual_ownership_ok(cand):
                            continue
                        out.append(cand)
    return out


def extend_with_move2(
    anchors: list[HousingCandidate],
    *,
    locations2: list[Location],
    move2_window: MoveWindow,
    move2_action: str,
    concurrent: bool,
    no_dual_ownership: bool,
) -> list[HousingCandidate]:
    """Add a second move to each anchor, using move 2's OWN declared window.

    The old implementation derived move 2's lower bound from the anchor's
    purchase year, silently overriding whatever the user asked for. Here the
    declared window is authoritative and the only coupling is the ordering
    rule: a sequential move 2 must come strictly after move 1. A concurrent
    move 2 is a second simultaneous residence, not a relocation, so it may
    share move 1's year.
    """
    mode = 'concurrent' if concurrent else 'sequential'
    out: list[HousingCandidate] = []
    for anchor in anchors:
        for loc in locations2:
            for year in range(move2_window.earliest_acquisition_year,
                              move2_window.latest_acquisition_year + 1):
                if not concurrent and year <= anchor.move1.acquisition_year:
                    continue
                for action in _actions(move2_action):
                    cand = HousingCandidate(
                        original_home=anchor.original_home,
                        moves=anchor.moves + (Move(index=2, acquisition_year=year,
                                                   action=action, location=loc,
                                                   mode=mode),),
                        anchor_of=anchor,
                    )
                    if no_dual_ownership and not concurrent and not dual_ownership_ok(cand):
                        continue
                    out.append(cand)
    return out


def select_anchors(ranked: list[ScoredCandidate], anchor_count: int) -> list[HousingCandidate]:
    """Top move-1 candidates eligible to carry a move 2.

    Unlike the old rule, a rental move 1 IS eligible: with sale decoupled from
    acquisition, renting first and buying at move 2 is an ordinary plan, not a
    dead end.
    """
    return [s.candidate for s in ranked][:max(0, anchor_count)]


def select_all_eligible(scored: list[ScoredCandidate]) -> list[HousingCandidate]:
    return [s.candidate for s in scored]


def estimate_move2_candidate_count(
    eligible: list[HousingCandidate],
    locations2: list[Location],
    move2_window: MoveWindow,
    move2_action: str,
    concurrent: bool,
    no_dual_ownership: bool,
    narrowed: bool,
) -> int:
    """Move-2 candidates cross_product would evaluate, computed before any
    engine call (see MOVE2_CROSS_PRODUCT_CAP)."""
    if narrowed:
        return len(eligible) * len(locations2) * _NARROWED_EVALS_PER_ANCHOR_LOCATION
    return len(extend_with_move2(
        eligible, locations2=locations2, move2_window=move2_window,
        move2_action=move2_action, concurrent=concurrent,
        no_dual_ownership=no_dual_ownership,
    ))
```

`filter_candidates_by_action` is deleted: action is now generated rather than filtered
after the fact, so a post-hoc filter would have nothing to remove.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_housing_candidates_decoupled.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add src/housing/candidates.py tests/test_housing_candidates_decoupled.py
git commit -m "feat(housing): generate candidates over independent sale and acquisition axes

Move 2 now uses its own declared window instead of deriving its lower bound
from move 1's purchase year, which silently overrode the user's input."
```

---

### Task 4: Narrowed search over the new axes

**Files:**
- Rewrite: `src/housing/search.py`
- Test: `tests/test_housing_coordinate_descent_unit.py` (rewrite in place)

**Interfaces:**
- Consumes: Task 3's generation, Task 2's types.
- Produces:
  - `generate_move1_candidates_narrowed(*, locations1, move1_window, sale_window, dispositions, move1_action, no_dual_ownership, score_fn) -> list[ScoredCandidate]`
  - `generate_move2_candidates_narrowed(anchors, *, locations2, move2_window, move2_action, concurrent, no_dual_ownership, score_fn) -> list[ScoredCandidate]`

  `score_fn: Callable[[HousingCandidate], ScoredCandidate | None]` — returns `None` for a
  candidate the constraints reject, which the search treats as an infeasible point.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_housing_coordinate_descent_unit.py
"""Bounded coordinate descent over (sale year, move-1 year, move-2 year).

Replaces the pre-2026-09-16 2D/1D version, whose axes were (sale, purchase)
with a separate 1D rent branch. Rent is now an action rather than a missing
year, so the rent branch is gone and the axes are the three year variables.
"""
import pytest

from src.housing.models import (
    HousingCandidate,
    Location,
    MoveWindow,
    SaleWindow,
    ScoredCandidate,
)
from src.housing.search import (
    generate_move1_candidates_narrowed,
    generate_move2_candidates_narrowed,
)

pytestmark = pytest.mark.unit

LOCS = [Location(state='CO')]


def _scorer(counter, peak_sale=2033, peak_acq=2036):
    """Single-peaked score so hill-climbing has a findable optimum."""
    def score(cand: HousingCandidate) -> ScoredCandidate | None:
        counter.append(cand)
        sale = cand.original_home.sale_year or peak_sale
        value = -abs(sale - peak_sale) - abs(cand.move1.acquisition_year - peak_acq)
        return ScoredCandidate(candidate=cand, net_worth=float(value),
                               lifetime_cost=-float(value), mc_success_rate=None,
                               sec121_exclusion_lost=[False])
    return score


def test_narrowed_search_finds_the_peak_without_evaluating_the_whole_grid():
    calls = []
    out = generate_move1_candidates_narrowed(
        locations1=LOCS, move1_window=MoveWindow(2030, 2050),
        sale_window=SaleWindow(2030, 2050), dispositions=('sell',),
        move1_action='buy', no_dual_ownership=False, score_fn=_scorer(calls),
    )
    best = max(out, key=lambda s: s.net_worth)
    assert best.candidate.original_home.sale_year == 2033
    assert best.candidate.move1.acquisition_year == 2036
    # A full grid over two 21-year windows is 441 points.
    assert len(calls) < 441


def test_keep_collapses_the_sale_axis():
    calls = []
    generate_move1_candidates_narrowed(
        locations1=LOCS, move1_window=MoveWindow(2030, 2050),
        sale_window=SaleWindow(2030, 2050), dispositions=('keep',),
        move1_action='rent', no_dual_ownership=False, score_fn=_scorer(calls),
    )
    assert calls
    assert all(c.original_home.sale_year is None for c in calls)


def test_infeasible_points_are_skipped_not_scored_as_zero():
    """A constraint rejection must not read as a very bad score, or the search
    will hill-climb away from a feasible region it has not explored yet."""
    def score(cand):
        if cand.move1.acquisition_year < 2040:
            return None
        return ScoredCandidate(candidate=cand, net_worth=1.0, lifetime_cost=1.0,
                               mc_success_rate=None, sec121_exclusion_lost=[False])

    out = generate_move1_candidates_narrowed(
        locations1=LOCS, move1_window=MoveWindow(2030, 2050),
        sale_window=SaleWindow(2030, 2050), dispositions=('sell',),
        move1_action='buy', no_dual_ownership=False, score_fn=score,
    )
    assert out
    assert all(s.candidate.move1.acquisition_year >= 2040 for s in out)


def test_move2_narrowed_respects_its_own_window_and_the_ordering_rule():
    calls = []
    anchors = generate_move1_candidates_narrowed(
        locations1=LOCS, move1_window=MoveWindow(2035, 2035),
        sale_window=SaleWindow(2033, 2033), dispositions=('sell',),
        move1_action='buy', no_dual_ownership=False, score_fn=_scorer(calls),
    )
    out = generate_move2_candidates_narrowed(
        [s.candidate for s in anchors], locations2=LOCS,
        move2_window=MoveWindow(2030, 2045), move2_action='buy',
        concurrent=False, no_dual_ownership=False, score_fn=_scorer([]),
    )
    assert out
    assert all(s.candidate.move2.acquisition_year > 2035 for s in out)


def test_an_all_infeasible_search_returns_empty_rather_than_looping():
    out = generate_move1_candidates_narrowed(
        locations1=LOCS, move1_window=MoveWindow(2030, 2040),
        sale_window=SaleWindow(2030, 2040), dispositions=('sell',),
        move1_action='buy', no_dual_ownership=False, score_fn=lambda c: None,
    )
    assert out == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_housing_coordinate_descent_unit.py -v`
Expected: FAIL — the new keyword-only signature does not exist.

- [ ] **Step 3: Rewrite the search**

Replace `_coordinate_search_2d` (`:38-93`), `_coordinate_search_1d` (`:96-137`),
`_score_move1_point` (`:144-165`), `generate_move1_candidates_narrowed` (`:168-199`),
`_score_move2_point` (`:202-226`) and `generate_move2_candidates_narrowed` (`:229-259`)
with one N-dimensional descent plus two thin wrappers:

```python
from __future__ import annotations

from itertools import product
from typing import Callable

from .candidates import dual_ownership_ok
from .models import (
    HousingCandidate,
    Location,
    Move,
    MoveWindow,
    NARROWED_MAX_EVALS_PER_AXIS,
    OriginalHome,
    SaleWindow,
    ScoredCandidate,
)

ScoreFn = Callable[[HousingCandidate], "ScoredCandidate | None"]


def _descend(axes, build, score_fn, max_evals):
    """Seed at each axis corner plus the centre, then hill-climb one axis at a
    time until no single-step neighbour improves.

    ``axes`` is a list of ``range`` objects; ``build(point)`` turns a tuple of
    axis values into a candidate. A point whose ``score_fn`` returns ``None``
    is infeasible: it is recorded as visited so it is never re-scored, but it
    never becomes the incumbent. Treating it as a very low score instead would
    push the climb away from a feasible region it has not reached yet.
    """
    seen: dict[tuple[int, ...], ScoredCandidate | None] = {}
    results: list[ScoredCandidate] = []

    def evaluate(point):
        if point in seen:
            return seen[point]
        if len(seen) >= max_evals:
            return None
        scored = score_fn(build(point))
        seen[point] = scored
        if scored is not None:
            results.append(scored)
        return scored

    corners = [tuple(v) for v in product(*[(a[0], a[-1]) for a in axes])]
    centre = tuple(a[len(a) // 2] for a in axes)
    incumbent, incumbent_score = None, None
    for seed in list(dict.fromkeys(corners + [centre])):
        scored = evaluate(seed)
        if scored is not None and (incumbent_score is None or scored.net_worth > incumbent_score):
            incumbent, incumbent_score = seed, scored.net_worth

    while incumbent is not None and len(seen) < max_evals:
        improved = False
        for i, axis in enumerate(axes):
            for delta in (-1, 1):
                nxt = list(incumbent)
                nxt[i] += delta
                if nxt[i] < axis[0] or nxt[i] > axis[-1]:
                    continue
                scored = evaluate(tuple(nxt))
                if scored is not None and scored.net_worth > incumbent_score:
                    incumbent, incumbent_score, improved = tuple(nxt), scored.net_worth, True
        if not improved:
            break
    return results


def _axes_for_move1(sale_window, move1_window, disposition):
    axes = [range(move1_window.earliest_acquisition_year,
                  move1_window.latest_acquisition_year + 1)]
    if disposition != 'keep':
        axes.insert(0, range(sale_window.earliest_sale_year,
                             sale_window.latest_sale_year + 1))
    return axes


def generate_move1_candidates_narrowed(
    *, locations1: list[Location], move1_window: MoveWindow, sale_window: SaleWindow,
    dispositions: tuple[str, ...], move1_action: str, no_dual_ownership: bool,
    score_fn: ScoreFn, max_evals: int = NARROWED_MAX_EVALS_PER_AXIS * 2,
) -> list[ScoredCandidate]:
    actions = ('buy', 'rent') if move1_action == 'auto' else (move1_action,)
    out: list[ScoredCandidate] = []
    for disposition in dispositions:
        axes = _axes_for_move1(sale_window, move1_window, disposition)
        keep = disposition == 'keep'
        for loc in locations1:
            for action in actions:
                def build(point, _loc=loc, _action=action, _keep=keep, _d=disposition):
                    sale_year = None if _keep else point[0]
                    year = point[0] if _keep else point[1]
                    return HousingCandidate(
                        original_home=OriginalHome(disposition=_d, sale_year=sale_year),
                        moves=(Move(index=1, acquisition_year=year,
                                    action=_action, location=_loc),),
                    )

                def guarded(cand, _fn=score_fn):
                    if no_dual_ownership and not dual_ownership_ok(cand):
                        return None
                    return _fn(cand)

                out.extend(_descend(axes, build, guarded, max_evals))
    return out


def generate_move2_candidates_narrowed(
    anchors: list[HousingCandidate], *, locations2: list[Location],
    move2_window: MoveWindow, move2_action: str, concurrent: bool,
    no_dual_ownership: bool, score_fn: ScoreFn,
    max_evals: int = NARROWED_MAX_EVALS_PER_AXIS,
) -> list[ScoredCandidate]:
    actions = ('buy', 'rent') if move2_action == 'auto' else (move2_action,)
    mode = 'concurrent' if concurrent else 'sequential'
    out: list[ScoredCandidate] = []
    axis = range(move2_window.earliest_acquisition_year,
                 move2_window.latest_acquisition_year + 1)
    for anchor in anchors:
        for loc in locations2:
            for action in actions:
                def build(point, _a=anchor, _loc=loc, _action=action):
                    return HousingCandidate(
                        original_home=_a.original_home,
                        moves=_a.moves + (Move(index=2, acquisition_year=point[0],
                                               action=_action, location=_loc, mode=mode),),
                        anchor_of=_a,
                    )

                def guarded(cand, _fn=score_fn, _a=anchor):
                    if not concurrent and cand.move2.acquisition_year <= _a.move1.acquisition_year:
                        return None
                    if no_dual_ownership and not concurrent and not dual_ownership_ok(cand):
                        return None
                    return _fn(cand)

                out.extend(_descend([axis], build, guarded, max_evals))
    return out
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_housing_coordinate_descent_unit.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/housing/search.py tests/test_housing_coordinate_descent_unit.py
git commit -m "feat(housing): coordinate descent over sale and acquisition axes

Replaces the 2D-plus-rent-branch search. Rent is an action now, not a missing
year, so the separate 1D branch is gone. Infeasible points are skipped rather
than scored, so a constraint rejection cannot steer the climb."
```

---

### Task 5: Area-type and population funnel stages

**Files:**
- Modify: `src/housing/zip_screen/screen.py:29-62` (`ScreenRequest`, `ScreenedZip`), `:150-218` (`run_screen`), `:129-147` (`_relaxation`)
- Test: `tests/test_zip_screen_filters.py` (create)

**Interfaces:**
- Consumes: `city_type_for_density` (`src/housing/zip_screen/resolve.py:22`).
- Produces: `ScreenRequest.area_type: str = 'any'`, `ScreenRequest.max_population: int | None = None`;
  `ScreenedZip.area_type: str`, `ScreenedZip.population: int`; funnel keys
  `matching_area_type`, `under_population_cap`; `_relaxation(...) -> dict | None` gaining a
  `stage` key naming what emptied the funnel.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_zip_screen_filters.py
"""Area-type and population funnel stages (design 2026-09-16 §6.2)."""
import pytest

from src.housing.zip_screen.schema import ZipRecord
from src.housing.zip_screen.screen import ScreenRequest, run_screen

pytestmark = pytest.mark.unit


def _rec(zcta, *, lat=39.7, lon=-104.9, density_pop=100000, land=10.0,
         place_pop=100000, state='Colorado'):
    """A record dense enough to clear the coverage floor on every percentile."""
    return ZipRecord(
        zcta=zcta, state=state, state_abbrev='CO', primary_place=f'Place{zcta}',
        place_population=place_pop, zcta_population=density_pop, land_area_sqmi=land,
        lat=lat, lon=lon, median_home_value=400000, state_median_home_value=400000,
        upi=0.02,
        pctl_owner_occupied=80, pctl_poverty=80, pctl_non_student_poverty=80,
        pctl_tenure=80, pctl_tenure_nonstudent=80, pctl_vacancy_deviation=80,
        pctl_eviction_execution=None, pctl_eviction_filing=None, pctl_median_income=80,
    )


def _table():
    # 40000/10 = 4000 ppsm -> urban;  5000/10 = 500 ppsm -> exurban
    return {
        '80001': _rec('80001', density_pop=40000, place_pop=500000),
        '80002': _rec('80002', lat=39.75, density_pop=5000, place_pop=9000),
    }


def _req(**kw):
    kw.setdefault('anchor_zip', '80001')
    kw.setdefault('radius_miles', 25)
    kw.setdefault('min_quality_score', 0)
    kw.setdefault('shortlist_size', 5)
    kw.setdefault('property_spec', {})
    kw.setdefault('area_type', 'any')
    kw.setdefault('max_population', None)
    return ScreenRequest(**kw)


def test_funnel_reports_every_stage_in_order():
    result = run_screen(_req(), table=_table())
    assert list(result.funnel) == [
        'in_radius', 'with_data', 'above_score', 'matching_area_type',
        'under_population_cap', 'affordable', 'distinct', 'near_family', 'promoted',
    ]


def test_area_type_any_filters_nothing_but_still_appears_in_the_funnel():
    result = run_screen(_req(area_type='any'), table=_table())
    assert result.funnel['matching_area_type'] == result.funnel['above_score']


def test_area_type_filters_to_the_matching_density_bucket():
    result = run_screen(_req(area_type='exurban'), table=_table())
    assert [z.zcta for z in result.shortlist] == ['80002']
    assert result.funnel['matching_area_type'] == 1


def test_population_cap_is_a_maximum_with_no_minimum():
    result = run_screen(_req(max_population=10000), table=_table())
    assert [z.zcta for z in result.shortlist] == ['80002']
    assert result.funnel['under_population_cap'] == 1


def test_no_population_cap_keeps_everything():
    result = run_screen(_req(max_population=None), table=_table())
    assert result.funnel['under_population_cap'] == result.funnel['matching_area_type']


def test_screened_zip_carries_area_type_and_population_for_display():
    z = next(z for z in run_screen(_req(), table=_table()).shortlist if z.zcta == '80002')
    assert z.area_type == 'exurban'
    assert z.population == 9000


def test_relaxation_names_the_stage_that_emptied_the_funnel():
    result = run_screen(_req(area_type='rural'), table=_table())
    assert result.shortlist == []
    assert result.relaxation['stage'] == 'matching_area_type'
    assert result.relaxation['field'] == 'area_type'


def test_relaxation_still_names_the_score_floor_when_that_is_the_cause():
    result = run_screen(_req(min_quality_score=99.9), table=_table())
    assert result.shortlist == []
    assert result.relaxation['stage'] == 'above_score'
    assert result.relaxation['field'] == 'min_quality_score'
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_zip_screen_filters.py -v`
Expected: FAIL — `ScreenRequest` has no `area_type` field.

- [ ] **Step 3: Extend the request and result types**

`src/housing/zip_screen/screen.py`, in `ScreenRequest` (`:29-35`) after `property_spec`:

```python
    area_type: str = 'any'
    max_population: int | None = None
```

In `ScreenedZip` (`:38-52`) after `est_price`:

```python
    area_type: str = 'suburban'
    population: int = 0
```

Add the import at the top of the file:

```python
from .resolve import city_type_for_density
```

- [ ] **Step 4: Add the two stages to `run_screen`**

Between `funnel['above_score']` (`:178`) and the `passing` loop (`:180`):

```python
    area_type = str(req.area_type or 'any').strip().lower()
    if area_type in ('', 'any'):
        matching_area = above_score
    else:
        matching_area = [t for t in above_score
                         if city_type_for_density(t[0].density) == area_type]
    funnel['matching_area_type'] = len(matching_area)

    cap = req.max_population
    if cap is None:
        under_cap = matching_area
    else:
        under_cap = [t for t in matching_area
                     if (t[0].place_population or t[0].zcta_population or 0) <= int(cap)]
    funnel['under_population_cap'] = len(under_cap)
```

Change the `passing` loop at `:181` to iterate `under_cap` instead of `above_score`, and
add the two new fields to the `ScreenedZip(...)` construction after `est_price=`:

```python
            area_type=city_type_for_density(rec.density),
            population=rec.place_population or rec.zcta_population or 0,
```

Rename the `after_dedup` funnel key to `distinct` at `:202` and add a placeholder
`near_family` stage immediately after it, which Task 7 fills in:

```python
    funnel['distinct'] = len(passing)
    funnel['near_family'] = len(passing)
```

Also update `coords` at `:200` to build from `under_cap` rather than `above_score`, so a
ZIP filtered out by the new stages cannot reappear as a dedup reference point.

- [ ] **Step 5: Make `_relaxation` name the stage**

Replace `_relaxation` (`:129-147`) with:

```python
def _relaxation(stages: dict[str, list], min_quality_score: float,
                area_type: str, max_population: int | None) -> dict[str, Any] | None:
    """What would the user have to give up to get results?

    A bare "no results" on a nine-stage funnel is unusable: the user cannot
    tell which constraint emptied it. Report the FIRST stage that went to zero
    while its predecessor had survivors -- that is the binding constraint, and
    relaxing anything later would change nothing.
    """
    with_data = stages['with_data']
    if not with_data:
        return None

    scores = sorted((t[2].score for t in with_data), reverse=True)
    if not stages['above_score']:
        suggested = math.floor(scores[0] * 10) / 10
        return {'stage': 'above_score', 'field': 'min_quality_score',
                'current': min_quality_score, 'suggested': suggested,
                'would_return': sum(1 for s in scores if s >= suggested)}

    if not stages['matching_area_type']:
        available = sorted({city_type_for_density(t[0].density)
                            for t in stages['above_score']})
        return {'stage': 'matching_area_type', 'field': 'area_type',
                'current': area_type, 'suggested': available[0] if available else 'any',
                'would_return': len(stages['above_score'])}

    if not stages['under_population_cap']:
        pops = sorted((t[0].place_population or t[0].zcta_population or 0)
                      for t in stages['matching_area_type'])
        return {'stage': 'under_population_cap', 'field': 'max_population',
                'current': max_population, 'suggested': pops[0],
                'would_return': sum(1 for p in pops if p <= pops[0])}

    if not stages['affordable']:
        return {'stage': 'affordable', 'field': 'target_purchase_price_range',
                'current': None, 'suggested': None,
                'would_return': len(stages['under_population_cap'])}
    return None
```

Update the call site at `:217` to pass the stage lists:

```python
        relaxation=_relaxation(
            {'with_data': with_data, 'above_score': above_score,
             'matching_area_type': matching_area, 'under_population_cap': under_cap,
             'affordable': affordable_passing},
            req.min_quality_score, area_type, req.max_population,
        ) if not shortlist else None,
```

Capture `affordable_passing = list(passing)` immediately after `funnel['affordable']` is
set, before `deduplicate` reassigns `passing`.

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_zip_screen_filters.py -v`
Expected: 8 passed

Run: `pytest tests/ -k zip_screen -q`
Expected: failures only in tests asserting the old `after_dedup` funnel key. Update those
assertions to `distinct` — the rename is deliberate (§6.2).

- [ ] **Step 7: Commit**

```bash
git add src/housing/zip_screen/screen.py tests/
git commit -m "feat(zip-screen): filter candidates on area type and a population cap

Relaxation hints now name the binding stage instead of always blaming the
score floor."
```

---

### Task 6: Multi-anchor screening

**Files:**
- Modify: `src/housing/zip_screen/screen.py` (add `run_multi_anchor_screen`)
- Test: `tests/test_housing_multi_anchor_screen.py` (create)

**Interfaces:**
- Consumes: Task 5's `run_screen`, `ScreenRequest`, `ScreenResult`.
- Produces: `MultiAnchorRequest(anchor_zips: list[str], radius_miles, min_quality_score, shortlist_size, property_spec, area_type, max_population)`
  and `run_multi_anchor_screen(req, table=None, current_state='') -> ScreenResult`, whose
  `ScreenResult` gains `anchors: list[dict]` and whose `ScreenedZip` gains
  `nearest_anchor_zip: str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_housing_multi_anchor_screen.py
"""Union-then-dedup across 2-5 anchors (design 2026-09-16 §6.1)."""
import pytest

from src.housing.zip_screen.screen import MultiAnchorRequest, run_multi_anchor_screen
from tests.test_zip_screen_filters import _rec

pytestmark = pytest.mark.unit


def _table():
    return {
        # Two anchors ~35 miles apart, with one ZIP sitting between them.
        '80001': _rec('80001', lat=39.70, lon=-104.90, place_pop=500000),
        '80002': _rec('80002', lat=39.75, lon=-104.90, place_pop=40000),
        '90001': _rec('90001', lat=40.20, lon=-104.90, place_pop=60000),
    }


def _req(**kw):
    kw.setdefault('anchor_zips', ['80001', '90001'])
    kw.setdefault('radius_miles', 50)
    kw.setdefault('min_quality_score', 0)
    kw.setdefault('shortlist_size', 5)
    kw.setdefault('property_spec', {})
    kw.setdefault('area_type', 'any')
    kw.setdefault('max_population', None)
    return MultiAnchorRequest(**kw)


def test_a_zip_in_both_radii_appears_exactly_once():
    result = run_multi_anchor_screen(_req(), table=_table())
    zctas = [z.zcta for z in result.shortlist]
    assert len(zctas) == len(set(zctas))


def test_distance_is_measured_to_the_nearest_anchor():
    result = run_multi_anchor_screen(_req(), table=_table())
    z = next(z for z in result.shortlist if z.zcta == '80002')
    assert z.nearest_anchor_zip == '80001'
    assert z.distance_miles < 10


def test_every_anchor_is_reported_for_display():
    result = run_multi_anchor_screen(_req(), table=_table())
    assert [a['zip'] for a in result.anchors] == ['80001', '90001']


def test_funnel_counts_the_union_not_the_sum_of_per_anchor_runs():
    """Summing per-anchor funnels would double-count the overlap and make the
    displayed 'N ZIPs in range' larger than the number of distinct ZIPs."""
    result = run_multi_anchor_screen(_req(), table=_table())
    assert result.funnel['in_radius'] == 3


def test_a_single_anchor_behaves_exactly_like_the_one_anchor_screen():
    result = run_multi_anchor_screen(_req(anchor_zips=['80001'], radius_miles=25),
                                     table=_table())
    assert result.anchors[0]['zip'] == '80001'
    assert all(z.nearest_anchor_zip == '80001' for z in result.shortlist)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_housing_multi_anchor_screen.py -v`
Expected: FAIL with `ImportError: cannot import name 'MultiAnchorRequest'`

- [ ] **Step 3: Add the multi-anchor request and the union**

Append to `src/housing/zip_screen/screen.py`. Add `nearest_anchor_zip: str = ''` to
`ScreenedZip` and `anchors: list[dict[str, Any]] = field(default_factory=list)` to
`ScreenResult` first, then:

```python
@dataclass(frozen=True)
class MultiAnchorRequest:
    anchor_zips: list[str]
    radius_miles: int
    min_quality_score: float
    shortlist_size: int
    property_spec: dict[str, Any]
    area_type: str = 'any'
    max_population: int | None = None


def run_multi_anchor_screen(
    req: MultiAnchorRequest, table: dict[str, ZipRecord] | None = None,
    current_state: str = '',
) -> ScreenResult:
    """Screen each anchor, then union before dedup and promotion.

    Unioning first is what makes two overlapping metros behave like one
    search: dedup and the shortlist cap both then operate on distinct ZIPs, so
    a ZIP in both radii cannot occupy two shortlist slots and the funnel counts
    ZIPs rather than (ZIP, anchor) pairs.
    """
    data = table if table is not None else load_table()
    per_anchor: list[ScreenResult] = []
    for zip_code in req.anchor_zips:
        per_anchor.append(run_screen(
            ScreenRequest(
                anchor_zip=zip_code, radius_miles=req.radius_miles,
                min_quality_score=req.min_quality_score,
                shortlist_size=len(data),          # no per-anchor truncation
                property_spec=req.property_spec,
                area_type=req.area_type, max_population=req.max_population,
            ),
            table=data, current_state=current_state,
        ))

    best: dict[str, ScreenedZip] = {}
    for anchor_result, zip_code in zip(per_anchor, req.anchor_zips):
        for z in anchor_result.all_passing:
            tagged = ScreenedZip(**{**z.__dict__, 'nearest_anchor_zip': zip_code,
                                    'promoted': False})
            prior = best.get(z.zcta)
            if prior is None or tagged.distance_miles < prior.distance_miles:
                best[z.zcta] = tagged

    funnel = {k: 0 for k in per_anchor[0].funnel} if per_anchor else {}
    for key in funnel:
        seen: set[str] = set()
        for anchor_result in per_anchor:
            seen |= set(anchor_result.stage_zctas.get(key, ()))
        funnel[key] = len(seen)

    union = sorted(best.values(), key=lambda z: (-z.nss, z.distance_miles, z.zcta))
    coords = {z.zcta: (data[z.zcta].lat, data[z.zcta].lon) for z in union}
    distinct = deduplicate(union, coords)
    funnel['distinct'] = len(distinct)
    funnel['near_family'] = len(distinct)

    shortlist = [ScreenedZip(**{**z.__dict__, 'promoted': True})
                 for z in distinct[: max(0, int(req.shortlist_size))]]
    funnel['promoted'] = len(shortlist)

    return ScreenResult(
        anchor=per_anchor[0].anchor if per_anchor else {},
        anchors=[r.anchor for r in per_anchor],
        radius_miles=req.radius_miles,
        funnel=funnel,
        shortlist=shortlist,
        all_passing=distinct,
        relaxation=next((r.relaxation for r in per_anchor if r.relaxation), None)
        if not shortlist else None,
    )
```

- [ ] **Step 4: Record per-stage ZCTAs in `run_screen` so the union can count them**

The union funnel needs to know *which* ZIPs survived each stage, not just how many, or
overlapping anchors double-count. Add `stage_zctas: dict[str, list[str]] = field(default_factory=dict)`
to `ScreenResult` and populate it in `run_screen` alongside each `funnel[...]` assignment:

```python
    stage_zctas = {
        'in_radius': [r.zcta for r, _ in in_radius],
        'with_data': [t[0].zcta for t in with_data],
        'above_score': [t[0].zcta for t in above_score],
        'matching_area_type': [t[0].zcta for t in matching_area],
        'under_population_cap': [t[0].zcta for t in under_cap],
        'affordable': [z.zcta for z in affordable_passing],
        'distinct': [z.zcta for z in passing],
        'near_family': [z.zcta for z in passing],
        'promoted': [z.zcta for z in shortlist],
    }
```

and pass `stage_zctas=stage_zctas` to the returned `ScreenResult`.

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_housing_multi_anchor_screen.py tests/test_zip_screen_filters.py -v`
Expected: 13 passed

- [ ] **Step 6: Commit**

```bash
git add src/housing/zip_screen/screen.py tests/test_housing_multi_anchor_screen.py
git commit -m "feat(zip-screen): union 2-5 anchors before dedup and promotion

Distance resolves to the nearest anchor and the funnel counts distinct ZIPs,
so overlapping metros do not double-count or occupy two shortlist slots."
```

---

### Task 7: Family presence as a ZIP-radius filter

**Files:**
- Rewrite: `src/housing/constraints.py`
- Modify: `src/housing/zip_screen/screen.py` (fill in the `near_family` stage)
- Test: `tests/test_housing_family_presence_radius.py` (create)

**Interfaces:**
- Consumes: `haversine_miles` (`src/housing/zip_screen/geo.py:21`), Task 2's `FamilyPresence`.
- Produces:
  - `residence_timeline(base_state, cand) -> list[tuple[int, int, Location | None, bool]]`
  - `family_presence_ok(cand, presence, coords) -> tuple[bool, bool]` where
    `coords: dict[str, tuple[float, float]]` maps ZIP → (lat, lon) and the second element
    is `via_rental`
  - `annotate_family_distance(shortlist, family_zip, coords) -> list[ScreenedZip]` setting
    `ScreenedZip.family_distance_miles`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_housing_family_presence_radius.py
"""Family presence as ZIP proximity, not state residence (design §6.4)."""
import pytest

from src.housing.constraints import family_presence_ok
from src.housing.models import (
    FamilyPresence,
    HousingCandidate,
    Location,
    Move,
    OriginalHome,
)

pytestmark = pytest.mark.unit

# 60521 Hinsdale IL; 60540 Naperville ~9 mi west; 80014 Aurora CO ~1000 mi west.
COORDS = {
    '60521': (41.80, -87.93),
    '60540': (41.77, -88.15),
    '80014': (39.68, -104.83),
}


def _cand(zip1, year1=2030, action1='buy', zip2=None, year2=None,
          action2='buy', mode2='sequential'):
    moves = [Move(index=1, acquisition_year=year1, action=action1,
                  location=Location(state='IL', zip_code=zip1))]
    if zip2:
        moves.append(Move(index=2, acquisition_year=year2, action=action2,
                          location=Location(state='CO', zip_code=zip2), mode=mode2))
    return HousingCandidate(
        original_home=OriginalHome(disposition='sell', sale_year=2029),
        moves=tuple(moves),
    )


def _presence(radius=25, from_year=2030, through_year=2040):
    return FamilyPresence(zip_code='60521', radius_miles=radius,
                          from_year=from_year, through_year=through_year)


def test_a_nearby_zip_satisfies_presence():
    ok, _ = family_presence_ok(_cand('60540'), _presence(radius=25), COORDS)
    assert ok is True


def test_a_distant_zip_fails_presence():
    ok, _ = family_presence_ok(_cand('80014'), _presence(radius=25), COORDS)
    assert ok is False


def test_the_radius_is_what_decides_not_the_state():
    """60540 is in the same state as the family ZIP but must still be inside
    the radius -- the old state-level rule would have passed it at any
    distance."""
    ok, _ = family_presence_ok(_cand('60540'), _presence(radius=5), COORDS)
    assert ok is False


def test_presence_is_only_checked_inside_the_declared_years():
    cand = _cand('80014', year1=2045)
    ok, _ = family_presence_ok(cand, _presence(from_year=2030, through_year=2040), COORDS)
    assert ok is True, 'the household is still at its original home through 2040'


def test_moving_away_mid_window_fails():
    cand = _cand('60540', year1=2030, zip2='80014', year2=2035)
    ok, _ = family_presence_ok(cand, _presence(from_year=2030, through_year=2040), COORDS)
    assert ok is False


def test_a_concurrent_second_residence_satisfies_presence():
    cand = _cand('80014', year1=2030, zip2='60540', year2=2030, mode2='concurrent')
    ok, _ = family_presence_ok(cand, _presence(), COORDS)
    assert ok is True


def test_via_rental_is_reported_when_a_rental_is_what_covers_the_window():
    cand = _cand('60540', action1='rent')
    ok, via_rental = family_presence_ok(cand, _presence(), COORDS)
    assert ok is True
    assert via_rental is True


def test_no_presence_requirement_passes_everything():
    ok, via_rental = family_presence_ok(_cand('80014'), None, COORDS)
    assert (ok, via_rental) == (True, False)


def test_an_unknown_zip_fails_closed_rather_than_passing_silently():
    """A ZIP missing from the coordinate table cannot be shown to be near
    family, and passing it would let an unscreened candidate through a filter
    the user asked for."""
    ok, _ = family_presence_ok(_cand('99999'), _presence(), COORDS)
    assert ok is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_housing_family_presence_radius.py -v`
Expected: FAIL — `family_presence_ok` still takes `(base_state, cand, presence)`.

- [ ] **Step 3: Rewrite `constraints.py`**

```python
"""Hard filters applied to a candidate before it is ever run, plus the
informational §121 flag. Pure functions over a candidate -- no engine, no
config.

Family presence became ZIP proximity on 2026-09-16 (design §6.4). The previous
state-level rule passed any candidate in the right state regardless of
distance, which is not what "near family" means in a state the size of Texas.
"""
from __future__ import annotations

from .models import FamilyPresence, HousingCandidate, Location
from .zip_screen.geo import haversine_miles


def residence_timeline(base_state: str, cand: HousingCandidate):
    """Ordered ``(start_year, end_year_inclusive, location, is_rental)`` legs
    covering the plan horizon for the PRIMARY residence.

    ``location`` is ``None`` for the opening leg: the household is still at its
    current home, whose ZIP the optimizer does not model. A concurrent move 2
    is excluded here and checked separately -- it is a second simultaneous
    residence, not a relocation.
    """
    m1 = cand.move1
    legs = [(1, m1.acquisition_year - 1, None, False)]
    m2 = cand.move2
    if m2 is not None and m2.mode != 'concurrent':
        legs.append((m1.acquisition_year, m2.acquisition_year - 1,
                     m1.location, m1.action == 'rent'))
        legs.append((m2.acquisition_year, 9999, m2.location, m2.action == 'rent'))
    else:
        legs.append((m1.acquisition_year, 9999, m1.location, m1.action == 'rent'))
    return legs


def _within(loc: Location | None, presence: FamilyPresence,
            coords: dict[str, tuple[float, float]]) -> bool:
    if loc is None:
        # Still at the current home. The plan's existing residence is taken to
        # satisfy presence: the user is asking where they should MOVE to stay
        # near family, not whether they live there now.
        return True
    family = coords.get(presence.zip_code)
    here = coords.get(loc.zip_code or '')
    if family is None or here is None:
        return False
    return haversine_miles(family[0], family[1], here[0], here[1]) <= presence.radius_miles


def family_presence_ok(
    cand: HousingCandidate, presence: FamilyPresence | None,
    coords: dict[str, tuple[float, float]],
) -> tuple[bool, bool]:
    """Returns ``(covered, via_rental)``.

    ``covered`` is False if, in any year of the presence window, the household's
    residence is farther from the family ZIP than the radius. A concurrent
    second residence satisfies a year on its own -- representing presence in
    two places at once is the point of concurrent mode.
    """
    if presence is None:
        return True, False
    legs = residence_timeline('', cand)
    m2 = cand.move2
    concurrent = m2 is not None and m2.mode == 'concurrent'
    via_rental = False
    for year in range(presence.from_year, presence.through_year + 1):
        leg = next((l for l in legs if l[0] <= year <= l[1]), None)
        primary_match = leg is not None and _within(leg[2], presence, coords)
        primary_rental = bool(leg and leg[3])
        concurrent_match = (
            concurrent and year >= m2.acquisition_year
            and _within(m2.location, presence, coords)
        )
        if not (primary_match or concurrent_match):
            return False, False
        if (primary_match and primary_rental) or (concurrent_match and m2.action == 'rent'):
            via_rental = True
    return True, via_rental


def sec121_exclusion_flag(acquisition_year: int | None, sale_year: int | None) -> bool:
    """Informational-only two-of-five-year ownership/use flag: True means the
    exclusion would likely NOT survive the real IRS test, even though the
    engine's computed dollar figures still assume it applies in full.
    """
    if acquisition_year is None or sale_year is None:
        return False
    return (sale_year - acquisition_year) < 2
```

- [ ] **Step 4: Fill in the `near_family` screening stage**

In `src/housing/zip_screen/screen.py`, add `family_distance_miles: float | None = None`
to `ScreenedZip`, then add beside `deduplicate`:

```python
def annotate_family_distance(shortlist, family_zip, coords):
    """Record each ZIP's distance to the family ZIP for display.

    An empty result under a tight family radius is otherwise undiagnosable:
    the user sees zero candidates with no indication of how close the search
    came.
    """
    family = coords.get(family_zip) if family_zip else None
    if family is None:
        return list(shortlist)
    out = []
    for z in shortlist:
        here = coords.get(z.zcta)
        dist = None if here is None else round(
            haversine_miles(family[0], family[1], here[0], here[1]), 2)
        out.append(ScreenedZip(**{**z.__dict__, 'family_distance_miles': dist}))
    return out
```

Task 9 calls this from the optimizer, where the family ZIP is known.

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_housing_family_presence_radius.py -v`
Expected: 9 passed

- [ ] **Step 6: Commit**

```bash
git add src/housing/constraints.py src/housing/zip_screen/screen.py \
        tests/test_housing_family_presence_radius.py
git commit -m "feat(housing): family presence becomes a ZIP-radius filter

Replaces the state-level rule, which passed any candidate in the right state
regardless of distance. Unknown ZIPs fail closed."
```

---

### Task 8: v2 result payload

**Files:**
- Rewrite: `src/housing/results.py`
- Test: `tests/test_housing_results_v2.py` (create)

**Interfaces:**
- Consumes: Task 2's `ScoredCandidate`.
- Produces: `format_output(ranked, *, objective, search_mode, move2_strategy, zip_screens, rejections, message=None) -> dict`,
  emitting `schema='housing_optimize_v2'`, a `candidates` list, and `recommendation` as an
  alias of `candidates[0]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_housing_results_v2.py
"""housing_optimize_v2 payload shape (design 2026-09-16 §7.2)."""
import pytest

from src.housing.models import (
    HousingCandidate,
    Location,
    Move,
    OriginalHome,
    ScoredCandidate,
)
from src.housing.results import format_output

pytestmark = pytest.mark.contract


def _scored(nw=1000.0, sale_year=2032, zip1='80024', two_move=False):
    moves = [Move(index=1, acquisition_year=2033, action='buy',
                  location=Location(state='CO', zip_code=zip1))]
    if two_move:
        moves.append(Move(index=2, acquisition_year=2041, action='rent',
                          location=Location(state='AZ', zip_code='85001')))
    return ScoredCandidate(
        candidate=HousingCandidate(
            original_home=OriginalHome(disposition='sell', sale_year=sale_year),
            moves=tuple(moves)),
        net_worth=nw, lifetime_cost=500.0, mc_success_rate=0.91,
        sec121_exclusion_lost=[False, False], notes=['family presence via rental'],
    )


def _out(ranked, **kw):
    kw.setdefault('objective', 'net_worth')
    kw.setdefault('search_mode', 'full')
    kw.setdefault('move2_strategy', 'anchored')
    kw.setdefault('zip_screens', {})
    kw.setdefault('rejections', {})
    return format_output(ranked, **kw)


def test_schema_is_v2():
    assert _out([_scored()])['schema'] == 'housing_optimize_v2'


def test_candidates_is_the_single_ranked_list_and_recommendation_aliases_its_head():
    out = _out([_scored(nw=2000.0), _scored(nw=1000.0)])
    assert [c['rank'] for c in out['candidates']] == [1, 2]
    assert out['recommendation'] == out['candidates'][0]
    assert 'alternatives' not in out


def test_each_move_carries_the_detail_needed_to_act_on_it():
    """The v1 payload dropped ZIP, price and distance, so a recommendation
    could not be acted on without a second lookup."""
    move = _out([_scored()])['candidates'][0]['moves'][0]
    assert move['acquisition_year'] == 2033
    assert move['action'] == 'buy'
    assert move['location']['zip_code'] == '80024'
    for key in ('est_price', 'distance_miles', 'area_type', 'population', 'nss'):
        assert key in move['location'], f'{key} missing from the move location'


def test_original_home_is_reported_separately_from_the_moves():
    out = _out([_scored()])['candidates'][0]
    assert out['original_home'] == {'disposition': 'sell', 'sale_year': 2032}


def test_a_kept_home_reports_a_null_sale_year():
    sc = _scored()
    sc.candidate.original_home = OriginalHome(disposition='keep', sale_year=None)
    out = _out([sc])['candidates'][0]
    assert out['original_home'] == {'disposition': 'keep', 'sale_year': None}


def test_notes_is_a_list_of_strings():
    assert _out([_scored()])['candidates'][0]['notes'] == ['family presence via rental']


def test_a_second_move_is_included_when_present():
    moves = _out([_scored(two_move=True)])['candidates'][0]['moves']
    assert len(moves) == 2
    assert moves[1]['action'] == 'rent'


def test_an_empty_run_reports_rejections_rather_than_a_bare_null():
    out = _out([], rejections={'dual_ownership': 40, 'family_presence': 12})
    assert out['recommendation'] is None
    assert out['candidates'] == []
    assert out['rejections']['family_presence'] == 12


def test_candidates_are_capped_at_ten():
    out = _out([_scored(nw=float(i)) for i in range(25)])
    assert len(out['candidates']) == 10
    assert out['candidates_evaluated'] == 25
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_housing_results_v2.py -v`
Expected: FAIL with `ImportError: cannot import name 'format_output'`

- [ ] **Step 3: Rewrite `results.py`**

```python
"""Shaping ranked ``ScoredCandidate``s into the ``housing_optimize_v2``
response body. Presentation only -- kept apart from ``optimizer.py`` so the
payload can be reshaped without touching the search, and from ``api.py`` so
the optimizer never imports the HTTP layer.
"""
from __future__ import annotations

from typing import Any

from .models import Location, Move, ScoredCandidate

SCHEMA = 'housing_optimize_v2'
MAX_CANDIDATES = 10


def _format_location(loc: Location) -> dict[str, Any]:
    """Every field the results table needs, so a recommendation can be acted
    on without a second lookup. The screening-derived fields are spliced onto
    the Location by api.py before this runs; they are None for a Location that
    never came from a screen."""
    return {
        'zip_code': loc.zip_code,
        'city': getattr(loc, 'city', None),
        'state': loc.state,
        'area_type': loc.city_type,
        'population': loc.population_size,
        'nss': getattr(loc, 'nss', None),
        'band': getattr(loc, 'band', None),
        'distance_miles': getattr(loc, 'distance_miles', None),
        'family_distance_miles': getattr(loc, 'family_distance_miles', None),
        'est_price': getattr(loc, 'est_price', None),
    }


def _format_move(move: Move, sec121_lost: bool) -> dict[str, Any]:
    return {
        'index': move.index,
        'acquisition_year': move.acquisition_year,
        'action': move.action,
        'mode': move.mode,
        'location': _format_location(move.location),
        'sec121_exclusion_lost': sec121_lost,
    }


def _format_candidate(sc: ScoredCandidate, objective: str, rank: int) -> dict[str, Any]:
    cand = sc.candidate
    lost = list(sc.sec121_exclusion_lost)
    return {
        'rank': rank,
        'original_home': {
            'disposition': cand.original_home.disposition,
            'sale_year': cand.original_home.sale_year,
        },
        'moves': [
            _format_move(m, lost[i] if i < len(lost) else False)
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


def format_output(
    ranked: list[ScoredCandidate], *, objective: str, search_mode: str,
    move2_strategy: str, zip_screens: dict[str, Any],
    rejections: dict[str, int], message: str | None = None,
) -> dict[str, Any]:
    """One ranked ``candidates`` list, not a recommendation plus a disjoint
    alternatives list -- v1 duplicated the rank-1 candidate across both and
    forced the frontend to render it two different ways. ``recommendation``
    remains as an alias of ``candidates[0]``.
    """
    formatted = [
        _format_candidate(sc, objective, i + 1)
        for i, sc in enumerate(ranked[:MAX_CANDIDATES])
    ]
    payload = {
        'success': True,
        'schema': SCHEMA,
        'objective': objective,
        'search_mode': search_mode,
        'move2_strategy': move2_strategy,
        'zip_screens': zip_screens,
        'recommendation': formatted[0] if formatted else None,
        'candidates': formatted,
        'candidates_evaluated': len(ranked),
        'rejections': dict(rejections),
    }
    if message:
        payload['message'] = message
    return payload
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_housing_results_v2.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/housing/results.py tests/test_housing_results_v2.py
git commit -m "feat(housing): housing_optimize_v2 payload

Moves carry ZIP, price, distance, area type and population, so a
recommendation is actionable without a second lookup. recommendation and
alternatives merge into one ranked candidates list."
```

---

### Task 9: Optimizer orchestration

**Files:**
- Modify: `src/housing/optimizer.py:43-215`
- Modify: `src/housing/plan_variant.py:16-17, 112-170`
- Modify: `src/housing/scoring.py:37-81`
- Test: `tests/test_housing_optimizer_unit.py` (update), `tests/test_housing_optimizer_integration.py` (update)

**Interfaces:**
- Consumes: Tasks 3, 4, 7, 8.
- Produces: `optimize_housing(c0, *, locations1, locations2, sale_window, move1_window, move2_window, dispositions, move1_action, move2_action, move2_concurrent, no_dual_ownership, family_presence, family_coords, anchor_count, objective, search_mode, move2_strategy, zip_screens, down_payment_pct, mortgage_rate_pct) -> dict`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_housing_optimizer_unit.py`:

```python
def test_rejection_reasons_are_tallied_for_an_empty_run(monkeypatch):
    """A zero-candidate run must say WHY. The v1 panel showed a generic
    sentence that named neither the constraint nor the field."""
    out = optimize_housing(
        _minimal_config(),
        locations1=[Location(state='CO', zip_code='80014')],
        locations2=[],
        sale_window=SaleWindow(2030, 2030),
        move1_window=MoveWindow(2029, 2029),
        move2_window=None,
        dispositions=('sell',), move1_action='buy', move2_action='auto',
        move2_concurrent=False, no_dual_ownership=True,
        family_presence=None, family_coords={}, anchor_count=5,
        objective='net_worth', search_mode='full', move2_strategy='anchored',
        zip_screens={}, down_payment_pct=0.20, mortgage_rate_pct=0.065,
    )
    assert out['candidates'] == []
    assert out['rejections']['dual_ownership'] > 0


def test_keep_leaves_home_sale_yr_at_zero():
    from src.housing.plan_variant import _apply_candidate
    cand = HousingCandidate(
        original_home=OriginalHome(disposition='keep', sale_year=None),
        moves=(Move(index=1, acquisition_year=2033, action='rent',
                    location=Location(state='AZ')),))
    c = _apply_candidate(_minimal_config(), cand,
                         down_payment_pct=0.20, mortgage_rate_pct=0.065)
    assert c['home_sale_yr'] == 0


def test_down_payment_and_rate_come_from_the_request_not_a_constant():
    from src.housing.plan_variant import _apply_candidate
    cand = HousingCandidate(
        original_home=OriginalHome(disposition='sell', sale_year=2032),
        moves=(Move(index=1, acquisition_year=2033, action='buy',
                    location=Location(state='AZ')),))
    c = _apply_candidate(_minimal_config(), cand,
                         down_payment_pct=0.35, mortgage_rate_pct=0.055)
    step = c['next_housing_steps'][0]
    assert step['down_payment'] == 0.35
    assert step['mortgage_rate_pct'] == 0.055
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_housing_optimizer_unit.py -v`
Expected: FAIL — `optimize_housing` still takes `locations`/`move1_window` positionally
with the old names.

- [ ] **Step 3: Rewire `plan_variant.py`**

Delete `_DEFAULT_DOWN_PAYMENT_PCT` (`:16-17`). Change `_apply_candidate`'s signature to
`_apply_candidate(c, cand, *, down_payment_pct, mortgage_rate_pct)` and inside it:

```python
    home = cand.original_home
    c['home_sale_yr'] = 0 if home.disposition == 'keep' else home.sale_year
```

Build each step from `Move.action` rather than from `purchase_year is None`:

```python
    steps = []
    for i, move in enumerate(cand.moves):
        if move.action == 'rent':
            steps.append(_rent_step(c, move, f'opt_move{move.index}'))
        else:
            steps.append(_purchase_step(c, move, f'opt_move{move.index}',
                                        down_payment_pct, mortgage_rate_pct))
```

`_purchase_step` and `_rent_step` take a `Move` and read `move.acquisition_year` and
`move.location`. A sequential move 2 sets the move-1 step's `end_year` to
`move2.acquisition_year - 1`, which is what triggers `apply_next_housing_sale`; a
concurrent move 2 leaves move 1's `end_year` at 0 so both run indefinitely.

- [ ] **Step 4: Rewire `scoring.py`**

`score_candidate` keeps its shape but builds `notes` instead of the
`family_presence_via_rental` boolean, and `sec121_exclusion_flag` is now called with
`(move.acquisition_year, original_home.sale_year)`:

```python
def score_candidate(c, cand, rows, *, via_rental: bool) -> ScoredCandidate:
    notes: list[str] = []
    if via_rental:
        notes.append('family presence via rental')
    sale_year = cand.original_home.sale_year
    lost = [sec121_exclusion_flag(m.acquisition_year, sale_year) for m in cand.moves]
    if any(lost):
        notes.append('likely loses §121 exclusion')
    buys = [m for m in cand.moves if m.action == 'buy' and m.mode != 'concurrent']
    if sale_year is not None and any(m.acquisition_year < sale_year for m in buys):
        first = min(m.acquisition_year for m in buys if m.acquisition_year < sale_year)
        notes.append(f'owns two homes {first}-{sale_year}')
    return ScoredCandidate(
        candidate=cand, net_worth=rows[-1]['total_nw'],
        lifetime_cost=_lifetime_cost(rows), mc_success_rate=None,
        sec121_exclusion_lost=lost, notes=notes,
    )
```

- [ ] **Step 5: Rewire `optimizer.py`**

Replace the signature and the generation calls. The tally is a plain dict incremented at
each rejection point:

```python
    rejections = {'dual_ownership': 0, 'family_presence': 0, 'move_order': 0}
```

Wrap the per-candidate scoring so a rejected candidate increments the right counter
instead of vanishing:

```python
    def score_or_reject(cand):
        if no_dual_ownership and not dual_ownership_ok(cand):
            rejections['dual_ownership'] += 1
            return None
        covered, via_rental = family_presence_ok(cand, family_presence, family_coords)
        if not covered:
            rejections['family_presence'] += 1
            return None
        rows = _run_engine(_apply_candidate(
            c0, cand, down_payment_pct=down_payment_pct,
            mortgage_rate_pct=mortgage_rate_pct))
        return score_candidate(c0, cand, rows, via_rental=via_rental)
```

Keep the existing two-pass structure (Pass 1 deterministic, Pass 2 Monte Carlo on the top
3–5, `:202-213`) and the `MOVE2_CROSS_PRODUCT_CAP` pre-flight (`:134-159`), updating the
latter to call `estimate_move2_candidate_count` with its new keyword signature. Return
`format_output(ranked, objective=..., search_mode=..., move2_strategy=...,
zip_screens=zip_screens, rejections=rejections)`.

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_housing_optimizer_unit.py tests/test_housing_optimizer_integration.py -v`
Expected: all pass. Where an existing test asserts on `alternatives` or
`family_presence_via_rental`, update it to `candidates` and `notes` — those are the
intended renames (§7.2).

- [ ] **Step 7: Commit**

```bash
git add src/housing/optimizer.py src/housing/plan_variant.py src/housing/scoring.py tests/
git commit -m "feat(housing): orchestrate the decoupled search and tally rejections

Down payment and mortgage rate come from the request instead of a hardcoded
20%, so the optimizer and the spending screen price the same house alike."
```

---

### Task 10: Request parsing and validation

**Files:**
- Rewrite: `src/housing/api.py`
- Modify: `src/api_contracts.py:130`
- Modify: `src/server/plan_routes.py:750-778`
- Test: `tests/test_housing_api_validation.py` (create)

**Interfaces:**
- Consumes: Tasks 5–9.
- Produces: `optimize_housing_from_request(c0, body, table_path=None) -> tuple[dict, int]`,
  `zip_screen_from_request(c0, body, table_path=None) -> tuple[dict, int]`,
  `parse_move_search(raw) -> MultiAnchorRequest`, `validate_request(body) -> str | None`
  returning the first violated rule's message or `None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_housing_api_validation.py
"""Server-side rejection of impossible requests (design 2026-09-16 §8)."""
import pytest

from src.housing.api import validate_request

pytestmark = pytest.mark.contract


def _body(**over):
    body = {
        'objective': 'net_worth', 'search_mode': 'full',
        'move2_strategy': 'anchored', 'no_dual_ownership': True,
        'original_home': {'disposition': 'sell',
                          'earliest_sale_year': 2030, 'latest_sale_year': 2045},
        'move1': {'earliest_acquisition_year': 2031,
                  'latest_acquisition_year': 2046, 'action': 'auto',
                  'search': {'anchors': [{'kind': 'zip', 'anchor_zip': '80014'},
                                         {'kind': 'zip', 'anchor_zip': '60521'}],
                             'radius_miles': 25, 'min_quality_score': 60,
                             'area_type': 'any', 'max_population': None,
                             'shortlist_size': 4, 'dwelling': {}}},
    }
    body.update(over)
    return body


def test_a_valid_request_passes():
    assert validate_request(_body()) is None


def test_rule1_sale_window_must_not_be_inverted():
    msg = validate_request(_body(original_home={
        'disposition': 'sell', 'earliest_sale_year': 2045, 'latest_sale_year': 2030}))
    assert 'sale year' in msg.lower()


def test_rule3_the_screenshot_case_is_rejected_before_any_search_runs():
    """Move-2 latest year 2030 against a move-1 window opening in 2031: no
    move-2 candidate can exist. v1 ran a full search and reported nothing."""
    msg = validate_request(_body(move2={
        'earliest_acquisition_year': 2029, 'latest_acquisition_year': 2030,
        'action': 'auto', 'concurrent': False, 'anchor_count': 5,
        'search': _body()['move1']['search']}))
    assert msg is not None
    assert '2031' in msg


def test_rule4_keep_plus_buy_is_rejected_under_no_dual_ownership():
    body = _body(original_home={'disposition': 'keep'})
    body['move1']['action'] = 'buy'
    msg = validate_request(body)
    assert 'owning two homes' in msg


def test_rule4_does_not_fire_under_auto_disposition():
    """Under auto the sell branch still yields candidates, so blocking the run
    would be wrong."""
    body = _body(original_home={'disposition': 'auto',
                                'earliest_sale_year': 2030, 'latest_sale_year': 2045})
    body['move1']['action'] = 'buy'
    assert validate_request(body) is None


def test_rule5_buying_before_the_sale_window_opens_is_rejected():
    body = _body(original_home={'disposition': 'sell',
                                'earliest_sale_year': 2040, 'latest_sale_year': 2045})
    body['move1'].update({'action': 'buy', 'earliest_acquisition_year': 2030,
                          'latest_acquisition_year': 2035})
    msg = validate_request(body)
    assert '2040' in msg


def test_rule6_anchor_count_must_be_between_two_and_five():
    body = _body()
    body['move1']['search']['anchors'] = [{'kind': 'zip', 'anchor_zip': '80014'}]
    assert 'between 2 and 5' in validate_request(body)

    body['move1']['search']['anchors'] = [
        {'kind': 'zip', 'anchor_zip': f'8001{i}'} for i in range(6)]
    assert 'between 2 and 5' in validate_request(body)


def test_rule7_family_presence_needs_a_five_digit_zip_and_an_ordered_window():
    assert validate_request(_body(family_presence={
        'zip': '123', 'radius_miles': 25,
        'from_year': 2026, 'through_year': 2050})) is not None
    assert validate_request(_body(family_presence={
        'zip': '60521', 'radius_miles': 25,
        'from_year': 2050, 'through_year': 2026})) is not None


def test_rule8_concurrent_requires_full_search_mode():
    msg = validate_request(_body(search_mode='narrowed', move2={
        'earliest_acquisition_year': 2040, 'latest_acquisition_year': 2050,
        'action': 'auto', 'concurrent': True, 'anchor_count': 5,
        'search': _body()['move1']['search']}))
    assert 'full' in msg.lower()


def test_rule9_price_range_must_not_be_inverted():
    body = _body()
    body['move1']['search']['dwelling']['target_purchase_price_range'] = [700000, 400000]
    assert 'maximum' in validate_request(body).lower()


def test_locations_is_no_longer_accepted():
    """The manual-location mode is gone; accepting it silently would produce
    candidates with no ZIP, score or distance."""
    assert validate_request(_body(locations=[{'state': 'CO'}])) is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_housing_api_validation.py -v`
Expected: FAIL with `ImportError: cannot import name 'validate_request'`

- [ ] **Step 3: Write `validate_request`**

In `src/housing/api.py`, as a list of `(predicate, message)` checks evaluated in order so
the first violation is the one reported:

```python
def validate_request(body: dict[str, Any]) -> str | None:
    """The §8 rules, server-side. The panel duplicates these for speed of
    feedback; this copy is the one that is trusted.

    Returns the first violated rule's message, or None.
    """
    if body.get('locations'):
        return ('Manual candidate locations are no longer supported. '
                'Provide 2-5 anchors per move instead.')

    home = body.get('original_home') or {}
    disposition = str(home.get('disposition', 'auto') or 'auto').lower()
    if disposition not in DISPOSITIONS:
        return f"Unknown disposition {disposition!r}."

    sells = disposition in ('sell', 'auto')
    earliest_sale = int(home.get('earliest_sale_year') or 0)
    latest_sale = int(home.get('latest_sale_year') or 0)
    if sells and earliest_sale > latest_sale:
        return 'Earliest sale year must not be after the latest sale year.'

    move1 = body.get('move1') or {}
    e1 = int(move1.get('earliest_acquisition_year') or 0)
    l1 = int(move1.get('latest_acquisition_year') or 0)
    if e1 > l1:
        return 'Earliest move-1 year must not be after the latest.'

    move2 = body.get('move2')
    if move2:
        e2 = int(move2.get('earliest_acquisition_year') or 0)
        l2 = int(move2.get('latest_acquisition_year') or 0)
        if e2 > l2:
            return 'Earliest move-2 year must not be after the latest.'
        if not move2.get('concurrent') and l2 <= e1:
            return (f'Move 2 must be able to happen after move 1. '
                    f'Raise the move-2 latest year above {e1}.')
        if move2.get('concurrent') and str(body.get('search_mode')) != 'full':
            return 'Concurrent mode is only available with Full grid search mode.'

    no_dual = bool(body.get('no_dual_ownership', True))
    actions = [str((body.get(f'move{i}') or {}).get('action', 'auto'))
               for i in (1, 2) if body.get(f'move{i}')]
    if no_dual and disposition == 'keep' and actions and all(a == 'buy' for a in actions):
        return ('Keeping the current home and buying another means owning two '
                "homes. Choose Rent, sell the current home, or turn off "
                "'Never own two homes at once'.")
    if no_dual and disposition == 'sell' and move1.get('action') == 'buy' \
            and l1 < earliest_sale:
        return ('With no dual ownership, move 1 cannot be bought before the home '
                f'is sold. Raise the move-1 latest year to at least {earliest_sale}.')

    for key in ('move1', 'move2'):
        block = body.get(key)
        if not block:
            continue
        search = block.get('search') or {}
        anchors = search.get('anchors') or []
        if not (2 <= len(anchors) <= 5):
            return f'Choose between 2 and 5 anchors for {key.replace("move", "move ")}.'
        if any(not str(a.get('anchor_zip', '')).strip() for a in anchors):
            return f'Every anchor for {key.replace("move", "move ")} needs a ZIP.'
        if int(search.get('radius_miles') or 0) not in ALLOWED_RADII_MILES:
            return f'Radius must be one of {", ".join(map(str, ALLOWED_RADII_MILES))} miles.'
        if str(search.get('area_type', 'any')) not in AREA_TYPES:
            return f"Unknown area type {search.get('area_type')!r}."
        rng = (search.get('dwelling') or {}).get('target_purchase_price_range')
        if rng and float(rng[0]) > float(rng[1]):
            return 'Minimum target price must not exceed the maximum.'

    fp = body.get('family_presence')
    if fp:
        zip_code = str(fp.get('zip', '') or '').strip()
        if len(zip_code) != 5 or not zip_code.isdigit():
            return ('Family presence needs a 5-digit ZIP and a from-year no later '
                    'than the through-year.')
        if int(fp.get('from_year') or 0) > int(fp.get('through_year') or 0):
            return ('Family presence needs a 5-digit ZIP and a from-year no later '
                    'than the through-year.')
        if int(fp.get('radius_miles') or 0) not in FAMILY_RADII_MILES:
            return f'Family radius must be one of {", ".join(map(str, FAMILY_RADII_MILES))} miles.'
    return None
```

- [ ] **Step 4: Rewrite the request adapter**

`optimize_housing_from_request` calls `validate_request` first and returns
`({'success': False, 'error': msg}, 400)` on a message. It then parses each move's search
into a `MultiAnchorRequest`, runs `run_multi_anchor_screen` per move, builds
`zip_screens={'move1': ..., 'move2': ...}`, splices the screening detail onto each
resolved `Location`, builds `family_coords` from the table, and calls `optimize_housing`.

The splice replaces the v1 `nss`-only version at `:156-162` and is what makes
`_format_location` in Task 8 non-empty:

```python
def _splice_screen_detail(location, screened, family_zip, coords):
    """Attach screening-derived display fields to a resolved Location.

    Location is frozen, so this returns a shallow copy carrying the extra
    attributes rather than mutating it. results.py reads them with getattr and
    tolerates their absence for a Location that never came from a screen.
    """
    out = copy.copy(location)
    object.__setattr__(out, 'city', screened.city)
    object.__setattr__(out, 'nss', screened.nss)
    object.__setattr__(out, 'band', screened.band)
    object.__setattr__(out, 'distance_miles', screened.distance_miles)
    object.__setattr__(out, 'family_distance_miles', screened.family_distance_miles)
    object.__setattr__(out, 'est_price', screened.est_price)
    return out
```

`zip_screen_from_request` accepts `{'search': {...}}` and returns a `zip_screen_v2`
payload, so "Preview shortlist" works for either move.

- [ ] **Step 5: Update the contract registry and routes**

`src/api_contracts.py:130`: `"housing_optimize_v1"` → `"housing_optimize_v2"`.
`src/server/plan_routes.py:761-770`: the `/api/housing/zip-screen` handler passes the body
through unchanged; no signature change is needed there.

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_housing_api_validation.py -v`
Expected: 11 passed

Run: `pytest tests/ -m "not slow and not nightly" -q`
Expected: the whole suite is green again for the first time since Task 2.

- [ ] **Step 7: Commit**

```bash
git add src/housing/api.py src/api_contracts.py src/server/plan_routes.py tests/
git commit -m "feat(housing): v2 request contract with server-side validation

An impossible year window is rejected with the field named, instead of
spending a full search to report that nothing matched."
```

---

### Task 11: Extract the panel into its own module

Pure move plus markup rewrite, no behaviour change beyond the new layout. Splitting it
from the behaviour tasks keeps the diff reviewable.

**Files:**
- Create: `frontend/js/dashboard_decomp_housing_optimizer.js`
- Modify: `frontend/js/dashboard_decomp_housing_scenarios.js` — delete lines 1206–1489 and 1491–1841's optimizer half; import and re-export instead
- Modify: `frontend/js/dashboard.js:7149` area — add the new module's window bridge
- Test: `tests/frontend/housing_optimize_panel.test.mjs` (rewrite)

**Interfaces:**
- Produces: `renderHousingOptimizePanelHtml()`, `startHousingOptimization()`,
  `previewHousingZipShortlist(moveIndex)`, `toggleHousingOptMove2Fields()`,
  `addHousingOptAnchor(moveIndex)`, `removeHousingOptAnchor(moveIndex, i)`,
  `showHousingOptFieldHelp(key)`, `HOUSING_OPT_FIELD_HELP`.

- [ ] **Step 1: Write the failing test**

```js
// tests/frontend/housing_optimize_panel.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderHousingOptimizePanelHtml }
  from '../../frontend/js/dashboard_decomp_housing_optimizer.js';

test('the manual-location mode is gone', () => {
  const html = renderHousingOptimizePanelHtml();
  assert.ok(!html.includes('Choose locations manually'));
  assert.ok(!html.includes('housingOptGeoMode'));
  assert.ok(!html.includes('housingOptLocCount'));
});

test('global constraints and objective come before the move sections', () => {
  const html = renderHousingOptimizePanelHtml();
  assert.ok(html.indexOf('housingOptObjective') < html.indexOf('housingOptMove1Earliest'));
  assert.ok(html.indexOf('housingOptPresenceZip') < html.indexOf('housingOptMove1Earliest'));
});

test('the current home is its own section with a disposition control', () => {
  const html = renderHousingOptimizePanelHtml();
  assert.ok(html.includes('housingOptDisposition'));
  assert.ok(html.includes('housingOptEarliestSale'));
  assert.ok(html.includes('housingOptLatestSale'));
});

test('each move has an acquisition window, not a purchase window', () => {
  const html = renderHousingOptimizePanelHtml();
  assert.ok(html.includes('housingOptMove1Earliest'));
  assert.ok(html.includes('housingOptMove2Earliest'));
  assert.ok(!html.includes('housingOptEarliestPurchase'));
});

test('family presence is a ZIP plus a proximity radius', () => {
  const html = renderHousingOptimizePanelHtml();
  assert.ok(html.includes('housingOptPresenceZip'));
  assert.ok(html.includes('housingOptPresenceRadius'));
  for (const r of ['10', '25', '50', '100']) {
    assert.ok(html.includes(`value="${r}"`), `radius ${r} missing`);
  }
  assert.ok(!html.includes('housingOptPresenceRegion'));
});

test('both moves expose the new candidate and dwelling constraints', () => {
  const html = renderHousingOptimizePanelHtml();
  for (const n of [1, 2]) {
    for (const f of ['AreaType', 'MaxPopulation', 'LotSize', 'Bedrooms', 'Bathrooms']) {
      assert.ok(html.includes(`housingOptMove${n}${f}`), `move ${n} ${f} missing`);
    }
  }
});

test('labels are stacked above their control, never inline before it', () => {
  const html = renderHousingOptimizePanelHtml();
  assert.ok(html.includes('housing-opt-field'));
  assert.ok(!/<label>[^<]*<input/.test(html),
    'found an inline label immediately followed by its input');
});

test('every field carries a help affordance instead of inline helper text', () => {
  const html = renderHousingOptimizePanelHtml();
  const fields = (html.match(/class="housing-opt-field"/g) || []).length;
  const helps = (html.match(/showHousingOptFieldHelp\(/g) || []).length;
  assert.ok(fields > 0);
  assert.ok(helps >= fields, `${helps} help hooks for ${fields} fields`);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test`
Expected: FAIL — the module does not exist.

- [ ] **Step 3: Create the module with the new markup**

Build `renderHousingOptimizePanelHtml()` from a small field helper so the label-above rule
and the help hook are structural rather than repeated by hand:

```js
// frontend/js/dashboard_decomp_housing_optimizer.js
// Housing move optimizer panel. Split out of
// dashboard_decomp_housing_scenarios.js on 2026-09-16: that file also owns the
// spending/housing screen and had reached 1,841 lines.
//
// Layout rule (design §9.2): every control is wrapped by housingOptField,
// which stacks the label ABOVE the control. A label placed to the left adds
// its width to every field and pushes a six-field row into horizontal
// scrolling. Helper text is never inline for the same reason -- it lives in
// the app's right-hand Context Help pane, reached via the "i" affordance.

function housingOptField(key, labelText, controlHtml, hint) {
  return `<div class="housing-opt-field" onclick="showHousingOptFieldHelp('${key}')">
    <label for="${key}">${esc(labelText)}<sup class="field-info-i" tabindex="0"
      title="${esc(hint)}">i</sup></label>
    ${controlHtml}
  </div>`;
}

function housingOptRow(title, fieldsHtml) {
  return `<div class="housing-opt-row">
    <div class="housing-opt-row-label">${esc(title)}</div>
    <div class="housing-opt-row-fields">${fieldsHtml}</div>
  </div>`;
}
```

Assemble the rows in the §9.2 order: Objective & constraints, Family presence, Current
home, Move 1 (where / what / when), Consider a second move, Run. Each control's `id` is
the `key` passed to `housingOptField`, so the help registry, the persistence snapshot and
the DOM all agree on one name.

- [ ] **Step 4: Delete the old block and re-export**

Remove lines 1206–1489 from `dashboard_decomp_housing_scenarios.js` and the optimizer
functions in 1491–1760, plus their entries in the window bridge at 1787–1841. Replace
the call site inside `renderScenarioManagementPanel` (`:1160-1161`) with an import:

```js
import { renderHousingOptimizePanelHtml } from './dashboard_decomp_housing_optimizer.js';
```

Add the new module's window bridge next to the existing ones in `dashboard.js`.

- [ ] **Step 5: Run the tests**

Run: `npm test`
Expected: 8 passed

Run: `pytest tests/ -k "zip_screen and functional" -q`
Expected: failures in the functional tests that assert on the old markup. Update them to
the new ids — the markup change is the point of this task.

- [ ] **Step 6: Commit**

```bash
git add frontend/js/ tests/
git commit -m "refactor(housing): extract the optimizer panel into its own module

Row-oriented layout with labels above their controls, no manual-location
mode, and a help affordance per field."
```

---

### Task 12: Request building and inline validation

**Files:**
- Modify: `frontend/js/dashboard_decomp_housing_optimizer.js`
- Test: `tests/frontend/housing_optimize_request.test.mjs` (create)

**Interfaces:**
- Consumes: Task 11's markup ids, Task 10's wire contract.
- Produces: `buildHousingOptRequest() -> object`, `validateHousingOptForm() -> string | null`
  (mirroring §8 rule-for-rule), `runHousingOptimization()`.

- [ ] **Step 1: Write the failing test**

```js
// tests/frontend/housing_optimize_request.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildHousingOptRequest, validateHousingOptForm }
  from '../../frontend/js/dashboard_decomp_housing_optimizer.js';
import { mountHousingOptPanel } from './helpers/mount_housing_opt.mjs';

test('the request carries no locations key', () => {
  mountHousingOptPanel();
  assert.ok(!('locations' in buildHousingOptRequest()));
});

test('anchors are collected per move', () => {
  mountHousingOptPanel({ move1Anchors: ['80014', '60521'] });
  const body = buildHousingOptRequest();
  assert.deepEqual(body.move1.search.anchors.map((a) => a.anchor_zip),
    ['80014', '60521']);
});

test('a kept home sends no sale window', () => {
  mountHousingOptPanel({ disposition: 'keep' });
  const body = buildHousingOptRequest();
  assert.equal(body.original_home.disposition, 'keep');
  assert.ok(!body.original_home.earliest_sale_year);
});

test('family presence sends a zip and a radius, never a region', () => {
  mountHousingOptPanel({ presenceZip: '60521', presenceRadius: 25 });
  const fp = buildHousingOptRequest().family_presence;
  assert.equal(fp.zip, '60521');
  assert.equal(fp.radius_miles, 25);
  assert.ok(!('region' in fp));
});

test('the screenshot case is blocked before any request is built', () => {
  mountHousingOptPanel({
    move1Earliest: 2031, move1Latest: 2046,
    move2Enabled: true, move2Earliest: 2029, move2Latest: 2030,
  });
  const msg = validateHousingOptForm();
  assert.ok(msg && msg.includes('2031'));
});

test('a valid form validates clean', () => {
  mountHousingOptPanel();
  assert.equal(validateHousingOptForm(), null);
});

test('the run button is disabled while the form is invalid', () => {
  mountHousingOptPanel({ move1Earliest: 2046, move1Latest: 2031 });
  assert.equal(document.getElementById('housingOptRun').disabled, true);
});
```

`tests/frontend/helpers/mount_housing_opt.mjs` renders the panel into a minimal DOM stub
and applies the given overrides; create it alongside, following whatever DOM stub the
existing `housing_optimize_panel.test.mjs` already uses.

- [ ] **Step 2: Run to verify it fails**

Run: `npm test`
Expected: FAIL — `buildHousingOptRequest` is not exported.

- [ ] **Step 3: Implement the builder and the validator**

`validateHousingOptForm()` implements the same nine rules as §8 in the same order and
returns the same messages, so client and server never disagree about which rule fired.
`runHousingOptimization()` calls it first and returns early, rendering the message into
the result area, rather than issuing the request.

Wire `oninput` on every year, ZIP and price field to a debounced
`refreshHousingOptValidation()` that sets `#housingOptRun.disabled` and writes the message
into `#housingOptValidation`.

- [ ] **Step 4: Run the tests**

Run: `npm test`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add frontend/js/dashboard_decomp_housing_optimizer.js tests/frontend/
git commit -m "feat(housing): build v2 requests and block impossible windows inline"
```

---

### Task 13: Results rendering

**Files:**
- Modify: `frontend/js/dashboard_decomp_housing_optimizer.js`
- Test: `tests/frontend/housing_optimize_results.test.mjs` (create)

**Interfaces:**
- Consumes: Task 8's payload.
- Produces: `renderHousingOptimizeResultsHtml(payload)`,
  `renderHousingZipShortlistHtml(screen, opts)`.

- [ ] **Step 1: Write the failing test**

```js
// tests/frontend/housing_optimize_results.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderHousingOptimizeResultsHtml }
  from '../../frontend/js/dashboard_decomp_housing_optimizer.js';

const MOVE1 = {
  index: 1, acquisition_year: 2033, action: 'buy', mode: 'sequential',
  location: { zip_code: '80024', city: 'Derby', state: 'CO', area_type: 'suburban',
              population: 12480, nss: 89.1, band: 'Very Favorable',
              distance_miles: 11.83, family_distance_miles: 18.4, est_price: 539400 },
  sec121_exclusion_lost: false,
};

function payload(over = {}) {
  return {
    success: true, schema: 'housing_optimize_v2', objective: 'net_worth',
    candidates: [{ rank: 1, original_home: { disposition: 'sell', sale_year: 2032 },
                   moves: [MOVE1], net_worth: 4210000, lifetime_cost: 1180000,
                   mc_success_rate: 0.912, objective_value: 4210000, notes: [] }],
    recommendation: null, candidates_evaluated: 12, rejections: {}, ...over,
  };
}

test('a recommendation row carries year, action, ZIP, price and distance', () => {
  const html = renderHousingOptimizeResultsHtml(payload());
  for (const part of ['2032', '2033', 'Buy', '80024', 'Derby', 'CO',
                      '$539,400', '11.8 mi']) {
    assert.ok(html.includes(part), `missing ${part}`);
  }
});

test('a kept home reads as Keep rather than a blank sale year', () => {
  const p = payload();
  p.candidates[0].original_home = { disposition: 'keep', sale_year: null };
  assert.ok(renderHousingOptimizeResultsHtml(p).includes('Keep'));
});

test('a missing second move renders an em dash, not an empty cell', () => {
  assert.ok(renderHousingOptimizeResultsHtml(payload()).includes('—'));
});

test('rank 1 is badged and labelled Recommended', () => {
  const html = renderHousingOptimizeResultsHtml(payload());
  assert.ok(html.includes('housing-opt-rank'));
  assert.ok(html.includes('Recommended'));
});

test('adjacent results alternate shading so a wrapped row stays one block', () => {
  const p = payload();
  p.candidates.push({ ...p.candidates[0], rank: 2 });
  const html = renderHousingOptimizeResultsHtml(p);
  assert.ok(html.includes('housing-opt-result-odd'));
  assert.ok(html.includes('housing-opt-result-even'));
});

test('an empty run reports the rejection tally instead of a generic sentence', () => {
  const html = renderHousingOptimizeResultsHtml(
    payload({ candidates: [], rejections: { family_presence: 12, dual_ownership: 40 } }));
  assert.ok(html.includes('12'));
  assert.ok(html.includes('40'));
  assert.ok(!html.includes('No candidates satisfied the search windows'));
});

test('family distance appears only when family presence was used', () => {
  assert.ok(renderHousingOptimizeResultsHtml(payload()).includes('18.4'));
  const p = payload();
  p.candidates[0].moves[0].location.family_distance_miles = null;
  assert.ok(!renderHousingOptimizeResultsHtml(p).includes('from family'));
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test`
Expected: FAIL — the renderer still reads `payload.alternatives`.

- [ ] **Step 3: Implement the renderer**

One `<tr>` per candidate with `class="housing-opt-result housing-opt-result-${rank % 2 ? 'odd' : 'even'}"`,
a rank badge cell, a current-home cell, one cell per move, then objective, MC and notes.
`housingOptMoveCellHtml(move)` produces
`${year} · ${Buy|Rent} · ${zip} ${city}, ${state} · ${price} · ${distance} mi`, appending
`· ${n} mi from family` only when `family_distance_miles` is non-null.

- [ ] **Step 4: Run the tests**

Run: `npm test`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add frontend/js/dashboard_decomp_housing_optimizer.js tests/frontend/
git commit -m "feat(housing): one detailed row per recommendation

Each row carries the sale year, each move's year, action, ZIP, price and
distance. An empty run reports why."
```

---

### Task 14: Panel CSS and the help registry

**Files:**
- Modify: `frontend/css/dashboard.css`
- Modify: `frontend/js/dashboard_decomp_housing_optimizer.js` (`HOUSING_OPT_FIELD_HELP`, `showHousingOptFieldHelp`)
- Test: `tests/test_housing_optimizer_panel_functional.py` (create)

**Interfaces:**
- Consumes: `ensureHelpPanelVisible()` (`dashboard_decomp_row_model.js:4288`), `pageHelp()` (`dashboard.js:963`).
- Produces: `HOUSING_OPT_FIELD_HELP: Record<string, string>`, `showHousingOptFieldHelp(key)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_housing_optimizer_panel_functional.py
"""Panel layout and help wiring (design 2026-09-16 §9.2, §9.5)."""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

JS = Path('frontend/js/dashboard_decomp_housing_optimizer.js').read_text(encoding='utf-8')
CSS = Path('frontend/css/dashboard.css').read_text(encoding='utf-8')


def _help_keys():
    block = JS.split('HOUSING_OPT_FIELD_HELP')[1]
    return set(re.findall(r"^\s{2}(\w+):", block, re.MULTILINE))


def test_every_field_that_asks_for_help_has_a_registry_entry():
    requested = set(re.findall(r"showHousingOptFieldHelp\('(\w+)'\)", JS))
    missing = requested - _help_keys() - {'_panel'}
    assert not missing, f'no help content for: {sorted(missing)}'


def test_screen_level_help_exists():
    assert '_panel' in _help_keys()


def test_help_writes_to_the_apps_existing_panel_and_reveals_it():
    assert 'ensureHelpPanelVisible' in JS
    assert 'helpPanel' in JS


def test_no_inline_helper_text_under_fields():
    """Inline helper text widens every field and forces the row to wrap."""
    assert 'housing-opt-hint' not in CSS


def test_selects_are_sized_to_their_longest_option():
    rule = re.search(r"\.housing-opt-field select\s*\{[^}]*\}", CSS)
    assert rule and 'width:auto' in rule.group(0).replace(' ', '')


def test_year_inputs_are_narrow():
    rule = re.search(r"\.housing-opt-field input\.year\s*\{[^}]*\}", CSS)
    assert rule and '5em' in rule.group(0)


def test_no_inline_width_styles_remain_in_the_panel():
    assert 'style="width:' not in JS


def test_results_use_shading_and_a_rank_badge_together():
    for selector in ['.housing-opt-result-odd', '.housing-opt-result-even',
                     '.housing-opt-rank']:
        assert selector in CSS, f'{selector} missing'


def test_a_result_boundary_is_ruled():
    rule = re.search(r"\.housing-opt-result\s*\+\s*\.housing-opt-result\s*\{[^}]*\}", CSS)
    assert rule and 'border-top' in rule.group(0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_housing_optimizer_panel_functional.py -v`
Expected: FAIL — the CSS rules do not exist.

- [ ] **Step 3: Add the CSS**

Append to `frontend/css/dashboard.css`:

```css
/* Housing optimizer panel (design 2026-09-16 §9.2). Labels stack above their
   control so each field is only as wide as the control needs; a left-hand
   label would add its width to every field and force horizontal scrolling. */
.housing-opt-row{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-start;padding:10px 0;border-top:1px solid var(--line)}
.housing-opt-row-label{flex:0 0 100%;font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.housing-opt-row-fields{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-start}
.housing-opt-field{display:flex;flex-direction:column;gap:3px}
.housing-opt-field label{font-size:12px;color:var(--muted);white-space:nowrap}
.housing-opt-field select{width:auto}
.housing-opt-field input.year{width:5em}
.housing-opt-field input.zip{width:5em}
.housing-opt-field input.money,.housing-opt-field input.count{width:8em}

/* A result may wrap to several lines. Three cues together keep the boundary
   obvious: alternating shade, a heavy rule, and the persistent rank badge. */
.housing-opt-result-odd{background:#fff}
.housing-opt-result-even{background:#f6f7f9}
.housing-opt-result + .housing-opt-result{border-top:2px solid var(--line)}
.housing-opt-rank{font-weight:850;font-variant-numeric:tabular-nums;white-space:nowrap}
.housing-opt-result-top .housing-opt-rank{color:#1d4ed8}
```

- [ ] **Step 4: Write the help registry**

One entry per field id used in Task 11, built with the app's `pageHelp()` so the headings
match every other help entry. Fields with real content to carry — `housingOptDisposition`,
`housingOptNoDualOwnership`, `housingOptObjective`, `housingOptSearchMode`,
`housingOptMove2Strategy`, `housingOptMove2Concurrent`, `housingOptPresenceZip`,
`housingOptPresenceRadius`, each move's `AreaType`, `MaxPopulation`, `LotSize`, `MinScore`,
`Radius`, `ShortlistSize` — get all four sections. Year fields get *What this value means*
plus the §8 rule that governs them. `_panel` covers the objective choices, the funnel, and
the Phase-1 rental-income limitation.

```js
export function showHousingOptFieldHelp(key) {
  const html = HOUSING_OPT_FIELD_HELP[key] || HOUSING_OPT_FIELD_HELP._panel;
  ensureHelpPanelVisible();
  const target = document.getElementById('helpPanel');
  if (target) target.innerHTML = html;
}
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_housing_optimizer_panel_functional.py -v`
Expected: 9 passed

- [ ] **Step 6: Commit**

```bash
git add frontend/css/dashboard.css frontend/js/ tests/
git commit -m "feat(housing): panel layout CSS and per-field context help

Help goes to the app's existing right-hand pane rather than inline, so a
field is only as wide as its control."
```

---

### Task 15: Input persistence

**Files:**
- Modify: `frontend/js/dashboard_decomp_housing_optimizer.js`
- Test: `tests/frontend/housing_optimize_persistence.test.mjs` (create)

**Interfaces:**
- Produces: `HOUSING_OPT_STORAGE_KEY = 'retirement.housing_optimizer.v1'`,
  `saveHousingOptInputs()`, `loadHousingOptInputs() -> object`.

- [ ] **Step 1: Write the failing test**

```js
// tests/frontend/housing_optimize_persistence.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  HOUSING_OPT_STORAGE_KEY, loadHousingOptInputs, saveHousingOptInputs,
  renderHousingOptimizePanelHtml,
} from '../../frontend/js/dashboard_decomp_housing_optimizer.js';
import { mountHousingOptPanel } from './helpers/mount_housing_opt.mjs';

test('inputs survive a re-render', () => {
  mountHousingOptPanel({ move1Earliest: 2037, presenceZip: '60521' });
  saveHousingOptInputs();
  mountHousingOptPanel();
  assert.equal(document.getElementById('housingOptMove1Earliest').value, '2037');
  assert.equal(document.getElementById('housingOptPresenceZip').value, '60521');
});

test('results are never restored', () => {
  mountHousingOptPanel();
  saveHousingOptInputs();
  const stored = JSON.parse(localStorage.getItem(HOUSING_OPT_STORAGE_KEY));
  assert.ok(!('results' in stored));
  assert.ok(!('candidates' in stored));
  mountHousingOptPanel();
  assert.equal(document.getElementById('housingOptimizeResults').innerHTML, '');
});

test('an unparseable payload falls back to defaults rather than throwing', () => {
  localStorage.setItem(HOUSING_OPT_STORAGE_KEY, '{not json');
  assert.doesNotThrow(() => loadHousingOptInputs());
  assert.doesNotThrow(() => renderHousingOptimizePanelHtml());
});

test('an unknown key is ignored so the shape can grow without a migration', () => {
  localStorage.setItem(HOUSING_OPT_STORAGE_KEY,
    JSON.stringify({ housingOptMove1Earliest: 2037, somethingRemoved: 'x' }));
  assert.doesNotThrow(() => mountHousingOptPanel());
  assert.equal(document.getElementById('housingOptMove1Earliest').value, '2037');
});

test('unavailable storage degrades silently', () => {
  const original = globalThis.localStorage;
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    get() { throw new Error('blocked'); },
  });
  try {
    assert.doesNotThrow(() => saveHousingOptInputs());
    assert.deepEqual(loadHousingOptInputs(), {});
  } finally {
    Object.defineProperty(globalThis, 'localStorage',
      { configurable: true, value: original });
  }
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test`
Expected: FAIL — `HOUSING_OPT_STORAGE_KEY` is not exported.

- [ ] **Step 3: Implement persistence**

Follow the `scenarioWriteSets` pattern in the same area of the codebase
(`dashboard_decomp_housing_scenarios.js:936-947`): one JSON object, every access wrapped
in try/catch.

```js
export const HOUSING_OPT_STORAGE_KEY = 'retirement.housing_optimizer.v1';

export function loadHousingOptInputs() {
  try {
    return JSON.parse(localStorage.getItem(HOUSING_OPT_STORAGE_KEY) || '{}') || {};
  } catch (e) {
    // Blocked, cleared, or corrupt storage is not an error worth surfacing:
    // the form simply starts at its defaults.
    return {};
  }
}
```

`saveHousingOptInputs()` snapshots every `[id]` in the panel plus the anchor lists, the
move-2 enabled flag and the `<details>` open state. It deliberately stores nothing
derived from a run: a restored form always shows an empty result area, so a stale
recommendation can never be mistaken for a fresh one.

Call `saveHousingOptInputs` from a debounced `oninput`/`onchange` on the panel container,
and apply `loadHousingOptInputs()` at the end of `renderHousingOptimizePanelHtml()`.

- [ ] **Step 4: Run the tests**

Run: `npm test`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add frontend/js/dashboard_decomp_housing_optimizer.js tests/frontend/
git commit -m "feat(housing): remember optimizer inputs between visits

Inputs only -- results are never restored, so a stale recommendation cannot
be mistaken for a fresh one."
```

---

### Task 16: Spending/housing screen parity

**Files:**
- Modify: `src/server_services/strategy_asset_service.py:48-88` (seed rows)
- Modify: `frontend/js/dashboard_decomp_housing_scenarios.js:426-432` (`housingAreaTypeSelect`), `:478-508` (field order), `:692` (cross-link copy)
- Test: `tests/test_housing_screen_parity.py` (create)

**Interfaces:**
- Consumes: Task 1's `LOT_SIZE_BAND_LABELS`, Task 11's option lists.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_housing_screen_parity.py
"""The spending screen and the optimizer describe the same dwelling (§10)."""
import re
from pathlib import Path

import pytest

from src.server_services.strategy_asset_service import HOUSING_SEED_ROWS

pytestmark = pytest.mark.contract

SPENDING = Path('frontend/js/dashboard_decomp_housing_scenarios.js').read_text(encoding='utf-8')
OPTIMIZER = Path('frontend/js/dashboard_decomp_housing_optimizer.js').read_text(encoding='utf-8')


def _seed_keys(section):
    return {r[2] for r in HOUSING_SEED_ROWS if r[1] == section}


def _options(js, select_id):
    block = js.split(select_id)[1].split('</select>')[0]
    return set(re.findall(r'value="([^"]+)"', block))


def test_both_next_steps_carry_the_full_dwelling_spec():
    expected = {'bedrooms', 'bathrooms', 'property_type', 'sqft_band',
                'lot_size_band', 'built_within_years', 'zip_code'}
    for section in ('next_step_1', 'next_step_2'):
        assert expected <= _seed_keys(section), f'{section} missing {expected - _seed_keys(section)}'


def test_area_type_includes_exurban_on_both_screens():
    """The optimizer buckets ZIPs into four area types; the spending screen
    offered only three, so an exurban recommendation could not be recorded."""
    assert 'exurban' in _options(SPENDING, 'housingAreaTypeSelect')
    assert 'exurban' in _options(OPTIMIZER, 'housingOptMove1AreaType')


def test_area_type_option_sets_are_identical():
    spending = _options(SPENDING, 'housingAreaTypeSelect')
    optimizer = _options(OPTIMIZER, 'housingOptMove1AreaType') - {'any'}
    assert spending == optimizer


@pytest.mark.parametrize('select_id_pair', [
    ('housingBedroomsSelect', 'housingOptMove1Bedrooms'),
    ('housingBathroomsSelect', 'housingOptMove1Bathrooms'),
    ('housingPropertyTypeSelect', 'housingOptMove1PropertyType'),
    ('housingSqftBandSelect', 'housingOptMove1SqftBand'),
    ('housingLotSizeSelect', 'housingOptMove1LotSize'),
])
def test_dwelling_option_sets_match_field_for_field(select_id_pair):
    spending_id, optimizer_id = select_id_pair
    assert _options(SPENDING, spending_id) == _options(OPTIMIZER, optimizer_id)


def test_the_seed_descriptions_name_all_four_area_types():
    for row in HOUSING_SEED_ROWS:
        if row[2] == 'city_type':
            assert 'exurban' in row[5], row


def test_the_cross_link_names_what_carries_across():
    assert 'Optimize next housing move' in SPENDING
    for word in ('ZIP', 'price', 'distance'):
        assert word in SPENDING
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_housing_screen_parity.py -v`
Expected: FAIL — `lot_size_band` and `zip_code` are not in the seed rows.

- [ ] **Step 3: Add the missing seed rows**

For both `next_step_1` and `next_step_2`, after `sqft_band`:

```python
    ["Housing","next_step_N","lot_size_band","quarter_half","choice","Lot size band for the Estimate button: under_quarter|quarter_half|half_one|one_three|over_three"],
    ["Housing","next_step_N","zip_code","","text","ZIP code this step's costs were estimated for (optional; recorded by the optimizer)"],
```

and change every `city_type` description from `Area type: urban|suburban|rural` to
`Area type: urban|suburban|exurban|rural`, including `current_home`'s.

- [ ] **Step 4: Align the option lists**

Add `<option value="exurban">Exurban</option>` to `housingAreaTypeSelect` (`:426-432`).
Extract the bedroom, bathroom, property-type, sqft and lot-size option lists into named
select helpers with the ids the test expects, so the two screens read from markup that is
visibly the same rather than agreeing by coincidence. Add `lot_size_band` and `zip_code`
to the purchase and rent field orders at `:478-508`.

- [ ] **Step 5: Rewrite the cross-link copy**

Replace the paragraph at `:692` so it names the fields that carry across and states that
the optimizer's results now include ZIP, estimated price and distance.

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_housing_screen_parity.py -v`
Expected: all pass

Run: `pytest tests/ -m "not slow and not nightly" -q && npm test`
Expected: green

- [ ] **Step 7: Commit**

```bash
git add src/server_services/strategy_asset_service.py frontend/js/ tests/
git commit -m "feat(housing): align the spending screen's dwelling fields with the optimizer

Adds lot size and ZIP, and the exurban area type the optimizer could already
produce but the screen could not record."
```

---

### Task 17: Harness, docs and archive

**Files:**
- Modify: `tools/housing_lab.py:187`
- Modify: `src/housing/__init__.py:49-54` (package narrative)
- Move: `documentation/archive/superpowers/specs/` ← the two superseded specs
- Test: existing suite

- [ ] **Step 1: Update the CLI harness**

`tools/housing_lab.py` builds a v1 body and prints `recommendation`/`alternatives`. Update
it to the v2 request shape and to print the ranked `candidates` list with the same columns
the panel shows, so the harness and the UI stay comparable.

- [ ] **Step 2: Update the package narrative**

`src/housing/__init__.py`'s docstring describes the sale/purchase-welded model and the
state-level family presence. Rewrite those paragraphs to describe the decoupled model and
the ZIP-radius filter, and keep the §121 caveat at `:49-54` — it is still accurate in
Phase 1 and is the hook Phase 2 extends. Update `__all__` (`:140-155`) for the renamed
exports.

- [ ] **Step 3: Archive the superseded specs**

```bash
git mv docs/superpowers/specs/2026-09-15-zip-code-housing-screening-design.md \
       documentation/archive/superpowers/specs/
git mv docs/superpowers/plans/2026-09-15-zip-code-housing-screening.md \
       documentation/archive/superpowers/plans/
git mv docs/superpowers/plans/2026-09-15-zip-code-housing-screening-followup.md \
       documentation/archive/superpowers/plans/
```

- [ ] **Step 4: Full verification**

Run: `pytest tests/ -m "not slow and not nightly" -q`
Expected: green

Run: `npm test`
Expected: green

Run: `python tools/housing_lab.py --help`
Expected: exits 0

- [ ] **Step 5: Commit**

```bash
git add tools/housing_lab.py src/housing/__init__.py docs/ documentation/
git commit -m "chore(housing): update the lab harness and archive superseded specs"
```

---

## Plan self-review

**Spec coverage.** §5.1 → Tasks 2, 3. §5.2 → Task 9. §5.3 → Tasks 3, 10. §5.4 → Tasks 3, 4.
§6.1 → Task 6. §6.2 → Task 5. §6.3 → Tasks 1, 16. §6.4 → Task 7. §7.1 → Task 10. §7.2 →
Task 8. §7.3 → Task 10. §8 → Task 10 (server) and Task 12 (client). §9.1 → Task 11. §9.2 →
Tasks 11, 14. §9.3 → Task 11. §9.4 → Tasks 13, 14. §9.5 → Task 14. §9.6 → Task 15. §10 →
Task 16. §11 → distributed across every task's test step. §12 → the file-structure table.
§13 is Phase 2 and has no task by design.

**Known sequencing hazard.** Task 2 deliberately leaves the housing suite red; it returns
to green at Task 10. Anyone stopping between those two tasks has a broken `/api/housing/*`
endpoint. If the work must be interrupted, stop at Task 1 or at Task 10, not between.

**Type consistency.** `acquisition_year`, `action`, `disposition`, `sale_year`,
`nearest_anchor_zip`, `family_distance_miles`, `area_type`, `population`, `notes`,
`candidates`, `rejections` and `zip_screens` are spelled identically in the spec, the
tests and the implementation snippets. `dual_ownership_ok` is defined once in Task 3 and
imported by Tasks 4 and 9. `format_output` is keyword-only in both its definition (Task 8)
and its call site (Task 9). `run_multi_anchor_screen` returns the same `ScreenResult` type
`run_screen` does, so `screen_payload` needs no second code path.
