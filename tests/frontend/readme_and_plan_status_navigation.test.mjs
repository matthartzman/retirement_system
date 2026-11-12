// DOC-002 / W2-09: the README and the Plan Status (Welcome) cards direct the reader to pages by
// name and by menu group. Check them against the real STEPS nav loaded in the Node vm sandbox, so a
// renamed or moved page fails here instead of leaving the reader hunting for it.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const README = fs.readFileSync(path.join(HERE, "..", "..", "documentation", "reference", "readme", "README.md"), "utf8");
const dash = loadDashboardSandbox();
const run = (code) => vm.runInContext(code, dash);
const steps = JSON.parse(run("JSON.stringify(STEPS.map((s) => ({id: s.id, group: s.group, title: s.title})))"));

// [page title, the group it must sit in, the phrase the README uses to point at it]
const PLACEMENTS = [
  ["Data & Backups", "Settings", "Settings → Data & Backups"],
  ["Plan Features", "Settings", "Settings → Plan Features"],
  ["Account Reconciliation", "Track & Reconcile", "(under **Track & Reconcile**)"],
  ["Rental Properties", "Accounts & Property", "under **Accounts & Property**"],
  ["Plan Status", "Plan Status", "**Plan Status**"],
];

test("every page the README points at exists in the group the README names", () => {
  for (const [title, group, phrase] of PLACEMENTS) {
    const step = steps.find((s) => s.title === title);
    assert.ok(step, `${title} is not a nav title`);
    assert.equal(step.group, group, `${title} moved out of ${group}`);
    assert.ok(README.includes(phrase), `README no longer says ${phrase}`);
  }
});

test("README names no retired page or group", () => {
  for (const retired of ["Reports & Review", "Welcome** page", "Spending Analysis"]) {
    assert.ok(!README.includes(retired), `README still says ${retired}`);
  }
});

test("every Plan Status checklist card opens and counts only pages that exist", () => {
  const ids = new Set(steps.map((s) => s.id));
  const html = run("firstRunChecklistHtml(false)");
  const targets = [...html.matchAll(/data-step-id="([^"]+)"/g)].map((m) => m[1]);
  assert.ok(targets.length >= 7, "checklist cards did not render");
  for (const id of targets) assert.ok(ids.has(id), `checklist opens retired page ${id}`);
  // the step lists that drive each card's status
  const src = fs.readFileSync(path.join(HERE, "..", "..", "frontend", "js", "dashboard_decomp_checklist_closeout.js"), "utf8");
  const body = src.slice(src.indexOf("export function firstRunChecklistHtml"), src.indexOf("export async function savePlanAs"));
  for (const list of body.matchAll(/steps:\s*\[([^\]]*)\]/g)) {
    for (const id of list[1].match(/"[a-z_0-9]+"/g) || []) assert.ok(ids.has(id.slice(1, -1)), `card counts retired page ${id}`);
  }
});

test("Plan Status direction text uses current page names", () => {
  const welcome = String(dash.renderWelcome);
  for (const retired of ["Reports &amp; Review", "Preflight tab", "Spending Categories defines"]) {
    assert.ok(!welcome.includes(retired), `Plan Status still says ${retired}`);
  }
  assert.ok(welcome.includes("Build &amp; Results") && welcome.includes("Track &amp; Reconcile"));
});
