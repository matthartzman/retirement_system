// WP5.1: the Plan Features tier picker's decision logic
// (frontend/js/dashboard_decomp_plan_tiers.js). The presets, the profile and
// what a pick changes are the server's (module_catalog); these pure helpers
// only turn them into the page's strings, so they are exercised here with
// payloads shaped as config_service / plan_tier_service serve them.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

const PRESETS = {
  default: "expert",
  switchable: ["roth_conversion_plan", "estate_legacy_plan", "heloc", "equity_compensation"],
  tiers: [
    { key: "simple", label: "Simple", description: "The essentials.", features: ["roth_conversion_plan"] },
    { key: "standard", label: "Standard", description: "Adds estate.", features: ["roth_conversion_plan", "estate_legacy_plan"] },
    { key: "advanced", label: "Advanced", description: "Adds HELOC.", features: ["roth_conversion_plan", "estate_legacy_plan", "heloc"] },
    { key: "expert", label: "Expert", description: "Everything.", features: ["roth_conversion_plan", "estate_legacy_plan", "heloc", "equity_compensation"] },
  ],
};

const ADVANCED_CUSTOMIZED = {
  tier: "advanced",
  tier_stored: true,
  customized: true,
  label: "Advanced (customized)",
  differing: ["heloc", "equity_compensation"],
};

