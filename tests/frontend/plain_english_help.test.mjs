// WI-033 + contextual help Phase 1: every page has a plain-English summary in the help registry,
// every term resolves to a glossary entry, and full panel records use the fixed layout.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const { GLOSSARY, HELP_PAGES, HELP_SECTIONS, plainHelpHtml, pageHelpHtml, sectionHelpHtml } = await import(
  "../../frontend/js/help_registry.js"
);

test("every STEPS page has a plain summary", () => {
  const src = fs.readFileSync("frontend/js/dashboard.js", "utf8");
  const block = src.slice(src.indexOf("const STEPS = ["), src.indexOf("\n];", src.indexOf("const STEPS = [")));
  const ids = [...block.matchAll(/\n    id: "(\w+)"/g)].map((m) => m[1]);
  assert.ok(ids.length >= 28);
  const missing = ids.filter((id) => !HELP_PAGES[id] || !HELP_PAGES[id].summary);
  assert.deepEqual(missing, []);
});

test("every page term has a glossary definition and every definition is used", () => {
  const used = new Set();
  for (const [id, p] of Object.entries(HELP_PAGES))
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
  assert.match(fs.readFileSync("frontend/index.html", "utf8"), /js\/help_registry\.js/);
});

test("the pilot page has a full record and renders the fixed panel layout in order", () => {
  const p = HELP_PAGES.household_people;
  for (const k of ["title", "summary", "whatFor", "connections", "options", "impact"]) assert.ok(p[k], k);
  const html = pageHelpHtml("household_people");
  const order = ["In plain English", "What this page is for", "How the values work together",
    "How to choose values", "Likely planning impact", "Words on this page"].map((h) => html.indexOf(h));
  assert.ok(order.every((i) => i >= 0), String(order));
  assert.deepEqual([...order].sort((a, b) => a - b), order);
  assert.match(html, /<dt>Filing status<\/dt>/);
});

test("pages without a full record return null so STEP_HELP stays the fallback", () => {
  const full = Object.keys(HELP_PAGES).filter((id) => HELP_PAGES[id].whatFor);
  assert.deepEqual(full, ["household_people"]);
  assert.equal(pageHelpHtml("holdings"), null);
  assert.equal(pageHelpHtml("no_such_page"), null);
  assert.match(fs.readFileSync("frontend/js/dashboard.js", "utf8"), /RPHelp\?\.pageHtml\(id\) \|\| STEP_HELP\[id\] \|\| STEP_HELP\.start/);
});

test("every section record names a real page and renders with a way back to page help", () => {
  for (const [key, s] of Object.entries(HELP_SECTIONS)) {
    assert.ok(HELP_PAGES[s.pageId], key);
    assert.ok(key.startsWith(`${s.pageId}.`), key);
    assert.match(sectionHelpHtml(key), /openStepHelp\('household_people'\)/);
  }
  assert.equal(sectionHelpHtml("nope.nope"), null);
});
