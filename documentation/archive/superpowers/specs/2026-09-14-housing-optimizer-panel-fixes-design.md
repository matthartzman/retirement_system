# Housing optimizer panel fixes — design

Follow-up to `2026-09-09-housing-optimization-design.md` (the original
scenario-manager panel, commit `fe496e4`, #109) and
`2026-09-09-housing-estimate-realism-and-dollar-convention-design.md` (the
five-characteristic pricing model that was specced but never wired in).

Fixes four issues found using the panel:

1. State fields are free text, not a dropdown of valid values.
2. The five housing criteria (bedrooms, bathrooms, property type, sqft,
   age) are missing everywhere a home is priced.
3. The recommendation text reads as nonsensical ("Sell 2035 → Buy 2032").
4. The UI structurally assumes move 1 and move 2 are sequential purchases;
   there's no way to model "buy here, rent there, concurrently" to satisfy
   family presence in two locations at once.

## 1. State fields → dropdown

Both free-text state inputs in the housing optimizer panel become
dropdowns, reusing the existing site-wide canonical state list instead of
inventing a new one:

- `frontend/js/dashboard_decomp_housing_scenarios.js:1171` — candidate
  location's `housingOptLocState${i}` input.
- `frontend/js/dashboard_decomp_housing_scenarios.js:1224`-area — family
  presence's `housingOptPresenceRegion` input (name attribute confirmed at
  investigation time; verify against current line numbers when
  implementing).

Both switch from `<input type="text">` to `<select>`, populated via
`_stateNameChoiceOptions()` (`frontend/js/dashboard_decomp_state_inputs.js:24-26`),
matching the `#260` convention ("every state Plan Data input is a pull-down
of the 50 states plus DC, never free text") already used elsewhere in the
dashboard. Values are full state names, matching what
`Location.state`/`FamilyPresence.region` already expect
(`housing_optimizer.py:103-117`'s `_STATE_ABBREV` comment confirms full
names are canonical there).

No backend change — the optimizer already accepts full state names.

## 2. Five housing criteria, fully wired

`documentation/archive/superpowers/plans/2026-09-09-housing-estimate-realism-and-dollar-convention-design.md`
§3.3 already specs this in full (fields, ranges, defaults, multiplier
tables, the condo/townhome HOA-floor adjustment). This design adopts that
spec verbatim and wires it into the two places that were never updated:

**Backend — `src/server_services/strategy_asset_service.py`,
`housing_state_estimate_payload()`:**

- Accept five new optional fields on the input `data` dict: `bedrooms`
  (int, clamped to `{2,3,4,5}`), `bathrooms` (choice:
  `1|1.5|2|2.5|3|3.5+`), `property_type` (choice:
  `single_family|townhome|condo|duplex`), `sqft_band` (choice:
  `under_1200|1200_1800|1800_2500|2500_3500|over_3500`),
  `built_within_years` (int or blank).
- Defaults match today's implicit assumption exactly (3BR/2BA/
  single_family/1800–2500 sqft/no preference), so omitting all five
  reproduces today's numbers unchanged.
- Add `BEDROOM_MULT`, `BATHROOM_MULT`, `PROPERTY_TYPE_MULT`,
  `SQFT_BAND_MULT` tables and `built_within_years_mult()` exactly as
  specced (doc lines 156-179), folded into the existing `combined`
  multiplier alongside `city_mult`/`pop_mult` (doc line 181), applied
  before the existing §3.2 dollar-year translation and rounding — i.e.
  inserted into the same multiplicative pipeline, not a parallel one.
- Property type also sets a floor on `hoa_pct` and reduces
  `maintenance_annual` for condo/townhome (doc lines 190-194).
- `estimate["note"]` states the actual characteristics used (doc §3.5),
  replacing the current hardcoded "3BR/2BA... 40x40 ft backyard" text.

**Backend — `src/housing_optimizer.py`:**

