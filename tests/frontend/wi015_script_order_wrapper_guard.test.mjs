// WI-015 / ARC-007 interim guard (system review 2026-10-19).
//
// The frontend is 52 order-dependent <script type="module"> tags joined by
// window globals and a renderMain/showStepHelp monkey-patch chain. Until
// WI-035 replaces the chain with an explicit hook registry, these tests freeze:
//   1. the exact script list and order in frontend/index.html, and
//   2. the exact set of files that define or reassign renderMain/showStepHelp.
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
  "js/text_size.js",
  "js/help_glossary.js",
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

// File -> symbols it defines/reassigns/wraps. Includes the original definitions
// (dashboard.js), the window bridge (dashboard.js, navigation.js) and every
// decorator in the chain.
const FROZEN_WRAPPERS = {
  "js/dashboard.js": ["renderMain", "showStepHelp"],
  "js/dashboard_batch_assumption_edit.js": ["renderMain"],
  "js/dashboard_decomp_roth_guardrails.js": ["renderMain"],
  "js/dashboard_decomp_tax_assumptions.js": ["renderMain"],
  "js/dashboard_source_truth_banners.js": ["renderMain", "showStepHelp"],
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

test("index.html script list and order are frozen (53 module scripts)", () => {
  assert.equal(scriptSrcs().length, 53);
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

test("wrapper chain order: base definition precedes every decorator", () => {
  const idx = (f) => FROZEN_SCRIPT_ORDER.indexOf(f);
  for (const [file, syms] of Object.entries(FROZEN_WRAPPERS)) {
    if (file === "js/dashboard.js" || file === "js/navigation.js") continue;
    assert.ok(idx(file) > idx("js/dashboard.js"), `${file} must load after dashboard.js (${syms})`);
  }
  // Decorators run last-installed-outermost; freeze their relative order.
  const chain = [
    "js/dashboard_decomp_tax_assumptions.js",
    "js/dashboard_decomp_roth_guardrails.js",
    "js/dashboard_source_truth_banners.js",
    "js/dashboard_batch_assumption_edit.js",
  ];
  assert.deepEqual([...chain].sort((a, b) => idx(a) - idx(b)), chain);
});
