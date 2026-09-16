# ZIP-Code Screening for Housing Optimization

**Date:** 2026-09-15
**Status:** Approved design, not yet implemented
**Backlog item:** 322
**Source methodology:** `ZIP_Code_Screening_Design_Spec.pdf` — "ZIP-Code Neighborhood Screening Score Framework", Rev 2.1

---

## 1. Problem

The housing optimizer today ranks **2–4 hand-picked locations**. A "location"
(`src/housing/models.py`, `Location`) is eight criteria:

`state`, `city_type`, `population_size`, `bedrooms`, `bathrooms`,
`property_type`, `sqft_band`, `built_within_years`

It searches sale/purchase *years* across those locations. It cannot discover a
location the user did not already name.

Item 322 adds two criteria and a discovery capability:

- **Criterion 9 — distance:** a radius of 5 / 10 / 25 / 50 miles from an anchor
  ZIP, where the anchor is chosen from a top-200-US-cities-by-population
  dropdown or entered directly.
- **Criterion 10 — minimum quality score:** a 0–100 neighborhood score floor,
  per the attached methodology.

## 2. Constraint that shapes everything

`src/housing/plan_variant.py` shows what geography actually drives:

- `Location.state` → `residency_schedule` → `core.state_for_year` → state income tax
- `Location.city_type` + `Location.population_size` → `housing_state_estimate_payload`
  → `STATE_ESTIMATES` → cost estimate

A ZIP therefore does **not replace** those fields. It **resolves to** them. This
is the seam the whole design hangs on: ZIP handling lives entirely in a new
package and stops existing before the optimizer is called.

`optimizer.py`, `search.py`, `scoring.py`, `constraints.py`, and
`plan_variant.py` are **not modified**.

## 3. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Reduced metric set, not the full PDF model | Safety (50 pts) and most of Street Environment have no national ZIP-level source |
| D2 | Two-stage search: cheap table screen, then the existing engine | A 50-mile radius is ~300 ZIPs; the engine budget stays what it is today |
| D3 | Shortlist ranked by score + affordability, de-duplicated | Stage 1 decides what the engine may recommend, so it must yield genuinely different bets |
| D4 | Cross-state radii allowed, with the tax delta surfaced | `state` drives income tax; a ZIP over the line is often the highest-value find |
| D5 | Bundled static data snapshot | The planner is offline and deterministic; a housing search must not be the one feature needing network and API keys |

---

## 4. The score

### 4.1 Why it is not the PDF's score

Of the PDF's 100 points, **33 are nationally sourceable at ZIP granularity**:
the entire Stability component (30) plus Eviction Filing Rate (3) from Street
Environment. Safety (50) and the remaining Street Environment metrics (17)
depend on per-city crime, 311, and Continuum-of-Care feeds with no national
ZIP-level equivalent.

The PDF's *relative* weights among surviving metrics are preserved and
renormalized by ×100/33.

### 4.2 Neighborhood Stability Score (NSS)

Version string: `nss-1.0 (derived from ZIP Screening Framework 2.1, Stability subset)`

| Metric | Source | PDF pts | NSS weight | Direction |
|---|---|---|---|---|
| Owner-occupied housing % | ACS B25003 | 8 | 24.2 | higher better |
| Poverty rate | ACS S1701 / B14006 | 6 | 18.2 | lower better |
| Residential turnover (tenure) | ACS B25038 | 5 | 15.2 | longer better |
| Housing vacancy rate | ACS B25002 | 4 | 12.1 | balanced |
| Eviction execution rate | Eviction Lab | 4 | 12.1 | lower better |
| Eviction filing rate | Eviction Lab | 3 | 9.1 | lower better |
| Median household income | ACS B19013 | 3 | 9.1 | higher better |
| | | **33** | **100.0** | |

### 4.3 Mandatory disclosure

The UI carries a permanent, non-dismissible line wherever an NSS value appears:

> Measures housing and economic stability. Does not measure crime or safety.

A 0–100 number that resembles a safety score but is not one is the worst
failure mode available to this feature. It is not dismissible and not
abbreviated away in compact views.

### 4.4 Scaling