describe("tierCardsHtml", () => {
  test("renders the four tiers in order with their descriptions and page counts", () => {
    const html = sandbox.tierCardsHtml(PRESETS, ADVANCED_CUSTOMIZED, { simple: 9, standard: 14, advanced: 19, expert: 21 });
    const names = [...html.matchAll(/class="pf-tier-name">([^<]+)</g)].map((m) => m[1]);
    assert.deepEqual(names, ["Simple", "Standard", "Advanced", "Expert"]);
    assert.match(html, /The essentials\./);
    assert.match(html, />9 pages</);
    assert.match(html, /role="group" aria-label="Plan tier"/);
  });

  test("highlights the plan's tier, and only that one, for sighted and screen-reader users", () => {
    const html = sandbox.tierCardsHtml(PRESETS, ADVANCED_CUSTOMIZED, {});
    assert.equal((html.match(/aria-pressed="true"/g) || []).length, 1);
    assert.match(html, /pf-tier-card selected" aria-pressed="true"[^>]*pickPlanTier\('advanced'\)/);
    assert.equal((html.match(/>Current</g) || []).length, 1);
    // no counts given: no "pages" text rather than "undefined pages"
    assert.doesNotMatch(html, /undefined|NaN|pages/);
  });

  test("a plan with no profile yet highlights the default tier (Expert)", () => {
    const html = sandbox.tierCardsHtml(PRESETS, {}, {});
    assert.match(html, /selected" aria-pressed="true"[^>]*pickPlanTier\('expert'\)/);
  });

  test("renders nothing before the presets have loaded", () => {
    assert.equal(sandbox.tierCardsHtml(undefined, undefined, undefined), "");
  });
});

describe("tierStatusHtml", () => {
  test("customized: says how many switches differ and offers the reset", () => {
    const html = sandbox.tierStatusHtml(ADVANCED_CUSTOMIZED, PRESETS);
    assert.match(html, /Plan tier: <b>Advanced \(customized\)<\/b>/);
    assert.match(html, /2 switches differ from the Advanced preset/);
    assert.match(html, /onclick="pickPlanTier\('advanced'\)">Reset to Advanced preset</);
  });

  test("matching the preset: no reset action", () => {
    const html = sandbox.tierStatusHtml({ tier: "simple", tier_stored: true, customized: false, label: "Simple", differing: [] }, PRESETS);
    assert.match(html, /<b>Simple<\/b>/);
    assert.doesNotMatch(html, /Reset to/);
  });

  test("no tier picked yet: explains that nothing changes until one is picked", () => {
    const html = sandbox.tierStatusHtml(
      { tier: "expert", tier_stored: false, customized: true, label: "Expert (customized)", differing: ["heloc"] },
      PRESETS,
    );
    assert.match(html, /1 switch differs from the Expert preset/);
    assert.match(html, /No tier picked yet/);
  });
});

describe("tierDiffBadgeHtml", () => {
  test("marks a switch that differs from the preset, saying what the preset has", () => {
    const on = sandbox.tierDiffBadgeHtml("equity_compensation", ADVANCED_CUSTOMIZED, PRESETS);
    assert.match(on, /class="badge pf-tier-diff" title="Advanced preset: off">Differs from Advanced preset</);
    const off = sandbox.tierDiffBadgeHtml("heloc", ADVANCED_CUSTOMIZED, PRESETS);
    assert.match(off, /title="Advanced preset: on"/);
  });

  test("says nothing for a switch that matches, or before the profile loads", () => {
    assert.equal(sandbox.tierDiffBadgeHtml("roth_conversion_plan", ADVANCED_CUSTOMIZED, PRESETS), "");
    assert.equal(sandbox.tierDiffBadgeHtml("heloc", {}, PRESETS), "");
    assert.equal(sandbox.tierDiffBadgeHtml("heloc", undefined, undefined), "");
  });
});

describe("tierPreviewHtml", () => {
  const PREVIEW = {
    tier: "simple",
    label: "Simple",
    turn_on: [],
    turn_off: [
      { key: "estate_legacy_plan", name: "Estate", entered_rows: null, engine_participation: false },
      { key: "existing_life_insurance", name: "Existing Life Insurance", entered_rows: 4, engine_participation: false },
      { key: "equity_compensation", name: "Equity Compensation", entered_rows: 0, engine_participation: true },
    ],
    engine_ignored: [{ key: "equity_compensation", name: "Equity Compensation" }],
    unchanged: false,
  };

  test("lists what turns off with the shared 'Off · N rows entered' wording and the engine warning", () => {
    const html = sandbox.tierPreviewHtml(PREVIEW, () => null);
    assert.match(html, /Turns off \(3\)/);
    assert.match(html, /Existing Life Insurance <span class="pf-retained">Off · 4 rows entered<\/span>/);
    // a feature with no entered rows gets no count
    assert.doesNotMatch(html, /Estate <span class="pf-retained">/);
    assert.match(html, /While Equity Compensation is off, the projection ignores it\. Your entries are kept\./);
    assert.doesNotMatch(html, /Turns on/);
    assert.match(html, /Your entered data is kept/);
  });

  test("prefers the page's own count over the server's", () => {
    const html = sandbox.tierPreviewHtml(PREVIEW, (key) => (key === "estate_legacy_plan" ? 1 : null));
    assert.match(html, /Estate <span class="pf-retained">Off · 1 row entered<\/span>/);
    assert.match(html, /Off · 4 rows entered/); // null locally: the server's count stands
  });

  test("lists what turns on", () => {
    const html = sandbox.tierPreviewHtml(
      { tier: "expert", label: "Expert", turn_on: [{ key: "heloc", name: "HELOC" }], turn_off: [], engine_ignored: [], unchanged: false },
      null,
    );
    assert.match(html, /Turns on \(1\)<\/b><\/p><ul class="inapp-modal-list"><li>HELOC<\/li>/);
    assert.doesNotMatch(html, /Turns off/);
  });

  test("an unchanged pick says it only records the tier", () => {
    const html = sandbox.tierPreviewHtml({ tier: "simple", label: "Simple", unchanged: true }, null);
    assert.match(html, /already matches the Simple preset/);
  });
});

describe("tierPageCount", () => {
  const STEPS = [
    { id: "start", group: "Plan Status" },
    { id: "roth_conversion", group: "Taxes" },
    { id: "estate", group: "Estate & Legacy" },
    { id: "heloc_strategy", group: "Investments & Property" },
    { id: "review", group: null },
    { id: "detailed_results", group: "Reports & Review", hidden: true },
  ];
  const GATES = { roth_conversion: "roth_conversion_plan", estate: "estate_legacy_plan", heloc_strategy: "heloc" };
  const gate = (stepId, isOn) => (GATES[stepId] ? !isOn(GATES[stepId]) : false);

  test("counts the visible pages the preset's features leave ungated", () => {
    assert.equal(sandbox.tierPageCount(STEPS, ["roth_conversion_plan"], gate), 2);
    assert.equal(sandbox.tierPageCount(STEPS, PRESETS.tiers[3].features, gate), 4);
  });

  test("grows with the tier, because the presets are cumulative", () => {
    const counts = PRESETS.tiers.map((t) => sandbox.tierPageCount(STEPS, t.features, gate));
    assert.deepEqual(Array.from(counts), [2, 3, 4, 4]);
  });

  test("the live gate takes a predicate: stepGatedByOptionalModule answers for a hypothetical switch set", () => {
    // With an isOn predicate the real gate never reads the live plan; a step no
    // gate names stays visible whatever the preset.
    assert.equal(sandbox.stepGatedByOptionalModule("start", () => false), false);
  });
});

describe("field tier filter (WP5.2)", () => {
  const rows = [
    { row_index: 1, label: "a", min_tier: "simple" },
    { row_index: 2, label: "b", min_tier: "standard" },
    { row_index: 3, label: "c", min_tier: "advanced" },
    { row_index: 4, label: "d", min_tier: "expert" },
    { row_index: 5, label: "e", min_tier: "" },
  ];
  const ids = (xs) => [...xs.map((r) => r.row_index)];

  test("a Standard plan hides advanced and expert fields; untiered rows stay", () => {
    const { shown, hidden } = sandbox.splitFieldsByTier(rows, "standard", () => false);
    assert.deepEqual(ids(shown), [1, 2, 5]);
    assert.deepEqual(ids(hidden), [3, 4]);
  });

  test("an Expert plan (the default) hides nothing", () => {
    const { shown, hidden } = sandbox.splitFieldsByTier(rows, "expert", () => false);
    assert.equal(shown.length, 5);
    assert.equal(hidden.length, 0);
  });

  test("a required field that is still empty is never hidden", () => {
    const { shown } = sandbox.splitFieldsByTier(rows, "simple", (r) => r.row_index === 4);
    assert.deepEqual(ids(shown), [1, 4, 5]);
  });

  test("an unknown plan tier hides nothing", () => {
    assert.equal(sandbox.splitFieldsByTier(rows, undefined, () => false).hidden.length, 0);
  });

  test("the control names how many fields are behind it", () => {
    assert.equal(sandbox.fieldTierControlHtml("income", 0, false), "");
    assert.match(sandbox.fieldTierControlHtml("income", 2, false), /Show advanced \(2 more fields\)/);
    assert.match(sandbox.fieldTierControlHtml("income", 1, false), /\(1 more field\)/);
    assert.match(sandbox.fieldTierControlHtml("income", 2, true), /Hide advanced fields/);
  });
});

describe("interview and self-suggest (WP5.3)", () => {
  const questions = [
    { id: "detail", text: "How much detail?", kind: "choice", options: [{ value: "simple", label: "Basics" }, { value: "expert", label: "All" }] },
    { id: "heloc", text: "Do you have a HELOC?", kind: "yes_no" },
  ];

  test("renders each question and keeps the suggestion button disabled until the tier question is answered", () => {
    const html = sandbox.interviewHtml({ questions, answers: {}, result: null });
    assert.match(html, /How much detail\?/);
    assert.match(html, /Do you have a HELOC\?/);
    assert.match(html, /disabled onclick="suggestFromInterview\(\)"/);
    const ready = sandbox.interviewHtml({ questions, answers: { detail: "simple", heloc: false }, result: null });
    assert.doesNotMatch(ready, /disabled onclick/);
    assert.equal((ready.match(/checked/g) || []).length, 2);
  });

  test("the result names the tier and the extra features", () => {
    const html = sandbox.interviewResultHtml({ label: "Simple", tier: "simple", reasons: [{ key: "heloc", name: "HELOC" }] });
    assert.match(html, /Suggested: Simple/);
    assert.match(html, /plus 1 extra feature/);
    assert.match(html, /<li>HELOC<\/li>/);
    assert.equal(sandbox.interviewResultHtml(null), "");
  });

  test("self-suggest rows name the feature and offer a turn-on button", () => {
    const html = sandbox.featureSuggestionsHtml([{ key: "heloc", name: "HELOC", entered_rows: 3, text: "Turn on HELOC? You have 3 rows entered for it." }]);
    assert.match(html, /Turn on HELOC\? You have 3 rows entered for it\./);
    assert.match(html, /setPlanFeatureSwitch\('heloc', true\)/);
    assert.equal(sandbox.featureSuggestionsHtml([]), "");
  });
});
