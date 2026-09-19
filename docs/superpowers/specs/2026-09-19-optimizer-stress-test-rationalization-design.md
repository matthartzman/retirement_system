# Optimizer & Stress-Test Rationalization

Item 329. Date: 2026-09-19.
Status: **Open questions resolved** (§5) — ready for planning, except the two
items in §5.1 that remain open.
Design only; no implementation. §6's phasing is indicative.

## Problem

"Optimizer" and "stress test" are load-bearing words in this system — they name
two workbook sections, two UI screens, two `module_catalog` kinds, and the
vocabulary the household reads — and nothing enforces what they mean. Tracing
the code rather than the labels turns up four separate kinds of drift:

1. **The two surfaces expose different sets.** The workbook's Optimizers
   section ships twelve-ish tabs; the UI's Optimize screen ships five sections,
   only three of which correspond to a workbook optimizer tab. The UI's Stress
   Test screen ships four sections; the workbook's Risk section ships three
   tabs, one of which is a *merge* of two different modules.
2. **Classification is asserted in two places that disagree.**
   `module_catalog.CATALOG` assigns every module a `kind`
   (`OPTIMIZATION`/`STRESS_TEST`/…) with a clean stated axis. `SHEET_REGISTRY`
   independently assigns every sheet a `section` and a `letter_prefix` by hand.
   Nothing checks that the two agree, and in several cases they do not — a
   REFERENCE module is lettered into the Optimizers block, and three
   OPTIMIZATION modules are physically filed in section `2` while lettered as
   `3D`–`3F` under Risk & Stress Tests.
3. **Things called optimizers do not optimize.** The UI's "HELOC" optimizer
   section renders a field form and nothing else. The workbook's "Tax Capacity"
   sheet states in its own docstring that it "derives nothing new." Neither
   searches anything or recommends a decision.
4. **Nothing can be applied.** Every UI optimizer panel except Housing is an
   *input form*; the recommendation itself only materializes in the workbook
   after a build. There is exactly one "copy the answer into the plan" button
   in the whole app (`copyOptimizerOverrideToUserTargets`), and the Planning
   Workbench's official answer to "adopt this" is a message telling the user to
   navigate to the source page and retype it.

The result is a household who cannot tell which screen answers which question,
and an advisor reading a workbook whose tab letters mean something different in
every build.

## Goals

- One definition of "optimizer" and one of "stress test", applied uniformly to
  every module in both surfaces, with misclassifications named.
- One classification source of truth, with the workbook section layout and the
  UI section registry *derived* from it rather than hand-maintained beside it.
- A stated, defensible rule for which modules surface in the UI vs. workbook-only.
- A concrete, feasible "Apply to plan" flow for optimizer results, built on the
  persistence machinery that already exists rather than a new subsystem.

## Non-goals

- No change to any calculation, scoring function, or engine. Every
  reclassification below moves a label, a section assignment, or a nav entry.
- No new optimizers or stress tests. (Merging two existing housing engines is
  proposed, but as a follow-on question, not decided here.)
- No change to the Planning Workbench's Baseline → Change Set → Run Type →
  Impact → Decision model, which the 2026-09-17 integration design settled.
  This design *reuses* it; it does not revise it.
- No implementation. The phasing sketch at the end is indicative only.

---

## 1. Current-state map

### 1.1 How workbook tab letters are actually produced

Letters are **not stable identifiers**. `compute_final_sheet_renames()`
(`src/reporting/workbook_common.py`) assigns letters densely, per build, over
whichever sheets survived module gating, walking `SHEET_LETTER_ORDER` (derived
from `SHEET_REGISTRY.letter_rank`). Disabling a module closes its gap and
shifts every later letter.

So the canonical order of `letter_prefix` `2`, by `letter_rank`, is:

| rank | stable sheet | display | catalog kind |
| --- | --- | --- | --- |
| 0 | `11. Roth Conversion` | Roth Conversion | OPTIMIZATION |
| 0.5 | `11C. HSA Drawdown` | HSA Drawdown | *(no catalog entry)* |
| 1 | `4. Asset Allocation` | Asset Allocation | OPTIMIZATION |
| 2 | `13. State Residency` | State Residency | OPTIMIZATION |
| 3 | `10. Social Security` | Social Security | OPTIMIZATION |
| 4 | `S-Corp vs LLC` | S-Corp vs LLC | OPTIMIZATION |
| 5 | `12. Charitable Giving` | Charitable Giving | OPTIMIZATION |
| 6 | `14. Estate Plan` | Estate & Legacy Planning | OPTIMIZATION |
| 7 | `27. Planning Levers` | Planning Levers | **REFERENCE** |
| 8 | `12B. Tax-Loss Harvesting` | Tax-Loss Harvesting | OPTIMIZATION |
| 9 | `30. Education Funding` | Education Funding | OPTIMIZATION |
| 10 | `35. Equity Compensation` | Equity Compensation | OPTIMIZATION |
| 11 | `36. Special-Needs Planning` | Special-Needs Planning | OPTIMIZATION |
| 12 | `34. Business Succession` | Business Succession | OPTIMIZATION |
| 13 | `12C. Gain Harvesting` | Gain Harvesting | OPTIMIZATION |
| 14 | `11B. Tax Capacity` | Tax Capacity | *(no catalog entry)* |
| 15 | `38. Housing Comparison` | Housing Comparison | OPTIMIZATION |

