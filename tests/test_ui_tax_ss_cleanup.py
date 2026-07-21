from pathlib import Path
import csv
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]

def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_user_and_admin_navigation_have_single_scope_toggle_search_and_status_offline_message():
    user_html = read('frontend/index.html')
    admin_html = read('frontend/admin.html')
    user_js = read('frontend/js/dashboard.js')
    admin_js = read('frontend/js/admin.js')
    assert 'id="combinedSearch"' in user_html
    assert 'setSearchScope(\'nav\')' in user_html and 'setSearchScope(\'page\')' in user_html
    assert 'id="adminCombinedSearch"' in admin_html
    assert 'setAdminSearchScope(\'nav\')' in admin_html and 'setAdminSearchScope(\'page\')' in admin_html
    assert 'Search this page...' in user_js and 'Search this page...' in admin_js
    assert 'Saving, build, download, pricing refresh, Plan Chat, and' in user_js


def test_inline_field_context_help_removed_and_nav_descriptions_break_line():
    user_js = read('frontend/js/dashboard.js')
    admin_js = read('frontend/js/admin.js')
    assert 'class="field-note"' not in user_js
    assert '<br><span class="step-desc"' in user_js
    assert '<br><span class="step-desc"' in admin_js


def test_social_security_funding_discount_defaults_and_engine_application_are_present():
    income = read('input/client_income.csv') if (ROOT/'input/client_income.csv').exists() else read('../input/input/client_income.csv')
    assert 'ss_funding_discount_year,2032' in income
    assert 'ss_funding_discount_pct,22.00%' in income
    assert 'ss_funding_factor' in read('src/planning_engines.py')
    assert 'ss_funding_discount_pct' in read('src/data_io.py')


def test_tax_and_irmaa_tables_updated_to_2025_and_workflow_documents_annual_review():
    taxes = read('src/taxes.py')
    tax_dashboard = read('reference_data/tax_update_dashboard.csv')
    constants = read('reference_data/tax_constants.csv')
    assert 'FEDERAL_BRACKETS_VALUE_YEAR = int(os.environ.get(\'FEDERAL_BRACKETS_VALUE_YEAR\') or 2025)' in taxes
    assert '2025' in tax_dashboard
    assert 'Annual process:' in tax_dashboard
    assert 'std_ded_mfj,2025,30000' in constants
    assert 'ss_wage_base,2026,184500' in constants


def test_other_assets_grouping_and_529_add_route_exist():
    user_js = read('frontend/js/dashboard.js')
    assets = read('input/client_assets.csv') if (ROOT/'input/client_assets.csv').exists() else read('../input/input/client_assets.csv')
    assert 'Other Assets' in user_js
    assert 'Note Receivable' in user_js or 'Note receivable' in user_js or 'note_receivable' in user_js
    assert "'HSA':1" in user_js and "'DAF':2" in user_js and "'529 Plans':3" in user_js
    assert 'Add 529 section' in user_js
    assert 'Education Funding,529 Plan 1' in assets


def test_withdrawal_order_is_fixed_and_reserve_ui_controls_are_dropdown_based():
    # The withdrawal priority table used to be editable (WITHDRAWAL_TYPES,
    # withdrawalPrioritySelect/withdrawalTypeSelect/withdrawalOptionSelect),
    # but that UI wrote to CSV rows the engine never read (see
    # documentation/reports/SYSTEM_REVIEW_2026-07-18.md §10.1). It was
    # deliberately removed and replaced with a fixed, read-only cascade
    # description; test_withdrawal_roth_ui_cleanup.py covers that in detail.
    user_js = read('frontend/js/dashboard.js')
    assets = read('input/client_assets.csv') if (ROOT/'input/client_assets.csv').exists() else read('../input/input/client_assets.csv')
    assert 'FIXED_WITHDRAWAL_CASCADE_DESCRIPTION' in user_js
    assert 'renderWithdrawalOrderTable' in user_js and 'not user-configurable' in user_js
    assert 'reserve_account' in assets
    assert 'Taxable/Trust | Roth | IRA | HSA | Cash' in assets


