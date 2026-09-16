"""Ticket 284 (superseded in part by ticket 323): Roth Conversion and Asset
Allocation were plain navigation buttons on the Distribution Strategy page,
not embedded <details> sections.

Ticket 323 deleted both renderDistributionStrategy() (a one-line wrapper
around renderPlanningLevers()) and the Planning Levers quick-nav hub that
held the "decide card" buttons this file used to assert on -- every one of
those destinations now has a real, permanent nav entry of its own instead
(one of the three Strategy screens), so the hub was exactly the redundancy
the redesign removes. The two tests that asserted directly on that deleted
code are gone with it.

What ticket 284 actually still protects -- that allocation_policy stays
reachable, nested under allocation_assets, without an entry of its own --
remains true and is still asserted below, now against
dashboard_decomp_strategy_workspace.js's Asset Allocation section, which is
where that nesting now lives.
"""

import re

from _decomp_dashboard import dashboard_js_text

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _planning_levers_body(js):
    m = re.search(
        r"export function renderPlanningLevers\(\) \{\n(.*?)\n\}\n\n",
        js,
        re.S,
    )
    assert m, "renderPlanningLevers body not found"
    return m.group(1)


def test_render_distribution_strategy_is_gone():
    js = dashboard_js_text()
    assert "function renderDistributionStrategy" not in js
    assert 'activeStep === "distribution_strategy"' not in js


def test_planning_levers_no_longer_has_a_decide_card():
    # The quick-nav hub (and leverNavButton(), its helper) that used to sit
    # here is fully removed -- see
    # test_planning_levers_layout_functional.py::test_planning_levers_no_longer_carries_its_own_quick_nav_hub
    # and test_strategy_workspace_module_gating.py for the module-gating
    # contract that moved with it onto the new screens.
    js = dashboard_js_text()
    fn = _planning_levers_body(js)
    assert "function leverNavButton" not in fn
    assert "= leverNavButton(" not in fn
    assert "function renderPlanningLevers(embedded)" not in js
    assert "embedded ?" not in fn


def test_navigation_no_longer_redirects_roth_or_allocation_off_their_steps():
    navigation = (ROOT / "frontend" / "js" / "navigation.js").read_text(
        encoding="utf-8"
    )
    # #323: distribution_strategy is retired as a destination, so nothing may
    # redirect TO it any more. What this test has always protected is that
    # roth_conversion and allocation_assets keep their own identity rather than
    # being folded into a parent page -- they now resolve to their own named
    # sections of Strategy -> Optimize, asserted behaviorally in
    # tests/frontend/strategy_section_redirects.test.mjs.
    assert "'distribution_strategy'" not in navigation
    assert "roth_conversion:{step:'strategy_optimize',section:'roth_conversion'}" in navigation
    assert "allocation_assets:{step:'strategy_optimize',section:'asset_allocation'}" in navigation
    # allocation_policy still has no section of its own; it rides along with
    # asset_allocation, which is where its fields render.
    assert "allocation_policy:{step:'strategy_optimize',section:'asset_allocation'}" in navigation


def test_roth_conversion_and_allocation_assets_activestep_branches_still_live():
    js = dashboard_js_text()
    assert 'else if (activeStep === "roth_conversion")' in js
    assert 'content += analysisFrame(renderRothConversion(), "strategy");' in js
    assert 'else if (activeStep === "allocation_assets")' in js


def test_allocation_policy_re_homed_under_allocation_assets_not_orphaned():
    js = dashboard_js_text()
    m = re.search(
        r'else if \(activeStep === "allocation_assets"\)\s*\n\s*content \+=(.*?);\n',
        js,
        re.S,
    )
    assert m, "allocation_assets branch not found"
    branch = m.group(1)
    assert "renderAllocationRecommendation" in branch
    assert "renderAllocationPolicy()" in branch
    assert "Allocation policy settings" in branch

    # No standalone nav entry / seventh decide button for allocation_policy.
    levers_fn = _planning_levers_body(js)
    assert '"allocation_policy"' not in levers_fn
