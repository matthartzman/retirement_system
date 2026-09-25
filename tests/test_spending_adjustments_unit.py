"""#335: category step-downs / step-ups by year (spec §5)."""
import pytest

from src.spending_adjustments import Adjustment, adjustment_factor, load_adjustments
from src.spending_budget_resolver import resolve_spending_inputs

A = [Adjustment("dining", 2035, None, -0.20), Adjustment("dining", 2042, None, -0.10),
     Adjustment("ALL:Travel", 2038, None, -0.50), Adjustment("home_aide", 2045, 2050, 0.40)]


def test_before_start_is_unchanged():
    assert adjustment_factor(A, "dining", "Core Expenses", 2034) == 1.0


def test_steps_compound_in_order():
    assert adjustment_factor(A, "dining", "Core Expenses", 2042) == pytest.approx(0.72)


def test_tracking_type_row_applies_to_every_category_in_it():
    assert adjustment_factor(A, "hotels", "Travel", 2040) == 0.5


def test_end_year_is_inclusive_then_reverts():
    assert adjustment_factor(A, "home_aide", "Wellness", 2050) == pytest.approx(1.4)
    assert adjustment_factor(A, "home_aide", "Wellness", 2051) == 1.0


def test_all_row_and_category_row_compound():
    adjs = [Adjustment("ALL:Travel", 2030, None, -0.50), Adjustment("hotels", 2030, None, -0.20)]
    assert adjustment_factor(adjs, "hotels", "Travel", 2030) == pytest.approx(0.4)
    assert adjustment_factor(adjs, "flights", "Travel", 2030) == pytest.approx(0.5)


def test_load_adjustments_reads_percent_rows():
    sectioned = {"Spending Adjustments": {
        "adj_1_category": "dining", "adj_1_start_year": "2035", "adj_1_end_year": "",
        "adj_1_change_pct": "-20",
        "adj_2_category": "ALL:Travel", "adj_2_start_year": "2038", "adj_2_end_year": "2045",
        "adj_2_change_pct": "-50%",
        "adj_3_category": "", "adj_3_start_year": "2030", "adj_3_change_pct": "10"}}
    assert load_adjustments(sectioned) == [
        Adjustment("dining", 2035, None, -0.20), Adjustment("ALL:Travel", 2038, 2045, -0.50)]


def _seed(root):
    (root / "input").mkdir(parents=True, exist_ok=True)
    (root / "input/client_spending_taxonomy.csv").write_text(
        "tracking_type,group,category_id,label,origin,status,notes\n"
        "Core Expenses,Food,groceries,Groceries,template,active,\n"
        "Core Expenses,Food,dining,Dining,template,active,\n"
        "Travel,Trips,hotels,Hotels,template,active,\n"
        "Wellness,Care,home_aide,Home Aide,template,active,\n", encoding="utf-8")
    (root / "input/client_spending_aliases.csv").write_text(
        "match_value,match_field,exact,priority,category_id,source\n", encoding="utf-8")
    (root / "input/client_spending_budget.csv").write_text(
        "kind,key,label,annual_budget,start_year,end_year,one_time_year,notes\n"
        "category,groceries,Groceries,6000,,,,\n"
        "category,dining,Dining,4000,,,,\n"
        "category,hotels,Hotels,5000,,,,\n"
        "category,home_aide,Home Aide,10000,,,,\n", encoding="utf-8")


def test_resolver_without_adjustments_emits_no_factors(tmp_path):
    _seed(tmp_path)
    out = resolve_spending_inputs(tmp_path, config={"plan_start": 2026, "plan_end": 2030})
    assert out["spend_base_adjustment_by_year"] == {}
    assert out["spending_category_rollup_by_year"][2030]["dining"] == 4000


def test_resolver_scales_rollups_and_spend_base_share(tmp_path):
    _seed(tmp_path)
    adjs = [Adjustment("dining", 2028, None, -0.50), Adjustment("home_aide", 2029, 2029, 0.40)]
    out = resolve_spending_inputs(tmp_path, config={"plan_start": 2026, "plan_end": 2030,
                                                    "spending_adjustments": adjs})
    assert out["spend_base"] == 10000  # unadjusted base; the factor is per year
    assert out["spend_base_adjustment_by_year"][2027] == 1.0
    assert out["spend_base_adjustment_by_year"][2028] == pytest.approx((6000 + 2000) / 10000)
    cats = out["spending_category_rollup_by_year"]
    assert cats[2028]["dining"] == 2000 and cats[2027]["dining"] == 4000
    assert cats[2029]["home_aide"] == pytest.approx(14000) and cats[2030]["home_aide"] == 10000
    assert out["spending_rollup_by_year"][2029]["Wellness"]["Care"] == pytest.approx(14000)
