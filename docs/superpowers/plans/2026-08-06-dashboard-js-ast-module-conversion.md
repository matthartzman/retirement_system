# dashboard.js AST-Based Module Conversion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert `frontend/js/dashboard.js` — the last classic (non-module) script and the file Wave 6.4 explicitly deferred — into a real ES module, using an auto-generated (not hand-typed) `export` + `window` bridge built and verified by a small Node AST codemod, so its public surface is an explicit, tool-verified list instead of "everything is a global."

**Architecture:** A new `tools/js_codemod/` Node toolchain built on `jscodeshift` (which wraps Babel's parser and the `recast` printer, so untouched source is byte-preserved — critical since `dashboard.js` sits at a hard line-count ceiling and two tests `eval()` a literal slice of its source) does three jobs: (1) **census** — exhaustively enumerate every top-level function and variable declaration in `dashboard.js` plus every external cross-file reference to them, since `dashboard.js` declares many top-level state variables via multi-declarator `let a = 1, b = 2, ...;` statements that a regex cannot safely enumerate; (2) **transform** — add `export` to every top-level function declaration and append a generated `window` bridge: `Object.assign(window, {...})` value-copy for functions that are only ever *called* externally, plus a `get`+`set` `Object.defineProperty` accessor (not a value copy, and not get-only) for the small number of functions that other already-converted leaf modules *reassign* as a monkey-patch decorator chain, and for every top-level state variable another module reads or writes; (3) **verify** — an empirical script-order spike using this repo's existing Playwright setup confirms `type="module"` scripts' actual execution timing relative to classic scripts, before any assumption about `frontend/index.html`'s script order is relied on. `dashboard.js` stays one file in this pass — splitting it into multiple cohesive modules by domain is named as explicit future work this tooling enables but does not attempt here (a second dependency-graph problem, out of scope).

> **Design correction (2026-08-06, mid-execution):** the original version of this plan assumed every top-level function is only ever *called* externally (safe for a one-time `Object.assign` value copy) and every top-level variable is only ever *read* externally (safe for a get-only accessor). Running the census for real falsified both assumptions: `dashboard_source_truth_banners.js` and `dashboard_batch_assumption_edit.js` reassign `renderMain`/`showStepHelp` as a decorator chain (`const old = renderMain; renderMain = function(){ old(); extra(); };`) — this works today because classic `<script>` top-level `let`/`function` bindings share one script-scope declarative environment across all classic scripts in a document, which module code can also read *and write* as bare identifiers (modules only make their *own* top-level bindings private, not other scripts'). A one-time value copy would let external code overwrite `window.renderMain` while dashboard.js's own ~19,000 lines kept calling their private, un-wrapped original — silently breaking glossary decoration and the batch-edit panel on every render. Separately, 42 top-level variables (`activeStep`, the `buildOverlay*`/`_smooth*` progress-tracker state, `liquidityBuffers`, `csrfToken`, etc.) are *written*, not just read, by already-converted leaf modules. Task 1 and Task 3 below reflect the corrected design: both cases get a `get`+`set` accessor, and the 2 reassigned functions additionally change from `function name(){}` to `let name = function(){}` so they're reassignable at all.

**Tech Stack:** Node.js v26+ (already available and already used via `subprocess.run(["node", ...])` in this repo's tests/tools) + `jscodeshift` (new npm devDependency — nothing AST-capable for JS exists in this repo today) + this repo's existing Playwright devDependency for the script-order spike. No new Python dependencies.

## Global Constraints

- `tests/test_frontend_size_ratchet.py`'s `DASHBOARD_JS_MAX_LINES` constant must be updated in the same commit that changes `dashboard.js`'s line count (the test explicitly forbids leaving it stale in either direction — `test_ratchet_is_not_slack` fails if the ceiling sits more than 500 lines above the real count).
- `tests/test_frontend_size_ratchet.py::test_total_frontend_js_has_a_ceiling` requires total `frontend/js/*.js` lines stay `<= 32,000`.
- `tests/test_dashboard_startup_race_and_script_order.py` has two tests that shell out to `node` and `eval()` a literal slice of `dashboard.js`'s source between the exact markers `let appCheckPromise = null;` and `function setAppControls(on) {`. That region's text must not move or change during this pass — the codemod's transform must not touch it beyond the mechanical `export` keyword insertion at the very start of a top-level `function` line (not applicable inside this region unless a function declaration itself starts there, which it does not per the grep in Task 1: only `let appCheckPromise` and `function setAppControls` sit at those markers, both preserved verbatim by a format-preserving printer).
- Per this repo's `CLAUDE.md`, run the fast test tier (`pytest tests/ -m "not slow" --tb=short -q`) after every non-trivial change in this plan, and the full suite (`pytest tests/ -n auto --tb=short -q`) before considering the whole plan done, since this touches the build/report-adjacent frontend surface.
- Follow this repo's test-naming convention: `test_<succinct_scope>_<type>.py`, no wave/issue/version numbers in the name (`tests/test_no_tracking_id_test_names_regression.py` enforces this mechanically).
- Per this repo's own UI-change rule: any step that changes what loads in the browser must be verified in an actual browser (desktop or server mode), not just by the automated test suite.

---

## File Structure

| File | Responsibility |
|---|---|
| `package.json` | Add `jscodeshift` as a devDependency |
| `tools/js_codemod/census.mjs` | **New.** Parses `dashboard.js` + every other `frontend/js/*.js` file + `frontend/index.html`'s inline `<script>` blocks. Emits `tools/js_codemod/census_report.json`: every top-level function/variable name in `dashboard.js`, and every external bare-identifier reference to those names, tagged `call`/`read`/`assign` and `top-level`/`inside-function`. |
| `tools/js_codemod/census_report.json` | **New, generated.** Committed so the regression test (Task 6) can diff against a re-run without needing Node at test time beyond the one subprocess call. |
| `tools/js_codemod/convert_dashboard.mjs` | **New.** Reads `census_report.json`, transforms `frontend/js/dashboard.js` in place: adds `export` to every top-level function, appends the generated `Object.defineProperty` getters + `Object.assign(window, {...})` bridge block. Supports `--check` (dry-run, non-zero exit on drift) for CI/regression use. |
| `tools/js_codemod/fixtures/script_order_spike.html` | **New.** Minimal repro page for the empirical script-order spike (Task 2). |
| `tests/e2e/test_script_order_spike.spec.ts` (or `.js`, matching this repo's existing Playwright test extension — confirm in Task 2) | **New.** Playwright test that loads the spike fixture and asserts observed script-execution order. |
| `frontend/js/dashboard.js` | **Modified** by the codemod (Task 3): every top-level `function`/`async function` gets `export` prefixed; a new generated block appended at end of file. |
| `frontend/index.html` | **Modified** (Task 4): `dashboard.js`'s `<script>` tag becomes `type="module"`, version-bumped query string. |
| `tests/test_frontend_size_ratchet.py` | **Modified** (Task 5): `DASHBOARD_JS_MAX_LINES` updated to the new real count. |
| `tests/test_dashboard_startup_race_and_script_order.py` | **Modified** (Task 5), exact edits depend on Task 2's spike finding — see Task 5 for both branches. |
| `tests/test_dashboard_js_module_bridge_regression.py` | **New** (Task 6). Regression coverage for the codemod's own output staying in sync. |
| `frontend/js/modules/phase3_module_manifest.js` | **Modified** (Task 8): bump schema, record `dashboard.js`'s conversion, explicitly document the multi-file-split non-goal. |

---

### Task 1: Census tool — enumerate every top-level declaration and every external reference

> **Note:** the code blocks below are the plan's original draft. The actual implementation (`tools/js_codemod/census.mjs`, already committed) reflects the design correction above: it reports `reassigned_functions` and `externally_referenced_variables` instead of a single `must_review` list, and does not gate/exit-1 (the census's job is now to *characterize* both cases correctly, not to flag them as a blocker — Task 3 handles both). Read the committed file for the current, authoritative version; the text below is left for historical rationale only.

**Files:**
- Create: `tools/js_codemod/census.mjs`
- Create: `package.json` devDependency entry for `jscodeshift`
- Test: `tests/test_dashboard_codemod_census_report_regression.py`

**Interfaces:**
- Produces: `tools/js_codemod/census_report.json` with shape:
  ```json
  {
    "schema": "dashboard_census_v1",
    "functions": ["acceptTerms", "accountDisplayLabel", "..."],
    "variables": ["activeStep", "apiBase", "budgetLines", "..."],
    "external_references": [
      {"name": "activeStep", "file": "frontend/js/dashboard_decomp_local_backups.js", "kind": "read", "scope": "inside-function"},
      {"name": "setStep", "file": "frontend/js/navigation.js", "kind": "call", "scope": "inside-function"}
    ],
    "must_review": []
  }
  ```
  `must_review` lists any `external_references` entry with `kind: "assign"` — an external file *writing* to one of `dashboard.js`'s top-level variables, which this plan's live-getter design (read-only) cannot safely bridge. This must be empty for Task 3 to proceed as designed; if non-empty, stop and re-plan that specific variable's bridge (do not silently ignore).

- [ ] **Step 1: Add jscodeshift as a devDependency**

```bash
cd "C:/RetirementPlanning/Version 10"
npm install --save-dev jscodeshift
```

Verify `package.json`'s `devDependencies` now includes `"jscodeshift"` alongside the existing `"@playwright/test"`.

- [ ] **Step 2: Write the census script**

Create `tools/js_codemod/census.mjs`:

```js
#!/usr/bin/env node
// Census tool for the dashboard.js module-conversion plan (docs/superpowers/plans/
// 2026-08-06-dashboard-js-ast-module-conversion.md). Read-only: never modifies source.
// Usage: node tools/js_codemod/census.mjs
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import jscodeshift from "jscodeshift";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..", "..");
const j = jscodeshift.withParser("babel");

const DASHBOARD_PATH = path.join(ROOT, "frontend", "js", "dashboard.js");
const JS_DIR = path.join(ROOT, "frontend", "js");
const INDEX_HTML_PATH = path.join(ROOT, "frontend", "index.html");

function collectTopLevelDeclarations(source) {
  const root = j(source);
  const functions = new Set();
  const variables = new Set();

  root.find(j.Program).forEach((programPath) => {
    for (const stmt of programPath.node.body) {
      if (
        (stmt.type === "FunctionDeclaration" || stmt.type === "FunctionExpression") &&
        stmt.id
      ) {
        functions.add(stmt.id.name);
      } else if (stmt.type === "VariableDeclaration") {
        for (const decl of stmt.declarations) {
          if (decl.id.type === "Identifier") variables.add(decl.id.name);
        }
      }
    }
  });

  return { functions: [...functions].sort(), variables: [...variables].sort() };
}

function findExternalReferences(names, source, fileLabel) {
  const nameSet = new Set(names);
  const root = j(source);
  const refs = [];

  root.find(j.Identifier).forEach((idPath) => {
    const name = idPath.node.name;
    if (!nameSet.has(name)) return;

    const parent = idPath.parent.node;
    // Skip the identifier's own declaration site / property-key / member-property
    // positions -- we only want bare-reference reads/calls/assignments.
    if (
      (parent.type === "FunctionDeclaration" && parent.id === idPath.node) ||
      (parent.type === "VariableDeclarator" && parent.id === idPath.node) ||
      (parent.type === "MemberExpression" && parent.property === idPath.node && !parent.computed) ||
      (parent.type === "Property" && parent.key === idPath.node && !parent.computed) ||
      parent.type === "FunctionDeclaration" && parent.params.includes(idPath.node)
    ) {
      return;
    }

    let kind = "read";
    if (parent.type === "CallExpression" && parent.callee === idPath.node) kind = "call";
    if (
      parent.type === "AssignmentExpression" &&
      parent.left === idPath.node
    ) {
      kind = "assign";
    }

    // Walk up to see if we're inside any function body (vs. true top-level).
    let scope = "top-level";
    let up = idPath.parent;
    while (up) {
      if (
        up.node.type === "FunctionDeclaration" ||
        up.node.type === "FunctionExpression" ||
        up.node.type === "ArrowFunctionExpression"
      ) {
        scope = "inside-function";
        break;
      }
      up = up.parent;
    }

    refs.push({ name, file: fileLabel, kind, scope });
  });

  return refs;
}

function main() {
  const dashboardSource = fs.readFileSync(DASHBOARD_PATH, "utf8");
  const { functions, variables } = collectTopLevelDeclarations(dashboardSource);
  const allNames = [...functions, ...variables];

  const externalReferences = [];
  for (const entry of fs.readdirSync(JS_DIR)) {
    const full = path.join(JS_DIR, entry);
    if (full === DASHBOARD_PATH || !entry.endsWith(".js")) continue;
    const source = fs.readFileSync(full, "utf8");
    const label = path.relative(ROOT, full).replace(/\\/g, "/");
    externalReferences.push(...findExternalReferences(allNames, source, label));
  }
  // frontend/index.html's inline <script> blocks (not src= files) can also
  // reference dashboard.js globals -- extract and scan them too.
  const html = fs.readFileSync(INDEX_HTML_PATH, "utf8");
  const inlineScriptRe = /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g;
  let m;
  while ((m = inlineScriptRe.exec(html))) {
    externalReferences.push(
      ...findExternalReferences(allNames, m[1], "frontend/index.html (inline)"),
    );
  }

  const mustReview = externalReferences.filter(
    (r) => r.kind === "assign" && variables.includes(r.name),
  );

  const report = {
    schema: "dashboard_census_v1",
    functions,
    variables,
    external_references: externalReferences,
    must_review: mustReview,
  };

  const outPath = path.join(__dirname, "census_report.json");
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2) + "\n", "utf8");
  console.log(
    `Wrote ${outPath}: ${functions.length} functions, ${variables.length} variables, ` +
      `${externalReferences.length} external references, ${mustReview.length} need review.`,
  );
  if (mustReview.length) {
    console.error("must_review is non-empty -- see census_report.json before proceeding.");
    process.exitCode = 1;
  }
}

main();
```

- [ ] **Step 3: Run it and inspect the output**

```bash
node tools/js_codemod/census.mjs
```

Expected: exits 0 (assuming `must_review` is empty — if it is not, stop here and read `census_report.json`'s `must_review` array before continuing to any later task, since it means some file *writes* to a `dashboard.js` top-level variable, not just reads it, and the live-getter bridge design in Task 3 does not handle writes). Sanity-check the printed counts: `functions` should be in the 700–850 range (760 at last measurement; new code may have landed since) and `variables` should be several dozen (the file declares many top-level state variables via multi-declarator `let a = 1, b = 2, ...;` statements — e.g. `activeStep` is declared at dashboard.js's existing line ~916 as one declarator inside a `let apiBase = "", ..., activeStep = "start", ...;` statement starting around line 895, which is exactly why a naive `^let name` regex cannot find it and this AST walk is required).

- [ ] **Step 4: Commit the generated report and write its regression test**

Create `tests/test_dashboard_codemod_census_report_regression.py`:

```python
"""The dashboard.js module-conversion census (tools/js_codemod/census.mjs) must
stay runnable and its invariants must hold, since the conversion codemod
(Task 3 of docs/superpowers/plans/2026-08-06-dashboard-js-ast-module-conversion.md)
depends on this report being accurate.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CENSUS_SCRIPT = ROOT / "tools" / "js_codemod" / "census.mjs"
REPORT_PATH = ROOT / "tools" / "js_codemod" / "census_report.json"


def _run_census():
    result = subprocess.run(
        ["node", str(CENSUS_SCRIPT)], cwd=ROOT, text=True, capture_output=True, timeout=60
    )
    return result


def test_census_script_runs_and_reports_no_variables_needing_review():
    result = _run_census()
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert report["must_review"] == [], (
        "An external file writes to a dashboard.js top-level variable -- the live-getter "
        "bridge design only handles reads. Re-plan that variable's bridge before proceeding."
    )


def test_census_function_and_variable_counts_are_in_expected_bands():
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert 700 <= len(report["functions"]) <= 900
    assert len(report["variables"]) >= 10
    assert set(report["functions"]).isdisjoint(report["variables"])


def test_census_report_committed_copy_matches_a_fresh_run():
    committed = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    _run_census()
    fresh = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert committed == fresh, (
        "dashboard.js's top-level declarations changed since the committed census_report.json "
        "was generated. Re-run tools/js_codemod/census.mjs and commit the new report."
    )
```

- [ ] **Step 5: Run the test**

```bash
python -m pytest tests/test_dashboard_codemod_census_report_regression.py -v
```

Expected: all 3 PASS (the third test re-runs the script, which overwrites `census_report.json` with an identical file if nothing changed — safe/idempotent).

- [ ] **Step 6: Commit**

```bash
git add package.json package-lock.json tools/js_codemod/census.mjs tools/js_codemod/census_report.json tests/test_dashboard_codemod_census_report_regression.py
git commit -m "Add dashboard.js census tool: enumerate top-level declarations and external references"
```

---

### Task 2: Empirical script-order spike

Converting `dashboard.js` from a classic (blocking, synchronous) script to `type="module"` (deferred) is a genuine timing change relative to the *other* classic scripts and the already-converted module leaves that sit both before and after `dashboard.js`'s `<script>` tag in `frontend/index.html` today. Confirm the actual browser behavior empirically before deciding whether `dashboard_decomp_local_backups.js` (the one documented classic-script consumer of `dashboard.js`'s bare globals) needs any change.

**Files:**
- Create: `tools/js_codemod/fixtures/script_order_spike.html`
- Create: `tests/e2e/test_script_order_spike.spec.js` (confirm this repo's actual Playwright test file convention/location first — check `tests/e2e/` if it exists, or wherever the existing Playwright devDependency is actually invoked from, e.g. a `playwright.config.js`; adjust the path below to match)

**Interfaces:**
- Produces: a documented finding (a short comment block) consumed by Task 5's decision about `tests/test_dashboard_startup_race_and_script_order.py`.

- [ ] **Step 1: Find how Playwright is currently invoked in this repo**

```bash
find . -maxdepth 2 -iname "playwright.config*"
grep -rn "playwright" package.json
```

Use whatever config/command that surfaces (e.g. `npx playwright test`) for Step 3 below instead of guessing a path.

- [ ] **Step 2: Write the spike fixture**

Create `tools/js_codemod/fixtures/script_order_spike.html`:

```html
<!doctype html>
<html>
<head><meta charset="utf-8"><title>script order spike</title></head>
<body>
<div id="log"></div>
<script>
  window.__order = [];
</script>
<script>
  window.__order.push("classic-early");
</script>
<script type="module">
  window.__order.push("module-before-tag");
</script>
<script>
  window.__order.push("classic-late");
</script>
<script type="module">
  window.__order.push("module-after-tag");
</script>
<script>
  document.addEventListener("DOMContentLoaded", () => {
    window.__order.push("dom-content-loaded");
    document.getElementById("log").textContent = window.__order.join(",");
  });
</script>
</body>
</html>
```

- [ ] **Step 3: Write the Playwright spike test**

Create `tests/e2e/test_script_order_spike.spec.js` (adjust extension/location to match Step 1's finding):

```js
const { test, expect } = require("@playwright/test");
const path = require("node:path");

test("classic scripts run before module scripts, both before DOMContentLoaded", async ({ page }) => {
  const fixture = path.resolve(__dirname, "../../tools/js_codemod/fixtures/script_order_spike.html");
  await page.goto("file://" + fixture);
  const log = await page.locator("#log").textContent();
  const order = log.split(",");

  expect(order.indexOf("classic-early")).toBeLessThan(order.indexOf("classic-late"));
  expect(order.indexOf("classic-late")).toBeLessThan(order.indexOf("module-before-tag"));
  expect(order.indexOf("module-before-tag")).toBeLessThan(order.indexOf("module-after-tag"));
  expect(order.indexOf("module-after-tag")).toBeLessThan(order.indexOf("dom-content-loaded"));
});
```

- [ ] **Step 4: Run it and record the finding**

```bash
npx playwright test tests/e2e/test_script_order_spike.spec.js
```

Expected (per the HTML spec's documented behavior for `type="module"` scripts without an `async` attribute: they defer, executing in document order relative to each other, after all classic scripts, before `DOMContentLoaded`): PASS, confirming `classic-early < classic-late < module-before-tag < module-after-tag < dom-content-loaded`.

Add a comment to `tools/js_codemod/fixtures/script_order_spike.html` recording the confirmed result:

```html
<!--
  Confirmed 2026-08-06 via tests/e2e/test_script_order_spike.spec.js: ALL classic
  scripts run (in document order) before ANY type="module" script runs; module
  scripts then run in document order among themselves; both finish before
  DOMContentLoaded fires. This means: once frontend/js/dashboard.js becomes
  type="module" (Task 4), it moves from "runs synchronously at its document
  position" to "runs after every remaining classic script (dashboard_shared_helpers.js,
  pywebview_bridge.js, dashboard_decomp_local_backups.js -- all three stay classic),
  in module-document-order relative to the other already-converted module leaves."
  Since dashboard_decomp_local_backups.js is CLASSIC and dashboard.js becomes a
  MODULE, dashboard_decomp_local_backups.js is now guaranteed to finish its
  top-level execution strictly BEFORE dashboard.js's module code runs (classic
  always precedes module), which is a STRONGER guarantee than today's
  classic-vs-classic document-order guarantee alone. dashboard_decomp_local_backups.js's
  functions (invoked later, from dashboard.js's own async checkAppStatus().then(...)
  boot chain) will find window.activeStep/api/showMessage/renderMain/esc already
  bridged by then regardless, since that boot chain runs even later still (a
  microtask after all top-level module/classic code has finished). No change
  needed to dashboard_decomp_local_backups.js or its script-tag position.
-->
```

- [ ] **Step 5: Commit**

```bash
git add tools/js_codemod/fixtures/script_order_spike.html tests/e2e/test_script_order_spike.spec.js
git commit -m "Add empirical script-order spike for dashboard.js module conversion"
```

---

### Task 3: Codemod — convert dashboard.js to export its top-level surface

> **Note:** per the design correction above, the actual codemod additionally: (a) converts `renderMain`/`showStepHelp` from `function name(){}` to `let name = function(){}` before exporting, and (b) emits a `get`+`set` `Object.defineProperty` accessor — not a value copy, not get-only — for those 2 functions and for every name in `externally_referenced_variables` (42 variables). Only the remaining ~758 functions (never reassigned) use the simple `Object.assign` value-copy bridge described below. Read the committed `tools/js_codemod/convert_dashboard.mjs` for the authoritative version once this task lands.

**Files:**
- Create: `tools/js_codemod/convert_dashboard.mjs`
- Modify: `frontend/js/dashboard.js` (generated output of running the codemod)

**Interfaces:**
- Consumes: `tools/js_codemod/census_report.json` (Task 1)
- Produces: `frontend/js/dashboard.js` with (a) `export` prefixed on every top-level `function`/`async function` declaration, (b) a new final block:
  ```js
  // AUTO-GENERATED by tools/js_codemod/convert_dashboard.mjs -- do not hand-edit.
  // Regenerate: node tools/js_codemod/census.mjs && node tools/js_codemod/convert_dashboard.mjs
  Object.defineProperty(window, "activeStep", { get: () => activeStep, configurable: true });
  // ... one such line per externally-read top-level variable ...
  Object.assign(window, {
    acceptTerms, accountDisplayLabel, /* ... all top-level function names ... */
  });
  ```

- [ ] **Step 1: Write the codemod**

Create `tools/js_codemod/convert_dashboard.mjs`:

```js
#!/usr/bin/env node
// Converts frontend/js/dashboard.js's top-level functions to `export function`
// and appends a generated window bridge, so the file can become type="module"
// while every existing external caller keeps working unchanged.
// Usage:
//   node tools/js_codemod/convert_dashboard.mjs          (writes the file)
//   node tools/js_codemod/convert_dashboard.mjs --check  (exit 1 if it would change anything)
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import jscodeshift from "jscodeshift";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..", "..");
const DASHBOARD_PATH = path.join(ROOT, "frontend", "js", "dashboard.js");
const CENSUS_PATH = path.join(__dirname, "census_report.json");
const j = jscodeshift.withParser("babel");

const START_MARKER = "// AUTO-GENERATED by tools/js_codemod/convert_dashboard.mjs";

function stripExistingGeneratedBlock(source) {
  const idx = source.indexOf(START_MARKER);
  return idx === -1 ? source : source.slice(0, idx).replace(/\s*$/, "\n");
}

function exportTopLevelFunctions(source) {
  const root = j(source);
  root.find(j.Program).forEach((programPath) => {
    for (const stmt of programPath.node.body) {
      if (stmt.type === "FunctionDeclaration" && stmt.id) {
        // jscodeshift/recast preserves formatting for untouched nodes; wrapping
        // in an ExportNamedDeclaration only changes this statement's own text.
        const exported = j.exportNamedDeclaration(stmt, []);
        j(stmt).replaceWith(exported);
      }
    }
  });
  return root.toSource({ quote: "double" });
}

function buildGeneratedBlock(census) {
  const { functions, variables, external_references } = census;
  const externallyRead = new Set(
    external_references
      .filter((r) => variables.includes(r.name) && r.kind !== "assign")
      .map((r) => r.name),
  );

  const getterLines = [...externallyRead]
    .sort()
    .map(
      (name) =>
        `Object.defineProperty(window, ${JSON.stringify(name)}, { get: () => ${name}, configurable: true });`,
    );

  const wrapped = [];
  let line = "";
  for (const name of functions) {
    const piece = name + ", ";
    if ((line + piece).length > 100) {
      wrapped.push("  " + line.trimEnd());
      line = "";
    }
    line += piece;
  }
  if (line) wrapped.push("  " + line.trimEnd());

  return [
    START_MARKER,
    "// Regenerate: node tools/js_codemod/census.mjs && node tools/js_codemod/convert_dashboard.mjs",
    ...getterLines,
    "Object.assign(window, {",
    ...wrapped,
    "});",
    "",
  ].join("\n");
}

function main() {
  const check = process.argv.includes("--check");
  const census = JSON.parse(fs.readFileSync(CENSUS_PATH, "utf8"));
  const original = fs.readFileSync(DASHBOARD_PATH, "utf8");
  const withoutGenerated = stripExistingGeneratedBlock(original);
  const exported = exportTopLevelFunctions(withoutGenerated);
  const generatedBlock = buildGeneratedBlock(census);
  const next = exported.replace(/\s*$/, "\n") + "\n" + generatedBlock;

  if (check) {
    if (next !== original) {
      console.error("dashboard.js is out of sync with the codemod. Run without --check to fix.");
      process.exitCode = 1;
    } else {
      console.log("dashboard.js matches the codemod's expected output.");
    }
    return;
  }

  fs.writeFileSync(DASHBOARD_PATH, next, "utf8");
  console.log(`Wrote ${DASHBOARD_PATH}: ${census.functions.length} functions exported and bridged.`);
}

main();
```

- [ ] **Step 2: Run it for real**

```bash
node tools/js_codemod/convert_dashboard.mjs
```

Expected: prints the function count (~760) and the diff (`git diff frontend/js/dashboard.js`) shows: every top-level `function name(` line gained a leading `export `; every top-level `async function name(` line gained a leading `export `; nothing else in the existing ~19,188 lines changed; a new block appended at the end.

- [ ] **Step 3: Verify the two literal markers survived untouched**

```bash
grep -n "let appCheckPromise = null;" frontend/js/dashboard.js
grep -n "function setAppControls(on) {" frontend/js/dashboard.js
```

Expected: both still present, verbatim (neither is a top-level `function` declaration matching the `export`-insertion rule at its own start — `setAppControls` is nested inside another function per the earlier grep showing it referenced, not declared, at top level — confirm this explicitly: `grep -n "^function setAppControls\|^async function setAppControls"` should return nothing, meaning it is NOT a top-level declaration and the codemod does not touch its line).

- [ ] **Step 4: Run the `--check` mode to confirm idempotency**

```bash
node tools/js_codemod/convert_dashboard.mjs --check
```

Expected: `dashboard.js matches the codemod's expected output.`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add tools/js_codemod/convert_dashboard.mjs frontend/js/dashboard.js
git commit -m "Codemod: export dashboard.js top-level functions and generate window bridge"
```

---

### Task 4: Flip the script tag to a real module

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: Change the script tag**

In `frontend/index.html`, change:
```html
<script src="js/dashboard.js?v=44"></script>
```
to:
```html
<script type="module" src="js/dashboard.js?v=45"></script>
```

- [ ] **Step 2: Manual browser check (per this repo's UI-change rule)**

Start the app (`python main.py --mode server` or the desktop mode) and in the browser:
- Confirm the page loads with no console errors (check for `ReferenceError` specifically — the classic symptom of a missing bridge entry).
- Click a Settings → Workbook Formatting Tab-navigation field (exercises an `onkeydown="wfWidthInputKeydown(event)"` handler defined in a sibling module, calling back into `window.showFieldHelp` etc. from dashboard.js).
- Click "Save Changes" (exercises `saveAll(true)`, a dashboard.js top-level function invoked via inline `onclick` in `frontend/index.html` itself).
- Navigate to the Local Backups settings page and click "Run Backup Now" (exercises the one documented classic-script cross-file dependency: `dashboard_decomp_local_backups.js` reading `activeStep`/`api`/`showMessage`/`renderMain`/`esc` from `window`).

Expected: no console errors, all three flows behave as before.

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "Load dashboard.js as a real ES module"
```

---

### Task 5: Update the two guardrail tests

**Files:**
- Modify: `tests/test_frontend_size_ratchet.py`
- Modify: `tests/test_dashboard_startup_race_and_script_order.py`

- [ ] **Step 1: Recompute and update the line-count ratchet**

```bash
wc -l frontend/js/dashboard.js
```

Update `DASHBOARD_JS_MAX_LINES` in `tests/test_frontend_size_ratchet.py` to this exact new value (the file only grows by the generated block's line count — no existing lines were removed — so this is a small, known increase from 19,188; compute and use the real number, do not estimate).

- [ ] **Step 2: Update the script-order test per Task 2's confirmed finding**

In `tests/test_dashboard_startup_race_and_script_order.py`, find `test_local_backups_module_loads_before_dashboard_js`. Per Task 2's finding (classic scripts always finish before any module script runs), this assertion becomes *more* true, not less — `dashboard_decomp_local_backups.js` stays classic and `dashboard.js` becomes a module, so the ordering guarantee strengthens from "same category, document order" to "different category, classic always first." Update the test's docstring/comment to record this reasoning (do not delete the test — it still protects real behavior, just via a stronger guarantee):

```python
def test_local_backups_module_loads_before_dashboard_js():
    """dashboard_decomp_local_backups.js (classic script) must appear before
    dashboard.js (type="module" as of the AST-based conversion, see
    docs/superpowers/plans/2026-08-06-dashboard-js-ast-module-conversion.md).
    Per that plan's script-order spike (tools/js_codemod/fixtures/script_order_spike.html),
    ALL classic scripts finish executing before ANY module script runs, so this
    ordering is not just document-order convention anymore -- it's a strictly
    stronger guarantee (different script category) that dashboard_decomp_local_backups.js's
    functions (invoked later, from dashboard.js's async checkAppStatus().then(...)
    boot chain) will find window.activeStep/api/showMessage/renderMain/esc already
    bridged by dashboard.js's generated Object.assign/defineProperty block.
    """
    # ... existing body unchanged ...
```

Leave the two Node-`eval()` tests (`test_concurrent_checkappstatus_calls_share_the_same_in_flight_result`, `test_checkappstatus_result_is_not_stale_false_during_the_race_window`) untouched — Task 3, Step 3 already confirmed their literal markers survived.

- [ ] **Step 3: Run both files**

```bash
python -m pytest tests/test_frontend_size_ratchet.py tests/test_dashboard_startup_race_and_script_order.py -v
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_frontend_size_ratchet.py tests/test_dashboard_startup_race_and_script_order.py
git commit -m "Update size ratchet and script-order test docs for dashboard.js module conversion"
```

---

### Task 6: Regression test for the codemod's own output

**Files:**
- Create: `tests/test_dashboard_js_module_bridge_regression.py`

- [ ] **Step 1: Write the test**

```python
"""Guards the output of tools/js_codemod/convert_dashboard.mjs staying in sync
with frontend/js/dashboard.js -- catches someone hand-editing the generated
bridge block later and drifting from the census, which the Wave 6.4 manifest
note this plan closes out was explicitly trying to prevent.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_JS = ROOT / "frontend" / "js" / "dashboard.js"
INDEX_HTML = ROOT / "frontend" / "index.html"
CENSUS_REPORT = ROOT / "tools" / "js_codemod" / "census_report.json"
CONVERT_SCRIPT = ROOT / "tools" / "js_codemod" / "convert_dashboard.mjs"


def test_dashboard_js_loads_as_a_real_module():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert '<script type="module" src="js/dashboard.js' in html


def test_every_census_function_is_in_the_generated_window_bridge():
    census = json.loads(CENSUS_REPORT.read_text(encoding="utf-8"))
    js = DASHBOARD_JS.read_text(encoding="utf-8")
    marker = "Object.assign(window, {"
    assert marker in js
    bridge_block = js.split(marker, 1)[1].split("});", 1)[0]
    bridged_names = {n.strip() for n in bridge_block.replace("\n", " ").split(",") if n.strip()}
    missing = [name for name in census["functions"] if name not in bridged_names]
    assert missing == [], f"Functions missing from the window bridge: {missing}"


def test_generated_block_has_the_do_not_hand_edit_header():
    js = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "AUTO-GENERATED by tools/js_codemod/convert_dashboard.mjs" in js
    assert "do not hand-edit" in js


def test_codemod_check_mode_reports_no_drift():
    result = subprocess.run(
        ["node", str(CONVERT_SCRIPT), "--check"],
        cwd=ROOT, text=True, capture_output=True, timeout=60,
    )
    assert result.returncode == 0, (
        "dashboard.js has drifted from the codemod's expected output "
        f"(hand-edited generated block?):\n{result.stdout}{result.stderr}"
    )
```

- [ ] **Step 2: Run it**

```bash
python -m pytest tests/test_dashboard_js_module_bridge_regression.py -v
```

Expected: all 4 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_dashboard_js_module_bridge_regression.py
git commit -m "Add regression coverage for the dashboard.js codemod's generated output"
```

---

### Task 7: Full verification

- [ ] **Step 1: Fast tier**

```bash
pytest tests/ -m "not slow" --tb=short -q
```

Expected: all pass (no new failures).

- [ ] **Step 2: Full suite, parallelized**

```bash
pytest tests/ -n auto --tb=short -q
```

Expected: all pass (rerun serially without `-n` for any failure that looks like the documented Windows file-lock flake before treating it as real — see `documentation/CLAUDE.md`'s Testing Discipline section).

- [ ] **Step 3: Playwright spike + any existing e2e suite**

```bash
npx playwright test
```

Expected: all pass, including the new script-order spike from Task 2.

- [ ] **Step 4: Manual smoke pass**

Repeat Task 4 Step 2's manual browser checks once more against the fully-committed state (not just the intermediate state right after the script-tag flip), since Tasks 5–6 touched test files only, but it's cheap insurance before declaring the pass done.

---

### Task 8: Document completion and declare the multi-file-split non-goal

**Files:**
- Modify: `frontend/js/modules/phase3_module_manifest.js`

- [ ] **Step 1: Update the manifest**

Bump `schema` to `'phase3_frontend_module_manifest_v3'`, add `dashboard.js` to a completed-list, and add an explicit comment recording the deliberate non-goal:

```js
// v3 (docs/superpowers/plans/2026-08-06-dashboard-js-ast-module-conversion.md):
// dashboard.js itself is now a real ES module -- tools/js_codemod/census.mjs
// and convert_dashboard.mjs auto-generate its export list and window bridge
// (see tests/test_dashboard_js_module_bridge_regression.py), closing the gap
// this manifest's v2 note left open. It remains ONE file (~19,700 lines):
// splitting it into multiple cohesive modules by domain is a SEPARATE,
// NOT-yet-scheduled future pass -- this wave only made its public surface
// explicit and tool-verified, it did not decompose the file. That future
// split needs its own dependency-graph analysis (which of the ~760 functions
// call which others, to group them into non-circular modules) using the same
// tooling built here as a starting point, not a continuation of this wave.
```

- [ ] **Step 2: Run the fast tier once more**

```bash
pytest tests/ -m "not slow" --tb=short -q
```

- [ ] **Step 3: Commit**

```bash
git add frontend/js/modules/phase3_module_manifest.js
git commit -m "Document dashboard.js's ES module conversion; declare multi-file split as separate future work"
```

---

## Self-Review

**Spec coverage:** The user's ask ("dashboard.js needs its own AST-tooling-based pass, not a file-at-a-time conversion") is covered by Tasks 1–3 (the AST tooling itself: census + codemod, replacing what would otherwise be 760 hand-typed `export` edits and a hand-typed bridge list) and Task 4 (the actual conversion). Tasks 2 and 5 address the real behavioral-timing risk a naive script-tag flip would carry, rather than assuming it away. Tasks 6–8 close the loop so the conversion doesn't silently drift or get mistaken for a full decomposition.

**Placeholder scan:** No TBD/"add appropriate"/"similar to Task N" language; every step has runnable code or an exact command with an expected result.

**Type/name consistency:** `census_report.json`'s shape (`functions`, `variables`, `external_references`, `must_review`) is defined once in Task 1 and consumed with the same field names in Task 3's `convert_dashboard.mjs` and Task 6's regression test. `START_MARKER`'s exact text (`"// AUTO-GENERATED by tools/js_codemod/convert_dashboard.mjs"`) is defined in Task 3 and matched verbatim in Task 6's `test_generated_block_has_the_do_not_hand_edit_header`.
