# dashboard.js Split-and-Verify Codemod Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable, self-verifying codemod that splits declarations out of `frontend/js/dashboard.js` into a new ES module, and prove it by extracting the 28-declaration assets/liabilities/notes/529 cluster.

**Architecture:** Two Node tools under `tools/js_codemod/`. `find_clusters.mjs` is read-only analysis (call graph → connected components → JSON report). `extract_module.mjs` does the split: it uses the AST only to discover exact byte offsets, then splices the source string, so every untouched byte is preserved literally. It then proves correctness by reading its own generated module back off disk and reconstructing the original file from it. Neither tool edits `index.html`, the census, or the size ratchet — those stay separate, reviewable diffs.

**Tech Stack:** Node 26 (ESM, repo `package.json` has `"type": "module"`), `jscodeshift@^17.4.0` with the `babel` parser, pytest for the regression net, Playwright for e2e.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-10-dashboard-js-split-codemod-design.md`. Read it before Task 1.
- **Never use `node -e` one-liners for analysis in this repo.** Shell escaping mangles `\b` inside dynamically built `RegExp`, silently producing false negatives. Every analysis runs from a real `.mjs` file on disk, invoked with cwd = repo root (module resolution for `jscodeshift` depends on it).
- `frontend/js/dashboard.js` must never contain the `export` keyword — several tests `eval()` it as a plain script. Guarded by `tests/test_dashboard_js_module_bridge_regression.py::test_dashboard_js_never_contains_an_export_keyword`.
- New extracted modules are named `dashboard_decomp_<domain>.js` so existing tests that glob `dashboard_decomp_*.js` pick them up automatically.
- All transforms are byte-splices at AST-discovered offsets. Never re-print an AST with `.toSource()` — it reformats untouched code.
- Any failure is a hard abort with full rollback. No partial application.
- Commit after every task. Work happens in an isolated git worktree.

---

### Task 1: Cluster analysis tool

**Files:**
- Create: `tools/js_codemod/find_clusters.mjs`
- Create (generated, committed): `tools/js_codemod/clusters_report.json`

**Interfaces:**
- Consumes: nothing.
- Produces: `clusters_report.json` with shape
  `{ schema: "dashboard_clusters_v1", cutoff: number, total_functions: number, hubs: [{name, fan_in}], components: [[name, ...]] }`.
  `components` is sorted by length descending; each component's names are sorted.

- [ ] **Step 1: Write the tool**

Create `tools/js_codemod/find_clusters.mjs`:

```js
#!/usr/bin/env node
// Read-only domain-cluster analysis for frontend/js/dashboard.js.
// Rebuilds the internal call graph (which top-level function's body text
// references which other top-level function's name), strips high-fan-in hub
// functions, and runs connected components on what's left. The large remaining
// components are the candidate domain modules for
// tools/js_codemod/extract_module.mjs to pull out.
//
// This tool exists because the numbers in docs/superpowers/plans/
// 2026-08-06-dashboard-js-domain-module-split-SCOPE.md are already stale: that
// analysis ran BEFORE the shared-core extraction (dashboard_decomp_row_model.js)
// removed the 172 fan-in>=3 hub functions it was measuring. Every extraction
// changes the graph for the next one, so re-run this after each pass rather
// than trusting a previous report.
//
// Never modifies source. Usage: node tools/js_codemod/find_clusters.mjs [--cutoff N]
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import jscodeshift from "jscodeshift";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..", "..");
const DASHBOARD_PATH = path.join(ROOT, "frontend", "js", "dashboard.js");
const OUT_PATH = path.join(__dirname, "clusters_report.json");
const j = jscodeshift.withParser("babel");

const cutoffArg = process.argv.indexOf("--cutoff");
const CUTOFF = cutoffArg === -1 ? 3 : Number(process.argv[cutoffArg + 1]);

const source = fs.readFileSync(DASHBOARD_PATH, "utf8");
const root = j(source);

// Only top-level FUNCTIONS participate in the call graph. A `let x = function(){}`
// is a function too (that is how convert_dashboard.mjs rewrites the reassigned
// ones), so classify by initializer, not by declaration keyword.
const functions = new Map();
root.find(j.Program).forEach((programPath) => {
  for (const stmt of programPath.node.body) {
    if (stmt.type === "FunctionDeclaration" && stmt.id) {
      functions.set(stmt.id.name, { start: stmt.start, end: stmt.end });
    } else if (stmt.type === "VariableDeclaration") {
      for (const decl of stmt.declarations) {
        if (
          decl.id.type === "Identifier" &&
          decl.init &&
          (decl.init.type === "FunctionExpression" || decl.init.type === "ArrowFunctionExpression")
        ) {
          functions.set(decl.id.name, { start: stmt.start, end: stmt.end });
        }
      }
    }
  }
});

const names = [...functions.keys()];
const regexCache = new Map();
function regexFor(name) {
  if (!regexCache.has(name)) regexCache.set(name, new RegExp(`\\b${name}\\b`));
  return regexCache.get(name);
}

// Conservative superset of "calls": any word-boundary mention of another
// top-level function's name in this one's body text. That includes passing it
// as a callback and naming it inside a rendered template literal's inline
// onclick= handler -- both of which are real edges for "must these two ship
// together, or does splitting them need an explicit cross-module bridge".
const calls = new Map();
for (const [name, { start, end }] of functions) {
  const body = source.slice(start, end);
  const refs = new Set();
  for (const other of names) {
    if (other !== name && regexFor(other).test(body)) refs.add(other);
  }
  calls.set(name, refs);
}

const fanIn = new Map(names.map((n) => [n, 0]));
for (const [, refs] of calls) for (const other of refs) fanIn.set(other, fanIn.get(other) + 1);

