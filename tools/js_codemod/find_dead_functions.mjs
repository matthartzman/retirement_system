#!/usr/bin/env node
// Preliminary dead-code sweep for dashboard.js, run before the AST-based
// module-conversion pass (docs/superpowers/plans/2026-08-06-dashboard-js-ast-module-conversion.md)
// so we don't bother exporting/bridging functions nothing calls. A function is
// a dead-code CANDIDATE only if it has ZERO references anywhere: not from
// dashboard.js's own JS body (excluding its own declaration), not from
// dashboard.js's own generated-HTML inline event handlers, not as a bare
// identifier or inline handler in any other frontend/js/*.js file or
// frontend/*.html, and not referenced by name in tests/. This is deliberately
// conservative -- read-only, never deletes anything itself.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import jscodeshift from "jscodeshift";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..", "..");
const j = jscodeshift.withParser("babel");

const DASHBOARD_PATH = path.join(ROOT, "frontend", "js", "dashboard.js");
const FRONTEND_DIR = path.join(ROOT, "frontend");
const JS_DIR = path.join(FRONTEND_DIR, "js");
const TESTS_DIR = path.join(ROOT, "tests");

function collectTopLevelFunctionNames(source) {
  const root = j(source);
  const names = new Set();
  root.find(j.Program).forEach((programPath) => {
    for (const stmt of programPath.node.body) {
      if (stmt.type === "FunctionDeclaration" && stmt.id) names.add(stmt.id.name);
    }
  });
  return names;
}

function countBareReferencesInJs(names, source) {
  const root = j(source);
  const counts = new Map();
  root.find(j.Identifier).forEach((idPath) => {
    const name = idPath.node.name;
    if (!names.has(name)) return;
    const parent = idPath.parent.node;
    if (
      (parent.type === "FunctionDeclaration" && parent.id === idPath.node) ||
      (parent.type === "MemberExpression" && parent.property === idPath.node && !parent.computed) ||
      (parent.type === "Property" && parent.key === idPath.node && !parent.computed)
    ) {
      return; // declaration site or a plain `.name` / `{name: ...}` key, not a reference
    }
    counts.set(name, (counts.get(name) || 0) + 1);
  });
  return counts;
}

function countStringOccurrences(names, text) {
  const counts = new Map();
  for (const name of names) {
    // Word-boundary text search: catches onclick="foo(...)" strings (which are
    // plain string literals inside dashboard.js's own template-literal HTML,
    // not real JS Identifier nodes an AST walk over dashboard.js's own AST
    // would find as "code" -- they're just characters inside a string).
    const re = new RegExp(`\\b${name}\\b`, "g");
    const matches = text.match(re);
    if (matches) counts.set(name, (counts.get(name) || 0) + matches.length);
  }
  return counts;
}

function addCounts(target, source) {
  for (const [name, n] of source) {
    target.set(name, (target.get(name) || 0) + n);
  }
}

function main() {
  const dashboardSource = fs.readFileSync(DASHBOARD_PATH, "utf8");
  const functionNames = collectTopLevelFunctionNames(dashboardSource);
  console.log(`Found ${functionNames.size} top-level function declarations in dashboard.js.`);

  const totalRefs = new Map();

  // 1. Internal AST references within dashboard.js itself (excluding each
  //    function's own declaration site) -- catches real JS-to-JS calls.
  addCounts(totalRefs, countBareReferencesInJs(functionNames, dashboardSource));

  // 2. Raw text search over dashboard.js's own source -- catches references
  //    inside its own template-literal-generated HTML strings (onclick="foo()"
  //    is plain text to the parser, not an Identifier node), MINUS the
  //    contribution already counted by #1's identifier-based JS-code count.
  //    Subtracting is unsafe (double counting is fine here -- this is a
  //    presence check, not an exact reference count), so just OR the results:
  //    if either method found >=1, treat as referenced.
  const dashboardTextRefs = countStringOccurrences(functionNames, dashboardSource);
  for (const [name, n] of dashboardTextRefs) {
    totalRefs.set(name, Math.max(totalRefs.get(name) || 0, n));
  }

  // 3. Every other frontend/js/*.js file: bare identifiers + raw text (for
  //    their own onclick="..." strings calling into dashboard.js).
  for (const entry of fs.readdirSync(JS_DIR)) {
    const full = path.join(JS_DIR, entry);
    if (full === DASHBOARD_PATH || !entry.endsWith(".js")) continue;
    const source = fs.readFileSync(full, "utf8");
    addCounts(totalRefs, countStringOccurrences(functionNames, source));
  }

  // 4. Every frontend/*.html file (inline scripts + onclick attributes are
  //    both plain text at this level of scrutiny).
  for (const entry of fs.readdirSync(FRONTEND_DIR)) {
    if (!entry.endsWith(".html")) continue;
    const source = fs.readFileSync(path.join(FRONTEND_DIR, entry), "utf8");
    addCounts(totalRefs, countStringOccurrences(functionNames, source));
  }

  // 5. tests/ -- a function referenced by name in a test is not "used" in the
  //    running app, but flag it separately as "referenced_only_in_tests" so a
  //    human reviews it rather than the tool silently deleting test coverage
  //    for something that might be intentionally still-called dead-simple code.
  const referencedInTests = new Set();
  function walkTests(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "__pycache__") continue;
        walkTests(full);
      } else if (entry.name.endsWith(".py")) {
        const source = fs.readFileSync(full, "utf8");
        for (const name of functionNames) {
          if (new RegExp(`\\b${name}\\b`).test(source)) referencedInTests.add(name);
        }
      }
    }
  }
  walkTests(TESTS_DIR);

  const deadCandidates = [];
  const zeroAppReferencesButInTests = [];
  for (const name of functionNames) {
    const refCount = totalRefs.get(name) || 0;
    if (refCount === 0) {
      if (referencedInTests.has(name)) {
        zeroAppReferencesButInTests.push(name);
      } else {
        deadCandidates.push(name);
      }
    }
  }
  deadCandidates.sort();
  zeroAppReferencesButInTests.sort();

  const report = {
    schema: "dead_function_candidates_v1",
    total_top_level_functions: functionNames.size,
    dead_candidates: deadCandidates,
    zero_app_references_but_referenced_in_tests: zeroAppReferencesButInTests,
  };
  const outPath = path.join(__dirname, "dead_function_candidates.json");
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2) + "\n", "utf8");
  console.log(
    `${deadCandidates.length} dead-code candidate(s), ` +
      `${zeroAppReferencesButInTests.length} referenced only in tests/ (needs human review either way). ` +
      `Wrote ${outPath}.`,
  );
}

main();
