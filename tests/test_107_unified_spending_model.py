from pathlib import Path

from src import spending_tracker as st
from src.spending_budget_resolver import resolve_spending_inputs


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_unified_summary_group_mode_disables_category_detail(tmp_path):
    root = tmp_path
    write(root / "input/client_spending_taxonomy.csv", """tracking_type,group,category_id,label,origin,status,notes
Core Expenses,Food,groceries,Groceries,template,active,
Core Expenses,Food,restaurants,Restaurants,template,active,
Business,Operations,biz_services,Business Services,template,active,
""")
    write(root / "input/client_spending_aliases.csv", """match_value,match_field,exact,priority,category_id,source
Groceries,category,1,80,groceries,seed
Business Services,category,1,80,biz_services,seed
""")
    write(root / "input/client_spending_budget.csv", """kind,key,label,annual_budget,start_year,end_year,one_time_year,notes
group,Core Expenses::Food,Food,12000,,,,group wins
category,groceries,Groceries,5000,,,,ignored in group mode
category,restaurants,Restaurants,3000,,,,ignored in group mode
category,biz_services,Business Services,7000,,,,business modeled not spend base
""")
    write(root / "input/ytd_transactions.csv", """Date,Merchant,Category,Account,Amount,Owner
2026-01-10,Store,Groceries,Card,-100,Shared
2026-01-11,Vendor,Business Services,Card,-50,Shared
""")
    model = st.spending_model(root, year=2026)
    food = next(g for t in model["tracking_types"] if t["tracking_type"] == "Core Expenses" for g in t["groups"] if g["group"] == "Food")
    assert food["budget"] == 12000
    assert food["budget_mode"] == "group"
    assert all(c["budget_disabled"] for c in food["categories"])
    assert model["totals"]["budget_derived_core_spend_base"] == 12000
    assert next(t for t in model["tracking_types"] if t["tracking_type"] == "Business")["budget"] == 7000


def test_resolver_routes_time_bounded_travel_lines_to_extras_and_keeps_core_lines_in_base(tmp_path):
    root = tmp_path
    write(root / "input/client_spending_taxonomy.csv", """tracking_type,group,category_id,label,origin,status,notes
Core Expenses,Gifts,charity,Charity,template,active,
Travel,Trips,domestic_flights,Domestic Flights,template,active,
Housing,Projects,other_improvement,Other Improvement,template,active,
Business,Operations,biz_services,Business Services,template,active,
""")
    write(root / "input/client_spending_aliases.csv", "match_value,match_field,exact,priority,category_id,source\n")
    write(root / "input/client_spending_budget.csv", """kind,key,label,annual_budget,start_year,end_year,one_time_year,notes
line,charity,Charitable Giving,5000,,,,core recurring line remains in spend_base
line,domestic_flights,Annual Vacation,25000,2026,2028,,time bounded travel extra
line,other_improvement,Home Project,10000,2027,2027,,home improvement extra
category,biz_services,Business Services,3000,,,,business not spend base
""")
    resolved = resolve_spending_inputs(root, year_range=range(2026, 2029))
    assert resolved["spend_base"] == 5000
    assert resolved["business_reference_budget"] == 3000
    assert any(e["type"] == "Annual Vacation" and not e["is_home_improvement"] for e in resolved["recurring_extras"])
    assert any(e["type"] == "Home Project" and e["is_home_improvement"] for e in resolved["recurring_extras"])