Per PDF §2.2, lower-is-better metrics use `Score = 100 × (1 − Percentile)`;
higher-is-better use `Score = 100 × Percentile`. Because the bundled table
contains all ~33k ZCTAs, percentiles are **computed exactly at build time**
rather than approximated. This part of the methodology is strengthened by the
bundling decision, not weakened.

Band thresholds from PDF §2.4 are retained (90+ Exceptional, 80–89 Very
Favorable, 70–79 Generally Favorable, 60–69 Mixed, 50–59 Below Average,
<50 Relatively Unfavorable), reading as *stability* bands.

### 4.5 University adjustment (PDF §5)

`UPI = enrolled students (ACS B14007) / total population`. Above 15%:

- Poverty is replaced with **non-student poverty** (ACS B14006).
- Student annual-lease churn is excluded from the tenure metric.

The PDF's other two UPI adjustments — ambient-population crime denominators and
police-call filtering — are Safety adjustments and are moot under the reduced
model. The reduced model therefore loses nothing here; the DeKalb 60115 case
still works.

### 4.6 Partial coverage

Eviction Lab coverage is incomplete. A ZIP missing a metric is scored on the
remaining weight, **renormalized**, and reports `coverage_pct`. ZIPs below
**70% coverage** are excluded from the shortlist and counted in the funnel
diagnostics.

Zero-filling is rejected: it would penalize rural ZIPs for a dataset gap rather
than for any property of the place.

### 4.7 Affordability index

`STATE_ESTIMATES` is keyed on state + city_type + population, so every ZIP in a
state sharing a `city_type` would receive an identical price estimate and the
affordability filter would have no discriminating power within a state.

Fix: the same ingest pulls **ACS B25077 median home value**. Each ZIP's ratio to
its state median becomes a price multiplier on the existing estimate. Same
source, no new dependency.

---

## 5. Architecture

```
src/housing/zip_screen/
  geo.py       ZCTA centroids, haversine, radius query, top-200 city table
  quality.py   NSS computation, percentile lookup, banding, UPI adjustment
  screen.py    Stage-1 funnel
  resolve.py   ZIP -> Location
  data/zip_metrics.csv
scripts/build_zip_metrics.py   offline ingest; NOT in the runtime path
```

### 5.1 resolve.py

Turns a ZIP into the `Location` the engine already understands:

- `state` — from the ZCTA record
- `city_type` — from population density (people/mi², via Gazetteer ALAND):
  `>= 3000` urban, `1000–3000` suburban, `200–1000` exurban, else rural.
  Thresholds are named constants in `models.py` beside the existing tunables.
- `population_size` — the ZIP's primary Census place population, falling back to
  ZCTA population.

`Location` gains one optional field, `zip_code: str | None`, carried for display
and traceability only. Nothing downstream reads it.

### 5.2 Stage-1 funnel (screen.py)

Ordered, with each step's surviving count recorded:

1. **Radius** — haversine from anchor centroid ≤ 5/10/25/50 mi *(criterion 9)*
2. **Coverage floor** — drop `coverage_pct < 70`
3. **Score floor** — `nss >= min_quality_score` *(criterion 10)*
4. **Affordability** — estimated price for the spec within `target_purchase_price_range`
5. **De-duplicate** — suppress a ZIP when an already-selected ZIP is within
   5 miles, in the same state, and within 5 NSS points
6. **Rank and promote** the top N (default 4, range 2–4)

De-duplication is **never silent**: collapsed ZIPs nest under their survivor as
"+N similar nearby" and are expandable.

### 5.3 Stage 2

The promoted ZIPs are resolved to `Location` objects and passed to
`optimize_housing` exactly as hand-picked locations are today.

---

## 6. API

### 6.1 `POST /api/housing/optimize`

`zip_search` and `locations` are **mutually exclusive**; sending both is a 400.

```json
{
  "zip_search": {
    "anchor": { "zip": "60521" },
    "radius_miles": 25,
    "min_quality_score": 70,
    "shortlist_size": 4,
    "property_spec": {
      "bedrooms": 3,
      "bathrooms": 2,
      "property_type": "single_family",
      "sqft_band": "1800_2500",
      "built_within_years": null,
      "target_purchase_price_range": [400000, 700000]
    }
  }
}
```

