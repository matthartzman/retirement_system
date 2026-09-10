# Modularization implementation plan — 2026-09-09

**Basis:** two design documents, both design-only, neither started:

* `docs/superpowers/plans/2026-09-09-dashboard-js-modularization-design.md` — `frontend/js/dashboard.js`, 7,512 lines
* `docs/superpowers/plans/2026-09-09-planning-engines-modularization-design.md` — `src/planning_engines.py`, 6,418 lines

**Status:** not started. This plan sequences both and assigns a model tier and
reasoning effort per item, following the policy convention established in
`documentation/reports/REMAINING_WORK_PLAN_2026-08-12.md` §5.

**Scope decision (2026-09-09):** the three tails both design docs left optional —
dashboard Tier C, engine Tier 3, and the `core` consumer cleanup — are **in
scope**, scheduled as M6, M7 and M8. Committed scope is **61–97 turns**, taking
`dashboard.js` to ~1,500 lines and `planning_engines.py` to a ~200-line façade.
See §5 decision 4 for what that overrides and why it is defensible.

**Conventions inherited:** worktree-per-lane with disjoint blast radius; one
batch per session with a hard stop at the batch boundary; effort down before
model down on specified work.

---

## 1. Why these two share one plan

They touch no common code — JavaScript under `frontend/js/` versus Python under
`src/`, different tools, different design docs. What they share is the thing that
actually schedules work here: **one `pytest tests/` gate on one CI job.** The
engine lane touches tests that 123 files import; the dashboard lane touches the
`dashboard_decomp_*.js` glob that 277 test files depend on. Both lanes run the
same suite, so a red suite during a two-lane window is ambiguous, and ambiguity
is what made the F3 batches expensive last time.

So this plan does not treat them as one project. It treats them as **two lanes
sharing one gate**, and its whole job is deciding which lane holds the gate when.

The second reason to weave them is that neither doc's ordering is optimal on its
own:

* The dashboard doc's Tier A is the cheapest, highest-yield work in either
  document (~330 lines/turn) and needs nothing from the engine lane.
* The engine doc's Pass 0 and P1 are the highest-value work in either document
  and are **not refactoring at all** — one removes a live correctness trap, the
  other closes a hole in the gating baseline. They should not wait behind a
  frontend refactor.
* The engine doc lists Tier 2 (`roth_strategy.py`) *after* Tier 1 (Monte Carlo).
  **This plan reverses that** — see M1.4.
* The engine doc treats the `core` consumer cleanup as an optional later pass.
  With the tails committed, **this plan runs it before Tier 3** (M7 → M8) — see
  M7's rationale.

The third reason is only visible once the full scope is committed: **the two
lanes finish at different times and that is useful.** The dashboard lane
completes at M6 and has no dependency on the engine lane; M8 is the phase most
likely to overrun. Running them as one plan makes "the frontend is done, the
engine is mid-flight" a stated, expected state rather than a stall.

---

## 2. Strategy — what this plan optimizes for

1. **Instrument before moving anything.** Every tool change, every new test, and
   both correctness fixes land in M0, before a single line moves. Four of the six
   guards protect against *silent* failure modes; none of them are worth adding
   after the pass they were supposed to guard.
2. **Harvest the covered work early.** M1 is everything already protected by a
   test that exists today. It is ~40% of the dashboard file and 12% of the engine
   file, at the lowest risk in the plan.
3. **Concentrate risk, don't spread it.** The two riskiest phases — M3 (3,120
   lines of numerically sensitive Monte Carlo) and M8 (the widest import surface
   in the plan) — each get sole occupancy of the shared gate. Nothing else lands
   in those windows, so a red suite has exactly one candidate cause.
4. **Keep every phase boundary a resting point.** The full scope is committed,
   but no phase leaves either file in a state that *requires* the next one. M5
   and M6 are named contingency lines in §4 for that reason. This is what the
   2026-08-12 scope decision bought by deferring F3.5, and committing the tails
   should not spend it.
5. **Front-load the analysis that later phases depend on.** M7 exists before M8
   because Tier 3's central question is unanswerable while 23 laundered names are
   still in the answer — the same argument engine design §2.2(c) makes about
   static analysis generally.

