# Planning Workbench Strategy Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Planning Workbench a fourth peer Strategy screen (Optimize / Stress Test / Scenarios / Workbench), eliminate its two real duplications (a full copy of the Stress Test screen, and a second stale Strategy Levers renderer that links to an already-dead step), and rebuild its internal layout on the same `strategySection` primitive its three siblings already use.

**Architecture:** Every piece of content the Workbench needs (`sourceButtons`, `overrideTable`, `matrixHtml`, `forwardLookingHtml`, `cardsHtml`, `stressSelectorHtml`, `readAll`, `activeId`, `currentManualOverrideItems`) is already exported on `window.RetirementPlanningWorkbench` from `planning_workbench_ui.js` — nothing in that file needs new entry points. The new screen module (`dashboard_decomp_strategy_workspace.js`) composes those existing exports directly, the same way its siblings already compose other modules' renderers inline. Routing changes are two-line edits to an existing `SECTION_REDIRECTS` map plus a new `STEPS` entry, following the exact precedent already set for the three other steps `dashboard_decomp_strategy_workspace.js` superseded (`distribution_strategy`, `state_residency`, `special_strategies`, `planning_levers`, `planning_workbench` — all hidden shells with `SECTION_REDIRECTS` entries, none deleted).

**Tech Stack:** Vanilla JS ES modules loaded as classic scripts (`frontend/js/*`), Node's built-in test runner (`node --test`, frontend).

## Global Constraints

- No new Workbench functionality — the Change Set Builder, Unified Comparison Matrix, Decision panel, and Saved Planning Cases sections keep their exact current capabilities. The case-store's `source` enum (`strategy`/`scenario`/`stress`/`manual`) is untouched.
- No change to `build_impact` ("Impact & Build History") — it stays exactly as it is, out of scope.
- Every existing `data-step-id="planning_workbench"` or `data-step-id="planning_levers"` button anywhere in the app (the header's "Compare & Decide" button on every page, every "Preview impact" analysisFrame footer, checklist closeout, source-truth banners) must keep working unchanged — only where those ids redirect to changes, never the ids themselves or any call site outside `navigation.js`.
- The new screen's internal layout uses the shared `strategySection`/`renderStrategyScreen` primitive (`dashboard_decomp_strategy_workspace.js`), matching Optimize/Stress Test/Scenarios exactly: same markup, same open-state persistence, same lazy-body-only-when-open behavior.
- `renderPlanningLevers()` (the fuller, two-ranked-table view) is the one surviving Strategy Levers renderer everywhere. `renderWorkbenchLeverEditorHtml()` (the compact one, which links to the already-retired `distribution_strategy` step) is deleted, not kept as an alternate view.
- The Workbench's "Stress & Probability" section (`renderWorkbenchStressHtml()`, a full duplicate of the Stress Test screen's four modules) is deleted entirely, not replaced with a summary — stress inputs are edited on the peer Stress Test screen only.

---

## File Map

| File | Change |
|---|---|
| `frontend/js/dashboard_decomp_strategy_workspace.js` | New `renderStrategyWorkbench()`; `renderStrategyScenarios()` drops `levers`/`workbench` entries; window bridge gains the new export |
| `frontend/js/dashboard.js` | New `strategy_workbench` `STEPS` entry; `planning_workbench`/`planning_levers` entries marked `hidden: true`; `renderMain()` switch gains a `strategy_workbench` branch |
| `frontend/js/navigation.js` | `SECTION_REDIRECTS.planning_workbench`/`.planning_levers` retargeted from `strategy_scenarios` to `strategy_workbench` |
| `frontend/js/dashboard_decomp_row_model.js` | `STRATEGY_SCREEN_MEMBER_STEPS` gains `strategy_workbench: []` |
| `frontend/js/dashboard_decomp_allocation_optimizer.js` | `renderPlanningLevers()` drops its "Back to Planning Workbench" button; `renderWorkbenchLeverEditorHtml()` deleted |
| `frontend/js/dashboard_decomp_mc_stress_options.js` | `renderWorkbenchStressHtml()` deleted |
| `frontend/js/planning_workbench_ui.js` | Old `renderWorkbench()` deleted, along with its `window.RetirementPlanningWorkbench` export entry |
| `tests/frontend/strategy_section_lazy_body.test.mjs` | New assertions for `renderStrategyWorkbench()`; `renderStrategyScenarios()` test updated to expect only `change_sets`; `NEW_STEPS`/STEPS-wiring tests extended; new "deletions stay deleted" tests |

