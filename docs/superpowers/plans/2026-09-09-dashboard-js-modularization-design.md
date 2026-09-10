# dashboard.js modularization — design

**Status:** design only. Nothing in this document has been implemented.
**Date:** 2026-09-09
**Subject:** `frontend/js/dashboard.js`, 7,512 lines
**Predecessors:** `docs/superpowers/specs/2026-08-10-dashboard-js-split-codemod-design.md`
(the codemod design), `frontend/js/modules/phase3_module_manifest.js` v1–v13
(the running history of every prior pass).

---

## 1. Where the file actually stands

The prior effort (manifest v4–v12) took dashboard.js from ~19,400 to 7,481 lines
via one shared-core extraction and twelve domain-cluster extractions, then
**deliberately stopped** — the 2026-08-12 scope decision (F3.5) judged the
remaining tail to be "111 single-function components with no cohesive domain
between them," and correctly refused to build themed modules out of unrelated
singletons.

That judgement was about **functions**. It is still right about functions. But
it measured the wrong thing, because the file that remains is no longer mostly
functions.

Measured today (`@babel/parser` over the current file, top-level statements only):

| Category | Statements | Lines | Share |
|---|---:|---:|---:|
| Static data literals (`const X = {…}` / `[…]`) | 29 | **3,515** | **47%** |
| Function declarations | 194 | 2,945 | 39% |
| Everything else (state `let`s, `renderMain`, `showStepHelp`, boot chain, generated bridge) | 203 | 667 | 9% |
| Blank / comment lines between top-level statements | — | 385 | 5% |

Nearly half the "monolith" is content, not code. And that content is
overwhelmingly one table:

```
FIELD_GUIDANCE_OVERRIDES   2,462 lines   (L4119–6580)   33% of the whole file
STEPS                        410 lines   (L14–423)
STEP_HELP                    282 lines   (L474–755)
FIELD_TOOLTIPS                87 lines   (L2215–2301)
SYSTEM_CONFIG_FIELD_HELP      44 lines   (L978–1021)
PLAN_DATA_FILES               34 lines
BUILD_IMPACT_SOURCE_STEP_IDS  31 lines
SPENDING_COMPLETION           27 lines
… 21 more, all ≤ 18 lines            (165 lines combined)
```

**The reframe this document proposes:** the next pass is not a thirteenth
function-cluster extraction. It is a *content* extraction, and it is worth more
than every remaining function extraction combined. `FIELD_GUIDANCE_OVERRIDES`
alone is larger than the four largest clusters ever extracted (assets 24 fns,
spending 39, housing 40, build-history 24) put together.

The function tail is still worth ~1,800 lines across six genuine domains
(§4) — the F3.5 "no cohesive domain" verdict counted *connected components* of
the call graph, which fragments a domain whenever its members talk through
shared state instead of calling each other. Grouping the same 194 functions by
what they *operate on* rather than who calls whom recovers six clusters covering
147 of them. That is a real answer to F3.5's objection, not a re-litigation of it.

---

## 2. What blocks this today (the actual design problem)

`tools/js_codemod/extract_module.mjs` **will refuse every single Tier-A move**,
by design. Its variable safety rule
(`tools/js_codemod/extract_module.mjs:167-194`):

> a moved variable becomes module-private, and dashboard.js's generated bridge
> cannot expose a binding that no longer lives in dashboard.js. So a variable
> may only move if nothing else anywhere still reads it.

That rule has earned its keep three times (it held back `SCENARIO_SET_STORAGE_KEY`
in v7, `BUILD_HISTORY_LS_KEY` in v8, `showStepHelp` in v9). It is correct for
**mutable state**. It is *over-broad* for **immutable content tables**, and it is
the only thing standing between the repo and its largest available win:

| Table | Readers in dashboard.js after removal | Readers elsewhere |
|---|---|---|
| `FIELD_GUIDANCE_OVERRIDES` | **zero** | `dashboard_decomp_row_model.js:4037` |
| `STEPS` | 4 | `row_model.js:39,726`, `checklist_closeout.js:940` |
| `STEP_HELP` | 1 (`showStepHelp`) | `checklist_closeout.js:6` |
| `SYSTEM_CONFIG_FIELD_HELP` | 0 | `checklist_closeout.js:6` |
| `FIELD_TOOLTIPS` | 2 | none |
| `TERM_NOTES` | 1 | none |

