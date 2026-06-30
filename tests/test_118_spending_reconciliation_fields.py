from pathlib import Path

from src import spending_tracker as st


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_spending_model_exposes_explicit_reconciliation_fields_and_keeps_budget_only_rows(tmp_path):
    root = tmp_path
    write(root / "input/client_spending_taxonomy.csv", """tracking_type,group,category_id,label,origin,status,notes
Housing,Utilities,electric,Electric,template,active,
Wellness,Premiums,medicare_part_b_premium,Medicare Part B Premium,template,active,
Core Expenses,Food,groceries,Groceries,transaction,active,
""")
    write(root / "input/client_spending_aliases.csv", """match_value,match_field,exact,priority,category_id,source
Groceries,category,1,80,groceries,seed
""")
    write(root / "input/client_spending_budget.csv", """kind,key,label,annual_budget,start_year,end_year,one_time_year,notes
category,electric,Electric,2400,,,,housing budget-only row must remain visible
category,medicare_part_b_premium,Medicare Part B Premium,2200,,,,wellness budget-only row must remain visible
category,groceries,Groceries,6000,,,,core budget row
""")
    write(root / "input/ytd_transactions.csv", """Date,Merchant,Category,Account,Amount,Owner
2026-01-10,Market,Groceries,Card,-100,Shared
""")
    model = st.spending_model(root, year=2026)
    housing = next(t for t in model["tracking_types"] if t["tracking_type"] == "Housing")
    utilities = next(g for g in housing["groups"] if g["group"] == "Utilities")
    electric = utilities["categories"][0]
    assert electric["ytd_actual"] == 0
    assert electric["annual_budget"] == 2400
    assert electric["projection_seed"] == 2400
    assert electric["source_page"] == "Housing"
    assert electric["is_read_only_reference"] is True
    assert utilities["annual_budget"] == 2400
    assert utilities["projection_seed"] == 2400
    assert model["totals"]["annual_budget"] == 10600
    assert model["totals"]["projection_seed"] == 10600


def test_spending_analysis_and_categories_use_same_reconciliation_labels():
    dash = Path("frontend/js/dashboard.js").read_text(encoding="utf-8")
    analysis = Path("frontend/js/spending_dashboard.js").read_text(encoding="utf-8")
    for label in ["YTD Actual", "Annualized Actual", "Annual Budget", "Projection Seed"]:
        assert label in dash
        assert label in analysis
    assert "spendYtd(row)" in analysis
    assert "spendingRowYtd(row)" in dash