---

## 3. The plan

### Phase M0 — Instrument · blocks everything that moves a line

| ID | Item | Model · effort | Turns |
|---|---|---|---:|
| M0.1 | **Engine Pass 0.** Replace `from .core import *` (`planning_engines.py:2423`) with an explicit re-export list. Handle the `rmd_divisor` clobber-and-patch at L2429. Delete the three stale `BEGIN/END` section markers this touches. | **opus · high** | 2–3 |
| M0.2 | **P3** — assert no `import *` anywhere in `src/`. | sonnet · low | 0–1 |
| M0.3 | **P2** — import-direction test: nothing under `src/monte_carlo/` or `src/engine_*.py` is imported at module scope by `planning_engines.py`; no non-deferred cycle. Must pass against the *current* layout before it guards a change. | opus · medium | 1–2 |
| M0.4 | **Dashboard Pass 0.** `--content-tables` mode in `extract_module.mjs`, with all four AST-checked conditions — the load-bearing one being *no mutation sites anywhere in the repo*, since a `const` object is still mutable. | **opus · high** | 2–3 |
| M0.5 | **Refusal test** for M0.4: a fixture table mutated via `Object.assign` elsewhere must be refused. Without this, the mutation condition is a comment. | sonnet · medium | 1 |
| M0.6 | **Naming-glob test** — every `<script>` in `index.html`'s extracted-module block matches the glob `tests/_decomp_dashboard.py` uses. | sonnet · medium | 1 |
| | **Subtotal** | | **7–11** |

**M0.1 and M0.4 are opus · high because they are the two items whose failure is
silent.** M0.1's wildcard fails as a wrong *number*, not an import error. M0.4's
mutation check, if wrong, permits a move that corrupts shared state at runtime.

**M0.6 guards the highest-consequence, lowest-visibility hazard in either doc:**
a module named `field_guidance_content.js` instead of
`dashboard_decomp_field_guidance_content.js` silently drops 2,462 lines out of
every content-assertion test in the suite — and those tests would **pass**.

**Exit criteria:** full `pytest tests/`, `node --test tests/frontend/`, and
`tools/release_gate.py` green. No line of production code has moved.

---

### Phase M1 — Harvest · everything already covered by a test that exists

| ID | Item | Model · effort | Turns |
|---|---|---|---:|
| M1.1 | **Dashboard A1** — `FIELD_GUIDANCE_OVERRIDES` (2,462 lines, 33% of the file) into `dashboard_decomp_field_guidance_content.js`. Zero readers inside dashboard.js; one in `row_model.js`. | sonnet · medium | 1–2 |
| M1.2 | **Dashboard A2** — step catalogue: `STEPS` + `SPENDING_WORKFLOW_STEPS` + `SPENDING_WORKFLOW_INDEX` + `SUGGESTED_NEXT` + `STRATEGY_TABS` + `REPORTS_TABS`. | opus · medium | 2–3 |
| M1.3 | **Dashboard A3** — help content: `STEP_HELP`, `SYSTEM_CONFIG_FIELD_HELP`, `TERM_NOTES`, `FIELD_TOOLTIPS` + `pageHelp`/`addParentheticals`/`helpList`/`stepHelpLinkHtml`. Plus the script-order test. | **opus · high** | 3–4 |
| M1.4 | **Engine Tier 2** — `src/roth_strategy.py` (761 lines). | **opus · high** | 2–4 |
| | **Subtotal** | | **8–13** |

**M1.1 is the single best value-per-turn item in either document** and is
sonnet · medium precisely because M0.4/M0.5/M0.6 already did the thinking:
`finish_extraction.mjs` automates index.html wiring, census, bridge, clusters
report, manifest and ratchet, and `--check` proves the move was lossless by
reconstructing dashboard.js from its own output. The judgement was front-loaded.

**M1.3 is opus · high for one reason:** `STEP_HELP` is not an inert literal — it
calls `pageHelp()` at module-evaluation time, which reaches into `row_model.js`
and `dashboard_shared_helpers.js`. Get the script order wrong and it fails at
load with a bare `ReferenceError` for a reason invisible from the code.

