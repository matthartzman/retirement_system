import csv
from pathlib import Path

from src.spending_tracker import monthly_series, taxonomy_flat

ROOT = Path(__file__).resolve().parents[1]


def _read_csv(path: Path):
    with path.open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def test_flask_removal_and_workbench_proposals_are_documented():
    flask_doc = (ROOT / 'documentation' / 'FLASK_REMOVAL_ARCHITECTURE.md').read_text()
    workbench_doc = (ROOT / 'documentation' / 'PLANNING_WORKBENCH_CONSOLIDATION_PROPOSAL.md').read_text()

    assert 'Stdlib Local HTTP Runtime' in flask_doc
    assert 'Preserve public URLs first' in flask_doc
    assert 'Move route business logic into dependency-free service functions' in flask_doc
    assert 'Planning Workbench' in workbench_doc
    assert 'Baseline' in workbench_doc
    assert 'Change Set' in workbench_doc
    assert 'Run Type' in workbench_doc
    assert 'Impact' in workbench_doc


def test_healthcare_premium_group_and_medical_oop_cap_contract():
    flat = taxonomy_flat(ROOT)

    for cid in ['pre65_wellness_premium', 'medicare_part_b', 'medicare_part_d', 'medigap_premium']:
        assert flat[cid]['tracking_type'] == 'Wellness'
        assert flat[cid]['group'] == 'Healthcare Premium'

    assert flat['pre65_wellness_premium']['label'] == 'Pre-65 Healthcare Premium'
    assert flat['annual_oop_max']['group'] == 'Medical Cap Reference'
    assert flat['annual_oop_max']['label'] == 'Annual Household Medical OOP Cap'

    budget_rows = _read_csv(ROOT / 'input' / 'client_spending_budget.csv')
    by_key = {r['key']: r for r in budget_rows if r.get('kind') == 'category'}
    assert by_key['annual_oop_max']['annual_budget'] == ''
    assert 'not a spending budget row' in by_key['annual_oop_max']['notes']
    assert by_key['wellness_premium']['annual_budget'] == ''
    assert by_key['wellness_premium']['notes'].startswith('Legacy transaction alias')


def test_travel_detail_is_not_an_active_group():
    rows = _read_csv(ROOT / 'input' / 'client_spending_taxonomy.csv')
    active_travel_rows = [r for r in rows if r.get('status') == 'active' and r.get('tracking_type') == 'Travel']
    assert active_travel_rows
    assert not any(r.get('group') == 'Travel Detail' for r in active_travel_rows)


