from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ADMIN_HTML = ROOT / "frontend" / "admin.html"
ADMIN_CSS = ROOT / "frontend" / "css" / "admin.css"
ADMIN_JS = ROOT / "frontend" / "js" / "admin.js"


def test_admin_accordion_uses_disclosure_triangles_and_help_buttons():
    """Disclosure triangles (▶▼) for section collapse, help buttons with data attributes."""
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_CSS.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    assert '.cfg-section>summary::before{content:"▶"' in html
    assert '.cfg-section[open]>summary::before{content:"▼"' in html
    assert 'class="section-help-btn"' in html
    assert 'onclick="showSectionHelp(event,this)"' in html
    assert 'data-help-note' in html
    assert '<span class="hint">' not in html


def test_admin_left_nav_has_non_clickable_intuitive_groups():
    """Left navigation uses group labels (non-clickable headers) with semantic names."""
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_CSS.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    assert 'nav-group-label' in html
    for group in [
        'System setup',
        'System configuration',
        'Investment policy',
        'Market data',
        'Tax & accounts',
        'Operations',
        'Reference data',
    ]:
        assert group in html
    assert re.search(r'group: "System configuration"', html)


def test_admin_click_handlers_still_have_backing_functions_after_refinement():
    """All onclick handlers have declared functions or are allowed builtins."""
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_CSS.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    functions = set(re.findall(r"\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", html))
    functions.update(re.findall(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", html))
    allowed = {"location", "document", "querySelectorAll", "forEach", "Math", "JSON", "encodeURIComponent", "esc"}
    missing = []
    for onclick in re.findall(r'onclick="([^"]+)"', html):
        if onclick == "${it.action}":
            continue
        for name in re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", onclick):
            if name not in functions and name not in allowed:
                missing.append((onclick, name))
    assert not missing


def test_system_config_pages_split_into_left_nav_with_correct_labels():
    """System configuration is split into left nav pages, specific labels present."""
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_CSS.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    assert "SYSTEM_CONFIG_PAGES" in html
    for label in [
        "Runtime & files",
        "Capital-market assumptions",
        "Global rebalancing controls",
    ]:
        assert label in html
    # Older labels removed in refactor
    pages_block = html.split("const SYSTEM_CONFIG_PAGES = [", 1)[1].split("];", 1)[0]
    assert "Pricing & market data" not in pages_block
    assert "All settings" not in pages_block


def test_collapsible_headings_closed_by_default_with_subsection_split():
    """Collapsible section headings grouped by subsection, closed by default, split to left nav."""
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_CSS.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    assert "collapseBySubsection" in html
    assert "headingIndex === 0" not in html  # not starting with first index open
    assert "single-section" in html
    assert "details.length <= 8" in html  # max details per page
    assert "editorHeadingNavPages" in html
    assert "Additional collapsible heading page in the left navigation" in html
    assert "showEditorHeadingPage" in html
    assert "applyEditorHeadingPage(Math.floor((idx + 1) / 8), false)" in html
    assert "headings split into" not in html


def test_save_bar_fixed_and_pricing_page_has_no_diagnostics_shortcut():
    """Save/cancel buttons fixed at bottom; pricing page excludes diagnostic links."""
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_CSS.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    assert ".cfg-actions{position:fixed" in html
    pricing_block = html.split("async function openPricingControls", 1)[1].split("async function showDiagnostics", 1)[0]
    assert "showDiagnostics()" not in pricing_block
    assert "Pricing diagnostics" not in pricing_block
    assert "Back</button>" not in html


def test_admin_left_nav_matches_user_ui_step_model_without_top_level_groups():
    """Left nav uses step navigation model (adminSteps) matching main dashboard."""
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    assert 'placeholder="Search navigation' in html and 'id="adminSteps"' in html
    assert '<div class="nav-section-title">' not in html
    assert 'function adminNavItems' in html
    assert 'renderAdminNav' in html


def test_focused_pages_use_left_step_navigation_not_nested_card_nav():
    """Page navigation uses left adminSteps list, not nested card/accordion nav."""
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_CSS.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    assert 'id="adminSteps"' in html
    assert "function adminNavItems" in html
    assert "openAreaFile" in html
    assert "openPricingControls" in html
    assert "openSecurityMaster" in html
    assert "Admin console" not in html


def test_admin_title_case_preserves_common_acronyms():
    """Field labels preserve uppercase for financial acronyms (LTCG, STCG, IRA, RMD, HSA, etc.)."""
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    for acronym in ["LTCG", "STCG", "PDIA", "ETF", "NIIT", "IRA", "RMD", "HSA", "CMA"]:
        assert acronym in html
    for mixed in ["Ltcg", "Stcg", "Pdia", "Niit", "Etf", "Ira", "Rmd", "Hsa", "Cma"]:
        assert mixed not in html


def test_system_config_compact_editor_uses_syscfg_prefix():
    """System config fields use syscfg_ namespace/prefix."""
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    assert "syscfg_" in html
