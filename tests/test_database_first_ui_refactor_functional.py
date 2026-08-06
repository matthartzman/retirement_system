from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def test_dashboard_top_level_groups():
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    js += open(r"C:\RetirementPlanning\Version 10\frontend\js\dashboard_decomp_row_model.js", encoding="utf-8").read()
    steps_block = re.search(r"const STEPS = \[(.*?)\n\];", js, re.S).group(1)
    groups = []
    for name in re.findall(r'group: "([^"]+)"', steps_block):
        if name not in groups:
            groups.append(name)
    # Item 178: the "Accounts" group was dissolved — Investment Holdings and
    # Reserve Requirements now live under "Assets & Protection".
    # Item 197: "Profile" renamed to "People and Income".
    assert groups == ["Plan Status", "People and Income", "Spending", "Assets & Protection", "Strategy", "Stress Tests", "Reports & Review", "Reports", "Settings"]
    assert "Advanced Options" not in re.search(r"function renderSteps\(\).*?box\.innerHTML", js, re.S).group(0)


def test_primary_workflow_is_database_first_not_csv_folder_save_load():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    js += open(r"C:\RetirementPlanning\Version 10\frontend\js\dashboard_decomp_row_model.js", encoding="utf-8").read()
    assert ">Admin<" not in html
    assert "Save Plan Data" not in html
    assert "Build Workbook" not in html
    assert "Save Changes" in html
    assert "Download Workbook" in html
    assert "function renderSystemConfiguration" in js
    # Export CSV backup is the real, reachable CSV import/export adapter
    # feature. The generic "CSV import/export" phrase this test used to also
    # check lived only in APP_UNAVAILABLE_MESSAGE, a constant nothing ever
    # read -- removed in the 2026-08-06 dead-code sweep ahead of the
    # dashboard.js ES-module conversion. See test_ui_tax_ss_cleanup.py's
    # status-offline-message assertion for the real "app unavailable" text.
    assert "Export CSV backup" in js


def test_system_configuration_route_replaces_separate_admin_workflow():
    routes = (ROOT / "src/server/admin_routes.py").read_text(encoding="utf-8")
    assert '@app.route("/system-configuration")' in routes
    assert "System Configuration UI not found" in routes
    assert "removed-client-registry" not in routes


def test_sqlite_remains_configured_source_of_truth():
    cfg = (ROOT / "system_config.csv").read_text(encoding="utf-8")
    assert "System Configuration,Runtime,config_backend,SQLITE" in cfg
    assert "SQLite" in cfg or "SQLITE" in cfg


def test_build_and_load_no_longer_use_remembered_csv_folder_as_authority():
    # loadAll/runBuild moved to dashboard_decomp_row_model.js (domain-module-
    # split shared-core extraction); startNewPlan/downloadFile stayed in
    # dashboard.js. The regexes below extract "everything between function A
    # and function B", so row_model's content must come FIRST or these two
    # cross-file boundaries land in the wrong order.
    js = (ROOT / "frontend/js/dashboard_decomp_row_model.js").read_text(encoding="utf-8")
    js += (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    load_fn = re.search(r"async function loadAll\(opts = \{\}\).*?async function startNewPlan", js, re.S).group(0)
    # downloadWithBuild (not downloadFile, a different, similarly-named
    # function that stayed in dashboard.js) is the next top-level declaration
    # after runBuild in dashboard_decomp_row_model.js now.
    build_fn = re.search(r"async function runBuild\(.*?\).*?async function downloadWithBuild", js, re.S).group(0)
    assert "refreshServerFromPlanFolder" not in load_fn
    assert "Local folder:" not in load_fn
    assert "saveCurrentPlanToSelectedFolderForBuild" not in build_fn
    assert "sqlite_snapshot" in build_fn
    assert "saved local database snapshot" in build_fn


def test_results_explorer_uses_simplified_categories():
    model_src = (ROOT / "src/results_model.py").read_text(encoding="utf-8")
    generated = ROOT / "output/results_explorer_model.json"
    assert 'order = ["Reports", "Strategy", "Stress Tests", "System Configuration", "Other workbook detail"]' in model_src
    if generated.exists():
        text = generated.read_text(encoding="utf-8")
        assert '"Reports"' in text
        assert "Overview & quality checks" not in text
        assert "Year-by-year projections" not in text


def test_build_endpoints_reject_direct_csv_payloads():
    routes = (ROOT / "src/server/workbook_routes.py").read_text(encoding="utf-8")
    assert "Direct CSV payloads are no longer accepted by the build endpoint" in routes
    assert "csv_updated_before_build" not in routes
    assert "local_plan_data_loaded_before_build" not in routes
