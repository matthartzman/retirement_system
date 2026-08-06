#!/usr/bin/env node
// Census tool for the dashboard.js module-conversion plan (docs/superpowers/plans/
// 2026-08-06-dashboard-js-ast-module-conversion.md). Read-only: never modifies source.
// Usage: node tools/js_codemod/census.mjs
//
// v2 (2026-08-06): the original design assumed top-level functions are only
// ever CALLED externally (safe for a one-time Object.assign value copy) and
// top-level variables are only ever READ externally (safe for a get-only
// accessor). A first run found that's false: dashboard_source_truth_banners.js
// and dashboard_batch_assumption_edit.js reassign `renderMain`/`showStepHelp`
// as a decorator-chain monkey-patch (already-converted ES modules CAN write a
// classic script's top-level `let`/function bindings -- they share the same
// global declarative environment, same as another classic script would), and
// several already-converted leaf modules WRITE (not just read) many of
// dashboard.js's top-level state variables (buildOverlay*, activeStep, etc.).
// So this census now explicitly separates "ever externally reassigned" from
// "only ever called/read" for both functions and variables, since those two
// groups need different bridge shapes (see convert_dashboard.mjs).
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
      if (stmt.type === "FunctionDeclaration" && stmt.id) {
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
    if (
      (parent.type === "FunctionDeclaration" && parent.id === idPath.node) ||
      (parent.type === "VariableDeclarator" && parent.id === idPath.node) ||
      (parent.type === "MemberExpression" && parent.property === idPath.node && !parent.computed) ||
      (parent.type === "Property" && parent.key === idPath.node && !parent.computed) ||
      (parent.type === "FunctionDeclaration" && parent.params.includes(idPath.node))
    ) {
      return;
    }

    let kind = "read";
    if (parent.type === "CallExpression" && parent.callee === idPath.node) kind = "call";
    if (parent.type === "AssignmentExpression" && parent.left === idPath.node) kind = "assign";

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
  const html = fs.readFileSync(INDEX_HTML_PATH, "utf8");
  const inlineScriptRe = /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g;
  let m;
  while ((m = inlineScriptRe.exec(html))) {
    externalReferences.push(
      ...findExternalReferences(allNames, m[1], "frontend/index.html (inline)"),
    );
  }

  const functionSet = new Set(functions);
  const variableSet = new Set(variables);

  const reassignedFunctions = [...new Set(
    externalReferences.filter((r) => r.kind === "assign" && functionSet.has(r.name)).map((r) => r.name),
  )].sort();

  const externallyReferencedVariables = [...new Set(
    externalReferences.filter((r) => variableSet.has(r.name)).map((r) => r.name),
  )].sort();

  const report = {
    schema: "dashboard_census_v2",
    functions,
    variables,
    external_references: externalReferences,
    // Functions reassigned (not just called) by another file -- a monkey-patch
    // decorator chain. These need `let name = function(){...}` (reassignable)
    // instead of `function name(){}`, plus a get+set window accessor instead
    // of a one-time Object.assign value copy, so dashboard.js's own internal
    // calls see the same live, externally-wrapped implementation.
    reassigned_functions: reassignedFunctions,
    // Variables read OR written externally -- all get a get+set accessor
    // (uniform; no need to distinguish read-only vs read-write, since a
    // get+set accessor correctly serves both).
    externally_referenced_variables: externallyReferencedVariables,
  };

  const outPath = path.join(__dirname, "census_report.json");
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2) + "\n", "utf8");
  console.log(
    `Wrote ${outPath}: ${functions.length} functions (${reassignedFunctions.length} reassigned externally), ` +
      `${variables.length} variables (${externallyReferencedVariables.length} referenced externally), ` +
      `${externalReferences.length} total external references.`,
  );
}

main();