**M1.4 is the ordering change from the engine design doc, and it is
verified, not assumed.** All 10 synthetic golden-master scenarios run
`optimize_roth_conversion_strategy` (`synthetic_plans.py:371`, confirmed
2026-09-09), so the Roth optimizer's behaviour is **already pinned today** by the
existing 125.4s deterministic gate. It therefore needs no new safety net, and it
serves as a rehearsal of the Python extraction pipeline — which has no
`--check` round-trip equivalent — under existing protection, before M3 moves
3,120 lines that have none. The design doc's reason for the other order (writing
one import once rather than twice) is worth one import line.

**Exit criteria:** `dashboard.js` at ~4,170 lines with the ratchet lowered in
each commit; `planning_engines.py` at ~5,660; golden-master pins unmoved.

---

### Phase M2 — Safety net · the gate on everything in M3

| ID | Item | Model · effort | Turns |
|---|---|---|---:|
| M2.1 | **P1** — fixed-seed Monte Carlo golden master. Vectorized at `n_sims=1000, mc_sensitivity_sims=200` and scalar at `n_sims=100, mc_sensitivity_sims=1`, all 10 scenarios, ~49s added. Plus one scenario at `n_sims=10, mc_sensitivity_sims=10` to cover the scalar sensitivity-grid path (L4326–4334), which the main pins do not reach. | **opus · max** | 3–4 |
| | **Subtotal** | | **3–4** |

The runtime feasibility question is closed by measurement (engine design §2.4):
`project()` is 25 ms, the vectorized engine is flat in `n_sims`, and the 85s
outlier was the sensitivity grid, not the paths. This gates every merge.

**opus · max, and this is the item where the tier matters most.** Its job is to
decide *what to pin* on code that currently has no pins at all — an
under-specified metric set produces a green suite that proves nothing, which is
the exact failure this phase exists to prevent. It also inherits the 2026-08-12
plan's rule 1: an item whose job is to re-check something the record treated as
settled gets the top tier regardless of diff size.

**Exit criteria:** MC pins generated, committed, and *demonstrated to fail* under
a deliberate one-line perturbation of RNG consumption order. A pin that has never
been seen to fail is not yet a safety net.

---

### Phase M3 — Monte Carlo extraction · sole occupancy of the shared gate

| ID | Item | Model · effort | Turns |
|---|---|---|---:|
| M3.1 | **1a** — `sampling.py` + `bucket_flows.py`; also reunites `_mc_bucket_return_tilts` / `_mc_apply_bucket_growth`, stranded at L99–171. | opus · medium | 2–3 |
| M3.2 | **1b** — `spending_cuts.py`, three self-contained public functions. | sonnet · medium | 1–2 |
| M3.3 | **1c** — `scalar.py`, including one 576-line function. | **opus · high** | 2–4 |
| M3.4 | **1d** — `vectorized.py`, 1,085 lines including a 552-line function. | **opus · high** | 3–5 |
| M3.5 | **1e** — `dispatch.py` + `__init__.py` + `report_compute.py:20`. | opus · medium | 2–3 |
| | **Subtotal** | | **10–17** |

**No other lane lands during M3.** The dashboard lane may develop in its worktree
but must not merge; see §4.

**Per-item gate:** golden-master pins unmoved (deterministic *and* the M2.1 MC
pins), then `pytest tests/ -k "monte_carlo or mc_ or roth_strategy or
scalar_vectorized"`, then full suite. **If any pinned value changes, that is a
bug in the extraction, not a golden-master update** — ticket 3.10's rule, carried
forward.

**Review rule for every M3 commit:** the diff shows only deletions from
`planning_engines.py` and additions to the new module, with the moved text
byte-identical. There is no Python equivalent of `extract_module.mjs --check`;
this rule is the substitute, and building the tool is not worth it for five moves.

**Exit criteria:** `planning_engines.py` at ~2,440 lines; no module-scope import
of `src/monte_carlo/` from `planning_engines` (M0.3 asserts this).

---

### Phase M4 — Domain modules · dashboard Tier B

Re-run `find_clusters.mjs` and `cluster_deps.mjs` before each item; every
extraction changes the graph for the next.