def test_monthly_trajectory_includes_all_non_tax_spending(tmp_path):
    input_dir = tmp_path / 'input'
    _write_csv(input_dir / 'client_spending_taxonomy.csv',
               ['tracking_type', 'group', 'category_id', 'label', 'origin', 'status', 'notes'], [
        {'tracking_type': 'Core Expenses', 'group': 'Food & Dining', 'category_id': 'groceries', 'label': 'Groceries', 'origin': 'custom', 'status': 'active', 'notes': ''},
        {'tracking_type': 'Housing', 'group': 'Mortgage', 'category_id': 'mortgage', 'label': 'Mortgage', 'origin': 'custom', 'status': 'active', 'notes': ''},
        {'tracking_type': 'Wellness', 'group': 'Healthcare Premium', 'category_id': 'pre65_wellness_premium', 'label': 'Pre-65 Healthcare Premium', 'origin': 'custom', 'status': 'active', 'notes': ''},
        {'tracking_type': 'Travel', 'group': 'Travel', 'category_id': 'travel_vacation', 'label': 'Travel Vacation', 'origin': 'custom', 'status': 'active', 'notes': ''},
        {'tracking_type': 'Large Discretionary', 'group': 'Large Discretionary', 'category_id': 'wedding', 'label': 'Wedding', 'origin': 'custom', 'status': 'active', 'notes': ''},
        {'tracking_type': 'Business', 'group': 'Business', 'category_id': 'office_supplies', 'label': 'Office Supplies', 'origin': 'custom', 'status': 'active', 'notes': ''},
        {'tracking_type': 'Transfer', 'group': 'Taxes', 'category_id': 'income_taxes', 'label': 'Income Taxes', 'origin': 'custom', 'status': 'active', 'notes': ''},
        {'tracking_type': 'Income', 'group': 'Income', 'category_id': 'paychecks', 'label': 'Paychecks', 'origin': 'custom', 'status': 'active', 'notes': ''},
        {'tracking_type': 'Transfer', 'group': 'Transfers', 'category_id': 'credit_card_payment', 'label': 'Credit Card Payment', 'origin': 'custom', 'status': 'active', 'notes': ''},
    ])
    _write_csv(input_dir / 'client_spending_aliases.csv',
               ['match_value', 'match_field', 'exact', 'priority', 'category_id', 'source'], [
        {'match_value': 'Groceries', 'match_field': 'category', 'exact': '1', 'priority': '90', 'category_id': 'groceries', 'source': 'test'},
        {'match_value': 'Mortgage', 'match_field': 'category', 'exact': '1', 'priority': '90', 'category_id': 'mortgage', 'source': 'test'},
        {'match_value': 'Healthcare Premium', 'match_field': 'category', 'exact': '1', 'priority': '90', 'category_id': 'pre65_wellness_premium', 'source': 'test'},
        {'match_value': 'Travel', 'match_field': 'category', 'exact': '1', 'priority': '90', 'category_id': 'travel_vacation', 'source': 'test'},
        {'match_value': 'Wedding', 'match_field': 'category', 'exact': '1', 'priority': '90', 'category_id': 'wedding', 'source': 'test'},
        {'match_value': 'Office Supplies', 'match_field': 'category', 'exact': '1', 'priority': '90', 'category_id': 'office_supplies', 'source': 'test'},
        {'match_value': 'Income Taxes', 'match_field': 'category', 'exact': '1', 'priority': '90', 'category_id': 'income_taxes', 'source': 'test'},
        {'match_value': 'Paychecks', 'match_field': 'category', 'exact': '1', 'priority': '90', 'category_id': 'paychecks', 'source': 'test'},
        {'match_value': 'Credit Card Payment', 'match_field': 'category', 'exact': '1', 'priority': '90', 'category_id': 'credit_card_payment', 'source': 'test'},
    ])
    _write_csv(input_dir / 'client_spending_budget.csv',
               ['kind', 'key', 'label', 'annual_budget', 'start_year', 'end_year', 'one_time_year', 'notes'], [])
    _write_csv(input_dir / 'ytd_transactions.csv',
               ['Date', 'Merchant', 'Category', 'Account', 'Original Statement', 'Notes', 'Amount', 'Tags', 'Owner'], [
        {'Date': '2026-01-03', 'Merchant': 'Market', 'Category': 'Groceries', 'Account': 'Checking', 'Original Statement': '', 'Notes': '', 'Amount': '-10', 'Tags': '', 'Owner': ''},
        {'Date': '2026-01-04', 'Merchant': 'Bank', 'Category': 'Mortgage', 'Account': 'Checking', 'Original Statement': '', 'Notes': '', 'Amount': '-20', 'Tags': '', 'Owner': ''},
        {'Date': '2026-01-05', 'Merchant': 'Carrier', 'Category': 'Healthcare Premium', 'Account': 'Checking', 'Original Statement': '', 'Notes': '', 'Amount': '-30', 'Tags': '', 'Owner': ''},
        {'Date': '2026-01-06', 'Merchant': 'Airline', 'Category': 'Travel', 'Account': 'Checking', 'Original Statement': '', 'Notes': '', 'Amount': '-40', 'Tags': '', 'Owner': ''},
        {'Date': '2026-01-07', 'Merchant': 'Venue', 'Category': 'Wedding', 'Account': 'Checking', 'Original Statement': '', 'Notes': '', 'Amount': '-50', 'Tags': '', 'Owner': ''},
        {'Date': '2026-01-08', 'Merchant': 'Office Store', 'Category': 'Office Supplies', 'Account': 'Checking', 'Original Statement': '', 'Notes': '', 'Amount': '-60', 'Tags': '', 'Owner': ''},
        {'Date': '2026-01-09', 'Merchant': 'IRS', 'Category': 'Income Taxes', 'Account': 'Checking', 'Original Statement': '', 'Notes': '', 'Amount': '-70', 'Tags': '', 'Owner': ''},
        {'Date': '2026-01-10', 'Merchant': 'Employer', 'Category': 'Paychecks', 'Account': 'Checking', 'Original Statement': '', 'Notes': '', 'Amount': '1000', 'Tags': '', 'Owner': ''},
        {'Date': '2026-01-11', 'Merchant': 'Card', 'Category': 'Credit Card Payment', 'Account': 'Checking', 'Original Statement': '', 'Notes': '', 'Amount': '-80', 'Tags': '', 'Owner': ''},
    ])

    series = monthly_series(tmp_path, 2026, total_budget=1200)
    assert series[0]['actual'] == 210.0
    assert series[0]['budget'] == 100.0
    assert all(m['actual'] == 0.0 for m in series[1:])
