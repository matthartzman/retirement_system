# dashboard.js Domain-Module Split: Codemod Tooling + First Real Extraction — Design

**Predecessor:** `docs/superpowers/plans/2026-08-06-dashboard-js-domain-module-split-SCOPE.md`
(scoping only, no code changes). Its recommendation #3 was: build the split-and-verify
codemod as shared infrastructure before attempting the remaining domain splits by hand.
This spec is that tool, plus one real extraction as its proof.

**Predecessor's step 1** (shared-core extraction) is already done and merged
(`dashboard_decomp_row_model.js`, commit `0a026db`).

## Goal

1. A generic, reusable codemod (`tools/js_codemod/extract_module.mjs`) that takes an
   explicit list of dashboard.js top-level function names and a target file path, and
   mechanically splits them into a new ES module — self-verifying that no function body
   changed, only its file location and the bridge wiring around it.
2. A companion read-only analysis tool (`tools/js_codemod/find_clusters.mjs`) that
   recomputes the domain clustering against dashboard.js's *current* state, so this pass
   and every future one starts from a fresh, accurate call graph instead of the SCOPE
   doc's now-stale numbers (row_model.js already removed the hub layer that doc analyzed).
3. One real extraction using the tool, as both its proof and genuine progress: the
   24-function "assets: liabilities / note receivables / 529s / other assets" cluster,
   into `frontend/js/dashboard_decomp_assets_other.js`.

## Non-goals

- Deciding or extracting the remaining ~10-14 domain clusters. This pass proves the tool
  on one cluster; the rest is future work using the same tool.
- Moving top-level *variables* (state). Only functions are in scope — dashboard.js stays
  a classic (well, `type="module"`) script that any extracted module can still read/write
  as a bare global with zero bridging, per the pattern already established by
  `dashboard_decomp_holdings.js`'s header comment. This keeps the mechanical transform
  simple and avoids re-deriving ownership rules for shared state.
- Handling reassigned (monkey-patched) functions like `renderMain`/`showStepHelp`. The
  tool hard-errors if asked to extract one; that needs the `let`/get+set-accessor
  treatment `convert_dashboard.mjs` already has for dashboard.js's own bridge, which this
  tool does not attempt to replicate for a *target* module.

## Architecture

### `tools/js_codemod/find_clusters.mjs` (read-only)

