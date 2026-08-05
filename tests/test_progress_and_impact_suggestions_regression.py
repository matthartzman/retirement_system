from pathlib import Path

from _decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "frontend" / "index.html"
DASHBOARD_JS = ROOT / "frontend" / "js" / "dashboard.js"
TEMPLATE = ROOT / "src" / "dashboard_ui" / "template.py"


def test_build_overlay_has_static_percent_not_looping_bar():
    text = INDEX_HTML.read_text(encoding="utf-8") + "\n" + dashboard_js_text() + "\n" + (ROOT / "frontend" / "css" / "dashboard.css").read_text(encoding="utf-8")
    assert "buildOverlayPct" in text
    assert "api/build/start" in text
    assert "api/build/progress" in text
    assert "buildPulse" not in text
    assert "build-overlay.active .build-overlay-bar span{animation" not in text
    assert 'pct === "waiting" || pct === "indeterminate" || pct === null' in text
    assert 'p.textContent = value === null ? "Working…" : Math.round(value) + "%"' in text


def test_build_impact_adds_actionable_suggestions_under_three_metrics():
    text = INDEX_HTML.read_text(encoding="utf-8") + "\n" + dashboard_js_text()
    assert "buildImpactSuggestionsHtml" in text
    assert "Suggestions to improve the plan without lowering risk" in text
    assert "What the model used in this build" in text
    assert "Plain-English checks for assumptions" in text
    assert 'suggestions.slice(0, 6)' in text
    assert "dynamic-suggestions-panel" in text
    assert "collapsible-impact-section" in text
    assert "collapse-caret" in text
    assert "Use ${riskFloor} as a floor" in text
    assert "LTCG harvesting limits" in text


def test_build_impact_panels_are_collapsible_default_closed_with_left_caret():
    js = dashboard_js_text()
    css = (ROOT / "frontend" / "css" / "dashboard.css").read_text(encoding="utf-8")
    assert '<details class="impact-suggestions model-used-panel collapsible-impact-section"' in js
    assert '<details class="impact-suggestions collapsible-impact-section dynamic-suggestions-panel"' in js
    assert '<span class="collapse-caret" aria-hidden="true"></span><span class="collapsible-title">What the model used in this build</span>' in js
    assert '<span class="collapse-caret" aria-hidden="true"></span><span class="collapsible-title">Suggestions to improve the plan without lowering risk</span>' in js
    assert 'open>' not in js[js.find('<details class="impact-suggestions model-used-panel collapsible-impact-section"'):js.find('<details class="impact-suggestions model-used-panel collapsible-impact-section"')+140]
    assert 'open>' not in js[js.find('<details class="impact-suggestions collapsible-impact-section dynamic-suggestions-panel"'):js.find('<details class="impact-suggestions collapsible-impact-section dynamic-suggestions-panel"')+140]
    assert 'summary.collapsible-summary{display:flex;align-items:center;gap:8px' in css
    assert 'summary.collapsible-summary::-webkit-details-marker{display:none}' in css
    assert '.collapsible-impact-section[open] .collapse-caret{transform:rotate(90deg)}' in css
