# Contextual Help Panel: move all explanation to the right panel

Status: approved (decisions accepted; Phases 0 and 1 implemented 2026-10-21, Phases 2-5 planned). Extends WI-033 — see `WI-033_plain_english_help_review.md` and `WI-033_glossary_draft.md`. Measured counts are in `ui_prose_inventory_summary.md`.

## 1. Context and problem

The center panel mixes three jobs: labels and inputs, live outputs, and prose. Prose appears at four levels:

| Level | Where it lives today | Rough size (search counts, not yet classified) |
|---|---|---|
| Page | `STEPS` in `frontend/js/dashboard.js`: `desc` (also shown in the left nav), `intro`, `help`; the "question" box in the center; `STEP_HELP` (`pageHelp(...)`, 56 entries) in the right panel | 28 pages |
| Section | `section-note` blocks and sub-headings in about 30 `dashboard_decomp_*.js` / `*_ui.js` modules | about 200 |
| Field | field notes and units, `title=` tooltips, the "i" button that opens `showFieldHelp` in the right panel | about 63 tooltips; field help already in the panel |
| Message | `class="small"` lines, banners, empty states, warnings | about 240 + 24 banners |

Problems:
1. The same page is explained up to four times (nav `desc`, `intro`, `help`, `STEP_HELP`), plus the WI-033 plain summary.
2. Prose pushes inputs down the page, most of all on the pre-build pages a new user needs first.
3. The right panel is opt-in: closed by default, stacked below the page under 1180px wide, and field help overwrites page help.

Goal: the center panel holds labels, inputs and outputs. Explanation lives in the right panel, with one source per page, section and field.

## 2. Requirements and non-goals

Requirements:
- R1. No explanatory prose in the center panel (class A below).
- R2. State, warning and error messages stay in the center, next to what they refer to, at most one line (classes B and C).
- R3. Help is discoverable for first-time users, and nothing is hidden by default on the pre-build pages.
- R4. One help record per page, section and field; the nav one-liner and WI-033 plain summary come from it.
- R5. The WI-033 glossary is shown per page in the panel.
- R6. Keyboard and screen-reader accessible; works under 1180px wide.
- R7. No change to engine, plan data or saved formats.

Non-goals: rewriting help wording beyond the WI-033 read-through; changing the left nav structure; making terms inside prose clickable (follow-up).

## 3. Decision: classify, then follow focus

Every string is placed in one class:

| Class | Meaning | Action |
|---|---|---|
| A | Explains what something is, how it works, what to choose | Move to the panel |
| B | State or empty ("No data yet", "Build is stale") | Stay; one line |
| C | Warning, error, or consequence ("this overrides the Auto Insurance budget") | Stay, beside the field |
| D | Duplicate: adds no information beyond another string that stays (see 3.1) | Delete |

### 3.1 Duplicate rule (aggressive)
A string is class D when it adds no incremental information over another string that stays, even if the wording, grammar or word choice differs. The test: delete it and ask whether a reader could now do or understand anything less. If not, it goes.

- Compare across levels and surfaces, not only within one page: nav `desc`, `intro`, `help`, `STEP_HELP`, section notes, field notes, tooltips and the WI-033 summary all count.
- Keep the surviving string by this order: (1) the one with the most information, (2) the one nearest to where the reader needs it, (3) the plainest wording (WI-033 audience).
- Fold any extra fact from the deleted string into the survivor before deleting; never lose information, only repetition.
- A string that restates the label, the page title, or the obvious effect of the control ("Enter the amount" under "Amount") is class D.
- Partial overlap: keep only the non-overlapping part.
- Page-level strings are merged by synthesis, not deleted pairwise: strings that carry different facts are combined into one record and rationalized (see 5, Phase 2). D is used for pure repetition only.
- When unsure, mark it D with a note in the Phase 0 CSV (`merged_into` column); the reviewer reverses a call there, so every deletion is traceable and reversible before code changes.

Rejected alternatives:
- Move everything including B and C: breaks error identification (WCAG) and hides consequences when the panel is closed.
- Leave the panel opt-in everywhere: new users never see it.
- Inline tooltips instead of the panel: poor on touch and keyboard, and cannot hold the glossary.

