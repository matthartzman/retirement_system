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

test("index.html loads the registry module", () => {
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

test("every page has a full record; the panel renders it, nothing falls back", () => {
  const src = fs.readFileSync("frontend/js/dashboard.js", "utf8");
  const block = src.slice(src.indexOf("const STEPS = ["), src.indexOf("\n];", src.indexOf("const STEPS = [")));
  const ids = [...block.matchAll(/\n    id: "(\w+)"/g)].map((m) => m[1]);
  assert.equal(ids.length, 28);
  for (const id of ids) {
    const p = HELP_PAGES[id];
    for (const k of ["title", "summary", "whatFor", "connections", "options", "impact"]) assert.ok(p && p[k], `${id}.${k}`);
    assert.ok(p.terms.length, `${id} has no glossary terms`);
    assert.match(pageHelpHtml(id), /What this page is for/);
  }
  assert.equal(Object.keys(HELP_PAGES).length, ids.length);
  assert.equal(pageHelpHtml("no_such_page"), null);
});

test("the center panel renders no question box, intro line or inline plain-help box", () => {
  const src = fs.readFileSync("frontend/js/dashboard.js", "utf8");
  const head = src.slice(src.indexOf('<div class="pane-head">'), src.indexOf('<div class="pane-head">') + 700);
  assert.doesNotMatch(head, /class="question"|st\.intro|st\.help|plainHelpHtml/);
  const steps = src.slice(src.indexOf("const STEPS = ["), src.indexOf("\n];", src.indexOf("const STEPS = [")));
  assert.doesNotMatch(steps, /\n    (intro|help|desc):/);
  assert.doesNotMatch(src, /\bSTEP_HELP\b/);
  assert.match(src, /RPHelp\?\.pageHtml\(id\)/);
});

test("every section record names a real page and renders with a way back to page help", () => {
  for (const [key, s] of Object.entries(HELP_SECTIONS)) {
    assert.ok(HELP_PAGES[s.pageId], key);
    assert.ok(key.startsWith(`${s.pageId}.`), key);
    assert.ok(sectionHelpHtml(key).includes(`openStepHelp('${s.pageId}')`), key);
  }
  assert.equal(sectionHelpHtml("nope.nope"), null);
});

test("page help keeps the pointer to where HSA withdrawal timing is controlled", () => {
  const all = Object.values(HELP_PAGES).map((p) => `${p.whatFor} ${p.connections} ${p.options} ${p.impact}`).join(" ");
  assert.match(all, /HSA withdrawal timing is controlled on Other → Other assets/);
});

test("page help keeps the planning workbench record and the YTD import wording", () => {
  assert.ok(HELP_PAGES.strategy_workbench.whatFor);
  assert.match(HELP_PAGES.strategy_workbench.whatFor + HELP_PAGES.strategy_workbench.connections, /Baseline → Change Set → Run Type → Impact → Decision/);
  const all = Object.values(HELP_PAGES).map((p) => `${p.whatFor} ${p.connections} ${p.options} ${p.impact}`).join(" ");
  assert.match(all, /Add to merge new transactions/);
});

test("section help keeps the facts moved out of the Spending and Other Assets pages", () => {
  assert.match(HELP_SECTIONS["spending_core.housing_costs"].body, /Real-estate taxes, homeowners insurance, maintenance, utilities, and HOA are budgeted in the groups below\./);
  assert.match(HELP_SECTIONS["assets_special.hsa_withdrawals"].body, /choose how the HSA is used in Cash Flow/);
});
