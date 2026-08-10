# dashboard.js Domain-Module Split: Codemod Tooling + First Real Extraction — Design

**Predecessor:** `docs/superpowers/plans/2026-08-06-dashboard-js-domain-module-split-SCOPE.md`
(scoping only, no code changes). Its recommendation #3 was: build the split-and-verify
codemod as shared infrastructure before attempting the remaining domain splits by hand.
This spec is that tool, plus one real extraction as its proof.

**Predecessor's step 1** (shared-core extraction) is already done and merged
(`dashboard_decomp_row_model.js`, commit `0a026db`).

**Revision note (design review, 2026-08-10):** the first draft of this spec had four
defects, all found by verifying its assumptions against the real source rather than
trusting them. They are corrected inline below and called out in "Review findings" at the
end, because each one is a trap the *next* extraction pass would otherwise re-walk into.

## Goal

1. A generic, reusable codemod (`tools/js_codemod/extract_module.mjs`) that takes an
   explicit list of dashboard.js top-level declarations and a target file path, and
   mechanically splits them into a new ES module — self-verifying that no declaration
   body changed, only its file location and the bridge wiring around it.
2. A companion read-only analysis tool (`tools/js_codemod/find_clusters.mjs`) that
   recomputes the domain clustering against dashboard.js's *current* state, so this pass
   and every future one starts from a fresh, accurate call graph instead of the SCOPE
   doc's now-stale numbers (row_model.js already removed the hub layer that doc analyzed).
3. One real extraction using the tool, as both its proof and genuine progress: the
   24-function "assets: liabilities / note receivables / 529s / other assets" cluster
   plus the 4 constant tables only that cluster uses, into
   `frontend/js/dashboard_decomp_assets_other.js`.

## Non-goals

- Deciding or extracting the remaining ~10-14 domain clusters. This pass proves the tool
  on one cluster; the rest is future work using the same tool.
- Moving *shared* state. Only declarations with zero remaining references in dashboard.js
  and zero references in any other file may move (see the variable safety rule below).
  Genuinely shared state (`rows`, `activeStep`, `dirty`, ...) stays in dashboard.js and is
  reached through the existing generated window bridge.
- Handling reassigned (monkey-patched) functions like `renderMain`/`showStepHelp`. The
  tool hard-errors if asked to extract one; that needs the `let`/get+set-accessor
  treatment `convert_dashboard.mjs` already has for dashboard.js's own bridge, which this
  tool does not attempt to replicate for a *target* module.
- Converting any caller to real `import` syntax. The window bridge stays the compatibility
  mechanism, exactly as in `dashboard_decomp_holdings.js`.

## Architecture

### `tools/js_codemod/find_clusters.mjs` (read-only)

Rebuilds the same call-graph analysis the SCOPE doc used (regex-based "does function A's
body text reference function B's name" over dashboard.js's current top-level function
set), applies a fan-in cutoff to strip local hub functions, and runs connected components
on what remains. Writes `tools/js_codemod/clusters_report.json`: each component as a
sorted function-name list, sorted by component size descending, plus the fan-in table.
Never modifies source. Rerunnable after every future extraction, since removing a cluster
changes the remaining graph.

### `tools/js_codemod/extract_module.mjs` (the split-and-verify codemod)

```
node tools/js_codemod/extract_module.mjs \
  --names name1,name2,... \
  --out frontend/js/dashboard_decomp_<name>.js \
  --header-file <path to a text file with the module's doc comment> \
  [--check]
```

`--names` accepts both function and variable declaration names; the tool classifies each
by its AST node rather than requiring the caller to pre-sort them. `--header-file` rather
than an inline `--header` string: these headers are multi-paragraph prose, which is
painful and error-prone to pass through a Windows shell.

**Phase 1 — resolve and validate (no writes).** Parse dashboard.js. Resolve each name to
exactly one top-level declaration. Hard-abort, with no files touched, on any of:
- a name not found as a top-level declaration (typo/rename guard);
- a name listed in `census_report.json`'s `reassigned_functions` (out of scope, see
  Non-goals);
- a duplicate name in the request;
- **a variable that fails the safety rule**: after removal, the name must have zero
  remaining references anywhere in dashboard.js *outside the generated bridge block*, and
  zero references in any other `frontend/js/*.js` file or `frontend/index.html`. A
  variable that fails this is shared state and must stay behind; the tool says so by name
  instead of silently breaking it.