`FIELD_GUIDANCE_OVERRIDES` is the extreme case: **2,462 lines with no reader at
all inside the file that declares it.** It is already, semantically, somebody
else's data. The safety rule blocks it purely on the mechanical grounds that
row_model.js reads it — which is exactly the case the fix below handles.

### 2.1 The fix: content-module mode

The rule's premise ("dashboard.js's generated bridge cannot expose it") is true
but the conclusion doesn't follow. **The new module can install its own bridge
entry**, exactly as every leaf module already does. Then:

* Cross-file readers (`row_model.js`, `checklist_closeout.js`) keep working
  unchanged — they already read these names as bare globals resolved through
  `window`, not as imports.
* dashboard.js's own remaining reads keep working unchanged: a bare read of an
  unresolvable identifier inside an ES module **falls through the scope chain to
  the global object**. This is not a new trick — it is precisely the mechanism
  by which dashboard.js already calls `rowsForStep()`, `navigationContext()` and
  ~170 other row_model.js functions, and the mechanism `load_dashboard.mjs`
  documents at length for `STEP_HELP`'s own evaluation.
* `census.mjs` / `convert_dashboard.mjs` need no change: they read dashboard.js's
  AST, so a moved declaration simply stops producing a bridge entry.

Proposed CLI surface, additive and narrow:

```bash
node tools/js_codemod/extract_module.mjs \
  --names FIELD_GUIDANCE_OVERRIDES \
  --out frontend/js/dashboard_decomp_field_guidance_content.js \
  --header-file tools/js_codemod/headers/field_guidance_content.txt \
  --content-tables FIELD_GUIDANCE_OVERRIDES \
  --check
```

`--content-tables` relaxes the variable rule for the named bindings **only if
all four of these hold**, each checked by the tool and each a hard `die()`:

1. Declared `const` (never `let`/`var`).
2. Initialiser is an `ObjectExpression`, `ArrayExpression`, `NewExpression`
   (for the `new Set([...])` tables), or a `CallExpression` whose callee is also
   being moved (this is what lets `STEP_HELP = { start: pageHelp(…) }` move
   together with `pageHelp`).
3. **No assignment to the name anywhere in the repo**, and no
   `Object.assign(NAME, …)` / `NAME[…] = …` / `delete NAME[…]` mutation site.
   This is the real safety condition, and it is stricter than "is it a `const`" —
   a `const` object is still mutable. Enforced by AST, not regex.
4. The generated module emits an explicit bridge entry for the name, and
   `finish_extraction.mjs` verifies it landed (it already performs the
   symmetrical check in the other direction).

**Condition 3 has one known live exception.** `loadCanonicalGlossary()`
(`dashboard.js:7192`) does `Object.assign(ACRONYM_DEFINITIONS, r.terms)` at
runtime. `ACRONYM_DEFINITIONS` lives in row_model.js, not here, so no Tier-A
candidate is affected — but the check must exist before someone extracts a table
that *is*, and it must be written against the whole repo including the
`dashboard_decomp_*.js` modules, not just dashboard.js.

---

## 3. Tier A — content modules

Four modules. Ordered by value-per-risk, not by size.

### A1. `dashboard_decomp_field_guidance_content.js` — ~2,470 lines

Moves `FIELD_GUIDANCE_OVERRIDES`. Zero readers in dashboard.js, one reader in
row_model.js, pure literal, no mutation sites. **This is the single highest-value,
lowest-risk change available in the frontend and should be done first and alone.**

It is also the cleanest possible proof of the `--content-tables` mechanism: if
the mechanism is wrong, this pass fails loudly and in isolation, with nothing
else in the diff to confuse the diagnosis.

Line effect: 7,512 → ~5,045.

### A2. `dashboard_decomp_step_catalog.js` — ~430 lines