The twelve-item list in the ticket (`2A`…`2M`) is what this table produces when
the four default-off modules (Education Funding, Equity Compensation,
Special-Needs, Business Succession) are off and Planning Levers is read past.
That is itself the finding: **the same sheet is `2J` in one household's
workbook and `2N` in another's**, while `_replace_text_refs` writes those
letters into prose inside cells. Any external reference to "2J" is unsound.

Letter group `3`:

| rank | stable sheet | display | catalog kind |
| --- | --- | --- | --- |
| 0 | `15. Market-Luck Stress Test` | Monte Carlo | STRESS_TEST |
| 1 | `18. Survivor Stress Test` | Survivor | STRESS_TEST |
| 2 | `19. Life Insurance` | LTC + Life Insurance | **OPTIMIZATION** |
| 3 | `31. Existing Life Insurance` | Existing Life Insurance | OPTIMIZATION |
| 4 | `32. Disability Income` | Disability Income | OPTIMIZATION |
| 5 | `33. P&C Umbrella` | P&C Umbrella | OPTIMIZATION |

Note `17. LTC Stress Test` does not appear: `_merge_ltc_into_life_insurance()`
(`workbook_builder.py`) copies it into `19. Life Insurance`, so the tab labelled
`3C. LTC + Life Insurance` carries **a stress test and a protection optimizer on
one sheet**. Ranks 3–5 carry `section='2'` but `letter_prefix='3'` — they are
filed in the Optimizers physical group and lettered under Risk. That
contradiction is in the registry data itself.

### 1.2 Modules with no visible home

- `9. Retirement Strategy` (Withdrawal Sequencing, OPTIMIZATION) — built, then
  merged into the Executive Summary and hidden.
- `24. Asset Location` (OPTIMIZATION) — built, merged into Asset Allocation,
  hidden.
- `16. Scenario Analysis` (OPTIMIZATION, `mode=comparison`) — built and hidden,
  while the UI promotes Scenarios to a top-level Strategy screen.
- `divorce_qdro` (STRESS_TEST) — `sheet=None`. UI-only; the mirror image of the
  workbook-only optimizers.

### 1.3 UI panels: what each one actually is

| UI section | Backing renderer | What it really does |
| --- | --- | --- |
| Roth Conversion | `renderRothConversion()` | **Input form.** Policy/guardrail/calibration rows. No result shown; the candidate table exists only on workbook `11. Roth Conversion`. |
| Asset Allocation | `renderAllocationRecommendation()` + `renderAllocationPolicy()` | Inputs **plus a live recommendation preview** (`optimizerPreviewTarget`, `renderOptimizerPreviewNote`) and the only apply button in the app. |
| Next Housing Move | `renderHousingOptimizePanelHtml()` → `startHousingOptimization()` | **A real in-UI search**: own Run button, own results table, ZIP shortlist. Deliberately not `analysisFrame`-wrapped. |
| Charitable Giving | `renderEntityCharitable()` | Input form. |
| HELOC | `renderHelocOptimizePanel()` | `renderFieldGroups(helocGatedRows(...))` — **an input form with a missing-fields list. Nothing optimizes.** |
| Monte Carlo / Survivor / LTC / Divorce | `renderMonteCarloOptions()` etc. | Stress *assumption* forms; results land in the workbook. |

So the UI's "Optimize" screen is, with two exceptions, a set of input pages for
optimizers whose output lives in Excel. That is the deepest asymmetry in the
system, and it is what makes "Apply to plan" (§4) feel missing: for four of five
sections there is nothing on screen to apply.

### 1.4 The housing relationship, resolved

These are **two different engines over an overlapping decision space**, neither
aware of the other:

- **UI "Next Housing Move"** → `src/housing/` (`optimizer.py` orchestrating
  `candidates` → `constraints` → `scoring` → `plan_variant` → `results`, with
  `zip_screen`). Searches over *location* (ZIP shortlist), move type, and
  timing; filters on family-presence, dual-ownership and housing-gap
  constraints, counting rejections for explainability; two-pass — deterministic
  rank, then Monte Carlo on the shortlist. Scored by
  `scoring._pass1_objective` / `_lifetime_cost`. **Has no workbook sheet.**
- **Workbook `2x. Housing Comparison`** → `src/housing_comparison.py`. A
  three-axis coordinate descent over current-home sale year × Step 1
  (type × year) × Step 2 (type × year), run under two axis orderings with the
  better kept, then MC-refined on the ±1 neighborhood. Reads
  `household.next_housing_steps` — it optimizes the *timing and type of steps
  the user has already specified*. Scored on **LCV**, deliberately aligned with
  the Social Security sweep in `build_sheet10`. **Has no UI panel.**

They are not the same feature under two names, and neither is a stress test.
They are a *location* search and a *schedule* search with different objective
functions and no shared result shape.

**Decided: keep both, and name them honestly** — "Where to live" (UI,
`src/housing/`) and "When to move" (workbook, `housing_comparison.py`). Neither
engine is retired and neither is rewritten. Two reasons:

1. Unifying on `housing_comparison.py` would strand the housing work designed on
   2026-09-19 (anchor reserved-slot selection and the future-year escalation
   fix), which invests further in `src/housing/`.
2. Unifying on `src/housing/` would discard LCV scoring that was deliberately
   aligned with the Social Security sweep in `build_sheet10` — cross-module
   comparability that is hard to win back.

The honest cost of keeping both: two scoring functions answer adjacent questions
differently, and a user could in principle get a "where" answer and a "when"
answer that don't compose. The names are what prevent that from being a trap —
each panel must state the question it answers and the one it does not.