**Phase 2 — transform.** Splice the declarations out of dashboard.js by byte offset,
removing in descending-offset order so earlier offsets stay valid (same technique as
`extract_core.mjs`). Build the new module: header comment from `--header-file`, each
declaration's verbatim original text prefixed with `export `, in original file order,
then a trailing `Object.assign(window, { name1, name2, ... });` bridge listing every moved
name — identical shape to `dashboard_decomp_holdings.js`.

**Phase 3 — verify.** Write both files, then run two independent checks plus a syntax
check. Any failure restores dashboard.js from the in-memory original, deletes the new
module, and exits non-zero.

- **Round-trip check.** Re-read the newly written module *from disk*, parse it, and for
  each moved name recover its declaration text from that file's AST, stripping the leading
  `export `. Splice those *module-derived* texts back into the new dashboard.js at the
  recorded original offsets. Assert the result is byte-identical to the original
  dashboard.js. Deriving the text from the written output — not from the in-memory
  original — is what makes this a real check rather than a tautology: it is what catches a
  mangled `export ` prefix, a reordering bug, a wrong byte range, or a newline-handling
  error in the module writer.
- **Inventory check.** Parse both output files and assert
  `topLevelDecls(newDashboard) == topLevelDecls(original) − moved` and
  `topLevelDecls(newModule) == moved`. This catches anything removed or duplicated that
  was not requested.
- **Syntax check.** `node --check` on both files.

`--check` runs phases 1-3 against temporary paths and reports without leaving changes.

**Phase 4 — report.** Print the moved count, new file path, new dashboard.js line count,
and the exact follow-up commands (below). The tool deliberately does *not* run them:
keeping the census/bridge regeneration, the HTML wiring, and the ratchet update as
separate diffs is what makes each one reviewable, and matches how the row-model extraction
actually landed (commit `0a026db`).

### First real extraction: `dashboard_decomp_assets_other.js`

24 functions (computed against the current call graph; the component is stable across
fan-in cutoffs 3 through 8):

```
addEducation529Section, addLiability, addNoteReceivable, addOtherAssetItem,
deleteLiability, deleteNoteReceivable, deleteOtherAssetItem, liabilityFieldsForType,
noteReceivableRow, noteReceivableSubsections, otherAssetInputCell, otherAssetRow,
otherAssetRows, otherAssetSubsections, otherAssetTypeCell, renderAssetsSpecial,
renderHELOCInputsOnOtherPage, renderHsaPolicyOnOtherAssets, renderLiabilitiesTable,
renderNoteInterestTable, renderNoteReceivableTable, renderOtherAssetItemsTable,
setLiabilityType, updateLiability
```

plus 4 `const` tables, verified to be referenced by nothing else in dashboard.js and
nothing at all outside it, so they move rather than being stranded behind a generated
accessor:

```
LIABILITY_LABELS, LIABILITY_TYPES, LIABILITY_TYPE_FIELDS, OTHER_ASSET_TYPES
```

`serializeLiabilities`/`saveLiabilities` are excluded — the current call graph puts them in
the YTD/file-io cluster, since they share plan-persistence helpers rather than the assets
DOM. Confirmed with the user rather than assumed.

**Verified dependency surface** (so the implementation does not re-derive it):
- The cluster calls exactly one function that stays in dashboard.js: `renderMain`. It is
  a reassigned function with a get accessor on `window`, so a bare `renderMain()` call
  from the new module resolves to the live, decorator-wrapped implementation.
- It touches 6 dashboard.js state variables — `rows`, `searchText`, `planSource`, `dirty`
  (read) and `activeStep`, `lastBuildOk` (written). All 6 are already in
  `census_report.json`'s `externally_referenced_variables` with get+set accessors, and
  both written ones are `let`, so the writes work. No census change is needed for them.
- No file outside dashboard.js references any of the 28 moved names.

Follow-up steps after running the tool:
1. Add `<script type="module" src="js/dashboard_decomp_assets_other.js?v=1">` to
   `index.html` **immediately before** the `dashboard.js` tag, in the same position
   `dashboard_decomp_row_model.js` occupies — *not* after it with the other leaves. See
   Review finding 3.
2. Re-run `census.mjs`, then `convert_dashboard.mjs` — in that order, and only after the
   new module file exists, so the census sees the new file's cross-file references.
   Commit the refreshed `census_report.json`. This is what removes the 28 moved names from
   dashboard.js's own generated bridge.