| ID | Item | Model · effort | Turns |
|---|---|---|---:|
| M4.1 | **B1** `dashboard_decomp_value_format.js` (11 fns, 102 lines) — smallest, calibrates the rest. | sonnet · medium | 1–2 |
| M4.2 | **B2** `dashboard_decomp_ytd_accounts.js` (20 fns, 273) — Playwright covers the file-system flows. | opus · medium | 2–3 |
| M4.3 | **B3** `dashboard_decomp_planning_cases.js` (28 fns, 217). | opus · medium | 2–3 |
| M4.4 | **B4** `dashboard_decomp_detailed_workbook.js` (19 fns, 316). | opus · medium | 2–3 |
| M4.5 | **B5** `dashboard_decomp_build_snapshot.js` (14 fns, 271) — widest write surface; the bridge-setter check earns its keep here. | **opus · high** | 2–3 |
| M4.6 | **B6** `dashboard_decomp_field_guidance.js` (25 fns, 650) — largest; touches the help system M1.3 moved. | **opus · high** | 3–4 |
| | **Subtotal** | | **12–18** |

**Batching option:** `extract_batch.mjs` could compress M4.1–M4.5 into ~6 turns.
The manifest records what that trades: v9 batched five clusters and broke four
tests; v10 did one cluster and broke zero. Take the batch only if M4.1 lands
clean on the first attempt.

**Exit criteria:** `dashboard.js` at ~2,340 lines; ratchet lowered each commit.

---

### Phase M5 — Mid-point close-out · not the end of the plan

| ID | Item | Model · effort | Turns |
|---|---|---|---:|
| M5.1 | Relax M2.1's scalar pins to 3 scenarios (~7s), keeping the vectorized set. Maximum RNG-order sensitivity is a refactor guard, not a permanent property worth maintaining. **Deferred to M9 if M8 is running close behind** — M8 moves engine code the pins still guard. | sonnet · low | 1 |
| M5.2 | Update `phase3_module_manifest.js` (v14) and both design docs with what actually happened, including anything that contradicted either design. | sonnet · medium | 1 |
| | **Subtotal** | | **2** |

The former M5.3 decision gate is **removed**. Scope decision 2026-09-09 (§5)
committed all three tails up front, so there is nothing to gate — they are
M6–M8 below, with model and effort assigned like every other phase.

---

### Phase M6 — Dashboard Tier C · return the orphans to domains that already exist

47 functions / ~808 lines. **This is append-to-existing, not create-new** — which
is what distinguishes it from the F3.5 proposal the 2026-08-12 scope decision
correctly rejected. F3.5 wanted to invent themed modules to house these; M6
returns each one to the domain module its subject already lives in.

| ID | Item | Model · effort | Turns |
|---|---|---|---:|
| M6.1 | **`--append-to` mode** in `extract_module.mjs`, plus its round-trip check against an existing module (the `--check` reconstruction has to prove *both* files, not just the new one). | **opus · high** | 2–3 |
| M6.2 | Allocation orphans (`allocationPreview*` ×4, `validateAllocationTargetsOrMessage`, ~67 lines) → `dashboard_decomp_allocation_optimizer.js`; housing/scenario orphans (`baseHomeSaleYearRow`, `stressHomeSaleYearRow`, `scenarioRowKeyFromParts`, ~28) → `dashboard_decomp_housing_scenarios.js`. | sonnet · medium | 1–2 |
| M6.3 | Spending orphans (9 fns, ~140 lines) → `dashboard_decomp_spending_taxonomy.js`. | opus · medium | 1–2 |
| M6.4 | Withdrawal/Roth surface (`renderWithdrawalStrategy` 80 lines, `renderWithdrawalOrderTable`, `withdrawalOtherRows`, `boolishValue`). | opus · medium | 1–2 |
| M6.5 | New `dashboard_decomp_household_residency.js` (`renderHouseholdPeople`, `personCellInput`, `personNickPlaceholder`, `renderStateResidency`, ~94 lines) — the only genuinely new module Tier C needs — plus the residual sweep and final ratchet. | sonnet · medium | 1 |
| | **Subtotal** | | **6–10** |

**Exit criteria:** `dashboard.js` at ~1,500 lines — boot, `renderMain` dispatch,
`showStepHelp`, ~90 shared state `let`s, and the ~200-line generated bridge,
which cannot leave (it references module-private bindings by name).

