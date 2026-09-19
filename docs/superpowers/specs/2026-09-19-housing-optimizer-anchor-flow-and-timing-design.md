# Housing Optimizer — Anchor Flow and Valuation Timing — Design

Date: 2026-09-19
Status: Draft for review
Backlog item: #331 (a) multi-anchor selection UX, (b) housing valuation timing
Amends: `docs/superpowers/specs/2026-09-16-housing-optimizer-refinement-design.md`
(all 17 tasks of its Part II plan are checked complete; this spec changes shipped code, not a plan in flight)
Reverses a prior choice recorded in: `documentation/archive/superpowers/plans/2026-09-09-housing-estimate-realism-and-dollar-convention-design.md` §4.3

## 1. Problem

Two unrelated defects in the same panel.

### 1.1 (a) Anchors are declared but not honoured

`run_multi_anchor_screen` (`src/housing/zip_screen/screen.py:340-402`) screens each
anchor, unions the survivors on ZCTA identity, dedups, sorts by
`(-nss, distance_miles, zcta)`, and promotes the global top `shortlist_size`:

```python
union = sorted(best.values(), key=lambda z: (-z.nss, z.distance_miles, z.zcta))
distinct = deduplicate(union, coords)
shortlist = [... for z in distinct[: max(0, int(req.shortlist_size))]]
```

Nothing in that path reserves a slot per anchor. A household that anchors on Denver
(to be near work) and Hinsdale (to be near family) and asks for a shortlist of four
can receive four Denver-metro ZIPs, because the Denver ZCTAs happen to score higher on
the NSS. The second anchor then contributes **zero** candidates, the optimizer never
evaluates a single move near family, and the results table gives no indication that
this happened — `nearest_anchor_zip` is on every row, but no row is missing, so there
is nothing to notice. The user's second stated requirement was silently discarded.

The default `shortlist_size` is 4 (`api.py:197`) and up to 5 anchors are accepted
(`api.py:126`), so the shortlist can be numerically too small to represent every
anchor even in principle.

### 1.2 (b) Future moves are priced in today's dollars

`src/housing/plan_variant.py:46-57`:

```python
def _estimate_for_location(loc: Location, housing_type: str) -> dict[str, Any]:
    payload, _status = housing_state_estimate_payload({
        'state': ..., 'type': housing_type, 'city_type': ..., 'population_size': ...,
        'bedrooms': ..., 'bathrooms': ..., 'property_type': ..., 'sqft_band': ...,
        'built_within_years': ...,
    })
    return payload['estimate']
```

`start_year`, `home_appr` and `inflation_general` are not passed. In
`housing_state_estimate_payload` (`strategy_asset_service.py:372-383`) the missing
`start_year` falls back to `0`, which makes `years_out = 0` in `estimate_housing_cost`
(`:313`), which skips the entire "Slice 1" today's-dollars → start-year-dollars
translation block (`:310-345`).

The resulting figures — `purchase_price`, `monthly_rent`, `insurance_annual`,
`utilities_annual`, `maintenance_annual` — are then written into
`next_housing_steps` with `start_year = move.acquisition_year`
(`plan_variant._purchase_step` / `_rent_step`, via `_step_for`). The engine reads
that field as *already being in start-year dollars*: `_next_housing_for_year`
(`deterministic_engine.py:179-213`) sets `base = start` and escalates from there,
and values the home at `price * (1 + home_appr) ** (year - start + 1)`. So a 2046
purchase is modelled as buying a 2026-priced house in 2046 and only then letting it
appreciate.

This is not a rounding-level error. At the `HOME_APPR_DEFAULT` of 3%/yr a move 20
years out is under-priced by ~45%. And because the understatement grows with the
horizon, it is **directionally biased in a way that corrupts the search itself**: the
optimizer is choosing between candidate years, and the later year always gets a
larger unearned discount. Every "move later" recommendation the panel has ever made
is suspect.

The same understatement flows into `lifetime_cost` (the objective), the down-payment
cash draw (`purchase_cash`), the mortgage principal, `next_housing_equity`, and
`next_housing_sale_*` at a second-move sale — so `net_worth` and `mc_success_rate`
are affected too, not just the displayed price.

## 2. Goals

- An anchor the user names is guaranteed to be represented in the candidate set the
  optimizer actually evaluates, or the user is told plainly that it could not be.
- Anchor selection becomes a deliberate, reviewable first step rather than six
  controls buried in a forty-field form, and the user sees and confirms the actual
  ZIPs before spending a multi-minute engine run on them.
- A move's cost is estimated as of the year the move happens, at the same rates the
  rest of the plan uses to escalate other future-dated costs, with no double counting
  against the engine's own within-step escalation.
