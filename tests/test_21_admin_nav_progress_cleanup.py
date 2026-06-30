from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN_HTML = ROOT / "frontend" / "admin.html"
ADMIN_CSS = ROOT / "frontend" / "css" / "admin.css"
ADMIN_JS = ROOT / "frontend" / "js" / "admin.js"
INDEX_HTML = ROOT / "frontend" / "index.html"
DASHBOARD_JS = ROOT / "frontend" / "js" / "dashboard.js"
TEMPLATE = ROOT / "src" / "dashboard_ui" / "template.py"


def test_system_config_is_split_into_left_nav_pages():
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_CSS.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    assert "SYSTEM_CONFIG_PAGES" in html
    for label in [
        "Runtime & files",
        "Capital-market assumptions",
        "Global rebalancing controls",
    ]:
        assert label in html
    assert "headingIndex===0" not in html
    assert "single-section" in html
    assert "collapseBySubsection" in html
    assert "syscfg_" in html


def test_focused_pages_use_left_step_navigation_not_nested_card_nav():
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_CSS.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    assert 'id="adminSteps"' in html
    assert "function adminNavItems" in html
    assert "openAreaFile" in html
    assert "openPricingControls" in html
    assert "openSecurityMaster" in html
    assert "Admin console" not in html


def test_build_progress_starts_at_beginning():
    html = INDEX_HTML.read_text(encoding="utf-8") + "\n" + DASHBOARD_JS.read_text(encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8")
    assert "Capturing the current workbook baseline...',0" in html
    assert "Math.max(0,Math.min(100,Number(pct)))" in html
    assert "b.style.width='0%'" in html
    assert "startBuildProgressTicker(20)" not in html
    assert "Elapsed ${elapsed}" in html
    assert "buildOverlayExpectedLabel" in html
    assert "api/build/progress" in html
    assert "dashboard UI asset loader" in template