**Not chosen, but the best long-term shape:** chaining them, so the location
search shortlists ZIPs and the schedule optimizer then optimizes timing for the
chosen location. That matches how the decision is actually made. It is deferred,
not rejected — and keeping both engines intact is what leaves the door open.

---

## 2. Definitions

`module_catalog`'s docstring already states the correct axis, and this design
adopts it verbatim as the primary test:

> Optimization changes a variable the household *controls* (a lever).
> Stress test changes a variable *outside* their control (a risk).

That axis is necessary but not sufficient — it does not separate "search for the
best value of a lever" from "show me the arithmetic of the lever." Three
questions, applied in order:

**Q1 — Whose variable moves?** A lever the household controls → decision family.
A risk they do not → stress family. Neither (the module only restates or
reconciles values) → worksheet family.

**Q2 — Does the module choose?** Within the decision family: does it enumerate
candidate values, score them against a stated objective, and return a ranked
recommendation? Yes → **Optimizer**. No — it evaluates one or a few
user-supplied alternatives side by side → **Comparator**.

**Q3 — Over what horizon does the recommendation act?** A multi-year assumption
the plan carries forward → **plan optimizer**. A discrete transaction to execute
this tax year → **action optimizer**. This matters entirely for §4: applying a
plan optimizer edits an assumption; "applying" an action optimizer means
recording that you did the trade.

Formally:

- **Optimizer** — searches a space of household-controllable decisions, scores
  candidates against an explicit objective, and returns a recommendation the
  household could adopt. Must have: a candidate set, an objective, a ranking.
- **Comparator** — evaluates named alternatives the *user* supplies, with no
  search. Ranking is incidental to there being two columns.
- **Stress test** — re-runs the plan under an adverse exogenous assumption and
  reports resilience. Changes nothing the household chose. Read-only by
  construction: its *inputs* are editable, its *result* is never adopted.
- **Protection decision** — a controllable decision (buy coverage) whose input
  is a stress result. A distinct third thing that today is filed under both.
- **Worksheet** — restates or consolidates figures computed elsewhere. No
  search, no adverse scenario, no recommendation.

### 2.1 Reclassification

| Item | Today | Under these definitions | Note |
| --- | --- | --- | --- |
| Roth Conversion (2A) | Optimizer | **Plan optimizer** ✓ | `optimize_roth_conversion_strategy` enumerates, scores on LCV with a feasibility gate, ranks. Textbook. |
| HSA Drawdown (2B) | Optimizer | **Plan optimizer** ✓ | Self-gates on `hsa_withdrawal_mode=='optimize'`; no `CATALOG` entry — registry gap. |
| Asset Allocation (2C) | Optimizer | **Plan optimizer** ✓ | |
| State Residency (2D) | Optimizer | **Comparator** ⚠ | `build_sheet13` compares the current state against a user-entered target. It does not search states. |
| Social Security (2E) | Optimizer | **Plan optimizer** ✓ | LCV sweep over claiming-age pairs. |
| S-Corp vs LLC (2F) | Optimizer | **Comparator** ⚠ | Two named structures, no search. |
| Charitable Giving (2G) | Optimizer | **Plan optimizer** ✓ | Bunching/QCD/DAF strategy selection. |
| Estate & Legacy (2H) | Optimizer | **Mixed** ⚠ | Gifting schedule and drawdown sensitivity are optimizer-shaped; beneficiary/titling audit is a *diagnostic*. One tab, two kinds. |
| Planning Levers (2I) | *(lettered into Optimizers)* | **Worksheet** ✗ | `kind=REFERENCE`, "restates the chosen dial positions with their source." Does not belong in the Optimizers block at all. |
| Tax-Loss Harvesting (2J) | Optimizer | **Action optimizer** ⚠ | Current-year harvestable lots. Different cadence from every plan optimizer beside it. |
| Gain Harvesting (2K) | Optimizer | **Action optimizer** ⚠ | Same. |
| Tax Capacity (2L) | *(in Optimizers)* | **Worksheet** ✗ | Own docstring: "derives nothing new." A consolidated headroom view assembled from four other sheets. Genuinely useful; not an optimizer. |
| Housing Comparison (2M) | Optimizer | **Plan optimizer** ✓ | Coordinate descent, LCV objective, ranked. Real optimizer — just not the same one as the UI's. |
| Withdrawal Sequencing (hidden) | Optimizer | **Plan optimizer**, homeless ⚠ | |
| Asset Location (hidden) | Optimizer | **Plan optimizer**, homeless ⚠ | |
| Scenario Analysis (hidden) | Optimizer `mode=comparison` | **Comparator** ✓ | Correctly typed; wrongly hidden given the UI elevates it. |
| Monte Carlo (3A) | Stress test | **Stress test** ✓ | |
| Survivor (3B) | Stress test | **Stress test** ✓ | |
| LTC + Life Insurance (3C) | Stress test | **Stress test + protection decision, merged** ✗ | Two kinds on one tab via `_merge_ltc_into_life_insurance`. |
| Existing Life Ins. / Disability / P&C (3D–3F) | Optimizer, filed in §2, lettered in §3 | **Protection decisions** ⚠ | Registry contradicts itself. |
| Divorce / QDRO (UI only) | Stress test | **Stress test** ✓ | Correct kind; no workbook sheet. |
| HELOC (UI only) | *(UI "optimizer")* | **Plan input** ✗ | No candidate set, no objective, no ranking. It is a financing feature modeled inside the cash-flow projection. |
| Next Housing Move (UI only) | Optimizer | **Plan optimizer** ✓ | |

