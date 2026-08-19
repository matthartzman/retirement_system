"""Ticket 284: Roth Conversion and Asset Allocation are plain navigation
buttons on the Distribution Strategy page, not embedded <details> sections.

Guards the three things that regress silently if this is undone:
  - the decide card renders data-step-id nav buttons for roth_conversion and
    allocation_assets (not inline embeds)
  - the decide-embed markup is gone from renderDistributionStrategy
  - allocation_policy stays reachable, nested under allocation_assets, without
    getting its own nav entry / seventh button
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


def test_distribution_strategy_is_lever_hub_with_no_embeds():
    js = dashboard_js_text()
    m = re.search(
        r"export function renderDistributionStrategy\(\) \{\n(.*?)\n\}\n",
        js,
        re.S,
    )
    assert m, "renderDistributionStrategy body not found"
    body = m.group(1)

    assert "decide-embed" not in body
    assert "renderPlanningLevers()" in body
    assert "renderRothConversion(" not in body
    assert "renderAllocationRecommendation(" not in body


def test_decide_card_has_six_buttons_including_roth_and_allocation():
    js = dashboard_js_text()
    fn = _planning_levers_body(js)

    assert 'leverNavButton("roth_conversion", "Roth conversion")' in fn
    assert (
        'leverNavButton("allocation_assets", "Asset allocation & location")' in fn
    )
    assert 'leverNavButton("spending_core", "Withdrawal order")' in fn
    assert 'leverNavButton("income_retirement", "Social Security")' in fn
    assert 'leverNavButton("entity_charitable", "Charitable giving")' in fn
    assert 'leverNavButton("heloc_strategy", "HELOC strategy")' in fn

    decide_button_calls = re.findall(
        r'leverNavButton\("(roth_conversion|allocation_assets|spending_core|'
        r'income_retirement|entity_charitable|heloc_strategy)"',
        fn,
    )
    assert len(decide_button_calls) == 6
    assert "function renderPlanningLevers(embedded)" not in js
    assert "embedded ?" not in fn


def test_navigation_no_longer_redirects_roth_or_allocation_off_their_steps():
    navigation = (ROOT / "frontend" / "js" / "navigation.js").read_text(
        encoding="utf-8"
    )
    assert "roth_conversion:'distribution_strategy'" not in navigation
    assert "allocation_assets:'distribution_strategy'" not in navigation
    # Untouched: allocation_policy has no button of its own and still redirects.
    assert "allocation_policy:'distribution_strategy'" in navigation


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