---

### Phase M7 — `core` consumer cleanup · ordered *before* M8, deliberately

| ID | Item | Model · effort | Turns |
|---|---|---|---:|
| M7.1 | Point the 23 laundered names at their real home: `from ..planning_engines import EvDeath` → `from ..core import EvDeath`, across `projection_stages/` (6 modules), plus `ensure_engine_config` back to `plan_config`. Then shrink M0.1's explicit re-export list to what is genuinely still re-exported. | opus · medium | 2–3 |
| | **Subtotal** | | **2–3** |

**Why this moves ahead of M8** — the standalone design listed it as an optional
later pass. Engine design §2.2(c) is the reason to reverse that: the wildcard
"defeats static analysis of exactly the question this refactor needs answered."
M8's central question is *which names does each consumer still need from
`planning_engines`* — and that question is only answerable once the 23 names that
were never `planning_engines`' to begin with have stopped appearing in the answer.
Doing M7 second would mean editing the same import blocks twice with the harder
edit first.

---

### Phase M8 — Engine Tier 3 · risk-ascending by measured importer count

Five modules, ordered by how many files reach into each. Counts measured
2026-09-09 across `src/` and `tests/`:

| ID | Item | Importers | Model · effort | Turns |
|---|---|---|---|---:|
| M8.1 | `src/engine_growth.py` (199 lines) | **1** file, 0 in `src/` | sonnet · medium | 1–2 |
| M8.2 | `src/engine_rmd.py` (165) | 3 files, 1 in `src/` | opus · medium | 1–2 |
| M8.3 | `src/engine_inheritance.py` (424) | 4 files, 2 in `src/` | opus · medium | 2–3 |
| M8.4 | `src/engine_withdrawal.py` (781) | 8 files, 1 `ImportFrom` — **plus 10 `_legacy_pe.` attribute call sites** across the `withdrawal_cascade_*` stages | **opus · high** | 2–4 |
| M8.5 | `src/engine_conversion.py` (633) | 11 files, 2 in `src/` + `_legacy_pe.` sites | **opus · high** | 2–4 |
| M8.6 | Façade pass: `planning_engines.py` down to `project()`, `run_scenario()`, and a curated re-export block. Delete the remaining `BEGIN/END` markers. | **opus · high** | 1–2 |
| | **Subtotal** | | **9–17** |

**The hazard M8 must not miss.** Consumers reach into these names two ways:
`from ..planning_engines import withdraw_pretax_elective`, *and*
`from .. import planning_engines as _legacy_pe` followed by
`_legacy_pe.withdraw_pretax_elective(...)`. The second form is invisible to an
`ImportFrom` scan — measured today: 18 attribute call sites across 9
`projection_stages` modules, concentrated in `spending_and_rmd.py` (4),
`withdrawal_cascade_ira_true_up.py` (3) and `roth_conversion_and_agi_tax.py` (3).
**Any M8 name-audit must cover both forms**, and M0.3's import-direction test
should be extended to assert it before M8.1 starts.

This is where the file header's "do not re-split" warning still bites hardest,
and M8 is the phase most likely to overrun its estimate. Sole occupancy of the
merge gate applies here exactly as it does in M3.

**Exit criteria:** `planning_engines.py` at ~200 lines; golden-master pins
(deterministic *and* MC) unmoved throughout.

---

### Phase M9 — Final close-out

| ID | Item | Model · effort | Turns |
|---|---|---|---:|
| M9.1 | Relax the MC scalar pins (M5.1, if deferred) now that engine code has stopped moving. | sonnet · low | 1 |
| M9.2 | Final manifest/design-doc update; record the end state and every place the plan was wrong. | sonnet · medium | 1 |
| | **Subtotal** | | **2** |

---

## 4. Sequencing, worktrees, and cost

