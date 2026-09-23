# W13 — Left-nav realignment: what was built, and the judgment calls

> Execution record for **W13** of
> `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md`
> §4, implementing #330 P8 / Q6. Requires W12 — landed on this branch.

## Scope, as the plan states it

> Scope: add Taxes and Family & Business nav groups; promote Housing out of
> Spending, so "where I turn it on" matches "where I use it".
>
> Files: `SECTION_REDIRECTS`, every `helpLink` target, `SUGGESTED_NEXT`, step
> ordering in `dashboard.js`'s `STEPS`.
>
> **This is the largest item in the plan and its entire risk is scope leak.**

Spec source: `docs/superpowers/specs/2026-09-19-modular-feature-nav-design.md`
§4.1 (domain is the primary axis, kind is a badge), §4.2 (the ten domains and
the nav group each maps to), §4.3 (the four placements), §7 Q6 (this
workstream's own question), §8 phase 8.

## The one precondition worth recording

The task brief asserted W1–W12 were all landed. On this session's first
checkout that was **not** true: `git log` showed the branch ending at W10c,
and `strategySectionGatedNote()` was still un-generalized (no
`featureGatedNote`). The first commit below was therefore written against a
pre-W12 tree. W11 and W12 had in fact been pushed to the remote in the
meantime — the local clone was stale, not the branch — and the merge is
commit 2 of this series. Nothing was built on the wrong base, but the check
is worth naming: W13's dependency on W12 is real (see "Off-states" below),
and "the plan says it landed" is not the same as "the branch has it."

## The result

| Nav group | Members (visible) | Change |
| --- | --- | --- |
| Plan Status | Plan Status | — |
| People and Income | Household & People, Work Income, SS/Pensions/Annuities | — |
| Spending | Spending Model, Wellness | **loses Housing** |
| **Housing & Property** | Housing, Home Equity Line | **new** |
| Assets & Protection | Investment Holdings, Reserve Requirements, Insurance, Other Assets and Liabilities, Estate Inputs | loses Home Equity Line |
| **Taxes** | Roth Conversion, Charitable Giving | **new** |
| **Family & Business** | Education & Equity Comp | **new** |
| Strategy | Optimize, Stress Test, Scenarios, Workbench | Optimize loses 2 of its 8 sections |
| Reports & Review / Reports / Settings | — | — |

Group order follows `DOMAINS` (`src/module_catalog.py`) wherever the nav has
an equivalent. It is not identical, and deliberately: the nav's single
"Assets & Protection" group conflates three catalog domains (Investments,
Assets & Protection, Estate & Legacy), so Taxes sits *after* it rather than
before, keeping the nav's existing "enter the facts, then decide" order.
Splitting Assets & Protection into three is not in this workstream's scope.

Nav groups are formed by `renderSteps()` from **consecutive runs of the same
`group` string in `STEPS`** — there is no separate group registry. So every
group change here is a reorder of the `STEPS` array plus a `group:` value,
and no grouping code changed. The Field Finder's category list
(`fieldFinderCategoryOrder()`) derives from the same array, so it followed
for free.

## What landed, commit by commit

**1. Housing promoted out of Spending.** `spending_mortgage_events`
("Housing") moves into a new `Housing & Property` group, and `heloc_strategy`
moves with it. `SUGGESTED_NEXT` gains a forward link out of the new group,
and `suggestedNext()` gains a guard (below). `SUGGESTED_NEXT`/
`suggestedNext()` move to `dashboard_decomp_row_model.js`.

**2. (merge)** W11 + W12 from the remote.

**3. The Taxes group.** `roth_conversion` and `entity_charitable` stop being
hidden shells redirected into Optimize and become real steps: `group`/`hidden`
flipped, their two `SECTION_REDIRECTS` entries deleted, both added to
`AUTOSAVE_STEPS`, both removed from `STRATEGY_SCREEN_MEMBER_STEPS.
strategy_optimize` and from `renderStrategyOptimize()`'s section list, and the
three `helpLink` labels renamed to "Open Taxes → Roth Conversion".

**4. The Family & Business group.** A new `family_business` step rendering
the two Family & Business row groups that already exist on Other Assets and
Liabilities. `SPENDING_COMPLETION`/`spendingFlowFooterHtml` move to
`dashboard_decomp_row_model.js` to pay for it under the ratchet.

## Judgment call — HELOC moves to Housing & Property

Not named in the scope line, and W9 deliberately put it under Assets &
Protection, citing §4.3's "Assets & Protection exists, and it is where HELOC
goes." But §4.2's own table and, decisively, the **catalog** disagree with
that prose: `heloc` is declared `domain=HOUSING_PROPERTY` (W1), which is why
Plan Features lists its switch under Housing & Property today. Leaving the
step under Assets & Protection would have re-created, inside this
workstream's own new group, the exact divergence it exists to close: turn
HELOC on under "Housing & Property", then fail to find it there. The catalog
is the source of truth for domain; §4.3's sentence predates the declaration.
One `group:` string; the Other Assets page keeps its read-only HELOC summary
and its "Open HELOC strategy page" button.

## Judgment call — what goes in Taxes, and what stays in Optimize

The Taxes domain has eight catalog modules. Only two own a page
(`dashboard_step`): `roth_conversion_plan` and `charitable_giving`. Those two
moved. The other Taxes-domain features on the Optimize screen — **HSA
Drawdown** and **Harvesting** (TLH + gain harvest) — did **not**, for two
reasons:

1. Neither owns a page. Both are `strategySection`s built by W9 out of
   row-filtering blocks borrowed from the Spending workspace's Withdrawal
   Order tab (`hsaWithdrawalPolicyBlock`, `taxLossHarvestingBlock`,
   `gainHarvestBlock`). Moving them means inventing pages, which is new UI,
   not nav realignment.
2. Moving them would leave Optimize as Asset Allocation + Withdrawal
   Sequencing + Social Security + Next Housing Move — i.e. it would turn
   "add two nav groups" into "redesign the Optimize screen." That is the
   scope leak the plan names as this workstream's entire risk.

Recorded as a follow-up below, not done here.

## Judgment call — Family & Business is a second way *in*, not a data move

This is the one group with no page to regroup. Its five catalog modules
(`education_funding_529`, `equity_compensation`, `business_succession`,
`scorp_vs_llc`, `special_needs_planning`) declare **no** `dashboard_step` at
all. Two of them declare `csv_sections` — `Education Funding` and `Equity
Compensation` — and those rows render as groups inside `renderAssetsSpecial()`
(Other Assets and Liabilities). The rest have no plan-input surface of their
own: S-Corp/entity choice is on Work Income.

Two ways to make the group real:

- **Move the rows onto a new page.** Rejected. It means changing
  `rawRowsForStep("assets_special")`, rewriting `renderAssetsSpecial()`, and
  re-homing the 529/Equity-Comp halves of W12's *just-landed* no-hidden-data
  fix — none of which is in the scope line's file list, and all of which is
  page surgery rather than navigation.
- **Add a nav destination that renders the same rows, leaving them where
  they live.** Taken. It is precisely W9's own precedent, in W9's own words:
  "Social Security has no page of its own — its claiming-age rows live on the
  `income_retirement` step... This filters to the Social Security rows only
  ... and links out for the rest, rather than duplicating them here."

So: `renderAssetsSpecial()`'s 529 and Equity Compensation groups were
**extracted** into `moduleGatedAssetGroup()`/`familyBusinessGroupsHtml()`
(`dashboard_decomp_assets_other.js`), and both pages call the same two
functions. There is one implementation of the gated-group rendering, not a
copy — which matters most for W12's invariant, whose fix now cannot drift
between the two entry points.

Consequences, all deliberate:

- `BUILD_IMPACT_SOURCE_STEP_IDS` deliberately does **not** list
  `family_business`, so `sourceStepForRow()` still answers `assets_special`
  for every one of these rows. Build Impact, the Field Finder, the closeout
  checklist and every source-jump button are untouched. Tested.
- `rawRowsForStep("family_business")` *is* added, so the step gets a real
  readiness badge and works in search mode. `overallStats()` reads `rows`
  directly rather than summing per-step, so nothing double-counts.
- The rows are editable from both pages. That is the same trade W9 accepted
  for Social Security, and `fieldHtml` keys by `row_index`, so the two views
  write the same row.

## Judgment call — the new step is not module-gated

`family_business` is owned by *two* modules, so there is no single
`dashboard_step` to declare, and the only precedent for "hide when all of N
are off" is `strategy_stress`'s hand-written branch in
`stepGatedByOptionalModule()` — the sort of branch W6/W9 spent two
workstreams removing. Left ungated: with a module off, its group shows W12's
`featureGatedNote()` with an inline "Turn on" switch *and* the retained rows
below it. That is §5.2's Collapsed-with-a-note state and §5.1's "offer the
switch inline, because the user who is reading that note has already
decided" — a better answer here than hiding, and it needs no new gate
mechanism.

## Off-states: why W12 is a real dependency

Promoting `roth_conversion`/`entity_charitable` to nav steps hands their
off-state to `visibleSteps()`, i.e. **Hidden** — which is exactly the
contract `module_catalog.py` already declares for `dashboard_step` ("the step
is hidden while the module is off") and exactly what W12's own regression
test pins. Nothing becomes *less* reachable than it was: a gated
`strategySection` already replaced its body with the note rather than
rendering the rows, so the data was equally unrendered before. What changes
is where the switch is offered — Plan Features, which is what W4 built it
for, and which W9 already wired with plan-flag link rows pointing at
`entity_charitable` for DAF and QCD.

`setStep('roth_conversion')` and `setStep('entity_charitable')` still resolve
when the module is off (`visibleSteps()` keeps `activeStep`), so those link
rows land, exactly as they do for `heloc_strategy`.

## `suggestedNext()` gained a guard

`SUGGESTED_NEXT` now points at module-gated steps for the first time, and
`suggestedNext()` did not check gating — it would have rendered a footer
link to a page the nav is not showing, which is the dead end
`tests/e2e/nav-integrity.spec.js` exists to catch. One line:
`if (!st || stepGatedByOptionalModule(st.id)) return ""`. It also covers the
pre-existing entries, none of which happened to name a gated step.

## Size ratchet

`tests/test_frontend_size_ratchet.py`'s `DASHBOARD_JS_MAX_LINES` is a
"do not raise" ceiling with **zero** headroom at the start of this workstream
(7,201 lines, ceiling 7,201). Every commit here therefore had to pay for its
own new lines by moving something out. What moved, and why each is the right
thing to move rather than an arbitrary offset:

- `SUGGESTED_NEXT`/`suggestedNext()` → `dashboard_decomp_row_model.js`, beside
  `visibleSteps()`/`stepGatedByOptionalModule()`, the two functions that
  decide whether the step a suggestion names is reachable at all. (The new
  guard reads one of them.)
- `SPENDING_COMPLETION`/`spendingFlowFooterHtml()` → the same file, beside
  `SUGGESTED_NEXT`: `renderMain()` picks between the two on one line, so they
  are two halves of "what does this page point at next."

`dashboard.js` **fell** on all three commits: 7,201 → 7,192 → 7,198 → 7,195,
while gaining a STEPS entry, a `pageHelp` entry and a dispatch case.
`TOTAL_JS_MAX_LINES` rose to the measured total in each commit, with the
reason recorded in the constant's own comment block per its contract.

## Verification

- **`tools/regen_golden_master.py measure` — `MATCH`, `+0.00` on both pins**
  (`terminal_nw=5,438,505.25`, `lifetime_tax=1,255,734.10`). Expected: no
  engine, catalog, or `src/` calculation file is touched by this workstream
  at all.
- **`npm test` — 647 pass, 2 fail.** Both failures are inside
  `js_codemod_parser_offsets.test.mjs` ("jscodeshift offsets"), the
  pre-existing environment difference W6/W8b/W9/W12's own notes already
  record. Reproduced identically on an unmodified checkout of this branch
  before any W13 change, so it is not this diff.
- **`pytest -m "not slow and not nightly"` — green**, run after each commit.
  One real failure surfaced and was fixed, not papered over:
  `test_distribution_strategy_buttons_regression.py` asserted that
  `roth_conversion` *has* a `SECTION_REDIRECTS` entry (see the table below).
- **`npx playwright test` — the e2e suite**, including
  `nav-integrity.spec.js`'s "no dead ends" walk over every `[data-step-id]`
  in the rendered nav. That spec passes with all three new groups present.
- Codemod/census kept in sync (`tools/js_codemod/census.mjs` then
  `convert_dashboard.mjs`) after each commit that changed dashboard.js's
  top-level declarations — moving `suggestedNext` out of the file changes the
  generated `Object.assign(window, {...})` bridge, which
  `tests/test_dashboard_js_module_bridge_regression.py` pins.

### Container caveat for whoever verifies next

This container needed both `npm ci` and a Python venv
(`uv pip install -r requirements.txt -r requirements-dev.txt`) before
anything ran — the same caveat W8a/W8b/W9/W12's verification sections
recorded for theirs.

Playwright additionally needs an override here: the repo pins
`@playwright/test` 1.62.1, which looks for `chromium-1234`, while the image
ships `chromium-1194` under `PLAYWRIGHT_BROWSERS_PATH`. A plain
`npx playwright test` therefore fails all 21 specs at browser launch, with
zero signal about the diff. Run it with a throwaway config that sets
`launchOptions.executablePath` to `/opt/pw-browsers/chromium` and leaves
`playwright.config.js` alone; the repo config is deliberately **not**
changed for a container quirk. The e2e server also spawns bare `python3`, so
the venv's `bin/` must be on `PATH` for the worker backends to import numpy.

### Tests updated, and why each was a real pin rather than a rubber stamp

| Test | Change |
| --- | --- |
| `test_database_first_ui_refactor_functional.py::test_dashboard_top_level_groups` | The pinned nav-group list — the single assertion that would catch an accidental group change. Updated to the new nine, with the reason. |
| `test_distribution_strategy_buttons_regression.py` | Asserted `roth_conversion` **has** a SECTION_REDIRECTS entry. Its stated intent is "roth_conversion keeps its own identity rather than being folded into a parent page"; a real nav step is a stronger form of that, so the assertion is inverted — it must now have **no** redirect, since one would fold it back into Optimize. |
| `test_strategy_workspace_module_gating.py` | `SECTION_GATES` loses the two sections that no longer exist. The `step_gate_map()` assertions for `roth_conversion`/`entity_charitable` are deliberately **kept**: the gate declaration is unchanged, it is simply read by `visibleSteps()` now instead of by a `strategySection()` call. |
| `strategy_section_redirects.test.mjs` | Two entries out of the Optimize redirect table, two new "lands directly on its own Taxes page" cases, autosave coverage for both, and the `pendingSectionDkey` leak test re-pointed at `allocation_assets` (it needed an id that still goes through `SECTION_REDIRECTS`). |
| `strategy_screen_rows_aggregate.test.mjs` | Optimize's union drops to `[2, 3]`; a new case asserts both promoted steps still return their own rows directly. |
| `strategy_section_lazy_body.test.mjs` | Optimize is six sections, and the first ungated one (HSA Drawdown) is what opens by default now. |
| `step_help_live_links.test.mjs` | Its reachability check was "navigation.js must carry a redirect for `roth_conversion`, since it is a hidden shell." Now the opposite: assert the STEPS entry is real and visible, and that no redirect exists. |
| `feature_gated_note_off_states.test.mjs` | Four new cases on `renderFamilyBusiness()`: both groups' rows survive with both modules off, it links back to the page the rows live on, `sourceStepForRow()` still answers `assets_special`, and `rawRowsForStep('family_business')` is exactly the two catalog-declared sections. |

## Scoped in vs. scoped out

**In** (everything the scope line names):
- Taxes and Family & Business nav groups; Housing promoted out of Spending.
- `SECTION_REDIRECTS` (two deletions), every `helpLink` target (three
  relabelled), `SUGGESTED_NEXT` (three new entries + the gating guard), step
  ordering and `group:` values in `STEPS`.
- The consequential edits those force: `AUTOSAVE_STEPS`,
  `STRATEGY_SCREEN_MEMBER_STEPS`, `renderStrategyOptimize()`'s section list,
  one new dispatch case, one new `rawRowsForStep` case, the shared-group
  extraction that keeps the Family & Business page from being a copy.

**Out** (found while working; documented, not done):
1. **HSA Drawdown and Harvesting stay on Optimize** even though both are
   Taxes-domain. See the judgment call above. Whoever picks this up should
   decide first whether Optimize survives as a screen at all once its tax
   sections leave — that is a screen redesign, not a nav move.
2. **Business Succession / S-Corp vs LLC rows stay on Work Income.** They are
   genuinely earned-income inputs (`Cashflow`/`s_corp`, `entity_type`) and
   moving them would change `income_work`'s row routing. The new page links
   to Work Income and says so.
3. **Special-Needs Planning has no plan-input surface at all** — it is a
   Family & Business catalog module with neither `dashboard_step` nor
   `csv_sections`. It appears on Plan Features and nowhere else. Not a W13
   defect; noted because the group's name now invites the question.
4. **Investments, Estate & Legacy and Risk & Resilience nav groups.** Three
   more catalog domains that the nav still folds into "Assets & Protection"
   and "Strategy". §4.2's table shows the mapping; the scope line names only
   two new groups, and splitting Assets & Protection is a bigger change than
   either of them.
5. **The `spending_dashboard` dual-registration bug** (a hidden step with a
   group makes a phantom nav group appear when it is the active step —
   navigation.js's own comment documents it). `ytd_transactions`,
   `lifestyle_spending`, `spending_travel` and `spending_travel_extras` share
   the shape inside the Spending run. All four redirect away before becoming
   `activeStep`, so none of them triggers it today, and W13 does not make it
   worse. Left alone.
6. **`renderFields()`'s "Some fields on this page feed reporting only" note**
   still keys on `assets_special` alone; the Family & Business page does not
   show it. Cosmetic, and adding the step id there is a one-line change
   whenever someone decides it belongs.

## Consequences for later work

- The switch surface (Plan Features, W4) and the left nav now agree on seven
  of the ten catalog domains. Items 1 and 4 above are what closes the rest.
- Anything that adds a Taxes-domain feature with a page of its own now has a
  nav group to put it in, which is what §4.3 said the left nav lacked.