const hubs = names.filter((n) => fanIn.get(n) >= CUTOFF);
const hubSet = new Set(hubs);
const remaining = names.filter((n) => !hubSet.has(n));
const remainingSet = new Set(remaining);

// Undirected connected components: a reference in EITHER direction binds two
// functions into the same component, because either direction becomes a
// cross-module edge if they are split apart.
const parent = new Map(remaining.map((n) => [n, n]));
function find(x) {
  while (parent.get(x) !== x) x = parent.get(x);
  return x;
}
function union(a, b) {
  const ra = find(a);
  const rb = find(b);
  if (ra !== rb) parent.set(ra, rb);
}
for (const n of remaining) {
  for (const other of calls.get(n)) if (remainingSet.has(other)) union(n, other);
}

const grouped = new Map();
for (const n of remaining) {
  const r = find(n);
  if (!grouped.has(r)) grouped.set(r, []);
  grouped.get(r).push(n);
}
const components = [...grouped.values()]
  .map((c) => c.sort())
  .sort((a, b) => b.length - a.length || a[0].localeCompare(b[0]));

const report = {
  schema: "dashboard_clusters_v1",
  cutoff: CUTOFF,
  total_functions: names.length,
  hubs: hubs.map((n) => ({ name: n, fan_in: fanIn.get(n) })).sort((a, b) => b.fan_in - a.fan_in),
  components,
};
fs.writeFileSync(OUT_PATH, JSON.stringify(report, null, 2) + "\n", "utf8");
console.log(
  `Wrote ${OUT_PATH}: ${names.length} functions, ${hubs.length} hubs (fan-in >= ${CUTOFF}), ` +
    `${components.length} components, largest ${components[0] ? components[0].length : 0}.`,
);
```

- [ ] **Step 2: Run it**

```bash
node tools/js_codemod/find_clusters.mjs
```

Expected: `Wrote .../clusters_report.json: 585 functions, 1 hubs (fan-in >= 3), 188 components, largest 80.`

(Only 1 hub — `renderMain` — because the row-model extraction already removed the rest.)

- [ ] **Step 3: Verify the target cluster is present and has exactly 24 members**

Create `tools/js_codemod/_verify_task1.mjs`:

```js
import fs from "node:fs";
const r = JSON.parse(fs.readFileSync("tools/js_codemod/clusters_report.json", "utf8"));
const target = r.components.find((c) => c.includes("renderLiabilitiesTable"));
console.log("size:", target.length);
console.log(JSON.stringify(target));
const expected = [
  "addEducation529Section", "addLiability", "addNoteReceivable", "addOtherAssetItem",
  "deleteLiability", "deleteNoteReceivable", "deleteOtherAssetItem", "liabilityFieldsForType",
  "noteReceivableRow", "noteReceivableSubsections", "otherAssetInputCell", "otherAssetRow",
  "otherAssetRows", "otherAssetSubsections", "otherAssetTypeCell", "renderAssetsSpecial",
  "renderHELOCInputsOnOtherPage", "renderHsaPolicyOnOtherAssets", "renderLiabilitiesTable",
  "renderNoteInterestTable", "renderNoteReceivableTable", "renderOtherAssetItemsTable",
  "setLiabilityType", "updateLiability",
];
const match = JSON.stringify(target) === JSON.stringify(expected);
console.log("MATCHES SPEC:", match);
if (!match) process.exit(1);
```

Run:

```bash
node tools/js_codemod/_verify_task1.mjs
```

Expected: `size: 24` then `MATCHES SPEC: true`, exit 0. If it does not match, STOP — the spec's cluster list is stale and must be re-agreed before continuing.

- [ ] **Step 4: Delete the throwaway verifier and commit**

```bash
rm tools/js_codemod/_verify_task1.mjs
git add tools/js_codemod/find_clusters.mjs tools/js_codemod/clusters_report.json
git commit -m "Add dashboard.js domain-cluster analysis tool"
```

---

### Task 2: Codemod validation phase

**Files:**
- Create: `tools/js_codemod/extract_module.mjs`
- Create: `tests/test_dashboard_extract_module_tool.py`

**Interfaces:**
- Consumes: `tools/js_codemod/census_report.json` (fields `reassigned_functions`, `functions`).
- Produces: CLI `node tools/js_codemod/extract_module.mjs --names <csv> --out <path> [--header-file <path>] [--check]`. Exit 0 on success, non-zero with a message on `stderr` for every abort. This task delivers phase 1 only: it validates and then exits 0 with `"validation passed"` without writing. Task 3 replaces that early exit with the real transform.

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_extract_module_tool.py`:

