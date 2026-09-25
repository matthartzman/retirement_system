"""#336: Large Discretionary is one-time only, never annualized (spec §4)."""
from pathlib import Path

from src.large_discretionary import (
    LD_CATEGORIES, LdItem, ld_budget_for_year, ld_cashflow_by_year, load_ld_items, migrate_repeatable,
)
from src.spending_budget_resolver import resolve_spending_inputs

ITEMS = [LdItem("Weddings", 60000, 2031, ""), LdItem("Auto", 45000, 2026, ""), LdItem("Large Gifts", 25000, 2029, "")]


def test_categories():
    assert LD_CATEGORIES == ("Weddings", "Large Gifts", "Education", "Auto", "Other")


def test_budget_counts_only_current_year_items():
    assert ld_budget_for_year(ITEMS, 2026) == 45000


def test_cashflow_lands_each_item_in_its_year():
    assert ld_cashflow_by_year(ITEMS) == {2031: 60000, 2026: 45000, 2029: 25000}


def test_repeatable_rows_expand_with_notice():
    sectioned = {"Large Discretionary Expenses": {
        "extra_1_type": "Vehicle", "extra_1_amount": "10000",
        "extra_1_start_year": "2026", "extra_1_end_year": "2037"}}
    items, notices = migrate_repeatable(sectioned)
    assert [i.year for i in items] == list(range(2026, 2038))
    assert all(i.category == "Auto" for i in items)
    assert any("Core category" in n for n in notices)  # 12 rows > 10


def test_short_repeatable_notice_does_not_recommend_core():
    sectioned = {"Large Discretionary Expenses": {
        "extra_1_type": "Tuition", "extra_1_amount": "$30,000",
        "extra_1_start_year": "2027", "extra_1_end_year": "2030"}}
    items, notices = migrate_repeatable(sectioned)
    assert [(i.category, i.year) for i in items] == [("Education", y) for y in range(2027, 2031)]
    assert len(notices) == 1 and "Core category" not in notices[0]


def test_legacy_type_mapping_and_one_time_rows():
    sectioned = {"Large Discretionary Expenses": {
        "extra_1_type": "Weddings", "extra_1_amount": "60000", "extra_1_year": "2031",
        "extra_2_type": "Gift to kids", "extra_2_amount": "5000", "extra_2_year": "2028",
        "extra_3_type": "Home Improvement", "extra_3_amount": "9000", "extra_3_year": "2029"}}
    items = load_ld_items(sectioned)
    assert [(i.category, i.year, i.amount) for i in items] == [
        ("Weddings", 2031, 60000), ("Large Gifts", 2028, 5000), ("Other", 2029, 9000)]


def _seed(root: Path, budget: str) -> None:
    (root / "input").mkdir(parents=True, exist_ok=True)
    (root / "input/client_spending_taxonomy.csv").write_text(
        "tracking_type,group,category_id,label,origin,status,notes\n"
        "Core Expenses,Food,groceries,Groceries,template,active,\n"
        "Large Discretionary,Weddings,weddings,Weddings,template,active,\n"
        "Large Discretionary,Auto,ld_auto,Auto,template,active,\n", encoding="utf-8")
    (root / "input/client_spending_aliases.csv").write_text(
        "match_value,match_field,exact,priority,category_id,source\n", encoding="utf-8")
    (root / "input/client_spending_budget.csv").write_text(
        "kind,key,label,annual_budget,start_year,end_year,one_time_year,notes\n" + budget, encoding="utf-8")


def test_resolver_projects_ld_only_in_each_rows_year(tmp_path):
    _seed(tmp_path, "category,groceries,Groceries,6000,,,,\n"
                    "line,weddings,Wedding,60000,,,2031,\n"
                    "line,ld_auto,Car,10000,2027,2028,,\n")
    out = resolve_spending_inputs(tmp_path, config={"plan_start": 2026, "plan_end": 2032})
    assert out["spend_base"] == 6000
    assert not [e for e in out["recurring_extras"] if e.get("tracking_type") == "Large Discretionary"]
    assert out["lump"] == {2031: 60000, 2027: 10000, 2028: 10000}
    assert out["lump_by_tracking_type"][2031]["Large Discretionary"] == 60000
    # Budget rollup: current year (2026) carries no LD dollars.
    assert "Large Discretionary" not in out["spending_rollup_by_year"][2026]
    assert out["spending_rollup_by_year"][2031]["Large Discretionary"]["Weddings"] == 60000
    assert len(out["ld_import_notices"]) == 1
