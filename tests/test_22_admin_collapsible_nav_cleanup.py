from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN_HTML = ROOT / "frontend" / "admin.html"
ADMIN_CSS = ROOT / "frontend" / "css" / "admin.css"
ADMIN_JS = ROOT / "frontend" / "js" / "admin.js"


def test_system_config_left_nav_removes_redundant_pricing_and_all_settings():
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_CSS.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    pages_block = html.split("const SYSTEM_CONFIG_PAGES=[", 1)[1].split("];", 1)[0]
    assert "Pricing & market data" not in pages_block
    assert "All settings" not in pages_block
    assert "Runtime & files" in pages_block
    assert "Global rebalancing controls" in pages_block


def test_collapsible_headings_are_closed_by_default_and_split_to_left_nav_pages():
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_CSS.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    assert "collapseBySubsection" in html
    assert "headingIndex===0" not in html
    assert "single-section" in html
    assert "details.length<=8" in html
    assert "editorHeadingNavPages" in html
    assert "Additional collapsible heading page in the left navigation" in html
    assert "showEditorHeadingPage" in html
    assert "applyEditorHeadingPage(Math.floor((idx+1)/8),false)" in html
    assert "headings split into" not in html


def test_save_bar_fixed_and_pricing_page_has_no_diagnostics_shortcut():
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_CSS.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    assert ".cfg-actions{position:fixed" in html
    pricing_block = html.split("async function openPricingControls", 1)[1].split("async function showDiagnostics", 1)[0]
    assert "showDiagnostics()" not in pricing_block
    assert "Pricing diagnostics" not in pricing_block
    assert "Back</button>" not in html
