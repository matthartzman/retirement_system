import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def rows(name):
    with open(ROOT / name, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def test_home_current_section_excludes_budget_detail_fields():
    js = (ROOT / 'frontend/js/dashboard.js').read_text(encoding='utf-8')
    assert "_CURRENT_MORTGAGE_EXCL=['annual_real_estate_taxes']" in js
    assert "'homeowners_insurance_annual','home_maintenance_annual','utilities_annual'" in js
    assert 'Real-estate taxes, homeowners insurance, maintenance, and utilities are entered in Housing Budget Detail below.' in js


def test_home_improvement_is_single_category_and_line_target():
    tax = rows('input/client_spending_taxonomy.csv')
    by_id = {r['category_id']: r for r in tax}
    assert by_id['home_improvement']['status'] == 'active'
    assert by_id['other_improvement']['status'] == 'deleted'
    assert by_id['other_improvement']['notes'].lower().find('merged') >= 0
    assert not any(r['key'] == 'other_improvement' for r in rows('input/client_spending_budget.csv'))
    assert not any(r['category_id'] == 'other_improvement' for r in rows('input/client_spending_budget_lines.csv'))


def test_wellness_budget_detail_uses_group_level_add_row_and_contains_premium_categories():
    js = (ROOT / 'frontend/js/dashboard.js').read_text(encoding='utf-8')
    # Wellness shares the same Tracking Type -> Group -> Category renderer as
    # Spending Model/Lifestyle Spending, so "+ Add row" appears once per group
    # instead of once per category (bug 132).
    assert 'wellness-flat-budget' not in js
    assert "addGroupDetailRow('${esc(tt)}','${gj}')" in js
    assert 'The Healthcare Premium group contains Pre-65 Healthcare Premium plus Medicare Part B, Part D, and Part G premiums' in js
    tax = rows('input/client_spending_taxonomy.csv')
    active_wellness = {r['category_id']: r for r in tax if r['tracking_type'] == 'Wellness' and r['status'] == 'active'}
    for cid in ['pre65_wellness_premium', 'medicare_part_b', 'medicare_part_d', 'medigap_premium', 'annual_oop_max']:
        assert cid in active_wellness
    assert active_wellness['pre65_wellness_premium']['label'] == 'Pre-65 Healthcare Premium'
    for cid in ['pre65_wellness_premium', 'medicare_part_b', 'medicare_part_d', 'medigap_premium']:
        assert active_wellness[cid]['group'] == 'Healthcare Premium'
    assert active_wellness['annual_oop_max']['group'] == 'Medical Cap Reference'
    assert active_wellness['medigap_premium']['label'] == 'Medicare Part G / Medigap Premium'


def test_travel_budget_detail_removes_domestic_and_lifestyle_active_labels():
    tax = rows('input/client_spending_taxonomy.csv')
    active_travel = [r for r in tax if r['tracking_type'] == 'Travel' and r['status'] == 'active']
    text = '\n'.join(','.join([r['group'], r['category_id'], r['label']]) for r in active_travel)
    assert 'Lifestyle' not in text
    assert 'Domestic' not in text
    assert 'domestic_flights' not in text
    assert any(r['category_id'] == 'recurring_travel' for r in active_travel)
    assert not any(r['group'] == 'Travel Detail' for r in active_travel)
    assert not any(r['key'] == 'domestic_flights' for r in rows('input/client_spending_budget.csv'))
    assert not any(r['category_id'] == 'domestic_flights' for r in rows('input/client_spending_budget_lines.csv'))
