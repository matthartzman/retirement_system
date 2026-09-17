// Ticket 323 / Phase 5: validateAllocationTargetsOrMessage() bypasses setStep()
// entirely -- it pokes `activeStep = "allocation_assets"` directly and calls
// renderMain() itself, rather than going through navigation.js's setStep(),
// which is the ONLY other place in the app that resolves a legacy id through
// SECTION_REDIRECTS. That is a real, live call path (triggered from save/build
// validation when allocation targets don't sum to 100%), not something the
// redesign's redirect table can see or protect on its own.
//
// Left unfixed, a validation failure lands the reader on the bare legacy
// "allocation_assets" page -- outside the Strategy nav, with no section
// context -- instead of Strategy -> Optimize with the Asset Allocation
// section open, the only place that panel is shown anywhere else in the
// redesigned app. Confirmed by grep that this is the ONLY direct write to
// activeStep for a step id SECTION_REDIRECTS also covers (dashboard.js has
// two other direct writes, "review" and "detailed_results", neither of
// which is a retired/redirected id).

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

beforeEach(() => {
  sandbox.window.rows = [];
  sandbox.window.activeStep = "strategy_optimize";
  sandbox.allocationSelectionMode = () => "user_target";
  sandbox.allocationTargetsValid = () => false;
  sandbox.optimizerOverrideValid = () => true;
  sandbox.showMessage = () => {};
});

describe("validateAllocationTargetsOrMessage() routes through setStep (ticket 323)", () => {
  test("an invalid user_target allocation calls setStep('allocation_assets'), not a direct activeStep write", () => {
    let setStepCalledWith = null;
    sandbox.setStep = (id) => {
      setStepCalledWith = id;
    };
    const ok = sandbox.validateAllocationTargetsOrMessage();
    assert.equal(ok, false);
    assert.equal(
      setStepCalledWith,
      "allocation_assets",
      "must route through setStep() so SECTION_REDIRECTS resolves it to strategy_optimize with the Asset Allocation section open",
    );
  });

  test("an invalid optimizer_recommendation override also routes through setStep", () => {
    sandbox.allocationSelectionMode = () => "optimizer_recommendation";
    sandbox.optimizerOverrideValid = () => false;
    let setStepCalledWith = null;
    sandbox.setStep = (id) => {
      setStepCalledWith = id;
    };
    const ok = sandbox.validateAllocationTargetsOrMessage();
    assert.equal(ok, false);
    assert.equal(setStepCalledWith, "allocation_assets");
  });

  test("a valid allocation does not navigate at all", () => {
    sandbox.allocationTargetsValid = () => true;
    let called = false;
    sandbox.setStep = () => {
      called = true;
    };
    const ok = sandbox.validateAllocationTargetsOrMessage();
    assert.equal(ok, true);
    assert.ok(!called);
  });
});
