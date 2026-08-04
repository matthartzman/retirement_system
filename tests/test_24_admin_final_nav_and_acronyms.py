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


# test_all_admin_click_handlers_have_declared_functions_or_safe_builtins was
# deleted here (system review 2026-08-04, quality finding
# `duplicate-admin-click-handler-test`): its regex extraction, allowed-set and
# assertion were byte-identical to
# test_25_admin_accordion_nav_refinement.test_admin_click_handlers_still_have_backing_functions_after_refinement,
# which additionally scans admin.css. The test_25 copy is a strict superset, so
# no coverage was lost. Removals from the numbered-file baseline are permitted
# by tests/test_freeze_numbered_test_files.py.

def test_admin_title_case_preserves_common_acronyms():
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    for acronym in ["LTCG", "STCG", "PDIA", "ETF", "NIIT", "IRA", "RMD", "HSA", "CMA"]:
        assert acronym in html
    for mixed in ["Ltcg", "Stcg", "Pdia", "Niit", "Etf", "Ira", "Rmd", "Hsa", "Cma"]:
        assert mixed not in html
