#!/usr/bin/env node
// Dead-code sweep for the dashboard front end. Originally written as a
// pre-flight for the AST module-conversion pass
// (docs/superpowers/plans/2026-08-06-dashboard-js-ast-module-conversion.md) so
// we didn't bother exporting/bridging functions nothing calls.
//
// A function is a dead-code CANDIDATE only if it has ZERO *real* references
// anywhere: not from its own file's JS body (excluding its declaration site),
// not from any file's generated-HTML inline event handlers, not as a bare
// identifier in any other frontend/js/*.js file or frontend/*.html, and not
// referenced by name in tests/. Read-only -- it never deletes anything itself.
//
// ── Two corrections, 2026-08-11 ────────────────────────────────────────────
//
// 1. REBINDINGS ARE NOT REFERENCES. The previous version reported 0 candidates
//    out of 559 functions, and that number was vacuous rather than clean: it
//    text-searched each file for `\bname\b`, and every file ends with an
//    `Object.assign(window, { ...every function it declares... })` bridge
//    block. That block named every function, so every function scored >=1
//    reference and the tool could never report anything. It was structurally
//    incapable of failing. Proven by deleting the genuinely-dead
//    renderTaxonomyBudgetTable: its orphaned helper loadAnnualizedActuals was
//    left with nothing but a declaration and a bridge entry, and the tool
//    still said zero.
//
//    So before counting, we MASK the ranges that only *rebind* a name rather
//    than use it: the object literal in `Object.assign(window, {...})`, whole
//    `import ... from "..."` declarations, and specifier-only exports
//    (`export { a, b }`). A use inside a masked region is by definition not a
//    call site. Masking replaces the range with spaces so every byte offset
//    outside it is preserved.
//
// 2. THE DECOMP MODULES WERE NEVER SCANNED FOR DECLARATIONS. Only dashboard.js
//    was mined for function declarations; frontend/js/dashboard_decomp_*.js
//    were read as reference *sources* only, so a dead function living in one
//    of them could never become a candidate. They are now declaration sources
//    too (unwrapping `export function foo()`).
//
// Parser note: this tool reads node.start/node.end, so per
// tests/frontend/js_codemod_parser_offsets.test.mjs it MUST parse with plain
// @babel/parser and MUST NOT use jscodeshift, whose offsets are wrong on any
// LF checkout (Linux/macOS/CI).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as babelParser from "@babel/parser";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..", "..");

const FRONTEND_DIR = path.join(ROOT, "frontend");
const JS_DIR = path.join(FRONTEND_DIR, "js");
const TESTS_DIR = path.join(ROOT, "tests");

const DASHBOARD_PATH = path.join(JS_DIR, "dashboard.js");

/** Files mined for function DECLARATIONS: the monolith plus its extractions. */
function declarationSourceFiles() {
  const files = [DASHBOARD_PATH];
  for (const entry of fs.readdirSync(JS_DIR).sort()) {
    if (entry.startsWith("dashboard_decomp_") && entry.endsWith(".js")) {
      files.push(path.join(JS_DIR, entry));
    }
  }
  return files;
}

function parse(source) {
  return babelParser.parse(source, {
    sourceType: "module",
    allowReturnOutsideFunction: true,
    errorRecovery: true,
  }).program;
}

/** Depth-first walk over every AST node, handing each one its parent. */
function walk(node, visit, parent = null) {
  if (node === null || typeof node !== "object") return;
  if (Array.isArray(node)) {
    for (const child of node) walk(child, visit, parent);
    return;
  }
  if (typeof node.type !== "string") return;
  visit(node, parent);
  for (const key of Object.keys(node)) {
    if (key === "loc" || key === "leadingComments" || key === "trailingComments") continue;
    walk(node[key], visit, node);
  }
}

/**
 * Top-level function declarations, unwrapping `export function foo() {}`.
 * Returns Map<name, Set<relative file path>>.
 */