- `Location` dataclass (line 124-129) gains the same five fields, same
  defaults, so existing callers/tests that construct a bare `Location(state=...)`
  keep working unchanged.
- `_estimate_for_location()` (line 190-197) passes them through to
  `housing_state_estimate_payload`.
- `api_contracts.py`'s `/api/housing/optimize` request-field contract
  (`~line 122`) gains the five optional fields per location.

**Frontend — both places a home gets priced:**

- The regular housing-step editor's Estimate flow (`dashboard.js`, the
  `filterChoiceOptionsForRow` options map) gains the five inputs, per the
  original design doc's intent — this was its actual target and simply
  never got built.
- The optimizer's candidate-location row
  (`housingOptLocationRowHtml`, `dashboard_decomp_housing_scenarios.js:1169-1179`)
  gains the same five inputs alongside the existing city-type/population
  selects, read into the `locations[]` payload in `runHousingOptimization()`
  (~line 1294-1298) the same way `city_type`/`population_size` are today.

One consistent pricing model, one place the multiplier logic lives
(`strategy_asset_service.py`), consumed identically by both UI surfaces —
matching how `city_type`/`population_size` already work today.

## 3. Move-label rendering fix

Investigation confirmed the backend numbers in the reported example
("Sell 2035 → Buy 2032... then Sell 2032 → Buy 2042") are **not** a
computation defect:

- `purchase_year < sale_year` (move 1) is a legitimate bridge-buy,
  reachable only when "never own two homes at once" is unchecked
  (`housing_optimizer.py` full-grid guard at line 310, narrowed-mode
  equivalent at lines 626-627).
- `sale_year_2 == purchase_year` (move 2 selling the move-1 home the same
  year it was bought) is a legitimate immediate-flip boundary case —
  `sale_year_2`'s floor is `anchor.purchase_year` (line 329), and
  `sale_year_2` always means "sell the home bought in move 1," never the
  original home (confirmed via `_apply_candidate` line 279 pointing that
  step at `home_sale.py`'s `apply_next_housing_sale`).

The actual defect is in `housingOptMoveText()`
(`dashboard_decomp_housing_scenarios.js:1232-1239`), which unconditionally
renders `"Sell ${sale_year} → ${action} in ${state}"` regardless of which
year is earlier, and never says *which* home is being sold (the original
home for move 1, the move-1 home for move 2). Fix, frontend-only:

- Render each move's transactions in true chronological order (if
  `purchase_year < sale_year`, show the buy first).
- Label which home each transaction refers to — e.g. "Buy in Illinois
  (2032)" then "Sell original home (2035)" for move 1, "Sell Illinois home
  (2032)" for move 2, rather than a bare "Sell"/"Buy" that reads as
  referring to the same property throughout.
- When a bridge/overlap period exists (`purchase_year < sale_year`, or
  `purchase_year_2 < sale_year_2`), add an inline note: "own both homes
  {earlier}–{later}."
- Apply the same treatment to the alternatives table rows, which use the
  same `housingOptMoveText()`.

## 4. No forced-purchase assumption + concurrent dual-location moves

