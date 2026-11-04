# Left nav redesign: follow-up plan (resolves deviations 1-7 and 10)

Status: planned
Date: 2026-11-04
Parent: `documentation/future/superpowers/specs/2026-11-04-left-nav-redesign-design.md`, shipped in PR #390 (branch `nav-redesign`).

## Decisions (from the review of the deviations)

| # | Deviation | Decision |
|---|---|---|
| 1 | Business Succession has no input screen; listed as a workbook-sheet row under Build & Results | Keep as sheet row. Add a backlog item: build real inputs on Work Income (then re-home the row). |
| 2 | "Always on" sections hard-coded in the nav file | Derive from a section registry exported by the strategy workspace. |
| 3 | Rows with no own switch show "Follows X" | Keep as is. No work. |
| 4 | Maintain mode shows no suggested-next footer outside Track & Reconcile | Fall back to the Set up chain on other pages. |
| 5 | Host-page "not enabled" note has no switches | Per-feature "Turn on" buttons using the same setter. |
| 6 | No dependency text on rows | Serve dependency data in the taxonomy payload; show "Needs X" and "Works best with X". |
| 7 | `year_end` help entry drafted by me | Rewrite to match the Annual Maintenance Runbook. |
| 10 | No proof popover and Plan Features agree | Server-level test through both write paths. |

Deviation 8 and 9 (loosened guard tests, spec status line) are accepted as shipped.

## Workstreams

Do them in this order. A and B are independent and can share a session; C depends on nothing but touches the same note as D, so do C then D. E is independent.

### A. Maintain footer fallback (decision 4) - small
- `suggestedNext()` in `dashboard_decomp_row_model.js`: in Maintain use `maintainNext(stepId)`, and when that is empty use `SUGGESTED_NEXT[stepId]`. Keep the module-gate guard.
- Test: extend `nav_features_popover.test.mjs` (or a small row-model test) for: Maintain chain page, non-chain page falls back, gated target yields no footer.
- Model/effort: Sonnet, low. Usage: light. Drivers: one grep and a ~15 line read of `suggestedNext`.

### B. Section registry for "Always on" (decision 2) - moderate
- In `dashboard_decomp_strategy_workspace.js`, export a registry `{ stepId, key, title, gate }` for the Optimize and Workbench sections, built from the same arrays the renderers use (no second list). Keep it a plain data export so node tests can read it.
- `dashboard_decomp_nav_features.js`: replace `ALWAYS_ON_SECTIONS` with a read of that registry (sections whose `gate` is null).
- Test: every registry entry with `gate: null` appears under Always on; a gated section never does; removing the old constant leaves no duplicate list.
- Risk: the section arrays are built inside render functions (`body:` closures). Extract only titles/keys/gates, do not move render code. Check `tests/test_frontend_size_ratchet.py` per-file ceilings for the workspace file.
- Model/effort: Sonnet, medium. Usage: moderate. Drivers: Grep, then read ~150 lines around the section arrays (lines ~296-490); do not read the file whole.

### C. Dependency data (decision 6) - moderate, touches Python
- Inspect which of `requires_inputs`, `requires_outputs`, `degrades_without` hold real, user-meaningful module keys (dump them with a one-off script; most modules likely declare none).
- `config_service._module_taxonomy`: serve the chosen fields per module (`degrades_without` is already served; add `requires_outputs` or equivalent as `needs`: `[{key, name}]`). Keep names resolved server-side, as `degraded_by` does.
- Popover row: "Needs Roth Conversion" when a needed module is off (strong), "Works best with X" for `degrades_without` (soft). Only render when the dependency is currently off.
- Tests: Python test that the payload carries `needs` for a known module; node test for the row text.
- Model/effort: Opus, medium (dependency semantics are easy to get wrong). Usage: moderate. Drivers: reading `module_catalog.py` around the dataclass and one dependency-bearing module; avoid reading the 2,500-line file whole.

### D. Turn-on buttons on host-page notes (decision 5) - moderate
- `offFeaturesLineHtml()` in `dashboard_decomp_plan_features.js` renders "Optional features not enabled that would appear here: ...". Change each name to a name plus "Turn on" button calling `setPlanFeatureSwitch(key, true)`; features with no own switch (decision 3) render as plain text with their "Follows X" hint; keep the "Plan Features" link.
- After a turn-on the page re-renders (the setter already reloads), so no extra state.
- Tests: update the assertions in `feature_gated_note_off_states.test.mjs` and `plan_features.test.mjs` that match the old text; add one test that the button uses `setPlanFeatureSwitch` and skips no-switch features.
- Expensive step to scope: the note is shown on many pages, so expect a short test-fix loop on text assertions. Grep the exact old string first and fix each test once.
- Model/effort: Sonnet, medium. Usage: moderate.

### E. Year-End help and the agreement test (decisions 7 and 10) - small
- Help: read `documentation/reference/ANNUAL_MAINTENANCE_RUNBOOK.md` (year-end section only), then rewrite the `year_end` entry in `help_registry.js` with the runbook's terms (carryforward, wash sale, 1099-B, cash-year close). Terms must exist in the glossary map or the glossary test fails; add definitions where needed. Needs the user's sign-off on terminology.
- Agreement test (`tests/test_nav_feature_agreement_unit.py`): for one module-toggle feature and one plan flag, flip it with `set_feature` (popover path) and by writing the plan row the Plan Features row switch writes (`feature_row_key` / `gate_ref`), then assert identical stored value and identical `feature_enabled`. Run both directions (on and off).
- Model/effort: Sonnet, medium for the test; Sonnet, low for the help text. Usage: light.

## Backlog item (decision 1)
Build Business Succession inputs on Work Income: fields, engine wiring, help, tests. When done, change `FEATURE_HOST.business_succession` to `["income_work", "section"]`. Not part of this plan.

## Cost and sequencing
| Step | Model / effort | Relative usage (vs a 5-hour Pro session) |
|---|---|---|
| A footer fallback | Sonnet, low | Light |
| B section registry | Sonnet, medium | Moderate |
| C dependency data | Opus, medium | Moderate |
| D turn-on buttons | Sonnet, medium | Moderate (test-fix loop is the risk) |
| E help and agreement test | Sonnet, low-medium | Light |
| Final: `npm test`, `pytest -m "not slow"` to a log file with `-v -rfE`, browser check | Sonnet, medium | Moderate; the full Python run took about 47 minutes last time, so run it once at the end in the background |

Totals: moderate to heavy if done in one sitting. Split into two sessions: (A, B, E) then (C, D). Check `/usage` against these estimates as the work proceeds.

## Checks for every workstream
- Regenerate `documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md` only if imports between modules change (B may).
- New code goes in `dashboard_decomp_nav_features.js` where possible; mind `tests/test_frontend_size_ratchet.py`.
- Do not edit `DOMAINS` or `nav_group` in `src/module_catalog.py`.