def test_group_budget_mode_round_trips_through_csv_and_drives_projection(tmp_path):
    """Save a summary group budget, reload it (as an app restart would), and
    confirm both the persisted mode and the projected dollars survive.

    Regression guard for the defect where a group-level Travel budget reverted
    to Detail on restart and dropped out of / distorted cash flow. The mode was
    written to the CSV but the read path (_legacy_budget_to_unified) discarded
    the _mode column, and the resolver ignored _mode entirely — so this must be
    exercised through the real save/load/resolve cycle, not a static file.
    """
    root = tmp_path
    write(root / "input/client_spending_taxonomy.csv", """tracking_type,group,category_id,label,origin,status,notes
Travel,Travel,travel_vacation,Travel & Vacation,transaction,active,
Travel,Travel,travel_housing,Travel - Housing,transaction,active,
""")
    write(root / "input/client_spending_aliases.csv", "match_value,match_field,exact,priority,category_id,source\n")
    # Mirror the real Travel data shape: each category carries both a category
    # budget row and a matching detail line (as travel_vacation/travel_housing do
    # in input/client_spending_budget.csv). In detail mode the lines are the
    # authority; a summary group budget must suppress this whole breakdown.
    write(root / "input/client_spending_budget.csv", """kind,key,label,annual_budget,start_year,end_year,one_time_year,notes
category,travel_vacation,Travel & Vacation,8000,,,,
category,travel_housing,Travel - Housing,2000,,,,
line,travel_vacation,Travel & Vacation,8000,,,,
line,travel_housing,Travel - Housing,2000,,,,
""")
    year_range = range(2026, 2031)

    def travel_total(res):
        return sum(e["amount"] for e in res["recurring_extras"]
                   if "travel" in str(e.get("category_id", "")).lower()
                   or "travel" in str(e.get("type", "")).lower())

    # Baseline: detail lines total $10,000.
    assert travel_total(resolve_spending_inputs(root, year_range=year_range)) == 10000

    # Frontend sets the Travel group to Summary $25,000 and saves. The taxBudget
    # object carries the group entry keyed grp::<tt>::<group> with _mode.
    budget = st.load_budget_by_category(root)
    budget["grp::Travel::Travel"] = {"annual_budget": 25000, "notes": "", "_mode": "summary"}
    st.save_budget_by_category(root, budget)

    # App restart: the mode must survive the CSV round-trip.
    reloaded = st.load_budget_by_category(root)
    assert reloaded["grp::Travel::Travel"].get("_mode") == "summary"

    # Summary mode suppresses the line detail and projects the single group amount.
    assert travel_total(resolve_spending_inputs(root, year_range=year_range)) == 25000

    # Toggle back to Detail: the group row is inert and the per-line detail returns.
    budget = st.load_budget_by_category(root)
    budget["grp::Travel::Travel"]["_mode"] = "detail"
    st.save_budget_by_category(root, budget)
    assert st.load_budget_by_category(root)["grp::Travel::Travel"].get("_mode") == "detail"
    assert travel_total(resolve_spending_inputs(root, year_range=year_range)) == 10000


def test_unused_template_categories_start_hidden_and_restore_by_group(tmp_path):
    root = tmp_path
    write(root / "input/client_spending_taxonomy.csv", """tracking_type,group,category_id,label,origin,status,notes
Core Expenses,Food,groceries,Groceries,transaction,active,
Core Expenses,Food,meal_delivery,Meal Delivery,template,active,
Core Expenses,Food,restaurants,Restaurants,template,active,
""")
    write(root / "input/client_spending_aliases.csv", """match_value,match_field,exact,priority,category_id,source
Groceries,category,1,80,groceries,seed
""")
    write(root / "input/client_spending_budget.csv", """kind,key,label,annual_budget,start_year,end_year,one_time_year,notes
category,groceries,Groceries,1000,,,,
""")
    write(root / "input/ytd_transactions.csv", """Date,Merchant,Category,Account,Amount,Owner
2026-01-10,Store,Groceries,Card,-100,Shared
""")
    hidden = st.hide_unused_template_categories(root)
    assert set(hidden) == {"meal_delivery", "restaurants"}
    model = st.spending_model(root, year=2026)
    food = next(g for t in model["tracking_types"] if t["tracking_type"] == "Core Expenses" for g in t["groups"] if g["group"] == "Food")
    assert [c["id"] for c in food["categories"]] == ["groceries"]
    assert food["template_available_count"] == 2
    restored = st.restore_template_group(root, "Core Expenses", "Food")
    assert set(restored) == {"meal_delivery", "restaurants"}


def test_spending_analysis_includes_income_and_expenses_but_excludes_taxes(tmp_path):
    root = tmp_path
    write(root / "input/client_spending_taxonomy.csv", """tracking_type,group,category_id,label,origin,status,notes
Income,Income,paychecks,Paychecks,transaction,active,
Core Expenses,Food,groceries,Groceries,transaction,active,
Business,Operations,biz_services,Business Services,transaction,active,
Transfer,Tax,income_taxes,Income Taxes,transaction,active,
""")
    write(root / "input/client_spending_aliases.csv", """match_value,match_field,exact,priority,category_id,source
Paychecks,category,1,80,paychecks,seed
Groceries,category,1,80,groceries,seed
Business Services,category,1,80,biz_services,seed
Income Taxes,category,1,80,income_taxes,seed
""")
    write(root / "input/client_spending_budget.csv", "kind,key,label,annual_budget,start_year,end_year,one_time_year,notes\n")
    write(root / "input/ytd_transactions.csv", """Date,Merchant,Category,Account,Amount,Owner
2026-01-10,Employer,Paychecks,Bank,10000,Shared
2026-01-11,Store,Groceries,Card,-100,Shared
2026-01-12,Vendor,Business Services,Card,-50,Shared
2026-01-13,IRS,Income Taxes,Bank,-500,Shared
""")
    dash = st.spending_dashboard(root, year=2026)
    assert dash["income_total"] == 10000
    assert dash["actuals_total"] == 150
    assert any(g["tracking_type"] == "Income" for g in dash["groups"])
    assert not any(g["tracking_type"] == "Transfer" for g in dash["groups"])
