"""Ticket 323 / Phase 1: the Strategy section becomes three screens.

Optimize / Stress Test / Scenarios replace the old Strategy + Stress Tests nav
groups. The eleven destinations that used to be reachable only through an
in-page launcher grid become collapsible sections on those three screens.

This file is deliberately narrow. It was originally a broader source-text-grep
file (test_strategy_workspace_screens.py); everything that could genuinely be
verified by *executing* the real code -- STEPS entries as real objects, the
three renderers' output, stepGatedByOptionalModule's actual behavior, the
deleted renderers being genuinely absent from the loaded sandbox -- moved to
tests/frontend/strategy_section_lazy_body.test.mjs, which runs the real
dashboard.js/dashboard_decomp_*.js source through the Node vm sandbox (see
tests/frontend/load_dashboard.mjs). That is strictly stronger than a substring
match: it would catch, for example, STEPS becoming a lookup table that still
happens to contain the string `group: "Strategy"` somewhere irrelevant.

What is left here is genuinely structural and cannot be expressed by running
the code in a sandbox, because it IS about which file a symbol lives in or
whether a file references another file by path -- there is no "behavior" to
execute:

  * the new module exists under the load-bearing `dashboard_decomp_` prefix
    and is <script>-loaded by index.html (a loader/build-order fact, not a
    runtime one);
  * the three screen renderers are defined in that module and NOT in
    dashboard.js (a "this symbol lives outside file X" placement check --
    tests._decomp_dashboard.dashboard_js_text() concatenates every module
    together specifically so per-file placement cannot be asked of it, so
    this one test reads dashboard.js directly and is listed in
    tests/test_dashboard_decomp_test_no_direct_reads_guard.py's ALLOWED);
  * renderMain's activeStep dispatch table contains a literal branch for each
    new step id calling the right renderer -- this is dashboard.js's own
    routing wiring (an if/else chain keyed by string literals), which the
    Node sandbox would need extensive additional DOM stubbing to execute
    safely end-to-end; asserting the branch exists in source is the
    proportionate check for a bootstrap dispatch table, the same shape as the
    module-bridge regression test this repo already runs.

Per tests/test_freeze_frontend_source_grep.py's docstring, "structural
assertions -- 'this file exists', 'this module is under N lines' -- are
legitimately text-based and are not what this freezes." This file is such a
case and is listed in tests/fixtures/frontend_source_grep_baseline.json for
that reason.
"""
from __future__ import annotations

from pathlib import Path

from tests._decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]
JS_DIR = ROOT / "frontend" / "js"
DASHBOARD_JS = JS_DIR / "dashboard.js"
WORKSPACE_JS = JS_DIR / "dashboard_decomp_strategy_workspace.js"
INDEX_HTML = ROOT / "frontend" / "index.html"

NEW_STEPS = ["strategy_optimize", "strategy_stress", "strategy_scenarios"]


def test_new_module_uses_the_decomp_prefix_and_is_loaded_by_the_page():
    # The dashboard_decomp_ prefix is load-bearing: tests/_decomp_dashboard.py
    # globs it to assemble the "full dashboard source" every content-assertion
    # test reads.
    assert WORKSPACE_JS.is_file()
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "js/dashboard_decomp_strategy_workspace.js" in html


def test_the_three_screen_renderers_live_outside_dashboard_js():
    # Placement check: dashboard_js_text() concatenates every module, so it
    # cannot express "not in dashboard.js" -- a direct read is the only way
    # to ask this question. See tests/test_dashboard_decomp_test_no_direct_
    # reads_guard.py's ALLOWED entry for this file.
    dash = DASHBOARD_JS.read_text(encoding="utf-8")
    mod = WORKSPACE_JS.read_text(encoding="utf-8")
    for name in (
        "strategySection",
        "renderStrategyOptimize",
        "renderStrategyStress",
        "renderStrategyScenarios",
    ):
        assert f"export function {name}(" in mod
        assert f"function {name}(" not in dash


def test_render_main_routes_the_three_new_steps():
    js = dashboard_js_text()
    for step_id, fn in zip(
        NEW_STEPS,
        ["renderStrategyOptimize", "renderStrategyStress", "renderStrategyScenarios"],
    ):
        assert f'activeStep === "{step_id}"' in js
        assert f"{fn}()" in js
