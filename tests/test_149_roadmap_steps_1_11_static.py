from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_frontend_phase3_and_ux_surfaces_present():
    js = read("frontend/js/dashboard_source_truth_banners.js")
    assert "dashboard_phase3_module_manifest_v1" in js
    assert "source-of-truth" in js
    assert "Recommended spending flow" in js
    assert "first_run.skip_reason" in js
    assert "Plan Data Summary preview" in js
    assert "important-row jumps" in js or "detail-jump" in js
    assert "State tax assumptions" in js
    assert "Withdrawal order" in js
    assert "Keyboard shortcuts" not in js  # behavior is encoded as key handlers, not a user-facing label
    assert "ctrlKey" in js and "ArrowRight" in js


def test_index_loads_modular_overlay_and_manifest():
    html = read("frontend/index.html")
    assert "js/modules/phase3_module_manifest.js" in html
    assert "js/dashboard_source_truth_banners.js" in html


def test_css_and_docs_record_roadmap_steps_1_11():
    css = read("frontend/css/dashboard.css")
    spec = read("documentation/CURRENT_SYSTEM_DESIGN_SPEC.md")
    api = read("documentation/API_CONTRACTS.md")
    assert "source-truth-label" in css
    assert "plan_snapshot_restore_v1" in api
    assert "Typed API contract registry" in spec
    assert "Detailed Results now adds readability controls" in spec
    assert "Review-and-Build closeout" in spec


def test_static_journey_guards_for_remaining_roadmap_items():
    js = read("frontend/js/dashboard_source_truth_banners.js")
    assert "Review and Build" in js
    assert "Categories → Transactions → Spending Analysis" in js
    assert "Open source input" in js
    assert "window.print" in js
    assert "Advisor-ready disabled" in js
    assert "expandPrintableSections" in js
