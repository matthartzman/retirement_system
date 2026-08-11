from pathlib import Path
import csv
import importlib.util
import sys

from conftest import TEST_INPUT_DIR, dashboard_js_sources

ROOT = Path(__file__).resolve().parents[1]

def read(path: str) -> str:
    # 'input/foo.csv' resolves to the committed frozen plan, not the user's
    # live input/ (gitignored, so absent on CI and in fresh worktrees).
    path = str(path)
    target = TEST_INPUT_DIR / Path(path).name if path.startswith('input/') else ROOT / path
    return target.read_text(encoding='utf-8')


def test_user_and_admin_navigation_have_single_scope_toggle_search_and_status_offline_message():
    user_html = read('frontend/index.html')
    admin_html = read('frontend/admin.html')
    user_js = dashboard_js_sources()
    admin_js = read('frontend/js/admin.js')
    assert 'id="combinedSearch"' in user_html
    assert 'setSearchScope(\'nav\')' in user_html and 'setSearchScope(\'page\')' in user_html
    assert 'id="adminCombinedSearch"' in admin_html
    assert 'setAdminSearchScope(\'nav\')' in admin_html and 'setAdminSearchScope(\'page\')' in admin_html
    assert 'Search this page...' in user_js and 'Search this page...' in admin_js
    # The dead-code sweep ahead of the dashboard.js ES-module conversion
    # (2026-08-06) removed APP_UNAVAILABLE_MESSAGE -- a constant nothing ever
    # actually read (setAppControls just disables data-requires-app="1"
    # buttons; it never displayed this text). The real "app unavailable"
    # status message users can hit is the one api() throws when appReady is
    # false.
    assert 'Application is not available. Start with tools/launchers/start_ui.bat' in user_js


def test_inline_field_context_help_removed_and_nav_descriptions_break_line():
    user_js = dashboard_js_sources()
    admin_js = read('frontend/js/admin.js')
    assert 'class="field-note"' not in user_js
    assert '<br><span class="step-desc"' in user_js
    assert '<br><span class="step-desc"' in admin_js


def test_social_security_funding_discount_defaults_and_engine_application_are_present():
    income = read('input/client_income.csv')
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
    user_js = dashboard_js_sources()
    assets = read('input/client_assets.csv')
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
    user_js = dashboard_js_sources()
    # The Liquidity Buffer reserve_account field is checked against the
    # schema template (the stable contract for "does this field still
    # exist"), not a live input/client_assets.csv -- a household with no
    # Liquidity Buffer rows configured legitimately has zero reserve_account
    # rows in its own CSV, which isn't a regression.
    schema = read('reference_data/schema.csv')
    assert 'FIXED_WITHDRAWAL_CASCADE_DESCRIPTION' in user_js
    assert 'renderWithdrawalOrderTable' in user_js and 'not user-configurable' in user_js
    assert 'reserve_account' in schema
    assert 'Taxable/Trust | Roth | IRA | HSA | Cash' in schema


