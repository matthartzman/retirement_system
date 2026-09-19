# Modular Features & Feature-Switch Navigation

Item 330. Date: 2026-09-19.
Status: **Open questions resolved** (§7) — ready for planning.
Design only; no implementation. §8's phasing is indicative.

Two resolutions came from investigating the code rather than from judgement, and
both reversed the draft's position — see §7's notes on `spending_summary` and on
DAF/QCD.

Sibling design: `2026-09-19-optimizer-stress-test-rationalization-design.md` (#329),
whose decisions are final and are treated here as constraints, not as material to
relitigate.

## Problem

The ticket asks for two things that turn out to be one thing: *make more features
optional*, and *organize the feature switches into sections*. They are one thing
because the reason the switch list cannot be organized today is the same reason
more features cannot be made optional today — **there is no declared answer to
"what domain does this module belong to" and no declared answer to "what happens
when it is off."**

Four observations, from the code rather than the labels:

1. **The switch surface is one flat list of 27 rows.** `renderOptionalFunctions()`
   renders `rowsForStep("optional_functions")` as an undifferentiated stack of
   ON/OFF buttons, in CSV file order. Roth Conversion sits between Social
   Security and Charitable Giving; Glossary sits between RMD Audit and Education
   Funding. There is no grouping, no search, no filter, and no statement of what
   any switch costs or saves.
2. **"Optional" means four different things in the code.** Disabling a module can
   (a) skip a workbook sheet, (b) hide a nav step, (c) hide a `section` of input
   rows inside a step that stays visible, or (d) change the projection's numbers.
   All four are spelled `module_enabled(c, key)`. Only (a) is systematically
   derived; (b) and (c) are derived from `dashboard_step`/`csv_sections`; (d) is
   two hand-written lines in `deterministic_engine.py` that deliberately bypass
   `module_enabled` altogether.
3. **Three different switch mechanisms are conflated in the UI and distinguished
   only by special case.** `strategySectionGatedNote()` carries an
   `if (gateStepId === "heloc_strategy")` branch because HELOC is a *plan-data
   feature flag*, not a module toggle; `stepGatedByOptionalModule()` carries the
   matching branch. Every future feature of that shape adds another branch.
4. **Turning a module off can silently hide data the user already entered.**
   `existing_life_insurance` gates the whole `Insurance In Force` CSV section —
   and the catalog's own comment records that this includes rows whose
   `policy_type` is Disability, LTC or Umbrella, which that module has nothing to
   do with. That module is `FALSE` by default in the demo plan. So a household
   can enter disability policies and have them vanish behind a switch named for
   life insurance.

The result is a settings page nobody can navigate, a feature-optionality story
that stops well short of what the ticket asks for, and no safe way to extend it,
because the consequences of "off" are not written down anywhere a machine can
check.

## Goals

- A **domain classification** for every module, declared once in
  `module_catalog` beside `kind`, from which both the switch nav and the input-page
  grouping are derived — not a fourth hand-maintained list.
- An explicit, per-module **off-contract**: what disappears, what is retained,
  what degrades, and what is auto-enabled anyway.
- A **defensible line** between features that can be optional and the projection
  spine that cannot, argued rather than asserted.
- A switch surface organized into sections a household can scan, where the
  question "should I turn this on?" is answerable from the row itself.
- **One mechanism** for module toggles and plan-data feature flags at the point
  of use, without conflating them at the point of storage.

## Non-goals

- No change to any calculation, engine, or scoring function. Everything here
  moves a label, a declaration, or a rendering decision.
- No new modules, and no new optimizers or stress tests. (#329 restores three
  hidden ones; this design inherits that, it does not extend it.)
- **No re-opening of #329's decisions.** The workbook's `1. Reports` /
  `2. Optimizers` / `3. Comparisons` / `4. Risks` structure, the HELOC
  reclassification, the three restored modules, the Planning Levers retirement,
  and `CATALOG.kind` as the classification source of truth are all inputs here.
- No migration of `client_optional_functions.csv` to a different storage format.
  The toggles stay CSV rows in the plan; only their organization and their
  declared semantics change.
- No implementation. §8 is indicative.

---

## 1. Relationship to #329

#329 answers *what kind of thing is this module, and where does it go in the
workbook*. This design answers *what domain does it belong to, can it be turned
off, and where does the switch live*. They meet at `module_catalog`, which both
designs make the single source of truth for a different field.

| #329 decides | #330 inherits it as |
| --- | --- |
| `CATALOG.kind` is the classification source of truth; `SHEET_REGISTRY.section`/`letter_prefix` derive from it | The same rule applied to a new `domain` field. The switch nav derives from `domain`; it must not become a fourth hand-maintained list. |
| Workbook sections: Reports / Optimizers / Comparisons / Risks | A *kind*-axis structure, correct for a flat Excel tab strip. §5 argues the UI switch nav must use a *domain* axis instead, with kind as a filter — and explains why that is consistency rather than divergence. |
| HELOC moves to "Assets & Protection" — a plan input, not an optimizer | §5.3. "Assets & Protection" already exists as a left-nav group in `dashboard.js`'s `STEPS`, holding Holdings, Reserve Requirements, Insurance, Other Assets & Liabilities, and Estate Inputs. HELOC lands there with no new category invented, and §3.3 proposes promoting its plan-data flag into the catalog so its switch appears beside the others. |
| Withdrawal Sequencing, Asset Location and Scenario Analysis are restored, each with its own tab | Three more rows in the switch nav. Asset Location is catalogued `optional=False` today and becomes toggleable here (§4.2). |
| Planning Levers is retired (`kind=REFERENCE`, restates chosen dial positions with their source) | §5.5 proposes the live replacement: the switch nav's own **Active Features** view is the natural home for "what are all my current settings", and #329's §4.7 row badges supply the provenance half. Stated as a candidate, not a decision — #329 gates the retirement on exactly this. |
| `slug` on `SheetSpec` makes tab letters presentation-only | §6.2. This is a **hard prerequisite** for #330, not an adjacent nicety: the whole point of this design is more modules being off more often, and every additional off module shifts more letters. |

One thing #329 left for here that must be said plainly: #329's §3.3 rule ("a
module earns a UI panel when…") decides *which modules get a Strategy screen
panel*. It does **not** decide which modules get a switch. Every module gets a
switch or is core; that is a different and larger set.

---

## 2. Current-state inventory

### 2.1 Three mechanisms, only one of them declared

| Mechanism | Stored as | Declared in | Count today | Gates |
| --- | --- | --- | --- | --- |
| **Module toggle** | `client_optional_functions.csv` row → `c['opt'][key]` | `module_catalog.CATALOG[key].optional` | 27 | Workbook sheet (26), nav step (6), CSV section (4), engine behavior (2) |
| **Plan-data feature flag** | An ordinary plan row read by `sectionFlagEnabled(section, subsection, label)` | Nowhere — hand-written per flag | 3 known (`HELOC/Setup/heloc_enabled`, `Hybrid LTC/Settings/enabled`, `DAF/Settings/enabled`) | Nav step, row group, and projection behavior |
| **Modeling option** | An ordinary plan row read directly by the engine | Nowhere | ~12 (`stochastic_irmaa`, `use_asset_class_covariance`, `mc_home_equity_contingency`, `ytd_blend_enabled`, `ACA PTC enabled`, `portability_enabled`, `holding_period_allocation_enabled`, `real_dollar_reporting_enabled`, …) | Nothing structural — they change a number |

The first two are features. The third is **not** a feature and must not be pulled
into the module system: `stochastic_irmaa` does not add or remove anything a
household would recognize as a capability, it refines an assumption. The line is
whether turning it off removes a *thing you were shown*; if it only changes a
*number you were shown*, it is an assumption and belongs where assumptions live.
This distinction is the single most important guard against the switch nav
becoming a dumping ground.

### 2.2 The catalog census

40 output modules: 13 core (`optional=False`), 27 optional. By kind:

| Kind | Count | Optional today |
| --- | --- | --- |
| Projection | 7 | 2 (`lifetime_tax_projection`, `charts_dashboard`) |
| Optimization | 22 | 18 |
| Stress test | 4 | 4 |
| Diagnostics | 3 | 1 (`rmd_audit`) |
| Reference | 5 | 2 (`methodology_rerun`, `glossary`) |

By the domain this design proposes (§5.2), which is the view the switch nav
needs and which nothing in the code produces today:

| Domain | Catalog modules |
| --- | --- |
| Income & Benefits | `social_security_timing` |
| Spending | `spending_summary` |
| Housing & Property | `housing_trajectory_comparison`, `state_residency` |
| Investments | `asset_allocation`, `asset_location`, `retirement_strategy`, `charts_dashboard` |
| Taxes | `roth_conversion_plan`, `tax_loss_harvesting`, `gain_harvesting`, `charitable_giving`, `lifetime_tax_projection`, `rmd_audit` |
| Protection & Insurance | `life_insurance_need`, `existing_life_insurance`, `disability_income_insurance`, `property_casualty_umbrella` |
| Estate & Legacy | `estate_legacy_plan` |
| Family & Business | `education_funding_529`, `special_needs_planning`, `equity_compensation`, `business_succession`, `scorp_vs_llc` |
| Risk & Resilience | `market_luck_stress_test`, `survivor_stress_test`, `long_term_care_stress`, `divorce_qdro`, `what_if_analysis` |
| Plan Core (never optional) | `net_worth`, `cash_flow`, `balance_sheet`, `executive_summary`, `quality_control`, `plan_data_ref`, `assumptions_ref`, `account_reconciliation` |
| Output & Documentation | `methodology_rerun`, `glossary` |
| Retired by #329 | `planning_levers_echo` |

### 2.3 Candidates outside the catalog

Nine things behave like features and are not catalogued. These are the ticket's
"as many features as feasible" frontier:

| Candidate | Where it lives | Switch today |
| --- | --- | --- |
| **HELOC** | `client_policy.csv` `HELOC/Setup/heloc_enabled`; projection draws/repays the line | Plan-data flag, `NO` by default |
| **Hybrid LTC policy** | `client_assets.csv` `Hybrid LTC/Settings/enabled` | Plan-data flag, `FALSE` by default |
| **DAF giving** | `client_assets.csv` `DAF/Settings/enabled`, plus `charitable_giving`'s `csv_sections=("DAF",)` | *Both* a plan flag and a module gate — the one place the two mechanisms already overlap |
| **Housing "Where to live" search** | `src/housing/`, UI-only; #329 names it | None. Always available |
| **Tax Capacity** | `11B. Tax Capacity`, registry-only | None. Always built |
| **HSA Drawdown** | `11C. HSA Drawdown`, registry-only; self-gates on `hsa_withdrawal_mode=='optimize'` | A mode field with no visible consequence |
| **Current vs Proposed** | `37. Current vs Proposed`, registry-only | None. Always built |
| **Spending Tracker / YTD blend** | `spending_tracker.py`, `ytd_blend_enabled`, the YTD input pages | A modeling option gating a whole workflow — the one genuine borderline case in §2.1's taxonomy |
| **ACA premium tax credit** | `client_household.csv` `Wellness/ACA Premium Tax Credit/enabled` | Modeling option — but it gates a visible bridge-year calculation |

### 2.4 Registry/catalog join defects found while inventorying

These are new findings, not #329's. They matter because #330 proposes *deriving*
more from the catalog, and every derivation is only as good as the join.

- **`scorp_vs_llc.sheet` is `'12C. S-Corp vs LLC'`; the registry key is
  `'S-Corp vs LLC'`.** The two never join. Worse, `'12C. Gain Harvesting'` is a
  real registry key, so the catalog is asserting a sheet name one character-class
  away from a different module's sheet. Nothing catches this because
  `validate()` only checks `CATALOG.sheet` for *uniqueness*, never for
  *existence in `SHEET_REGISTRY`*.
- **`plan_data_ref.sheet` is `'4A. Plan Data'`; the registry key is
  `'Plan Data'`.** Same defect, same cause.
- **Three visible sheets have no catalog entry at all**: `11B. Tax Capacity`,
  `11C. HSA Drawdown`, `37. Current vs Proposed`. #329 already adds the first
  two; `37. Current vs Proposed` is a third and is not mentioned in #329.
- **`divorce_qdro` has `sheet=None`, so it is absent from
  `OPTIONAL_MODULE_SHEETS`, so `module_status()` returns no status row for it** —
  it is the one toggle the Optional Modules page cannot show an auto-enable badge
  for. #329 gives it a sheet, which incidentally fixes this.
- **`housing_trajectory_comparison` is `optional=True` but has no row in
  `client_optional_functions.csv`.** `_base_enabled()` defaults absent keys to
  enabled, so it is silently always-on — an optional module with no switch.

**Proposed guard:** `validate()` asserts that every `CATALOG[key].sheet` is a key
of `SHEET_REGISTRY`, that every `SHEET_REGISTRY` entry with a `display` has a
catalog module, and that every `optional=True` module has a toggle row in the
default plan. Three assertions, all at import time, all cheap. This is the same
move #329's phase 1 makes for `kind` vs `letter_prefix`, on the adjacent join.

### 2.5 What "off" does today, module by module

| Off-behavior | Derived from | Modules |
| --- | --- | --- |
| **Sheet skipped** (not created, not computed) | `OPTIONAL_MODULE_SHEETS` → `disabled_sheets` in `workbook_builder` | 26 |
| **Nav step hidden** | `step_gate_map()` → `moduleGates.step_gates` | `roth_conversion_plan`, `what_if_analysis`, `charitable_giving`, `market_luck_stress_test`, `survivor_stress_test`, `long_term_care_stress`, `divorce_qdro` |
| **CSV section hidden inside a visible step** | `section_gate_map()` → `moduleGates.section_gates` | `charitable_giving` (DAF), `education_funding_529`, `equity_compensation`, `existing_life_insurance` (Insurance In Force) |
| **Strategy screen section collapses to a note** | `strategySectionGatedNote()` | The 5 Optimize + 4 Stress sections |
| **Whole screen hidden** | `stepGatedByOptionalModule('strategy_stress')` special case | Stress Test, when all four of its modules are off |
| **Projection numbers change** | Raw `c['opt']` reads in `deterministic_engine.py` | `equity_compensation`, `disability_income_insurance` |
| **A headline is suppressed** | `module_enabled` reads inside another module's builder | Exec Summary (SS claim-age headline, MC success), Charts (MC series) |

The last two rows are the problem. They are consequences of a toggle that the
toggle's own declaration does not mention.

---

## 3. Feasibility assessment

### 3.1 The test

A module can be optional when all four hold:

**F1 — Off has a meaning a household would recognize.** "I don't have equity
compensation" is a fact about the household. "I don't have a net worth
projection" is not.

**F2 — Off is self-contained, or its consumers are declared.** Either nothing
reads its output, or every reader declares the dependency and states whether it
hard-requires (auto-enable) or soft-degrades.

**F3 — Off does not silently change a number the user is still being shown.** A
module may stop producing a sheet. It may not quietly alter the headline
projection while the user believes they only hid a tab. (`equity_compensation`
and `disability_income_insurance` violate this today — see §3.3.)

**F4 — Off is reversible with no data loss.** Turning it back on restores exactly
the prior state. This holds today, because toggles never delete plan rows, and it
must be preserved as an explicit guarantee rather than an accident.

### 3.2 The verdict

Candidate universe: **49** — 40 catalog modules, 3 registry-only visible sheets,
6 uncatalogued features from §2.3.

| Verdict | Count | Members |
| --- | --- | --- |
| **Optional today, stays optional** | 27 | The current `client_optional_functions.csv` set |
| **Newly optional** | 12 | `asset_location`, `scorp_vs_llc`, `account_reconciliation`, Tax Capacity, HSA Drawdown, Current vs Proposed, HELOC, Housing "Where to live", Hybrid LTC, DAF giving, Spending Tracker / YTD, `spending_summary` |
| **Must stay core** | 8 | `net_worth`, `cash_flow`, `balance_sheet`, `executive_summary`, `asset_allocation`, `quality_control`, `plan_data_ref`, `assumptions_ref` |
| **Modeling option, not a feature** | 1 | ACA PTC — see §7 Q3 |
| **Retired by #329** | 1 | `planning_levers_echo` |

**40 of 49 feasible as optional; 8 core.**

Two changes from the draft, both decided in §7: `spending_summary` moves from
core to optional (bundled with Spending Tracker / YTD, not as its own switch),
and ACA PTC leaves the feature list entirely for being a modeling option.

Per newly-optional candidate, the off-semantics being proposed:

| Candidate | Off means | Risk |
| --- | --- | --- |
| `asset_location` | Its restored tab is not built; draw order and allocation are unaffected | Low. Nothing reads it — #329 notes it was merged into Asset Allocation and hidden, which is a *display* merge |
| `scorp_vs_llc` | Sheet not built | Low. `low` demand, self-employment-only, and it is a Comparator under #329 — no other module consumes it. Currently core purely by omission |
| `account_reconciliation` | Sheet not built | Low, and it is already empty without YTD data. Better: auto-off when `ytd` inputs are absent (§7, Q4) |
| Tax Capacity | Sheet not built | Low by construction — #329 quotes its own docstring: "derives nothing new" |
| HSA Drawdown | Sheet not built; `hsa_withdrawal_mode` stops being honored | **Medium.** It is a mode-switch auto-apply in #329's §4.1 sense: off changes the drawdown the plan actually models. Needs #329's §4.7 disclosure to be honest |
| Current vs Proposed | Sheet not built | Low |
| HELOC | Already effectively optional; this only moves the switch into the module system | Low mechanically, **high in blast radius** — the projection draws and repays the line, so off changes every downstream number. Which is fine and expected, because the flag already says so; the change is that the switch is now findable |
| Housing "Where to live" | The UI panel is hidden; `src/housing/` is not invoked | Low. #329 establishes it has no workbook sheet and no consumer |
| Hybrid LTC | Policy rows stop feeding cash flow and LTC stress | **Medium.** `long_term_care_stress` reads the policy. Needs a declared soft dependency |
| DAF giving | DAF rows hidden, DAF contributions/grants not modeled | **Medium**, and it is the existing double-gate: `charitable_giving`'s `csv_sections=("DAF",)` *and* the plan flag both control it. Resolve to one owner (§7, Q2) |
| Spending Tracker / YTD | YTD pages hidden; `ytd_blend_enabled` forced off; reconciliation auto-off | **Medium.** The largest surface of the twelve, and the one most likely to be scoped out of a first pass |
| `spending_summary` | Not built; bundled with the Spending Tracker / YTD switch rather than its own | Low. Near-empty without YTD data, and the #221 reconciliation it carries is tracker output (§3.3) |
| ~~ACA PTC~~ | — | **Excluded by §7 Q3.** It changes a number rather than removing a visible thing, so it stays a modeling option on Economic & Tax Assumptions. Keeping §2.1's rule unbent is what keeps twelve other assumptions out of the switch nav |

### 3.3 Why the nine stay core

- **`net_worth`, `cash_flow`, `balance_sheet`** — every optimization and stress
  module declares `requires_outputs=BASE_PROJECTION` or reads these directly.
  Failing F1 and F2 at once.
- **`executive_summary`** — its whole job is to roll up the others. Off leaves a
  workbook with no front page.
- **`spending_summary`** — ~~carries the #221 reconciliation, so off would delete
  a reconciliation rather than a feature.~~ **Retracted.** Reading the builder
  shows the sheet is the *YTD spending tracker's* summary: its title renders as
  `SPENDING SUMMARY — {year} YTD ({days} days elapsed)` and its body is built
  from transaction tracking types. The #221 reconciliation compares Core Expenses
  *annualized from YTD transactions* against `spend_base`, and renders only
  `if core_assumption > 0`. So it is tracker output, not a plan-wide correctness
  check, and the whole sheet is near-empty without YTD data — the same condition
  that made `account_reconciliation` optional. It moves to §3.2's newly-optional
  list, bundled with the Spending Tracker / YTD feature rather than carrying its
  own switch, since a household not tracking transactions has no use for either
  and neither can compute without the other's data.
- **`asset_allocation`** — the interesting one. It is `kind=OPTIMIZATION`,
  `optional=False`, and it *should* stay that way: `charts_dashboard` declares it
  as a prerequisite, the Monte Carlo engine reads the target allocation
  (`use_asset_class_covariance`), and `asset_location` and rebalancing guidance
  are both downstream. It is an optimizer that has become load-bearing
  infrastructure. Making it optional would mean auto-enabling it for nearly every
  other module — a switch that is never off is worse than no switch.
- **`quality_control`** — a diagnostic of record. Off means "I would like fewer
  checks on whether my plan is wrong."
- **`plan_data_ref`, `assumptions_ref`** — the audit trail. Off means the
  workbook cannot be reproduced from itself.
- **`account_reconciliation`** appears in §3.2 as newly optional, not here; it is
  the one diagnostic whose usefulness is genuinely conditional on the household
  having YTD data.

### 3.4 Dependency chains: what exists, what is missing

**What exists.** `OutputModule.requires_outputs` is a real, transitive,
cycle-checked dependency declaration, and `effective_enabled_modules()` uses it to
**auto-enable** prerequisites — enabling `life_insurance_need` silently turns on
`survivor_stress_test`. `module_status()` then explains that to the UI via
`auto_enabled` / `required_by`, which `renderOptionalFunctions()` already renders
as a badge. This is a genuinely good piece of machinery and the design builds on
it rather than around it.

**What is missing.** `requires_outputs` expresses exactly one relationship:
*B cannot run without A, so turning B on turns A on.* Four real relationships in
the codebase are not that:

1. **Soft degradation.** `sheets_summary_builder.py` reads
   `module_enabled(c, 'market_luck_stress_test')` and
   `module_enabled(c, 'social_security_timing')` to decide whether to show the MC
   success and SS claim-age headlines. `executive_summary` declares neither. The
   Exec Summary works fine without them — it just says less. Auto-enabling would
   be wrong here; *declaring* is right.
2. **Same shape, charts.** `sheets_projection_charts.py` gates an MC series on
   the same toggle; `charts_dashboard` declares `net_worth`, `cash_flow` and
   `asset_allocation`, but not `market_luck_stress_test`.
3. **Cross-package.** `spending_tracker.py` reads the
   `existing_life_insurance` toggle. Nothing in the catalog records that a
   spending module cares about an insurance module.
4. **Engine participation, deliberately excluded from the gate.**
   `deterministic_engine.py` reads `c['opt']` directly for
   `equity_compensation` and `disability_income_insurance`, with a comment
   stating this is *on purpose* — so golden masters don't move under
   `RETIREMENT_SYSTEM_FORCE_ALL_MODULES`. The cost is a state the system can
   reach and cannot describe: a module force-enabled or auto-enabled for sheet
   purposes while the engine still models it as off. The sheet is built from a
   projection that does not contain the thing the sheet is about.

There is also a #329-adjacent case: `life_insurance_need` declares
`requires_outputs=('survivor_stress_test',)` but its *sheet* is populated by
`_merge_ltc_into_life_insurance()` from `long_term_care_stress` — an undeclared
dependency on a different module. #329's O10 splits that tab, which dissolves the
problem rather than fixing the declaration.

**Proposal.** Add one field and one test.

- `degrades_without: Tuple[str, ...]` — a soft dependency. Never auto-enables.
  Drives (a) a "this module shows less because X is off" note wherever the
  dependent's output is rendered, and (b) a reverse-direction warning on the
  switch: *"Turning Monte Carlo off also removes the success-probability
  headline from Executive Summary and the fan chart from Charts."* That reverse
  warning is the single highest-value thing this field buys, because it is the
  question a user actually has at the switch.
- `engine_participation: bool` — True for modules whose toggle changes the
  projection. Drives a stronger confirmation and a distinct visual treatment, and
  makes §3.1's F3 checkable instead of aspirational.

**Decided: fix the bypass, do not merely declare it.** The draft proposed
recording item 4's behavior and leaving it in place. That is not enough. Because
`effective_enabled_modules()` **auto-enables** prerequisites, the incoherent
state is reachable in ordinary use and not only under
`RETIREMENT_SYSTEM_FORCE_ALL_MODULES` — a module can be enabled for sheet
purposes while the engine still models it as off, producing a sheet built from a
projection that excludes the sheet's own subject. That is wrong output, and the
in-code comment justifying it is a testing convenience, not a design rationale.

`deterministic_engine.py` therefore reads `module_enabled` like every other call
site, and the golden masters are regenerated as the known, bounded cost. The
regeneration is the entire risk of this change, so it should land alone, on a
commit that touches nothing else, with the golden diff reviewed as the artifact
rather than as noise. `engine_participation` survives the fix — it still declares
*which* modules change the projection, which is what F3 and the toggle
confirmation need — but it now describes intended behavior rather than
documenting a divergence.
- **A test that greps for `module_enabled(` and raw `c['opt']` reads across
  `src/`, and asserts every call site outside the named module's own builder is
  backed by a `requires_outputs` or `degrades_without` declaration.** This is the
  enforcement half. Without it the new field drifts exactly like
  `section`/`letter_prefix` did, which is the failure #329 exists to kill. Ten
  call sites today, so the test is cheap to write and cheap to keep green.

---

## 4. Proposed category structure

### 4.1 Resolving the ticket's axis collision first

The ticket proposes *Spending, Investments, Income, Optimizers, Stress Tests*.
The first three are **domains** (what part of my life is this about); the last two
are **kinds** (what shape of answer does it produce). Mixing them means Roth
Conversion could sit under "Taxes" or under "Optimizers" and a user cannot
predict which — and whichever is chosen, the other is wrong for some other
module. Housing Comparison is an optimizer *and* a housing feature. Monte Carlo
is a stress test *and*, arguably, an investments feature.

**Resolution: domain is the primary axis; kind is a badge and a filter.**

Three reasons:

1. **The switch question is a domain question.** At a switch the user is asking
   "do I have equity compensation / do I care about state residency" — a fact
   about their life, answered by domain. "Is this an optimizer" does not help
   them decide.
2. **Kind already has a home, and #329 gave it a good one.** Kind organizes the
   *workbook* (Optimizers / Comparisons / Risks) and the *Strategy screens*
   (Optimize / Stress Test / Scenarios). Repeating it as the switch taxonomy
   would be the third statement of the same thing — and #329's whole thesis is
   that restating a classification is how classifications drift.
3. **Domain is the axis the left nav already uses.** `dashboard.js`'s `STEPS`
   groups steps as Plan Status / People and Income / Spending / Assets &
   Protection / Strategy / Reports / Settings. A switch taxonomy that matches the
   nav means "where I turn it on" is adjacent to "where I use it."

This is consistency with #329, not divergence from it. #329 chose section
structure by *what the reader is asking at that moment*: an Excel reader asks
"does this recommend an answer." A user at a settings page asks "does this apply
to me." Different question, different axis, same principle.

The ticket's Optimizers/Stress Tests view is not lost: a filter chip row above
the sections (`All · Optimizers · Comparisons · Stress tests · Reports`) produces
it on demand, from `CATALOG.kind`, with no second taxonomy to maintain.

### 4.2 The categories

Ten sections. Each declared as `OutputModule.domain`, each mapping to an existing
or proposed left-nav group.

| # | Category | Nav group today | Members |
| --- | --- | --- | --- |
| 1 | **Income & Benefits** | People and Income | Social Security timing |
| 2 | **Spending** | Spending | Spending Tracker / YTD blend — one switch, bundling Spending Summary and Account Reconciliation (§3.3) |
| 3 | **Housing & Property** | Spending → *promote* | Housing Comparison ("When to move"), Housing Location Search ("Where to live"), State Residency |
| 4 | **Investments** | Assets & Protection | Asset Allocation *(core, locked)*, Asset Location, Withdrawal Sequencing, Charts |
| 5 | **Taxes** | *none today* | Roth Conversion, HSA Drawdown, Tax-Loss Harvesting, Gain Harvesting, Tax Capacity, Lifetime Taxes, Charitable Giving, RMD Audit |
| 6 | **Assets & Protection** | Assets & Protection | HELOC, Existing Life Insurance, Disability Income, P&C / Umbrella, Hybrid LTC — coverage you **hold** |
| 7 | **Estate & Legacy** | Assets & Protection | Estate & Legacy Plan; *(DAF giving, pending §7 Q2)* |
| 8 | **Family & Business** | *none today* | Education Funding 529, Special-Needs Planning, Equity Compensation, Business Succession, S-Corp vs LLC |
| 9 | **Risk & Resilience** | Strategy | Monte Carlo, Survivor, LTC Stress, Divorce / QDRO, Scenario Analysis, Life Insurance **Need** — coverage you are sizing |
| 10 | **Reports & Documentation** | Reports | Current vs Proposed, Account Reconciliation, Methodology, Glossary; Executive Summary / Net Worth / Cash Flow / Balance Sheet / Plan Data / Assumptions / Quality Control *(core, locked)* |

### 4.3 The four placements the ticket asks to resolve

**Housing gets its own category, not a slot under Spending.** Three reasons that
outweigh the "it's a budget line" intuition: it carries two distinct optimizers
with different objectives (#329 §1.4), it is where HELOC's collateral sits, and
State Residency's table already physically moved to the Housing page
(`SECTION_REDIRECTS.state_residency → spending_mortgage_events`,
`dkey:'housing:residency'`). Three features and a liability is a category. The
cost is honest: the housing *budget* rows stay under Spending, so the domain
splits across two nav groups. That split already exists in the nav today; this
design does not create it, and §7 Q6 asks whether to close it.

**Taxes is its own category, with no nav group today.** This is the sharpest
finding of the inventory: eight of the 49 candidates are tax features and the
left nav has no tax group at all. They are scattered across Strategy
(Roth Conversion, Charitable Giving), Assets (HSA mode), Reports (Lifetime
Taxes, RMD Audit) and nowhere (Tax Capacity, harvesting). Taxes is the single
largest domain in the system and the least navigable. Creating the category in
the switch nav is the cheap half; creating the matching nav group is a larger
change and is deliberately *not* proposed here (§7 Q6).

**Estate & Legacy stays its own category** rather than folding into Assets &
Protection. It has one catalog module today, which argues for folding — but the
Estate Inputs page is large, `estate_legacy_plan` is described in the catalog as
four distinct analyses on one sheet (exposure, titling audit, gifting schedule,
per-beneficiary drawdown), and #329's §2.1 already flags it as "one tab, two
kinds." A category with one member that is visibly about to become several
members is worth keeping. If #329's follow-on splits that sheet, this category
fills itself.

**Assets & Protection exists, and it is where HELOC goes.** It is already a
left-nav group with five steps, so #329's O11 placement needs no new category.

**Protection splits by owned vs needed, rather than moving as a block.** The
draft put all four protection modules under Assets & Protection and called it a
deliberate divergence from #329, which files them under workbook section 4.2
"Risks". The divergence is unnecessary, because the four are not one kind of
thing:

- **Coverage you hold** — Existing Life Insurance, Disability Income, P&C /
  Umbrella, Hybrid LTC. The switch question is *"do I own disability
  insurance"*, a fact about your balance sheet. → **Assets & Protection**.
- **Coverage you are sizing** — Life Insurance Need. This is an analysis that
  recommends an amount, and it is precisely the module #329's §4.3
  stress→protection bridge needs adjacent to the survivor stress. →
  **Risk & Resilience**.

This dissolves the tension instead of trading one inconsistency for another: the
module the bridge depends on stays beside its stress test on both surfaces, and
the policy inventory sits where a household would look for it.

**The workbook does not follow this split.** #329's section 4.2 keeps all four
together under Risks, unchanged. On that surface all four are analyses that
recommend or audit coverage, so the *kind* axis groups them correctly; the switch
nav asks about your situation, so the owned-vs-needed axis groups them correctly
there. Same principle #329 used to choose its own sections — group by the
question the reader is asking on that surface.

⚠ **To verify before implementing:** this rests on Existing Life Insurance,
Disability Income and P&C / Umbrella being inventories of held coverage rather
than sizing analyses. If any of the three primarily *recommends* an amount, it
belongs with Life Insurance Need and the line moves. Confirm against each
module's builder before the phase 2 `domain` assignments are written.

### 4.4 What is deliberately not a category

- **"Optimizers" and "Stress Tests"** — §4.1. Available as filter chips.
- **"Advanced"** — a tier by sophistication rather than subject. It would
  collect exactly the modules a user is least equipped to evaluate, under a label
  that tells them nothing. Demand band (`low`/`niche`) already orders within a
  section; that is enough.
- **"Model & Simulation"** — the home that `stochastic_irmaa` and friends would
  want. Keeping it out is the enforcement of §2.1's line. Those rows stay on
  Economic & Tax Assumptions.

---

## 5. Toggle UX

### 5.1 Where the switches live

**Three surfaces, one registry.**

1. **Plan Features** (Settings; renames "Optional Modules"). The complete list,
   grouped by §4.2's ten categories, each collapsible, with a kind filter row and
   the existing page search. Each row: name, one-line description
   (`CATALOG.description`, already present), kind badge, demand hint, current
   state, auto-enable badge (already implemented), and — new — an off-impact
   line derived from reverse `degrades_without`.
2. **In-place, on the page the feature owns.** A feature whose `dashboard_step`
   or `csv_sections` gate a page the user is standing on should be switchable
   there. `renderStrategyOptimize()` already does this for HELOC, with a comment
   explaining why: *"the toggle itself must render here so it can be turned on
   in-place."* Generalize that, rather than keeping it as HELOC's special case.
3. **From the gated note.** `strategySectionGatedNote()` currently links to the
   Optional Modules page. It should offer the switch inline, because the user who
   is reading that note has already decided.

### 5.2 Off-states: three, chosen per module from declared data

| State | When | Rendering |
| --- | --- | --- |
| **Hidden** | The module owns a nav step and the household has entered no data for it | Step absent from nav; sheet not built. Today's behavior for `step_gate_map()` modules |
| **Collapsed with a note** | The module owns a section inside a page that stays visible, *or* the household has data | `strategySectionGatedNote()`'s pattern, generalized: a one-line note naming the feature, what it would add, and an inline switch |
| **Disabled in place** | The module gates individual rows inside a group the user is editing | Rows visible, greyed, not editable, with `optionalModuleState()`'s existing `reason` / `activation` / `effect` triple — which is already written and already good |

The rule that decides between Hidden and Collapsed is **"does the household have
data behind this switch"**, not the module's identity. This is the direct fix for
§1's fourth observation: `existing_life_insurance` may hide a page, but it may
never hide a page that has Disability and Umbrella rows in it. Stated as an
invariant: *no switch may render a row invisible when that row holds a
user-entered value.* If it would, it renders Collapsed-with-a-note instead, and
the note says how many rows are affected.

### 5.3 Module toggles vs plan-data feature flags

These must not be conflated at the point of **storage** — a module toggle is a
build-gating boolean in `client_optional_functions.csv`; a plan flag is an
ordinary plan row that other rows are semantically nested under, and HELOC's flag
in particular sits beside the credit limit and draw-year fields it governs. They
should absolutely be unified at the point of **use**, which is what
`strategySectionGatedNote()`'s `if (gateStepId === "heloc_strategy")` branch is
poorly approximating today.

**Proposal.** `OutputModule` gains:

```
gate_kind:  "module_toggle" | "plan_flag"
gate_ref:   None                              # module_toggle: the key itself
            | ("HELOC", "Setup", "heloc_enabled")   # plan_flag: section/subsection/label
```

`HELOC`, `Hybrid LTC`, `DAF` **and `QCD`** get catalog entries with
`gate_kind="plan_flag"`.

**DAF and QCD are treated identically, and QCD is the one that was already
right.** Investigating the double-gate (§7 Q2) showed QCD is gated solely by a
plan-data flag — `Cashflow / Charitable Giving / qcd_enabled`, default `FALSE` —
with no section gate, and it *cannot* have one: its rows live in the shared
`Cashflow` section, which `csv_sections` gating would take out wholesale. DAF is
the anomaly. So `charitable_giving` **drops `csv_sections=("DAF",)`** and DAF's
plan flag becomes its sole gate, matching QCD. Both then appear on Plan Features
as links to the page holding their data, which is how §5.3's one-writer rule
applies to plan flags generally.

Two consequences worth stating: DAF rows are no longer hidden when the
`charitable_giving` *module* is off — they are governed by the DAF flag alone,
exactly as QCD rows already are — and no user-set plan row is deleted by the
change, which was the objection to resolving the double-gate the other way. `step_gate_map()` gains a sibling `flag_gate_map()`, and
`stepGatedByOptionalModule()` loses its two hand-written branches — the
`heloc_strategy` one and the `special_strategies` one — in favour of reading
`moduleGates.flag_gates`, exactly as it already reads `step_gates`. The `where do
I turn this on` link resolves from `gate_ref` instead of an `if`.

What stays different, and should: a plan flag's switch renders **where its data
is** (HELOC's switch on the HELOC setup rows), while a module toggle's switch
renders on Plan Features. The Plan Features page lists both; for a plan flag it
renders a link to the owning page rather than a toggle, so there is one writer
per value.

### 5.4 Data retention

**Turning a module off never deletes plan data.** This is true today and should
become a stated guarantee rather than an emergent property. Concretely: no toggle
handler may clear rows, and re-enabling must restore the prior state exactly.

Two consequences to surface:

- A feature that is off but holds data should say so on the Plan Features row —
  *"Off · 4 policies entered."* This is the discoverability fix for §1's fourth
  observation and is independently useful.
- A feature that is off but whose data **has already been consumed** by a build
  is a different and harder case, and it is an open question (§7 Q5).

### 5.5 A live "all my current settings" view

#329 retires Planning Levers (`kind=REFERENCE`, "restates the chosen dial
positions with their source") and gates that retirement on something else being
able to show lever provenance live.

The Plan Features page is the natural half of that: an **Active Features** view —
the same registry, filtered to what is on, grouped by category — answers "what is
this plan actually doing." It does not answer "and where did that dial position
come from," which is the provenance half; #329's §4.7 row badges do. Together
they cover what the sheet covered.

Stated as a candidate for #329's gate, not as a claim that the gate is cleared.

---

## 6. UI ↔ workbook sync

### 6.1 One switch, two surfaces

The module toggle is already the single gate for both: `module_enabled(c, key)`
drives `disabled_sheets` in `workbook_builder`, and the same `c['opt']` reaches
the frontend through `config_service` as `module_status` / `module_gates`. **If a
module is off in the UI, its workbook sheet is suppressed.** That is existing,
working behavior and this design changes none of it.

Three asymmetries to close, all inherited:

- `divorce_qdro` has a toggle and no sheet. #329 gives it one.
- `housing_trajectory_comparison` has a sheet and no toggle row (§2.4).
- HELOC and the Housing location search have UI presence and no workbook sheet —
  correct per #329's permanent-split rule, but the Plan Features row must say
  "UI only" rather than implying a tab will appear.

Also: `apply_final_workbook_structure` already prunes empty sections and deletes
a divider whose sheets all vanished. Under #330 an entire section can go empty
far more often — a household with no business, no equity comp and no education
goals empties most of "Family & Business". The pruning handles it; worth stating
that it does, because it is the mechanism that keeps "more things optional" from
producing a workbook full of empty dividers.

### 6.2 Letter shifting — the hard dependency on #329 phase 2

`compute_final_sheet_renames()` assigns letters **densely, per build, over the
sheets that survived gating**. #329 §1.1 states the consequence: the same sheet is
`2J` in one household's workbook and `2N` in another's, while `_replace_text_refs`
writes those letters into prose inside cells.

#330 makes this strictly worse. Going from 27 optional modules to 39 means more
sheets absent in any given build, more letter collapse, and more cross-reference
prose resolving differently per household. **#329's phase 2 — `slug` on
`SheetSpec`, with every cross-reference resolving through
`FINAL_SHEET_RENAMES[slug]` — is therefore a prerequisite for shipping the
newly-optional modules, not an adjacent improvement.** §8's phasing orders
accordingly: nav and classification work can land first, but the twelve new
toggles wait for the slug.

Two smaller sync rules follow:

- **The switch nav must not derive from `letter_prefix` or `section`.** Those are
  workbook presentation and they change with #329's regrouping. The nav derives
  from `domain`, which is orthogonal and stable. This is the specific way #330
  could accidentally become the fourth hand-maintained list.
- **`domain` must not be derivable from `kind`, and vice versa.** They are
  independent axes — Housing Comparison is `OPTIMIZATION` in the Housing domain;
  Monte Carlo is `STRESS_TEST` in Risk & Resilience; Roth Conversion is
  `OPTIMIZATION` in Taxes. Two fields, both declared, neither derived from the
  other. `validate()` should assert every module has both.

---

## 7. Decisions

All eight open questions were resolved on 2026-09-19, along with four follow-on
questions the answers exposed. Two were resolved by reading the code rather than
by judgement, and **both reversed the draft's position** — they are marked ⟲.

| # | Question | Decision |
| --- | --- | --- |
| Q1 | Toggle state per-plan or per-scenario? | **Per-plan only.** A case that changes which *sheets exist* makes the Comparison Matrix compare workbooks of different shapes. Scenarios vary inputs, not output structure. |
| Q2 ⟲ | DAF's double gate | **Plan flag owns it; DAF drops `csv_sections`, matching QCD.** Both catalogued as `gate_kind="plan_flag"` (§5.3). QCD was already correct — DAF was the anomaly. |
| Q3 | ACA PTC: feature or modeling option? | **Modeling option; the §2.1 rule does not bend.** It stays on Economic & Tax Assumptions. The rule is what keeps twelve other assumptions out of the switch nav. |
| Q4 | Data-conditional auto-off? | **No.** Render "Off · no data entered" / "On · nothing to show yet" hints instead. Auto-off would add a fifth precedence rule to `module_enabled`'s four and carries its own failure mode. |
| Q5 | Stale builds after a toggle change | **Verify whether toggles raise a `build_impact` notice today; wire it if not.** Reuses the existing staleness machinery rather than inventing one. |
| Q6 | Do the nav groups change? | **Yes — but as its own project**, sequenced after the switch page. See §8. |
| Q7 | Admin/advanced tier? | **No writable tier — but disclose active overrides.** When a force env var is set, Plan Features says so, read-only. No new precedence rule; fixes the case where the switch page disagrees with what the build did. |
| Q8 ⟲ | Must `spending_summary` be core? | **No — it becomes optional, bundled with Spending Tracker / YTD.** The #221 reconciliation is tracker output, not a plan-wide check (§3.3). Core drops 9 → 8. |

Follow-on decisions:

| # | Question | Decision |
| --- | --- | --- |
| F1 | Protection placement vs #329 | **Split by owned vs needed** (§4.3), not moved as a block. Life Insurance Need stays in Risk & Resilience; the three held-coverage modules go to Assets & Protection. ⚠ verification noted in §4.3. |
| F2 | Does the workbook follow that split? | **No.** #329's section 4.2 is unchanged — on that surface all four are analyses, so `kind` groups them correctly. |
| F3 | The `deterministic_engine.py` bypass | **Fix it and regenerate goldens** (§3.4) — it is a correctness bug, reachable in ordinary use via auto-enable, not merely a documented divergence. |
| F4 | Scope of the newly-optional set | **Both batches, 6a then 6b**, sequenced strictly by risk and never combined in one session. |

### 7.1 Still open

- **The owned-vs-needed line needs verifying** against what Existing Life
  Insurance, Disability Income and P&C / Umbrella actually compute (§4.3). If any
  primarily recommends an amount rather than inventorying held coverage, it moves
  to Risk & Resilience with Life Insurance Need.
- **Whether a toggle change raises a `build_impact` notice today** is unverified
  (Q5). The decision is to wire it if absent — but which of those it is remains
  unknown, and it changes phase 4's size.
- **Deferred, not rejected:** marking Build History snapshots unreproducible when
  their module set no longer matches current settings (Q5); a data-conditional
  auto-off mechanism (Q4).

<details>
<summary>7.2 — The questions as originally posed (superseded by the tables above)</summary>

**Q1 — Is module state per-plan or per-scenario?** Today it is per-plan:
`client_optional_functions.csv` is plan data, and a Planning Case's overrides
carry `row_index`, which means a case could in principle stage a toggle change
like any other row edit. Should it? A scenario "what if I retire without the
HELOC strategy" is a legitimate comparison, and #329's optimizer-patch contract
would carry it for free. Against: a case that changes which *sheets exist* makes
the Unified Comparison Matrix compare workbooks of different shapes. **Not
guessed.** Recommend deciding before §8 phase 4.

**Q2 — DAF is double-gated. Which mechanism owns it?** `charitable_giving`
declares `csv_sections=("DAF",)` *and* `client_assets.csv` carries
`DAF/Settings/enabled`. Two writers, one meaning. Options: promote the plan flag
to the catalog and drop the `csv_sections` entry; or keep the section gate and
retire the flag. The second is cleaner but deletes a plan row users may have set.

**Q3 — Is ACA PTC a feature or a modeling option?** It fails §2.1's test
literally (it changes a number, not a visible thing) but passes it in spirit
(whether you model premium credits in bridge years is a real planning choice with
a real household-level answer). Whichever way it goes, the *rule* must not bend —
if it is a feature, the rule needs restating to cover it, not an exception.

**Q4 — Should any module be auto-off rather than auto-on?**
`effective_enabled_modules()` only ever auto-*enables*. `account_reconciliation`
without YTD data and `equity_compensation` without grants are both empty by
construction. A data-conditional auto-off would be genuinely useful and is a new
mechanism with its own failure mode (a user enters data and nothing appears,
because the auto-off decision was cached). Flagged, not designed.

**Q5 — What happens to a module that is off but whose data a prior build already
consumed?** Concretely: build with `equity_compensation` on, then turn it off.
The last built workbook still contains the sheet, `lastBuildCompare` still
reflects the projection that included ISO exercises, and Build History has a
snapshot whose numbers can no longer be reproduced from current settings. The
staleness machinery (`dashboard_source_truth_banners`'s `build_impact`/`review`
notices) already exists for exactly this class of problem — does a toggle change
raise a `build_impact` notice today? It should, and whether it does needs
checking rather than assuming.

**Q6 — Do the nav groups change, or only the switch categories?** §4.3 proposes
Taxes and Family & Business as switch categories with no corresponding nav group,
and promotes Housing out of Spending. Making the left nav match is a larger,
higher-risk change (every `SECTION_REDIRECTS` entry, every `helpLink`, every
`SUGGESTED_NEXT`) and is deliberately out of scope here. But leaving them
mismatched means "where I turn it on" and "where I use it" diverge for eight tax
features — which is precisely the defect §4.1 argued the domain axis would fix.
**This is the most consequential open question in the design.**

**Q7 — Is there an admin/advanced tier?** The env overrides
(`RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES`, `FORCE_DISABLE`, `FORCE_ALL`) are
already an out-of-band admin tier, used by tests. Should the UI expose anything
like it — a "show everything" developer switch? Recommend **no**: the env vars
serve the testing need, and a UI tier would be a second precedence rule layered
on `module_enabled`'s existing four. Recorded as a question because the ticket
asks.

**Q8 — Does `spending_summary` really have to be core?** §3.3 says yes because of
the #221 reconciliation merge. If that reconciliation moved to Cash Flow or the
Executive Summary, the sheet itself becomes an ordinary optional report. Worth a
look; it is the weakest of the nine.

</details>

---

## 8. Indicative phasing (not scoped for execution)

Per project convention: model/effort, approximate tool-use turns, what drives
context, and weight relative to a 5-hour session on a Claude Pro plan. These are
relative sketches for planning only. **Phases 4 and 5 are ordered after #329's
phase 2 (`slug`) and phase 3 (regrouping) and should not start before them.**

| # | Phase | Model / effort | Turns | Context driver | Weight vs. a 5-hr session |
| --- | --- | --- | --- | --- | --- |
| 1 | **Registry join guards** (§2.4): `validate()` asserts catalog↔registry sheet-name join, catalog coverage of displayed sheets, and a toggle row for every `optional=True` module. Fix `scorp_vs_llc` / `plan_data_ref` names; add the `housing_trajectory_comparison` CSV row | Sonnet, medium | ~10–15 | `module_catalog.py` (916 lines, read once) plus `tests/test_sheet_table_consistency.py`. Self-contained | **Light** |
| 2 | **Declare `domain` on all 40 modules**; `validate()` requires it; expose via `config_service` alongside `module_gates` | Sonnet, medium | ~10–15 | One file plus the config payload. The judgement is in this doc, not in the code | **Light** |
| 3 | **Plan Features page**: regroup `renderOptionalFunctions()` by `domain`, add kind filter chips, off-impact line, "off but holds data" indicator | Sonnet, medium | ~20–30 | `dashboard.js` is 7,287 lines — read `renderOptionalFunctions` and its neighbours only, never linearly. Frontend tests glob `dashboard_decomp_*.js` | **Moderate** |
| 4 | **Dependency declarations** (§3.4): `degrades_without`, `engine_participation`, and the call-site enforcement test | Opus, high | ~25–35 | The enforcement test must sweep `src/` for `module_enabled(` and raw `c['opt']` reads — a genuinely broad search, and the findings need judgement per site. ~10 sites today | **Moderate–Heavy** |
| 5 | **Unify plan flags into the catalog** (§5.3): `gate_kind`/`gate_ref`, `flag_gate_map()`, remove the two hand-written branches in `stepGatedByOptionalModule()`; catalog entries for HELOC, Hybrid LTC, DAF | Opus, high | ~25–35 | Cross-cutting frontend+backend; `dashboard_decomp_row_model.js` is 5,188 lines and will be reopened repeatedly. Behavior-preserving, so regression risk is the cost driver | **Heavy** |
| 5b | **Engine gate fix** (§3.4, F3): `deterministic_engine.py` reads `module_enabled`; regenerate golden masters | Opus, high | ~15–25 | Small code change, large verification surface. The golden diff IS the deliverable and must be read, not skimmed | **Moderate — must land alone** |
| 6 | **Newly-optional modules, in two batches**: 6a low-risk (`asset_location`, `scorp_vs_llc`, Tax Capacity, Current vs Proposed); 6b medium-risk (HSA Drawdown, Hybrid LTC, DAF+QCD, Housing search, Spending Tracker/YTD — which now bundles `spending_summary` and `account_reconciliation`) | Sonnet, medium (6a) / Opus, high (6b) | ~15–20 (6a); ~30–40 (6b) | 6a is registry edits plus a build per toggle combination. 6b touches the engine and needs golden-master reasoning | 6a **Moderate**; 6b **Heavy** |
| 7 | **Off-state rendering** (§5.2): generalize `strategySectionGatedNote()` to a registry-driven `featureGatedNote`, implement the no-hidden-data invariant, inline switches | Sonnet, medium | ~15–25 | `dashboard_decomp_strategy_workspace.js` is only 280 lines; the invariant is the work, and it needs a test per off-state | **Moderate** |
| 8 | **Left-nav realignment** (Q6): add Taxes and Family & Business nav groups, promote Housing out of Spending, so "where I turn it on" matches "where I use it" | Opus, high | ~40–60 | `SECTION_REDIRECTS`, every `helpLink` target, `SUGGESTED_NEXT`, and the step ordering in `dashboard.js`'s `STEPS`. Touches nearly every navigation path in the frontend | **Heavy — its own project** |

**Disproportionately expensive, with scoping advice:**

- **Phase 5 is the heaviest and the least visible.** It is a pure refactor that
  removes two `if` branches and produces no user-facing change — the classic
  shape for an open-ended session. Constrain it by doing HELOC alone first, end
  to end, and treating Hybrid LTC and DAF as repetitions only once HELOC's
  pattern is proven. If HELOC alone is not clean, stop: the mechanism is wrong.
- **Phase 6b is heavy for a different reason — the test loop.** Each engine-
  touching toggle needs a build under on and off, and the golden masters are the
  arbiter. Cap it by pinning **two or three** representative toggle combinations
  rather than sweeping the space, which is the same advice #329 gives its phase 2
  for the same reason. Do not batch 6a and 6b into one session; 6a's cheapness is
  entirely because nothing reads its modules.
- **Phase 4's sweep is the one broad search in the plan.** Scope it with a
  targeted grep for two exact strings (`module_enabled(` and `c['opt']`) rather
  than a semantic search for "places that read toggles," and write the findings
  into the test as a fixture list so the sweep happens once, not once per run.
- **Phase 3 looks larger than it is.** `dashboard.js` is 7,287 lines, but
  `renderOptionalFunctions()` is about 35 of them and the grouping data comes
  from phase 2. The risk is opening the file and reading it; do not.
- **Phase 8 is now a decided commitment, and it is the largest thing here.** Q6
  resolved toward realigning the left nav, which makes it real work rather than a
  hypothetical. Its entire risk is scope leak into phase 3 — the switch page and
  the navigation refactor must not share a session, because the switch page is
  shippable on its own and the nav refactor is not. Ship phases 1–7, use the
  result, *then* plan phase 8 against what the mismatch actually feels like.
- **Phase 5b must land alone.** A commit that regenerates golden masters
  alongside anything else makes the golden diff unreviewable, which defeats the
  point of having them. Nothing else in the same commit, and read the diff as the
  artifact.
- **Two unknowns can still move these estimates.** Whether a toggle change
  already raises a `build_impact` notice (§7.1) changes phase 4's size, and the
  owned-vs-needed verification (§4.3) could move a module between domains before
  phase 2 writes them down. Both are cheap to check and should be checked first.

Check `/usage` against these estimates as any resulting plan executes — the
relative weights above are the useful signal, not absolute figures.