function collectTopLevelFunctionNames(program, relPath, into) {
  for (const raw of program.body) {
    const stmt =
      raw.type === "ExportNamedDeclaration" && raw.declaration ? raw.declaration : raw;
    if (stmt.type === "FunctionDeclaration" && stmt.id) {
      if (!into.has(stmt.id.name)) into.set(stmt.id.name, new Set());
      into.get(stmt.id.name).add(relPath);
    }
  }
  return into;
}

/**
 * Character ranges that REBIND a name rather than use it. See note 1 up top.
 * Returned as [start, end) pairs.
 */
function rebindingRanges(program) {
  const ranges = [];
  walk(program, (node) => {
    // import { foo } from "./x.js"  /  import foo from "./x.js"
    if (node.type === "ImportDeclaration") {
      ranges.push([node.start, node.end]);
      return;
    }
    // export { foo, bar }  /  export { foo } from "./x.js"  /  export * from ...
    // (but NOT `export function foo() {}`, which has a .declaration and whose
    // body is real code we must still scan.)
    if (node.type === "ExportNamedDeclaration" && !node.declaration) {
      ranges.push([node.start, node.end]);
      return;
    }
    if (node.type === "ExportAllDeclaration") {
      ranges.push([node.start, node.end]);
      return;
    }
    // Object.assign(window, { foo, bar })  -- mask each object-literal arg.
    if (node.type === "CallExpression") {
      const callee = node.callee;
      const isObjectAssign =
        callee.type === "MemberExpression" &&
        !callee.computed &&
        callee.object.type === "Identifier" &&
        callee.object.name === "Object" &&
        callee.property.type === "Identifier" &&
        callee.property.name === "assign";
      if (!isObjectAssign) return;
      const targetsWindow = node.arguments.some(
        (a) => a.type === "Identifier" && a.name === "window",
      );
      if (!targetsWindow) return;
      for (const arg of node.arguments) {
        if (arg.type === "ObjectExpression") ranges.push([arg.start, arg.end]);
      }
    }
  });
  return ranges;
}

/**
 * The name identifier in `function foo() {}` -- a definition, not a use. The
 * AST pass already skips these, but the raw-text pass cannot see the
 * difference, so every function used to match its own declaration and score a
 * phantom reference. That alone kept the report empty even before the bridge
 * block was accounted for.
 */
function declarationIdRanges(program) {
  const ranges = [];
  walk(program, (node) => {
    if (node.type === "FunctionDeclaration" && node.id) {
      ranges.push([node.id.start, node.id.end]);
    }
  });
  return ranges;
}

/** Replace each range with equal-length spaces, preserving all other offsets. */
function maskRanges(source, ranges) {
  if (!ranges.length) return source;
  const chars = [...source];
  for (const [start, end] of ranges) {
    for (let i = start; i < end && i < chars.length; i += 1) {
      if (chars[i] !== "\n" && chars[i] !== "\r") chars[i] = " ";
    }
  }
  return chars.join("");
}

function inAnyRange(pos, ranges) {
  return ranges.some(([start, end]) => pos >= start && pos < end);
}

/** Real JS identifier references, skipping declaration sites and rebindings. */
function countBareReferencesInJs(names, program, rebindings) {
  const counts = new Map();
  walk(program, (node, parent) => {
    if (node.type !== "Identifier") return;
    if (!names.has(node.name)) return;
    if (inAnyRange(node.start, rebindings)) return;
    if (parent) {
      if (parent.type === "FunctionDeclaration" && parent.id === node) return;
      if (parent.type === "MemberExpression" && parent.property === node && !parent.computed) {
        return;
      }
      if (
        (parent.type === "Property" || parent.type === "ObjectProperty") &&
        parent.key === node &&
        !parent.computed
      ) {
        return;
      }
    }
    counts.set(node.name, (counts.get(node.name) || 0) + 1);
  });
  return counts;
}

/**
 * Word-boundary text search. Catches onclick="foo(...)" handlers, which live
 * inside template-literal HTML strings and so are plain characters to the
 * parser, not Identifier nodes an AST walk would ever see.
 */
