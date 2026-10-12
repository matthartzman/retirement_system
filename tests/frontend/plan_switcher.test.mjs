// WP8.4: the header plan switcher (dashboard_decomp_plan_switcher.js) renders
// the plan registry: the active plan selected, every registered plan listed,
// and a Demo badge with "Exit demo" only while the demo plan is active.
//
// Run with: node --test tests/frontend/

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

const userPlan = { plan_id: "plan", name: "My Plan", kind: "user", path: "/w/plan.rpx", active: true, exists: true };
const demoPlan = { plan_id: "demo", name: "Demo plan (Alex & Morgan)", kind: "demo", path: "/w/demo.rpx", active: false, exists: true };

describe("planSwitcherHtml", () => {
  test("renders nothing before the registry has been fetched", () => {
    assert.equal(sandbox.planSwitcherHtml(null), "");
  });

  test("lists every plan with the active one selected and no demo badge", () => {
    const html = sandbox.planSwitcherHtml({ plans: [userPlan, demoPlan], active: userPlan, demo_active: false });
    assert.match(html, /<option value="plan" selected>My Plan<\/option>/);
    assert.match(html, /<option value="demo">Demo plan \(Alex &amp; Morgan\) \(demo\)<\/option>/);
    assert.match(html, /onchange="switchPlanFromSelect\(this.value\)"/);
    assert.doesNotMatch(html, /Exit demo/);
  });

  test("shows the Demo badge and Exit demo while the demo is active", () => {
    const active = { ...demoPlan, active: true };
    const html = sandbox.planSwitcherHtml({ plans: [{ ...userPlan, active: false }, active], active, demo_active: true });
    assert.match(html, /<option value="demo" selected>/);
    assert.match(html, /plan-demo-badge/);
    assert.match(html, /onclick="openCurrentPlan\(\)">Exit demo<\/button>/);
  });

  test("a plan whose file is missing is listed but cannot be chosen", () => {
    const gone = { plan_id: "old", name: "Old", kind: "user", path: "/x/old.rpx", active: false, exists: false };
    const html = sandbox.planSwitcherHtml({ plans: [userPlan, gone], active: userPlan, demo_active: false });
    assert.match(html, /<option value="old" disabled>Old \(file missing\)<\/option>/);
  });
});
