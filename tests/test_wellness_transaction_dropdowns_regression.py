from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[1]

from conftest import TEST_INPUT_DIR
from tests._decomp_dashboard import dashboard_js_text
HEALTHCARE_PREMIUM = "Healthcare Premium"
OLD_STEP = "retirement_" + "health" + "care"


def test_wellness_uses_healthcare_premium_language_without_renaming_step():
    js = dashboard_js_text()
    assert 'id: "retirement_wellness"' in js
    assert 'title: "Wellness"' in js
    assert OLD_STEP not in js
    assert HEALTHCARE_PREMIUM in js

    with (TEST_INPUT_DIR / "client_spending_taxonomy.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_id = {r["category_id"]: r for r in rows}
    assert by_id["exercise_health_equipment"]["tracking_type"] == "Wellness"
    assert by_id["health_club"]["tracking_type"] == "Wellness"
    assert by_id["vitamins_supplements"]["tracking_type"] == "Wellness"
    assert not any(r["tracking_type"] == "Healthcare" for r in rows)
    premium = [r for r in rows if r["tracking_type"] == "Wellness" and r["group"] == HEALTHCARE_PREMIUM and r["status"] == "active"]
    ids = {r["category_id"] for r in premium}
    assert {"pre65_wellness_premium", "medicare_part_b", "medicare_part_d", "medigap_premium"}.issubset(ids)


def test_income_expense_transactions_is_last_spending_step():
    js = dashboard_js_text()
    steps_src = js.split("const STEPS = [", 1)[1].split("\n];", 1)[0]
    step_blocks = steps_src.split("\n  {\n")
    spending_blocks = [b for b in step_blocks if 'group: "Spending"' in b]
    assert spending_blocks[-1].startswith('    id: "ytd_transactions"')
    assert "Actual Spending (This Year)" in spending_blocks[-1]


def test_ytd_transaction_merchant_category_account_pick_from_existing_values():
    js = dashboard_js_text()
    assert "function ytdSelectFieldHtml" in js
    assert "ytdExistingValues(field)" in js
    assert 'Merchant: ytdFirstExistingValue("Merchant")' in js
    assert 'Category: ytdFirstExistingValue("Category")' in js
    assert 'Account: ytdFirstExistingValue("Account")' in js
    assert '${ytdSelectFieldHtml(i, "Merchant", r.Merchant)}' in js
    assert '${ytdSelectFieldHtml(i, "Category", r.Category)}' in js
    assert '${ytdSelectFieldHtml(i, "Account", r.Account)}' in js
    # The three columns must never write straight through to the row: every
    # edit goes via commitYtdExistingValue, which rejects anything that is not
    # already an existing value (see the next test).
    assert "updateYtdTxn(${i},'Merchant',this.value)" not in js
    assert "updateYtdTxn(${i},'Category',this.value)" not in js
    assert "updateYtdTxn(${i},'Account',this.value)" not in js
    assert "commitYtdExistingValue(${i},'${field}',this)" in js


def test_ytd_existing_value_options_are_shared_not_inlined_per_row():
    """Perf ratchet. These columns used to inline a full <option> list into a
    per-row <select>: O(rows x distinct values), measured on a real plan at
    825,635 <option> nodes / ~62MB of DOM for one page of the step. They now
    share one <datalist> per field, rendered once for the whole table.
    """
    js = dashboard_js_text()
    assert "function ytdExistingDatalistsHtml" in js
    assert "${ytdExistingDatalistsHtml()}" in js
    # Exactly one call site -- once for the table, not once per row.
    assert js.count("${ytdExistingDatalistsHtml()}") == 1
    field_html = js.split("function ytdSelectFieldHtml", 1)[1].split("\n}", 1)[0]
    assert 'list="${ytdDatalistId(field)}"' in field_html
    assert "<option" not in field_html
    assert "<select" not in field_html
    # The per-row path must not rebuild the distinct-value set either.
    assert "ytdExistingValues(" not in field_html
    assert "ytdHasExistingValues(field)" in field_html
