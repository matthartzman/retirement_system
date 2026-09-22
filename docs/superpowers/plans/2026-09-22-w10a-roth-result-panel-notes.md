# W10a — Roth result panel: what was built, and the judgment calls

> Execution record for **W10a** of
> `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md`
> §4, implementing #329 P5 (spec
> `docs/superpowers/specs/2026-09-19-optimizer-stress-test-rationalization-design.md`
> §4.5 path 1, §3.3, §1.3). Requires W9 — landed on this branch.

## Scope, as the plan states it

> **W10a — Roth result panel, end to end.** Path 1 (read from last build):
> `roth_optimization` / `roth_strategy_result` are already attached to the plan
> result, so this is a display change over existing data. **Scope to Roth
> only.**

Held to that. W10b (§4.7 disclosure badges) and W10c (apply-to-plan) are
separate commits in separate sessions and nothing here anticipates them: no
badge machinery, no Planning Case, no apply or pin affordance, no
`source: "optimizer"` enum value. The remaining result panels (§3.3's HSA
Drawdown, Withdrawal Sequencing, Social Security, Harvesting — the four W9
added as input-only sections) are phase 5b's "one per session", untouched.

## The gap the plan's own summary line understates

"Already attached to the plan result" is true and was the starting point, but
it describes the *server's* config dict, not anything a browser can read.
Grepping the path end to end (`optimize_roth_conversion_strategy()` →
`c['roth_optimization']` → `attach_plan_result()` → `c['roth_strategy_result']`
→ Sheet 11 / `summary_figures`) found three consumers, all server-side:
`sheets_strategy.build_sheet11`, `summary_figures.roth_strategy_benefit` (the
Executive Summary's versus-next-best row) and `governance.py`. Nothing in
`frontend/js/` reads either key, and no HTTP route serves them —
`save_result_snapshot()` writes the whole `PlanResult` to SQLite, but no
endpoint exposes that table.

So W10a is a display change over existing *data*, not over an existing
*payload*. The missing half is one hop: from the contract to the browser.

### Judgment call 1 — `plan_summary.json`, not a new endpoint or a new artifact

Three candidate carriers, all of which already exist:

| Carrier | Why not / why |
| --- | --- |
| `results_explorer_model.json` (`/api/detailed-results`) | Row- and sheet-oriented; Sheet 11 is built directly by `sheets_strategy.py` and is not in it. Would mean inventing a semantic page for a table that has one. |
| A new `/api/roth-result` route | A route per optimizer is the hand-maintained list #329 exists to end, and phase 5b adds four more. |
| **`plan_summary.json`** (`/api/summary`, and `/api/build`'s own `kpi` response) | **Chosen.** Already the artifact the UI reads for "what did the last build conclude" — `lastBuildSummary` *is* this payload. Needs no new route, and because `/api/summary` reads the file from disk, the panel survives a page reload. |

The cost is that `plan_summary.json` grows. Bounded deliberately: the payload
is a projection of the existing `RothStrategyResult`, capped at the same ten
candidates Sheet 11 prints, and **`binding_constraints_by_year` is left out** —
one row per projected year of workbook-depth diagnostics for a table the panel
does not draw. Nothing is recomputed; no engine or projection code was touched.

### Judgment call 2 — the 0-100 score moved into `summary_figures`, and Sheet 11 now reads it from there

Sheet 11's "Score (0-100)" is not a stored figure. It is normalized *inside*
`build_sheet11`, across exactly the candidates that sheet chose to print
(`candidates[:10]`), so the same candidate scores differently in a set of 4
than in a set of 10. A panel that re-derived it in JavaScript — or that used a
different cap — would put a different Score next to the same candidate on the
two surfaces. That is precisely the failure `summary_figures.py`'s own
docstring records this codebase already shipped once, when two copies of the
same definition drifted.

So `ROTH_CANDIDATE_DISPLAY_LIMIT`, `roth_candidate_objective_values()` and
`roth_candidate_relative_scores()` live in `summary_figures` — the module that
exists for figures read by more than one surface — and `build_sheet11` calls
them instead of computing the same scale inline. Identical math, deliberately:
the extraction is not an improvement to the formula, it is a removal of the
second copy. The slow test asserts it directly, reading the workbook's own
candidate table back with `openpyxl` and comparing rank, label and score
against the payload, rather than trusting that the two agree.

One behavior clarification fell out of writing it down: a candidate set with no
spread (including a one-candidate set) scores 100 across the board rather than
dividing by zero. That is what the inline version did; it is now stated and
pinned.

### Judgment call 3 — the marker follows the selected strategy, not rank 1

Sheet 11 bolds and green-fills row 1. The panel marks the row whose label
matches `selected_strategy_name`, which is **not always row 1**: a household
can name a Roth policy the optimizer would not have chosen, and the contract's
own `why_selected` text has three different sentences for exactly this
distinction. The frozen sample plan is such a plan — it runs "Fill to 22%
bracket", which the optimizer ranks second — so this is the case a reader meets
first, not a hypothetical.

This is a styling difference between the two surfaces, not a numeric one, and
it is the more truthful of the two.

### The bug that judgment call 3 exposed

Putting the marker next to the per-candidate sentence made a live defect plain.
`_explain_candidate()` (`src/result_contract.py`) guarded its "Selected
because..." wording with:

```python
if rank == 1 and label == str(selected.get('selected_label', label)):
```

`selected` is a *candidate* dict. Candidate dicts carry `label`, never
`selected_label`, so the default fired every time and the comparison reduced to
`label == label` — meaning **the top-ranked row always read "Selected because it
produced the highest total objective score"**, whether or not it was the
strategy in the plan. On the frozen sample plan the panel would have said that
on row 1 while marking row 2 "In the plan", and row 2's own sentence would have
read "Not selected".

Fixed by comparing against the selected candidate's actual label, with the
rank-1 wording unchanged for the case it was written for and two new branches
for the two cases it silently mishandled:

* selected but not top-ranked → "In the plan: explicitly chosen rather than
  ranked first by the optimizer."
* top-ranked but not selected → "Ranked first by the optimizer ... but not the
  strategy this plan is running."

**This is display text, not a calculation**, so it sits inside the global "no
calculation changes" constraint: `tools/regen_golden_master.py measure` is
`+0.00` on both pins after it. Sheet 11 has carried the same sentence with the
same defect all along and now carries the corrected one; this panel is only the
first surface to put the sentence and the marker side by side, where the
contradiction was visible. Fixing it was preferred to shipping a panel that
contradicts itself on the flagship fixture, and it is pinned by two tests (one
of which fails against the old guard).

### Judgment call 4 — the panel lives in `dashboard_decomp_allocation_optimizer.js`

That file already owns `renderRothConversion()`, the Roth policy/IRMAA helpers
the panel's copy has to agree with, and `planningLeversBaselineReady()` — the
gate §4.5 names for this exact path. Splitting the result renderer from the
input renderer it sits above would have put one section's two halves in two
files. `dashboard.js` is untouched, so `DASHBOARD_JS_MAX_LINES` stays flat at
7,201 and no extraction was owed.

If 5b's four repetitions each add a panel here, the file becomes the natural
extraction candidate — `dashboard_decomp_optimizer_results.js` — and that is the
standard next step, not a reason to pre-build the file for one panel.

### Judgment call 5 — three empty states, each naming its own reason

`planningLeversBaselineReady()` gates the panel, per §4.5. But "no baseline" is
not the only way to have no result, and one generic placeholder for all of them
would misdirect a reader:

1. **No baseline.** A short note saying the result appears once the plan is
   built, and that the controls below stage the inputs. Deliberately *not*
   `planningLeversPlaceholder()` — that is a full-page empty state for the
   Planning Levers screen, and dropping it inside one collapsible section would
   bury the controls that are the rest of the section.
2. **Baseline, result not read yet.** A one-shot `/api/summary` fetch and a
   "reading..." line, re-rendering when it lands.
3. **Baseline, build recorded no result.** Says exactly that and points at
   rebuilding. Reached by a plan whose newest build predates this payload, and
   by one whose Roth policy left the optimizer nothing to score.

The fetch latches on *completion*, not on success. `renderMain()` re-renders the
whole tree on every field edit, so a state-3 plan would otherwise re-fetch on
every keystroke on this page. A newer build still wins over the cached read,
because `runBuild()` sets `lastBuildSummary` from the build's own response and
that source is checked first.

### What the panel does not do

- **No apply, pin or lock-in affordance.** §4.4's three-state footer bar is
  W10c's, and §4.3's "Let the plan keep optimizing this" / "Lock in this
  schedule" pair with it.
- **No row badges, no section banner.** §4.7 is W10b's, built on
  `dashboard_source_truth_banners.js`. The panel prints the contract's own
  `why_selected` sentence, which already says whether the optimizer or the user
  picked the winner; it does not add a second, differently-styled way of saying
  a value is not what you think it is, which is the thing §4.7 explicitly warns
  against.
- **No calculation changes.** The one Python behavior change is display text
  (above). The `summary_figures` extraction is a move, not a rewrite.
- **Hides nothing.** The global constraint — no switch may render a row
  invisible when that row holds a user-entered value — is untouched: the panel
  is added above the existing controls and removes no row. The section keeps
  W9's `gate: "roth_conversion"` exactly as it was.

## Verification

- `tools/regen_golden_master.py measure` — exact match, `terminal_nw +0.00`,
  `lifetime_tax +0.00`. Expected: this is a display-only change, and the one
  Python behavior change is a sentence.
- `pytest -m "not slow and not nightly" -n auto --dist loadfile` (CI's own
  invocation) — green.
- **A real subprocess build**, not a registry-level assertion: `tools/
  build_workbook.py` against the frozen sample plan, then `plan_summary.json`
  and `retirement_plan.xlsx` both read back and compared candidate-for-
  candidate. This is what caught judgment call 3's case (the frozen plan's
  selected strategy is rank 2) and the `_explain_candidate` bug, neither of
  which any synthetic payload would have shown.
- **The panel rendered against that real payload** through the same
  `loadDashboardSandbox()` the frontend tests use, and the HTML read by hand —
  which is how the "Selected because..." / "In the plan" contradiction was
  actually spotted.
- `tests/test_roth_result_panel_payload_functional.py` — 9 fast + 1 slow. The
  slow one is the workbook-versus-payload comparison above; the two
  `_explain_candidate` tests fail against the old guard (confirmed by reverting
  it).
- `tests/frontend/roth_optimizer_result_panel.test.mjs` — 12 cases, including
  the marker following the selected strategy rather than rank 1, the relative-
  score disclosure, the trimmed-list count, null figures reading as "Not
  available" rather than `$0`, and escaping.
- `npm test` — 494/496. The two failures are in
  `tests/frontend/js_codemod_parser_offsets.test.mjs`, the pre-existing
  jscodeshift-offset environment difference W6/W8b/W9's notes all record;
  reproduced identically with this workstream's entire diff stashed.
- `node tools/js_codemod/census.mjs --check` — regenerated, no drift (the new
  window-bridge entries are the only change).
- `ruff` — clean on every changed Python file.

### Frontend size ratchet

`DASHBOARD_JS_MAX_LINES` **unchanged at 7,201** — `dashboard.js` is not touched,
so nothing was owed and nothing was padded. `TOTAL_JS_MAX_LINES` raised 33,816 →
33,992, the measured total with no slack: genuine new behavior (the renderer,
its three empty states, and the `/api/summary` read), per that ceiling's own
contract.

## Consequences for later workstreams

- **W10b** (§4.7 badges) inherits a panel that already states which strategy is
  in the plan and prints the contract's why-selected sentence. The badge work
  is about *rows* — plan-data values that are live optimizer output — which is a
  different surface from this panel, and `dashboard_source_truth_banners.js`
  remains the place for it.
- **W10c** (apply-to-plan) inherits the thing §4.5 calls its prerequisite: a
  UI-visible result for Roth. `rothStrategyResultFromLastBuild()` is the
  accessor an optimizer patch would read `after` values from, and
  `selected_policy` is in the payload precisely because §4.6's computed
  *applied* / *diverged* comparison needs to name the policy row the plan is
  running.
- **Phase 5b** (the remaining panels, one per session) inherits the pattern in
  three named pieces, which is what "proven pattern" has to mean to be cheap:
  (1) a `*_result_payload()` projection in `summary_figures` feeding
  `plan_summary.json`, with any cross-surface scale computed there rather than
  in JS; (2) a pure `*ResultPanelHtml(result)` renderer plus a thin stateful
  wrapper holding the gate, the fetch and the empty states; (3) verification by
  a real build compared against the workbook sheet, because that is what found
  both defects here. **Do not batch them** — the plan says so, and both findings
  in this session came from looking closely at one optimizer's real output.
- Whoever next touches `_explain_candidate` should know its three branches are
  now load-bearing on two surfaces, not one.
