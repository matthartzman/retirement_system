// Unit tests for the pure/stateless helper functions in frontend/js/dashboard.js.
//
// This is the first JS test coverage of any kind in this repo (see
// documentation/SYSTEM_REVIEW_AND_REFACTOR_PLAN.md Phase 5/2d — previously
// dashboard.js behavior was verified only indirectly, via Python tests that
// read the file as text and assert substrings are present). Run with:
//
//   node --test tests/frontend/
//
// No new dependency: Node 18+ ships a built-in test runner and assert module.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

describe("esc (HTML-escaping)", () => {
  test("escapes the five HTML special characters", () => {
    assert.equal(sandbox.esc(`<b>&"'`), "&lt;b&gt;&amp;&quot;&#39;");
  });
  test("null/undefined become empty string, not the literal text", () => {
    assert.equal(sandbox.esc(null), "");
    assert.equal(sandbox.esc(undefined), "");
  });
  test("passes plain text through unchanged", () => {
    assert.equal(sandbox.esc("Terminal Net Worth"), "Terminal Net Worth");
  });
});

describe("norm (label normalization)", () => {
  test("lowercases and collapses non-alphanumeric runs to a single underscore", () => {
    assert.equal(sandbox.norm("Hello World!"), "hello_world_");
    assert.equal(sandbox.norm("Roth IRA (Traditional)"), "roth_ira_traditional_");
  });
  test("null/undefined/empty all normalize to empty string", () => {
    assert.equal(sandbox.norm(null), "");
    assert.equal(sandbox.norm(undefined), "");
    assert.equal(sandbox.norm(""), "");
  });
});

describe("titleWord", () => {
  test("known acronyms are returned in their canonical form", () => {
    assert.equal(sandbox.titleWord("ssdi"), "SSDI");
    assert.equal(sandbox.titleWord("RMD"), "RMD");
  });
  test("unknown words are title-cased", () => {
    assert.equal(sandbox.titleWord("balance"), "Balance");
  });
});

describe("stripUiLabelPrefix", () => {
  test("strips a short slash-delimited prefix", () => {
    assert.equal(sandbox.stripUiLabelPrefix("Household / Retirement Age"), "Retirement Age");
  });
  test("leaves text with no prefix unchanged", () => {
    assert.equal(sandbox.stripUiLabelPrefix("Retirement Age"), "Retirement Age");
  });
});

describe("formatAcronyms", () => {
  test("expands known acronyms to their full label, word-boundary matched", () => {
    assert.equal(sandbox.formatAcronyms("the rmd and ss rules"), "the RMD and SS rules");
  });
  test("does not partially match inside a longer word", () => {
    // "ss" must not match inside "assess" — word-boundary regex protects this.
    assert.equal(sandbox.formatAcronyms("we assess the plan"), "we assess the plan");
  });
});

describe("fmtMoney", () => {
  test("formats a finite number as USD with no cents", () => {
    assert.equal(sandbox.fmtMoney(1234.5), "$1,235");
  });
  test("strips currency symbols/commas already in the input string", () => {
    assert.equal(sandbox.fmtMoney("$1,234.50"), "$1,235");
  });
  test("null/undefined/empty become 'Not available'", () => {
    assert.equal(sandbox.fmtMoney(null), "Not available");
    assert.equal(sandbox.fmtMoney(undefined), "Not available");
    assert.equal(sandbox.fmtMoney(""), "Not available");
  });
});

describe("fmtPct", () => {
  test("formats a finite number to one decimal place with a percent sign", () => {
    assert.equal(sandbox.fmtPct(12.345), "12.3%");
  });
  test("null/undefined/empty become 'Not available'", () => {
    assert.equal(sandbox.fmtPct(null), "Not available");
  });
});

describe("finiteOrNull / firstFinite", () => {
  test("finiteOrNull returns the numeric value for a finite input", () => {
    assert.equal(sandbox.finiteOrNull(42), 42);
    assert.equal(sandbox.finiteOrNull("42.5"), 42.5);
  });
  test("finiteOrNull returns null for undefined/null/empty string", () => {
    assert.equal(sandbox.finiteOrNull(undefined), null);
    assert.equal(sandbox.finiteOrNull(null), null);
    assert.equal(sandbox.finiteOrNull(""), null);
  });
  test("KNOWN QUIRK: finiteOrNull(NaN) returns 0, not null", () => {
    // String(NaN) -> "NaN" -> stripped of non-numeric chars -> "" -> Number("") -> 0,
    // which passes Number.isFinite. This means a NaN value is silently treated as
    // the number 0 rather than "no value" — documenting actual behavior here,
    // not asserting what it "should" do. See SYSTEM_REVIEW_AND_REFACTOR_PLAN.md
    // Phase 2d for context; not fixed here since other code may rely on it.
    assert.equal(sandbox.finiteOrNull(NaN), 0);
  });
  test("firstFinite returns the first argument that resolves to a finite number", () => {
    assert.equal(sandbox.firstFinite(undefined, null, 5, 7), 5);
  });
  test("firstFinite returns NaN when nothing resolves to finite", () => {
    assert.ok(Number.isNaN(sandbox.firstFinite(undefined, null, "")));
  });
  test("KNOWN QUIRK: a NaN argument before a real value short-circuits firstFinite to 0", () => {
    // Consequence of the finiteOrNull(NaN) === 0 quirk above.
    assert.equal(sandbox.firstFinite(undefined, null, NaN, 5, 7), 0);
  });
});

describe("normalizeLanguageMode", () => {
  test("only the literal string 'advisor' maps to advisor mode", () => {
    assert.equal(sandbox.normalizeLanguageMode("advisor"), "advisor");
    assert.equal(sandbox.normalizeLanguageMode("Advisor"), "advisor");
  });
  test("anything else (including unset) defaults to household mode", () => {
    assert.equal(sandbox.normalizeLanguageMode("household"), "household");
    assert.equal(sandbox.normalizeLanguageMode(undefined), "household");
    assert.equal(sandbox.normalizeLanguageMode("client"), "household");
  });
});