Nine of roughly twenty-four items are mislabeled today, and three of the four
worst cases (`2I`, `2L`, HELOC) are things sitting in an "Optimizers" list that
recommend nothing at all.

---

## 3. Proposed organization

### 3.1 One classification source of truth

`module_catalog.CATALOG.kind` becomes the only place a module's family is
declared, and `SHEET_REGISTRY.section` / `letter_prefix` are **derived from it**
rather than hand-typed beside it. This is the same move
`_derive_sheet_tables()` already made for the four tables it consolidated; the
`kind` field was simply left out of that consolidation.

**Decided: the invariant ships first, full derivation follows with the
regrouping.** Phase 1 adds an assertion in `module_catalog.validate()` that a
sheet's `letter_prefix` matches the group implied by its module's `kind`, and
that `section` matches `letter_prefix`. That one assertion catches `2I`,
`3D`–`3F`, and every future recurrence, and it fails at import time — so the
guardrail is in place before anything moves. Full derivation of
`section`/`letter_prefix` from `kind` happens in phase 3, when the regrouping is
already rewriting that code and `test_sheet_table_consistency.py` has to be
revisited regardless. Doing the refactor twice in one file, a phase apart, is the
thing this sequencing avoids.

`kind` gains two members to match §2: `COMPARISON` (promoted from the existing
`mode=MODE_COMPARISON`, which is already a half-built version of this) and
`PROTECTION`. `HSA Drawdown` and `Tax Capacity` get `CATALOG` entries; they are
sheets with no module record today.

### 3.2 Workbook sections

```
1. Reports                (unchanged; gains Tax Capacity)
2. Optimizers             search a space, score against an objective, rank
   2.1 Plan optimizers    Roth Conversion, HSA Drawdown, Asset Allocation,
                          Asset Location, Withdrawal Sequencing, Social
                          Security, Charitable Giving, Housing, Education
                          Funding, Equity Compensation, Estate & Legacy
   2.2 This year's actions Tax-Loss Harvesting, Gain Harvesting
3. Comparisons            score alternatives the user supplied; no search
                          State Residency, S-Corp vs LLC, Scenario Analysis
4. Risks
   4.1 Stress tests       Monte Carlo, Survivor, LTC, Divorce/QDRO
   4.2 Protection decisions  Life Insurance Need, Existing Life Insurance,
                          Disability Income, P&C Umbrella
   (retired)              Planning Levers
```

**Why three decision-ish sections rather than one with subgroups.** Excel renders
one flat tab strip, so a "subgroup" is only ordering plus divider-row semantics
inside the section-summary tab — weak signal. The sharpest distinction in §2 is
*does this module recommend an answer, or does it only score alternatives you
supplied?*, and burying that in a subgroup means a reader never encounters it.
Promoting it to a section makes it visible where the reader actually looks.

This also **reduces** rename churn versus renaming §2 to "Decisions": section 2
keeps the name "Optimizers" and finally contains only optimizers. Two renames
remain, both load-bearing: "Risk & Stress Tests" → **"Risks"** (so protection
decisions fit under it), and splitting `3C` back into a stress tab and a
protection tab.

**Protection decisions stay under Risks** even though several are catalogued
`kind=OPTIMIZATION`. Placement follows the question the reader is asking — "what
could go wrong, and what do I do about it" — and the stress→protection bridge in
§4.3 depends on each coverage decision sitting beside the stress that motivates
it. The strict-consistency alternative (all searching modules under Optimizers)
was rejected for severing that adjacency. Section 4.2's divider label carries the
distinction instead.

**Action optimizers stay inside Optimizers** (§2.2) rather than becoming their own
section: they pass the search-score-rank test, so the divider is enough to mark
the different cadence.

**Tax Capacity moves to Reports**, not to a Reference section. With Planning
Levers retired there is only one worksheet left, and a section holding one tab is
not worth the structure; a consolidated headroom view reads naturally as a report.

**Planning Levers is retired.** It is `kind=REFERENCE` and, by its own docstring,
restates chosen dial positions with their source. ⚠ Before deletion, confirm
nothing else depends on it as the only provenance view for lever sources — if the
UI cannot yet show the same source attribution live, retire it *after* the row
badges from §4.7 ship, not before.

**Stable identifiers.** Add a `slug` to `SheetSpec` (`roth_conversion`,
`housing_comparison`, …) and make every cross-reference — `_replace_text_refs`,
`_SHEET_NUM_TO_STABLE`, design docs, support material — resolve display text
through `FINAL_SHEET_RENAMES[slug]` at build time. Letters stay as presentation
only. This is the fix for §1.1's shifting-letters defect and is independently
worth doing.

### 3.3 Which modules surface in the UI

