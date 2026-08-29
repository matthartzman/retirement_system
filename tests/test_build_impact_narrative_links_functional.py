from pathlib import Path

from _decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]
from tests._decomp_dashboard import dashboard_js_text
DASHBOARD_CSS = ROOT / "frontend" / "css" / "dashboard.css"


def test_build_impact_has_natural_language_summary_and_source_links():
    js = dashboard_js_text()
    assert "function buildImpactNarrativeHtml" in js
    assert "Plain-English Build Impact summary" in js
    assert "Source-page links" in js
    assert "function buildImpactSourceLinksHtml" in js
    assert "buildSourceJumpHtml" in js
    assert "latestBuildImpactHtml(buildHistory[0])" in js


def test_captured_changes_store_source_step_metadata():
    js = dashboard_js_text()
    assert "sourceStepForRow(row)" in js
    assert 'sourceTitle: stepTitleById(sourceStep)' in js
    assert "sourceStepForSpecialLabel(label)" in js
    assert "<th>Source page</th>" in js


def test_build_impact_summary_is_styled():
    css = DASHBOARD_CSS.read_text(encoding="utf-8")
    assert ".latest-build-impact" in css
    assert ".impact-narrative" in css
    assert ".build-impact-source-list" in css