```python
"""Guards the safety rails of tools/js_codemod/extract_module.mjs.

That codemod moves top-level declarations out of frontend/js/dashboard.js into
a new ES module. Its correctness is enforced at runtime by a round-trip check
it performs on every invocation (see the tool's own header). What THIS file
guards is the set of refusals -- the cases where the tool must abort rather
than produce a plausible-looking but broken split. Those rails are the part
most likely to be quietly deleted by a future edit, because removing them makes
the tool "work" on inputs it should reject.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "js_codemod" / "extract_module.mjs"
DASHBOARD_JS = ROOT / "frontend" / "js" / "dashboard.js"
CENSUS_REPORT = ROOT / "tools" / "js_codemod" / "census_report.json"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", str(TOOL), *args], cwd=ROOT, text=True, capture_output=True, timeout=120
    )


def test_tool_exists():
    assert TOOL.is_file()


def test_unknown_name_is_refused():
    before = DASHBOARD_JS.read_bytes()
    result = _run("--names", "thisFunctionDoesNotExistAnywhere", "--out",
                  "frontend/js/dashboard_decomp_should_not_exist.js", "--check")
    assert result.returncode != 0, result.stdout + result.stderr
    assert "not a top-level declaration" in (result.stdout + result.stderr)
    assert DASHBOARD_JS.read_bytes() == before
    assert not (ROOT / "frontend" / "js" / "dashboard_decomp_should_not_exist.js").exists()


def test_reassigned_function_is_refused():
    """renderMain is monkey-patched by other leaf modules as a decorator chain,
    so it needs the reassignable-let + get/set accessor treatment that
    convert_dashboard.mjs applies inside dashboard.js. This tool does not
    reproduce that for a target module, so it must refuse rather than emit a
    plain `export function renderMain` that silently breaks the chain."""
    census = json.loads(CENSUS_REPORT.read_text(encoding="utf-8"))
    assert "renderMain" in census["reassigned_functions"]
    before = DASHBOARD_JS.read_bytes()
    result = _run("--names", "renderMain", "--out",
                  "frontend/js/dashboard_decomp_should_not_exist.js", "--check")
    assert result.returncode != 0, result.stdout + result.stderr
    assert "reassigned" in (result.stdout + result.stderr).lower()
    assert DASHBOARD_JS.read_bytes() == before


def test_duplicate_name_is_refused():
    result = _run("--names", "renderLiabilitiesTable,renderLiabilitiesTable", "--out",
                  "frontend/js/dashboard_decomp_should_not_exist.js", "--check")
    assert result.returncode != 0, result.stdout + result.stderr
    assert "duplicate" in (result.stdout + result.stderr).lower()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_dashboard_extract_module_tool.py -v
```

Expected: FAIL — `test_tool_exists` asserts False because `extract_module.mjs` does not exist yet.

- [ ] **Step 3: Write the validation phase**

Create `tools/js_codemod/extract_module.mjs`:

