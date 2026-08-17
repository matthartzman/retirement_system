from pathlib import Path
import pytest
from tests._decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_new_frontend_modules_are_loaded_before_dashboard():
    # Wave 6.4 ("leaves inward" ES-module migration) converted these five to
    # type="module" -- a deferred script, which always finishes executing
    # before any user interaction or promise-driven callback can run. That
    # guarantee only holds because NONE of these five are called from
    # dashboard.js's own synchronous top-level boot chain (verified: their
    # only callers are wrapper functions invoked later, from rendering/event
    # handlers) -- dashboard_decomp_local_backups.js is the one file in this
    # codebase that IS called from that boot chain (checkAppStatus(true).then(...)
    # calls refreshLocalBackupStatus()) and deliberately stayed a classic
    # script for exactly that reason; see
    # test_dashboard_startup_race_and_script_order.py's docstring for the
    # real 2026-07-22 outage that guard protects against.
    #
    # dashboard.js itself became type="module" too (docs/superpowers/plans/
    # 2026-08-06-dashboard-js-ast-module-conversion.md) -- module scripts run
    # in document order relative to each other, so dashboard_pos below is no
    # longer "the classic-script boundary these five must beat"; it's kept
    # only so this test still fails loudly if dashboard.js's tag is ever
    # removed or radically changed, rather than silently no-op'ing.
    html = read("frontend/index.html")
    order = [
        "js/api_client.js",
        "js/app_store.js",
        "js/navigation.js",
        "js/reports_ui.js",
        "js/planning_workbench_ui.js",
        "js/dashboard.js",
    ]
    dashboard_module_marker = '<script type="module" src="js/dashboard.js'
    dashboard_classic_marker = '<script src="js/dashboard.js'
    assert dashboard_module_marker in html or dashboard_classic_marker in html, (
        "dashboard.js's <script> tag not found in frontend/index.html"
    )
    dashboard_pos = html.index(
        dashboard_module_marker if dashboard_module_marker in html else dashboard_classic_marker
    )
    for item in order[:-1]:
        module_marker = f'<script type="module" src="{item}'
        classic_marker = f'<script src="{item}'
        if module_marker in html:
            continue  # deferred module: always finishes before dashboard.js's callbacks can call it
        assert classic_marker in html, f"{item} is neither a classic <script src> tag nor a type=\"module\" one"
        assert html.index(classic_marker) < dashboard_pos, (
            f"{item} loads as a classic script but after dashboard.js -- "
            "either move it earlier or convert it to type=\"module\"."
        )


def test_navigation_behavior_is_feature_owned_with_dashboard_wrappers():
    nav = read("frontend/js/navigation.js")
    dashboard = dashboard_js_text()
    assert "window.RetirementNavigation" in nav
    assert "AUTOSAVE_STEPS" in nav
    assert 'function setStep(id) {\n  return window.RetirementNavigation.setStep' in dashboard
    assert 'function wireStepNavigation() {\n  return window.RetirementNavigation.wireStepNavigation' in dashboard
    assert 'function renderNav() {\n  return window.RetirementNavigation.renderNav' in dashboard


def test_planning_workbench_case_store_moved_out_of_dashboard():
    workbench = read("frontend/js/planning_workbench_ui.js")
    dashboard = dashboard_js_text()
    assert "window.RetirementPlanningWorkbench" in workbench
    assert "retirement.planning_case_v1" in workbench
    assert "planning_case_v1" in workbench
    assert 'function renderPlanningWorkbench() {\n  return window.RetirementPlanningWorkbench.renderWorkbench' in dashboard
    assert 'function planningWorkbenchBuildImpactHtml() {\n  return window.RetirementPlanningWorkbench.renderBuildImpactContext' in dashboard


def test_reports_shell_rendering_moved_out_of_dashboard():
    reports = read("frontend/js/reports_ui.js")
    dashboard = dashboard_js_text()
    assert "window.RetirementReportsUI" in reports
    assert 'function renderDetailedResults() {\n  return window.RetirementReportsUI.renderDetailedResults' in dashboard
    assert 'function renderDetailedResultsNav() {\n  return window.RetirementReportsUI.renderDetailedResultsNav' in dashboard
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