The backend already auto-searches buy vs. rent-indefinitely as an
emergent outcome for both moves (`purchase_year`/`purchase_year_2 = None`
means rent indefinitely, already explored by the grid/narrowed search per
`housing_optimizer.py`'s module docstring) — that part isn't actually
broken, just not visible/controllable from the UI. The real gap is that
the model only ever represents **one** occupied location at a time
(`_location_timeline()`, lines 462-475, builds a strictly sequential,
non-overlapping timeline) — there's no way to model "buy in location A,
also rent in location B, both ongoing" to satisfy family presence in two
places simultaneously.

**Per-move action constraint (optional, UI-only default `Auto`):**

- Add an "Action" select next to each move's window: `Auto (search
  buy & rent)` / `Buy only` / `Rent only`.
- `Auto` (default) preserves exactly today's behavior — no backend
  change needed for this part beyond accepting the constraint and, when
  not `Auto`, skipping generation of the excluded branch
  (`generate_move1_candidates`/narrowed equivalents, and the move-2
  counterparts).

**Move-2 timing: Sequential (default) vs. Concurrent:**

- New UI choice, default `Sequential` (today's only behavior — move 2
  sells/replaces the move-1 home).
- `Concurrent with move 1` — new mode: keep the move-1 home/location as
  an ongoing residence (no sale), and add `location_2` as a second,
  simultaneous residence (bought or rented, per its own action
  constraint) starting at a chosen year.
- Backend: `HousingCandidate` gains `move2_mode: Literal['sequential',
  'concurrent'] = 'sequential'` (additive, default preserves existing
  candidates/tests unchanged). When `'concurrent'`, `_apply_candidate`
  builds an additional ongoing housing step for `location_2` (purchase or
  rent) instead of pointing `location_1`'s step at
  `apply_next_housing_sale` — both steps run through the same plan
  window, and the engine's normal cost aggregation across concurrent
  steps naturally produces the doubled housing cost, no separate cost
  model needed.
- `no_dual_ownership` does not apply to concurrent mode (it's a
  transitional-overlap guard; concurrent is an intentional standing
  arrangement) — the UI's "never own two homes at once" checkbox is
  disabled/ignored when `Concurrent` is selected, with a short inline
  note explaining why.
- Family-presence check (`family_presence_ok`) is extended: when
  `move2_mode == 'concurrent'`, the region/window requirement is
  satisfied if *either* concurrent location matches, not just the single
  active location on the (now branching) timeline.
- Concurrent mode is a real, evaluable option that always appears among
  ranked candidates when enabled -- but it cannot win the objective
  outright given the current anchor-eligibility architecture: a
  concurrent candidate's anchor must already satisfy `family_presence_ok`
  on its own before it is eligible to become an anchor at all (see
  `select_anchors`/`select_all_eligible_move1_candidates`, which draw only
  from already-filtered `move1_scored`), so concurrent's second home can
  only ever add cost on top of an anchor that already passes presence --
  it is provably not cost-competitive with the sequential-only anchor it
  extends. (Verified by two independent task-reviews and a live manual
  smoke test; see `.superpowers/sdd/progress.md`.)

## Testing

- `tests/frontend/housing_optimize_panel.test.mjs` — extend for the state
  dropdowns, five new candidate-location fields, and the move-label
  chronological/labeling fix.
- Backend tests for `housing_optimizer.py` — new cases for the five
  `Location` fields flowing into `_estimate_for_location`, the
  `move2_mode='concurrent'` candidate generation and scoring path, and
  the per-move action constraint skipping the excluded search branch.
- `strategy_asset_service.py` — extend existing
  `housing_state_estimate_payload` tests for the five-characteristic
  multipliers and the condo/townhome HOA/maintenance adjustment, matching
  the illustrative values in the referenced 2026-09-09 design doc.

## Out of scope

- Sourcing real market data for the multiplier tables (doc already notes
  they're editable starting points, not sourced).
- More than two concurrent locations, or concurrent mode on move 1 (only
  move 2 can be concurrent with move 1, per the request).
- Changing `FamilyPresence` to carry more than one region — concurrent
  mode's dual-location check works against the existing single-region
  field by testing both active locations against it.
- `move2_mode='concurrent'` candidate generation ships for `search_mode='full'`
  only in this pass. `search_mode='narrowed'`'s coordinate/pattern search
  (`_coordinate_search_2d`/`_coordinate_search_1d`) is a separate, more
  intricate code path; concurrent mode there is deferred to a follow-up
  rather than risked in this change. The UI disables "Concurrent" whenever
  "Narrowed search" is selected, with an inline note, rather than silently
  ignoring the combination. `move2_strategy='cross_product'` is likewise
  untouched — concurrent candidates are generated independently of, and in
  addition to, whatever the sequential path (anchored or cross_product)
  produces.
