// W10c (#329 P6 / §4.2-§4.6): apply-to-plan's core machinery.
//
// Everything asserted here is a pure function of its arguments --
// optimizer_apply.js deliberately reads the monolith off `window` at call
// time rather than importing it, so the file loads alone in its own vm
// sandbox (the same isolation live_optimizer_disclosure.test.mjs uses, and
// for the same reason: load_dashboard.mjs's shared sandbox is used by every
// other suite and a new window-namespace registration in it leaks).
//
// The test this file exists for is the §4.6 one. "Applied" must be COMPUTED
// by comparing the patch against live row values; a stored flag is the bug
// the design names explicitly. So the applied-state cases below drive
// optimizerAppliedState() through a fake row reader and assert all three
// states, including the one that only a computed answer can produce: rows
// that matched, were then hand-edited, and must now read "diverged".

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const APPLY_PATH = path.join(
  __dirname,
  "..",
  "..",
  "frontend",
  "js",
  "optimizer_apply.js",
);
const WORKBENCH_PATH = path.join(
  __dirname,
  "..",
  "..",
  "frontend",
  "js",
  "planning_workbench_ui.js",
);

function loadApplySandbox(windowExtras) {
  const noop = () => {};
  const box = {
    window: Object.assign(
      {
        // The two escapers optimizer_apply.js delegates to; real enough to
        // prove the markup escapes what it interpolates.
        esc: (v) =>
          String(v == null ? "" : v)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;"),
        escJs: (v) =>
          String(v == null ? "" : v).replace(/\\/g, "\\\\").replace(/'/g, "\\'"),
      },
      windowExtras || {},
    ),
    document: { addEventListener: noop, readyState: "complete" },
    localStorage: { getItem: () => null, setItem: noop, removeItem: noop },
    setTimeout: () => 0,
    console,
  };
  box.globalThis = box;
  vm.createContext(box);
  new vm.Script(fs.readFileSync(APPLY_PATH, "utf8"), {
    filename: "optimizer_apply.js",
  }).runInContext(box);
  return box;
}

// planning_workbench_ui.js loaded alone, only to assert the enum change.
function loadWorkbenchSandbox() {
  const noop = () => {};
  const box = {
    window: { esc: (v) => String(v ?? ""), escJs: (v) => String(v ?? "") },
    document: { addEventListener: noop },
    localStorage: { getItem: () => null, setItem: noop, removeItem: noop },
    setTimeout: () => 0,
    console,
  };
  box.globalThis = box;
  vm.createContext(box);
  new vm.Script(fs.readFileSync(WORKBENCH_PATH, "utf8"), {
    filename: "planning_workbench_ui.js",
  }).runInContext(box);
  return box.window.RetirementPlanningWorkbench;
}

const OA = loadApplySandbox().window.OptimizerApply;

// A two-row scalar patch, the Social Security shape: claim dates for two
// people, each carrying both the display and the storage form.
function scalarPatch() {
  return [
    {
      source: "optimizer",
      sourceStep: "income_streams",
      section: "Social Security",
      subsection: "Member 1",
      field: "claim_date",
      label: "Claim date",
      before: "5/2032",
      beforeRaw: "5/2032",
      after: "5/2035",
      afterRaw: "5/2035",
      row_index: 41,
      rationale: "Optimizer's recommended claim age.",
    },
    {
      source: "optimizer",
      sourceStep: "income_streams",
      section: "Social Security",
      subsection: "Member 2",
      field: "claim_date",
      label: "Claim date",
      before: "9/2034",
      beforeRaw: "9/2034",
      after: "9/2036",
      afterRaw: "9/2036",
      row_index: 42,
      rationale: "Optimizer's recommended claim age.",
    },
  ];
}

const reader = (map) => (idx) => map[idx];

describe("§4.2 the source enum gains exactly one value", () => {
  const wb = loadWorkbenchSandbox();

  test('"optimizer" normalizes to itself', () => {
    assert.equal(wb.normalizeSource("optimizer"), "optimizer");
    assert.equal(wb.normalizeSource("OPTIMIZER"), "optimizer");
  });

  test("the four pre-existing values are unchanged", () => {
    for (const s of ["manual", "strategy", "scenario", "stress"])
      assert.equal(wb.normalizeSource(s), s);
  });

  test("a per-optimizer source value is NOT accepted — §4.2 rejected them", () => {
    for (const s of ["roth", "housing", "social_security", "optimizer_roth"])
      assert.equal(wb.normalizeSource(s), "manual", s);
  });

  test("overridesForSource('optimizer') scrapes nothing from the page", () => {
    // The fallthrough it must not take would label the user's staged manual
    // edits as optimizer output.
    assert.deepEqual(Array.from(wb.overridesForSource({}, "optimizer")), []);
  });
});

describe("§4.6 applied state is computed, never stored", () => {
  test("no row matching the patch reads not_applied", () => {
    const state = OA.optimizerAppliedState(
      scalarPatch(),
      reader({ 41: "5/2032", 42: "9/2034" }),
    );
    assert.equal(state, OA.NOT_APPLIED);
  });

  test("every row matching the patch reads applied", () => {
    const state = OA.optimizerAppliedState(
      scalarPatch(),
      reader({ 41: "5/2035", 42: "9/2036" }),
    );
    assert.equal(state, OA.APPLIED);
  });

  test("applied, then one row hand-edited, reads diverged", () => {
    const state = OA.optimizerAppliedState(
      scalarPatch(),
      reader({ 41: "5/2035", 42: "1/2038" }),
    );
    assert.equal(state, OA.DIVERGED);
  });

  test("the state follows the rows, not any flag on the patch", () => {
    // The same patch object, twice, against two different worlds. A stored
    // boolean could not produce both answers.
    const patch = scalarPatch();
    patch.forEach((x) => {
      x.applied = true; // a stray flag must change nothing
    });
    assert.equal(
      OA.optimizerAppliedState(patch, reader({ 41: "5/2035", 42: "9/2036" })),
      OA.APPLIED,
    );
    assert.equal(
      OA.optimizerAppliedState(patch, reader({ 41: "x", 42: "y" })),
      OA.NOT_APPLIED,
    );
  });

  test("an advisory-only patch has nothing to compare and reads not_applied", () => {
    const advisory = [{ label: "ZIP", after: "80202", rationale: "" }];
    assert.equal(OA.optimizerAppliedState(advisory), OA.NOT_APPLIED);
    assert.equal(OA.promotableItems(advisory).length, 0);
    assert.equal(OA.advisoryItems(advisory).length, 1);
  });

  test("advisory items never drag a fully-applied patch down to diverged", () => {
    const patch = scalarPatch().concat([
      { label: "ZIP", after: "80202", rationale: "" },
    ]);
    assert.equal(
      OA.optimizerAppliedState(patch, reader({ 41: "5/2035", 42: "9/2036" })),
      OA.APPLIED,
    );
  });
});

describe("value comparison is tolerant in exactly two ways", () => {
  test("whitespace does not count as a difference", () => {
    assert.equal(OA.sameValue(" 70 ", "70"), true);
  });

  test("numeric equality across formats does not count as a difference", () => {
    assert.equal(OA.sameValue("70.0", "70"), true);
    assert.equal(OA.sameValue(70, "70"), true);
  });

  test("everything else compares exactly", () => {
    assert.equal(OA.sameValue("5/2035", "05/2035"), false);
    assert.equal(OA.sameValue("optimize", "Optimize"), false);
    assert.equal(OA.sameValue("", "0"), false);
    assert.equal(OA.sameValue(undefined, "70"), false);
  });

  test("a missing row (undefined) never reads as applied", () => {
    assert.equal(
      OA.optimizerAppliedState(scalarPatch(), reader({})),
      OA.NOT_APPLIED,
    );
  });
});

describe("§4.6 un-apply is the reverse patch", () => {
  test("before and after swap on every item, in both display and raw form", () => {
    const rev = OA.reverseOptimizerPatch(scalarPatch());
    assert.equal(rev[0].before, "5/2035");
    assert.equal(rev[0].after, "5/2032");
    assert.equal(rev[0].beforeRaw, "5/2035");
    assert.equal(rev[0].afterRaw, "5/2032");
    assert.equal(rev[1].after, "9/2034");
  });

  test("row_index and the routing fields survive the reversal", () => {
    const rev = OA.reverseOptimizerPatch(scalarPatch());
    assert.equal(rev[0].row_index, 41);
    assert.equal(rev[0].sourceStep, "income_streams");
    assert.equal(rev[0].section, "Social Security");
  });

  test("reversing twice returns the original values — it is an involution", () => {
    const twice = OA.reverseOptimizerPatch(
      OA.reverseOptimizerPatch(scalarPatch()),
    );
    const orig = scalarPatch();
    twice.forEach((x, i) => {
      assert.equal(x.before, orig[i].before);
      assert.equal(x.after, orig[i].after);
      assert.equal(x.afterRaw, orig[i].afterRaw);
      assert.equal(x.beforeRaw, orig[i].beforeRaw);
    });
  });

  test("applying the reverse patch takes an applied plan back to not_applied", () => {
    // The whole point: after un-apply the rows hold `before` again, so the
    // forward patch's computed state returns to not_applied by itself.
    const patch = scalarPatch();
    const rev = OA.reverseOptimizerPatch(patch);
    const worldAfterUnapply = {};
    rev.forEach((x) => {
      worldAfterUnapply[x.row_index] = x.afterRaw;
    });
    assert.equal(
      OA.optimizerAppliedState(patch, reader(worldAfterUnapply)),
      OA.NOT_APPLIED,
    );
  });

  test("an item with no beforeRaw falls back to its display before", () => {
    const rev = OA.reverseOptimizerPatch([
      { row_index: 7, before: "62", after: "70", afterRaw: "70" },
    ]);
    assert.equal(rev[0].afterRaw, "62");
  });
});

describe("§4.2 the Planning Case record", () => {
  const box = loadApplySandbox();
  const A = box.window.OptimizerApply;
  const rec = A.optimizerPlanningCase(scalarPatch(), {
    optimizerId: "social_security_timing",
    optimizerTitle: "Social Security Timing",
    at: "2026-09-22T00:00:00.000Z",
  });

  test('source is exactly "optimizer"', () => {
    assert.equal(rec.source, "optimizer");
    assert.equal(A.SOURCE, "optimizer");
  });

  test("it carries the overrides the promote path already knows how to read", () => {
    assert.equal(rec.overrides.length, 2);
    assert.equal(rec.overrides[0].row_index, 41);
  });

  test("it has the fields createCase() writes, so the matrix needs no change", () => {
    for (const k of [
      "case_id",
      "name",
      "base_snapshot_id",
      "source",
      "overrides",
      "run_type",
      "created_at",
    ])
      assert.ok(k in rec, k);
  });

  test("provenance is on the record and names the optimizer", () => {
    assert.equal(rec.optimizer_id, "social_security_timing");
    assert.match(rec.provenance_note, /Social Security Timing/);
  });

  test("the provenance note says it is browser-local, per §4.6's caveat", () => {
    assert.match(rec.provenance_note, /browser only/i);
  });

  test("there is no applied flag on the record", () => {
    for (const k of Object.keys(rec))
      assert.ok(!/^applied|_applied$/.test(k), `unexpected stored flag: ${k}`);
  });
});

describe("§4.4 the action strip", () => {
  const strip = (over) =>
    OA.optimizerApplyStripHtml(
      Object.assign(
        {
          optimizerId: "social_security_timing",
          patch: scalarPatch(),
          state: OA.NOT_APPLIED,
          actions: [
            { intent: "apply", label: "Apply to plan", primary: true },
          ],
        },
        over || {},
      ),
    );

  test("it renders only the actions the caller declares", () => {
    const html = strip();
    assert.match(html, /Apply to plan/);
    assert.ok(!/Lock in this schedule/.test(html));
  });

  test("§4.3's two named actions render when an optimizer declares both", () => {
    const html = strip({
      actions: [
        {
          intent: "policy",
          label: "Let the plan keep optimizing this",
          primary: true,
        },
        { intent: "schedule", label: "Lock in this schedule" },
      ],
    });
    assert.match(html, /Let the plan keep optimizing this/);
    assert.match(html, /Lock in this schedule/);
    // Policy adoption is the default, so it is the primary button.
    assert.match(
      html,
      /class="btn primary"[^>]*>Let the plan keep optimizing this</,
    );
  });

  test("the undo action appears only once something is applied", () => {
    assert.ok(!/Undo this/.test(strip({ state: OA.NOT_APPLIED })));
    assert.match(strip({ state: OA.APPLIED }), /Undo this/);
    assert.match(strip({ state: OA.DIVERGED }), /Undo this/);
  });

  test("the diverged state is visible, not silent", () => {
    const html = strip({ state: OA.DIVERGED });
    assert.match(html, /data-applied-state="diverged"/);
    assert.match(html, /Edited since/);
  });

  test("it states that applying only stages the change", () => {
    assert.match(strip(), /Save Changes, then rebuild/);
  });

  test("§4.6: it says provenance and undo are browser-local, not durable", () => {
    const html = strip();
    assert.match(html, /kept in this browser only/i);
    assert.ok(
      !/permanent|forever|audit trail/i.test(html),
      "must not imply the provenance is durable",
    );
  });

  test("advisory items are named as needing their own page", () => {
    const html = strip({
      patch: scalarPatch().concat([
        { label: "Destination ZIP", after: "80202" },
      ]),
    });
    assert.match(html, /must be adopted from its own page/);
    assert.match(html, /Destination ZIP/);
  });

  test("an empty patch renders nothing at all", () => {
    assert.equal(strip({ patch: [] }), "");
  });

  test("an untrusted optimizer title cannot inject markup", () => {
    const html = OA.optimizerApplyStripHtml({
      optimizerId: '"><img src=x onerror=alert(1)>',
      patch: scalarPatch(),
      state: OA.NOT_APPLIED,
      actions: [{ intent: "apply", label: "<b>Apply</b>" }],
    });
    assert.ok(!/<img/.test(html));
    assert.ok(!/<b>Apply<\/b>/.test(html));
    assert.match(html, /&lt;b&gt;Apply/);
  });
});

describe("the optimizer registry", () => {
  test("a patch is rebuilt at click time, not captured at render time", () => {
    const box = loadApplySandbox();
    const A = box.window.OptimizerApply;
    let value = "5/2032";
    A.registerOptimizer({
      id: "demo",
      title: "Demo",
      buildPatch: () => [
        { row_index: 3, before: value, after: "5/2035", afterRaw: "5/2035" },
      ],
    });
    assert.equal(A.buildPatch("demo")[0].before, "5/2032");
    value = "5/2033";
    assert.equal(A.buildPatch("demo")[0].before, "5/2033");
  });

  test("a throwing patch builder yields an empty patch, not an exception", () => {
    const box = loadApplySandbox();
    const A = box.window.OptimizerApply;
    A.registerOptimizer({
      id: "boom",
      buildPatch: () => {
        throw new Error("no result yet");
      },
    });
    assert.deepEqual(Array.from(A.buildPatch("boom")), []);
    assert.equal(A.renderApplyStrip("boom"), "");
  });

  test("an unregistered optimizer renders no strip", () => {
    assert.equal(OA.renderApplyStrip("nope"), "");
  });

  test("renderApplyStrip computes the state from the live rows", () => {
    const box = loadApplySandbox({
      rows: [{ row_index: 3, value: "5/2035" }],
      dirty: new Map(),
    });
    const A = box.window.OptimizerApply;
    A.registerOptimizer({
      id: "demo",
      title: "Demo",
      buildPatch: () => [
        { row_index: 3, before: "5/2032", after: "5/2035", afterRaw: "5/2035" },
      ],
    });
    assert.match(A.renderApplyStrip("demo"), /data-applied-state="applied"/);
  });

  test("a staged (dirty) edit wins over the saved value, as editValue sees it", () => {
    const box = loadApplySandbox({
      rows: [{ row_index: 3, value: "5/2035" }],
      dirty: new Map([[3, "1/2040"]]),
    });
    const A = box.window.OptimizerApply;
    assert.equal(A.liveRawValueForRowIndex(3), "1/2040");
  });
});

describe("apply routes through the existing promote path", () => {
  function box() {
    const calls = { saved: null, promoted: null, messages: [] };
    const store = [];
    const b = loadApplySandbox({
      RetirementPlanningWorkbench: {
        readAll: () => store.slice(),
        saveAll: (c) => {
          calls.saved = c;
        },
        caseId: () => "case_test",
      },
      promotePlanningCase: async (id) => {
        calls.promoted = id;
      },
      showMessage: (m, k) => calls.messages.push([m, k]),
      renderMain: () => {},
      planningCaseBaseSnapshotId: () => "snap_1",
      planningCaseMetricSummary: () => ({ lcv: 1 }),
    });
    return { A: b.window.OptimizerApply, calls };
  }

  test("it saves the case, then promotes it by id", async () => {
    const { A, calls } = box();
    await A.applyOptimizerPatch(scalarPatch(), {
      optimizerId: "social_security_timing",
    });
    assert.equal(calls.saved.length, 1);
    assert.equal(calls.saved[0].source, "optimizer");
    assert.equal(calls.promoted, "case_test");
  });

  test("it never saves the plan or triggers a build itself", () => {
    // Nothing in the module may reach for these -- §4.4: applying stages.
    const src = fs.readFileSync(APPLY_PATH, "utf8");
    assert.ok(!/saveChanges\s*\(/.test(src));
    assert.ok(!/buildReports\s*\(|startBuild\s*\(/.test(src));
  });

  test("a patch with nothing promotable warns instead of promoting", async () => {
    const { A, calls } = box();
    const rec = await A.applyOptimizerPatch([{ label: "ZIP", after: "80202" }], {
      optimizerId: "x",
    });
    assert.equal(rec, null);
    assert.equal(calls.promoted, null);
    assert.equal(calls.messages[0][1], "warn");
  });

  test("un-apply promotes the reversed values", async () => {
    const { A, calls } = box();
    await A.unapplyOptimizerPatch(scalarPatch(), { optimizerId: "x" });
    assert.equal(calls.saved[0].overrides[0].afterRaw, "5/2032");
    assert.equal(calls.promoted, "case_test");
  });

  test("pin saves the case without promoting it", async () => {
    const { A, calls } = box();
    A.registerOptimizer({
      id: "demo",
      title: "Demo",
      buildPatch: () => scalarPatch(),
    });
    await A.runAction("demo", "pin");
    assert.equal(calls.saved.length, 1);
    assert.equal(calls.promoted, null);
    assert.match(calls.messages[0][0], /this browser only/i);
  });

  test("a descriptor's patchForIntent picks the patch the intent means", async () => {
    const { A, calls } = box();
    A.registerOptimizer({
      id: "twoway",
      title: "Two Way",
      buildPatch: () => scalarPatch(),
      patchForIntent: (intent) =>
        intent === "schedule"
          ? [
              {
                row_index: 99,
                before: "optimize",
                after: "fixed",
                afterRaw: "fixed",
              },
            ]
          : scalarPatch(),
    });
    await A.runAction("twoway", "schedule");
    assert.equal(calls.saved[0].overrides[0].row_index, 99);
  });
});
