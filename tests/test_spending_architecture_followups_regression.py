import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def csv_rows(name):
    with open(ROOT / name, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def test_taxonomy_realignment_for_104():
    rows = csv_rows('input/client_spending_taxonomy.csv')
    by_id = {r['category_id']: r for r in rows}
    assert by_id['entertainment_recreation']['tracking_type'] == 'Travel'
    assert by_id['entertainment_recreation']['group'] == 'Travel'
    assert all(r['group'] != 'Travel & Lifestyle' for r in rows)
    assert all(r['group'] != 'Transportation' for r in rows)
    assert by_id['dentist']['tracking_type'] == 'Wellness'
    assert by_id['vision']['tracking_type'] == 'Wellness'
    assert not any(r['tracking_type'] == 'Core Expenses' and r['group'] == 'Wellness' for r in rows)


def test_spending_nav_and_save_copy():
    js = (ROOT / 'frontend/js/dashboard.js').read_text(encoding='utf-8')
    spending_core = js.index('id: "spending_core"')
    travel = js.index('id: "spending_travel"')
    large = js.index('id: "spending_travel_extras"')
    ytd = js.index('id: "ytd_transactions"')
    holdings = js.index('id: "holdings"')
    assert spending_core < travel < large < ytd < holdings
    assert 'title: "Spending Model"' in js
    assert 'Save Budget' not in js
    assert 'saveAll(true)' in js


def test_insurance_policy_dropdown_includes_all_types_and_heloc_on_other_page():
    js = (ROOT / 'frontend/js/dashboard.js').read_text(encoding='utf-8')
    assert "renderHELOCInputsOnOtherPage" in js
    assert "HELOC modeling inputs" in js
    assert "Use HELOC or turn it off" in js
    # Protection Policies (Disability, Long-Term Care, Umbrella, Auto, Home,
    # Property and Casualty, Other) were merged into the Special Income,
    # Annuities & Insurance page's single policy-type dropdown alongside Life,
    # so the choice notes should now list all 8 types together.
    rows = csv_rows('input/client_insurance_estate.csv')
    policy_rows = [r for r in rows if r.get('section') == 'Insurance In Force' and r.get('label') == 'policy_type' and r.get('units') == 'choice']
    assert policy_rows
    for row in policy_rows:
        notes = row.get('notes', '')
        assert 'Auto |' in notes
        assert 'Home |' in notes
        assert 'Property and Casualty' in notes