**Actionability and cadence are the deciding rule — not audience.** The earlier
draft of this section justified the split by reader ("workbook = advisor
artifact, UI = household's"). Nothing in the code establishes that a second
person reads the workbook, and a rule resting on an unverified audience is a rule
that can't be applied consistently. The durable version does not assume a second
human: the UI carries decisions you revisit and can act on; the workbook stays
complete and auditable, holding depth that would only clutter a screen.

The split is therefore **permanent, not an interim triage**. Some modules are
legitimately workbook-only forever, and that is a destination rather than a
backlog.

**A module earns a UI panel when all four hold:**

1. It is an Optimizer or a Stress test (not a Comparator or Worksheet — those
   read better as a page in a document than as a screen).
2. Its demand band is `high` or `medium_high`, *or* it gates inputs the
   household must supply anyway.
3. Its result can be shown on screen without a full workbook build — or it can
   be made to (see §4.5).
4. It is revisited on a cadence that justifies a screen, and there is an action
   you would take from it — not a one-time or advisor-cadence analysis you read
   once and file.

Applying it:

| | Workbook | UI | Change |
| --- | --- | --- | --- |
| Roth Conversion | ✓ | ✓ | Add result display, not just inputs |
| Asset Allocation | ✓ | ✓ | — |
| Social Security | ✓ | **add** | `high` demand, household-owned, one scalar decision. The clearest gap. |
| HSA Drawdown | ✓ | **add** | Currently reachable only by setting a mode field with no visible consequence. |
| Housing | ✓ | ✓ | Keep both engines, named honestly: "When to move" (workbook) vs "Where to live" (UI) — §1.4 |
| Charitable Giving | ✓ | ✓ | — |
| Harvesting (TLH + Gain) | ✓ ✓ | **add, as one panel** | Action-cadence; belongs near holdings, not in the plan-optimizer stack. Ships as an exportable trade list, not a writeback (§4.3) |
| Withdrawal Sequencing | hidden → restore | **add** | `medium_high`; currently invisible in both surfaces |
| Estate & Legacy | ✓ | no | Advisor-led; inputs already live on Estate Inputs |
| State Residency | ✓ | no | Comparator; the old UI screen was already retired for being mostly dead |
| S-Corp vs LLC | ✓ | no | Comparator; advisor/CPA decision |
| Tax Capacity, Planning Levers | ✓ (§4) | no | Worksheets |
| Education / Equity Comp / Special Needs / Business Succession | ✓ | no | `low`/`niche`; input pages suffice |
| Monte Carlo, Survivor, LTC | ✓ | ✓ | — |
| Divorce / QDRO | **add** | ✓ | UI-only stress test with no workbook counterpart — asymmetry with no stated reason |
| HELOC | n/a | **move to Assets & Protection** | Reclassify as a plan input — a liability held against an asset. Stop calling it an optimizer. Feeds #330's nav categories |
| Scenario Analysis | hidden → restore | ✓ | The UI elevates it to a screen while the workbook hides the sheet |

The UI's Optimize screen then reads: Roth Conversion · HSA Drawdown · Asset
Allocation · Withdrawal Sequencing · Social Security · Next Housing Move ·
Charitable Giving · Harvesting. Stress Test keeps its four and gains nothing.
`strategySection()`'s registry already takes exactly this shape, so the UI side
of this is section-list edits plus the new panels — no new primitive.

---

## 4. Apply-to-plan design

### 4.1 Three apply mechanisms already exist, unnamed

Grounding first, because the vocabulary problem here is worse than the missing
feature:

**(a) Mode-switch auto-apply at build time.** Setting `roth_policy='optimize'`
makes `optimize_roth_conversion_strategy()` run *inside* the build and mutate
`c` with the winning candidate. `hsa_withdrawal_mode='optimize'` and
`allocation_selection_mode='optimizer_recommendation'` behave the same way. The
recommendation is therefore **already applied, continuously, and re-derived from
scratch on every build.** Nothing in the UI says so.

**(b) Materialize into plan inputs.** `copyOptimizerOverrideToUserTargets()`
writes optimizer percentages into the user-defined allocation rows via
`editValue(row_index, value, null)`, which stages them in the `dirty` map for
`saveAll()`. This freezes one snapshot of the recommendation as explicit plan
data.

**(c) Navigate and retype.** `adoptCase()` shows a persistent warning and calls
`setStep(first.sourceStep)`. Zero automation, by design.

There is also a near-miss: `promotePlanningCase()` already implements a full
confirm-then-apply flow — it lists `label: before → after` per override, asks
for confirmation, and applies each via `editValue(x.row_index, x.afterRaw)`.
**It works on any Planning Case whose overrides carry a `row_index`.** That is
the machinery this design needs; it simply has no optimizer producing input for
it today.

### 4.2 The contract

An optimizer result becomes appliable by emitting an **optimizer patch**: a list
of items in the *existing* `overrideFromRow()` shape —
`{sourceStep, section, subsection, field, label, before, after, afterRaw,
row_index, rationale}`. Items with a `row_index` are promotable; items without
are advisory and route the user to a source page.

Apply = construct a Planning Case with `source: "optimizer"` and that patch,
then hand it to the existing promote path. Consequences that fall out for free:

- The confirmation dialog, the `before → after` list, and `editValue` +
  `saveAll` persistence already exist and are already tested.
- `before` is captured per item, so **un-apply is just the reverse patch** — no
  new storage, no snapshot format.
- The Unified Comparison Matrix, Decision panel and Saved Cases list pick the
  case up with no changes, because it is the same record type.
- The case store's `source` enum gains one value. The 2026-09-17 design
  explicitly declined to add a source type for housing; adding one *now*, for a
  generalized optimizer-apply flow, is the change that design was leaving room
  for rather than one it ruled out. **Decided: add exactly one value,
  `"optimizer"`.** Per-optimizer source values were rejected — an enum that grows
  with every optimizer is the same hand-maintained-list failure mode §3.1 exists
  to eliminate. Which optimizer produced a case belongs in the case's provenance
  note, not in the type system.

### 4.3 Apply semantics per optimizer type

Applying is not one operation. Four distinct shapes:

**Policy adoption (mode switch).** Roth Conversion, HSA Drawdown, Asset
Allocation. The patch sets a *mode* row (`roth_conversion_policy` = `optimize`,
etc.). The plan then re-optimizes every build and tracks changing inputs. Live,
not frozen.

**Schedule freeze.** The same three optimizers, alternate intent: write the
chosen year-by-year amounts as explicit rows (forced conversions, target
percentages). The plan stops re-optimizing. Deterministic and auditable.

These two are different decisions and the UI must make the user pick. Today
mode (a) happens silently and mode (b) is one button on one panel.

**Decided: both are offered, and policy adoption is the default.** The primary
action reads **"Let the plan keep optimizing this"**; the secondary reads **"Lock
in this schedule."** Defaulting to policy adoption means existing plans keep
behaving exactly as they do today — this change names the behavior rather than
altering it, so no plan silently changes its numbers when the feature ships. The
honesty problem it fixes is addressed by §4.7's disclosure, not by changing what
the plan does.

**Scalar adoption.** Social Security (claiming ages), Withdrawal Sequencing
(draw order). One or two rows; the simplest case; straight `row_index` patch.

**Structural adoption.** Housing. The winning candidate spans sale year, step
type, step year, purchase price, ZIP/state, and financing — multiple sections,
some rows possibly absent until created. This is the only optimizer whose patch
is not a set of existing-row edits, and it is also the one with *no* apply path
today. Proposal: emit `row_index` items for the Housing rows that exist and
advisory items with `sourceStep: 'assets_home_cash'` for the rest; `editValue`'s
existing housing hook (`reestimateHousingCostsOnValueChange`) then re-estimates
utilities/maintenance/insurance automatically, which is exactly the desired
behavior and already implemented.

**Trade list export (action optimizers).** Harvesting recommends *trades*, not
assumptions, so it has no apply path at all. **Decided: it exports an executable
list of lots** — the affordance reads **"Export trade list"** and produces a
CSV/printable artifact you take to the broker. Nothing is written back.

The rejected alternative was a "Record as executed" writeback to YTD
transactions. It closes the loop more completely, but it writes basis data, and
basis written from a *recommendation* rather than a confirmed fill is a silent
corruption risk with no cheap way to detect it. Export delivers the actionability
without touching the tax lots. If a YTD writeback is wanted later it should be
driven by confirmed broker fills, not by this optimizer's output.

**Stress tests: no apply.** A stress result is never adopted — adopting "the
market fell 40%" is meaningless. Stress panels keep only "Save as stress case,"
which writes their *inputs* and is what `stressOverrideItems()` already does.
The only legitimate stress→plan edge is the protection decisions (§3.2): a
survivor shortfall implies a coverage amount, and *that* is an ordinary scalar
apply on the insurance rows.

**Decided: that bridge is built, and it is the only one.** A failed LTC or
survivor stress surfaces a "size the coverage" affordance that hands off to the
corresponding protection decision, which then applies as a scalar patch like any
other optimizer. The stress result itself is still never adopted — what gets
applied is the coverage amount the protection module recommends in response to
it. This is why protection decisions sit beside the stress tests in the workbook
layout (§3.2) rather than under Optimizers: the adjacency is the feature.

A general "remediate this failure" affordance (cut spending, delay retirement,
raise reserves) was considered and rejected for now — it needs its own objective
function to rank remediations, which is a new optimizer rather than a bridge.

### 4.4 Where the affordance lives

A footer bar on each optimizer's `strategySection`, extending rather than
replacing `analysisFrame()`'s existing "Preview impact (Planning overview)"
footer — which already establishes the pattern of a per-section action strip and
already routes to the Workbench.

Three states, left to right:

- **Explore** (default) — Run / recompute. Result table visible.
- **Pin** — "Save as planning case." Creates the case with the patch,
  unadopted. Exists so a user can compare two optimizer results in the matrix
  before committing, which is the whole point of the Workbench.
- **Apply to plan** — runs the promote confirmation, writes rows into `dirty`,
  then tells the truth about what remains: *"N changes staged. Save Changes,
  then rebuild."* It does **not** silently save or build. This matters — the
  whole app's staleness model (`dashboard_source_truth_banners`'s
  `build_impact`/`review` notices) assumes edits are staged-then-saved-then-built,
  and an optimizer that skips straight to a build would bypass it.

