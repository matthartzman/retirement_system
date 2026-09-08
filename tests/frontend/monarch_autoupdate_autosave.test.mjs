// Finding UX-103 (system review 2026-09-07, Wave 5 item W5-8): the Monarch
// auto-update card broke the app's autosave contract -- it used a manual
// "Save setting" button with no dirty/busy indicator, and "Import now" gave
// no feedback while running. This exercises the real
// dashboard_decomp_monarch_autoupdate.js source (via loadDashboardSandbox)
// to confirm: (a) there is no manual save button any more, (b) the
// checkbox/source-dir input trigger autosave on change/blur, (c) inputs and
// buttons show a busy/disabled state while a save or run is in flight, and
// (d) the busy flags are always cleared afterward, even when the underlying
// api() call throws -- since dashboard.js's own renderMain() throws against
// this sandbox's minimal DOM stubs regardless of outcome, only the module's
// internal busy-flag bookkeeping (verified indirectly through the rendered
// HTML, since the flags are plain top-level `let`s not reified onto the vm
// sandbox object -- see monarch_autoupdate_card.test.mjs's header comment)
// is what these tests can and should observe.
//
// Run with: node --test tests/frontend/

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

function deferred() {
  let resolve, reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("Monarch auto-update card has no manual save button", () => {
  test("default-state markup contains no leftover 'Save setting' button", () => {
    const sandbox = loadDashboardSandbox();
    const html = sandbox.monarchAutoUpdateControlsHtml();
    assert.doesNotMatch(html, />\s*Save setting\s*</);
    assert.doesNotMatch(html, /saveMonarchAutoUpdatePolicy\(\)"[^>]*>\s*Save/);
  });

  test("the enable checkbox autosaves on change, not via a separate button", () => {
    const sandbox = loadDashboardSandbox();
    const html = sandbox.monarchAutoUpdateControlsHtml();
    assert.match(
      html,
      /id="monarchAutoUpdateEnabled"[^>]*onchange="[^"]*saveMonarchAutoUpdatePolicy\(\)/,
    );
  });

  test("the source-dir input autosaves on blur, not via a separate button", () => {
    const sandbox = loadDashboardSandbox();
    const html = sandbox.monarchAutoUpdateControlsHtml();
    assert.match(
      html,
      /id="monarchAutoUpdateSourceDir"[^>]*onblur="[^"]*saveMonarchAutoUpdatePolicy\(\)/,
    );
  });
});

describe("Monarch auto-update card shows busy state while saving", () => {
  test("inputs are disabled and a Saving indicator appears mid-save, and clear afterward", async () => {
    const sandbox = loadDashboardSandbox();
    const gate = deferred();
    sandbox.api = () => gate.promise;
    sandbox.document.getElementById = (id) => {
      if (id === "monarchAutoUpdateEnabled") return { checked: true };
      if (id === "monarchAutoUpdateSourceDir") return { value: "Monarch Extractor/output" };
      return { style: {}, classList: { add() {}, remove() {}, toggle() {}, contains: () => false } };
    };

    const inFlight = sandbox.saveMonarchAutoUpdatePolicy().catch(() => {});

    const busyHtml = sandbox.monarchAutoUpdateControlsHtml();
    assert.match(busyHtml, /id="monarchAutoUpdateEnabled"[^>]*disabled/);
    assert.match(busyHtml, /id="monarchAutoUpdateSourceDir"[^>]*disabled/);
    assert.match(busyHtml, /Saving…/);
    // The busy-state re-render must reflect what the user just submitted
    // (checked=true, captured from the DOM before this render), not the
    // stale pre-save server policy (enabled defaults to false at this
    // point, since monarchAutoUpdateStatus hasn't been fetched yet in this
    // test) -- a real bug caught by tests/e2e/monarch-autoupdate-card.spec.js
    // where the busy render was clobbering a just-checked box back to
    // unchecked while disabled, defeating every click.
    assert.match(
      busyHtml,
      /id="monarchAutoUpdateEnabled" checked/,
      "busy-state render must show the just-submitted value, not the stale pre-save policy",
    );

    gate.resolve({ policy: { enabled: true, source_dir: "Monarch Extractor/output" } });
    await inFlight;

    const doneHtml = sandbox.monarchAutoUpdateControlsHtml();
    assert.doesNotMatch(doneHtml, /id="monarchAutoUpdateEnabled"[^>]*disabled/);
    assert.doesNotMatch(doneHtml, /id="monarchAutoUpdateSourceDir"[^>]*disabled/);
    assert.doesNotMatch(doneHtml, /Saving…/);
  });

  test("the busy flag is cleared even when the save call throws", async () => {
    const sandbox = loadDashboardSandbox();
    sandbox.api = async () => {
      throw new Error("network down");
    };
    sandbox.document.getElementById = (id) => {
      if (id === "monarchAutoUpdateEnabled") return { checked: true };
      if (id === "monarchAutoUpdateSourceDir") return { value: "Monarch Extractor/output" };
      return { style: {}, classList: { add() {}, remove() {}, toggle() {}, contains: () => false } };
    };

    await sandbox.saveMonarchAutoUpdatePolicy().catch(() => {});

    const doneHtml = sandbox.monarchAutoUpdateControlsHtml();
    assert.doesNotMatch(doneHtml, /id="monarchAutoUpdateEnabled"[^>]*disabled/);
    assert.doesNotMatch(doneHtml, /Saving…/);
  });
});

describe("Monarch auto-update card shows busy state while running an import", () => {
  test("Import now button disables and relabels mid-run, and clears afterward", async () => {
    const sandbox = loadDashboardSandbox();
    const gate = deferred();
    sandbox.api = () => gate.promise;

    const beforeHtml = sandbox.monarchAutoUpdateControlsHtml();
    assert.match(beforeHtml, />Import now</);

    const inFlight = sandbox.runMonarchAutoUpdateNow().catch(() => {});

    const busyHtml = sandbox.monarchAutoUpdateControlsHtml();
    assert.match(busyHtml, /disabled[^>]*onclick="[^"]*runMonarchAutoUpdateNow\(\)/);
    assert.match(busyHtml, />Importing…</);

    gate.resolve({ success: true, upsert: { added: 1, updated: 0 } });
    await inFlight;

    const doneHtml = sandbox.monarchAutoUpdateControlsHtml();
    assert.match(doneHtml, />Import now</);
    assert.doesNotMatch(doneHtml, /disabled[^>]*onclick="[^"]*runMonarchAutoUpdateNow\(\)/);
  });

  test("the running flag is cleared even when the run call throws", async () => {
    const sandbox = loadDashboardSandbox();
    sandbox.api = async () => {
      throw new Error("import failed");
    };

    await sandbox.runMonarchAutoUpdateNow().catch(() => {});

    const doneHtml = sandbox.monarchAutoUpdateControlsHtml();
    assert.match(doneHtml, />Import now</);
    assert.doesNotMatch(doneHtml, /disabled[^>]*onclick="[^"]*runMonarchAutoUpdateNow\(\)/);
  });
});
