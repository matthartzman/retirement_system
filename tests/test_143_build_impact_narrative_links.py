from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_JS = ROOT / "frontend" / "js" / "dashboard.js"
DASHBOARD_CSS = ROOT / "frontend" / "css" / "dashboard.css"
SPEC = ROOT / "documentation" / "CURRENT_SYSTEM_DESIGN_SPEC.md"


def test_build_impact_has_natural_language_summary_and_source_links():
    js = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "function buildImpactNarrativeHtml" in js
    assert "Plain-English Build Impact summary" in js
    assert "Source-page links" in js
    assert "function buildImpactSourceLinksHtml" in js
    assert "buildSourceJumpHtml" in js
    assert "latestBuildImpactHtml(buildHistory[0])" in js


def test_captured_changes_store_source_step_metadata():
    js = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "sourceStepForRow(row)" in js
    assert "sourceTitle:stepTitleById(sourceStep)" in js
    assert "sourceStepForSpecialLabel(label)" in js
    assert "<th>Source page</th>" in js


def test_build_impact_summary_is_styled_and_roadmap_marked_complete():
    css = DASHBOARD_CSS.read_text(encoding="utf-8")
    spec = SPEC.read_text(encoding="utf-8")
    assert ".latest-build-impact" in css
    assert ".impact-narrative" in css
    assert ".build-impact-source-list" in css
    assert "Natural-language Build Impact summary with source-page links completed" in spec