Housing's panel is not `analysisFrame`-wrapped (deliberately — it is a
self-contained search, per its own comment). It gets the same three-button strip
appended to its own results table instead.

### 4.5 A prerequisite: results must exist in the UI

Four of five current UI optimizer panels are input forms. There is nothing to
apply because there is nothing on screen. So Apply-to-plan depends on each
optimizer having a **UI-visible result**, by one of:

1. **Read from the last build.** `roth_optimization` / `roth_strategy_result`
   are already attached to the plan result the workbook reads. Surfacing the
   top-N candidate table in the Roth panel is a display change over data that
   already exists — the cheapest path, and it is exactly what
   `planningLeversBaselineReady()` already gates on.
2. **A run endpoint.** What Housing already has (`startHousingOptimization()` →
   server route → results payload). Right for anything the user should be able
   to re-run without a full build.
3. **Client-side preview.** What Asset Allocation already has
   (`optimizerPreviewTarget`, `resetAllocationPreview`). Only viable for cheap
   optimizers.

Path 1 covers Roth, HSA, Social Security and Withdrawal Sequencing with no new
compute. That should be the default, with path 2 reserved for optimizers whose
inputs the user tunes iteratively.

### 4.6 Applied state, honestly

Resist storing an `applied: true` flag on the optimizer. The plan rows **are**
the source of truth; once written, the applied values are indistinguishable from
values the user typed, and a stored flag goes stale the moment anyone edits a
row by hand.