3. Add a v5 entry to `frontend/js/modules/phase3_module_manifest.js` documenting this
   pass, following the v4 entry's precedent (commit `4b8ea07`).
4. Lower `DASHBOARD_JS_MAX_LINES` in `tests/test_frontend_size_ratchet.py` to the new
   actual line count (that file's own `test_ratchet_is_not_slack` requires it). Total-JS
   headroom is not a concern: 28,792 of 32,000 lines used, and this pass moves lines
   rather than adding them.
5. Run the regression net: `test_frontend_size_ratchet.py`,
   `test_dashboard_codemod_census_report_regression.py`,
   `test_dashboard_js_module_bridge_regression.py`,
   `test_dashboard_startup_race_and_script_order.py`,
   `test_dashboard_dead_code_sweep_regression.py`,
   `test_roadmap_steps_1_11_static_regression.py`, and the e2e
   `tests/e2e/script-order-spike.spec.js`.
6. Manual browser smoke: load the app, then add/edit/delete a row in each of Liabilities,
   Note Receivables, 529, and Other Assets, confirming no console `ReferenceError`.

## Error handling

Every failure mode in `extract_module.mjs` is a hard abort. Phase 1 aborts before any
write; phase 3 rolls back to the in-memory original and deletes the new module. There is
no partial-application mode — a codemod touching production financial software's UI layer
should never half-apply, and a rollback that leaves a syntactically valid but
behaviourally broken pair of files is the failure this tool exists to prevent.

## Testing

The codemod's primary correctness guarantee is the round-trip + inventory verification it
runs on *every* invocation, not a test that runs occasionally. Beyond that, the real
extraction is covered by the existing Python regression net listed above, which already
guards the bridge, the census, script order, and the size ratchet.

One new test file is added, `tests/test_dashboard_extract_module_tool.py`, with two
guards that the existing suite does not provide:
- the tool's `--check` mode exits 0 against the committed tree (drift detector, matching
  `test_codemod_check_mode_reports_no_drift`'s precedent);
- asking it to extract a reassigned function (`renderMain`) exits non-zero and leaves the
  tree unmodified — the safety rail most likely to be silently removed by a future edit.

## Review findings (2026-08-10)

Recorded because each is a trap the next extraction pass would otherwise repeat.

1. **The original self-verification was a tautology.** Reconstructing dashboard.js from
   the in-memory original chunks at their original offsets trivially reproduces the
   original by construction and proves nothing about what was written. The check only has
   force if the chunks are read back from the generated module file.
2. **"Functions only" was wrong.** Four `const` tables (`LIABILITY_LABELS`,
   `LIABILITY_TYPES`, `LIABILITY_TYPE_FIELDS`, `OTHER_ASSET_TYPES`) are read by the
   cluster and by nothing else anywhere in the repo. Leaving them behind would have
   stranded ~40 lines of dead-to-dashboard.js data and grown the generated bridge with
   four accessors that exist only to serve one other file. The tool needs variable support
   plus the zero-remaining-references safety rule.
3. **Script placement is load-bearing, and "after dashboard.js" was wrong.** dashboard.js
   ends its module body with `queueMicrotask(...)` scheduling the real boot work
   (`wireStepNavigation`, `restoreWorkbookViewState`, `loadCanonicalGlossary`, ...). A
   microtask checkpoint runs after that script's evaluation and can therefore fire before
   a *later* module script evaluates — so a module placed after dashboard.js is not
   guaranteed to have installed its window bridge before boot code that transitively
   reaches it. Placing the new module immediately *before* dashboard.js, where
   `row_model.js` already sits, removes the question entirely; it is safe to do so because
   the module's own top level is nothing but declarations and one `Object.assign`.
4. **A required step was missing:** `frontend/js/modules/phase3_module_manifest.js` needs a
   v5 entry. (The file also lives at `js/modules/`, not `js/`, which the first draft had
   wrong.)

A methodological note for whoever picks this up next: several intermediate findings here
were first produced by `node -e` one-liners through the Bash tool, and two of them were
*wrong* — shell escaping mangled the `\b` in a dynamically built `RegExp`, silently
producing false negatives on reference scans. Every conclusion in this document was
re-derived with a real `.mjs` file on disk. Do not trust `node -e` for this codebase's
analysis work.