```js
#!/usr/bin/env node
// Splits top-level declarations out of frontend/js/dashboard.js into a new ES
// module, and PROVES it moved them without altering them.
//
// Why a tool instead of hand-editing: the predecessor pass
// (docs/superpowers/plans/2026-08-06-dashboard-js-ast-module-conversion.md)
// established that hand-editing this file at scale is not a responsible
// approach for production financial software. The holdings leaf was moved by
// hand because it was one self-contained block; the remaining ~10-15 domain
// clusters are not.
//
// Transform strategy (same as convert_dashboard.mjs and extract_core.mjs): use
// the AST purely to DISCOVER exact character offsets, then splice the source
// STRING at those offsets. Asking a printer (recast/jscodeshift .toSource()) to
// re-emit the file would reformat untouched code.
//
// The verification is the point of this tool. After writing the new module it
// reads that module BACK OFF DISK, recovers each moved declaration's text from
// the written file's own AST, and reconstructs the original dashboard.js from
// (post-removal dashboard.js + those recovered texts). Deriving the texts from
// the OUTPUT rather than from the in-memory original is what makes this a real
// check instead of a tautology: it is what catches a mangled `export ` prefix,
// a reordering bug, a wrong byte range, or a newline-handling error.
//
// Usage:
//   node tools/js_codemod/extract_module.mjs --names a,b,c --out frontend/js/dashboard_decomp_x.js --header-file hdr.txt
//   node tools/js_codemod/extract_module.mjs --names a,b,c --out ... --check   (dry run, writes nothing to the real paths)
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import jscodeshift from "jscodeshift";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..", "..");
const DASHBOARD_PATH = path.join(ROOT, "frontend", "js", "dashboard.js");
const CENSUS_PATH = path.join(__dirname, "census_report.json");
const JS_DIR = path.join(ROOT, "frontend", "js");
const INDEX_HTML_PATH = path.join(ROOT, "frontend", "index.html");
const BRIDGE_MARKER = "// AUTO-GENERATED by tools/js_codemod/convert_dashboard.mjs";
const j = jscodeshift.withParser("babel");

function die(message) {
  console.error("ABORT: " + message);
  process.exit(1);
}

function parseArgs(argv) {
  const out = { names: null, out: null, headerFile: null, check: false };
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === "--names") out.names = argv[++i];
    else if (argv[i] === "--out") out.out = argv[++i];
    else if (argv[i] === "--header-file") out.headerFile = argv[++i];
    else if (argv[i] === "--check") out.check = true;
    else die(`unknown argument ${argv[i]}`);
  }
  if (!out.names) die("--names is required");
  if (!out.out) die("--out is required");
  return out;
}

// One entry per top-level statement that declares something. `names` holds
// EVERY name the statement declares, because `let a = 1, b = 2;` is a single
// splice unit -- moving `a` necessarily moves `b`.
function collectTopLevelStatements(source) {
  const root = j(source);
  const statements = [];
  root.find(j.Program).forEach((programPath) => {
    for (const stmt of programPath.node.body) {
      if (stmt.type === "FunctionDeclaration" && stmt.id) {
        statements.push({
          names: [stmt.id.name], start: stmt.start, end: stmt.end, kind: "function",
        });
      } else if (stmt.type === "VariableDeclaration") {
        const names = [];
        let everyInitIsFunction = stmt.declarations.length > 0;
        for (const decl of stmt.declarations) {
          if (decl.id.type !== "Identifier") { everyInitIsFunction = false; continue; }
          names.push(decl.id.name);
          const isFn = decl.init &&
            (decl.init.type === "FunctionExpression" || decl.init.type === "ArrowFunctionExpression");
          if (!isFn) everyInitIsFunction = false;
        }
        if (names.length) {
          statements.push({
            names, start: stmt.start, end: stmt.end,
            kind: everyInitIsFunction ? "function" : "variable",
            declKind: stmt.kind,
          });
        }
      }
    }
  });
  return statements;
}

function stripBridge(source) {
  const idx = source.indexOf(BRIDGE_MARKER);
  return idx === -1 ? source : source.slice(0, idx);
}

function otherFileSources(outAbs) {
  const sources = [];
  for (const entry of fs.readdirSync(JS_DIR)) {
    const full = path.join(JS_DIR, entry);
    if (!entry.endsWith(".js")) continue;
    if (full === DASHBOARD_PATH || full === outAbs) continue;
    sources.push([path.relative(ROOT, full), fs.readFileSync(full, "utf8")]);
  }
  sources.push(["frontend/index.html", fs.readFileSync(INDEX_HTML_PATH, "utf8")]);
  return sources;
}

function validate(source, requested, outAbs) {
  const census = JSON.parse(fs.readFileSync(CENSUS_PATH, "utf8"));
  const statements = collectTopLevelStatements(source);
  const byName = new Map();
  for (const st of statements) for (const n of st.names) byName.set(n, st);

  const seen = new Set();
  const duplicates = requested.filter((n) => (seen.has(n) ? true : (seen.add(n), false)));
  if (duplicates.length) die(`duplicate name(s) in --names: ${[...new Set(duplicates)].join(", ")}`);

  const missing = requested.filter((n) => !byName.has(n));
  if (missing.length) {
    die(`not a top-level declaration in dashboard.js: ${missing.join(", ")}`);
  }

  const reassigned = requested.filter((n) => census.reassigned_functions.includes(n));
  if (reassigned.length) {
    die(
      `refusing to move reassigned function(s): ${reassigned.join(", ")}. ` +
        "Other leaf modules monkey-patch these as a decorator chain, which needs the " +
        "reassignable-let + get/set accessor treatment convert_dashboard.mjs applies " +
        "inside dashboard.js. This tool does not reproduce that for a target module.",
    );
  }

  const requestedSet = new Set(requested);
  const chosen = [...new Set(requested.map((n) => byName.get(n)))];
  for (const st of chosen) {
    const strays = st.names.filter((n) => !requestedSet.has(n));
    if (strays.length) {
      die(
        `${st.names.filter((n) => requestedSet.has(n)).join(", ")} shares one declaration ` +
          `statement with ${strays.join(", ")}, which was not requested. Splicing is ` +
          "per-statement, so request all of them or none.",
      );
    }
  }

  // Variable safety rule. Functions are EXPECTED to still be called from
  // dashboard.js -- the window bridge exists for exactly that. Variables are
  // not: a moved variable becomes module-private, and dashboard.js's generated
  // bridge cannot expose a binding that no longer lives in dashboard.js. So a
  // variable may only move if nothing else anywhere still reads it.
  let afterPreview = source;
  for (const st of [...chosen].sort((a, b) => b.start - a.start)) {
    afterPreview = afterPreview.slice(0, st.start) + afterPreview.slice(st.end);
  }
  const afterNoBridge = stripBridge(afterPreview);
  const others = otherFileSources(outAbs);
  for (const st of chosen) {
    if (st.kind !== "variable") continue;
    for (const name of st.names) {
      const re = new RegExp(`\\b${name}\\b`);
      if (re.test(afterNoBridge)) {
        die(
          `${name} is still referenced in dashboard.js after removal, so it is shared ` +
            "state and must stay behind. Leave it out of --names; the generated window " +
            "bridge will expose it to the new module.",
        );
      }
      for (const [label, text] of others) {
        if (re.test(text)) {
          die(`${name} is referenced by ${label}, so it is shared state and must stay behind.`);
        }
      }
    }
  }
  return chosen.sort((a, b) => a.start - b.start);
}

function main() {
  const args = parseArgs(process.argv);
  const requested = args.names.split(",").map((s) => s.trim()).filter(Boolean);
  const outAbs = path.resolve(ROOT, args.out);
  const source = fs.readFileSync(DASHBOARD_PATH, "utf8");
  const chosen = validate(source, requested, outAbs);
  console.log(`validation passed: ${chosen.length} statement(s), ${requested.length} name(s).`);
}

main();
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_dashboard_extract_module_tool.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/js_codemod/extract_module.mjs tests/test_dashboard_extract_module_tool.py
git commit -m "Add extract_module codemod: validation and refusal rails"
```

---

### Task 3: Codemod transform and round-trip verification

**Files:**
- Modify: `tools/js_codemod/extract_module.mjs` (replace `main()`, add transform/verify helpers)
- Modify: `tests/test_dashboard_extract_module_tool.py` (add the dry-run end-to-end test)

**Interfaces:**
- Consumes: `validate()` and `collectTopLevelStatements()` from Task 2.
- Produces: on success, writes `<out>` and a rewritten `dashboard.js`; prints `EXTRACTED <n> declaration(s)` plus the follow-up command list. With `--check`, writes nothing to either real path and prints `CHECK PASSED`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dashboard_extract_module_tool.py`:

```python
def test_check_mode_round_trips_real_functions_without_writing():
    """End-to-end proof that the transform is lossless, run against whatever
    functions dashboard.js actually has right now.

    The two names are picked from the census at runtime rather than hardcoded,
    so this test keeps working after future extraction passes remove any
    particular function. It exercises the full pipeline -- splice out, write the
    module, read the module back, reconstruct the original from it -- and the
    tool exits non-zero if the reconstruction is not byte-identical.
    """
    census = json.loads(CENSUS_REPORT.read_text(encoding="utf-8"))
    reassigned = set(census["reassigned_functions"])
    candidates = [n for n in census["functions"] if n not in reassigned][:2]
    assert len(candidates) == 2

    before = DASHBOARD_JS.read_bytes()
    out_rel = "frontend/js/dashboard_decomp_check_only_tmp.js"
    result = _run("--names", ",".join(candidates), "--out", out_rel, "--check")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "CHECK PASSED" in result.stdout
    assert DASHBOARD_JS.read_bytes() == before, "check mode must not modify dashboard.js"
    assert not (ROOT / out_rel).exists(), "check mode must not leave its output file behind"