---

### Task 1: `renderStrategyWorkbench()` — the new screen, additive only

**Files:**
- Modify: `frontend/js/dashboard_decomp_strategy_workspace.js` (new function + window bridge entry)
- Test: `tests/frontend/strategy_section_lazy_body.test.mjs`

**Interfaces:**
- Consumes: `window.RetirementPlanningWorkbench.{readAll, activeId, sourceButtons, overrideTable, currentManualOverrideItems, matrixHtml, forwardLookingHtml, stressSelectorHtml, cardsHtml}` (all already exported, verify their exact signatures by reading `frontend/js/planning_workbench_ui.js` before writing this task's code — they are: `readAll(): array`, `activeId(): string`, `sourceButtons(): string`, `overrideTable(ctx, items, emptyText): string`, `currentManualOverrideItems(ctx): array`, `matrixHtml(ctx, cases): string`, `forwardLookingHtml(ctx): string`, `stressSelectorHtml(ctx, cases): string`, `cardsHtml(ctx, cases, active): string`); `renderStrategyScreen(sections)`, `strategySection`, `planningWorkbenchContext()`, `renderPlanningLevers()`, `esc`, `escJs` — all already bare globals/exports this file and its siblings already use.
- Produces: `renderStrategyWorkbench()`, exported and window-bridged, callable with no arguments, returning an HTML string. No other task's code depends on its internals beyond calling it.

- [ ] **Step 1: Write the failing test**

Add to `tests/frontend/strategy_section_lazy_body.test.mjs`, in the `describe("the three Strategy screens (ticket 323)", ...)` block (rename that describe's title in this same step — see Step 1b):

```javascript
  test("Workbench renders its five sections; the first (Strategy Levers) opens, the rest stay collapsed", () => {
    const html = sandbox.renderStrategyWorkbench();
    for (const key of ["levers", "change_sets", "comparison", "decision", "saved_cases"]) {
      assert.ok(
        html.includes(`data-dkey="strategy:${key}"`),
        `missing section ${key}`,
      );
    }
    assert.match(html, /data-dkey="strategy:levers"[^>]*\sopen/);
    for (const key of ["change_sets", "comparison", "decision", "saved_cases"]) {
      assert.doesNotMatch(
        html,
        new RegExp(`data-dkey="strategy:${key}"[^>]*\\sopen`),
      );
    }
  });

  test("Workbench keeps its top model-note intro above the sections", () => {
    const html = sandbox.renderStrategyWorkbench();
    assert.match(html, /Planning Workbench model/);
    assert.ok(
      html.indexOf("Planning Workbench model") < html.indexOf('data-dkey="strategy:levers"'),
      "the model note must render before the first section",
    );
  });
```

**Step 1b:** Rename the enclosing `describe("the three Strategy screens (ticket 323)", ...)` to `describe("the four Strategy screens (ticket 323 + Workbench)", ...)` — a one-word title edit, no behavior change, just keeping the describe name accurate once there are four screens.

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/frontend/strategy_section_lazy_body.test.mjs`
Expected: FAIL — `sandbox.renderStrategyWorkbench is not a function`

- [ ] **Step 3: Read the current `renderWorkbench()` and its exports to confirm exact signatures**

Read `frontend/js/planning_workbench_ui.js`, specifically:
- The `window.RetirementPlanningWorkbench = {...}` object (near the end of the file) to confirm every name listed in this task's Interfaces section is actually present.
- The current `renderWorkbench(ctx)` function body, to copy its "Decision panel" `feature-grid` block verbatim in Step 4 below (do not paraphrase or rewrite it — copy the exact markup so behavior is unchanged).

- [ ] **Step 4: Add `renderStrategyWorkbench()`**

In `frontend/js/dashboard_decomp_strategy_workspace.js`, add this function after `renderStrategyScenarios()` (before the `// Every export above is also re-attached to window` comment block):

```javascript
export function renderStrategyWorkbench() {
  const W = window.RetirementPlanningWorkbench;
  const ctx = planningWorkbenchContext();
  const cases = W.readAll();
  const active =
    cases.find((c) => c.case_id === W.activeId()) ||
    cases.find((c) => !c.archived) ||
    null;
  return (
    '<div class="section-note workbench-model"><b>Planning Workbench model:</b> Baseline -> Change Set -> Run Type -> Impact -> Decision. A Planning Case is browser-local and never changes the saved plan by itself.</div>' +
    renderStrategyScreen([
      {
        key: "levers",
        title: "Strategy Levers",
        gate: null,
        body: () => renderPlanningLevers(),
      },
      {
        key: "change_sets",
        title: "Change Set Builder",
        gate: null,
        body: () =>
          W.sourceButtons() +
          "<h4>Currently staged manual edits</h4>" +
          W.overrideTable(ctx, W.currentManualOverrideItems(ctx), "No unsaved field edits are currently staged."),
      },
      {
        key: "comparison",
        title: "Unified Comparison Matrix",
        gate: null,
        body: () => W.matrixHtml(ctx, cases),
      },
      {
        key: "decision",
        title: "Decision",
        gate: null,
        body: () =>
          W.forwardLookingHtml(ctx) +
          '<div class="feature-grid">' +
          W.stressSelectorHtml(ctx, cases) +
          '<div class="feature-card"><h3>Decision panel</h3><p class="small">Every comparison ends with one deliberate choice: adopt selected changes into the saved plan via source pages, keep as a named scenario only, or archive/no action.</p>' +
          (active
            ? `<p><b>Selected:</b> ${esc(active.name)}</p><div class="pane-actions"><button class="btn primary" type="button" onclick="planningCaseAdopt('${escJs(active.case_id)}')">Adopt via source pages</button><button class="btn" type="button" data-step-id="build_impact">View impact</button><button class="btn" type="button" onclick="planningCaseArchive('${escJs(active.case_id)}')">Archive/no action</button></div>`
            : '<p class="small">Select or create a case to make a decision.</p>') +
          "</div></div>",
      },
      {
        key: "saved_cases",
        title: "Saved Planning Cases",
        gate: null,
        body: () => W.cardsHtml(ctx, cases, active),
      },
    ])
  );
}
```

Then add `renderStrategyWorkbench` to the `Object.assign(window, {...})` bridge block at the bottom of the same file:

```javascript
Object.assign(window, {
  strategySectionOpenMap,
  strategySectionResetOpenCache,
  strategySectionSetOpen,
  strategySectionToggle,
  strategySectionGatedNote,
  strategySection,
  renderStrategyScreen,
  renderStrategyOptimize,
  renderStrategyStress,
  renderStrategyScenarios,
  renderStrategyWorkbench,
});
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `node --test tests/frontend/strategy_section_lazy_body.test.mjs`
Expected: all PASS

- [ ] **Step 6: Run the full frontend suite to check for regressions**

Run: `node --test tests/frontend/*.test.mjs`
Expected: all PASS (this task is purely additive — nothing yet calls the new function outside the test, so nothing else can regress)

- [ ] **Step 7: Commit**

```bash
git add frontend/js/dashboard_decomp_strategy_workspace.js tests/frontend/strategy_section_lazy_body.test.mjs
git commit -m "feat(strategy): add renderStrategyWorkbench(), the new Workbench screen"
```

---

### Task 2: Route `strategy_workbench` into the nav

**Files:**
- Modify: `frontend/js/dashboard.js` (new `STEPS` entry, `hidden: true` on two existing entries, `renderMain()` switch branch)
- Modify: `frontend/js/navigation.js` (`SECTION_REDIRECTS` retarget)
- Modify: `frontend/js/dashboard_decomp_row_model.js` (`STRATEGY_SCREEN_MEMBER_STEPS`)
- Test: `tests/frontend/strategy_section_lazy_body.test.mjs`

**Interfaces:**
- Consumes: `renderStrategyWorkbench()` (Task 1)
- Produces: `setStep('strategy_workbench')` renders the new screen; `setStep('planning_workbench')` and `setStep('planning_levers')` both redirect to it via `SECTION_REDIRECTS`; nothing later depends on internals beyond these three ids being live.

- [ ] **Step 1: Write the failing tests**

Add to `tests/frontend/strategy_section_lazy_body.test.mjs`'s `describe("STEPS wiring for the three Strategy screens (ticket 323)", ...)` block (rename its title too, same reasoning as Task 1 Step 1b — see Step 1b below):

```javascript
  test("strategy_workbench is a Strategy-group nav entry with desc/intro/help", () => {
    const step = stepById("strategy_workbench");
    assert.ok(step, "missing STEPS entry for strategy_workbench");
    assert.equal(step.group, "Strategy");
    assert.equal(step.title, "Workbench");
    assert.ok(step.desc, "strategy_workbench missing desc");
    assert.ok(step.intro, "strategy_workbench missing intro");
    assert.ok(step.help, "strategy_workbench missing help");
  });

  test("planning_workbench and planning_levers are now hidden shells", () => {
    for (const id of ["planning_workbench", "planning_levers"]) {
      const step = stepById(id);
      assert.ok(step, `missing STEPS shell for ${id}`);
      assert.equal(step.hidden, true, id);
    }
  });
```

Add a new test in a new `describe` block right after that one:

```javascript
describe("SECTION_REDIRECTS points planning_workbench/planning_levers at the Workbench (ticket 323 + Workbench)", () => {
  test("both ids redirect to strategy_workbench", () => {
    const redirects = sandbox.window.SECTION_REDIRECTS || sandbox.SECTION_REDIRECTS;
    assert.equal(redirects.planning_workbench.step, "strategy_workbench");
    assert.equal(redirects.planning_levers.step, "strategy_workbench");
  });
});
```

**Step 1b:** Rename `describe("STEPS wiring for the three Strategy screens (ticket 323)", ...)` to `describe("STEPS wiring for the four Strategy screens (ticket 323 + Workbench)", ...)`.

Also update the existing test in that block, `"the three new steps are adjacent so the nav groups them together"`, which currently reads `const NEW_STEPS = ["strategy_optimize", "strategy_stress", "strategy_scenarios"];` — add `"strategy_workbench"` to that array so the adjacency check covers all four:

```javascript
  const NEW_STEPS = ["strategy_optimize", "strategy_stress", "strategy_scenarios", "strategy_workbench"];
```

(this is the same `const` referenced by the `"each new step is a Strategy-group nav entry"` test — that test's `titles` map also needs `strategy_workbench: "Workbench"` added: `const titles = { strategy_optimize: "Optimize", strategy_stress: "Stress Test", strategy_scenarios: "Scenarios", strategy_workbench: "Workbench" };`)

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/frontend/strategy_section_lazy_body.test.mjs`
Expected: FAIL — no `strategy_workbench` STEPS entry, `planning_workbench`/`planning_levers` not yet hidden, redirects not yet retargeted

- [ ] **Step 3: Read the current STEPS entries and SECTION_REDIRECTS map exactly**

Read `frontend/js/dashboard.js` around the `planning_workbench`/`planning_levers`/`strategy_scenarios` `STEPS` entries (search for `id: "planning_workbench"`) and `frontend/js/navigation.js` around `SECTION_REDIRECTS` (search for `planning_levers:{step:`) to confirm the exact current text before editing — line numbers may have shifted from what's quoted below.

- [ ] **Step 4: Add the `strategy_workbench` STEPS entry**

In `frontend/js/dashboard.js`, insert this new entry immediately after the existing `strategy_scenarios` entry (which currently ends `},` right before the `distribution_strategy` entry):

```javascript
  {
    id: "strategy_workbench",
    group: "Strategy",
    title: "Workbench",
    desc: "Compare the baseline, named change sets, and stress-suite results in one place, then decide what to adopt.",
    intro:
      "Pick a baseline, stage a change set to test, choose Scenario or Stress as the run type, then review Impact and record a Decision.",
    help: "Planning cases are browser-local change sets. They do not alter the saved plan until you explicitly jump to source pages, edit inputs, save, and rebuild.",
  },
```

- [ ] **Step 5: Mark `planning_workbench` and `planning_levers` hidden**

In `frontend/js/dashboard.js`, add `hidden: true,` to both existing `STEPS` entries (matching how `distribution_strategy`/`state_residency`/`special_strategies` already do it — do not change any other field on either entry):

```javascript
  {
    id: "planning_workbench",
    group: null,
    hidden: true,
    title: "Planning Workbench",
    // ...unchanged desc/intro/help...
  },
```

```javascript
  {
    id: "planning_levers",
    group: "Strategy",
    hidden: true,
    title: "Strategy Levers",
    // ...unchanged desc/intro/help...
  },
```

(Match each entry's existing field order and content exactly — only the `hidden: true,` line is new, placed the same way `distribution_strategy`'s entry places it, i.e. directly after `group`.)

- [ ] **Step 6: Add the `renderMain()` switch branch**

In `frontend/js/dashboard.js`, in the `renderMain()` function's step-routing `if`/`else if` chain, add a `strategy_workbench` branch next to its three siblings:

```javascript
  else if (activeStep === "strategy_optimize") content += renderStrategyOptimize();
  else if (activeStep === "strategy_stress") content += renderStrategyStress();
  else if (activeStep === "strategy_scenarios")
    content += renderStrategyScenarios();
  else if (activeStep === "strategy_workbench")
    content += renderStrategyWorkbench();
```

(insert the new line immediately after the existing `strategy_scenarios` branch)

- [ ] **Step 7: Retarget the SECTION_REDIRECTS entries**

In `frontend/js/navigation.js`, change:

```javascript
    planning_levers:{step:'strategy_scenarios',section:'levers'},
```

to:

```javascript
    planning_levers:{step:'strategy_workbench',section:'levers'},
```

and change:

```javascript
    planning_workbench:{step:'strategy_scenarios',section:'workbench'},
```

to:

```javascript
    planning_workbench:{step:'strategy_workbench',section:'levers'},
```

(`planning_workbench` now redirects to the same `levers` section as `planning_levers`, not a `workbench` section — there is no separate `workbench` section key once the Workbench IS the screen rather than a section within Scenarios; `levers` is the Workbench screen's first/default-open section, matching today's "land on a ranked-levers view first" behavior from the header's "Compare & Decide" button.)

- [ ] **Step 8: Add the `STRATEGY_SCREEN_MEMBER_STEPS` entry**

In `frontend/js/dashboard_decomp_row_model.js`, add `strategy_workbench: []` to the `STRATEGY_SCREEN_MEMBER_STEPS` object:

```javascript
const STRATEGY_SCREEN_MEMBER_STEPS = {
  strategy_optimize: [
    "roth_conversion",
    "allocation_assets",
    "allocation_policy",
    "entity_charitable",
    "heloc_strategy",
  ],
  strategy_stress: [
    "monte_carlo_options",
    "survivor_stress",
    "ltc_stress",
    "divorce_options",
  ],
  strategy_scenarios: ["scenarios"],
  strategy_workbench: [],
};
```

(an empty array is still truthy in the `if (members)` check right below this object in `rawRowsForStep()`, so this correctly makes `strategy_workbench` return zero aggregated rows — matching "the Workbench screen owns no editable plan-data rows itself" — without needing any other switch statement touched)

- [ ] **Step 9: Run tests to verify they pass**

Run: `node --test tests/frontend/strategy_section_lazy_body.test.mjs`
Expected: all PASS

- [ ] **Step 10: Run the full frontend suite**

Run: `node --test tests/frontend/*.test.mjs`
Expected: all PASS

- [ ] **Step 11: Commit**

```bash
git add frontend/js/dashboard.js frontend/js/navigation.js frontend/js/dashboard_decomp_row_model.js tests/frontend/strategy_section_lazy_body.test.mjs
git commit -m "feat(strategy): route strategy_workbench into nav, retarget planning_workbench/planning_levers redirects"
```

---

### Task 3: Shrink Scenarios to just Scenario Change Sets

**Files:**
- Modify: `frontend/js/dashboard_decomp_strategy_workspace.js` (`renderStrategyScenarios()`)
- Test: `tests/frontend/strategy_section_lazy_body.test.mjs`

**Interfaces:**
- Consumes: nothing new
- Produces: `renderStrategyScenarios()` returns exactly one section (`change_sets`); nothing else depends on its old `levers`/`workbench` entries continuing to exist (Task 2 already redirects every entry point for both away from Scenarios).

- [ ] **Step 1: Write the failing test**

Replace the existing test in `tests/frontend/strategy_section_lazy_body.test.mjs`'s (now four-)`describe` block:

```javascript
  test("Scenarios renders only Scenario Change Sets, which opens by default", () => {
    const html = sandbox.renderStrategyScenarios();
    assert.ok(html.includes('data-dkey="strategy:change_sets"'));
    assert.ok(!html.includes('data-dkey="strategy:levers"'), "levers must no longer live under Scenarios");
    assert.ok(!html.includes('data-dkey="strategy:workbench"'), "workbench must no longer live under Scenarios");
    assert.match(html, /data-dkey="strategy:change_sets"[^>]*\sopen/);
  });
```

(this replaces the existing `"Scenarios renders its three sections; the first (Strategy Levers) opens, the rest stay collapsed"` test, which asserted the pre-change three-tab shape)

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/frontend/strategy_section_lazy_body.test.mjs`
Expected: FAIL — `renderStrategyScenarios()` still has 3 sections (`levers`, `change_sets`, `workbench`), and the currently-open default section is `levers`, not `change_sets`

- [ ] **Step 3: Shrink `renderStrategyScenarios()`**

In `frontend/js/dashboard_decomp_strategy_workspace.js`, replace:

```javascript
export function renderStrategyScenarios() {
  return renderStrategyScreen([
    { key: "levers", title: "Strategy Levers", gate: null, body: () => renderPlanningLevers() },
    {
      key: "change_sets",
      title: "Scenario Change Sets",
      gate: "scenarios",
      body: () => analysisFrame(renderScenarios(), "strategy"),
    },
    {
      key: "workbench",
      title: "Planning Workbench",
      gate: null,
      body: () => renderPlanningWorkbench(),
    },
  ]);
}
```

with:

```javascript
export function renderStrategyScenarios() {
  return renderStrategyScreen([
    {
      key: "change_sets",
      title: "Scenario Change Sets",
      gate: "scenarios",
      body: () => analysisFrame(renderScenarios(), "strategy"),
    },
  ]);
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test tests/frontend/strategy_section_lazy_body.test.mjs`
Expected: all PASS

- [ ] **Step 5: Run the full frontend suite**

Run: `node --test tests/frontend/*.test.mjs`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/js/dashboard_decomp_strategy_workspace.js tests/frontend/strategy_section_lazy_body.test.mjs
git commit -m "feat(strategy): Scenarios screen now holds only Scenario Change Sets"
```

---

### Task 4: Delete the dead/duplicate code

**Files:**
- Modify: `frontend/js/dashboard_decomp_allocation_optimizer.js` (remove "Back to Planning Workbench" button from `renderPlanningLevers()`; delete `renderWorkbenchLeverEditorHtml()`)
- Modify: `frontend/js/dashboard_decomp_mc_stress_options.js` (delete `renderWorkbenchStressHtml()`)
- Modify: `frontend/js/planning_workbench_ui.js` (delete old `renderWorkbench()` and its window export entry)
- Test: `tests/frontend/strategy_section_lazy_body.test.mjs`

**Interfaces:**
- Consumes: nothing new (this task only removes code nothing calls anymore after Tasks 1-3 landed)
- Produces: nothing new; confirms deletion

- [ ] **Step 1: Write the failing tests**

Add a new `describe` block to `tests/frontend/strategy_section_lazy_body.test.mjs`, after the "deletions stay deleted (ticket 323)" block, following that block's exact existing pattern:

```javascript
describe("deletions stay deleted (Workbench integration)", () => {
  test("renderWorkbenchStressHtml and renderWorkbenchLeverEditorHtml are gone -- no stale duplicate renderers", () => {
    assert.equal(typeof sandbox.renderWorkbenchStressHtml, "undefined");
    assert.equal(typeof sandbox.renderWorkbenchLeverEditorHtml, "undefined");
  });

  test("the old planning_workbench_ui.js renderWorkbench() is gone -- superseded by renderStrategyWorkbench()", () => {
    assert.equal(typeof sandbox.window.RetirementPlanningWorkbench.renderWorkbench, "undefined");
  });

  test("renderPlanningLevers() no longer links back to itself", () => {
    // planningLeversBaselineReady() gates the real body vs. a "build first"
    // placeholder; force it true (both planLoaded and lastBuildOk have
    // get/set window accessors -- dashboard.js:7188/7202 -- generated by
    // this repo's module-bridge codemod) so this test exercises the actual
    // markup the deletion touches, not the unrelated placeholder.
    sandbox.window.planLoaded = true;
    sandbox.window.lastBuildOk = true;
    const html = sandbox.renderPlanningLevers();
    assert.ok(!html.includes("Back to Planning Workbench"));
    sandbox.window.planLoaded = false;
    sandbox.window.lastBuildOk = false;
  });
});
```

No existing test in this repo already stubs `renderPlanningLevers()` into its real (non-placeholder) body -- this is the first one to do so, which is why the stub is spelled out here rather than referenced.

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/frontend/strategy_section_lazy_body.test.mjs`
Expected: FAIL — all three functions/behaviors still present

- [ ] **Step 3: Remove the "Back to Planning Workbench" button from `renderPlanningLevers()`**

In `frontend/js/dashboard_decomp_allocation_optimizer.js`, in `renderPlanningLevers()`'s return statement, remove exactly this substring (leave everything before and after it untouched):

```
<p class="small"><button class="btn tiny" type="button" data-step-id="planning_workbench">Back to Planning Workbench</button></p>
```

- [ ] **Step 4: Delete `renderWorkbenchLeverEditorHtml()`**

In `frontend/js/dashboard_decomp_allocation_optimizer.js`, delete the entire `renderWorkbenchLeverEditorHtml()` function (from `export function renderWorkbenchLeverEditorHtml() {` through its closing `}`), and remove its entry from that file's own `Object.assign(window, {...})` bridge block (search for `renderWorkbenchLeverEditorHtml,` in that block).

- [ ] **Step 5: Delete `renderWorkbenchStressHtml()`**

In `frontend/js/dashboard_decomp_mc_stress_options.js`, delete the entire `renderWorkbenchStressHtml()` function (from `export function renderWorkbenchStressHtml() {` through its closing `}`), and remove its entry from that file's own window bridge block (search for `renderWorkbenchStressHtml,`).

Read the function body first (it is longer than the excerpt already seen in this plan's design doc -- it has branches for all four stress modules) so the deletion removes the whole function, not a truncated part of it.

- [ ] **Step 6: Delete the old `renderWorkbench()`**

In `frontend/js/planning_workbench_ui.js`, delete the entire `renderWorkbench(ctx)` function (from `function renderWorkbench(ctx) {` through its closing `}`, immediately before `function renderBuildImpactContext(ctx) {`, which stays), and remove `renderWorkbench,` from the `window.RetirementPlanningWorkbench = {...}` export object at the bottom of the same file. Do not touch `renderBuildImpactContext` or anything else in that export object.

- [ ] **Step 7: Run tests to verify they pass**

Run: `node --test tests/frontend/strategy_section_lazy_body.test.mjs`
Expected: all PASS

- [ ] **Step 8: Run the full frontend suite**

Run: `node --test tests/frontend/*.test.mjs`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add frontend/js/dashboard_decomp_allocation_optimizer.js frontend/js/dashboard_decomp_mc_stress_options.js frontend/js/planning_workbench_ui.js tests/frontend/strategy_section_lazy_body.test.mjs
git commit -m "refactor(strategy): delete the Workbench's duplicate stress/levers renderers"
```

---

### Task 5: Full regression and manual verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full frontend test suite**

Run: `node --test tests/frontend/*.test.mjs`
Expected: all PASS

- [ ] **Step 2: Run the relevant backend suite**

Run: `python -m pytest tests/test_strategy_workspace_screens_functional.py tests/test_strategy_workspace_module_gating.py tests/test_scenario_templates_sets_functional.py tests/test_dashboard_dead_code_sweep_regression.py -q`
Expected: all PASS. (These are the backend tests this branch's earlier session work found already cover the Strategy workspace and scenario templates; `test_dashboard_dead_code_sweep_regression.py` in particular should confirm the deleted functions from Task 4 leave no other dangling reference in `dashboard.js`'s own text, since that file's source-grep tests are sensitive to stale references.)

- [ ] **Step 3: Check the frontend size ratchet**

Run: `python -m pytest tests/test_frontend_size_ratchet.py -v`
Expected: PASS, or FAIL with a specific over/under-budget line count. Task 4 deletes more lines (two full renderer functions plus a button) than Tasks 1-3 add (one new composed function, mostly reusing existing exports) — if the ratchet fails on the LOW side (a large unused slack, per `test_ratchet_is_not_slack`), lower `TOTAL_JS_MAX_LINES` in `tests/test_frontend_size_ratchet.py` to the new measured size, following the exact dated-comment precedent already used repeatedly in that file. If it fails on the high side, raise it the same way, with a comment explaining the net new/removed lines from this branch's five tasks.

- [ ] **Step 4: Manual browser verification**

Start the dev server via this project's `.claude/launch.json` config and, in the browser:
- Confirm Strategy now shows four tabs: Optimize, Stress Test, Scenarios, Workbench.
- Open Workbench; confirm its five sections (Strategy Levers, Change Set Builder, Unified Comparison Matrix, Decision, Saved Planning Cases) render, Strategy Levers opens by default, and the "Planning Workbench model" note appears above the sections.
- Confirm Strategy Levers inside the Workbench shows the two-ranked-table view (KPI strip, "Ranked by estimated TNW lift" / "Ranked by estimated success lift" tables) -- not the old single-table compact view.
- From any Optimize tab (e.g. Roth Conversion), click "Preview impact (Planning overview)"; confirm it lands on the Workbench screen's Strategy Levers section, not a separate page.
- From any page, click the header's "Compare & Decide" button; confirm it also lands on the Workbench.
- Open Scenarios; confirm it now shows only "Scenario Change Sets" (no Strategy Levers or Planning Workbench tabs).
- Save a staged edit as a Planning Case from the Workbench's Change Set Builder section; confirm it appears in Saved Planning Cases and the Unified Comparison Matrix, exactly as before this branch (functionality unchanged, only location/duplication changed).

No commit for this task -- verification only. If any step surfaces a bug, fix it as a small addendum to the task whose code owns the bug, re-run that task's tests, and commit the fix under that task's own commit message convention.

---

## Self-Review Notes

- **Spec coverage:** Section 1 (new screen) -> Task 1. Section 2 (one Strategy Levers view) -> Tasks 1 (composition) + 4 (deleting the stale one and the circular button). Section 3 (redirect wiring) -> Task 2. Section 4 (Scenarios after the split) -> Task 3. The Stress & Probability removal (Goals/Non-goals) -> Task 4 Step 5. Testing section -> covered per-task plus Task 5's full-suite pass and manual verification list.
- **Placeholder scan:** no TBD/TODO; every step has complete, pasteable code, including Task 4 Step 1's test stub for `planLoaded`/`lastBuildOk` (resolved during self-review after confirming no existing test already stubbed `renderPlanningLevers()` into its real body).
- **Type/name consistency checked:** `renderStrategyWorkbench`, the five section keys (`levers`/`change_sets`/`comparison`/`decision`/`saved_cases`), `strategy_workbench` (the STEPS id), and every `window.RetirementPlanningWorkbench.*` method name are spelled identically everywhere they appear across all five tasks.
