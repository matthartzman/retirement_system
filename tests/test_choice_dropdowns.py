from pathlib import Path
import csv
import pytest
ROOT = Path(__file__).resolve().parents[1]


def test_manual_schema_overrides_generated_duplicates_and_roth_choices_are_choices():
    import sys
    sys.path.insert(0, str(ROOT))
    from src.schema_registry import load_schema
    schema = load_schema()
    key = ('Withdrawal Policy','Roth Conversion','roth_objective_mode')
    assert schema[key]['type'] == 'choice'
    assert 'BALANCED_RETIREMENT' in schema[key]['description']
    assert schema[('Withdrawal Policy','Roth Conversion','roth_target_bracket_rate')]['type'] == 'choice'
    assert schema[('Withdrawal Policy','Roth Conversion','roth_irmaa_target_tier')]['type'] == 'choice'


def test_user_ui_choice_renderer_uses_server_choice_options_and_irmaa_tier_labels():
    js = (ROOT/'frontend/js/dashboard.js').read_text(encoding='utf-8')
    assert 'r?.choice_options' in js
    assert 'choiceValue(o)' in js
    assert 'choiceLabel(o)' in js
    assert 'roth_irmaa_target_tier' in js
    assert 'roth_target_bracket_rate' in js


def test_admin_ui_choice_renderer_covers_brackets_irmaa_and_schema_type():
    js = (ROOT/'frontend/js/admin.js').read_text(encoding='utf-8')
    assert "['10.00%','12.00%','22.00%','24.00%','32.00%','35.00%','37.00%']" in js
    assert "label==='irmaa_tier2_mfj_base_year'" not in js
    assert "label==='roth_irmaa_target_tier'" in js
    assert "gridChoicesFor(profile,col,row,head)" in js
    assert "if(c==='type')return ['text','choice','boolean'" in js


def test_plan_data_contains_roth_irmaa_tier_choice_row():
    p = ROOT/'input/client_policy.csv'
    if not p.exists():
        pytest.skip('secure complete package excludes input/; run with input overlay for Plan Data assertions')
    with p.open(newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    row = next(r for r in rows if r['section']=='Withdrawal Policy' and r['subsection']=='Roth Conversion' and r['label']=='roth_irmaa_target_tier')
    assert row['units'] == 'choice'
    assert row['value'] == 'TIER_2'
    assert 'TIER_1' in row['notes'] and 'TIER_5' in row['notes']
