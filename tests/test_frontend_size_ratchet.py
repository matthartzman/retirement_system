"""dashboard.js must not grow.

System review 2026-08-04, architect finding `frontend-single-global-namespace`,
recommended option 3: "The size ratchet is the highest value-per-hour action
available here: the six decomp files prove extraction happens, but without a
constraint the monolith reabsorbs the growth."

This is a ratchet, not a budget. The ceiling only ever moves DOWN, and it moves
by editing the number below after real extraction work. A change that adds
lines to dashboard.js must take lines out of it somewhere else, or move the new
code into its own module -- which is the point.

Why a line ceiling rather than "no new code in this file": a hard freeze would
block ordinary bug fixes in a 19k-line file that still owns most of the UI. The
ratchet allows churn while making growth a deliberate, visible decision.

When you legitimately extract code, LOWER the ceiling in the same commit. That
is the only supported way to change it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS_DIR = ROOT / "frontend" / "js"

# Ceiling for the monolith. Ratchet DOWN only; never raise to make a diff pass.
# 2026-08-05: lowered from 19,661 to 19,188 -- Wave 6.4's "holdings" leaf
# extraction (dashboard_decomp_holdings.js) moved the Plan Holdings lot
# table and its CRUD/CSV-import/pricing-tester helpers out of dashboard.js.
# 2026-08-06: lowered from 19,188 to 19,167 -- pre-conversion dead-code sweep
# (documentation/archive/superpowers/plans/2026-08-06-dashboard-js-ast-module-conversion.md)
# removed three top-level bindings with zero references anywhere in the repo:
# APP_UNAVAILABLE_MESSAGE, BUDGET_SECTION_DEFS, planFileHandles.
# 2026-08-06: RAISED from 19,167 to 19,403 -- the one deliberate exception this
# ratchet's own docstring anticipates ("a change that adds lines... must take
# lines out of it somewhere else, or move the new code into its own module").
# Converting dashboard.js to a real ES module (same plan as above) requires a
# generated window-bridge block (tools/js_codemod/convert_dashboard.mjs) that
# MUST live inside dashboard.js itself: it references renderMain, activeStep,
# and 758 other bare top-level bindings that are module-private and invisible
# to any other file the moment this module conversion lands, so the bridge
# cannot be extracted elsewhere. This is not organic feature growth -- it's
# tool-generated, verified by test_dashboard_js_module_bridge_regression.py,
# and is the explicit-interface list the "frontend-single-global-namespace"
# finding this ratchet exists for was asking for in the first place.
# 2026-08-06: lowered from 19,403 to 15,411 -- domain-module-split shared-core
# extraction (documentation/archive/superpowers/plans/2026-08-06-dashboard-js-domain-module-split-SCOPE.md):
# moved the 172 fan-in>=3 hub functions (row-model DSL + app-shell) into
# frontend/js/dashboard_decomp_row_model.js. renderMain/showStepHelp stayed
# (other leaf modules reassign them as a monkey-patch chain).
# 2026-08-06: raised from 15,305 to 15,308 -- census.mjs's inline-HTML-
# event-handler-assignment detection (a real gap: onchange="ytdCategoryFilter=
# this.value" etc. execute in browser global scope, not dashboard.js's module
# scope, once type="module" applies -- see census.mjs's v4 header comment)
# found 3 more variables needing get+set window accessors
# (ytdCategoryFilter, ytdTxSearch, ytdAccountFilter), fixing 3 real silent-
# failure bugs (those filter/search inputs updating an accidental implicit
# global instead of the real state). 3 new generated lines, no slack added.
# 2026-08-10: lowered from 15,308 -- first domain-cluster extraction
# (documentation/archive/superpowers/specs/2026-08-10-dashboard-js-split-codemod-design.md):
# tools/js_codemod/extract_module.mjs moved the 24-function assets cluster
# (liabilities, note receivables, 529s, other-asset items) plus the 4 constant
# tables only it reads into frontend/js/dashboard_decomp_assets_other.js.
# Set at the post-extraction measurement with no headroom.
# 2026-08-11: lowered from 14,822 -- extracted 39 declaration(s) into
# dashboard_decomp_spending_taxonomy.js via
# tools/js_codemod/extract_module.mjs. Measured after regenerating the
# census and bridge, so it includes the bridge shrinking as those names left
# its Object.assign block.
# 2026-08-12: lowered from 14,021 -- extracted 40 declaration(s) into
# dashboard_decomp_housing_scenarios.js via
# tools/js_codemod/extract_module.mjs. Measured after regenerating the
# census and bridge, so it includes the bridge shrinking as those names left
# its Object.assign block.
# 2026-08-12: lowered from 13,060 -- extracted 24 declaration(s) into
# dashboard_decomp_build_history.js via tools/js_codemod/extract_module.mjs.
# Measured after regenerating the census and bridge, so it includes the
# bridge shrinking as those names left its Object.assign block.
#
# 2026-08-12: lowered again from 12,304 -- merged the dead-code sweep
# (claude/elastic-chaum-1e4a9c), which deleted unreachable top-level functions
# from the post-extraction tree (see
# tests/test_dashboard_dead_code_sweep_regression.py). The branch's own note
# claimed 12,202, measured against a tree that predated the build_history
# extraction; the two changes compound, so neither side's number survives the
# merge. Extraction moves declarations OUT to new modules, the sweep removes
# ones that were never reachable from anywhere. Re-measured on the merged tree
# after regenerating census + bridge, in that order (convert_dashboard.mjs
# reads census_report.json, so a stale census silently regenerates a stale
# bridge).
# 2026-08-17: lowered from 11,447 -- extracted 14 declaration(s) into
# dashboard_decomp_page_recommendations.js via
# tools/js_codemod/extract_module.mjs. Measured after regenerating the
# census and bridge, so it includes the bridge shrinking as those names left
# its Object.assign block.
# 2026-08-17: lowered from 10,967 -- extracted 11 declaration(s) into
# dashboard_decomp_income_streams.js via
# tools/js_codemod/extract_module.mjs. Measured after regenerating the
# census and bridge, so it includes the bridge shrinking as those names left
# its Object.assign block.
# 2026-08-17: lowered from 10,778 -- extracted 9 declaration(s) into
# dashboard_decomp_large_discretionary.js via
# tools/js_codemod/extract_module.mjs. Measured after regenerating the
# census and bridge, so it includes the bridge shrinking as those names left
# its Object.assign block.
# 2026-08-17: lowered from 10,659 -- extracted 8 declaration(s) into
# dashboard_decomp_death_benefits.js via
# tools/js_codemod/extract_module.mjs. Measured after regenerating the
# census and bridge, so it includes the bridge shrinking as those names left
# its Object.assign block.
# 2026-08-17: lowered from 10,588 -- extracted 8 declaration(s) into
# dashboard_decomp_mc_stress_options.js via
# tools/js_codemod/extract_module.mjs. Measured after regenerating the
# census and bridge, so it includes the bridge shrinking as those names left
# its Object.assign block.
# 2026-08-17: lowered from 10,454 -- extracted 31 declaration(s) into
# dashboard_decomp_checklist_closeout.js via
# tools/js_codemod/extract_module.mjs. Measured after regenerating the
# census and bridge, so it includes the bridge shrinking as those names left
# its Object.assign block.
# 2026-08-17: lowered from 9,276 -- extracted 48 declaration(s) into
# dashboard_decomp_allocation_optimizer.js via
# tools/js_codemod/extract_module.mjs. Measured after regenerating the
# census and bridge, so it includes the bridge shrinking as those names left
# its Object.assign block.
# 2026-08-17: lowered from 8,373 -- extracted 65 declaration(s) into
# dashboard_decomp_ytd_and_plan_folder_io.js via
# tools/js_codemod/extract_module.mjs. Measured after regenerating the
# census and bridge, so it includes the bridge shrinking as those names left
# its Object.assign block.
# 2026-08-18: Ticket 285 fix round 3 -- fixing the regression Task 2 caused
# by adding a ~66-line focus capture/restore block inline inside renderMain()
# instead of as its own module. Extracted the two helpers
# (captureMainPaneFocus/restoreMainPaneFocus) into
# frontend/js/dashboard_decomp_focus_restore.js via
# tools/js_codemod/extract_module.mjs; renderMain() itself stays in
# dashboard.js (it is reassigned by other leaf modules as a monkey-patch
# chain) and now just calls the two extracted functions, capture before the
# innerHTML write and restore after, synchronously as before. Task 2 had
# raised the file to 7,545 lines against the 7,481 ceiling; this extraction
# only recovers to 7,504 (the extracted block was ~66 lines but the call
# sites plus the regenerated window-bridge Object.assign entries add some
# back), which is still above the prior 7,481 ceiling, so the ceiling here
# is set to the new measured size with no slack rather than restored to
# 7,481.
# 2026-09-09: lowered from 7,504 -- extracted 7 declaration(s) into
# dashboard_decomp_field_choice_help.js via
# tools/js_codemod/extract_module.mjs. Measured after regenerating the
# census and bridge, so it includes the bridge shrinking as those names left
# its Object.assign block.
# 2026-09-16: lowered from 7,320 to 7,293 -- ticket 323's Strategy redesign.
# New code (the three Strategy screens and their lazy-section primitive)
# landed entirely in a new module, dashboard_decomp_strategy_workspace.js,
# not here. dashboard.js itself only lost lines: three renderMain branches
# (distribution_strategy, special_strategies, state_residency) collapsed to
# three (the new screens), and renderStateResidency()/
# renderSpecialStrategies() were deleted outright. Measured after every
# deletion in the ticket landed, including the ones in sibling
# dashboard_decomp_*.js files that don't move this number but do free the
# module-bridge lines that made room for it.
# 2026-09-21 (W4, #330 P3): lowered from 7,293 to 7,246 -- renderOptionalFunctions()
# extracted to frontend/js/dashboard_decomp_plan_features.js. Real extraction,
# so the ceiling moves DOWN in the same commit, exactly as this file's
# docstring requires. W4 then grows that page (domain grouping, kind filter
# chips, demand hints, the off-but-holds-data indicator, the env-override
# disclosure) inside its own module, where it does not press on this ceiling.
# 2026-09-22 (W9, #329 P4 + #330): lowered from 7,246 to 7,201 --
# hsaWithdrawalPolicyBlock/taxLossHarvestingBlock/gainHarvestBlock/
# withdrawalMiscBlock extracted to dashboard_decomp_strategy_workspace.js so
# Optimize's new sections could reuse them without duplicating the filters.
# dashboard.js also grew (a new activeStep dispatch case for heloc_strategy,
# a moved/expanded STEPS entry, a generalized flag-gate check), but the
# extraction outweighed the growth -- measured to the new total with no
# slack, exactly as this ceiling's own contract requires on a real
# extraction.
DASHBOARD_JS_MAX_LINES = 7_201

# Total frontend JS is allowed to grow -- extraction moves lines out of
# dashboard.js into new modules, which should not be penalised. This ceiling
# only catches wholesale duplication.
# 2026-09-16: raised from 32,000 to 32,730, the measured size with no slack.
# The housing-optimizer refinement (docs/superpowers/specs/2026-09-16-housing-
# optimizer-refinement-design.md) added frontend/js/dashboard_decomp_housing_
# optimizer.js. Checked against what this ceiling is actually for -- wholesale
# duplication -- rather than against the number: dashboard.js is byte-for-byte
# unchanged at 7,320, and the panel's former host shrank by 641 lines, so
# nothing was duplicated out of the monolith. The net +1,379 is new behaviour
# the old ~635-line panel did not have: 2-5 anchors per move, the nine §8
# validation rules mirrored from the server, ~50 context-help entries, input
# persistence, and the per-recommendation results table. Unlike
# DASHBOARD_JS_MAX_LINES above, this constant's own contract is that it MAY
# rise for genuine new code; it is set to the measured size so it keeps
# constraining the next change.
# 2026-09-16: raised from 32,730 to 32,792. dashboard_decomp_housing_optimizer.js
# gained a shared progress-popup overlay for the panel's two async calls
# (preview shortlist, run optimization) and a snapshot/restore fix for a bug
# where adding or removing an anchor wiped out the values already entered for
# the other anchors. Neither is lines moved from elsewhere -- both are new,
# so the ceiling is raised to the measured size with no slack, same as before.
# 2026-09-16: raised from 32,792 to 33,076 -- merging main (the housing-
# optimizer raise above) into the ticket-323 Strategy redesign branch, whose
# own new module (dashboard_decomp_strategy_workspace.js, the three Strategy
# screens' lazy-section primitive) had never needed to touch this ceiling on
# its own. Two independently-sufficient ceilings, combined by a merge neither
# side's diff alone could see coming; raised to the genuinely measured total
# of both real, non-duplicate additions.
# 2026-09-17: raised from 33,076 to 33,217 -- merging the housing-financing-
# and-zip-ux branch (docs/superpowers/specs/2026-09-16-housing-financing-and-
# zip-ux-design.md) into main, which by then already carried the ticket-323
# Strategy redesign's own raise to 33,076. dashboard_decomp_housing_optimizer.js
# gained a Purchase assumptions section (down payment %/mortgage rate % inputs,
# help entries) and rent/buy-specific results rendering; dashboard_decomp_
# housing_scenarios.js gained ZIP-first location entry (resolveHousingStepZip,
# a read-only City/State display, auto-filled Area Type/Population). Neither
# branch's own diff could see the other's prior raise; raised here to the
# genuinely measured total of both real, non-duplicate additions.
# 2026-09-17: raised from 33,217 to 33,237 on a separate branch -- relocated
# the housing optimizer to Strategy -> Optimize (a new tab entry in
# dashboard_decomp_strategy_workspace.js, plus its own removal from
# dashboard_decomp_housing_scenarios.js's Scenario Change Sets, a net add
# since the new tab's wrapping/help text is more than what was removed),
# added the "Apartment (rent only)" property type option and its
# validation-rule/help-copy additions in dashboard_decomp_housing_optimizer.js,
# and the 1-5 (was 2-5) anchor range's message-text updates. All new
# behaviour, not lines moved from elsewhere.
# 2026-09-17: raised from 33,217 to 33,265 -- ticket-326 per-popup average
# run-time (dashboard_decomp_build_lifecycle.js gained history storage/lookup
# helpers keyed by popup id, replacing "Working…"/percent text below the bar
# with "average run-time over the last N runs" once 2+ runs are recorded).
# dashboard.js is unchanged (still 7,293); the new lines are the history
# helpers plus a popupId argument threaded through the existing setBuildOverlay
# call sites, none of it moved from elsewhere, so raised to the measured size.
# 2026-09-17: merging the two branches above (ticket-326's 33,265, PR #124,
# and the housing-optimize-nav-and-anchors branch's 33,237, each independently
# sufficient, neither diff able to see the other's prior raise) plus that
# second branch's own later Planning Workbench Strategy Integration work
# (a new consolidated strategy_workbench screen composed mostly from
# existing exports, plus a net cleanup that deleted more duplicate/dead
# code -- old renderWorkbench(), renderWorkbenchLeverEditorHtml(),
# renderWorkbenchStressHtml(), several orphaned wrapper functions, and two
# unreachable renderMain() branches -- than the new screen added, and a
# final-review fix pass for three plan-independence gates plus stale copy)
# -- raised here to the genuinely measured total of all real, non-duplicate
# additions across both branches.
# 2026-09-17 (housing-screen-fixes): the Housing screen's inconsistency/gap-
# year/ZIP-input fixes plus an inline HELOC-enabled toggle on Optimize are
# real new logic, not duplication -- raised to the measured total.
# 2026-09-21 (8291678, Build History schema versioning + one-click cache
# reset): 48 new lines across admin.js, dashboard.js and
# dashboard_decomp_row_model.js for the Clear-cache button and its
# reporting of which cache folders were cleared vs. still locked by the
# running window -- real new behavior, not duplication -- raised to the
# measured total. The ceiling should have moved with that commit and did
# not; caught only because a later, unrelated PR's CI ran against main.
# 2026-09-21 (W5, #330 §3.4 dependency declarations): raised from 33,311 to
# 33,351 -- the reverse-direction off-impact warning on an optional module's
# switch ("Turning Monte Carlo off also removes the success-probability
# headline from Executive Summary and the fan chart from Charts"). 35 lines in
# dashboard_decomp_row_model.js (the taxonomy payload's module-private state
# plus moduleOffImpactWarning(), which builds the sentence) and 5 in
# dashboard.js's renderOptionalFunctions(). New behavior, not duplication:
# nothing rendered this before, and the helper was put in row_model
# specifically to keep DASHBOARD_JS_MAX_LINES intact -- dashboard.js had 6
# lines of headroom and now has 1. Raised to the measured total with no slack,
# per this ceiling's own contract.
# 2026-09-21 (W4, #330 P3): raised from 33,351 to 33,604 -- the Plan Features
# page (frontend/js/dashboard_decomp_plan_features.js). renderOptionalFunctions()
# moved out of dashboard.js (a wash: DASHBOARD_JS_MAX_LINES drops by the same
# 45 lines, above), and the rest is the page #330 P3 asks for and that did not
# exist before: domain grouping with collapsible groups, kind filter chips
# derived from CATALOG.kind, plain-language demand hints, the "off but still
# holds N entries" indicator (§5.4), and Q7's read-only env-override
# disclosure. New behavior, not duplication, so the ceiling rises to the
# measured total with no slack, per this constant's own contract.
# 2026-09-22 (W9, #329 P4 + #330): raised from 33,604 to 33,732 -- Optimize
# gained four new sections (HSA Drawdown, Withdrawal Sequencing, Social
# Security, Harvesting) per #329 §3.3's UI list, HELOC moved to its own
# Assets & Protection nav step (a new STEPS entry, a new activeStep dispatch
# case, and the rowsForStep() HELOC gate generalized to read moduleGates.
# flag_gates like strategySectionGatedNote() already does), and
# navigation.js/AUTOSAVE_STEPS/SECTION_REDIRECTS picked up HELOC's new
# destination. hsaWithdrawalPolicyBlock/taxLossHarvestingBlock/
# gainHarvestBlock/withdrawalMiscBlock moved out of dashboard.js in the same
# commit (DASHBOARD_JS_MAX_LINES stays flat, below) -- this rise is genuine
# new behavior (new panels, new nav step, a generalized gate check), not
# duplication, per this constant's own contract.
# 2026-09-22 (W9, #329 P4 + #330 §5.3): raised from 33,732 to 33,816 --
# dashboard_decomp_plan_features.js gained the plan-flag link rows W6's notes
# assigned to W9 (HELOC/Hybrid LTC/DAF/QCD now findable on Plan Features, as
# a link rather than a toggle -- §5.1's "three surfaces, one registry").
# Genuine new behavior, not duplication, per this constant's own contract.
# 2026-09-22 (W10a, #329 P5 / §4.5 path 1): raised from 33,816 to 33,992 --
# dashboard_decomp_allocation_optimizer.js gained the Roth optimizer's result
# panel, which is what §1.3's "Input form... no result shown" describes as the
# deepest asymmetry in the system: the candidate table existed only on workbook
# 11. Roth Conversion. Genuine new behavior (a renderer, its three empty-state
# answers, and the /api/summary read that makes it survive a page reload), not
# duplication, per this constant's own contract. dashboard.js is untouched.
# (33,992 -> 33,997 in the same workstream: loadAll() clears the panel's
# cached /api/summary read on a plan switch, beside the resetAllocationPreview()
# call that is there for the same reason one plan over.)
TOTAL_JS_MAX_LINES = 33_997


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_dashboard_js_does_not_grow():
    path = JS_DIR / "dashboard.js"
    actual = _line_count(path)
    assert actual <= DASHBOARD_JS_MAX_LINES, (
        f"frontend/js/dashboard.js is {actual:,} lines, over the "
        f"{DASHBOARD_JS_MAX_LINES:,}-line ratchet by {actual - DASHBOARD_JS_MAX_LINES:,}.\n"
        "This file is a single global namespace with load-order contracts; it is "
        "meant to shrink, not grow. Either extract the new code into its own "
        "module under frontend/js/, or remove an equivalent number of lines here.\n"
        "Do NOT raise DASHBOARD_JS_MAX_LINES to make this pass -- that is the "
        "drift this test exists to prevent."
    )


def test_ratchet_is_not_slack():
    """The ceiling must stay close to reality, or it stops constraining anything.

    A ceiling far above the real size silently permits the growth it was added
    to prevent. If genuine extraction drops the file well below the ceiling,
    lower the ceiling in that same commit.
    """
    actual = _line_count(JS_DIR / "dashboard.js")
    slack = DASHBOARD_JS_MAX_LINES - actual
    assert slack <= 500, (
        f"dashboard.js is {actual:,} lines but the ratchet is set at "
        f"{DASHBOARD_JS_MAX_LINES:,} -- {slack:,} lines of unused headroom. "
        "Lower DASHBOARD_JS_MAX_LINES to the current size so the ratchet keeps "
        "constraining growth."
    )


def test_total_frontend_js_has_a_ceiling():
    total = sum(_line_count(p) for p in JS_DIR.glob("*.js"))
    assert total <= TOTAL_JS_MAX_LINES, (
        f"frontend/js totals {total:,} lines, over {TOTAL_JS_MAX_LINES:,}. "
        "Extraction should MOVE lines out of dashboard.js, not duplicate them."
    )


@pytest.mark.parametrize("name", ["dashboard.js"])
def test_ratchet_target_exists(name):
    assert (JS_DIR / name).is_file(), (
        f"frontend/js/{name} not found -- if it was renamed or split, update "
        "this ratchet to point at whatever now holds the bulk of the UI."
    )