Instead: **"Applied" is computed** by comparing the optimizer's current result
against the live values of the rows in its patch. Three honest states —
*not applied* (rows differ), *applied* (all rows match), *diverged* (some match,
some do not, i.e. applied then edited). The Planning Case record keeps the
provenance ("applied from Roth optimizer, 2026-09-19, case X") as an audit note,
not as the state itself.

**Un-apply** = promote the reverse patch (`after` ↔ `before`), through the same
confirmation. Available while the case exists and the rows still match.

**Workbook reflection** is automatic and needs no new wiring: the workbook is
built from saved plan data, so applied → saved → rebuilt → the workbook shows
it. An *unapplied* optimizer result reaches the workbook only as its own sheet's
candidate table, which is correct — the workbook shows what the plan is, plus
what it could be.

**Caveat to state plainly:** the Planning Case store is `localStorage`
(`retirement.planning_case_v1`, capped at 25 cases). Provenance and un-apply
capability are therefore browser-local and lost on cache clear, while the
applied *values* are safely in the plan.

**Decided: keep `localStorage`, and say so rather than implying permanence.**
What is browser-local is an audit note and the convenience of un-apply — never
plan data. Moving Planning Cases server-side is a project in its own right and
out of scope here. Two obligations follow, and they are the price of this choice:
the UI must not present provenance as a durable audit trail, and un-apply must be
described as available while the case exists, not forever. If provenance later
needs to be load-bearing, the Build History schema-versioning work is the
adjacent prior art to build on.

### 4.7 Disclosing what the optimizer is driving

Because policy adoption is the default (§4.3), a plan can be silently
self-optimizing — which is exactly today's behavior, and today nothing says so.
Naming the behavior is the point of the change, so disclosure is a requirement of
this design, not a nicety.

**Decided: a row-level badge plus a section-level banner.**

- **Row badge.** Any row whose current value is live optimizer output carries a
  marker. This is the part that matters: without it, a number on screen is
  indistinguishable from one you typed, and §4.6's *applied* / *diverged* states
  are computed but invisible at the point where you'd act on them.
- **Section banner.** Each optimizer section in live mode states plainly that the
  plan re-optimizes this on every build, and offers the switch to "Lock in this
  schedule."

Build both on the existing `dashboard_source_truth_banners.js` machinery rather
than introducing a parallel indicator system — it already owns the vocabulary for
`build_impact` and `review` notices, and a second, differently-styled way of
saying "this value is not what you think it is" would undercut the first.

The three §4.6 states map directly onto the badge: *not applied* (no badge),
*applied* (badge, values match), *diverged* (badge with a warning affordance —
applied, then hand-edited). The diverged state is the one that most needs to be
visible and is impossible to surface without per-row marking.

---

## 5. Decisions

All eleven open questions raised by the first draft were resolved on 2026-09-19,
along with seven follow-on questions the answers exposed. Recorded here as the
decision plus the reasoning that survives it — the rejected alternatives matter,
because several are the obvious thing to reach for again in six months.

| # | Question | Decision |
| --- | --- | --- |
| O1 | UI parity, or permanent split? | **Permanent split, by actionability and cadence.** Audience was never verified and is no longer the rule (§3.3). |
| O2 | Is "Comparator" a user-facing word? | **Yes — "Comparisons" is the visible label**, and it is a top-level section, not a subgroup. |
| O3 | Two housing engines | **Keep both, name them honestly**: "Where to live" vs "When to move" (§1.4). Chaining deferred. |
| O4 | Are stress tests ever appliable? | **No — but build the protection bridge.** A failed stress sizes a coverage decision, which applies as an ordinary scalar (§4.3). |
| O5 | Policy adoption vs schedule freeze | **Offer both; policy adoption is the default.** No existing plan changes behavior; §4.7 supplies the honesty instead. |
| O6 | Planning Case `source` enum | **Add exactly one value, `"optimizer"`** (§4.2). Per-optimizer values rejected. |
| O7 | Rename + slug sequencing | **Slug ships first, separately** (phase 2 before 3). Section 2 keeps the name "Optimizers"; only "Risks" is renamed. |
| O8 | Server-side provenance? | **No — keep `localStorage`, and state the limitation** rather than implying permanence (§4.6). |
| O9 | Hidden modules | **Restore all three.** Withdrawal Sequencing, Asset Location and Scenario Analysis each get their own tab back. |
| O10 | `3C. LTC + Life Insurance` | **Split, and regroup**: the LTC stress tab separates, and Life Insurance Need joins the other protection decisions (§3.2). |
| O11 | HELOC's home | **Assets & Protection** — a liability held against an asset. Feeds #330's nav categories. |

Follow-on decisions:

