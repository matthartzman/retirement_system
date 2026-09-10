// Bug: clicking "Build Reports" from Reports & Review's own header (which
// already shows Impact inline -- renderReportsAndReview()/
// renderImpactSectionContent()) landed the user on the OLD standalone
// build_impact step instead. Root cause: renderBuildImpactAfterBuild()
// unconditionally set activeStep = "build_impact" after every non-download
// build, regardless of where the build was started -- runBuild() had
// already captured stepBeforeBuild for exactly this purpose but never used
// it. Reported live: "tried to download dirty workbook, clicked cancel,
// then rebuild button clicked" -- expected to stay on Reports & Review,
// landed on Impact & Build History instead.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

function freshSandbox(startingStep) {
  const sandbox = loadDashboardSandbox();
  sandbox.window.activeStep = startingStep;
  sandbox.window.planLoaded = false;
  sandbox.renderMain = () => {};
  sandbox.setAppControls = () => {};
  sandbox.showStepHelp = () => {};
  sandbox.showMessage = () => {};
  sandbox.hideBuildOverlay = () => {};
  sandbox.window.scrollTo = () => {};
  sandbox.document.querySelector = () => null;
  return sandbox;
}

describe("renderBuildImpactAfterBuild: stays put when the build started on Reports & Review", () => {
  test("originStep 'reports_and_review' does not force-navigate away", () => {
    const sandbox = freshSandbox("reports_and_review");
    sandbox.renderBuildImpactAfterBuild("Build successful.", "reports_and_review");
    assert.equal(sandbox.window.activeStep, "reports_and_review");
  });

  test("originStep 'planning_workbench' still jumps to build_impact (unchanged prior behavior)", () => {
    const sandbox = freshSandbox("planning_workbench");
    sandbox.renderBuildImpactAfterBuild("Build successful.", "planning_workbench");
    assert.equal(sandbox.window.activeStep, "build_impact");
  });

  test("no originStep argument (e.g. an older caller) preserves the original always-jump behavior", () => {
    const sandbox = freshSandbox("start");
    sandbox.renderBuildImpactAfterBuild("Build successful.");
    assert.equal(sandbox.window.activeStep, "build_impact");
  });

  test("originStep 'build_impact' itself is a no-op (already there)", () => {
    const sandbox = freshSandbox("build_impact");
    sandbox.renderBuildImpactAfterBuild("Build successful.", "build_impact");
    assert.equal(sandbox.window.activeStep, "build_impact");
  });
});
