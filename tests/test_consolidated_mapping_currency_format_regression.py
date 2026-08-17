import re
from pathlib import Path

from _decomp_dashboard import dashboard_function_source, dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]


def test_spending_category_mapping_language_is_consolidated():
    js = dashboard_js_text()
    assert "Category Manager" in js
    assert "Advanced Auto-Mapping Rules" in js
    assert "Target category" in js
    assert "Accounts &amp; Sources" in js
    assert "Category Mapping Rules" not in js
    assert "Taxonomy & Category Mapping" not in js
    assert "Taxonomy &amp; Mapping" not in js
    assert "Category → Group Map" not in js
    assert "Category Group Map" not in js
    assert re.search(r"function\s+renderCategoryMap\s*\(", js) is None
    assert "/api/spending/category-map" not in js


def test_accounts_sources_live_on_transactions_page_not_category_manager():
    # Both of these used to be sliced between neighbouring functions. F3.4 moved
    # renderYtdTransactionsStep and renderYtdTracking into
    # dashboard_decomp_ytd_and_plan_folder_io.js, where they appear in a
    # different order than they did in dashboard.js -- so the old slice came out
    # empty and the assertion failed against "".
    ytd_fn = dashboard_function_source("renderYtdTransactionsStep")
    assert "${renderYtdAccounts()}" in ytd_fn
    tax_fn = dashboard_function_source("renderTaxonomyManager")
    assert "renderYtdAccounts" not in tax_fn


def test_budget_amount_inputs_use_dollar_formatting_helpers():
    js = dashboard_js_text()
    assert "function budgetMoneyInputValue" in js
    assert "class=\"budget-money-input\"" in js
    assert "placeholder=\"$0\"" in js
    assert "updateTaxBudgetMoney" in js
    assert "updateCategoryDetailMoney" in js
    assert "updateLargeDiscLineMoney" in js
    assert "type=\"number\" min=\"0\" step=\"100\"" not in js
