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
// Uses @babel/parser directly, NOT jscodeshift: jscodeshift's node.start/.end
// are only valid byte offsets when the source is CRLF, and this tool slices
// function bodies by offset to build the reference graph. On an LF checkout
// (Linux/CI) jscodeshift offsets are wrong for every function, which would
// silently produce a meaningless clustering rather than an obvious error. See
// the parser note in extract_module.mjs for the measurement.
//
// Never modifies source. Usage: node tools/js_codemod/find_clusters.mjs [--cutoff N]
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as babelParser from "@babel/parser";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..", "..");
const DASHBOARD_PATH = path.join(ROOT, "frontend", "js", "dashboard.js");
const OUT_PATH = path.join(__dirname, "clusters_report.json");

const cutoffArg = process.argv.indexOf("--cutoff");
const CUTOFF = cutoffArg === -1 ? 3 : Number(process.argv[cutoffArg + 1]);

const source = fs.readFileSync(DASHBOARD_PATH, "utf8");
const program = babelParser.parse(source, { sourceType: "module" }).program;

// Only top-level FUNCTIONS participate in the call graph. A `let x = function(){}`
// is a function too (that is how convert_dashboard.mjs rewrites the reassigned
// ones), so classify by initializer, not by declaration keyword.
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
