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
# (docs/superpowers/plans/2026-08-06-dashboard-js-ast-module-conversion.md)
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
# extraction (docs/superpowers/plans/2026-08-06-dashboard-js-domain-module-split-SCOPE.md):
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
# Set at the post-extraction measurement with no headroom.
DASHBOARD_JS_MAX_LINES = 15_308

# Total frontend JS is allowed to grow -- extraction moves lines out of
# dashboard.js into new modules, which should not be penalised. This ceiling
# only catches wholesale duplication.
TOTAL_JS_MAX_LINES = 32_000


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