## 4. Target design

### 4.1 Help registry (single source)
New module `frontend/js/help_registry.js` (data and lookup only; replaces `help_glossary.js` data and the prose parts of `STEPS` / `STEP_HELP`):

```
HELP_PAGES[stepId]    = { summary, whatFor, connections, options, impact, terms[] }
HELP_SECTIONS[key]    = { pageId, title, body }          // key = the section's data attribute
HELP_FIELDS[rowKey]   = existing fieldGuidance output     // stays generated by showFieldHelp
GLOSSARY[term]        = definition                        // from WI-033
```

`STEPS` keeps `id`, `group`, `title`, `helpLink`; its `desc` becomes `HELP_PAGES[id].summary`.

### 4.2 Panel behaviour
- **Follows the user:** page help on arrival; section help when a section opens or receives focus; field help on field focus (today it needs a click on "i"). A pinned entry stays until the user changes context.
- **Fixed layout:** "In plain English" line, then what it is for, connections, options, impact, then "Words on this page".
- **Discoverability:** panel opens by default on the 11 pre-build pages and remembers the user closing it (`retirementHelpOpen` already exists in localStorage). A small "?" beside the page title opens it everywhere.
- **Narrow screens:** below 1180px the panel becomes a slide-over sheet opened by the "?" and "i" buttons, not a block stacked below the page.
- **Accessibility:** `aria-live="polite"` is not used on focus changes (it would chatter); the panel is a labelled region and "i" buttons use `aria-controls`.

### 4.3 Center panel after the change
Page header = title, status badge, actions. Sections = label, input, output. Class B and C messages remain, using the existing `section-note` styles with a `data-kind="state|warn"` attribute so the guard test can tell them from prose.

## 5. Implementation plan

Effort is stated against a 5-hour Claude Code Pro session. Check `/usage` as each phase runs.

### Phase 0: inventory and classification (Sonnet, medium; light)
- Write `tools/extract_ui_prose.py`: scans `frontend/js/*.js` and `frontend/index.html` for template-literal and string prose in `section-note`, `small`, `muted`, `question`, `title=`, banner, `STEPS.intro/help`, and `pageHelp(` calls; writes `ui_prose_inventory.csv` (to be created in documentation/future/) (file, line, class guess, text, level, step id).
- Review the CSV together; correct the class column. Replace the estimates in this plan with measured counts.
- Add `merged_into` and `unique_info_kept` columns for class D rows (3.1). Group near-duplicates by step id and meaning, not by exact text.
- Exit: every string has a class and a destination (page, section or field record, or delete).
- Cost driver: script runs, not reading whole files (do not open `dashboard.js` or `dashboard_decomp_row_model.js` linearly; use Grep and offset reads).

### Phase 1: registry and panel mechanics (Opus, high; moderate)
- Create `help_registry.js`; load it from `frontend/index.html`; update the frozen script list in `tests/frontend/wi015_script_order_wrapper_guard.test.mjs` and the total ceiling in `tests/test_frontend_size_ratchet.py`.
- Panel follow-focus: extend `showStepHelp` / `showFieldHelp` / `ensureHelpPanelVisible`; add section help hook; default-open on pre-build pages; narrow-screen sheet; "?" button in the page header.
- Keep the old `STEP_HELP` as a fallback until Phase 2 completes so nothing goes blank.
- Tests: new `tests/frontend/help_panel_follow_focus.test.mjs`; extend `plain_english_help.test.mjs`.
- Exit: panel shows page, section and field help from the registry on a pilot page (Household & People); other pages unchanged.
- As built: `help_glossary.js` was renamed to `help_registry.js` (same script slot) so GLOSSARY keeps one source. `showStepHelp` (dashboard.js) and `showFieldHelp` / `ensureHelpPanelVisible` (`dashboard_decomp_row_model.js`) are the real functions; before this phase `showStepHelp` called `ensureHelpPanelVisible()` on every `renderMain`, so the panel was in fact forced open on every page. Now the open state is set only when the page changes (`arriveAtPage`), and a re-render keeps pinned field or section help. The 11 pre-build pages are `PRE_BUILD_PAGES` (Household & People through Estate & Legacy in nav order); default-open applies above 1180px only. Explicit openers are any control with `aria-controls="helpPanel"` (the "i" badges, the new "?" buttons) plus Step Help (`openStepHelp`).