| # | Question | Decision |
| --- | --- | --- |
| F1 | Top-level section structure | **Three decision-ish sections, not one with subgroups**: Optimizers / Comparisons / Risks (§3.2). Excel's flat tab strip makes subgroups near-invisible. |
| F2 | Where do protection decisions sit? | **Under Risks**, beside the stresses they hedge, despite several being `kind=OPTIMIZATION`. The adjacency is what O4's bridge depends on. |
| F3 | Where do action optimizers sit? | **Inside Optimizers**, as a "This year's actions" divider. They pass search-score-rank; only the cadence differs. |
| F4 | Worksheets | **Retire Planning Levers; keep Tax Capacity.** See the ⚠ in §3.2 — confirm nothing depends on Levers as the sole lever-provenance view before deleting. |
| F5 | Disclosing live optimizer output | **Row badge + section banner**, built on the existing source-truth banner machinery (§4.7). Required, not optional, given F-O5. |
| F6 | Harvesting apply semantics | **Export a trade list.** No YTD writeback — basis written from a recommendation rather than a confirmed fill is an undetectable corruption risk (§4.3). |
| F7 | `kind` as single source of truth | **Invariant in phase 1, full derivation in phase 3** (§3.1), so the guardrail lands before anything moves. |

### 5.1 Still open

- **Tax Capacity's placement was resolved by inference, not by decision.** With
  Planning Levers retired, one worksheet does not justify its own section, so
  §3.2 folds Tax Capacity into Reports. Confirm that reading — the alternative is
  a one-tab Reference section.
- **Planning Levers' retirement is gated** on confirming nothing else relies on
  it as the only place lever provenance is shown (§3.2). If the UI cannot yet
  show source attribution live, retire it after §4.7's badges ship.
- **Deferred, not rejected:** chaining the two housing engines (§1.4); a YTD
  writeback driven by confirmed broker fills (§4.3); a general stress-remediation
  optimizer (§4.3); server-side Planning Cases (§4.6).

---

## 6. Indicative phasing (not scoped for execution)

Per project convention, with model/effort and usage character. These are
relative sketches for planning only; a real plan follows separately, after the
open questions above are answered.

Now that §5 is settled these are firmer, and the order is fixed by two of the
decisions: slug before regrouping (O7), and Roth end-to-end before any other
result panel (F-phase-5).

| # | Phase | Model / effort | Turns | Context driver | Weight vs. a 5-hr session |
| --- | --- | --- | --- | --- | --- |
| 1 | Classification invariant in `module_catalog.validate()`; missing `CATALOG` entries (HSA Drawdown, Tax Capacity); fix `3D`–`3F` section/letter contradiction | Sonnet, medium | ~10–15 | Two files, both already read; one test file | Light |
| 2 | Stable `slug` on `SheetSpec`; route cross-references through it. **Ships alone** (O7) | Sonnet, medium | ~20–30 | `_replace_text_refs` touches every cell of every sheet — verification is a full workbook build, not a unit test | Moderate |
| 3 | Regroup into Optimizers / Comparisons / Risks; rename to "Risks"; split `3C`; retire Planning Levers; move Tax Capacity to Reports; **full `kind` derivation** (F7) | Sonnet, medium | ~20–30 | Depends on phase 2; `test_sheet_table_consistency.py` pins the derived shape and needs deliberate updating. Larger than the first draft's phase 3 because derivation folded in | Moderate |
| 4 | UI section-registry changes; restore the three hidden modules; move HELOC to Assets & Protection | Sonnet, medium | ~15–20 | `dashboard_decomp_strategy_workspace.js` is small; `navigation.js` redirects are the fiddly part | Light |
| 5 | **Roth result panel only**, end to end (path 1: read from last build) | Opus, high | ~15–25 | One renderer, not eight. `dashboard_decomp_row_model.js` is 5,188 lines and will still be read repeatedly | Moderate |
| 5b | Remaining result panels, as repetitions of phase 5's proven pattern | Sonnet, medium | ~15–20 each | Per-panel; cheap only if phase 5 genuinely established the pattern | Moderate per panel — **do not batch** |
| 6 | Apply-to-plan: optimizer patch contract + reuse of the promote path, plus §4.7 badges | Opus, high | ~30–40 | Cross-cutting; correctness-critical (it writes plan data); needs real test coverage per patch shape | **Heavy** |
| 7 | Housing: rename both engines, state each panel's question | Sonnet, low | ~5–10 | Naming and copy only — O3 chose "keep both," so this is no longer an engine project | **Light** (was Heavy) |

**Disproportionately expensive, with scoping advice:**

- **Phase 6 is now the only Heavy phase** and the one to watch. It writes plan
  data, which invites a repeated test-fix cycle. Constrain it by building on
  `promotePlanningCase`'s existing, tested path rather than a new apply
  mechanism, and by covering one patch shape (scalar adoption — Social Security)
  before the structural one (Housing). Treat the §4.7 badges as a separate
  commit inside the phase so a stalled apply path doesn't block the disclosure
  work, which has standalone value.
- **Phase 5 dropped from Heavy to Moderate** purely by scoping it to Roth. Hold
  that line: the temptation at 5b will be to batch the remaining panels into one
  session, which rebuilds the original Heavy phase under a different name.
- **Phase 2 looks small and is not.** `_replace_text_refs` is a full-workbook
  string pass, so verification means building workbooks under several
  module-toggle combinations. Cap it by pinning two or three representative
  toggle configurations rather than sweeping them.
- **Phase 3 grew** by absorbing the full `kind` derivation (F7). That is the
  right trade — it avoids touching the same file twice a phase apart — but it
  means phase 3 is no longer a pure data move, and its test churn is real.
- **Phase 7 collapsed** from the largest item in the first draft to the
  smallest, entirely because O3 chose to keep both engines. If the deferred
  chaining option (§1.4) is ever taken up, it returns as a Heavy phase of its
  own and should be planned separately.

Check `/usage` against these estimates as any resulting plan executes — the
relative weights above are the useful signal, not absolute figures.
