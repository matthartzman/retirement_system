"""Static source-text checks that named UI/CSS/JS surfaces exist -- NOT that
they render or behave correctly. Every assertion is a substring match against
HTML/JS/CSS files (system review 2026-07-21, Q1); despite the "usability
surfaces" name, nothing here opens a page, drives a DOM, or checks rendered
output. Treat as a trip-wire against a renamed/deleted identifier, not
usability coverage.
"""
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


def test_system_configuration_is_single_consolidated_section():
    # Item 180: the Settings page was consolidated into a single section.
    # The Normal Settings / Advanced Maintenance split (and its <details>
    # wrapper) was removed; Save Plan and Report Readiness were dropped; CSV
    # Backup and the renamed "All Assumptions Editor" moved into the one
    # section, and a button opens the System Configuration Console.
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend/css/dashboard.css").read_text(encoding="utf-8")

    # Consolidated: the split headings and the advanced <details> are gone.
    assert "system-config-section normal-settings" not in js
    assert "system-config-section advanced-maintenance" not in js
    assert "system-maintenance-details" not in js
    # Removed cards.
    assert "showConfigCardHelp('save_plan')" not in js
    assert "showConfigCardHelp('report_readiness')" not in js
    # Item 192 (Option 4 Phase 2): the navigable Settings destinations —
    # Economic & Tax Assumptions, Optional Modules, Field Finder, and Workbook
    # Formatting — moved out of the card hub into first-class left-nav pages, so
    # the hub is now just operational maintenance tools.
    assert "showConfigCardHelp('planning_assumptions')" not in js
    assert "showConfigCardHelp('all_assumptions_link')" not in js
    # Retained operational surfaces in the single maintenance section.
    assert "Export CSV backup" in js
    assert "Open System Configuration Console" in js
    assert ".system-config-section" in css
