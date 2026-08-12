from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from tests._decomp_dashboard import dashboard_js_text


def _run_build_function(js: str) -> str:
    # saveAll/runBuild both live in dashboard_decomp_row_model.js now (domain-
    # module-split shared-core extraction); downloadWithBuild is the next
    # top-level declaration after runBuild in that file. "function
    # downloadFile" (a different, similarly-named function) stayed in
    # dashboard.js and is no longer physically adjacent to runBuild.
    start = js.index("async function runBuild")
    return js[start: js.index("async function downloadWithBuild", start)]


def _save_all_function(js: str) -> str:
    start = js.index("async function saveAll")
    return js[start: js.index("async function runBuild", start)]


def test_save_plan_data_does_not_reload_selected_folder_over_unsaved_ui_state():
    js = (ROOT / "frontend/js/dashboard_decomp_row_model.js").read_text(encoding="utf-8")
    save_all = _save_all_function(js)
    assert "loadLocalPlanDataFirst" not in save_all


def test_build_never_silently_reloads_selected_folder_over_loaded_plan():
    row_model_js = (ROOT / "frontend/js/dashboard_decomp_row_model.js").read_text(encoding="utf-8")
    js = row_model_js + (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    run_build = _run_build_function(row_model_js)
    assert 'const hadUnsaved = hasUnsavedPlanChanges()' in run_build
    assert "loadLocalPlanDataFirst" not in run_build
    assert "selectedFolderDiffersFromLoadedPlan" in js


def test_frontend_assets_are_cache_busted_and_no_cache_headers_are_set():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    assert "js/dashboard.js?v=" in html
    assert "css/dashboard.css?v=" in html
    routes = (ROOT / "src/server/base_routes.py").read_text(encoding="utf-8")
    assert "Cache-Control" in routes and "no-store" in routes


def test_pywebview_bridge_is_inert_for_http_server_mode():
    bridge = (ROOT / "frontend/js/pywebview_bridge.js").read_text(encoding="utf-8")
    assert "window.location.protocol !== 'file:'" in bridge
    assert "return;" in bridge.split("window.location.protocol !== 'file:'", 1)[1].split("Readiness queue", 1)[0]
