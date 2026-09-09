from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from tests._decomp_dashboard import dashboard_js_text


def test_user_ui_hides_legacy_irmaa_cap_and_uses_single_guardrail_behavior():
    js = dashboard_js_text()
    assert (
        'const ROTH_IRMAA_LABELS = [\n  "irmaa_guardrail_mode",\n  "roth_irmaa_target_tier",\n  "roth_irmaa_headroom_usage_pct",\n  "irmaa_annual_inflator",\n];'
        in js
    )
    assert "ROTH_LEGACY_IRMAA_LABELS" not in js
    assert "orderedRowsByLabel(['irmaa_guardrail_mode','roth_irmaa_cap'])" not in js
    assert "Use IRMAA Guardrail" not in js


def test_fill_to_irmaa_policy_does_not_duplicate_irmaa_guardrail_rows():
    js = dashboard_js_text()
    assert (
        '} else if (policyIsIrmaa) {\n    strategy = orderedRowsByLabel([\n      "roth_irmaa_target_tier",\n      "roth_irmaa_headroom_usage_pct",\n      "irmaa_annual_inflator",\n      ...ROTH_WINDOW_LABELS,\n    ]);'
        in js
    )
    assert "if (!policyIsNone && !policyIsIrmaa)" in js


def test_engine_derives_effective_irmaa_cap_from_guardrail_behavior():
    # Ticket 312: this logic moved into src/parsing/roth_conversion_policy.py
    # when parse_client()'s Roth Conversion Policy section was extracted.
    src = (ROOT / 'src/parsing/roth_conversion_policy.py').read_text(encoding='utf-8')
    assert "roth_irmaa_cap_legacy_value" not in src
    assert "out['roth_irmaa_cap'] = out['irmaa_guardrail_mode'] not in ('IGNORE', 'WARN_ONLY')" in src
