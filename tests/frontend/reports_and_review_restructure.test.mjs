// Ticket 301: Reports & Review is primarily the Impact page now -- Build and
// Download live as buttons on that page (not separate tabs), and Plan Data
// Review / Build History are collapsible <details> sections on it instead
// of their own tabs.
//
// Executable test against the real render output rather than a source-text
// assertion, per this repo's existing convention (a string search would
// keep passing if the markup moved without the actual structure changing).

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

function freshSandbox() {
  const sandbox = loadDashboardSandbox();
  // loadBuildHistory() unconditionally reloads from localStorage (stubbed to
  // always return null), clobbering whatever buildHistory this test sets --
  // no-op it so the pre-set value sticks.
  sandbox.loadBuildHistory = () => {};
  sandbox.dirty = new Map();
  return sandbox;
}

describe("Reports & Review restructure (ticket 301)", () => {
  test("no build history yet: Build/Download buttons and Plan Data Review are present, no leftover 'Back to Download Reports'", () => {
    const sandbox = freshSandbox();
    sandbox.window.buildHistory = [];
    const out = sandbox.renderBuildImpactPage();
    assert.match(out, /Build Reports/);
    assert.match(out, /Download Workbook/);
    assert.match(out, /class="plan-data-review-collapsible"/);
    assert.doesNotMatch(out, /Back to Download Reports/);
  });

  test("with build history: Build History is a collapsible <details>, not a plain always-open list", () => {
    const sandbox = freshSandbox();
    sandbox.window.RetirementPlanningWorkbench = { renderBuildImpactContext: () => "" };
    sandbox.window.buildHistory = [
      { id: "1", kpi: { inheritable_nw: 100, lifetime_tax: 10, mc_success: 0.9 }, changes: [] },
    ];
    const out = sandbox.renderBuildImpactPage();
    assert.match(out, /<details class="build-history-collapsible">/);
    assert.match(out, /<summary class="section-header">Build History/);
    assert.match(out, /Build Reports/);
    assert.match(out, /Download Workbook/);
    assert.match(out, /class="plan-data-review-collapsible"/);
  });
});

// Reports & Review redesign: the 3-tab strip (Preflight/Impact/Results) is
// gone. The page always shows Impact (unchanged content -- see the
// renderBuildImpactPage() tests above, which cover the same
// renderImpactSectionContent() this page also renders) and Plan Data Review
// together; Preflight folds into a compact note and Results becomes a link
// to its own standalone page instead of a tab.
describe("Reports & Review redesign: no tabs, two always-visible sections", () => {
  function freshSandbox() {
    const sandbox = loadDashboardSandbox();
    sandbox.loadBuildHistory = () => {};
    sandbox.window.dirty = new Map();
    sandbox.window.rows = [];
    sandbox.window.buildHistory = [];
    return sandbox;
  }

  test("renders with no tab strip markup", () => {
    const sandbox = freshSandbox();
    const out = sandbox.renderReportsAndReview();
    assert.doesNotMatch(out, /workspace-tabs/);
    assert.doesNotMatch(out, /role="tablist"/);
  });

  test("Impact content is always visible; Plan Data Review is its own section, collapsed by default", () => {
    const sandbox = freshSandbox();
    const out = sandbox.renderReportsAndReview();
    assert.match(out, /<h3>No build history yet<\/h3>/); // renderImpactSectionContent()'s empty state
    // Its own <details> (not nested inside Impact's plan-data-review-collapsible,
    // and not force-opened) -- collapsed is the default <details> state whenever
    // the "open" attribute is absent.
    assert.match(out, /<details class="plan-data-review-section">/);
    assert.doesNotMatch(out, /<details class="plan-data-review-section" open>/);
    assert.doesNotMatch(out, /plan-data-review-collapsible/);
  });

  test("does not embed a Results link in the body -- that lives in the header now (View Workbook)", () => {
    const sandbox = freshSandbox();
    const out = sandbox.renderReportsAndReview();
    assert.doesNotMatch(out, /data-step-id="detailed_results"/);
  });

  test("no Refresh Status button on this page", () => {
    const sandbox = freshSandbox();
    const out = sandbox.renderReportsAndReview();
    assert.doesNotMatch(out, /Refresh Status/);
  });

  test("no required fields missing: no preflight warning note", () => {
    const sandbox = freshSandbox();
    const out = sandbox.renderReportsAndReview();
    assert.doesNotMatch(out, /required field/);
  });
});

