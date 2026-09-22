// W10c (#329 P6 / §4.3): the policy-adoption / schedule-freeze pair.
//
// §4.3 decided that the mode-switch optimizers offer two different decisions
// and the UI must make the user pick: "Let the plan keep optimizing this"
// (primary, the default, because it is what plans already do) and "Lock in
// this schedule" (secondary). Asset Allocation is the one optimizer where
// both halves are ordinary plan rows, so it is where the pair is wired.
//
// The cases that matter are the ones where a plausible implementation is
// quietly dishonest:
//
//   - a plan already on max_sharpe IS letting the plan optimize, so the
//     policy patch must target THAT mode, not the default, or the computed
//     state reads "not applied" for a plan doing exactly what is asked;
//   - freezing with no computed percentages available must offer nothing,
//     not write user_target and leave stale hand-entered targets in force --
//     that would change what the plan does, opposite to the button's promise;
//   - the target rows are percent-formatted, so afterRaw must be the stored
//     form or an already-frozen plan reads "not applied".

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const {
  allocationLiveModeTarget,
  allocationPolicyAdoptionPatch,
  allocationScheduleFreezePatch,
  allocationOptimizerApplyStripHtml,
} = sandbox;
const OA = sandbox.window.OptimizerApply;
// A top-level `const` in the loader's concatenated classic script is lexical,
// so it never lands on the sandbox global the way a `function` declaration
// does -- it is only reachable through the file's own window bridge. (Same
// reason load_dashboard.mjs's own notes say to set `sandbox.window.rows`.)
const ALLOCATION_OPTIMIZER_ID = sandbox.window.ALLOCATION_OPTIMIZER_ID;

const CLASSES = ["US Large Cap", "US Small Cap", "Cash"];

function planRows(mode = "user_target") {
  const rows = [
    {
      row_index: 1,
      section: "Asset Allocation Policy",
      subsection: "Global",
      label: "allocation_selection_mode",
      value: mode,
      format: "choice",
      editable: true,
    },
  ];
  CLASSES.forEach((name, i) => {
    rows.push({
      row_index: 10 + i,
      section: "Asset Allocation Policy",
      subsection: name,
      label: "target_pct",
      value: ["60%", "20%", "20%"][i],
      format: "pct",
      editable: true,
    });
  });
  return rows;
}

// What requestAllocationPreview() leaves in allocationPreview: the optimizer's
// computed liquid targets, as fractions.
function preview() {
  return {
    selected_liquid_targets: {
      "US Large Cap": 0.55,
      "US Small Cap": 0.1,
      Cash: 0.35,
    },
    optimizer_liquid_targets: {
      "US Large Cap": 0.55,
      "US Small Cap": 0.1,
      Cash: 0.35,
    },
  };
}

function setup(mode, withPreview = true) {
  sandbox.window.rows = planRows(mode);
  sandbox.window.dirty = new Map();
  sandbox.window.allocationPreview = withPreview ? preview() : null;
  // assetClassNamesForAllocation() reads the selection-action rows; the
  // target rows alone are what this patch writes, so the name list is stubbed
  // rather than fabricating a second row family this test does not exercise.
  sandbox.assetClassNamesForAllocation = () => CLASSES.slice();
  sandbox.window.assetClassNamesForAllocation = sandbox.assetClassNamesForAllocation;
}

beforeEach(() => setup("user_target"));

describe('"Let the plan keep optimizing this"', () => {
  test("a user_target plan is offered the default computed mode", () => {
    assert.equal(allocationLiveModeTarget(), "optimizer_recommendation");
    const [item] = allocationPolicyAdoptionPatch();
    assert.equal(item.afterRaw, "optimizer_recommendation");
    assert.equal(item.field, "allocation_selection_mode");
  });

  test("a plan already on max_sharpe keeps max_sharpe", () => {
    // It is already letting the plan optimize. Switching it to the default
    // would be a silent change of strategy behind a button that promises to
    // keep doing what it is doing.
    setup("max_sharpe");
    assert.equal(allocationLiveModeTarget(), "max_sharpe");
    assert.equal(allocationPolicyAdoptionPatch()[0].afterRaw, "max_sharpe");
  });

  test("every computed mode is preserved, not normalized away", () => {
    for (const m of ["optimizer_recommendation", "max_sharpe", "tangency", "real_loss_aware"]) {
      setup(m);
      assert.equal(allocationLiveModeTarget(), m, m);
    }
  });

  test("a plan already optimizing reads applied, not not_applied", () => {
    setup("max_sharpe");
    const patch = allocationPolicyAdoptionPatch();
    assert.equal(
      OA.optimizerAppliedState(patch, OA.liveStorageValueForRowIndex),
      OA.APPLIED,
    );
  });

  test("a user_target plan reads not_applied", () => {
    const patch = allocationPolicyAdoptionPatch();
    assert.equal(
      OA.optimizerAppliedState(patch, OA.liveStorageValueForRowIndex),
      OA.NOT_APPLIED,
    );
  });

  test("it is a one-row patch — the mode row and nothing else", () => {
    assert.equal(allocationPolicyAdoptionPatch().length, 1);
  });

  test("no mode row means no patch, not a half-written one", () => {
    sandbox.window.rows = planRows().filter((r) => r.label !== "allocation_selection_mode");
    assert.deepEqual(Array.from(allocationPolicyAdoptionPatch()), []);
  });
});

