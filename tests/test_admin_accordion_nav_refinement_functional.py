from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ADMIN_HTML = ROOT / "frontend" / "admin.html"
ADMIN_CSS = ROOT / "frontend" / "css" / "admin.css"
ADMIN_JS = ROOT / "frontend" / "js" / "admin.js"


def test_admin_accordion_uses_disclosure_triangles_and_help_buttons():
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_CSS.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    assert '.cfg-section>summary::before{content:"▶"' in html
    assert '.cfg-section[open]>summary::before{content:"▼"' in html
    assert 'class="section-help-btn"' in html
    assert 'onclick="showSectionHelp(event,this)"' in html
    assert 'data-help-note' in html
    assert '<span class="hint">' not in html


def test_admin_left_nav_has_non_clickable_intuitive_groups():
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
