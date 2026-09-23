// W10b (#329 §4.7): the row badge + section banner disclosing that a
// section's numbers are live optimizer output, re-derived on every build.
//
// Built on dashboard_source_truth_banners.js's own SOURCE_TRUTH_STEPS/badge
// machinery -- see that file's LIVE_OPTIMIZER_MODES comment for why the
// scope is exactly the three "policy adoption (mode switch)" optimizers
// §4.3 names (Roth Conversion, HSA Drawdown, Asset Allocation) and why the
// badge marks the mode row itself rather than guessing which downstream
// fields the engine ignores once optimizing.
//
// liveOptimizerRowBadges()/liveOptimizerSectionBanners() themselves are
// DOM-writing wiring, exercised nowhere in this file's own pre-existing code
// either (no test file covered dashboard_source_truth_banners.js before this
// workstream -- grep confirms it, and load_dashboard.mjs's shared sandbox
// deliberately does NOT load this file: it monkey-patches the shared
// sandbox's `renderMain`, and every OTHER test using that loader calls
// (patched) renderMain() against a deliberately minimal DOM stub that lacks
// what decorateGlossary()/applyEnhancements() need -- confirmed by trying it
// and watching four unrelated suites fail on "root.querySelectorAll is not a
// function"). This file loads dashboard_source_truth_banners.js on its own,
// in isolation, so nothing here can leak into another suite's sandbox.
//
// What's tested: everything the DOM-writing functions call that IS pure --
// the live-mode classification each optimizer already computes for its own
// input renderer (rothPolicyIsOptimizer, allocationModeIsComputed -- both
// take their value as a parameter already, via the real, shared
// loadDashboardSandbox()) and the two markup builders this workstream adds
// (liveOptimizerBadgeHtml/liveOptimizerBannerHtml), split out from the DOM-
// insertion functions the same way sourceTruthHtml() is already split from
// insertAfterPaneHead().

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
// Values built by the vm sandbox's own Array (a different realm) fail
// assert.deepEqual's reference-equality-of-structure check even when their
// contents match -- see plan_features.test.mjs's identical `here()`.
const here = (a) => Array.from(a);

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BANNERS_PATH = path.join(
  __dirname,
  "..",
  "..",
  "frontend",
  "js",
  "dashboard_source_truth_banners.js",
);

// A purpose-built, minimal sandbox for this ONE file, evaluated alone.
// dashboard_source_truth_banners.js's own top-level code only reaches
// outside itself through `try { ... } catch (_e) {}`-guarded reads of
// renderMain/showStepHelp (both absent here, both swallowed) and
// installShortcuts()'s document.addEventListener call (stubbed below) --
// applyEnhancements() itself is never invoked during load, because setTimeout
// here never calls back, exactly like load_dashboard.mjs's own stub. What
// this buys over adding the file to the shared loader: none of its
// window-bridged functions or its renderMain monkey-patch exist in any other
// test's sandbox.
function loadBannersSandbox() {
  const src = fs.readFileSync(BANNERS_PATH, "utf8");
  const noop = () => {};
  const box = {
    window: {},
    document: {
      addEventListener: noop,
      readyState: "complete",
      querySelector: () => null,
    },
    localStorage: { getItem: () => null, setItem: noop, removeItem: noop },
    setTimeout: () => 0,
    console,
  };
  box.globalThis = box;
  vm.createContext(box);
  new vm.Script(src, { filename: "dashboard_source_truth_banners.js" }).runInContext(box);
  return box;
}

const R = loadBannersSandbox().window.RPDashboardRoadmap11;