Moves `STEPS` + `SPENDING_WORKFLOW_STEPS` + `SPENDING_WORKFLOW_INDEX` +
`SUGGESTED_NEXT` + `STRATEGY_TABS` + `REPORTS_TABS`.

`STEPS` is the wizard's step catalogue — the definition of the application's
information architecture. Four cross-file readers, all bare-global. Grouping the
five small navigation-adjacent tables with it keeps "which steps exist, in what
order, with what tabs and what suggested next step" in one file.

**Do not move `renderMain` with it.** `renderMain` is a `let` reassigned as a
monkey-patch decorator chain by other leaf modules and needs
`convert_dashboard.mjs`'s get/set accessor treatment, which only applies inside
dashboard.js. The tool already refuses it by name.

Line effect: ~5,045 → ~4,610.

### A3. `dashboard_decomp_help_content.js` — ~450 lines

Moves `STEP_HELP`, `SYSTEM_CONFIG_FIELD_HELP`, `TERM_NOTES`, `FIELD_TOOLTIPS`,
plus the four functions that exist only to build them: `pageHelp`,
`addParentheticals`, `helpList`, `stepHelpLinkHtml`.

**This one has a real evaluation-order constraint and is the reason A3 is not
merged into A2.** `STEP_HELP` and `SYSTEM_CONFIG_FIELD_HELP` are not inert
literals — they invoke `pageHelp(...)` at module-evaluation time, and `pageHelp`
in turn calls `acronymDefinitionsHtml()` and `esc()`, which live in row_model.js
and `dashboard_shared_helpers.js`. So this module's `<script>` tag must sit
**after** row_model.js and shared_helpers.js and **before** dashboard.js. That is
already true of every position in the extracted-module block in `index.html`
(lines 106–119), so the constraint is satisfiable — but it must be stated in the
module header and asserted by a test, because it is invisible from the code and
a future reorder would break it at load time with a bare `ReferenceError`.

`showStepHelp` stays behind (reassignable monkey-patch chain, same reason as
`renderMain`).

Line effect: ~4,610 → ~4,170.

### A4. Residual tables — fold into their owning domain modules, don't make a module

The remaining ~165 lines (`PLAN_DATA_FILES`, `BUILD_IMPACT_SOURCE_STEP_IDS`,
`SPENDING_COMPLETION`, `GROUP_KEY_LABELS`, the five `ROTH_*_LABELS` arrays,
`LIABILITY_HEADER`, `PERSON_TABLE_LABELS`, `LARGE_DISC_*`, `IRMAA_OFF_MODES`,
`DEFAULT_TRAVEL_TYPES`, `PROTECTED_CLIENT_DATA_KEYS`, `RECOMMENDATION_*`) are
each small and each read by exactly one domain. They should ride along with
whichever Tier-B module claims their consumer, not become a junk-drawer
"constants" file. A `constants.js` here would be the filing-system-not-a-boundary
mistake F3.5 was right to refuse.

---

## 4. Tier B — six domain modules from the function tail

`find_clusters.mjs` reports 140 connected components over the remaining 194
functions, 110 of them singletons — which is why F3.5 called this a tail with no
domains. That measure fragments a domain the moment two of its members
communicate through module-level state rather than by calling each other, which
in this codebase is the *normal* case (`ytdData`, `detailedResultsData`,
`allocationPreview`, … are all shared `let`s).

Re-grouped by **subject** (what state and what API surface each function
touches), the same 194 functions yield:

