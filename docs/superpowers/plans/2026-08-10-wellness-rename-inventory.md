# wellness → healthcare rename inventory (F5.2 / Phase 3 Task 7)

**Produced:** 2026-08-17. **Status: decisions taken 2026-08-17 (see "Decisions" at the
bottom). Nothing has been renamed yet.**

No client values appear in this document. `/input/*` is gitignored real client data;
only structural keys are recorded.

---

## Headline: the plan's scoping is wrong, and in the expensive direction

Phase 3 says "**at least three distinct namespaces** … and they are NOT one rename", then
lists MC shock params, `pre65_wellness_premium`, and prose. The actual inventory has
**four**, and the one it omits is by far the largest and the only genuinely dangerous one.

| # | Namespace | Occurrences | In the plan? | Safe to rename at rest today? |
|---|---|---|---|---|
| 1 | **Section name `Wellness`** | 44 `src/` readers, ~50 rows across 3 files | **NO** | **NO — machinery does not exist** |
| 2 | MC shock params (`wellness_cost_shocks`, `_shock_annual_prob`, `_shock_mean_cost`) | 3 rows, `client_policy.csv` | yes | yes |
| 3 | `pre65_wellness_premium` / `wellness_premium` category ids | 8 rows across 4 files | yes | yes, with care (see below) |
| 4 | Prose in `notes` columns | 24 rows across 5 files | yes | yes (no behavior) |

### Why namespace 1 blocks the phase as written

`migrate_rows` supports exactly two rename kinds: `_LABEL_RENAMES`, keyed by
`(section, subsection)`, and `_SUBSECTION_RENAMES`, keyed by `section`. **There is no
`_SECTION_RENAMES` and no code path that renames a section.**

So renaming the `Wellness` section at rest is not a data edit — it needs a new transform
kind first. And the safety argument the whole phase rests on does not hold for it:

> "Renaming CSV labels while leaving the Python identifiers alone is safe **only** because
> `migrate_sectioned_data` maps old→new on load, so the engine keeps reading the key it
> always read."

That is true for labels and subsections. For sections it is currently false — nothing
remaps them. Rewriting `Wellness` → `Healthcare` in the CSVs today would silently break all
44 readers in `src/`, which are positional lookups of the form:

```
src/data_io.py:841:  c['partb'] = _n(_v(data,'Wellness','Medicare','part_b_base_premium_monthly','185'), 185)
```

`_v()` returns the **default** when the section is missing. So every one of these would fall
back to its hardcoded default rather than raising: Medicare Part B would quietly become 185,
the ACA benchmark premium 32000, out-of-pocket 8000. A silent revert to defaults on real
client data is the worst possible failure mode here — it produces a plausible plan that is
not the client's plan, and no test that does not pin those dollars would notice.

## Recommended scope

**Do namespaces 2, 3 and 4. Do not do namespace 1 in this phase.**

That keeps Phase 3's original safety argument intact — every rename below is a label the
load-path migration already knows how to remap — and it leaves the section rename as its own
scoped piece of work, which needs `_SECTION_RENAMES` plus a guard test proving `_v()` does
not fall through to defaults for any migrated section.

### Namespace 2 — MC shock params (`client_policy.csv`, section `Model Constants`, subsection `Monte Carlo`)

| old label | proposed new label | `src/` reader |
|---|---|---|
| `wellness_cost_shocks` | `healthcare_cost_shocks` | `src/data_io.py:1734` |
| `wellness_shock_annual_prob` | `healthcare_shock_annual_prob` | `src/data_io.py:1736` |
| `wellness_shock_mean_cost` | `healthcare_shock_mean_cost` | `src/data_io.py:1738` |

Each reader keeps its current Python identifier; the load-path remap feeds it the renamed
row. Note `planning_engines.py:2857,3624` and `sheets_stress.py:83` use
`sampled_wellness_shock_*` — those are **computed result keys, not plan-data labels**, and
are out of scope by the "no Python identifier renames" rule.

### Namespace 3 — spending category ids

| file | section | subsection | old label | proposed new label |
|---|---|---|---|---|
| `client_spending_taxonomy.csv` | `Wellness` | `Healthcare Premium` | `pre65_wellness_premium` | `pre65_healthcare_premium` |
| `client_spending_taxonomy.csv` | `Wellness` | `Healthcare Premium` | `wellness_premium` | `healthcare_premium` |

⚠ **`client_spending_budget.csv`, `client_spending_budget.recovery_seed.csv` and
`client_spending_rules.csv` are flat tables, not sectioned data.** They carry
`pre65_wellness_premium` in a `category` column, and `migrate_rows` operates on
`(section, subsection, label)` triples — it will not touch them. Renaming only the taxonomy
side would break the join between a budget line and its category. Either the transform is
extended to cover the flat category columns in the same pass, or namespace 3 is deferred
too. **This is a second gap in the plan as written.**