def test_check_mode_leaves_no_temp_files():
    tmp_leftovers = list((ROOT / "frontend" / "js").glob("*check-tmp*"))
    assert tmp_leftovers == [], f"temp files left behind: {tmp_leftovers}"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_dashboard_extract_module_tool.py::test_check_mode_round_trips_real_functions_without_writing -v
```

Expected: FAIL — the tool prints `validation passed` and never prints `CHECK PASSED`.

- [ ] **Step 3: Implement the transform and verification**

In `tools/js_codemod/extract_module.mjs`, add these functions immediately above `main()`:

```js
// Cut each chosen statement out, consuming the single trailing newline that
// follows it so the removal does not leave a blank line behind. Records
// exactly how many bytes each removal took, which the reconstruction below
// needs to walk the post-removal string.
function removeStatements(source, chosen) {
  let after = source;
  for (const st of [...chosen].sort((a, b) => b.start - a.start)) {
    let end = st.end;
    if (source[end] === "\n") end += 1;
    after = after.slice(0, st.start) + after.slice(end);
  }
  const moved = chosen.map((st) => {
    const consumedNewline = source[st.end] === "\n";
    return {
      names: st.names,
      start: st.start,
      text: source.slice(st.start, st.end),
      consumedNewline,
      removedLen: st.end - st.start + (consumedNewline ? 1 : 0),
    };
  });
  return { after, moved };
}

function buildModule(headerText, moved) {
  const bodies = moved.map((m) => `export ${m.text}`).join("\n\n");
  const allNames = moved.flatMap((m) => m.names);
  const bridge =
    "\n\n// Every export above is also re-attached to window: dashboard.js calls these\n" +
    "// as bare globals, and this file's own rendered HTML uses inline\n" +
    '// onclick="..." handlers, which always resolve through window regardless of\n' +
    "// module scoping. New code should prefer `import` from this module; this\n" +
    "// bridge exists only for callers that cannot move to import in the same pass.\n" +
    "Object.assign(window, {\n" +
    allNames.map((n) => `  ${n},`).join("\n") +
    "\n});\n";
  return headerText.replace(/\s*$/, "\n") + "\n" + bodies + bridge;
}

// Recover each moved declaration's text from the WRITTEN module file's own AST.
// Returns a Map from the joined name key to the declaration source text with
// the `export ` prefix removed.
function recoverFromModule(moduleSource) {
  const root = j(moduleSource);
  const recovered = new Map();
  root.find(j.Program).forEach((programPath) => {
    for (const stmt of programPath.node.body) {
      if (stmt.type !== "ExportNamedDeclaration" || !stmt.declaration) continue;
      const decl = stmt.declaration;
      const names = [];
      if (decl.type === "FunctionDeclaration" && decl.id) names.push(decl.id.name);
      else if (decl.type === "VariableDeclaration") {
        for (const d of decl.declarations) if (d.id.type === "Identifier") names.push(d.id.name);
      }
      if (names.length) recovered.set(names.join(","), moduleSource.slice(decl.start, decl.end));
    }
  });
  return recovered;
}

// Rebuild the original file from (post-removal source + texts recovered from
// the written module). Walks ascending, translating each original offset into
// its position in the shortened string by subtracting everything removed
// before it.
// Returns null (rather than exiting) if the module is missing a declaration,
// so the caller can roll back before reporting.
function reconstruct(after, moved, recovered) {
  let out = "";
  let cursor = 0;
  let removedSoFar = 0;
  for (const m of [...moved].sort((a, b) => a.start - b.start)) {
    const key = m.names.join(",");
    if (!recovered.has(key)) return null;
    const cut = m.start - removedSoFar;
    out += after.slice(cursor, cut);
    out += recovered.get(key) + (m.consumedNewline ? "\n" : "");
    cursor = cut;
    removedSoFar += m.removedLen;
  }
  out += after.slice(cursor);
  return out;
}

function topLevelNames(source) {
  return new Set(collectTopLevelStatements(source).flatMap((st) => st.names));
}