| Module | Fns | Lines | Subject |
|---|---:|---:|---|
| `dashboard_decomp_ytd_accounts.js` | 20 | 273 | YTD account setup: role/mapping dropdowns, money-cell edit/focus/blur, add/delete/save/recover, stale-growth rollover banner |
| `dashboard_decomp_planning_cases.js` | 28 | 217 | Planning-case store (`retirement.planning_case_v1`), override collection per source, promote/adopt/archive, workbench matrix + cards |
| `dashboard_decomp_detailed_workbook.js` | 19 | 316 | Detailed-results sheet loading, the progress-tick state machine, column-group expand/collapse, results nav drawer |
| `dashboard_decomp_field_guidance.js` | 25 | 650 | The *functions* behind field help: `fieldDefaultMeaning`, `fieldConnection`, `fieldLikelyImpact`, `fieldAllowedValues`, `choiceOptions`/`choiceLabel`/`choiceHelpText`, `fieldTooltip*`, `dependencyRank` |
| `dashboard_decomp_build_snapshot.js` | 14 | 271 | Build snapshot/compare: `takeBuildSnapshot`, `rememberBuildCompare`, session-change tracking (`changeKey`, `changeImpactScope`, `noteSessionFieldChange`), desktop build progress |
| `dashboard_decomp_value_format.js` | 11 | 102 | Display/parse round-trip for a row value: decimals, percent, money-negative class, `normalizeValueForSave`, `saveValueForRow`, `parseCsvLine` |
| **Total** | **117** | **1,829** | |

Two of these are corroborated by `find_clusters.mjs` as genuine multi-member
components even under the stricter call-graph measure — the 7-member
`{choiceHelpText, choiceLabel, choiceOptions, fieldAllowedValues,
filterChoiceOptionsForRow, helpList, yesNoOptionHelp}` component (→ field
guidance) and the 6-member `{chooseDefaultDetailedSheet, detailProgressState,
loadDetailedResults, renderDetailedResultsProgressTick,
startDetailedResultsProgress, stopDetailedResultsProgress}` component (→ detailed
workbook). The remaining four are subject-coherent but call-graph-sparse; that is
the argument this tier has to win on review, and it should be won module by
module, not in one commit.

**Pairing note:** `dashboard_decomp_field_guidance.js` (B) and
`dashboard_decomp_field_guidance_content.js` (A1) are deliberately two files —
data and behaviour. A1 is 2,470 lines of pure content that changes when a
planner rewords a field explanation; B is 650 lines of logic that changes when
the help *system* changes. Merging them would put a 3,100-line file back on the
board and reintroduce the exact review problem this project exists to remove.

**Ordering caution:** every extraction changes the graph for the next one. Re-run
`find_clusters.mjs` and `cluster_deps.mjs` before each pass rather than trusting
the numbers in this table, which are a snapshot of 2026-09-09.

---

## 5. Tier C — the 47 orphan step-renderers

47 functions / 808 lines remain unbucketed. Almost all are single step-page
renderers whose domain **already has a module**:

* `renderWithdrawalStrategy` (80), `renderWithdrawalOrderTable`,
  `withdrawalOtherRows`, `boolishValue` → the Roth/withdrawal surface
* `allocationPreview*` (4 fns, 45), `validateAllocationTargetsOrMessage`
  → `dashboard_decomp_allocation_optimizer.js`
* `catEffectiveBudget`, `groupModelData`, `restoreGroupBudgetModes`,
  `recoverPriorSpendingBudget`, `domainBudgetNote`, `hideUnusedTemplateCategories`,
  `renderSpendingDashboardOrLoad`, `renderSpendingWorkflowBanner`,
  `spendingFlowFooterHtml` → `dashboard_decomp_spending_taxonomy.js`
* `baseHomeSaleYearRow`, `stressHomeSaleYearRow`, `scenarioRowKeyFromParts`
  → `dashboard_decomp_housing_scenarios.js`
* `renderHouseholdPeople`, `personCellInput`, `personNickPlaceholder`,
  `renderStateResidency` → a small new household/residency module (60 lines; the
  only genuinely new home Tier C needs)

**Tier C is append-to-existing, not create-new.** That is what makes it different
from the F3.5 proposal that was correctly rejected: F3.5 wanted to invent themed
modules to house these; this wants to return each one to the domain module its
subject already lives in. `extract_module.mjs` currently only creates new files —
appending to an existing module is a tool change (`--append-to`) of similar size
to `--content-tables`, and should be scoped as its own decision after Tier B
lands, not committed to here.

Tier C is **explicitly optional**. Tiers A and B alone take the file from 7,512
to roughly 2,300 lines. If the project's appetite runs out after Tier B, that is
a defensible resting point in a way that 7,512 currently is not.

