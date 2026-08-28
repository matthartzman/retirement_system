from pathlib import Path

from _decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]
from tests._decomp_dashboard import dashboard_js_text
DASHBOARD_JS = ROOT / "frontend" / "js" / "dashboard.js"
DASHBOARD_CSS = ROOT / "frontend" / "css" / "dashboard.css"
CHANGELOG = ROOT / "documentation" / "GOLDEN_MASTER_CHANGELOG.md"


def test_scenarios_page_has_templates_saved_sets_and_diffs():
    js = dashboard_js_text()

    assert "SCENARIO_TEMPLATES" in js
    assert "Conservative markets" in js
    assert "Spending pressure" in js
    assert "Retire later bridge" in js
    assert "Home-sale liquidity" in js
    assert "function renderScenarioManagementPanel" in js
    assert "Scenario templates" in js
    assert "Saved named scenario sets" in js
    assert "Current scenario overrides" in js
    assert "scenarioDiffTableHtml" in js
    assert "scenario_set_v1" in js
    assert "retirement.scenario_sets.v1" in js


def test_scenario_templates_stage_existing_fields_without_build_logic_changes():
    js = dashboard_js_text()

    assert "applyScenarioTemplate" in js
    assert "applySavedScenarioSet" in js
    assert "editValue(r.row_index" in js
    assert "saveCurrentScenarioSet" in js
    assert "include_low_return" in js
    assert "include_high_inflation" in js
    assert "spend_multiplier" in js
    assert "home_sale_year" in js


def test_scenario_management_is_styled_and_documented():
    css = DASHBOARD_CSS.read_text(encoding="utf-8")
    changelog = CHANGELOG.read_text(encoding="utf-8")

    assert ".scenario-management" in css
    assert ".scenario-template-grid" in css
    assert ".scenario-set-card" in css
    assert ".scenario-diff-table" in css
    assert "scenario_set_v1" in changelog
