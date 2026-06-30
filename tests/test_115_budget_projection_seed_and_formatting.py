from pathlib import Path

from src.spending_budget_resolver import apply_budget_to_engine_config


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_budget_rollup_applies_even_when_only_housing_domain_rows_exist(tmp_path):
    root = tmp_path
    write(root / 'input/client_spending_taxonomy.csv', '''tracking_type,group,category_id,label,origin,status,notes
Housing,Utilities,housing_utilities,Utilities,custom,active,
Housing,Maintenance,home_maintenance,Home Maintenance,custom,active,
Housing,Other,ho_insurance,Homeowners Insurance,template,active,
''')
    write(root / 'input/client_spending_aliases.csv', 'match_value,match_field,exact,priority,category_id,source\n')
    write(root / 'input/client_spending_budget.csv', '''kind,key,label,annual_budget,start_year,end_year,one_time_year,notes
category,housing_utilities,Utilities,2100,,,,
category,home_maintenance,Home Maintenance,1200,,,,
category,ho_insurance,Homeowners Insurance,2000,,,,
''')
    c = {'plan_start': 2026, 'plan_end': 2027}
    apply_budget_to_engine_config(c, root=root)
    assert c['budget_drives_projection'] is True
    assert c['spending_rollup_by_year'][2026]['Housing']['Utilities'] == 2100
    assert c['spending_rollup_by_year'][2026]['Housing']['Maintenance'] == 1200
    assert c['spending_rollup_by_year'][2026]['Housing']['Other'] == 2000


def test_heloc_repayment_years_is_integer_not_currency_in_ui_source():
    js = Path('frontend/js/dashboard.js').read_text(encoding='utf-8')
    assert "if(r&&l==='heloc_repayment_years')return 'number'" in js


def test_home_improvement_line_controls_projection_window_over_category_actual(tmp_path):
    root = tmp_path
    write(root / 'input/client_spending_taxonomy.csv', '''tracking_type,group,category_id,label,origin,status,notes
Housing,Home Improvement,home_improvement,Home Improvement,custom,active,
''')
    write(root / 'input/client_spending_aliases.csv', 'match_value,match_field,exact,priority,category_id,source\n')
    write(root / 'input/client_spending_budget.csv', '''kind,key,label,annual_budget,start_year,end_year,one_time_year,notes
category,home_improvement,Home Improvement,15082,,,,annualized actual should not run forever when detail line exists
line,home_improvement,Home Improvement,25000,2026,2030,,projection window
''')
    from src.spending_budget_resolver import resolve_spending_inputs
    out = resolve_spending_inputs(root, year_range=range(2026, 2033), config={'plan_start': 2026, 'plan_end': 2032})
    assert out['spending_rollup_by_year'][2026]['Housing']['Home Improvement'] == 25000
    assert out['spending_rollup_by_year'][2030]['Housing']['Home Improvement'] == 25000
    assert 'Home Improvement' not in out['spending_rollup_by_year'][2031].get('Housing', {})


def test_housing_ui_has_rent_buy_toggle_and_area_type_dropdown():
    js = Path('frontend/js/dashboard.js').read_text(encoding='utf-8')
    assert 'Rent or Buy' in js
    assert "<button type=\"button\" class=\"btn-toggle'+(!isPurchase?' active':'')+'\" onclick=\"editValue('+typeRow.row_index+',\\'rent\\',null);renderMain()\">Rent</button>" in js
    assert "function housingAreaTypeSelect(row)" in js
    assert "city_type:['urban','suburban','rural']" in js


def test_mortgage_budget_fallback_does_not_resurrect_configured_mortgage_after_payoff():
    src = Path('src/projection_stages/deterministic_engine.py').read_text(encoding='utf-8')
    assert 'mort_pmt_configured' in src
    assert 'never resurrect the budget amount after' in src
    assert "if mort_yr <= 0 and not (mort_pmt_configured and mort_end_configured):" in src