---

## 6. Load-order contract

Every new module in this design is loaded **before** dashboard.js, in the
existing extracted-module block (`frontend/index.html:106–119`), for the reason
already documented in `dashboard_decomp_build_history.js`'s header and enforced
by `test_dashboard_startup_race_and_script_order.py`: dashboard.js ends its
module body with `queueMicrotask()`, and a microtask checkpoint runs after that
script's evaluation — so a module loaded *after* dashboard.js is not guaranteed
to have installed its window bridge before dashboard.js's boot work runs.

Within that block, the required relative order is:

```
dashboard_shared_helpers.js            (esc, fmtMoney, …)
dashboard_decomp_row_model.js          (acronymDefinitionsHtml, ACRONYM_DEFINITIONS, …)
  ↓ must precede
dashboard_decomp_help_content.js       (A3: STEP_HELP evaluates pageHelp → acronymDefinitionsHtml)
  ↓ must precede
dashboard.js
```

A1, A2, and every Tier-B module have **no** evaluation-time dependency (pure
literals; function declarations plus one `Object.assign`) and may sit anywhere in
the block. Only A3 constrains order, and that constraint must be (a) stated in
A3's header file and (b) asserted by a new test — a positional assertion over
`index.html`'s script tags, in the style of
`test_dynamic_import_specifiers_match_script_tags`.

**Naming is load-bearing.** Every new file must match `dashboard_decomp_*.js`.
`tests/_decomp_dashboard.py::dashboard_js_text()` globs exactly that pattern to
assemble "the full dashboard source," and 277 test files depend on it. A file
named `field_guidance_content.js` would silently drop 2,462 lines of content out
of every content-assertion test in the suite — which would *pass*, not fail. This
is the highest-consequence, lowest-visibility hazard in the whole plan.

---

## 7. Verification per pass

The prior passes established that the extraction itself is cheap and the *tests
that read dashboard.js directly* are what cost sessions (v9 broke four tests
moving 50 functions; v10 broke zero moving 31, after the sweep onto
`tests/_decomp_dashboard.py`). Every pass here runs the same gate:

1. `extract_module.mjs --check` — round-trip proof: reads the generated module
   back off disk and reconstructs the original dashboard.js from it. Deriving the
   comparison text from the *output* is what makes this a real check.
2. `node --check` on both files (the tool already does this).
3. `finish_extraction.mjs` — index.html wiring, census, bridge regeneration,
   clusters report, manifest, ratchet, **and** the bridge-completeness check that
   nothing else performs: every dashboard.js binding the new module reaches back
   for is on the bridge, with a setter where the module assigns to it.
4. `pytest tests/ -k "frontend or dashboard or decomp or ratchet"`.
5. `node --test tests/frontend/` — 26 `.mjs` suites, including
   `load_dashboard.mjs`, which concatenates the real files in real `index.html`
   order and is the only check that would catch an A3 load-order mistake.
6. Playwright suite (`playwright.config.js`) — the only check covering the
   YTD/plan-folder file-system and permission flows Tier B's YTD module touches.

**Three additions this design requires:**

* **A `--content-tables` mutation-check test.** Feed the tool a fixture table
  that is mutated via `Object.assign` elsewhere and assert it refuses. Without
  this, condition 3 in §2.1 is a comment, not a rule.
* **An A3 script-order test.** Assert `dashboard_decomp_help_content.js`'s tag
  appears after row_model.js's and shared_helpers.js's in `index.html`.
* **A `dashboard_decomp_*.js` naming test.** Assert every `<script>` tag in the
  extracted-module block matches the glob `_decomp_dashboard.py` uses — so the
  §6 hazard fails loudly the first time someone names a file wrong.

---

## 8. Sequencing and line budget

