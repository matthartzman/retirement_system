// WI-015 / ARC-007 interim guard (system review 2026-10-19).
//
// The frontend is 52 order-dependent <script type="module"> tags joined by
// window globals. WI-035 replaced the renderMain/showStepHelp monkey-patch chain
// with the explicit hook registry in js/render_hooks.js (RPHooks.after(point,
// fn, order)); hook order is now the numeric `order`, not script order. These
// tests still freeze:
//   1. the exact script list and order in frontend/index.html, and
//   2. the exact set of files that define or assign renderMain/showStepHelp
//      (only the base definitions/bridges -- NO wrapper may reappear), and
//   3. the registry contract: loaded first, explicit unique hook orders.
// A module that is added, removed or reordered, or a NEW wrapper, fails here.
// The ?v= cache-busting query is deliberately ignored: bumping it is routine.
//
// To change intentionally: update the frozen lists below in the same commit and
// say why in the commit message (the order is behaviour, not formatting).
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "frontend");

const FROZEN_SCRIPT_ORDER = [
  "js/pywebview_bridge.js",
  "js/dashboard_shared_helpers.js",
  "js/render_hooks.js",
  "js/text_size.js",
  "js/help_registry.js",
  "js/api_client.js",
  "js/app_store.js",
  "js/navigation.js",
  "js/reports_ui.js",
  "js/planning_workbench_ui.js",
  "js/dashboard_decomp_estate_insurance.js",
  "js/dashboard_decomp_build_lifecycle.js",
  "js/dashboard_decomp_supplemental_tables.js",
  "js/dashboard_decomp_local_backups.js",
  "js/dashboard_decomp_monarch_autoupdate.js",
  "js/dashboard_decomp_row_model.js",
  "js/dashboard_decomp_assets_other.js",
  "js/dashboard_decomp_spending_taxonomy.js",
  "js/dashboard_decomp_spending_sources.js",
  "js/dashboard_decomp_spending_adjustments.js",
  "js/dashboard_decomp_housing_optimizer.js",
  "js/dashboard_decomp_housing_scenarios.js",
  "js/dashboard_decomp_build_history.js",
  "js/dashboard_decomp_page_recommendations.js",
  "js/dashboard_decomp_income_streams.js",
  "js/dashboard_decomp_large_discretionary.js",
  "js/dashboard_decomp_death_benefits.js",
  "js/dashboard_decomp_mc_stress_options.js",
  "js/dashboard_decomp_checklist_closeout.js",
  "js/dashboard_decomp_plan_switcher.js",
  "js/dashboard_decomp_conversion.js",
  "js/dashboard_decomp_allocation_optimizer.js",
  "js/dashboard_decomp_strategy_workspace.js",
  "js/dashboard_decomp_ytd_and_plan_folder_io.js",
  "js/dashboard_plan_folder_io.js",
  "js/dashboard_decomp_focus_restore.js",
  "js/dashboard_decomp_field_choice_help.js",
  "js/dashboard.js",
  "js/dashboard_decomp_workbook_formatting.js",
  "js/dashboard_decomp_plan_features.js",
  "js/dashboard_decomp_plan_tiers.js",
  "js/dashboard_decomp_rental_properties.js",
  "js/dashboard_decomp_monarch_reconciliation.js",
  "js/dashboard_decomp_sales_ledger.js",
  "js/dashboard_decomp_sales_queue.js",
  "js/dashboard_decomp_sales_tax.js",
  "js/dashboard_decomp_broker_import.js",
  "js/dashboard_decomp_tax_assumptions.js",
  "js/dashboard_decomp_roth_guardrails.js",
  "js/dashboard_decomp_misc.js",
  "js/dashboard_decomp_state_inputs.js",
  "js/dashboard_decomp_home_panels.js",
  "js/modules/phase3_module_manifest.js",
  "js/dashboard_source_truth_banners.js",
  "js/dashboard_decomp_optimizer_apply.js",
  "js/dashboard_batch_assumption_edit.js",
  "js/dashboard_decomp_holdings.js",
  "js/spending_dashboard.js",
];

// File -> symbols it defines/assigns: the original definitions and window
// bridge (dashboard.js) and navigation.js's showStepHelp global. Wrappers are
// gone (WI-035); behaviour is added only through RPHooks.after().
const FROZEN_WRAPPERS = {
  "js/dashboard.js": ["renderMain", "showStepHelp"],
  "js/navigation.js": ["showStepHelp"],
};

