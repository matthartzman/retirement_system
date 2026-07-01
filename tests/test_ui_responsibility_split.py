from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.version import VERSION

ROOT = Path(__file__).resolve().parents[1]

CLIENT_PLAN_FILES = [
    'client_household.csv','client_income.csv','client_spending.csv','client_assets.csv',
    'client_policy.csv','client_insurance_estate.csv','client_optional_functions.csv',
    'client_holdings.csv','target_allocation.csv','asset_class_optimizer_controls.csv'
]


def test_navigation_search_exists_in_user_and_admin_ui():
    user_html = (ROOT/'frontend/index.html').read_text(encoding='utf-8')
    admin_html = (ROOT/'frontend/admin.html').read_text(encoding='utf-8')
    user_js = (ROOT/'frontend/js/dashboard.js').read_text(encoding='utf-8')
    admin_js = (ROOT/'frontend/js/admin.js').read_text(encoding='utf-8')
    assert 'placeholder="Search navigation' in user_html
    assert 'function setNavSearch' in user_js
    assert 'placeholder="Search navigation' in admin_html
    assert 'function setAdminNavSearch' in admin_js


def test_collapsible_sections_closed_by_default_and_single_section_not_forced_open():
    user_js = (ROOT/'frontend/js/dashboard.js').read_text(encoding='utf-8')
    admin_js = (ROOT/'frontend/js/admin.js').read_text(encoding='utf-8')
    assert "idx===0?'open'" not in user_js
    assert "opts.defaultOpen||isFirst" not in admin_js
    assert 'single-section' in admin_js


def test_admin_no_longer_exposes_client_plan_data_editors():
    admin_js = (ROOT/'frontend/js/admin.js').read_text(encoding='utf-8')
    for name in CLIENT_PLAN_FILES:
        assert f"file:'{name}'" not in admin_js
    assert 'Client-specific Plan Data is read-only here' in admin_js
    assert 'editWorkspacePlanData' in admin_js
    assert 'Compact edit</button>`' not in admin_js


def test_user_ui_has_client_specific_advanced_pages_and_output_focused_help():
    user_js = (ROOT/'frontend/js/dashboard.js').read_text(encoding='utf-8')
    for token in ["id:'economic_tax_assumptions'", "id:'withdrawal_strategy'", "id:'roth_conversion'", "id:'allocation_assets'", "id:'optional_functions'"]:
        assert token in user_js
    for phrase in ['Monte Carlo', 'Executive Summary']:
        assert phrase in user_js


def test_release_surfaces_are_v10():
    paths = ['frontend/index.html','frontend/admin.html','system_config.csv','src/version.py']
    for rel in paths:
        text = (ROOT/rel).read_text(encoding='utf-8', errors='ignore')
        assert ('v8.'+'2') not in text
        assert VERSION in text
