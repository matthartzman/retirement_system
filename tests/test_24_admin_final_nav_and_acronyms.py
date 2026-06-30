from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ADMIN_HTML = ROOT / "frontend" / "admin.html"
ADMIN_JS = ROOT / "frontend" / "js" / "admin.js"


def test_admin_left_nav_matches_user_ui_step_model_without_top_level_groups():
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    assert 'placeholder="Search navigation' in html and 'id="adminSteps"' in html
    assert '<div class="nav-section-title">' not in html
    assert 'function adminNavItems' in html
    assert 'renderAdminNav' in html


def test_all_admin_click_handlers_have_declared_functions_or_safe_builtins():
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
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


def test_admin_title_case_preserves_common_acronyms():
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    for acronym in ["LTCG", "STCG", "PDIA", "ETF", "NIIT", "IRA", "RMD", "HSA", "CMA"]:
        assert acronym in html
    for mixed in ["Ltcg", "Stcg", "Pdia", "Niit", "Etf", "Ira", "Rmd", "Hsa", "Cma"]:
        assert mixed not in html
