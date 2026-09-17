// Ticket 323 / Phase 5: requestAllocationPreview() and its completion guard
// gate on activeStep === "allocation_assets" || "distribution_strategy". Both
// of those ids now redirect to strategy_optimize (see SECTION_REDIRECTS in
// navigation.js) -- activeStep can never actually equal either of them any
// more once a plan is loaded and the reader navigates there. Left unfixed,
// the preview would silently never fire on the redesigned nav: the request
// guard returns early, and even a preview started before the redesign landed
// would find its own completion guard false and drop the result on the
// floor.
//
// distribution_strategy is retired outright in this commit (renderMain's
// branch for it and renderDistributionStrategy() are both deleted), so this
// is not "add a third accepted value" -- allocation_assets and
// distribution_strategy are both replaced by strategy_optimize, the only id
// the allocation panel is ever actually shown under now.

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

beforeEach(() => {
  sandbox.window.planLoaded = true;
  sandbox.window.allocationPreview = null;
  sandbox.window.allocationPreviewKey = "";
  sandbox.window.allocationPreviewLoading = false;
  sandbox.window.allocationPreviewSeq = 0;
  sandbox.window.rows = [];
  sandbox.api = async () => ({ success: true, target: {} });
});

describe("requestAllocationPreview() fires on the screen that actually hosts the panel", () => {
  test("fires when activeStep is strategy_optimize", () => {
    sandbox.window.activeStep = "strategy_optimize";
    let called = false;
    sandbox.api = async (...args) => {
      called = true;
      return { success: true, target: {} };
    };
    sandbox.requestAllocationPreview();
    assert.ok(called, "the preview request never fired on strategy_optimize");
  });

  test("does not fire on an unrelated step", () => {
    sandbox.window.activeStep = "holdings";
    let called = false;
    sandbox.api = async () => {
      called = true;
      return { success: true };
    };
    sandbox.requestAllocationPreview();
    assert.ok(!called, "the preview request fired on a step that doesn't host the panel");
  });

  test("the retired legacy ids no longer trigger it -- they never reach activeStep any more", () => {
    for (const legacy of ["allocation_assets", "distribution_strategy"]) {
      sandbox.window.activeStep = legacy;
      let called = false;
      sandbox.api = async () => {
        called = true;
        return { success: true };
      };
      sandbox.requestAllocationPreview();
      assert.ok(
        !called,
        `${legacy} still triggers the preview directly -- it must go through strategy_optimize now`,
      );
    }
  });
});
