from pathlib import Path

from _decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "frontend" / "index.html"
DASHBOARD_JS = ROOT / "frontend" / "js" / "dashboard.js"


def test_build_progress_starts_at_beginning():
    """Build progress overlay starts at 0%, displays elapsed time, updates dynamically."""
    html = INDEX_HTML.read_text(encoding="utf-8") + "\n" + dashboard_js_text()
    assert 'Capturing the current workbook baseline...",\n      0' in html
    assert 'Math.max(0, Math.min(100, Number(pct)))' in html
    assert 'b.style.width = "0%"' in html
    assert "startBuildProgressTicker(20)" not in html
    assert "Elapsed ${formatElapsed(" in html
    assert "buildOverlayExpectedLabel" not in html
    assert "api/build/progress" in html