describe('"Lock in this schedule"', () => {
  test("it writes user_target plus every computed percentage", () => {
    setup("optimizer_recommendation");
    const patch = allocationScheduleFreezePatch();
    assert.equal(patch.length, 1 + CLASSES.length);
    assert.equal(patch[0].field, "allocation_selection_mode");
    assert.equal(patch[0].afterRaw, "user_target");
  });

  test("the percentages are the optimizer's own, converted from fractions", () => {
    setup("optimizer_recommendation");
    const byClass = {};
    allocationScheduleFreezePatch()
      .filter((x) => x.field === "target_pct")
      .forEach((x) => {
        byClass[x.subsection] = x.afterRaw;
      });
    // 0.55 -> 55, through storageValueForInput's percent normalization.
    assert.equal(Number(byClass["US Large Cap"]), 55);
    assert.equal(Number(byClass["US Small Cap"]), 10);
    assert.equal(Number(byClass["Cash"]), 35);
  });

  test("the written percentages total 100", () => {
    setup("optimizer_recommendation");
    const total = allocationScheduleFreezePatch()
      .filter((x) => x.field === "target_pct")
      .reduce((s, x) => s + Number(x.afterRaw), 0);
    assert.ok(
      Math.abs(total - 100) < 0.01,
      `frozen targets total ${total}, which the plan would refuse to save`,
    );
  });

  test("afterRaw is the stored form, so a frozen plan reads applied", () => {
    setup("optimizer_recommendation");
    const patch = allocationScheduleFreezePatch();
    // Apply it into the rows, then recompute the state from those rows.
    const rows = planRows("user_target");
    patch.forEach((x) => {
      const row = rows.find((r) => r.row_index === x.row_index);
      if (row) row.value = x.afterRaw;
    });
    sandbox.window.rows = rows;
    assert.equal(
      OA.optimizerAppliedState(patch, OA.liveStorageValueForRowIndex),
      OA.APPLIED,
    );
  });

  test("no preview means NOTHING is offered — not a bare mode switch", () => {
    // Writing user_target with no percentages to write would leave the stale
    // hand-entered targets driving the plan, which is a silent change in the
    // opposite direction from what the button promises.
    setup("optimizer_recommendation", false);
    assert.deepEqual(Array.from(allocationScheduleFreezePatch()), []);
  });

  test("no target rows means nothing is offered either", () => {
    setup("optimizer_recommendation");
    sandbox.window.rows = planRows("optimizer_recommendation").filter(
      (r) => r.label !== "target_pct",
    );
    assert.deepEqual(Array.from(allocationScheduleFreezePatch()), []);
  });

  test("the mode row is first, so the confirmation reads in the right order", () => {
    setup("optimizer_recommendation");
    assert.equal(allocationScheduleFreezePatch()[0].field, "allocation_selection_mode");
  });
});

describe("the two are genuinely different patches", () => {
  test("the same optimizer id serves both through patchForIntent", () => {
    setup("optimizer_recommendation");
    allocationOptimizerApplyStripHtml();
    const d = OA.optimizerDescriptor(ALLOCATION_OPTIMIZER_ID);
    assert.ok(d);
    assert.equal(d.patchForIntent("schedule").length, 1 + CLASSES.length);
    assert.equal(d.patchForIntent("policy").length, 1);
  });

  test("freezing and adopting write opposite values to the same row", () => {
    setup("optimizer_recommendation");
    assert.equal(allocationPolicyAdoptionPatch()[0].afterRaw, "optimizer_recommendation");
    assert.equal(allocationScheduleFreezePatch()[0].afterRaw, "user_target");
  });
});

describe("the strip", () => {
  test("§4.3's two named actions, with policy adoption primary", () => {
    setup("optimizer_recommendation");
    const html = allocationOptimizerApplyStripHtml();
    assert.match(html, /Let the plan keep optimizing this/);
    assert.match(html, /Lock in this schedule/);
    assert.match(
      html,
      /class="btn primary"[^>]*>Let the plan keep optimizing this</,
    );
  });

  test("with no computed percentages, the freeze button is absent and explained", () => {
    setup("user_target", false);
    const html = allocationOptimizerApplyStripHtml();
    assert.ok(!/>Lock in this schedule</.test(html));
    assert.match(html, /needs the optimizer's computed percentages/);
  });

  test("no mode row means no strip at all", () => {
    sandbox.window.rows = planRows().filter((r) => r.label !== "allocation_selection_mode");
    assert.equal(allocationOptimizerApplyStripHtml(), "");
  });

  test("§4.6: it does not imply the provenance is durable", () => {
    setup("optimizer_recommendation");
    assert.match(allocationOptimizerApplyStripHtml(), /this browser only/i);
  });

  test("it states that applying only stages the change", () => {
    setup("optimizer_recommendation");
    assert.match(allocationOptimizerApplyStripHtml(), /Save Changes, then rebuild/);
  });

  test("the Allocation Mode panel carries it", () => {
    setup("optimizer_recommendation");
    assert.match(sandbox.allocationModeHtml(), /optimizer-apply-strip/);
  });
});