function countStringOccurrences(names, text) {
  const counts = new Map();
  for (const name of names) {
    const matches = text.match(new RegExp(`\\b${name}\\b`, "g"));
    if (matches) counts.set(name, (counts.get(name) || 0) + matches.length);
  }
  return counts;
}

function addCounts(target, source) {
  for (const [name, n] of source) target.set(name, (target.get(name) || 0) + n);
}

function orCounts(target, source) {
  for (const [name, n] of source) target.set(name, Math.max(target.get(name) || 0, n));
}

function main() {
  const declFiles = declarationSourceFiles();

  // Every frontend JS file, parsed once, with its rebinding ranges masked out.
  // Recursive: frontend/js/modules/ holds real reference sources too, and a
  // function called only from there must not read as dead.
  const jsFiles = new Map();
  const jsPaths = [];
  (function collectJs(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) =>
      a.name.localeCompare(b.name),
    )) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "node_modules") continue;
        collectJs(full);
      } else if (entry.name.endsWith(".js")) {
        jsPaths.push(full);
      }
    }
  })(JS_DIR);
  for (const full of jsPaths) {
    const source = fs.readFileSync(full, "utf8");
    let program = null;
    let ranges = [];
    let maskOnly = [];
    try {
      program = parse(source);
      ranges = rebindingRanges(program);
      maskOnly = declarationIdRanges(program);
    } catch (err) {
      console.warn(`  ! could not parse ${entry}: ${err.message} (text search only)`);
    }
    jsFiles.set(full, {
      source,
      program,
      ranges,
      masked: maskRanges(source, [...ranges, ...maskOnly]),
    });
  }

  // 0. Declarations, from dashboard.js AND the decomp modules.
  const declaredIn = new Map();
  for (const full of declFiles) {
    const info = jsFiles.get(full);
    if (!info || !info.program) continue;
    collectTopLevelFunctionNames(info.program, path.relative(ROOT, full), declaredIn);
  }
  const functionNames = new Set(declaredIn.keys());
  console.log(
    `Found ${functionNames.size} top-level function declarations across ` +
      `${declFiles.length} file(s).`,
  );

  const totalRefs = new Map();

  for (const info of jsFiles.values()) {
    // 1. Real JS-to-JS identifier references (declaration sites and rebindings
    //    already excluded).
    if (info.program) {
      addCounts(totalRefs, countBareReferencesInJs(functionNames, info.program, info.ranges));
    }
    // 2. Raw text over the MASKED source -- catches inline handlers inside
    //    template-literal HTML. OR rather than add: double counting is fine
    //    here (this is a presence check, not an exact reference count), but
    //    double counting a name that appears zero times must stay zero.
    orCounts(totalRefs, countStringOccurrences(functionNames, info.masked));
  }

  // 3. frontend/*.html -- inline scripts and onclick attributes are both plain
  //    text at this level of scrutiny, and neither can contain a bridge block.
  for (const entry of fs.readdirSync(FRONTEND_DIR)) {
    if (!entry.endsWith(".html")) continue;
    const source = fs.readFileSync(path.join(FRONTEND_DIR, entry), "utf8");
    addCounts(totalRefs, countStringOccurrences(functionNames, source));
  }

  // 4. The Python side calls JS functions BY NAME through pywebview's
  //    evaluate_js(), e.g. src/desktop_api.py builds
  //    `typeof updateBuildProgress==='function'&&updateBuildProgress({...})`.
  //    Those are real call sites that live entirely outside frontend/, and
  //    missing them reported updateBuildProgress as dead when desktop mode
  //    calls it on every build tick. Scan the Python sources as text.
  for (const dir of [path.join(ROOT, "src"), ROOT]) {
    const walk = (d, depth) => {
      let entries;
      try {
        entries = fs.readdirSync(d, { withFileTypes: true });
      } catch {
        return;
      }
      for (const entry of entries) {
        const full = path.join(d, entry.name);
        if (entry.isDirectory()) {
          if (depth === 0) continue; // only recurse under src/
          if (["__pycache__", "node_modules", ".git", "frontend", "tests"].includes(entry.name)) {
            continue;
          }
          walk(full, depth);
          continue;
        }
        if (!entry.name.endsWith(".py")) continue;
        addCounts(totalRefs, countStringOccurrences(functionNames, fs.readFileSync(full, "utf8")));
      }
    };
    walk(dir, dir === ROOT ? 0 : 1);
  }

  // 5. tests/ -- a name referenced only by a test is not "used" in the running
  //    app, so flag it separately for human review rather than letting the
  //    tool imply it is safe to delete along with its coverage.
  //
  //    Two kinds of file in tests/ MENTION names without using them, and both
  //    would otherwise launder dead code into the "covered by tests" bucket:
  //      - the sweep ratchet itself, which pins the known-dead backlog BY NAME
  //        (a self-reference loop: every name it records stops being reported,
  //        which is what it exists to prevent), and
  //      - tests/fixtures/*.json snapshots of frontend source, which are data
  //        captures rather than callers.
  const TEST_FILES_THAT_ONLY_MENTION_NAMES = new Set([
    "test_dashboard_dead_code_sweep_regression.py",
  ]);
  const referencedInTests = new Set();

  //    tools/*.py belongs in this same bucket, not the "referenced" one.
  //    tools/run_regression.py (which CI runs) is a smoke checker full of
  //    `check("... defined", "function foo(" in dash)` assertions. Those
  //    MENTION a name without calling it, so counting them as references would
  //    hide real dead code -- but ignoring them entirely means deleting the
  //    function silently breaks CI, which is exactly what happened to
  //    buildWithDesktopProgress. Surfacing them for human review is the only
  //    correct answer.
  for (const entry of fs.readdirSync(path.join(ROOT, "tools"))) {
    if (!entry.endsWith(".py")) continue;
    const source = fs.readFileSync(path.join(ROOT, "tools", entry), "utf8");
    for (const name of functionNames) {
      if (new RegExp(`\\b${name}\\b`).test(source)) referencedInTests.add(name);
    }
  }

  (function walkTests(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "__pycache__" || entry.name === "node_modules") continue;
        if (entry.name === "fixtures") continue;
        walkTests(full);
        continue;
      }
      if (TEST_FILES_THAT_ONLY_MENTION_NAMES.has(entry.name)) continue;
      if (!/\.(py|mjs|js)$/.test(entry.name)) continue;
      const source = fs.readFileSync(full, "utf8");
      for (const name of functionNames) {
        if (new RegExp(`\\b${name}\\b`).test(source)) referencedInTests.add(name);
      }
    }
  })(TESTS_DIR);

  const deadCandidates = [];
  const zeroAppReferencesButInTests = [];
  for (const name of functionNames) {
    if ((totalRefs.get(name) || 0) !== 0) continue;
    (referencedInTests.has(name) ? zeroAppReferencesButInTests : deadCandidates).push(name);
  }
  deadCandidates.sort();
  zeroAppReferencesButInTests.sort();

  const declaredInReport = {};
  for (const name of [...deadCandidates, ...zeroAppReferencesButInTests]) {
    declaredInReport[name] = [...declaredIn.get(name)].sort();
  }

  const report = {
    schema: "dead_function_candidates_v2",
    declaration_sources: declFiles.map((f) => path.relative(ROOT, f).replace(/\\/g, "/")),
    total_top_level_functions: functionNames.size,
    dead_candidates: deadCandidates,
    zero_app_references_but_referenced_in_tests: zeroAppReferencesButInTests,
    declared_in: declaredInReport,
  };
  const outPath = path.join(__dirname, "dead_function_candidates.json");
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2) + "\n", "utf8");
  console.log(
    `${deadCandidates.length} dead-code candidate(s), ` +
      `${zeroAppReferencesButInTests.length} referenced only in tests/ ` +
      `(needs human review either way). Wrote ${outPath}.`,
  );
}

main();