```
M0  (both lanes, instrumentation only)
 │
 ├─> M1.1 M1.2 M1.3        wt/js-modularize   ← dashboard.js owner
 ├─> M1.4                  wt/engine-split    ← planning_engines.py owner
 │
 └─> M2.1 ──> M3.1 … M3.5  wt/engine-split, SOLE OCCUPANCY ①
                  │
                  └─> M4.1 … M4.6   wt/js-modularize
                         │
                         ├─> M5 (mid-point)
                         │
                         ├─> M6.1 … M6.5   wt/js-modularize   ─┐
                         │                                     ├─ may overlap
                         └─> M7.1 ──> M8.1 … M8.6              │
                                      wt/engine-split,         ─┘
                                      SOLE OCCUPANCY ②
                                             │
                                             └─> M9
```

**Two worktrees, disjoint blast radius** — `frontend/js/` + `tools/js_codemod/`
in one, `src/` + `tests/fixtures/` in the other. They may develop concurrently
throughout. They may **not both merge** during the two sole-occupancy windows,
① M2–M3 and ② M8: those are the stretches where a red suite would be ambiguous,
and they cover the most numerically sensitive code in the plan.

M1 is the deliberate exception — M1.1–M1.3 and M1.4 can land in the same window
because both are protected by tests that already exist and pass today.

**M6 and M7/M8 may overlap**, and this is the main wall-clock lever the committed
scope creates: M6 is frontend-only and lands against a suite M8 does not touch,
so the dashboard lane can run M6 while the engine lane prepares M7. **M6 must
still finish merging before M8.1 opens window ②** — overlap means concurrent
development, not concurrent merging.

**Inherited trap** (2026-08-12 §5): a worktree running the app writes
`local_state/retirement_system_v10.db` in the *main* repo. Do not run the app
from the dashboard lane while an engine-lane test run is in flight.

### Model and reasoning-effort policy

Model and effort are separate dials, set separately, per the house convention.

| | Use | Items |
|---|---|---|
| **opus · max** | Deciding what "correct" even means, on code with no existing assertion. | M2.1 |
| **opus · high** | The failure mode is silent, or the answer is not yet known. | M0.1, M0.4, M1.3, M1.4, M3.3, M3.4, M4.5, M4.6, M6.1, M8.4, M8.5, M8.6 |
| **opus · medium** | Path known, blast radius wide — judgement about consequences, not discovery. | M0.3, M1.2, M3.1, M3.5, M4.2, M4.3, M4.4, M6.3, M6.4, M7.1, M8.2, M8.3 |
| **sonnet · medium** | Specified work with local judgement calls, behind a tool that verifies. | M0.5, M0.6, M1.1, M3.2, M4.1, M5.2, M6.2, M6.5, M8.1, M9.2 |
| **sonnet · low** | The edit is known and repeated; reasoning adds tokens, not correctness. | M0.2, M5.1, M9.1 |
| **haiku** | — | **Nothing.** No item here has a verifiable-output-plus-trivial-judgement shape; the three that look like it (M0.2, M5.1, M9.1) sit next to conventions that fail silently if misread. |

Two assignments in the newly committed phases are worth naming, because they are
the ones a reader would expect to go the other way:

* **M8.1 (`engine_growth.py`) is sonnet · medium despite being an engine move**,
  because the measurement says it has **one** importer and none in `src/`. Tier
  follows blast radius, not subject matter.
* **M8.4/M8.5 are opus · high despite being "just" import updates**, because the
  `_legacy_pe.` attribute form is invisible to the obvious static check. A missed
  call site there is an `AttributeError` at runtime in tax-sensitive code, not a
  failed import at collection time.

Three rules that matter more than the table:

1. **Silent failure sets the tier, not diff size.** M1.1 moves 2,462 lines at
   sonnet · medium; M0.2 adds one test at sonnet · low; M2.1 writes a fixture at
   opus · max. Line count is not the variable — whether being wrong is *visible*
   is.
2. **Effort down before model down.** A sonnet · low pass over a written task
   list is cheaper and more predictable than opus · low.
3. **One item per session, hard stop at the boundary.** R3 from the 2026-08-12
   plan still dominates both dials, and both design docs record the same finding
   independently: the per-pass cost was never the extraction, it was the tests
   that read the subject file directly.

### Cost

