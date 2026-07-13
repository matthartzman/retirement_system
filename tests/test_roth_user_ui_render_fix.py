from pathlib import Path
import csv
import pytest

ROOT = Path(__file__).resolve().parents[1]

ROTH_PRIMARY = {
    'roth_conversion_policy',
    'roth_objective_mode',
    'estate_tax_objective_mode',
    'roth_headroom_usage_pct',
    'roth_target_bracket_rate',
    'roth_irmaa_target_tier',
    'irmaa_guardrail_mode',
    'roth_irmaa_headroom_usage_pct',
    'roth_fixed_annual_amount',
}


def _norm(s: str) -> str:
    import re
    return re.sub(r'[^a-z0-9]+', '_', str(s or '').lower()).strip('_')


def test_user_ui_roth_step_matches_normalized_subsection_names():
    js = (ROOT / 'frontend/js/dashboard.js').read_text(encoding='utf-8')
    assert 'case "roth_conversion"' in js
    # rowsForStep() normalizes subsection names before comparison. Comparing to
    # title-case values made only forced-conversion rows visible.
    assert '(sec === "Withdrawal Policy" &&' in js
    assert 'sec === "Model Constants" && sub === "roth_conversion"' in js
    assert 'sec === "Model Constants" &&\n            sub === "irmaa"' in js
    assert "sub==='Roth Conversion'" not in js


def test_input_package_contains_all_primary_roth_controls_with_defaults():
    p = ROOT / 'input' / 'client_policy.csv'
    if not p.exists():
        pytest.skip('secure complete package excludes input/; run with input overlay for Plan Data assertions')
    with p.open(newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    labels = {
        r['label'] for r in rows
        if r['section'] == 'Withdrawal Policy' and r['subsection'] == 'Roth Conversion'
    }
    assert ROTH_PRIMARY <= labels
    defaults = {r['label']: r['value'] for r in rows if r['section'] == 'Withdrawal Policy' and r['subsection'] == 'Roth Conversion'}
    assert defaults['roth_objective_mode'] == 'MAXIMIZE_TERMINAL_NET_WORTH'
    assert defaults['estate_tax_objective_mode'] == 'BALANCED'
    assert defaults['roth_headroom_usage_pct'] == '100.00%'
    assert defaults['roth_irmaa_headroom_usage_pct'] == '100.00%'
    assert defaults['roth_irmaa_target_tier'] == 'TIER_2'


def test_roth_step_filter_would_return_controls_from_input_rows():
    p = ROOT / 'input' / 'client_policy.csv'
    if not p.exists():
        pytest.skip('secure complete package excludes input/; run with input overlay for Plan Data assertions')
    with p.open(newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    ui_rows = [
        r for r in rows
        if (r['section'] == 'Withdrawal Policy' and _norm(r['subsection']) == 'roth_conversion')
        or (r['section'] == 'Model Constants' and _norm(r['subsection']) in {'roth_conversion', 'irmaa'})
        or (r['section'] == 'Forced Actions' and 'roth' in _norm(r['label']))
    ]
    labels = {r['label'] for r in ui_rows}
    assert ROTH_PRIMARY <= labels
    assert 'roth_conversion_wife_ira_to_roth' not in labels
    assert len(ui_rows) >= 15