- One pricing path. `src/housing/` and `src/housing_comparison.py` should not disagree
  about what a 2040 house costs.

## 3. Non-goals

- No change to the deterministic engine or Monte Carlo runner. Directive 3 of the
  2026-09-09 dollar-convention design still binds: `deterministic_engine.py` is not
  touched. §6 below is an estimator-side correction to what number gets written into
  a field, exactly as that design framed it.
- No change to the `OriginalHome` / `Move` / `HousingCandidate` model from the
  2026-09-16 spec §5.1. Both halves of this design are additive to it.
- No re-pricing of a user's hand-entered `next_housing_steps` values. If the household
  typed a purchase price, that number is theirs and stays (§6.6).
- No Phase 2 (keep-and-rent-out) work. This spec is orthogonal to 2026-09-16 §13.
- No new ZIP data build. Per-anchor quotas operate on the existing snapshot.
- No per-anchor radius. The 2026-09-16 decision log settled that ("Per-anchor radii
  add a control per anchor for a distinction users did not ask for") and this spec
  does not reopen it.

## 4. Relationship to the 2026-09-16 spec

The 2026-09-16 refinement design is **shipped**, not pending: all 100 checkboxes in
its Part II plan are checked, `housing_optimize_v2` is live, and
`frontend/js/dashboard_decomp_housing_optimizer.js` exists as that spec's §9.1
described. This spec therefore amends running code rather than redirecting a plan.

| 2026-09-16 element | This spec's relationship |
|---|---|
| §5.1 `OriginalHome`/`Move`/`HousingCandidate` | **Unchanged.** §6 changes what dollars a `Move` prices at, not the type. §5 changes how `Location`s are chosen before a `Move` is built. |
| §6.1 multi-anchor search ("Screening runs once per anchor and the results are unioned before dedup") | **Amended.** That paragraph specified the union and said nothing about per-anchor representation, which is precisely the gap in §1.1. §5.2 adds a promotion rule after the union. The union-then-dedup mechanism itself is kept. |
| §6.2 funnel | **Extended** by one stage name (`per_anchor_quota`) between `near_family` and `promoted`. No existing stage changes meaning. |
| §7.1 request `move1.search.shortlist_size` | **Removed** and replaced by `selected_zips` (§5.4). This is the pulldown the two-step flow makes redundant. |
| §9.2 layout table | **Restructured** into two steps (§5.3). The rows themselves and their field sets survive; they are redistributed across the steps and one field is dropped. |
| §9.6 `localStorage` persistence under `retirement.housing_optimizer.v1` | **Extended** with the step-1 selection. Its stated forward-compatibility rule — unknown keys ignored, missing keys defaulted — means no migration is needed. |
| §10 spending-screen parity | **One gap found and folded in** (§6.5): `lot_size_band` reached the seed rows but never reached the Estimate button's request body. |
| §13 Phase 2 (keep-and-rent-out) | **Untouched and unblocked.** Rental income would be priced in move-year dollars by the same helper §6.2 introduces, so this spec makes Phase 2 slightly easier, never harder. |
| §14 decision log | Two entries amended, recorded in §8. |

Nothing here contradicts the 2026-09-16 spec's *reasoning*; §1.1 is a case its §6.1
did not consider, and §1.2 is in a module its Phase 1 deliberately left alone.

## 5. Design for (a) — two-step anchor-then-search flow

### 5.1 Resolving "include at least one from each"

**Reading adopted:** *the promoted shortlist for a move must contain at least one
candidate ZIP whose nearest anchor is each of that move's anchors.*

The code supports this reading over the alternatives. Every `ScreenedZip` already
carries `nearest_anchor_zip`, assigned in `run_multi_anchor_screen:366-372` by
keeping, for each ZCTA, the anchor it is closest to. That field exists, is already in
the wire payload (`api.py:420`), and is already rendered — but it is currently only
*descriptive*. Making it *prescriptive* is a small, well-supported change, and it is
the only reading under which the phrase describes a defect that actually exists in
the shipped behaviour (§1.1).

Two alternatives were considered and rejected:

- *"One anchor represented in each result set"* — i.e. each of the ten ranked
  `candidates` rows must involve a different anchor. Rejected: the ranked list is
  ordered by an objective, and forcing anchor diversity into it would mean displaying
  a candidate that is not actually rank-ordered, which the 2026-09-16 spec explicitly
  avoided for family presence ("Soft ranking would let the optimizer recommend a move
  away from family on a small dollar edge"). Constrain the *input* set, report the
  *output* honestly.
- *"One per anchor per move"* — i.e. move 1 and move 2 must each draw from every
  anchor. This is implied by the adopted reading anyway, since each move has its own
  independent anchor list (2026-09-16 §6.1), so it is not a separate rule.

**This remains an open question (§7, OQ-1)** — it is an inference from the code, not
from a stated requirement, and the quota's failure mode (§5.2) is user-visible enough
that guessing wrong is cheap to correct but not free.

### 5.2 Per-anchor quota in the screen

A new stage between `near_family` and `promoted` in `run_multi_anchor_screen`:

```
in_radius → with_data → above_score → matching_area_type → under_population_cap
          → affordable → distinct → near_family → per_anchor_quota → promoted
```

Promotion becomes a two-pass fill over the deduped, score-ordered `distinct` list:

1. **Reserved pass.** For each anchor in the user's declared order, promote the
   highest-scoring `distinct` ZIP whose `nearest_anchor_zip` is that anchor. An anchor
   with no surviving ZIP is skipped and recorded in `unrepresented_anchors`.
2. **Open pass.** Fill the remaining slots from the rest of `distinct` in existing
   score order, exactly as today.

Score order within each pass is unchanged, so the rule costs nothing when the natural
top-N already covers every anchor — which is the common case for two nearby anchors,
and is why this has gone unnoticed.

`ScreenResult` gains `unrepresented_anchors: list[str]`, surfaced in
`screen_payload` and rendered above the shortlist as a warning, not an error:

> *No ZIP near 60521 (Hinsdale, IL) survived the screen. The shortlist covers your
> other anchors only. Widen the radius, lower the minimum score, or drop this anchor.*

Failing loudly here is the point. The current silence is the whole defect.

**Selection size floor.** The selection must be able to hold one per anchor, so the
step-1 UI enforces `len(selected_zips) >= len(represented_anchors)` before advancing.
With `shortlist_size` gone (§5.4) there is no longer a number that can be set too
small; the preview simply promotes `max(default_preview_size, len(anchors))` ZIPs and
the user selects from them.

### 5.3 The two steps

The panel becomes a two-step wizard inside the existing `<details>` element, with a
step indicator in the summary row. Both steps use the 2026-09-16 §9.2 field-cell
convention unchanged — label above control, horizontal flex row that wraps, help in
`#helpPanel` via `showHousingOptFieldHelp`, never inline.

**Step 1 — Where could you go?** Location only, for each enabled move.

| Row | Contents |
|---|---|
| **Move 1 — where** | Anchors (1–5) · Area type · Within (mi) · Min score · Max population |
| **Move 1 — what (price-shaping)** | BR · BA · Property type · Sqft · Lot size · Built within · Price max |
| **Consider a second move** | checkbox; when on, the two Move-2 rows mirroring the above |
| | **Find candidate locations** |

Pressing *Find candidate locations* calls the existing `POST /api/housing/zip-screen`
endpoint — once per enabled move — and renders a **selection table** in place of
today's read-only "Preview shortlist" output. Each row is a checkbox plus the columns
the 2026-09-16 spec §9.4 already defined for the preview (ZIP, city/state, score,
band, distance, area type, population, estimated price, and family distance when
family presence is on), with one column added: **Anchor**, showing
`nearest_anchor_zip`. Rows promoted by the reserved pass carry a small *"covers
{anchor}"* badge so the user can see the quota working.

Rows are pre-checked exactly as the quota promoted them, so *Continue* with no
interaction reproduces today's behaviour plus the quota. The user may check
additional ZIPs from the `all_passing` set or uncheck promoted ones, subject to the
§5.2 floor. Above the table, a per-anchor coverage line:
`Aurora, CO — 3 ZIPs · Hinsdale, IL — 1 ZIP · Madison, WI — none found`.

Step 1 cannot be left until every enabled move has at least one selected ZIP.

**Step 2 — What would it cost?** Everything the search needs once the places are
fixed.

| Row | Contents |
|---|---|
| **Selected locations** | read-only summary chip per move: `Move 1: 80024, 80122, 60521 · Edit` (returns to step 1) |
| **Objective & constraints** | Objective · Search mode · Move-2 strategy · Never own two homes at once |
| **Purchase assumptions** | Down payment % · Mortgage rate % |
| **Family presence** | Enable · Family ZIP · Within · From year · Through year |
| **Current home** | Sell/Keep/Auto · Earliest sale year · Latest sale year |
| **Move 1 — when** | Earliest year · Latest year · Action |
| **Move 2 — when / mode** | (when enabled) Earliest · Latest · Action · Concurrent · Anchor count |
| | **Run optimization** |

The 2026-09-16 §8 validation rules are unchanged and simply fire on whichever step
owns the offending field; rule 6 (anchor count) becomes a step-1 rule, everything
else a step-2 rule. The Run button lives on step 2 and is disabled while any rule on
either step fails, so the split cannot be used to smuggle an invalid request through.

### 5.4 The pulldown that goes away

**Removed: the per-move "Shortlist size" `<select>`** —
`housingOptMove1ShortlistSize` / `housingOptMove2ShortlistSize`, built from
`HOUSING_OPT_SHORTLIST_SIZES` in `housingOptMoveWhereRowHtml()`
(`dashboard_decomp_housing_optimizer.js:1029-1035`), and carried on the wire as
`move{n}.search.shortlist_size`.

Its help text states its entire job: *"How many screened ZIPs are promoted into the
optimizer for this move."* That question only needs asking because, in today's
single-step form, the user never sees the ZIPs. It is a blind proxy for a choice they
would rather make directly — a number standing in for a selection.

Once step 1 ends with the user ticking the ZIPs they want, the count **is** the
selection: `len(selected_zips)`. Keeping the pulldown would be strictly worse than
removing it, because the two controls could disagree (pick six ZIPs with the size set
to four — which four?), and any rule resolving that disagreement would override an
explicit user choice with an implicit one.

`shortlist_size` therefore leaves the request schema entirely, and
`MultiAnchorRequest.shortlist_size` becomes an internal preview cap rather than a
user-facing knob.

**Explicitly not removed: "Move-2 strategy."** It is tempting — `anchored` +
`anchor_count` exist to bound combinatorics — but the reasoning does not hold.
`select_anchors` (`candidates.py:192-199`) selects from `move1_scored`, i.e. *scored
move-1 candidates* (location × acquisition year × action × disposition), not
locations. Bounding the location set in step 1 does not bound the year axis, so the
`MOVE2_CROSS_PRODUCT_CAP` trade this pulldown exposes is still real. It stays on step
2. Whether it could be replaced by a single automatic "widen until the cap" rule is
**OQ-4**.

### 5.5 Wire changes

`move{n}.search` drops `shortlist_size` and gains:

```jsonc
"selected_zips": ["80024", "80122", "60521"]   // 1-10, from step 1's selection
```

`optimize_housing_from_request` (`api.py:301-335`) stops taking the screen's own
shortlist and instead filters the screen result to the requested ZIPs:

- Every entry of `selected_zips` must appear in that move's `all_passing`. One that
  does not returns `{"success": false, "error": ...}` naming the ZIP — a stale
  `localStorage` selection made against different filters must not silently degrade
  into a smaller search.
- `_resolve_screened_locations` is otherwise unchanged; it just receives the filtered
  list rather than `screen.shortlist`.

The response's `zip_screens.move{n}` gains `unrepresented_anchors` and a
`per_anchor_quota` funnel count. The schema id stays `housing_optimize_v2`: the
2026-09-16 spec already established there is one consumer and it ships in the same
change, and the shape is additive apart from one removed optional field. Bumping to
v3 for that is churn — **OQ-5** records the dissent.

`localStorage` (§9.6) gains `selectedZips1` / `selectedZips2` and the current step
index, under the existing key, relying on that section's documented
ignore-unknown/default-missing rule.

## 6. Design for (b) — valuation as of the move year

### 6.1 Why it is the way it is, and what part of that to preserve

This behaviour has a traceable origin. The 2026-09-09 dollar-convention design
(commit `9f9886a`, "Housing estimate Slice 1") drew a line that is still correct:

| | What it does | Where |
|---|---|---|
| **Ongoing (within-step) escalation** | costs grow by CPI each year the step is active; home value grows by `home_appr` post-purchase | `deterministic_engine.py`'s year loop — **"Already correct. Not touched."** |
| **Estimator (pre-step) translation** | one-time projection of a today's-dollars estimate forward to `start_year` | `estimate_housing_cost` — **"the entire scope of this design"** |

Its directive 3 was explicit: *"This entire design is a one-time, at-estimate-time
correction to what number gets written into a field. It is not an engine change."*
The engine "has always assumed the field already holds the right start-year number."

That same document then predicted this exact bug, in §4.3, while designing the
comparison sweep:

> *"A sweep candidate that changes a step's `start_year` must **re-derive**
> `purchase_price` for the new year via `estimate_housing_cost`, not reuse the parsed
> value — otherwise the sweep would silently reintroduce this design's own bug (a
> stale-year price) inside the fix for it."*

`src/housing_comparison.py:178-210` heeded it: `priced_step` passes `start_year`,
`home_appr` and `inflation_general` on every re-priced point. `src/housing/` did not.
The optimizer track (2026-09-09 housing-optimization, a sibling design) adopted
`housing_state_estimate_payload` as a *location → cost* lookup and never threaded the
year through, because in the original model a `Location` had no year attached to it —
the year lived on the candidate. The 2026-09-16 refinement then made the
`Move.acquisition_year` the natural place to get it from, and nobody revisited
`_estimate_for_location`.

**So this is not a considered decision to hold prices in today's dollars.** It is the
§4.3 trap, sprung in the one module that design did not audit. There is no
simplicity or double-counting rationale to weigh against reversing it.

**The constraint that must survive the reversal** is the one directive 3 protects:
the engine escalates *from* `start_year`. Writing a move-year-dollars figure into a
step whose `start_year` is that same move year is exactly what the engine expects and
introduces **no** double counting. Escalating anywhere else — in the engine, or by
pre-inflating and also letting `_infl_ratio` run from an earlier base — would.

### 6.2 The fix

`plan_variant._estimate_for_location` becomes year-aware:

```python
def _estimate_for_location(loc: Location, housing_type: str, *,
                           start_year: int, home_appr: float,
                           inflation_general: float) -> dict[str, Any]:
    payload, _status = housing_state_estimate_payload({
        ...,                       # unchanged characteristic fields
        'lot_size_band': loc.lot_size_band,     # §6.5
        'start_year': int(start_year),
        'home_appr': float(home_appr),
        'inflation_general': float(inflation_general),
    })
    return payload['estimate']
```

`_purchase_step` and `_rent_step` already receive `start_year`; `_step_for` already
has `move.acquisition_year`. The two rates come from the engine config `c`, which
`_apply_candidate` already holds:

- `home_appr` ← `c['home_appr']`, falling back to `HOME_APPR_DEFAULT` (0.03)
- `inflation_general` ← `c['inf']`, falling back to `INFLATION_GENERAL_DEFAULT` (0.025)

These are the same two reads, from the same two keys, with the same two fallbacks,
that `housing_comparison.priced_step:204-205` performs. Threading `c` into
`_purchase_step`/`_rent_step` (or capturing it in the `_step_for` closure) is the only
structural change; the cost figures keep the same keys and shapes.

`_purchase_price_for_location` and `_effective_mortgage_rate` gain the same three
parameters. `_effective_mortgage_rate` does **not** escalate — a rate is not a
monetary quantity — it only needs the parameters because it shares the call.

### 6.3 Escalation methodology

Adopted wholesale from 2026-09-09 §3.2, because "consistent with how the rest of the
plan escalates other future-year costs" and "identical to `housing_comparison.py`" are
the same requirement, and that table is the answer to both.

| Field | Rate | Rationale |
|---|---|---|
| `purchase_price` | `home_appr` | The same rate the engine uses for the home's own post-purchase growth, so one rate governs value before and after the transaction with no seam at `start_year`. |
| `monthly_rent` | `inflation_general` (CPI) | The engine escalates rent at CPI once the step is active (`_infl_ratio`); using CPI for the pre-step translation makes rent uniform from today through the life of the step. |
| `insurance_annual`, `utilities_annual`, `maintenance_annual` | `inflation_general` (CPI) | Flat recurring dollar costs, not value-linked. The same rate the engine already applies within the step, one segment earlier. |
| `re_tax_pct`, `hoa_pct`, `mortgage_rate_pct`, `down_payment_pct` | **not escalated** | Percentages and rate assumptions, not monetary quantities. They apply to an already-escalated price, so escalating them too would compound twice. |

Base year is `plan_start = platform_runtime.today().year`, which
`estimate_housing_cost:315` already computes and which `data_io.py` sets `c['plan_start']`
from identically — so `years_out` lines up with the `year - start` the engine later
uses for the same step. `years_out = max(0, start_year - plan_start)`: a move in the
current year or the past is not discounted backwards.

No new rate, no new assumption, no new constant. Every number already exists.

### 6.4 Every call site using a present-day estimate for a future year

| # | Site | What is wrong | Fix |
|---|---|---|---|
| 1 | `plan_variant._estimate_for_location` (`:46-57`) | No `start_year`/`home_appr`/`inflation_general`. **Root cause.** Feeds `_purchase_step`'s insurance/utilities/maintenance/`re_tax_pct`/`hoa_pct`, `_rent_step`'s `monthly_rent`/insurance/utilities, `_effective_mortgage_rate`, and `_purchase_price_for_location` tier 3. | §6.2. |
| 2 | `_purchase_price_for_location` tier 2 — `Location.est_price` (`:63-72`) | `est_price` comes from `screen.estimate_price` → ACS `median_home_value` ratio × `state_median_home_value`, i.e. **today's ACS dollars**, and is used raw as the engine's cost basis. This tier was added deliberately by `2026-09-16-housing-financing-and-zip-ux-design.md` §1 to make the cost basis match the displayed ZIP price — correct in intent, but it imported the screen's today's-dollars basis into a future year. | Escalate `est_price` by `home_appr` over `move.acquisition_year - plan_start` at the point of use in `plan_variant`. Do **not** escalate it in `screen.py` — see §6.6. |
| 3 | `_purchase_price_for_location` tier 1 — `target_purchase_price_range` midpoint (`:66-68`) | The user types a shopping budget in today's dollars and the midpoint becomes a future year's purchase price unescalated. | Escalate the midpoint by `home_appr` on the same basis, **and label the field "Price max (today's $)"** so the input's basis is stated rather than assumed. See OQ-2. |
| 4 | `screen.estimate_price` / the `affordable` funnel stage (`screen.py:85-95, 274-295`) | Compares a today's-dollars ZIP estimate against a today's-dollars user range. **Internally consistent — no dollar error.** But `est_price` leaks out of the screen into sites 2 and 5, where it stops being consistent. | No arithmetic change. `ScreenedZip` gains `est_price_basis_year` (= `plan_start`) so no downstream consumer can mistake its basis again. |
| 5 | `results.py` — displayed `est_price` and the `estimate_monthly_pi_payment` display figure | The results row shows a today's-dollars price for a future-year move, next to an objective computed (after this fix) on the escalated price. Internally inconsistent once §6.2 lands. | Display the **move-year** price, and add the today's-dollars figure as secondary text: `$742,000 in 2046 ($539,400 today)`. The P&I estimate uses the escalated price and therefore changes too. |
| 6 | `dashboard_decomp_housing_scenarios.estimateHousingFromState` (`:140-280`) | **Correct at the moment of the click** — it passes `start_year`, `home_appr` and `inflation_general` (`:271-274`). But the value is frozen into the CSV, so editing `start_year` afterwards leaves a stale-year price with no indication. This is the Spending-projection half of the backlog item. | Not a re-pricing change. On a `start_year` edit where a previously-estimated price exists, show an inline *"Estimated for {old year}. Re-estimate for {new year}?"* prompt with a one-click re-run. Never silently overwrite a user's number (§3). |
| 7 | `estimateHousingFromState` request body (`:265-275`) | `lot_size_band` is absent, although 2026-09-16 §10 added the seed row and `estimate_housing_cost` accepts the parameter. The Spending screen therefore prices every home at the neutral `quarter_half` multiplier while the optimizer honours the user's choice. | Add it to the body. Closes a §10 parity gap. |

Sites 1, 2 and 3 are the fix proper; 5 makes it visible; 4, 6 and 7 stop it recurring.

### 6.5 Where the escalation must *not* go

- **Not in `deterministic_engine.py`.** Directive 3. The engine's
  `infl = _infl_ratio(year, base=start)` and
  `home_value = price * (1 + home_appr) ** (year - start + 1)` are correct and stay
  byte-for-byte.
- **Not in `screen.py`'s funnel.** The `affordable` stage is a today's-dollars
  comparison on both sides (§6.4 site 4). Escalating one side there would break a
  currently-correct filter, and escalating both would be a no-op with extra arithmetic.
  The screen stays a today's-dollars shopping tool; `plan_variant` is the boundary
  where a location acquires a year.
- **Not in `housing_comparison.py`.** Already correct. It is the reference
  implementation for §6.2, not a target of it.
- **Not on a user-entered `next_housing_steps` price.** `data_io.py` parses it flat,
  on purpose. Site 6 prompts; it does not rewrite.

### 6.6 Consequences to state plainly

**Every optimizer result changes.** Objectives, rankings, and very likely the rank-1
recommendation. Any golden-master fixture covering the optimizer must be regenerated,
and the PR description must say so explicitly — the same treatment
`2026-09-16-housing-financing-and-zip-ux-design.md` §1 gave the `est_price` tier, and
for the same reason: a large recompute drift that is not called out reads as a
regression.

**The bias reverses in a specific direction.** Today the optimizer systematically
prefers later moves, because a later move buys a today's-priced house further in the
future and collects the appreciation for free. After the fix, moves are compared on
equal footing. Expect recommendations to shift earlier; that is the fix working, not a
new bug.

**Cross-candidate comparability is not harmed.** Each candidate is priced in its own
move year, which reads odd in isolation, but the objective is not the price — it is
`net_worth` / `lifetime_cost` / `mc_success_rate` computed by the engine over the whole
plan, all already nominal and already comparable across candidates. Pricing each
candidate at its own year is what makes those objectives comparable, not what breaks
them.

**Phasing.** This belongs to **neither** phase of the 2026-09-16 spec. Phase 1 is
shipped and explicitly declared "No engine changes. `src/projection_stages/` is not
modified in Phase 1" — a constraint this spec also honours, but it is a separate
layered fix, not an unfinished Phase 1 task. It is independent of Phase 2. It should
ship **before** §5, because §5's step-1 selection table displays `est_price` and
should display it on the corrected basis from the start.

## 7. Open questions

**OQ-1 — "at least one from each" semantics.** §5.1 resolves this by inference from
`nearest_anchor_zip` and the §1.1 failure mode, not from a stated requirement. The two
rejected readings are recorded there. **Confirm before implementing §5.2** — the
quota's reserved pass is cheap to build and cheap to change, but the funnel stage name
and the `unrepresented_anchors` payload field would both churn.

**OQ-2 — is `target_purchase_price_range` a today's-dollars budget or a move-year
budget?** §6.4 site 3 assumes today's dollars, because it is a shopping figure typed
next to bedrooms and square footage, and because `screen.py`'s `affordable` stage
already compares it against a today's-dollars estimate. But a user who types "we can
spend $700k when we move in 2046" means move-year dollars, and both readings are
plausible from the current label. The recommendation is to state the basis in the
label rather than infer the intent. **Needs a decision**; it changes both the
escalation at site 3 and the field's help text.

**OQ-3 — retroactive scope beyond the listed sites.** Confirmed in scope and listed:
`plan_variant` (sites 1–3), `results.py` (5), the Spending Estimate button (6–7).
Confirmed out of scope and already correct: `housing_comparison.py`, the engine,
`data_io.py`'s parsed user values. **Not yet audited:** (i) `tools/housing_lab.py`,
which builds optimizer payloads and may carry its own assumptions about the price
basis; (ii) the Planning Workbench strategy integration
(`2026-09-17-planning-workbench-strategy-integration-design.md`), if it surfaces
optimizer output anywhere; (iii) any saved scenario in `localStorage` or a plan CSV
holding an optimizer-derived price, which is now known to be understated and which
nothing will correct on its own. (iii) in particular may warrant a one-time notice
rather than a silent change of meaning.

**OQ-4 — should "Move-2 strategy" survive at all?** §5.4 keeps it, because bounding
locations in step 1 does not bound the year axis that `MOVE2_CROSS_PRODUCT_CAP`
actually guards. But a single automatic rule — try `cross_product`, fall back to
`anchored` when the pre-flight estimate exceeds the cap, and say which ran — would
remove a pulldown *and* the `anchor_count` number input, and would turn a
`ValueError` the user must decode into a decision the system makes and reports. That
is a larger UX claim than item #331 asked for, so it is flagged rather than folded in.

**OQ-5 — schema version.** §5.5 keeps `housing_optimize_v2` on the grounds that the
change is additive apart from one removed optional field and there is exactly one
consumer shipping in the same change. The counter-argument is that
`shortlist_size` → `selected_zips` is a genuine semantic change to how the candidate
set is chosen, and the 2026-09-16 spec's own precedent was to bump rather than shim.
**Cheap either way; decide before the API task, not during it.**

**OQ-6 — step-1 preview cost.** Step 1 runs `POST /api/housing/zip-screen` once per
enabled move on every *Find candidate locations* press. That endpoint does no engine
runs (pure table math) so it is fast, but the two-step flow makes it a required
round-trip rather than an optional preview. Confirm this is acceptable on a cold
`load_table()`, or cache the table across the two calls.

## 8. Decision log

| Decision | Choice | Rationale |
|---|---|---|
| "At least one from each" | Per-anchor reserved slot in the promoted shortlist | The only reading under which the phrase names a defect that actually exists; `nearest_anchor_zip` already exists to key it on. Amends 2026-09-16 §6.1. |
| Unrepresentable anchor | Warn and continue, never fail the run | A run with three of four anchors covered is still useful; silently dropping the fourth is the bug being fixed. |
| Quota placement | In `screen.py`, after dedup, before promotion | Dedup must run on the full union first or the quota could reserve a slot for a ZIP that dedup would have collapsed. |
| Pulldown removed | Per-move "Shortlist size" | It is a blind proxy for a selection the user makes directly in step 1; keeping both invites a disagreement with no non-arbitrary resolution. |
| "Move-2 strategy" | Kept, on step 2 | It bounds the year axis, which step 1 does not touch. Flagged as OQ-4. |
| Escalation rates | `home_appr` for value, CPI for recurring costs, nothing for percentages | Verbatim from 2026-09-09 §3.2, which is what `housing_comparison.py` already implements. No new assumption. |
| Escalation location | `plan_variant`, at the point a `Location` acquires a `Move`'s year | The engine escalates from `start_year` (directive 3); the screen is a today's-dollars shopping tool. `plan_variant` is the only boundary where both facts hold. |
| Screen funnel | Stays in today's dollars | Both sides of the `affordable` comparison are today's dollars; it is already correct. |
| Basis disclosure | `est_price_basis_year` on `ScreenedZip`; results show both years | The defect was possible because a number's basis was implicit. Making it explicit is what stops a third recurrence. |
| Spending-screen staleness | Prompt to re-estimate, never silently re-price | A hand-entered or previously-accepted number belongs to the user. |
| Phasing relative to 2026-09-16 | Separate layered fix; ship (b) before (a) | Phase 1 is shipped; Phase 2 is orthogonal. (a)'s selection table displays `est_price`, so it should display the corrected value from day one. |

## 9. Implementation phasing and expected Claude Code usage

Relative estimates against a 5-hour session on the Pro plan, per the repo's design-doc
convention. **Check `/usage` against these as the plan executes** — they are
proportions, not measurements.

| Phase | Scope | Model · effort | Tool-use turns | Context drivers | Weight |
|---|---|---|---|---|---|
| **B1** | §6.2 — thread `start_year`/`home_appr`/`inflation_general` through `plan_variant`; sites 1–3 | sonnet · medium | 6–10 | `plan_variant.py` is ~250 lines and self-contained; `strategy_asset_service.estimate_housing_cost` is read-only reference | **Light** |
| **B2** | Unit tests for B1: escalation applied, rates correct per field, percentages untouched, `years_out=0` for a current-year move | sonnet · medium | 5–8 | New test file; mirror `tests/` housing patterns | **Light** |
| **B3** | §6.4 sites 4–5 — basis-year field, results display both years, P&I recompute | sonnet · medium | 6–10 | `results.py` + the results-rendering block of the optimizer JS | **Light–moderate** |
| **B4** | **Golden-master regeneration and diff review.** Every optimizer fixture moves. | opus · high | 10–20 | **The expensive step.** Large fixture diffs, and each delta must be *explained*, not just accepted | **Heavy — flagged** |
| **B5** | §6.4 sites 6–7 — Spending screen re-estimate prompt and `lot_size_band` | sonnet · medium | 5–8 | `dashboard_decomp_housing_scenarios.js` is ~1,800 lines; read only the `estimateHousingFromState` region | **Light–moderate** |
| **A1** | §5.2 — per-anchor quota, `unrepresented_anchors`, funnel stage | sonnet · medium | 6–10 | `screen.py` is ~400 lines and readable whole | **Light** |
| **A2** | §5.5 — `selected_zips` on the wire, validation, `api.py` filtering | sonnet · medium | 6–10 | `api.py` ~500 lines; server-side validation must mirror client order | **Light–moderate** |
| **A3** | §5.3 — the two-step panel, selection table, step gating, persistence | opus · high | 15–25 | `dashboard_decomp_housing_optimizer.js` restructure; **plus the three Python functional tests that read the panel JS as text** (`test_zip_screen_panel_functional.py` and siblings) — the 2026-09-16 plan's Global Constraints flag these as the standard trap here | **Moderate–heavy** |
| **A4** | Frontend tests: quota rendering, selection round-trip, stale-selection rejection, step gating | sonnet · medium | 6–10 | `node --test` plus the Python functional trio | **Moderate** |

**Disproportionately expensive steps and how to scope them down:**

- **B4 (golden masters)** is the single largest cost and the one most likely to turn
  into a repeated test-fix cycle. Scope it down by regenerating **one** representative
  fixture first, hand-verifying its delta against a spreadsheet check of
  `(1 + home_appr) ** years_out`, and only then batch-regenerating the rest. Do not
  enter a regenerate-run-regenerate loop; a wrong rate will look exactly like a right
  one at scale.
- **A3 (panel restructure)** risks a broad-search blowup if the three text-asserting
  Python functional tests are discovered late. Read them *first*, before touching the
  JS, and treat their assertions as the interface contract. The 2026-09-16 plan
  records that a similar move broke 24 of them.
- **Sequencing** is itself a cost control: B1–B5 before A1–A4 means A3 renders correct
  prices on first write and is never re-opened to fix them.