| Phase | Turns | Cumulative | `dashboard.js` | `planning_engines.py` |
|---|---:|---:|---:|---:|
| M0 Instrument | 7–11 | 7–11 | 7,512 | 6,418 |
| M1 Harvest | 8–13 | 15–24 | ~4,170 | ~5,660 |
| M2 Safety net | 3–4 | 18–28 | ~4,170 | ~5,660 |
| M3 Monte Carlo | 10–17 | 28–45 | ~4,170 | ~2,440 |
| M4 Domain modules | 12–18 | 40–63 | ~2,340 | ~2,440 |
| M5 Mid-point | 2 | 42–65 | ~2,340 | ~2,440 |
| M6 Dashboard Tier C | 6–10 | 48–75 | **~1,500** | ~2,440 |
| M7 `core` cleanup | 2–3 | 50–78 | ~1,500 | ~2,440 |
| M8 Engine Tier 3 | 9–17 | 59–95 | ~1,500 | **~200** |
| M9 Final close-out | 2 | **61–97** | ~1,500 | ~200 |

End state: `dashboard.js` **7,512 → ~1,500** (−80%), `planning_engines.py`
**6,418 → ~200** (−97%, a `project()`/`run_scenario()` façade), plus two removed
correctness traps, two closed holes in the gating baseline, and the 23 laundered
`core` names pointing at their real home.

**The full scope is now committed** (§5 decision 4), so the stopping points below
are contingency, not a menu. Each is a real resting point rather than an
abandoned migration, which matters because M8 is the phase most likely to
overrun:

* **After M2** (18–28): both correctness fixes landed, MC gated for the first
  time, `dashboard.js` down 44%. Nothing risky attempted.
* **After M5** (42–65): both files past halfway; the original two design docs'
  recommended scope is complete.
* **After M6** (48–75): the entire dashboard lane is finished. If M8 stalls, this
  is the line to hold — the frontend work has no dependency on the engine lane.

---

## 5. Open decisions

1. **Does M4 start before M3 finishes?** §4 says no, on gate-ambiguity grounds.
   The counter-argument is wall-clock: the lanes are genuinely independent and
   M3 is the longest phase. Anyone taking the parallel option should require
   per-lane suite runs before merge and accept that a shared-suite failure costs
   a bisect.
2. **Is M4.1–M4.5 batched or serial?** Serial by default; see the batching note.
   Decide after M4.1, on evidence, not now.
3. ~~**Does M0.1's explicit re-export list ship as permanent or as a deprecation
   shim?**~~ **Resolved by decision 4.** It is a shim with a scheduled end:
   M0.1 writes it, M7.1 shrinks it to what is genuinely still re-exported, M8.6
   finalises it as the façade. Engine design §9 question 2's
   "permanent-for-now" recommendation assumed consumer cleanup might never
   happen; it is now M7.
4. ~~**Who owns the M5.3 gate?**~~ **Answered 2026-09-09 — scope decision: all
   three tails are IN SCOPE**, scheduled as M6 (dashboard Tier C), M7 (`core`
   consumer cleanup) and M8 (engine Tier 3). The M5.3 gate is removed; there is
   nothing left to drift into. Committed scope rose from 43–66 to **61–97
   turns**.

   Recorded honestly, because both design docs argued the other way and a later
   reader deserves to know that: the dashboard doc called Tier C "explicitly
   optional" and the engine doc marked Tier 3 "optional, later" and warned it is
   where the "do not re-split" header bites hardest. Two things reduce that
   tension rather than dismiss it. **Tier C as designed is append-to-existing,
   not create-new** — it returns orphans to domain modules that already exist,
   which is not the invent-themed-modules idea the 2026-08-12 decision rejected.
   And **M7 now precedes M8**, so Tier 3's import audit runs against a cleaned
   surface. What remains genuinely riskier than the rest of the plan is M8.4/M8.5
   (§M8's `_legacy_pe.` hazard), which is why they carry the plan's widest turn
   ranges and why "after M6" is named as the line to hold if M8 stalls.
5. **Does M6 overlap M7, or wait?** §4 permits concurrent development with
   serialized merges. Overlapping is the main wall-clock lever the committed
   scope creates; taking it requires discipline about the merge order, not just
   about the branches.

---

## 6. Execution log

*(empty — append one line per landed item: ID, commit, turns actually taken,
model · effort actually used, and anything that contradicted this plan.)*
