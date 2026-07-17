from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_phase1_save_mode_closeout_and_planning_lever_gate_are_present():
    js = read("frontend/js/dashboard.js")
    css = read("frontend/css/dashboard.css")

    assert "function pageSaveMode" in js
    assert "pageSaveModeHtml(st.id)" in js
    assert "Save Changes" in js
    assert "Build saves first" in js
    assert ".save-mode-chip" in css

    assert "function renderReviewCloseoutChecklist" in js
    assert "Review-and-Build closeout" in js
    assert "Validate required inputs" in js
    assert "Refresh or freeze pricing" in js
    assert "Inspect Plan Data Summary" in js
    assert ".review-closeout" in css

    assert "function planningLeversBaselineReady" in js
    assert "Build once before using Strategy Levers" in js
    assert ".empty-state-panel" in css


def test_phase1_plan_data_summary_print_preview_is_active():
    html = read("frontend/index.html")
    js = read("frontend/js/dashboard.js")
    css = read("frontend/css/dashboard.css")

    assert "dashboard.css?v=13" in html
    assert "dashboard.js?v=30" in html
    assert "Plan Data Summary preview" in js
    assert "window.print()" in js
    assert ".plan-data-preview-tools" in css
    assert "@media print" in css
