// Navigation consistency guard: every hard-coded sourceStep / data-step-id
// literal must resolve (through setStep) to a real STEPS id or a redirect key,
// and no JS string literal may name a page that no longer exists.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const JS_DIR = path.join(import.meta.dirname, "..", "..", "frontend", "js");
const files = [];
(function walk(d) {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p);
    else if (e.name.endsWith(".js")) files.push(p);
  }
})(JS_DIR);
const read = (p) => fs.readFileSync(p, "utf8");

const dashboard = read(path.join(JS_DIR, "dashboard.js"));
const stepsStart = dashboard.indexOf("const STEPS");
const stepIds = new Set(
  [...dashboard.slice(stepsStart).matchAll(/^ {4}id: "([a-z0-9_]+)",/gm)].map(
    (m) => m[1],
  ),
);
const nav = read(path.join(JS_DIR, "navigation.js"));
const redirectKeys = new Set();
for (const name of [
  "WORKSPACE_TAB_REDIRECTS",
  "STEP_REDIRECTS",
  "SECTION_REDIRECTS",
]) {
  const start = nav.indexOf(`const ${name}=`);
  assert.ok(start >= 0, `${name} not found in navigation.js`);
  const end = nav.indexOf("\n  };", start);
  const body = nav
    .slice(start, end)
    .split("\n")
    .filter((l) => !l.trim().startsWith("//"))
    .join("\n");
  for (const m of body.matchAll(/^\s{4}([a-z0-9_]+):/gm)) redirectKeys.add(m[1]);
}

// Reports & Review sub-page ids are an array, not a map, in navigation.js.
const reportsRedirect = nav.match(/const REPORTS_REDIRECT_IDS=\[([^\]]*)\]/);
assert.ok(reportsRedirect, "REPORTS_REDIRECT_IDS not found in navigation.js");
for (const m of reportsRedirect[1].matchAll(/'([a-z0-9_]+)'/g)) redirectKeys.add(m[1]);

test("STEPS ids and redirect keys were extracted", () => {
  assert.ok(stepIds.size > 20, `only ${stepIds.size} step ids found`);
  assert.ok(stepIds.has("strategy_optimize"));
  assert.ok(redirectKeys.has("allocation_assets"));
});

test("every sourceStep / data-step-id literal resolves to a real step", () => {
  const bad = [];
  const re =
    /(?:sourceStep\s*(?::|\|\|)\s*|data-step-id=\\?["'])["']?([a-z][a-z0-9_]*)["']/g;
  for (const f of files) {
    const src = read(f);
    for (const m of src.matchAll(re)) {
      const id = m[1];
      if (!stepIds.has(id) && !redirectKeys.has(id))
        bad.push(`${path.relative(JS_DIR, f)}: ${id}`);
    }
  }
  assert.deepEqual(bad, []);
});

test("no hard-coded sourceTitle literal for a real step (use stepTitleById)", () => {
  const bad = [];
  for (const f of files) {
    const src = read(f);
    for (const m of src.matchAll(/sourceTitle:\s*"([^"]+)"/g)) {
      // Titles for ids that are not STEPS entries (Workbench case-change sets)
      // are allowed; everything else must derive from STEPS.
      if (/Home & Housing|Asset Allocation|Income & Social Security/.test(m[1]))
        bad.push(`${path.relative(JS_DIR, f)}: ${m[1]}`);
    }
  }
  assert.deepEqual(bad, []);
});

test("no string literal names a page that was renamed or merged away", () => {
  const stale = [
    "Home & Housing page",
    "Home & Housing",
    "Build Impact page",
    "The Housing step",
  ];
  const hits = [];
  for (const f of files) {
    const lines = read(f).split("\n");
    lines.forEach((line, i) => {
      const t = line.trim();
      if (t.startsWith("//") || t.startsWith("*")) return;
      for (const s of stale)
        if (line.includes(s)) hits.push(`${path.relative(JS_DIR, f)}:${i + 1} ${s}`);
    });
  }
  assert.deepEqual(hits, []);
});
