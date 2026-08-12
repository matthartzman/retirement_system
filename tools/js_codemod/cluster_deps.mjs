#!/usr/bin/env node
// Reports what a candidate cluster would still reach back into dashboard.js
// for, BEFORE it is extracted.
//
// Why this is separate from finish_extraction.mjs: that tool verifies the
// bridge surface after the fact, which is the safety net. This one answers the
// question you have earlier, while writing the new module's header comment --
// "what does this cluster depend on, and which of those does it WRITE?".
// Doing that by hand means a throwaway script every pass (it was written and
// deleted twice before becoming this file), and doing it by eye means a header
// comment that is plausible rather than true.
//
// The write/read split is the part worth knowing up front. A moved function
// that assigns to a dashboard.js `let` only works because
// convert_dashboard.mjs emits a set accessor for it; module code is strict, so
// the assignment throws at call time otherwise. If this report shows a written
// binding that is `const` in dashboard.js, the cluster cannot move as-is and
// you want to know that before running the extraction, not after.
//
// Read-only: never modifies anything.
//
// PARSER CHOICE -- @babel/parser directly, not jscodeshift, for the same
// CRLF/LF offset reason documented at the top of extract_module.mjs.
//
// Usage:
//   node tools/js_codemod/cluster_deps.mjs --names a,b,c
//   node tools/js_codemod/cluster_deps.mjs --component 2   (read from clusters_report.json)
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as babelParser from "@babel/parser";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..", "..");
const DASHBOARD_PATH = path.join(ROOT, "frontend", "js", "dashboard.js");
const CLUSTERS_PATH = path.join(__dirname, "clusters_report.json");
const CENSUS_PATH = path.join(__dirname, "census_report.json");

function die(message) {
  console.error("ABORT: " + message);
  process.exit(1);
}

function parseProgram(source) {
  return babelParser.parse(source, { sourceType: "module" }).program;
}

function walk(node, visit) {
  if (!node || typeof node !== "object") return;
  if (Array.isArray(node)) {
    for (const child of node) walk(child, visit);
    return;
  }
  if (typeof node.type !== "string") return;
  visit(node);
  for (const key of Object.keys(node)) {
    if (key === "loc" || key === "leadingComments" || key === "trailingComments") continue;
    walk(node[key], visit);
  }
}

function parseArgs(argv) {
  const out = { names: null, component: null };
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === "--names") out.names = argv[++i];
    else if (argv[i] === "--component") out.component = Number(argv[++i]);
    else die(`unknown argument ${argv[i]}`);
  }
  if (out.names === null && out.component === null) {
    die("one of --names or --component is required");
  }
  return out;
}

// Every top-level declaration in dashboard.js, with its span and kind.
function topLevelDeclarations(source) {
  const decls = new Map();
  for (const stmt of parseProgram(source).body) {
    if (stmt.type === "FunctionDeclaration" && stmt.id) {
      decls.set(stmt.id.name, { start: stmt.start, end: stmt.end, kind: "function" });
    } else if (stmt.type === "VariableDeclaration") {
      for (const d of stmt.declarations) {
        if (d.id.type !== "Identifier") continue;
        const isFn =
          d.init &&
          (d.init.type === "FunctionExpression" || d.init.type === "ArrowFunctionExpression");
        decls.set(d.id.name, {
          start: stmt.start,
          end: stmt.end,
          kind: isFn ? "function" : `${stmt.kind} variable`,
        });
      }
    }
  }
  return decls;
}

const args = parseArgs(process.argv);
let requested;
if (args.names !== null) {
  requested = args.names.split(",").map((s) => s.trim()).filter(Boolean);
} else {
  const report = JSON.parse(fs.readFileSync(CLUSTERS_PATH, "utf8"));
  const component = report.components[args.component];
  if (!component) die(`clusters_report.json has no component ${args.component}`);
  requested = component;
}

const source = fs.readFileSync(DASHBOARD_PATH, "utf8");
const decls = topLevelDeclarations(source);
const movedSet = new Set(requested);

const missing = requested.filter((n) => !decls.has(n));
if (missing.length) die(`not top-level in dashboard.js: ${missing.join(", ")}`);

// Parse ONLY the cluster's own text, so references are the cluster's, not the
// whole file's. Wrapped in a program of its own; each declaration is already a
// complete top-level statement so they concatenate cleanly.
const clusterText = requested.map((n) => source.slice(decls.get(n).start, decls.get(n).end)).join("\n");

const skip = new Set();
walk(parseProgram(clusterText), (node) => {
  if (node.type === "MemberExpression" && !node.computed && node.property) skip.add(node.property);
  if (node.type === "ObjectProperty" && !node.computed && node.key) skip.add(node.key);
  if (node.type === "ObjectMethod" && !node.computed && node.key) skip.add(node.key);
});
const refs = new Set();
const writes = new Set();
walk(parseProgram(clusterText), (node) => {
  if (node.type === "Identifier" && !skip.has(node)) refs.add(node.name);
  if (node.type === "AssignmentExpression" && node.left && node.left.type === "Identifier") {
    writes.add(node.left.name);
  }
  if (node.type === "UpdateExpression" && node.argument && node.argument.type === "Identifier") {
    writes.add(node.argument.name);
  }
});

const needed = [...refs].filter((n) => decls.has(n) && !movedSet.has(n)).sort();
const fns = needed.filter((n) => decls.get(n).kind === "function");
const vars = needed.filter((n) => decls.get(n).kind !== "function");

const census = JSON.parse(fs.readFileSync(CENSUS_PATH, "utf8"));
const reassigned = new Set(census.reassigned_functions || []);

console.log(`Cluster: ${requested.length} declaration(s).`);
console.log(`\nFunctions it still calls in dashboard.js (${fns.length}):`);
for (const n of fns) {
  console.log(`  ${n}${reassigned.has(n) ? "   [REASSIGNED -- get accessor, monkey-patch chain]" : ""}`);
}
console.log(`\nState it reads or writes in dashboard.js (${vars.length}):`);
const blockers = [];
for (const n of vars) {
  const kind = decls.get(n).kind;
  const written = writes.has(n);
  if (written && kind.startsWith("const")) blockers.push(n);
  console.log(`  ${n} [${kind}] ${written ? "WRITTEN" : "read-only"}`);
}

if (blockers.length) {
  console.log(
    `\nBLOCKER: the cluster assigns to ${blockers.join(", ")}, which ${
      blockers.length === 1 ? "is" : "are"
    } const in dashboard.js. A const gets a get-only accessor, so those ` +
      "assignments would throw at call time. Resolve before extracting.",
  );
  process.exit(1);
}
console.log(
  `\nAll ${vars.filter((n) => writes.has(n)).length} written binding(s) are non-const, so ` +
    "convert_dashboard.mjs will emit set accessors for them.",
);
