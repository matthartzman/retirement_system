# Planning Workbench integration into the Strategy redesign

2026-09-17

## Problem

Ticket 323's Strategy redesign split the old monolithic Strategy page into
three peer screens -- Optimize, Stress Test, Scenarios -- built on a shared
`strategySection`/`renderStrategyScreen` lazy-collapsible-section primitive
(`dashboard_decomp_strategy_workspace.js`). Planning Workbench was not
updated to match: it still lives as the third tab inside the Scenarios
screen specifically (`renderStrategyScenarios()`'s `"workbench"` entry,
calling `renderPlanningWorkbench()` -> `window.RetirementPlanningWorkbench
.renderWorkbench()` in `planning_workbench_ui.js`), even though its actual
job -- comparing and adopting changes -- is cross-cutting across all three
screens, not scoped to Scenarios.

That mismatch produced three concrete problems, found by tracing the code
rather than assumed:

1. **Findability.** The Workbench is nested one level inside just one of
   three peer screens, with no indication from Optimize or Stress Test that
   it exists there.
2. **Conceptual overlap.** Three related-but-separately-addressable things
   exist for what should be one concept:
   - The Workbench tab itself (`strategy_scenarios` -> `workbench` section).
   - A standalone nav step `planning_workbench` (`group: null` in `dashboard
     .js`'s `STEPS`), which `navigation.js`'s `SECTION_REDIRECTS` map already
     routes to `{step:'strategy_scenarios', section:'workbench'}` -- so it
     is not independently rendered, just an indirection layer.
   - A hidden nav step `planning_levers` ("Strategy Levers"), similarly
     redirected via `SECTION_REDIRECTS` to `{step:'strategy_scenarios',
     section:'levers'}` -- the OTHER Scenarios tab, not the Workbench tab.
   Every "Preview impact (Planning overview)" footer button on every
   Optimize/Stress Test tab (`analysisFrame()`'s generated footer,
   `dashboard_decomp_row_model.js:1043`) targets `planning_levers`, landing
   on a *different* Scenarios tab than the Workbench itself.
3. **Real duplication, not just architecture.** Tracing the Workbench's own
   six `<details>` blocks turned up two genuine redundancies:
   - `renderWorkbenchStressHtml()` (`dashboard_decomp_mc_stress_options.js`)
     fully duplicates the Stress Test screen: the same four modules (Monte
     Carlo, Survivor, LTC, Divorce), the same renderers, the same
     `stepGatedByOptionalModule`/`optionalFunctionEnabled` gating -- just
     wrapped in its own `<details>` instead of `strategySection`.
   - Two different "Strategy Levers" renderers exist. `renderPlanningLevers()`
     (`dashboard_decomp_allocation_optimizer.js`) is the fuller view -- a
     baseline KPI strip plus two ranked tables (top 6 by ATNW lift, top 6 by
     Asuccess lift) -- and is what both the `planning_levers` redirect target
     and the Scenarios "Strategy Levers" tab already use. It carries a ticket
     323 comment confirming it already had its own redundancy pass (an old
     quick-nav launcher grid was removed once the three new screens covered
     those destinations). `renderWorkbenchLeverEditorHtml()` (same file) is a
     second, more compact, single-table view embedded specifically inside the
     Workbench's own "Strategy Levers" `<details>` block -- and its footer
     button links to `data-step-id="distribution_strategy"`, a step already
     retired and hidden by the same redesign. That is a live dead link in
     current code, evidence this second renderer is the stale leftover, not
     a deliberate alternate view.

## Goals

- One coherent, discoverable home for the Workbench: a fourth peer Strategy
  screen, `strategy_workbench`, alongside Optimize / Stress Test / Scenarios.
- One "Strategy Levers" view (`renderPlanningLevers()`), reachable
  identically from every entry point that currently targets `planning_levers`
  or the Workbench's own levers section.
- No duplicate editing surface for Stress Test inputs inside the Workbench.
- The Workbench's internal layout matches its three siblings' shared
  `strategySection` primitive: same look, same open-state persistence, same
  lazy-body-only-when-open behavior.
- Every existing link that targets `planning_workbench` or `planning_levers`
  by id (the header's "Compare & Decide" button on every page, "Preview
  impact" footers, checklist closeout, source-truth banners) keeps working
  unchanged -- only where those ids redirect to changes.

## Non-goals

- No new Workbench functionality. The Change Set Builder, Unified Comparison
  Matrix, Decision panel, and Saved Planning Cases sections keep their
  current capabilities exactly; this is a location/structure/duplication
  cleanup, not a feature build. In particular, the case-store's `source`
  enum (`strategy`/`scenario`/`stress`/`manual`) is untouched -- no new
  source type is added for housing or anything else.
- No change to `build_impact` ("Impact & Build History", Reports group).
  Its own description ("Use the Planning Workbench to define the comparison,
  then use Impact & Build History to inspect...") already describes a clean,
  correct two-step relationship with the Workbench; it is out of scope here.
- No change to the Scenarios screen's remaining "Scenario Change Sets" tab
  content itself, beyond it losing its two siblings (Strategy Levers moves
  to the redirect-only `planning_levers` id which now points at the new
  Workbench screen instead of at Scenarios; the Workbench tab moves out
  entirely). Scenarios becomes a single-tab screen; `renderStrategyScreen()`
  already renders correctly with fewer entries (no special-case needed).

## Design

### 1. New `strategy_workbench` screen

Every piece `renderWorkbench()` currently assembles inline -- `sourceButtons()`,
`overrideTable()`, `matrixHtml()`, `forwardLookingHtml()`, `cardsHtml()`,
`stressSelectorHtml()`, `currentManualOverrideItems()`, `readAll()`,
`activeId()` -- is **already** exported on `window.RetirementPlanningWorkbench`
(verified against the file's own export object, `planning_workbench_ui.js`
lines 451+), even though today only `renderWorkbench()` itself calls them.
No new entry points need adding to that file: `dashboard_decomp_strategy_
workspace.js`'s new `renderStrategyWorkbench()` composes these existing
exports directly, the same way `renderStrategyOptimize()`'s Asset Allocation
entry already composes `renderAllocationRecommendation()` +
`renderAllocationPolicy()` inline.

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

(The "Decision" body above is `renderWorkbench()`'s existing `feature-grid`
block, copied verbatim -- not new markup -- just relocated from a bare
`<details>` into a `strategySection` entry.) The top "Planning Workbench
model" note is kept as a fixed intro ABOVE the `renderStrategyScreen(...)`
call, prepended in the return statement rather than folded into a specific
section -- the one deliberate, minor departure from the three sibling
screens' exact `return renderStrategyScreen([...])` minimalism, because this
sentence explains the whole page's workflow model and does not belong inside
any one section.

`renderWorkbench()` and `renderBuildImpactContext()`'s sibling in
`planning_workbench_ui.js` are otherwise unaffected -- `renderBuildImpactContext()`
still backs the separate `build_impact` step (Section 5's non-goal) and stays.
`renderWorkbench()` itself becomes dead once `dashboard.js` stops calling it
(Section 3) and is deleted, along with its entry in the `window.
RetirementPlanningWorkbench` export object; every helper it used to call
privately is already exported and keeps being used, just from the new
screen module instead.

The Strategy Levers section drops the "Stress & Probability" duplicate
entirely -- there is no `render*Html` entry for it in the list above. Stress
inputs are edited on the peer Stress Test screen; the Comparison Matrix and
Saved Cases already support a `stress` source (`normalizeSource()` in
`planning_workbench_ui.js`) and are unaffected -- only the redundant editing
surface is removed, not stress-case tracking.

### 2. One Strategy Levers view

`renderWorkbenchLeverEditorHtml()` (`dashboard_decomp_allocation_optimizer.js`)
is deleted, along with its `window.RetirementPlanningWorkbench`-side caller
in `planning_workbench_ui.js`'s old `renderWorkbench()` (which is itself
being deleted per Section 1). `renderPlanningLevers()` becomes the Workbench
screen's own Strategy Levers section body, as shown above.

`renderPlanningLevers()` loses its "Back to Planning Workbench" button (the
`<p class="small"><button ... data-step-id="planning_workbench">Back to
Planning Workbench</button></p>` line) -- once Levers lives inside the
Workbench screen itself, a button that navigates back to the Workbench is
circular. Nothing else in that function's markup changes.

### 3. Redirect wiring

In `navigation.js`'s `SECTION_REDIRECTS` map, both entries move from
`strategy_scenarios` to `strategy_workbench`:

```javascript
// before
planning_levers:{step:'strategy_scenarios',section:'levers'},
planning_workbench:{step:'strategy_scenarios',section:'workbench'},
// after
planning_levers:{step:'strategy_workbench',section:'levers'},
planning_workbench:{step:'strategy_workbench',section:'levers'},
```

`planning_workbench` redirects to the same `levers` section as
`planning_levers` rather than a `workbench` section, because "Strategy
Levers" is now the Workbench screen's first/default-open section (matching
today's behavior where clicking "Compare & Decide" or "Preview impact"
lands you on a ranked-levers view first) -- there is no separate `workbench`
section key once the Workbench IS the screen, not a section within it. Every
existing `data-step-id="planning_workbench"` button (the header's persistent
"Compare & Decide" button on every page, `dashboard.js:3831`) and every
`data-step-id="planning_levers"` button (analysisFrame footers, checklist
closeout, source-truth banners) keeps its id unchanged and simply lands on
the new screen -- no call site outside `navigation.js` needs to change.

`dashboard.js`'s `STEPS` array gains a new entry (`strategy_workbench`,
`group: "Strategy"`, following the exact shape of its three siblings) and
the existing `planning_workbench`/`planning_levers` entries are marked
`hidden: true` (matching `distribution_strategy`/`state_residency`
/`special_strategies`'s existing precedent) -- both remain in `STEPS` since
row-routing and the redirect map still key off them, they simply no longer
render their own content or show as independent nav destinations.
`dashboard.js`'s `renderMain()` switch gains
`else if (activeStep === "strategy_workbench") content +=
renderStrategyWorkbench();`, following the exact pattern of the three
existing `strategy_*` branches, placed next to them.

`STRATEGY_SCREEN_MEMBER_STEPS` (`dashboard_decomp_row_model.js`, used for
the Strategy nav group's aggregate readiness badge) gains a
`strategy_workbench: []` entry -- empty, matching the comment already there
("planning_levers and planning_workbench have no case below and own no
rows -- both are derived/computed pages") -- the Workbench screen owns no
editable plan-data rows itself, only browser-local Planning Cases.

### 4. Scenarios screen after the split

`renderStrategyScenarios()` loses its `"levers"` and `"workbench"` entries,
leaving only `"change_sets"`. No change to `renderStrategyScreen()` itself
is needed -- it already handles an arbitrary-length section array, and the
existing "first usable section opens by default" logic degrades correctly
to a single always-relevant default-open section.

## Testing

- **Frontend:** extend `tests/frontend/strategy_section_lazy_body.test.mjs`
  (the file already asserting each screen's section keys and first-visit
  open state) with a fourth screen block for `renderStrategyWorkbench()`,
  and update the existing `renderStrategyScenarios()` test to expect only
  `["change_sets"]`. Update `NEW_STEPS` and the `STEPS` wiring tests to
  include `strategy_workbench`. New tests confirming: `renderWorkbenchStressHtml`
  and `renderWorkbenchLeverEditorHtml` are gone (`typeof sandbox.X ===
  "undefined"`, matching the existing "deletions stay deleted" pattern);
  `renderPlanningLevers()`'s output no longer contains "Back to Planning
  Workbench"; `SECTION_REDIRECTS.planning_workbench` and
  `.planning_levers` both resolve to `strategy_workbench`.
- **Manual:** browser-verify the four-screen Strategy nav renders correctly,
  every "Compare & Decide" / "Preview impact" button lands on the new
  Workbench screen's Strategy Levers section, the Workbench's Change Set
  Builder / Comparison Matrix / Decision / Saved Cases sections render their
  existing content unchanged, and Scenarios now shows only Scenario Change
  Sets.
