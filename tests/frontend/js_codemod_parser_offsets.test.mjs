// Regression guard for the parser choice in tools/js_codemod/*.mjs.
//
// Every codemod in that directory that SLICES SOURCE BY OFFSET (reads
// node.start / node.end and does source.slice(start, end)) must parse with
// plain @babel/parser, never jscodeshift.withParser("babel").
//
// Why: jscodeshift's offsets are only correct when the file on disk uses CRLF
// line endings. On an LF source it reports offsets as though every newline
// were still two characters, so every slice lands progressively further into
// unrelated code. Measured against this repo's own frontend/js/dashboard.js:
// CRLF checkout -> 584 top-level functions, 0 slice wrong; the identical file
// LF-normalised -> 584 top-level functions, ALL 584 slice wrong.
//
// That is not theoretical. This repo sets core.autocrlf=true and .gitattributes
// pins only *.csv and input/plan_data_manifest.json to eol=lf -- nothing covers
// *.js. So a Windows checkout gets CRLF (the codemods work by luck) and a
// Linux/macOS/CI checkout gets LF (the codemods silently emit garbage). The
// shipped dashboard_decomp_row_model.js extraction is correct only because
// extract_core.mjs happened to be run on Windows.
//
// node.loc is not a workaround: recast returns loc: null for a declaration
// nested inside an `export`.
//
// Run with: node --test tests/frontend/
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as babelParser from "@babel/parser";
import jscodeshift from "jscodeshift";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CODEMOD_DIR = path.resolve(__dirname, "..", "..", "tools", "js_codemod");

// ── The fixture ────────────────────────────────────────────────────────────
// Built from an array joined with an explicit "\n" rather than checked in as a
// file on purpose: a checked-in .js fixture would be converted to CRLF on
// checkout by core.autocrlf, which would make this entire test vacuous on
// Windows -- exactly the platform where the bug hides. Long enough that a
// one-character-per-newline drift pushes the later declarations clearly out of
// their own bodies.
// `exported: true` wraps the declaration in `export ` in the FIXTURE but not in
// the EXPECTED text -- the codemods unwrap ExportNamedDeclaration and splice the
// inner declaration's own offsets. delta covers that path, which is also the one
// where recast returns loc: null and so offers no fallback to node.loc.
const DECLARATIONS = [
  { name: "alpha", text: "function alpha(x) {\n  const bumped = x + 1;\n  return bumped;\n}" },
  {
    name: "beta",
    text: "async function beta(y) {\n  const settled = await y;\n  return { ok: settled };\n}",
  },
  { name: "gamma", text: "let gamma = function (z) {\n  return z * 2;\n};" },
  {
    name: "delta",
    text: "function delta() {\n  return alpha(1) + gamma(2);\n}",
    exported: true,
  },
];

const FIXTURE_LF = [
  "// A miniature stand-in for frontend/js/dashboard.js.",
  "// The leading comment block exists to push real offsets well past zero.",
  "const PREAMBLE = 1;",
  "",
  ...DECLARATIONS.flatMap((d) => [(d.exported ? "export " : "") + d.text, ""]),
  "export const TRAILER = PREAMBLE;",
  "",
].join("\n");

const FIXTURE_CRLF = FIXTURE_LF.replace(/\n/g, "\r\n");

/** The text each declaration should slice to, for a given line ending. */
function expectedText(name, source) {
  const { text } = DECLARATIONS.find((d) => d.name === name);
  return source.includes("\r\n") ? text.replace(/\n/g, "\r\n") : text;
}

/**
 * Discover top-level declaration offsets exactly the way the codemods do:
 * unwrap `export <decl>`, then record the statement's own start/end.
 */
function sliceTopLevelDeclarations(program, source) {
  const out = [];
  for (const raw of program.body) {
    const stmt =
      raw.type === "ExportNamedDeclaration" && raw.declaration ? raw.declaration : raw;
    // Splice units are whole statements, and the offsets that matter are the
    // ones the codemods actually read -- on the unwrapped declaration.
    if (stmt.type === "FunctionDeclaration" && stmt.id) {
      out.push({ name: stmt.id.name, text: source.slice(stmt.start, stmt.end) });
    } else if (stmt.type === "VariableDeclaration") {
      for (const decl of stmt.declarations) {
        if (
          decl.id.type === "Identifier" &&
          decl.init &&
          (decl.init.type === "FunctionExpression" ||
            decl.init.type === "ArrowFunctionExpression")
        ) {
          out.push({ name: decl.id.name, text: source.slice(stmt.start, stmt.end) });
        }
      }
    }
  }
  return out;
}

const babelProgram = (src) => babelParser.parse(src, { sourceType: "module" }).program;

function jscodeshiftProgram(src) {
  const j = jscodeshift.withParser("babel");
  let program = null;
  j(src)
    .find(j.Program)
    .forEach((p) => {
      program = p.node;
    });
  return program;
}

