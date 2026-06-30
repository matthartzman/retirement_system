from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_plan_state_and_preflight_ui_are_first_class_surfaces():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend/css/dashboard.css").read_text(encoding="utf-8")

    assert 'id="planStateBanner"' in html
    assert "function updatePlanStateBanner" in js
    assert "function renderBuildPreflightPanel" in js
    assert "/api/build/preflight" in js
    assert "Build preflight" in js
    assert ".plan-state-banner" in css
    assert ".preflight-panel" in css


def test_first_run_checklist_guides_logical_flow_to_review_and_build():
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend/css/dashboard.css").read_text(encoding="utf-8")

    assert "function firstRunChecklistHtml" in js
    for title in [
        "Household foundation",
        "Income",
        "Spending and actuals",
        "Assets and protection",
        "Strategy",
        "Stress tests",
        "Review and build",
    ]:
        assert title in js
    assert "firstRunChecklistHtml(false)" in js
    assert "firstRunChecklistHtml(true)" in js
    assert ".first-run-checklist" in css
    assert ".first-run-item" in css


def test_report_navigation_surfaces_stale_output_state():
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")

    assert "planStateFresh" in js
    assert "reportStale" in js
    assert "Stale" in js
    assert "Reports may be stale" in js


def test_build_history_surfaces_output_fingerprints_and_pricing_mode():
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend/css/dashboard.css").read_text(encoding="utf-8")

    assert "function buildHistoryProvenance" in js
    assert "function buildHistoryProvenanceHtml" in js
    assert "pricing_mode" in js
    assert "workbook_fingerprint" in js
    assert "results_model_fingerprint" in js
    assert "output_fingerprints" in js
    assert ".build-history-provenance" in css


def test_system_configuration_splits_normal_settings_and_advanced_maintenance():
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend/css/dashboard.css").read_text(encoding="utf-8")

    assert "Normal Settings" in js
    assert "Advanced Maintenance" in js
    assert "Open advanced maintenance tools" in js
    assert "system-maintenance-details" in js
    assert "system-config-section normal-settings" in js
    assert "system-config-section advanced-maintenance" in js
    assert ".system-config-section" in css
    assert ".system-maintenance-details" in css
