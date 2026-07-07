from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_new_frontend_modules_are_loaded_before_dashboard():
    html = read("frontend/index.html")
    order = [
        "js/api_client.js",
        "js/app_store.js",
        "js/navigation.js",
        "js/reports_ui.js",
        "js/planning_workbench_ui.js",
        "js/dashboard.js",
    ]
    script_positions = []
    for item in order:
        marker = f'<script src="{item}'
        script_positions.append(html.index(marker))
    assert script_positions == sorted(script_positions)


def test_navigation_behavior_is_feature_owned_with_dashboard_wrappers():
    nav = read("frontend/js/navigation.js")
    dashboard = read("frontend/js/dashboard.js")
    assert "window.RetirementNavigation" in nav
    assert "AUTOSAVE_STEPS" in nav
    assert "function setStep(id){return window.RetirementNavigation.setStep" in dashboard
    assert "function wireStepNavigation(){return window.RetirementNavigation.wireStepNavigation" in dashboard
    assert "function renderNav(){return window.RetirementNavigation.renderNav" in dashboard


def test_planning_workbench_case_store_moved_out_of_dashboard():
    workbench = read("frontend/js/planning_workbench_ui.js")
    dashboard = read("frontend/js/dashboard.js")
    assert "window.RetirementPlanningWorkbench" in workbench
    assert "retirement.planning_case_v1" in workbench
    assert "planning_case_v1" in workbench
    assert "function renderPlanningWorkbench(){return window.RetirementPlanningWorkbench.renderWorkbench" in dashboard
    assert "function planningWorkbenchBuildImpactHtml(){return window.RetirementPlanningWorkbench.renderBuildImpactContext" in dashboard


def test_reports_shell_rendering_moved_out_of_dashboard():
    reports = read("frontend/js/reports_ui.js")
    dashboard = read("frontend/js/dashboard.js")
    assert "window.RetirementReportsUI" in reports
    assert "function renderDetailedResults(){return window.RetirementReportsUI.renderDetailedResults" in dashboard
    assert "function renderDetailedResultsNav(){return window.RetirementReportsUI.renderDetailedResultsNav" in dashboard
    assert "Loading results index" not in dashboard
    assert "Retirement Plan Workbook" in reports


@pytest.mark.skip(reason="Phase A removed committed output/ artifacts; Phase B will update tests to generate fixtures instead")
def test_output_assets_stay_synced_for_new_modules():
    for name in ["navigation.js", "reports_ui.js", "planning_workbench_ui.js"]:
        assert read(f"frontend/js/{name}") == read(f"output/js/{name}")
    for rel in ["frontend/index.html", "output/index.html"]:
        text = read(rel)
        assert "js/navigation.js" in text
        assert "js/reports_ui.js" in text
        assert "js/planning_workbench_ui.js" in text