describe("Reports & Review header: Build/Download buttons (primaryActionForStep)", () => {
  function freshSandbox() {
    const sandbox = loadDashboardSandbox();
    sandbox.window.dirty = new Map();
    return sandbox;
  }

  test("Build is active when there are unsaved edits", () => {
    const sandbox = freshSandbox();
    sandbox.window.dirty.set(1, "x");
    sandbox.window.lastBuildOk = true;
    assert.equal(sandbox.reportsAndReviewCanBuild(), true);
  });

  test("Build is active on a never-built plan even with no edits", () => {
    const sandbox = freshSandbox();
    sandbox.window.lastBuildOk = false;
    assert.equal(sandbox.reportsAndReviewCanBuild(), true);
  });

  test("Build is inactive once built and nothing has changed since", () => {
    const sandbox = freshSandbox();
    sandbox.window.lastBuildOk = true;
    assert.equal(sandbox.reportsAndReviewCanBuild(), false);
  });

  test("View Workbook sits between Build Reports and Download Workbook, linking to the standalone Results page", () => {
    const sandbox = freshSandbox();
    sandbox.window.lastBuildOk = true;
    const out = sandbox.primaryActionForStep("reports_and_review");
    const buildIdx = out.indexOf("Build Reports");
    const viewIdx = out.indexOf("View Workbook");
    const downloadIdx = out.indexOf("Download Workbook");
    assert.ok(buildIdx >= 0 && viewIdx > buildIdx && downloadIdx > viewIdx, out);
    assert.match(out, /data-step-id="detailed_results"[^>]*>View Workbook</);
  });
});

// Gated on planStateArtifactsReady() (do report output files actually
// exist), not lastBuildOk: updateUnsaved() (row_model.js) forces lastBuildOk
// false as soon as ANY input is dirty, regardless of whether a build has
// ever succeeded -- exactly the case this button needs to allow (downloading
// the last real build despite newer unsaved edits). It downloads via
// performFileDownload() (dashboard.js), not downloadFile(), for the same
// reason: downloadFile()'s own lastBuildOk gate would otherwise refuse right
// after the user has just confirmed "download anyway".
describe("reportsAndReviewDownloadWorkbook", () => {
  function freshSandbox() {
    const sandbox = loadDashboardSandbox();
    sandbox.window.dirty = new Map();
    return sandbox;
  }

  test("refuses with a message when no report artifacts exist yet", async () => {
    const sandbox = freshSandbox();
    sandbox.planStateArtifactsReady = () => false;
    const messages = [];
    sandbox.showMessage = (msg) => messages.push(msg);
    let downloaded = false;
    sandbox.performFileDownload = () => {
      downloaded = true;
    };
    await sandbox.reportsAndReviewDownloadWorkbook();
    assert.equal(downloaded, false);
    assert.match(messages[0], /Build reports before downloading/);
  });

  test("downloads immediately, no confirm, when planStateFresh() says the build is current", async () => {
    // planStateFresh() -- not unsavedChangeCount() alone -- is the gate: it's
    // the same "is it stale" signal the left-nav Stale badge uses (stepButton(),
    // reportStale in row_model.js), so this button agrees with what the rest
    // of the app is telling the user. A prior version of this check used
    // unsavedChangeCount() only, which disagreed with the badge right after a
    // plain page reload (lastBuildOk resets every session, planStateFresh()
    // reflects that, unsavedChangeCount() alone does not) -- reproduced live,
    // see the comment on reportsAndReviewDownloadWorkbook() itself.
    const sandbox = freshSandbox();
    sandbox.planStateArtifactsReady = () => true;
    sandbox.planStateFresh = () => true;
    let confirmCalled = false;
    sandbox.showInAppConfirm = () => {
      confirmCalled = true;
      return Promise.resolve(true);
    };
    let downloadedUrl = null;
    sandbox.performFileDownload = (url) => {
      downloadedUrl = url;
    };
    await sandbox.reportsAndReviewDownloadWorkbook();
    assert.equal(confirmCalled, false);
    assert.equal(downloadedUrl, "/api/xlsx");
  });

  test("warns even with zero unsaved edits when planStateFresh() says the build is stale (e.g. a fresh reload)", async () => {
    const sandbox = freshSandbox();
    sandbox.planStateArtifactsReady = () => true;
    sandbox.planStateFresh = () => false; // e.g. lastBuildOk reset by a reload, not an edit
    let confirmCalled = false;
    sandbox.showInAppConfirm = () => {
      confirmCalled = true;
      return Promise.resolve(false);
    };
    let downloaded = false;
    sandbox.performFileDownload = () => {
      downloaded = true;
    };
    await sandbox.reportsAndReviewDownloadWorkbook();
    assert.equal(confirmCalled, true);
    assert.equal(downloaded, false);
  });

  test("stale build: confirming downloads the last build's workbook as-is", async () => {
    const sandbox = freshSandbox();
    sandbox.planStateArtifactsReady = () => true;
    sandbox.window.dirty.set(1, "x");
    sandbox.showInAppConfirm = () => Promise.resolve(true);
    let downloadedUrl = null;
    sandbox.performFileDownload = (url) => {
      downloadedUrl = url;
    };
    await sandbox.reportsAndReviewDownloadWorkbook();
    assert.equal(downloadedUrl, "/api/xlsx");
  });

  test("stale build: cancelling does not download", async () => {
    const sandbox = freshSandbox();
    sandbox.planStateArtifactsReady = () => true;
    sandbox.window.dirty.set(1, "x");
    sandbox.showInAppConfirm = () => Promise.resolve(false);
    let downloaded = false;
    sandbox.performFileDownload = () => {
      downloaded = true;
    };
    await sandbox.reportsAndReviewDownloadWorkbook();
    assert.equal(downloaded, false);
  });
});