function nodeSyntaxCheck(filePath) {
  // The repo's package.json sets "type": "module", so `node --check` parses
  // .js files here with the ESM goal and accepts `export`. Verified against
  // both dashboard.js (export-free) and dashboard_decomp_row_model.js.
  try {
    execFileSync(process.execPath, ["--check", filePath], { stdio: "pipe" });
    return null;
  } catch (err) {
    return String(err.stderr || err.message);
  }
}
```

Then replace `main()` with:

```js
function main() {
  const args = parseArgs(process.argv);
  const requested = args.names.split(",").map((s) => s.trim()).filter(Boolean);
  const outAbs = path.resolve(ROOT, args.out);
  const source = fs.readFileSync(DASHBOARD_PATH, "utf8");

  const chosen = validate(source, requested, outAbs);
  const { after, moved } = removeStatements(source, chosen);

  const headerText = args.headerFile
    ? fs.readFileSync(path.resolve(ROOT, args.headerFile), "utf8")
    : "// Extracted from dashboard.js by tools/js_codemod/extract_module.mjs.";
  const moduleSource = buildModule(headerText, moved);

  // In check mode the module still has to hit the disk -- the round-trip
  // verification is only meaningful if it reads back what was actually
  // written -- but it goes to a sibling temp path and dashboard.js is never
  // touched.
  const modulePath = args.check ? outAbs + ".check-tmp" : outAbs;
  fs.writeFileSync(modulePath, moduleSource, "utf8");
  if (!args.check) fs.writeFileSync(DASHBOARD_PATH, after, "utf8");

  const rollback = (message) => {
    if (!args.check) fs.writeFileSync(DASHBOARD_PATH, source, "utf8");
    try { fs.unlinkSync(modulePath); } catch { /* already gone */ }
    die(message);
  };

  const writtenModule = fs.readFileSync(modulePath, "utf8");
  const recovered = recoverFromModule(writtenModule);

  const rebuilt = reconstruct(after, moved, recovered);
  if (rebuilt === null) {
    rollback("the written module is missing one of the declarations it should contain");
  }
  if (rebuilt !== source) {
    let at = 0;
    while (at < rebuilt.length && at < source.length && rebuilt[at] === source[at]) at++;
    rollback(
      "round-trip verification FAILED: reconstructing dashboard.js from the written " +
        `module does not reproduce the original. First difference at byte ${at}: ` +
        `expected ${JSON.stringify(source.slice(at, at + 60))} ` +
        `but got ${JSON.stringify(rebuilt.slice(at, at + 60))}`,
    );
  }

  const movedNames = new Set(moved.flatMap((m) => m.names));
  const expectedDashboard = new Set([...topLevelNames(source)].filter((n) => !movedNames.has(n)));
  const actualDashboard = topLevelNames(after);
  const lostFromDashboard = [...expectedDashboard].filter((n) => !actualDashboard.has(n));
  const gainedInDashboard = [...actualDashboard].filter((n) => !expectedDashboard.has(n));
  if (lostFromDashboard.length || gainedInDashboard.length) {
    rollback(
      `inventory verification FAILED for dashboard.js: unexpectedly removed ` +
        `[${lostFromDashboard.join(", ")}], unexpectedly present [${gainedInDashboard.join(", ")}]`,
    );
  }
  const actualModule = new Set(
    [...recovered.keys()].flatMap((k) => k.split(",")),
  );
  const missingFromModule = [...movedNames].filter((n) => !actualModule.has(n));
  const extraInModule = [...actualModule].filter((n) => !movedNames.has(n));
  if (missingFromModule.length || extraInModule.length) {
    rollback(
      `inventory verification FAILED for the new module: missing ` +
        `[${missingFromModule.join(", ")}], unexpected [${extraInModule.join(", ")}]`,
    );
  }

  const moduleErr = nodeSyntaxCheck(modulePath);
  if (moduleErr) rollback("the generated module is not valid JavaScript:\n" + moduleErr);
  if (!args.check) {
    const dashErr = nodeSyntaxCheck(DASHBOARD_PATH);
    if (dashErr) rollback("the rewritten dashboard.js is not valid JavaScript:\n" + dashErr);
  }

  if (args.check) {
    fs.unlinkSync(modulePath);
    console.log(
      `CHECK PASSED: ${moved.length} statement(s) / ${movedNames.size} name(s) would move ` +
        `to ${args.out}. Nothing was written.`,
    );
    return;
  }

  console.log(`EXTRACTED ${movedNames.size} declaration(s) to ${args.out}`);
  console.log(`dashboard.js is now ${after.split("\n").length} lines.`);
  console.log("\nRequired follow-up (this tool deliberately does NOT do these):");
  console.log(`  1. Add <script type="module" src="js/${path.basename(args.out)}?v=1"></script>`);
  console.log("     to frontend/index.html IMMEDIATELY BEFORE the dashboard.js tag.");
  console.log("  2. node tools/js_codemod/census.mjs");
  console.log("  3. node tools/js_codemod/convert_dashboard.mjs");
  console.log("  4. Add a manifest entry to frontend/js/modules/phase3_module_manifest.js");
  console.log("  5. Lower DASHBOARD_JS_MAX_LINES in tests/test_frontend_size_ratchet.py");
}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_dashboard_extract_module_tool.py -v
```

Expected: 6 passed. In particular `test_check_mode_round_trips_real_functions_without_writing` proves the splice → write → read-back → reconstruct cycle is byte-lossless.

- [ ] **Step 5: Prove the round-trip check actually catches corruption**

This confirms the verification is not vacuous. Temporarily break `buildModule` by changing:

```js
  const bodies = moved.map((m) => `export ${m.text}`).join("\n\n");
```

to:

```js
  const bodies = moved.map((m) => `export ${m.text.replace(/\s+$/, "")}`).join("\n\n");