| Pass | Content | dashboard.js after | Ratchet |
|---|---|---:|---:|
| 0 | Add `--content-tables` to `extract_module.mjs` + its refusal test. No extraction. | 7,512 | 7,504 (unchanged) |
| A1 | `FIELD_GUIDANCE_OVERRIDES` | ~5,045 | lower to actual |
| A2 | Step catalogue (6 tables) | ~4,610 | lower |
| A3 | Help content (4 tables + 4 builders) + order test | ~4,170 | lower |
| B1–B6 | Six domain modules, one commit each, re-running `find_clusters.mjs` between | ~2,340 | lower each time |
| C (optional) | `--append-to`, then return 47 orphans to their existing domains | ~1,500 | lower |

Floor estimate for the final shell: **~1,200–1,500 lines** — the boot chain, the
`renderMain` dispatch, `showStepHelp`, ~90 shared state `let`s, and the ~200-line
generated bridge. Those cannot leave: the bridge references module-private
bindings by name and must live in the file that declares them
(`test_frontend_size_ratchet.py`'s 2026-08-06 entry records this as the ratchet's
one deliberate exception).

**Ratchet discipline:** `DASHBOARD_JS_MAX_LINES` (currently 7,504,
`tests/test_frontend_size_ratchet.py:149`) moves down in the same commit as each
extraction. `test_ratchet_is_not_slack` enforces ≤ 500 lines of headroom, so this
is not optional.

**`TOTAL_JS_MAX_LINES` (32,000) is the tighter constraint and needs attention
before A1.** `frontend/js` totals 30,363 today — 1,637 lines of headroom. Each
new module costs a header comment (the existing headers run 25–60 lines) plus its
own bridge block. Ten new modules at ~50 lines of overhead each is ~500 lines,
which fits — but only just, and only if extraction genuinely *moves* rather than
duplicates. Confirm the arithmetic against the real A1 output before assuming the
rest of the plan clears it; if it doesn't, that ceiling needs a documented,
justified raise rather than a surprise failure mid-sequence.

---

## 9. Out of scope

* **Converting the window bridge to real `import`/`export`.** The no-`export`
  convention is load-bearing: several tests `eval()` dashboard.js (whole or by
  literal-text slice) as a plain script, where any `export` keyword is a
  `SyntaxError`. Changing that is a separate project with its own test-harness
  migration, and merging it into this one would make every failure ambiguous.
* **Reducing the ~90 shared `let`s to a state object.** This is the deeper
  coupling problem and the reason the call graph fragments the way §4 describes.
  It is a genuinely larger and riskier project than this one, and this design
  neither depends on it nor blocks it.
* **`admin.js` (2,143 lines).** A separate classic app, still out of scope, as
  the manifest records.
* **Dead-code removal.** `tools/js_codemod/dead_function_candidates.json` exists
  and may overlap with functions named here. Sweep it as its own pass — deleting
  and moving in the same diff makes the round-trip check meaningless.

---

## 10. Open questions for review

1. **Is `--content-tables` the right shape, or should immutability be inferred?**
   The tool could detect "const + literal + no mutation sites anywhere" and allow
   the move without an explicit flag. That is less ceremony but removes the
   author's declaration of intent, and the existing tool's whole character is
   refusing-by-default and making the operator say what they mean. This design
   recommends the explicit flag; the alternative is reasonable.
2. **Should A1 ship before Pass 0's refusal test?** A1 is provably safe by
   inspection (zero mutation sites, zero in-file readers) and is 33% of the file.
   The argument for shipping it first is that the test guards *future* moves, not
   this one. The argument against is that a tool capability without its guard is
   how the next person gets hurt. This design puts the test first.
3. **Does Tier B need review sign-off per module, or once for the tier?** The
   six modules differ in how well the call graph corroborates them (§4). Per
   module is safer and slower.
4. **Is Tier C worth the `--append-to` tool work?** It buys ~800 lines for a new
   tool capability plus 47 individually-reviewed moves. Reasonable to decline.

---

## 11. What this document does not claim

It does not claim the F3.5 decision was wrong. It claims F3.5 measured functions
and stopped when the function-clustering signal ran out — which was correct — and
that the 3,515 lines of static content sitting in the same file were never part
of that analysis. That is the finding. Everything in Tier A follows from it; Tier
B and C are a smaller, more arguable second act.