describe("rothPolicyIsOptimizer (shared by renderRothConversion and the live-optimizer banner)", () => {
  test("every auto-optimize policy spelling counts as live", () => {
    for (const p of [
      "optimize",
      "optimize_terminal_tax",
      "terminal_tax_optimize",
      "balanced_optimize",
      "balanced_retirement",
    ]) {
      assert.equal(sandbox.rothPolicyIsOptimizer(p), true, p);
    }
  });

  test("an explicit, non-optimizing policy is not live", () => {
    for (const p of [
      "fill_to_bracket",
      "fixed_dollar",
      "none",
      "fill_to_irmaa",
      "",
    ]) {
      assert.equal(sandbox.rothPolicyIsOptimizer(p), false, p);
    }
  });
});

describe("allocationModeIsComputed (reused unchanged from dashboard_decomp_allocation_optimizer.js)", () => {
  test("user_target is the only non-live mode", () => {
    assert.equal(sandbox.allocationModeIsComputed("user_target"), false);
  });

  test("every computed mode is live", () => {
    for (const m of [
      "optimizer_recommendation",
      "max_sharpe",
      "tangency",
      "real_loss_aware",
    ]) {
      assert.equal(sandbox.allocationModeIsComputed(m), true, m);
    }
  });
});

describe("hsaWithdrawalModeValue", () => {
  test("defaults to spend_as_needed with no HSA mode row present", () => {
    // Mirrors rothPolicyValue()/irmaaModeValue()'s own no-row default -- see
    // dashboard_decomp_allocation_optimizer.js. `rows` is a module-scoped
    // `let` the vm sandbox cannot be seeded with from outside (see
    // module_off_impact_warning.test.mjs's own note on this), so the empty-
    // rows default is what every load starts from.
    assert.equal(sandbox.hsaWithdrawalModeValue(), "spend_as_needed");
  });
});

describe("liveOptimizerModes registry", () => {
  test("covers exactly the three policy-adoption (mode-switch) optimizers §4.3 names", () => {
    const keys = here(R.liveOptimizerModes.map((e) => e.key)).sort();
    assert.deepEqual(keys, [
      "asset_allocation",
      "hsa_drawdown",
      "roth_conversion",
    ]);
  });

  test("each entry's isLive() runs standalone without throwing (its own try/catch swallows the missing globals)", () => {
    for (const entry of R.liveOptimizerModes) {
      assert.equal(typeof entry.isLive(), "boolean", entry.key);
    }
  });
});

describe("liveOptimizerBadgeHtml", () => {
  test("names the optimizer and carries the live-optimizer marker", () => {
    const html = R.liveOptimizerBadgeHtml("Roth Conversion");
    assert.match(html, /badge live/);
    assert.match(html, /data-roadmap11="live-optimizer-badge"/);
    assert.match(html, /Live optimizer output/);
    assert.match(html, /Roth Conversion/);
  });

  test("escapes an untrusted title", () => {
    const html = R.liveOptimizerBadgeHtml('<script>alert(1)</script>');
    assert.doesNotMatch(html, /<script>/);
    assert.match(html, /&lt;script&gt;/);
  });
});

describe("liveOptimizerBannerHtml", () => {
  test("states the section re-optimizes every build", () => {
    const html = R.liveOptimizerBannerHtml("HSA Drawdown", 42);
    assert.match(html, /live-optimizer-banner/);
    assert.match(html, /HSA Drawdown/);
    assert.match(html, /re-optimizes on every build/);
  });

  test("the jump button targets the mode row's index when one was found", () => {
    const html = R.liveOptimizerBannerHtml("Asset Allocation", 7);
    assert.match(html, /jumpToLiveOptimizerRow\(7\)/);
    assert.match(html, /Change to a fixed strategy/);
  });

  test("no dead jump button when the mode row could not be found", () => {
    const html = R.liveOptimizerBannerHtml("Roth Conversion", null);
    assert.doesNotMatch(html, /jumpToLiveOptimizerRow/);
    assert.doesNotMatch(html, /<button/);
  });

  test("escapes an untrusted title", () => {
    const html = R.liveOptimizerBannerHtml('<script>alert(1)</script>', null);
    assert.doesNotMatch(html, /<script>/);
    assert.match(html, /&lt;script&gt;/);
  });
});