Rebuilds the same call-graph analysis the SCOPE doc used (regex-based "does function A's
body text reference function B's name" over dashboard.js's current top-level function
set), applies a fan-in cutoff to strip local hub functions (e.g. `renderMain`, still
excluded from row-model extraction because it's reassigned), and runs connected components
on what remains. Writes `tools/js_codemod/clusters_report.json`: each component as a sorted
function-name list, sorted by component size descending. Never modifies source. Rerunnable
after every future extraction, since removing a cluster changes the remaining graph.

### `tools/js_codemod/extract_module.mjs` (the split-and-verify codemod)

```
node tools/js_codemod/extract_module.mjs \
  --functions name1,name2,... \
  --out frontend/js/dashboard_decomp_<name>.js \
  --header "<doc comment text>"
```

Steps:
1. Parse dashboard.js (jscodeshift/babel, same as `census.mjs`/`extract_core.mjs`).
   Resolve each requested name to exactly one top-level `FunctionDeclaration` (or a
   top-level `let/const name = function...` — same detection `census.mjs` already uses).
2. **Validate, hard-abort on any problem, before touching disk:**
   - Any requested name not found as a top-level function → abort (typo/rename guard).
   - Any requested name appears in `census_report.json`'s `reassigned_functions` → abort
     (out of scope; needs different handling — see Non-goals).
   - Duplicate names in the request → abort.
3. Splice the functions out of dashboard.js by byte offset, position-preserving
   (descending-offset removal so earlier offsets stay valid — same technique as
   `extract_core.mjs`).
4. Write the new module: header comment, each function's verbatim original text prefixed
   with `export `, in original file order, then a trailing
   `Object.assign(window, { name1, name2, ... });` bridge listing every extracted name —
   identical shape to `dashboard_decomp_holdings.js`.
5. **Self-verify before writing to disk**: reconstruct what dashboard.js would look like
   by re-inserting each removed function's exact original text back at its original
   offset into the new (post-removal) dashboard.js source, and assert that string is
   byte-identical to the original dashboard.js source read at step 1. Abort (write
   nothing) on any mismatch — this is the "verify byte-for-byte that no function body
   changed, only its file location" guarantee the SCOPE doc asked for.
6. Write both files, then run `node --check` on each. On failure, restore the original
   dashboard.js from the in-memory copy and delete the new file, then exit non-zero.
7. Print a summary (count extracted, new file path, new dashboard.js line count) and an
   explicit reminder of the manual follow-up steps (index.html script tag, census/bridge
   regen, ratchet update) — the tool does not perform these itself, keeping each concern
   a separately reviewable diff.

`--check` mode (matching `convert_dashboard.mjs`'s existing convention) runs steps 1-5
without writing, for CI/pre-flight use.

### First real extraction: `dashboard_decomp_assets_other.js`

Cluster (computed against the current call graph, stable across fan-in cutoffs 3-8):

```
addEducation529Section, addLiability, addNoteReceivable, addOtherAssetItem,
deleteLiability, deleteNoteReceivable, deleteOtherAssetItem, liabilityFieldsForType,
noteReceivableRow, noteReceivableSubsections, otherAssetInputCell, otherAssetRow,
otherAssetRows, otherAssetSubsections, otherAssetTypeCell, renderAssetsSpecial,
renderHELOCInputsOnOtherPage, renderHsaPolicyOnOtherAssets, renderLiabilitiesTable,
renderNoteInterestTable, renderNoteReceivableTable, renderOtherAssetItemsTable,
setLiabilityType, updateLiability
```

(`serializeLiabilities`/`saveLiabilities` are excluded — the current call graph puts them
in the YTD/file-io cluster, since they share plan-persistence helpers, not the assets DOM.
Confirmed with the user rather than assumed.)

Follow-up steps after running the tool:
1. Grep dashboard.js's top-level (non-function-body) boot code to confirm none of these
   24 names are called before any module has a chance to execute; place the new
   `<script type="module" src="js/dashboard_decomp_assets_other.js?v=1">` tag in
   `index.html` alongside the other post-dashboard.js decomp modules (matching
   `holdings`/`misc`'s existing position) if confirmed.
2. Re-run `census.mjs` (updates `census_report.json` to reflect dashboard.js's shrunk
   function set) and `convert_dashboard.mjs` (regenerates dashboard.js's own window-bridge
   block, dropping the 24 removed names). Commit the refreshed census report.
3. Lower `DASHBOARD_JS_MAX_LINES` in `tests/test_frontend_size_ratchet.py` to the new
   actual line count (that test's own `test_ratchet_is_not_slack` requires this).
4. Run the full regression net: `test_frontend_size_ratchet.py`,
   `test_dashboard_codemod_census_report_regression.py`,
   `test_dashboard_js_module_bridge_regression.py`,
   `test_dashboard_startup_race_and_script_order.py`,
   `test_dashboard_dead_code_sweep_regression.py`, and the e2e
   `tests/e2e/script-order-spike.spec.js`.
5. Manual browser smoke: load the app, add/edit/delete a row in each of Liabilities, Note
   Receivables, 529, and Other Assets, confirming no console `ReferenceError`.

## Error handling

Every failure mode in `extract_module.mjs` is a hard abort with no partial writes: missing
function, reassigned function, duplicate name, byte-reconstruction mismatch, or a
`node --check` failure post-write (which triggers rollback rather than leaving a broken
pair of files). There is no "best effort" mode — a codemod touching production financial
software's UI layer should never partially apply.

## Testing

- `extract_module.mjs` and `find_clusters.mjs` are themselves tools, not app code; their
  correctness is proven by (a) the self-verification step built into the codemod itself
  (byte-for-byte reconstruction check, run on every invocation, not just in tests) and
  (b) the existing Python regression suite listed above, run after the real extraction.
- No new Python test file is added for the tools themselves — consistent with
  `census.mjs`/`convert_dashboard.mjs`/`extract_core.mjs`, which are exercised indirectly
  through the regression suite's `subprocess.run([...])` calls (e.g.
  `test_codemod_check_mode_reports_no_drift`) rather than unit-tested directly. Adding a
  matching `test_extract_module_check_mode...` style guard for the new tool's `--check`
  mode is in scope if the implementation plan finds it valuable, but is not a hard
  requirement of this spec.