### Phase 2: page level (Sonnet, high; moderate)
Phase 0 measured 284 page-level strings (STEPS `desc` / `intro` / `help` for 28 pages, plus `pageHelp` arguments for 43 STEP_HELP keys). The automated duplicate pass found only 6, because the sources for one page mostly carry different facts. They are therefore merged by synthesis, one record per page.

- **Synthesize per page, all 28.** For each page, take every source (`desc`, `intro`, `help`, `pageHelp` meaning / connections / options / impact, and the WI-033 plain summary) and write one `HELP_PAGES[id]` record:
  - `summary`: the WI-033 plain one-liner; the nav `desc` is derived from it.
  - `whatFor`: `intro` plus `meaning`.
  - `connections`, `options`, `impact`: the matching `pageHelp` arguments, with `help` folded into whichever slot it fits.
  - A fact stated in several sources is written once; survivor order is the 3.1 order (most information, nearest the reader, plainest wording).
- **Fact ledger.** Each page's draft lists every source sentence with a fate: kept, merged into a named slot, or dropped as repetition. A script checks that every number, percent, age, proper noun and glossary term in the sources still appears in the merged record and flags any that do not.
- **Review in batches.** Show each page as sources beside the merged record with ledger flags: first the 11 pre-build pages (this overlaps the WI-033 read-through), then batches of 4 or 5 pages until all 28 are reviewed. Sonnet drafts, the reviewer edits, then the record is applied.
- **Inventory trace.** Add a `slot` column to `ui_prose_inventory.csv` (for example `HELP_PAGES[income_work].impact`). Every page-level row must land in a slot or be marked D, so the check is mechanical. Rows keep class A with `merged_into` set until the code change.
- **As built (Phase 2a, drafting only):** `tools/page_help_ledger.py` (`check`, `review`, `slots`), `page_help_drafts.json` (28 records plus per-sentence ledger), `page_help_review.md` (review order: the 11 `PRE_BUILD_PAGES`, then four batches), and the `slot` column in `ui_prose_inventory.csv`. The 21 legacy STEP_HELP keys that are not STEPS pages (for example `monte_carlo_options`, `review`, `spending_travel`) are folded into their parent page (`SUB_PAGE` in the tool); their section-level text is Phase 3's job. Nothing in the app changed.
- Remove the `intro` line and "question" box from the center (`renderMain` at the `pane-head` / `question` render); change the nav `desc` source.
- Update tests that assert on `intro` / `help` text.
- Exit: all 28 page records reviewed; no page shows a question box or intro paragraph; nav and panel text come from one record; the ledger check reports no lost facts.

### Phase 3: section and field level (Sonnet, medium; heavy, about two sessions)
- Work in batches by module, from the Phase 0 CSV, one batch per `dashboard_decomp_*` group: Income and Benefits; Spending; Investments and Property; Insurance, Estate, Taxes; Strategy; Reports and Review; Settings.
- For each class A string: add a `HELP_SECTIONS` / field entry, remove the node. For class B and C: shorten to one line and tag `data-kind`.
- Parallelise by module group (separate files, so no merge conflicts); each batch runs its own module tests.
- Apply class D deletions from the CSV in the same pass; each deleted string's `merged_into` target must exist.
- Exit: Phase 0 CSV shows every class A string moved or deleted.
- **As built (batches 1-3, Income and Benefits; Spending; Investments and Property):** 36 `HELP_SECTIONS` records, 10 modules, tests updated, ceilings reset; see `ui_prose_inventory_summary.md`. Later groups remain.
- **As built (Phase 3b: Insurance, Estate, Taxes; Strategy; Reports and Review; Settings):** 54 `HELP_SECTIONS` records in one `// Phase 3b:` block at the start of `help_registry.js`. Section prose left the center; wrappers carry `data-help-section` (a few headings use the section "?" button instead). Class B/C lines were shortened and tagged `data-kind="state|warn"`. The CSV `destination` column records each row as `moved: ...`, `deleted: ...` or `kept: ...`; two automated D calls were reversed (a loading state; tax-loss vs gain harvesting). `admin.html` is a separate shell with its own panel, so `admin.js` prose moved into its `ADMIN_HELP` entries, and config-card prose (Local backups, auto-update import) went into `SYSTEM_CONFIG_FIELD_HELP`. No `HELP_FIELDS` entries were needed: none of these modules' class A text was row-level field help.