```

Then run:

```bash
python -m pytest tests/test_dashboard_extract_module_tool.py::test_check_mode_round_trips_real_functions_without_writing -v
```

Expected: FAIL, with the tool's stderr containing `round-trip verification FAILED`. **Revert the edit** and re-run to confirm 6 passed again. If the test PASSES with the corruption in place, the verification is broken — stop and fix it before continuing.

- [ ] **Step 6: Commit**

```bash
git add tools/js_codemod/extract_module.mjs tests/test_dashboard_extract_module_tool.py
git commit -m "extract_module: byte-splice transform with round-trip and inventory verification"
```

---

### Task 4: Extract the assets/liabilities/notes/529 cluster

**Files:**
- Create: `frontend/js/dashboard_decomp_assets_other.js` (generated)
- Modify: `frontend/js/dashboard.js` (28 declarations removed, bridge regenerated)
- Modify: `frontend/index.html:104-105` (new script tag)
- Modify: `tools/js_codemod/census_report.json` (regenerated)

**Interfaces:**
- Consumes: `extract_module.mjs` from Task 3.
- Produces: `window.<name>` for all 24 functions and 4 consts listed below, installed before `dashboard.js` evaluates.

- [ ] **Step 1: Write the module header file**

Create `tools/js_codemod/headers/assets_other.txt`:

```
/* Assets & Protection: liabilities, note receivables, 529 education accounts,
   and the "other assets" item table -- extracted from dashboard.js by
   tools/js_codemod/extract_module.mjs.

   First domain cluster of the Wave 6.4 domain-module split (see
   docs/superpowers/specs/2026-08-10-dashboard-js-split-codemod-design.md),
   following the shared-core extraction that produced
   dashboard_decomp_row_model.js. Selected as a connected component of
   dashboard.js's internal call graph (tools/js_codemod/find_clusters.mjs),
   stable across fan-in cutoffs 3 through 8.

   Loaded BEFORE dashboard.js, in the same position as
   dashboard_decomp_row_model.js -- not after it with the other leaves.
   dashboard.js ends its module body with a queueMicrotask() that schedules the
   real boot work, and a microtask checkpoint runs after that script's
   evaluation, so it can fire before a LATER module script has evaluated. This
   module's own top level is nothing but declarations and one Object.assign, so
   it has no evaluation-time dependency on dashboard.js and is safe to run
   first.

   The four constant tables (LIABILITY_LABELS, LIABILITY_TYPES,
   LIABILITY_TYPE_FIELDS, OTHER_ASSET_TYPES) moved with the code: they are read
   by this cluster and by nothing else anywhere in the repo, so leaving them in
   dashboard.js would have stranded them behind four generated window accessors
   that exist to serve exactly one other file.

   What this module still reaches back into dashboard.js for, all through the
   generated window bridge and all verified present before this pass landed:
   the function renderMain (a reassigned monkey-patch chain, exposed via a get
   accessor, so a bare call here gets the live decorated implementation), the
   read-only state rows/searchText/planSource/dirty, and the writable state
   activeStep/lastBuildOk (both `let`, both with set accessors). */
```

- [ ] **Step 2: Dry-run the extraction**

```bash
node tools/js_codemod/extract_module.mjs --names addEducation529Section,addLiability,addNoteReceivable,addOtherAssetItem,deleteLiability,deleteNoteReceivable,deleteOtherAssetItem,liabilityFieldsForType,noteReceivableRow,noteReceivableSubsections,otherAssetInputCell,otherAssetRow,otherAssetRows,otherAssetSubsections,otherAssetTypeCell,renderAssetsSpecial,renderHELOCInputsOnOtherPage,renderHsaPolicyOnOtherAssets,renderLiabilitiesTable,renderNoteInterestTable,renderNoteReceivableTable,renderOtherAssetItemsTable,setLiabilityType,updateLiability,LIABILITY_LABELS,LIABILITY_TYPES,LIABILITY_TYPE_FIELDS,OTHER_ASSET_TYPES --out frontend/js/dashboard_decomp_assets_other.js --header-file tools/js_codemod/headers/assets_other.txt --check
```

Expected: `CHECK PASSED: 28 statement(s) / 28 name(s) would move to frontend/js/dashboard_decomp_assets_other.js. Nothing was written.`

If it instead aborts on a variable safety rule, STOP: a const is shared after all, and the spec's premise needs revisiting.

- [ ] **Step 3: Run it for real**

Same command, with `--check` removed.

Expected: `EXTRACTED 28 declaration(s) to frontend/js/dashboard_decomp_assets_other.js`, a new dashboard.js line count several hundred lines below the current 15,304 (record the exact number — Task 5 Step 2 needs it), and the 5-step follow-up list.

Note: between this step and Step 5, dashboard.js's *stale* generated bridge still lists the 24 moved function names as object shorthand. That is not a syntax error, and at runtime it resolves through `window` to the new module's exports because the new module loads first — but do not stop here. Step 5 regenerates the bridge so it no longer claims to own them.

- [ ] **Step 4: Add the script tag before dashboard.js**

In `frontend/index.html`, the current lines 104-105 are:

```html
<script type="module" src="js/dashboard_decomp_row_model.js?v=1"></script>
<script type="module" src="js/dashboard.js?v=46"></script>
```

Change to:

```html
<script type="module" src="js/dashboard_decomp_row_model.js?v=1"></script>
<script type="module" src="js/dashboard_decomp_assets_other.js?v=1"></script>
<script type="module" src="js/dashboard.js?v=47"></script>
```

(The `?v=46` → `?v=47` bump busts the browser cache for the now-shrunken dashboard.js.)

- [ ] **Step 5: Regenerate the census and the bridge, in that order**

```bash
node tools/js_codemod/census.mjs
```

Expected: a line reporting roughly `557 functions (2 reassigned externally), ... variables (... referenced externally)` — 28 fewer functions than before.

```bash
node tools/js_codemod/convert_dashboard.mjs
```

Expected: it rewrites dashboard.js's generated bridge block, dropping the 24 moved function names.

- [ ] **Step 6: Verify both files parse and the moved names are gone from dashboard.js**

```bash
node --check frontend/js/dashboard.js && node --check frontend/js/dashboard_decomp_assets_other.js && echo BOTH_PARSE
```

Expected: `BOTH_PARSE`

```bash
grep -c "renderLiabilitiesTable\|OTHER_ASSET_TYPES" frontend/js/dashboard.js
```

Expected: `0`

- [ ] **Step 7: Run the bridge and census regression tests**

```bash
python -m pytest tests/test_dashboard_js_module_bridge_regression.py tests/test_dashboard_codemod_census_report_regression.py -v
```

Expected: all pass. `test_census_report_committed_copy_matches_a_fresh_run` passing confirms the committed census matches the new tree; `test_codemod_check_mode_reports_no_drift` passing confirms the bridge was regenerated rather than hand-edited.

- [ ] **Step 8: Commit**

```bash
git add frontend/js/dashboard_decomp_assets_other.js frontend/js/dashboard.js frontend/index.html tools/js_codemod/census_report.json tools/js_codemod/headers/assets_other.txt
git commit -m "Extract assets/liabilities/notes/529 cluster into its own ES module"
```

---

### Task 5: Manifest entry, size ratchet, and the full regression net

**Files:**
- Modify: `frontend/js/modules/phase3_module_manifest.js:60-79`
- Modify: `tests/test_frontend_size_ratchet.py:63`
- Modify: `tools/js_codemod/clusters_report.json` (regenerated)

**Interfaces:**
- Consumes: the landed extraction from Task 4.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add the v5 manifest entry**

In `frontend/js/modules/phase3_module_manifest.js`, immediately before the line `loaded_by:'dashboard_source_truth_banners.js',`, insert:

```js
    // v5 (docs/superpowers/specs/2026-08-10-dashboard-js-split-codemod-design.md):
    // first DOMAIN cluster extracted, and the first one done by a general
    // tool rather than by hand. Built tools/js_codemod/extract_module.mjs: it
    // discovers byte offsets via the AST, splices the source string, then
    // proves the move was lossless by reading its own generated module back
    // off disk and reconstructing the original dashboard.js from it (deriving
    // the text from the OUTPUT is what makes that a real check and not a
    // tautology). Moved the 24-function assets cluster (liabilities, note
    // receivables, 529s, other-asset items) plus the 4 constant tables only
    // that cluster reads into frontend/js/dashboard_decomp_assets_other.js.
    // Loaded BEFORE dashboard.js like row_model.js: dashboard.js schedules its
    // boot work with queueMicrotask, whose checkpoint can fire before a later
    // module script evaluates, so a leaf loaded after it is not guaranteed to
    // have installed its window bridge in time. ~13 domain clusters remain;
    // re-run tools/js_codemod/find_clusters.mjs before each, since every
    // extraction changes the graph for the next one.
