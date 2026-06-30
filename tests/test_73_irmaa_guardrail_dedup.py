from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_user_ui_hides_legacy_irmaa_cap_and_uses_single_guardrail_behavior():
    js = (ROOT / 'frontend/js/dashboard.js').read_text(encoding='utf-8')
    assert "ROTH_IRMAA_LABELS=['irmaa_guardrail_mode','roth_irmaa_target_tier','roth_irmaa_headroom_usage_pct','irmaa_annual_inflator']" in js
    assert "ROTH_LEGACY_IRMAA_LABELS" not in js
    assert "orderedRowsByLabel(['irmaa_guardrail_mode','roth_irmaa_cap'])" not in js
    assert "Use IRMAA Guardrail" not in js


def test_fill_to_irmaa_policy_does_not_duplicate_irmaa_guardrail_rows():
    js = (ROOT / 'frontend/js/dashboard.js').read_text(encoding='utf-8')
    assert "else if(policyIsIrmaa){strategy=orderedRowsByLabel(['roth_irmaa_target_tier','roth_irmaa_headroom_usage_pct','irmaa_annual_inflator',...ROTH_WINDOW_LABELS]);}" in js
    assert "if(!policyIsNone && !policyIsIrmaa)" in js


def test_engine_derives_effective_irmaa_cap_from_guardrail_behavior():
    data_io = (ROOT / 'src/data_io.py').read_text(encoding='utf-8')
    assert "roth_irmaa_cap_legacy_value" not in data_io
    assert "c['roth_irmaa_cap'] = c['irmaa_guardrail_mode'] not in ('IGNORE', 'WARN_ONLY')" in data_io
