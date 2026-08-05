from pathlib import Path

from _decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "frontend" / "index.html"
DASHBOARD_JS = ROOT / "frontend" / "js" / "dashboard.js"
TEMPLATE = ROOT / "src" / "dashboard_ui" / "template.py"


def test_build_overlay_uses_real_milestones_not_fake_ticker():
    text = INDEX_HTML.read_text(encoding="utf-8") + "\n" + dashboard_js_text()
    assert "api/build/start" in text
    assert "api/build/progress" in text
    assert "Elapsed ${elapsed}s" not in text
    assert "typical local builds finish" not in text
    assert "phases=['Running retirement projection'" not in text
    assert "buildPulse" not in text
    assert "dashboard UI asset loader" in TEMPLATE.read_text(encoding="utf-8")


def test_build_impact_includes_monte_carlo_risk_dimension():
    text = INDEX_HTML.read_text(encoding="utf-8") + "\n" + dashboard_js_text() + "\n" + (ROOT / "frontend" / "css" / "dashboard.css").read_text(encoding="utf-8")
    assert "Probability of Success" in text
    assert "fmtPctDelta" in text
    assert "mc_success" in text
    assert "mc_success" in text
    assert ".impact-grid{display:grid;grid-template-columns:" in text