function scriptSrcs() {
  const html = fs.readFileSync(path.join(FRONTEND, "index.html"), "utf8");
  const out = [];
  for (const m of html.matchAll(/<script\b[^>]*>/gi)) {
    const tag = m[0];
    const src = /\bsrc\s*=\s*["']([^"']+)["']/i.exec(tag);
    assert.ok(src, `inline/srcless script tag found: ${tag}`);
    assert.match(tag, /type\s*=\s*["']module["']/i, `non-module script: ${tag}`);
    out.push(src[1].split("?")[0]);
  }
  return out;
}

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    return e.isDirectory() ? walk(p) : p.endsWith(".js") ? [p] : [];
  });
}

// Matches `renderMain = `, `window.renderMain = `, `let renderMain = `,
// `Object.defineProperty(window, "renderMain"` -- but not `==`/`===`/`=>`.
function definesOrWraps(src, sym) {
  const stripped = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  const assign = new RegExp(
    `(?:^|[^\\w.$])(?:window\\.|globalThis\\.)?(?:let\\s+|var\\s+|const\\s+)?${sym}\\s*=(?![=>])`,
    "m",
  );
  const define = new RegExp(`defineProperty\\(\\s*(?:window|globalThis)\\s*,\\s*["']${sym}["']`);
  return assign.test(stripped) || define.test(stripped);
}

test("index.html script list and order are frozen (58 module scripts)", () => {
  assert.equal(scriptSrcs().length, 58);
  assert.deepEqual(scriptSrcs(), FROZEN_SCRIPT_ORDER);
});

test("every frozen script exists on disk and there are no duplicates", () => {
  assert.equal(new Set(FROZEN_SCRIPT_ORDER).size, FROZEN_SCRIPT_ORDER.length);
  for (const s of FROZEN_SCRIPT_ORDER) assert.ok(fs.existsSync(path.join(FRONTEND, s)), s);
});

test("renderMain/showStepHelp wrapper set is frozen", () => {
  const found = {};
  for (const file of walk(path.join(FRONTEND, "js"))) {
    const rel = path.relative(FRONTEND, file).split(path.sep).join("/");
    const src = fs.readFileSync(file, "utf8");
    const syms = ["renderMain", "showStepHelp"].filter((s) => definesOrWraps(src, s));
    if (syms.length) found[rel] = syms;
  }
  assert.deepEqual(found, FROZEN_WRAPPERS);
});

test("registry loads right after the bridge and shared helpers (before any registrant)", () => {
  assert.equal(FROZEN_SCRIPT_ORDER.indexOf("js/render_hooks.js"), 2);
});

// Lint (WI-035): no module may assign window.renderMain / window.showStepHelp
// (or wrap them) except dashboard.js, which owns the base functions and bridge.
test("no module assigns window.renderMain outside dashboard.js", () => {
  for (const file of walk(path.join(FRONTEND, "js"))) {
    const rel = path.relative(FRONTEND, file).split(path.sep).join("/");
    if (rel === "js/dashboard.js") continue;
    const src = fs.readFileSync(file, "utf8");
    assert.equal(definesOrWraps(src, "renderMain"), false, `${rel} assigns renderMain`);
    assert.doesNotMatch(src, /window\.renderMain\s*=(?![=>])/, rel);
    assert.doesNotMatch(src, /\b(prev|old)RenderMain\b/, `${rel} has a wrapper-chain remnant`);
  }
});

test("hook registrations use explicit, unique orders (script order carries no meaning)", () => {
  const seen = {};
  for (const file of walk(path.join(FRONTEND, "js"))) {
    const src = fs.readFileSync(file, "utf8");
    for (const m of src.matchAll(/RPHooks\??\.after\(\s*"(\w+)"\s*,[\s\S]*?,\s*(\d+)\s*\)/g)) {
      const key = `${m[1]}:${m[2]}`;
      assert.ok(!seen[key], `duplicate hook order ${key} (${seen[key]} and ${file})`);
      seen[key] = path.basename(file);
    }
  }
  assert.deepEqual(Object.keys(seen).sort(), [
    "renderMain:10", "renderMain:20", "renderMain:30", "renderMain:40", "showStepHelp:30",
  ]);
});
