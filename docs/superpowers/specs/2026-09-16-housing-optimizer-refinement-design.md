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
- Reduce the form to labelled horizontal rows with help in the existing right-hand panel.

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
flex row that wraps. Sizing rules, applied as CSS in `frontend/css/dashboard.css` under a
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
| Helper text | Right-hand Context Help pane, not inline | Inline text widens every row; the app already has this surface and its heading conventions. |
| Down payment / mortgage rate | Added to the optimizer | Otherwise the two screens price the same house differently. |
| Keep-and-rent-out | Phase 2 | Needs a tax subsystem that does not exist; `Keep` is still a valid Phase 1 outcome without it. |
