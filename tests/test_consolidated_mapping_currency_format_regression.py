import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_spending_category_mapping_language_is_consolidated():
    js = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")
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
    js = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")
    ytd_fn = js[js.index("function renderYtdTransactionsStep") : js.index("function renderYtdTracking", js.index("function renderYtdTransactionsStep")) if "function renderYtdTracking" in js[js.index("function renderYtdTransactionsStep"):] else js.index("function renderSpendingDashboardOrLoad")]
    assert "${renderYtdAccounts()}" in ytd_fn
    tax_fn = js[js.index("function renderTaxonomyManager") : js.index("function showTaxonomyAddForm")]
    assert "renderYtdAccounts" not in tax_fn


def test_budget_amount_inputs_use_dollar_formatting_helpers():
    js = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")
    assert "function budgetMoneyInputValue" in js
    assert "class=\"budget-money-input\"" in js
    assert "placeholder=\"$0\"" in js
    assert "updateTaxBudgetMoney" in js
    assert "updateCategoryDetailMoney" in js
    assert "updateLargeDiscLineMoney" in js
    assert "type=\"number\" min=\"0\" step=\"100\"" not in js