`anchor` accepts `{"zip": "..."}` or `{"city_id": "chicago-il"}` from the
top-200 table. `radius_miles` must be one of 5, 10, 25, 50.

Response gains:

```json
"zip_screen": {
  "schema": "zip_screen_v1",
  "score_model": "nss-1.0",
  "anchor": { "zip": "60521", "city": "Hinsdale, IL", "lat": 41.80, "lon": -87.93 },
  "radius_miles": 25,
  "funnel": { "in_radius": 312, "with_data": 289, "above_score": 41,
              "affordable": 22, "after_dedup": 9, "promoted": 4 },
  "shortlist": [
    {
      "zip": "60521", "city": "Hinsdale", "state": "Illinois",
      "distance_miles": 0.0, "nss": 89.7, "band": "Very Favorable",
      "components": { "owner_occupied": 92.1, "poverty": 95.4 },
      "coverage_pct": 100.0, "est_price": 612000,
      "cross_state": null, "promoted": true, "collapsed": []
    }
  ]
}
```

`cross_state` is non-null when the ZIP's state differs from the plan's current
state, carrying that state and how its retirement-income tax treatment differs.

Recommendation and alternative rows gain `location.zip_code` and `location.nss`.

### 6.2 `POST /api/housing/zip-screen`

Runs Stage 1 alone and returns the same `zip_screen` block. Backs the
"Preview shortlist" button, is testable without the engine, and lets a user
explore ~300 ZIPs at zero engine cost before spending an optimization run.

---

## 7. UI

A mode toggle at the top of the existing `housing-optimize-panel`:

- **Choose locations manually** — today's behavior, unchanged
- **Search by ZIP radius** — anchor (top-200 city dropdown, plus a free-ZIP
  escape hatch), radius select, minimum score (default **60**, the PDF's
  "Mixed" floor), shortlist size, and the property spec

"Preview shortlist" calls `/api/housing/zip-screen` and renders the ranked
table with the NSS disclosure line, component breakdown, distance, estimated
price, cross-state tax notes, and collapsed-neighbor expanders.

### 7.1 Empty results

When the funnel empties, report **where** it emptied and what would relax it:

> 312 ZIPs in range → 289 with data → 0 above score 85.
> Lowering the minimum score to 72 would return 6.

A bare "no results" on a ten-criteria search is unusable.

---

## 8. Error handling

| Condition | Behavior |
|---|---|
| Unknown / malformed ZIP | 400, named explicitly |
| `radius_miles` not in {5,10,25,50} | 400 |
| Both `zip_search` and `locations` | 400 |
| ZIP absent from metrics table | Screened out, counted in `funnel.with_data` |
| Shortlist empty | 200 with funnel diagnostics and a relaxation suggestion; no engine runs |
| Fewer than 2 survivors | 200 with the shortlist and an explanatory message; no optimization (the optimizer requires 2–4 locations) |

---

## 9. Testing

Every component above is a pure function over a static table.

- **Golden fixtures from the PDF:** 60521's Stability component reproducing
  ≈89.7 from the stated raw inputs; 60115's UPI adjustment moving poverty
  26.4% → ≈10.1%.
- **Renormalization:** a ZIP missing eviction data scores identically to one
  whose eviction metrics sit exactly at their own weighted mean.
- **Funnel ordering:** each step's count is correct and steps apply in the
  documented order.
- **De-duplication:** the 5mi / same-state / 5-point rule, including that
  collapsed ZIPs are returned rather than dropped.
- **Resolution:** density thresholds map to the expected `city_type`; a
  resolved `Location` is accepted unchanged by `optimize_housing`.
- **Contract:** mutual exclusivity, radius validation, empty-funnel payloads.

---

## 10. Out of scope

- Live listing inventory or any real-estate feed
- Crime, school, climate, or hazard data
- ZIP-level tax modeling beyond the existing state-granularity `residency_schedule`
- Automatic refresh of the bundled snapshot (manual, via the ingest script)