// ── 1. @babel/parser slices correctly under BOTH line endings ──────────────
for (const [label, source] of [
  ["LF", FIXTURE_LF],
  ["CRLF", FIXTURE_CRLF],
]) {
  describe(`@babel/parser offsets on a ${label} source`, () => {
    const sliced = sliceTopLevelDeclarations(babelProgram(source), source);

    test("finds every top-level function declaration", () => {
      assert.deepEqual(
        sliced.map((s) => s.name),
        DECLARATIONS.map((d) => d.name),
      );
    });

    test("every slice starts with function/async function/let and ends with a brace", () => {
      for (const { name, text } of sliced) {
        assert.match(
          text,
          /^(async function |function |let )/,
          `${name} sliced to something that is not a declaration: ${JSON.stringify(text.slice(0, 60))}`,
        );
        assert.match(
          text,
          /\};?$/,
          `${name} slice does not end at its closing brace: ${JSON.stringify(text.slice(-60))}`,
        );
      }
    });

    test("every slice is byte-identical to the declaration it names", () => {
      for (const { name, text } of sliced) {
        assert.equal(text, expectedText(name, source), `${name} sliced to the wrong bytes`);
      }
    });
  });
}

// ── 2. The hazard itself: jscodeshift is wrong on LF, right on CRLF ────────
describe("jscodeshift offsets (the reason the codemods must not use it)", () => {
  test("are correct on a CRLF source -- which is why this bug hid on Windows", () => {
    const sliced = sliceTopLevelDeclarations(
      jscodeshiftProgram(FIXTURE_CRLF),
      FIXTURE_CRLF,
    );
    for (const { name, text } of sliced) {
      assert.equal(text, expectedText(name, FIXTURE_CRLF));
    }
  });

  test("are wrong on an LF source -- garbage taken from unrelated code", () => {
    // If this ever FAILS, jscodeshift/recast has fixed its offset handling.
    // That is good news, but do not just delete this test: confirm the fix
    // against the real frontend/js/dashboard.js at the version being used,
    // pin that jscodeshift version, and only then relax the static guard below.
    const sliced = sliceTopLevelDeclarations(jscodeshiftProgram(FIXTURE_LF), FIXTURE_LF);
    const wrong = sliced.filter(({ name, text }) => text !== expectedText(name, FIXTURE_LF));
    assert.ok(
      wrong.length > 0,
      "jscodeshift now appears to report true offsets on LF sources -- see the comment above",
    );
  });
});

// ── 3. Static guard over the real tools ────────────────────────────────────
// This is the part that actually stops the regression. The behavioural tests
// above prove the premise; this asserts the tools act on it.
describe("tools/js_codemod parser choice", () => {
  const toolFiles = fs
    .readdirSync(CODEMOD_DIR)
    .filter((f) => f.endsWith(".mjs"))
    .map((f) => ({ name: f, source: fs.readFileSync(path.join(CODEMOD_DIR, f), "utf8") }));

  test("the codemod directory is where this test thinks it is", () => {
    assert.ok(toolFiles.length > 0, `no .mjs tools found in ${CODEMOD_DIR}`);
  });

  // Reading .start/.end off an AST node is the signature of offset slicing.
  const readsOffsets = (source) => /\bstmt\.(start|end)\b|\bnode\.(start|end)\b|\.node\.(start|end)\b/.test(source);
  const usesJscodeshift = (source) => /\bfrom\s+["']jscodeshift["']/.test(source);
  const usesBabelParser = (source) => /\bfrom\s+["']@babel\/parser["']/.test(source);

  for (const { name, source } of toolFiles) {
    if (!readsOffsets(source)) continue;

    test(`${name} slices by offset, so it must parse with @babel/parser`, () => {
      assert.ok(
        usesBabelParser(source),
        `${name} reads node.start/node.end but does not import @babel/parser`,
      );
    });

    test(`${name} slices by offset, so it must not import jscodeshift`, () => {
      assert.ok(
        !usesJscodeshift(source),
        `${name} reads node.start/node.end but imports jscodeshift, whose offsets ` +
          "are wrong on any LF checkout (Linux/macOS/CI). Parse with @babel/parser instead.",
      );
    });
  }

  test("the four known offset-slicing tools are all covered by the checks above", () => {
    // Named explicitly so that renaming or gutting one of them fails here
    // rather than silently dropping it out of the loop.
    for (const expected of [
      "extract_core.mjs",
      "extract_module.mjs",
      "convert_dashboard.mjs",
      "find_clusters.mjs",
    ]) {
      const tool = toolFiles.find((t) => t.name === expected);
      assert.ok(tool, `${expected} is missing from ${CODEMOD_DIR}`);
      assert.ok(
        readsOffsets(tool.source),
        `${expected} no longer reads node.start/node.end -- if that is intentional, ` +
          "remove it from this list; if it is a rename of the offset access, fix the detector",
      );
    }
  });
});
