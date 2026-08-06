# dashboard.js Domain-Module Split — Scoping Investigation

**Status:** Scoping only. Not a ready-to-execute plan. No source files changed by this
investigation.

**Predecessor:** `2026-08-06-dashboard-js-ast-module-conversion.md` (done, merged) converted
`dashboard.js` from a classic script to a real `type="module"` script via a generated
`window` bridge. That closed the "implicit global namespace" problem. It explicitly did
**not** attempt to split the file — `phase3_module_manifest.js`'s `v3` entry names that as
"a SEPARATE, NOT-yet-scheduled future pass: that needs its own dependency-graph analysis."
This document is that analysis.

## The question this answers

Can `dashboard.js`'s ~760 top-level functions be mechanically grouped into cohesive,
independent domain modules (`dashboard_spending.js`, `dashboard_assets.js`, ...), the same
way `dashboard_decomp_holdings.js` was pulled out by hand during Wave 6.4?

**Short answer: not cleanly, not by hand, and not without a real shared-core module first.**
The functions are far more interconnected than the UI's own domain grouping suggests.

## Method

A one-off script (`tools/js_codemod/census.mjs`'s AST parsing, reused — not committed,
this was throwaway analysis) built an internal call graph: for each of the 760 top-level
functions, which *other* top-level functions does its body reference. This is a
conservative superset of "calls" (includes passing a function as a callback, referencing
it in a template literal, etc.) — the right direction for "must these two functions ship
together, or does splitting them require an explicit cross-module reference."

Then: connected-components over that graph (undirected — a reference in either direction
binds two functions into the same component), and fan-in ranking (how many *other*
top-level functions reference each function) to find the "glue."

## Finding 1: almost everything is one component

760 functions form 23 connected components. **One component has 732 functions — 96.3% of
the file.** This is the opposite of "cleanly separable by domain": nearly every render
function, save handler, and loader is transitively reachable from nearly every other one.

## Finding 2: the glue is a shared field-rendering DSL, not formatting utilities

Top fan-in functions (referenced by the most other top-level functions):

| Fan-in | Function | What it is |
|---|---|---|
| 155 | `section` | Row-model primitive — which section a row belongs to |
| 112 | `norm` | String normalization used everywhere rows are matched/compared |
| 104 | `renderMain` | Top-level dispatch (already has a reassignment bridge — see below) |
| 77 | `showMessage` | App-shell status/toast |
| 74 | `api` | Fetch wrapper every loader/saver uses |
| 62 | `valOf` | Row-model primitive — read a row's current value |
| 35 | `isEditable` | Row-model primitive |
| 28 | `showInAppConfirm` | App-shell modal |
| 25 | `fieldHtml` | Row-model primitive — renders one field's HTML |
| 23 | `editValue` | Row-model primitive |
| 22 | `rowsForStep` | Row-model primitive — which rows belong to a given step |
| 21 | `humanLabel` | Row-model primitive — label formatting |
| 20 | `planningWorkbenchContext` | Cross-domain KPI aggregator (reads spending, holdings, allocation, MC results) |
| 18 | `setStep` / `loadAll` | App-shell navigation / bootstrap |
| 15 | `renderFields` / `saveAll` | Row-model / app-shell |

The codebase's actual architecture is: **one shared "row" data model** (`rows` array +
`section`/`norm`/`valOf`/`isEditable`/`fieldHtml`/`rowsForStep`/`editValue`/`humanLabel`/
`displayValueForInput`, ~15-20 functions) that *every* domain's render function is built on
top of, plus **one shared app shell** (`renderMain`/`api`/`showMessage`/`setStep`/`loadAll`/
`saveAll`/`setAppControls`/`unsavedChangeCount`, ~15-20 functions). These aren't
"utilities" in the CSS-formatter sense — they're the load-bearing data layer, so almost
every domain-specific function touches at least one of them, which is what glues the
732-function component together.

## Finding 3: real domain clusters DO exist underneath, once enough hub functions are excluded

Progressively excluding functions by fan-in threshold (>= N other top-level functions
reference it) and re-running connected components on what's left:

| Cutoff (fan-in >=) | Functions excluded as "hub" | Functions remaining | Largest remaining component |
|---|---|---|---|
| 6 | 58 (7.6%) | 702 | 577 |
| 5 | 71 (9.3%) | 689 | 535 |
| 4 | 114 (15.0%) | 646 | 315 |
| **3** | **174 (22.9%)** | **586** | **80** |
| 2 | 304 (40.0%) | 456 | 22 |

At cutoff >= 3 (174 functions pulled into a shared layer — nearly a quarter of the file),
the remaining 586 functions break into ~188 components, and the large ones map cleanly
onto real, recognizable domains:

