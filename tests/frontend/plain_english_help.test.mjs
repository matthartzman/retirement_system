// WI-033: every page has a plain-English summary and every term resolves to a glossary entry.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const { GLOSSARY, PLAIN_PAGE_HELP, plainHelpHtml } = await import("../../frontend/js/help_glossary.js");

test("every STEPS page has a plain summary", () => {
  const src = fs.readFileSync("frontend/js/dashboard.js", "utf8");
  const block = src.slice(src.indexOf("const STEPS = ["), src.indexOf("\n];", src.indexOf("const STEPS = [")));
  const ids = [...block.matchAll(/\n    id: "(\w+)"/g)].map((m) => m[1]);
  assert.ok(ids.length >= 28);
  const missing = ids.filter((id) => !PLAIN_PAGE_HELP[id] || !PLAIN_PAGE_HELP[id].summary);
  assert.deepEqual(missing, []);
});

test("every page term has a glossary definition and every definition is used", () => {
  const used = new Set();
  for (const [id, p] of Object.entries(PLAIN_PAGE_HELP))
    for (const t of p.terms) {
      assert.ok(GLOSSARY[t], `${id}: no glossary entry for ${t}`);
      used.add(t);
    }
  assert.deepEqual(Object.keys(GLOSSARY).filter((k) => !used.has(k)), []);
});

test("plainHelpHtml renders the summary and escapes text; unknown pages render nothing", () => {
  const html = plainHelpHtml("holdings");
  assert.match(html, /In plain English/);
  assert.match(html, /Tax lot/);
  assert.equal(plainHelpHtml("no_such_page"), "");
});

test("dashboard.js calls the plain-help hook and index.html loads the module", () => {
  assert.match(fs.readFileSync("frontend/js/dashboard.js", "utf8"), /window\.plainHelpHtml/);
  assert.match(fs.readFileSync("frontend/index.html", "utf8"), /js\/help_glossary\.js/);
});