// setAppControls() (row_model.js) is the OTHER half of the disabled-state
// story: primaryActionForStep() (dashboard.js) computes the initial disabled
// attribute, but setAppControls() runs after every render and unconditionally
// re-derives .disabled for every [data-requires-app="1"] button -- without
// the data-requires-edit/data-requires-artifacts markers it checks here, it
// would silently clear whatever the initial render decided (a real bug this
// suite caught live in the browser, not something the render-output-only
// tests above could have caught).
describe("setAppControls: Reports & Review's Build/Download markers", () => {
  function freshSandbox() {
    const sandbox = loadDashboardSandbox();
    sandbox.document.querySelectorAll = (sel) =>
      sel === '[data-requires-app="1"]' ? sandbox.__testButtons || [] : [];
    return sandbox;
  }
  function fakeButton(attrs) {
    const store = { ...attrs };
    return {
      getAttribute: (name) => (name in store ? store[name] : null),
      disabled: false,
    };
  }

  test("a data-requires-edit button is disabled when reportsAndReviewCanBuild() is false", () => {
    const sandbox = freshSandbox();
    const btn = fakeButton({ "data-requires-edit": "1" });
    sandbox.__testButtons = [btn];
    sandbox.reportsAndReviewCanBuild = () => false;
    sandbox.setAppControls(true);
    assert.equal(btn.disabled, true);
  });

  test("a data-requires-edit button is enabled when reportsAndReviewCanBuild() is true", () => {
    const sandbox = freshSandbox();
    const btn = fakeButton({ "data-requires-edit": "1" });
    sandbox.__testButtons = [btn];
    sandbox.reportsAndReviewCanBuild = () => true;
    sandbox.setAppControls(true);
    assert.equal(btn.disabled, false);
  });

  test("a data-requires-artifacts button is disabled when planStateArtifactsReady() is false", () => {
    const sandbox = freshSandbox();
    const btn = fakeButton({ "data-requires-artifacts": "1" });
    sandbox.__testButtons = [btn];
    sandbox.planStateArtifactsReady = () => false;
    sandbox.setAppControls(true);
    assert.equal(btn.disabled, true);
  });

  test("a data-requires-artifacts button stays enabled through unsaved edits, unlike a plain data-download button", () => {
    const sandbox = freshSandbox();
    const artifactsBtn = fakeButton({ "data-requires-artifacts": "1" });
    const downloadBtn = fakeButton({ "data-download": "1" });
    sandbox.__testButtons = [artifactsBtn, downloadBtn];
    sandbox.planStateArtifactsReady = () => true;
    sandbox.window.lastBuildOk = false; // e.g. forced false by an unsaved edit
    sandbox.setAppControls(true);
    assert.equal(artifactsBtn.disabled, false);
    assert.equal(downloadBtn.disabled, true);
  });

  test("every marked button is disabled when the app itself isn't ready", () => {
    const sandbox = freshSandbox();
    const btn = fakeButton({ "data-requires-edit": "1" });
    sandbox.__testButtons = [btn];
    sandbox.reportsAndReviewCanBuild = () => true;
    sandbox.setAppControls(false);
    assert.equal(btn.disabled, true);
  });
});
