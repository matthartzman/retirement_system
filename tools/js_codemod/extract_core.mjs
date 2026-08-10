#!/usr/bin/env node
// Extracts dashboard.js's shared "row model + app shell" hub functions
// (fan-in >= 3 in the internal call graph, per
// docs/superpowers/plans/2026-08-06-dashboard-js-domain-module-split-SCOPE.md)
// into frontend/js/dashboard_decomp_row_model.js as a real ES module.
// Named dashboard_decomp_*.js (not dashboard_row_model.js) deliberately: several
// existing tests already glob JS_DIR.glob("dashboard_decomp_*.js") to build a
// multi-file "full picture" read/smoke-exec source list (see
// tests/test_active_input_recursion_guard_regression.py's
// _dashboard_smoke_sources()) -- matching that convention means those tests
// pick this file up with zero changes.
//
// PARSER CHOICE -- load-bearing, do not "simplify" this back to jscodeshift.
// This tool slices function bodies out of the source by byte offset and
// rewrites dashboard.js with the result. jscodeshift.withParser("babel")
// reports node.start/node.end as though every newline were two characters, so
// its offsets are only correct on a CRLF source. Measured against this repo's
// own dashboard.js: CRLF -> all 584 top-level functions slice correctly;
// the identical file LF-normalised -> ALL 584 slice wrong, each "function"
// being garbage taken from the middle of unrelated code. This repo has
// core.autocrlf=true and .gitattributes pins only *.csv and
// input/plan_data_manifest.json to eol=lf -- nothing covers *.js -- so a
// Windows checkout is CRLF and a Linux/macOS/CI checkout is LF. The shipped
// dashboard_decomp_row_model.js extraction is correct only because this tool
// was run on Windows; re-running it on Linux under jscodeshift would silently
// corrupt both output files. recast's node.loc is not a fallback either: it is
// null for a declaration nested inside an `export`. Plain @babel/parser reports
// true offsets under both line endings. Guarded by
// tests/frontend/js_codemod_parser_offsets.test.mjs. Same choice as
// extract_module.mjs and find_clusters.mjs.
//
// Usage: node tools/js_codemod/extract_core.mjs
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as babelParser from "@babel/parser";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..", "..");
const DASHBOARD_PATH = path.join(ROOT, "frontend", "js", "dashboard.js");
const OUT_PATH = path.join(ROOT, "frontend", "js", "dashboard_decomp_row_model.js");

const source = fs.readFileSync(DASHBOARD_PATH, "utf8");
const program = babelParser.parse(source, { sourceType: "module" }).program;

const functions = new Map();
for (const stmt of program.body) {
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

const names = [...functions.keys()];
const regexCache = new Map();
function regexFor(name) {
  if (!regexCache.has(name)) regexCache.set(name, new RegExp(`\\b${name}\\b`));
  return regexCache.get(name);
}
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

const CUTOFF = 3;
const hubNames = [...fanIn.entries()].filter(([, c]) => c >= CUTOFF).map(([n]) => n);
const REASSIGNED = new Set(["renderMain", "showStepHelp"]);
const extractNames = hubNames.filter((n) => !REASSIGNED.has(n)).sort();

console.log(`Extracting ${extractNames.length} hub functions (fan-in >= ${CUTOFF}, excluding reassigned).`);

const byPosDesc = extractNames.map((n) => ({ name: n, ...functions.get(n) })).sort((a, b) => b.start - a.start);
const byPosAsc = [...byPosDesc].sort((a, b) => a.start - b.start);
const extractedBodies = byPosAsc.map((f) => ({ name: f.name, text: source.slice(f.start, f.end) }));

let dashboardSource = source;
for (const f of byPosDesc) {
  let end = f.end;
  if (source[end] === "\n") end += 1;
  dashboardSource = dashboardSource.slice(0, f.start) + dashboardSource.slice(end);
}

const header = `// ── Row-model + app-shell core (Wave 6.4 domain-module-split, shared-core extraction) ──
// Extracted from dashboard.js verbatim: the ${extractNames.length} functions every
// other domain page's render logic is built on top of (section/norm/valOf/
// isEditable/fieldHtml/rowsForStep/humanLabel/... plus app-shell orchestration
// like api/showMessage/setStep/loadAll/saveAll). Selected as the fan-in >= ${CUTOFF}
// hub set from the internal call-graph analysis in
// docs/superpowers/plans/2026-08-06-dashboard-js-domain-module-split-SCOPE.md.
// renderMain and showStepHelp stay in dashboard.js: other leaf modules
// reassign them as a monkey-patch decorator chain, which this pass does not
// touch. A real ES module (type="module"), same export+window-bridge pattern
// as every other Wave 6.4 leaf. Named dashboard_decomp_*.js (not
// dashboard_row_model.js) so existing tests that glob that pattern for a
// multi-file "full dashboard source" read/smoke-exec pick it up automatically.
`;

const body = extractedBodies
  .map(({ text }) => {
    if (/^async function /.test(text)) return "export " + text;
    if (/^function /.test(text)) return "export " + text;
    if (/^let /.test(text)) return "export " + text;
    return text;
  })
  .join("\n\n");

const bridge = `

Object.assign(window, {
${extractNames.map((n) => `  ${n},`).join("\n")}
});
`;

fs.writeFileSync(OUT_PATH, header + "\n" + body + bridge, "utf8");
fs.writeFileSync(DASHBOARD_PATH, dashboardSource, "utf8");

console.log(`Wrote ${OUT_PATH} (${extractNames.length} functions).`);
console.log(`Rewrote ${DASHBOARD_PATH} (removed extracted functions).`);