### Phase 4: tests and guard (Sonnet, high; moderate)
- Fix the tests coupled to center text (found so far: `tests/test_field_finder_category_grouping_functional.py`, `tests/test_frozen_sample_plan_golden_master_regression.py`, `tests/frontend/strategy_section_lazy_body.test.mjs`; the Phase 0 scan lists the rest).
- Add a guard test that fails when new `section-note` / `small` nodes lack `data-kind` or exceed one line of text, so prose cannot creep back.
- Add Playwright checks: panel opens by default on a pre-build page, follows focus, works at 1000px width, keyboard-only path.
- Watch the repeated test-fix loop; fix one failing group at a time.
- **As built (Phase 4):** `tests/frontend/ui_prose_guard.test.mjs` (static guard, 120-character line limit), `tests/e2e/contextual-help-panel.spec.js` (default-open, follow focus, 1000px sheet, keyboard path, rendered-DOM check), `tools/verify_ui_prose_inventory.py` with `tests/test_ui_prose_inventory_closeout.py`. About 100 leftover nodes from Phases 2-3 were moved to the registry (95 `HELP_SECTIONS` records now) or shortened. Final counts are in `ui_prose_inventory_summary.md`.

### Phase 5: content pass (light)
- Fold the WI-033 non-expert read-through into the registry text; confirm the glossary terms; regenerate nothing by script after this point (the registry is the source).

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Users do not find help | Default-open on pre-build pages; "?" in every header; remembered state |
| Warnings or consequences lost with the panel closed | Classes B and C stay in the center by rule; guard test |
| Merging pages loses a fact | Per-page fact ledger plus an automated check that numbers and terms survive; all 28 pages reviewed |
| Aggressive deletion removes something useful | Fold unique facts into the survivor first; Phase 0 CSV records `merged_into` so each call is reviewed and reversible before code changes |
| Large diff across 30 modules | Batches by module group; each batch independently shippable |
| Test churn | Phase 0 lists coupled tests up front; fix per group |
| Size ratchets | Moving text out should lower `dashboard.js`; lower the ceilings to measured size after each phase |
| Generated files go stale | Re-run `tools/generate_system_diagram.py` when a JS file is added; add `Status:` lines to new docs |
| Panel steals focus on every field | Update on focus only; no focus movement into the panel |

## 7. Verification

- Python: `pytest -m "not slow"`. Frontend: `npm test`. Known pre-existing failure: `tests/frontend/js_codemod_parser_offsets.test.mjs`.
- Visual: Playwright screenshots of the 11 pre-build pages before and after.
- Acceptance: a non-expert completes the WI-033 read-through using only the panel; no class A string remains in the Phase 0 CSV.

## 8. Rough effort

| Phase | Model / effort | Usage vs a 5-hour session |
|---|---|---|
| 0 Inventory | Sonnet, medium | Light |
| 1 Registry and panel | Opus, high | Moderate |
| 2 Page level | Sonnet, high | Moderate |
| 3 Section and field | Sonnet, medium (parallel batches) | Heavy, about 2 sessions |
| 4 Tests and guard | Sonnet, high | Moderate |
| 5 Content | Sonnet, medium | Light |

Total about 4 to 6 sessions. To limit cost, ship Phases 0 to 2 first: they remove the page-level boxes, which is most of the visible clutter. Expensive steps: broad searches across 30 modules (use the Phase 0 CSV instead) and the Phase 4 test-fix loop.

## 9. Decisions (resolved)

1. Default-open panel on the 11 pre-build pages: **yes**, and remember if the user closes it.
2. Clickable glossary terms inside panel text: **follow-up**, not in this plan.
3. Class B empty and state messages: **stay in the center**, one line each.
4. Duplicates: **aggressive deletion** under rule 3.1; page-level strings with different facts are **merged and rationalized** into one record per page, all 28 reviewed (Phase 2).