`deterministic_engine.py:1319` reads the literal string `'pre65_wellness_premium'` in a
category-id list, so it depends on the same remap.

### Namespace 4 — prose

24 rows across `client_spending.csv`, `client_spending_aliases.csv`,
`client_spending_budget.csv`, `spending_category_map.csv`, `ytd_transactions.csv`, plus the
`client_household.csv` header comment and the `Wellness Budget Detail` subsection label.
Changes no behavior. Note that `Wellness Budget Detail` is a *subsection*, which
`_SUBSECTION_RENAMES` **can** handle — it is the only display-facing string here that is
also a real key.

---

## Decisions (2026-08-17)

**The domain model, as stated by the plan owner, corrects this document's framing:**

> Wellness is the highest group in the hierarchy. Healthcare applies to premiums, and other
> doctor, dentist, etc. expenses.

So `Wellness` is the **parent** and `Healthcare` is the medical subset. That reframes
namespace 1 entirely: the section name is not "too risky to rename", it is **already
correct**. The 44-reader / silent-default analysis above still stands as a reason never to
rename it casually, but it is no longer the operative reason.

The data agrees with the hierarchy. `Wellness | Wellness Budget Detail` holds
`gym_fitness`, `health_club`, `massage_bodywork`, `supplements`, `vitamins_supplements` and
`exercise_health_equipment` alongside `dentist`, `hospital_bills` and `prescription_drugs`.
Only a Wellness umbrella covers both.

| # | Namespace | Decision |
|---|---|---|
| 1 | Section `Wellness` | **KEEP — correct by design.** Not deferred, not pending machinery. Do not re-open. |
| 2 | MC shock params | **RENAME** to `healthcare_*`. A $150k mean-cost shock is a medical event, not a gym membership. |
| 3 | Category ids | **RENAME** to `*_healthcare_premium`, **including the flat columns** — see the corrected file list below. |
| 4 | Prose | **Reviewed case by case. Net effect: rename nothing.** See below. |
| — | `Wellness Budget Detail` subsection | **KEEP as one subsection.** Not split, not renamed. It legitimately holds both kinds under the Wellness parent. |

### Namespace 3 — corrected file list

The body of this document listed three flat files. There are **four**. `migrate_rows` reaches
none of them, so all four move in the same pass as the taxonomy rename:

| file | column | note |
|---|---|---|
| `client_spending_budget.csv` | `category` | budget line → category join |
| `client_spending_budget.recovery_seed.csv` | `category` | same, seed copy |
| `client_spending_rules.csv` | `category` | mapping rule target |
| **`client_spending_aliases.csv`** | **`category_id`** | **missed on the first pass.** Two rows carry `pre65_wellness_premium` as a foreign key; renaming the taxonomy without these silently stops the alias resolving. |

### Namespace 4 — case-by-case result: rename nothing

All 24 "prose" hits were classified. **None should be rewritten**, and two are not prose at
all:

| rows | what they are | disposition |
|---|---|---|
| `client_spending_aliases.csv` 65-66 | **not prose** — `category_id` foreign keys | **move to namespace 3** (above) |
| `spending_category_map.csv` 54, 67-75 | **not prose** — column 4 is `tracking`, a functional grouping key read by `spending_tracker.py` and feeding `wellness_base_yr` via `report_compute.py:66` / `results_model.py:73` | **KEEP.** It is the umbrella bucket, and renaming it would be an engine change, which the phase forbids. Note rows 72-75 map Health Club / Vitamins / Exercise Equipment / Fitness to `wellness` — exactly the hierarchy above. |
| `client_spending_budget.csv` 20, 22, 45-48, 69 | provenance notes reading "Source: Wellness Budget Detail / …" | **KEEP.** They name a subsection we decided to keep, so they are already accurate. |
| `client_spending.csv` 9 | "excludes housing/wellness/travel/large discretionary" | **KEEP.** Umbrella-level, and it states the core-spending scope rule correctly. |
| `ytd_transactions.csv` 606, 1257, 1693, 2102 | **client transaction data** — Amazon product titles containing "Optimal Wellness" (Nordic Naturals, Flora Digest) | **NEVER TOUCH.** These are the client's real imported records. Editing them would falsify a financial transaction log to satisfy a terminology sweep. |

That last row is the reason this was worth doing case by case rather than as a sweep: a
blanket `wellness → healthcare` replace across `input/*.csv` would have rewritten four of
the client's actual purchase descriptions and broken two category foreign keys, while
"correctly" renaming a functional tracking bucket into an engine mismatch.

### Remaining work for Task 8

Rename namespaces 2 and 3 only, in one pass, covering the four flat files above plus the
sectioned taxonomy. Everything else stays.