```

- [ ] **Step 2: Measure the new dashboard.js and update the ratchet**

```bash
python -c "print(len(open('frontend/js/dashboard.js',encoding='utf-8').read().splitlines()))"
```

Note the number `N`. In `tests/test_frontend_size_ratchet.py`, replace the line `DASHBOARD_JS_MAX_LINES = 15_308` with `DASHBOARD_JS_MAX_LINES = N` (formatted with an underscore separator, e.g. `15_042`), and add this comment immediately above it, below the existing comment block:

```python
# 2026-08-10: lowered from 15,308 -- first domain-cluster extraction
# (docs/superpowers/specs/2026-08-10-dashboard-js-split-codemod-design.md):
# tools/js_codemod/extract_module.mjs moved the 24-function assets cluster
# (liabilities, note receivables, 529s, other-asset items) plus the 4 constant
# tables only it reads into frontend/js/dashboard_decomp_assets_other.js.
```

- [ ] **Step 3: Regenerate the cluster report against the shrunken file**

```bash
node tools/js_codemod/find_clusters.mjs
```

Expected: `557 functions`, and the 24-member assets component is gone.

- [ ] **Step 4: Run the full regression net**

```bash
python -m pytest tests/test_frontend_size_ratchet.py tests/test_dashboard_codemod_census_report_regression.py tests/test_dashboard_js_module_bridge_regression.py tests/test_dashboard_startup_race_and_script_order.py tests/test_dashboard_dead_code_sweep_regression.py tests/test_roadmap_steps_1_11_static_regression.py tests/test_dashboard_extract_module_tool.py -v
```

Expected: all pass. If `test_ratchet_is_not_slack` fails, `N` in Step 2 was wrong — re-measure.

- [ ] **Step 5: Run the Playwright script-order spec**

```bash
npx playwright test tests/e2e/script-order-spike.spec.js
```

Expected: pass. If Playwright browsers are not installed, run `npx playwright install chromium` first.

- [ ] **Step 6: Commit**

```bash
git add frontend/js/modules/phase3_module_manifest.js tests/test_frontend_size_ratchet.py tools/js_codemod/clusters_report.json
git commit -m "Document the assets extraction in the manifest and lower the size ratchet"
```

---

### Task 6: Live browser verification

**Files:** none modified (verification only; any fix found here is its own commit).

**Interfaces:**
- Consumes: the landed extraction.
- Produces: evidence that the four affected UI panels work.

- [ ] **Step 1: Start the app**

Use the `run` skill, or the project's documented start command. Open the dashboard in the Browser pane.

- [ ] **Step 2: Check the console is clean on load**

Use `read_console_messages` with `onlyErrors: true`.

Expected: no `ReferenceError`. A `ReferenceError: <name> is not defined` naming any moved declaration means the script tag is in the wrong position or the census/bridge regeneration in Task 4 Step 5 did not run.

- [ ] **Step 3: Exercise each affected panel**

Navigate to Assets & Protection. For each of Liabilities, Note Receivables, 529 education accounts, and Other Assets: add a row, edit a field in it, then delete it. Re-check `read_console_messages` after each panel.

Expected: each table re-renders after every action, and the console stays free of errors. This specifically exercises the cross-module edges the design identified: `renderMain()` (the reassigned decorator chain), the `activeStep`/`lastBuildOk` writes, and the `rows`/`dirty`/`planSource`/`searchText` reads.

- [ ] **Step 4: Screenshot as evidence**

`computer` with `action: "screenshot"` on the Liabilities panel with a row present.

- [ ] **Step 5: Report**

State plainly which panels were exercised and what the console showed. If anything failed, report the failure with its console output rather than describing the work as complete.

---

## Notes for the executor

- If Task 4 Step 2's dry run aborts, do not "work around" it by dropping names from `--names` until it passes. The refusal encodes a real constraint; re-read the message and the spec's dependency section first.
- `census.mjs` must run *after* the new module file exists on disk — it scans `frontend/js/*.js` for cross-file references, and that is how the four moved consts stop being reported as dashboard.js's problem.
- The size ratchet is a ratchet: it only moves down. Never raise it to make a diff pass.