| Size | Domain (inferred from function names) | Maps to UI group |
|---|---|---|
| 80 | YTD transactions / accounts / CSV import-export | Spending (Actual Spending) |
| 56 | Asset-class allocation / optimizer | Strategy |
| 39 | Housing scenarios / home-sale estimation | Spending (Housing) |
| 39 | Spending taxonomy / category-group mapping | Spending (Categories) |
| 33 | Plan lifecycle: save/load/checklist/CSV backup | Plan Status / Settings |
| 25 | Build history / build-impact narrative | Reports & Review |
| 24 | Assets: liabilities, note receivables, 529s, other assets | Assets & Protection |
| 14 | Page-local recommendations | (cross-cutting, appears on many pages) |
| 11 | Social Security / retirement income | People and Income |
| 10 | Large discretionary / travel / DAF | Spending |
| 8 | Monte Carlo / LTC / survivor / divorce stress options | Stress Tests |
| 8 | Life insurance / annuity illustration matrix | Assets & Protection |
| 7 | Choice-field help text | (row-model adjacent) |
| 6 | Value normalization for save | (row-model adjacent) |
| 6 | Detailed-results progress polling | Reports & Review |

This is the real, validated shape of a future split: it is NOT one module per UI nav group
(some UI groups split into 2-3 clusters; a few small clusters are cross-cutting and don't
belong to any single UI group). But it is recognizable and roughly proportional to what a
person familiar with the app would expect.

## What this means for scope and risk

**This is a materially bigger and riskier undertaking than the module-conversion pass.**
That pass moved zero logic — it added an `export`+`window` bridge around code that stayed
exactly where it was. A domain split requires:

1. **A real shared-core module first** (~174-300 functions: the row-model DSL, app shell,
   and the mid-tier connectors like `planningWorkbenchContext`). This module alone would be
   comparable in size to several of the *already-shipped* Wave 6.4 leaves combined — it is
   not a quick warm-up step, it is the majority of the engineering risk in this whole
   effort, since it's the piece every other new module will import from.
2. **~10-15 genuine domain modules** for the remainder, each importing from the shared core
   — closer in spirit to the existing `dashboard_decomp_holdings.js` extraction, but there
   are roughly 10-15 more of them to do, several larger (the YTD cluster alone is bigger
   than the holdings extraction was).
3. **New tooling, not a continuation of hand-editing.** The holdings extraction was done by
   hand because it was one self-contained ~470-line block. Moving 700+ functions with
   dense, verified cross-references by hand is not a responsible approach for production
   financial software — per this repo's own reasoning for why the module-conversion pass
   needed `jscodeshift` instead of manual `export` prefixing. A split-and-verify codemod
   would need to: (a) assign each function to a target module using something like this
   analysis's clustering, (b) auto-generate the cross-module `import`/`window`-bridge calls
   for every edge that crosses a module boundary, and (c) verify byte-for-byte that no
   function body changed, only its file location and the bridge wiring around it — the same
   discipline `convert_dashboard.mjs` already applies, extended to a many-file transform
   instead of a single-file one.
4. **Every cross-module edge is a new load-order question.** The conversion pass spent real
   effort establishing that `type="module"` deferred-execution timing is safe for the
   existing file graph (`test_dashboard_startup_race_and_script_order.py`,
   the script-order Playwright spike). Splitting `dashboard.js` internally multiplies the
   number of "does A actually exist by the time B runs" questions from "handful of already-
   separate files" to "every one of the ~600 cross-domain-cluster call edges, including ones
   through the shared core." This needs the same rigor, not a lighter version of it.

## Recommendation

Do not schedule this as a direct continuation of Wave 6.4. It is a new, comparably-sized
project with its own risk profile. If/when it's prioritized:

1. Build the shared-core extraction first, as its own scoped pass — get
   `dashboard_row_model.js` (or similar) and `dashboard_app_shell.js` out, verified, and
   stable. This is valuable on its own even if the domain split never happens: it shrinks
   `dashboard.js` by ~20-25% and gives every future domain module something real to import
   from.
2. Only after that lands, revisit whether the remaining ~586-function graph's clusters are
   still stable (extracting the shared core will change some fan-in counts for what's left)
   and scope the domain modules from there.
3. Build the split-and-verify codemod as shared infrastructure before attempting either
   step by hand — the same "AST tool over regex/manual edits" judgment call the module-
   conversion pass already made, at larger scale.

**Not scoped further here — this document stops at "here is the shape of the problem and
why it's a separate project," per the request to scope it, not implement it.**
