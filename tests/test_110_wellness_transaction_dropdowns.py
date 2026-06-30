from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[1]
HEALTHCARE_PREMIUM = "Healthcare Premium"
OLD_STEP = "retirement_" + "health" + "care"


def test_wellness_uses_healthcare_premium_language_without_renaming_step():
    js = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")
    assert "id:'retirement_wellness'" in js
    assert "title:'Wellness'" in js
    assert OLD_STEP not in js
    assert HEALTHCARE_PREMIUM in js

    with (ROOT / "input" / "client_spending_taxonomy.csv").open(newline="", encoding="utf-8") as f:
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
    js = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")
    spending_steps = [line for line in js.splitlines() if "group:'Spending'" in line and "id:" in line]
    assert spending_steps[-1].startswith("{id:'ytd_transactions'")
    assert "Actual Spending (This Year)" in spending_steps[-1]


def test_ytd_transaction_merchant_category_account_are_selects():
    js = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")
    assert "function ytdSelectFieldHtml" in js
    assert "ytdExistingValues(field)" in js
    assert "Merchant:ytdFirstExistingValue('Merchant')" in js
    assert "Category:ytdFirstExistingValue('Category')" in js
    assert "Account:ytdFirstExistingValue('Account')" in js
    assert "${ytdSelectFieldHtml(i,'Merchant',r.Merchant)}" in js
    assert "${ytdSelectFieldHtml(i,'Category',r.Category)}" in js
    assert "${ytdSelectFieldHtml(i,'Account',r.Account)}" in js
    assert "updateYtdTxn(${i},'Merchant',this.value)" not in js
    assert "updateYtdTxn(${i},'Category',this.value)" not in js
    assert "updateYtdTxn(${i},'Account',this.value)" not in js
