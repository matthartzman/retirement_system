from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_withdrawal_page_excludes_roth_and_uses_custom_table():
    js = (ROOT / 'frontend/js/dashboard.js').read_text(encoding='utf-8')
    assert 'case "withdrawal_strategy":\n        return sec === "Withdrawal Policy" && sub !== "roth_conversion";' in js
    assert "renderWithdrawalOrderTable" in js
    assert "Withdrawal order" in js
    assert (
        'const WITHDRAWAL_TYPES = [\n  "RMD",\n  "HSA",\n  "IRA_elective",\n  "Trust",\n  "Roth",\n  "Home_equity_tap",\n];'
        in js
    )
    assert "WITHDRAWAL_OPTIONS" in js


def test_roth_page_uses_collapsible_sections_and_does_not_show_legacy_irmaa_base():
    js = (ROOT / 'frontend/js/dashboard.js').read_text(encoding='utf-8')
    assert 'details class="roth-section"' in js
    assert 'ROTH_ENGINE_LABELS' in js and 'roth_conv_window_end_offset' in js and 'irmaa_annual_inflator' in js
    assert 'irmaa_tier2_mfj_base_year' not in js


def test_hsa_withdrawal_policy_defaults_are_backfilled_and_schema_choices():
    app_core = (ROOT / 'src/server/app_core.py').read_text(encoding='utf-8')
    schema = (ROOT / 'reference_data/schema.csv').read_text(encoding='utf-8')
    assert 'hsa_withdrawal_mode' in app_core
    assert 'spend_as_needed | annual_pct | smooth_window' in app_core
    assert 'HSA Policy,Withdrawals,hsa_withdrawal_mode,choice' in schema
    assert 'HSA Policy,Withdrawals,hsa_annual_spend_pct,percent' in schema


def test_legacy_irmaa_threshold_row_removed_from_user_facing_schema():
    schema = (ROOT / 'reference_data/schema.csv').read_text(encoding='utf-8')
    generated = (ROOT / 'reference_data/generated_schema_coverage.csv').read_text(encoding='utf-8')
    assert 'Model Constants,IRMAA,irmaa_tier2_mfj_base_year' not in schema
    assert 'Model Constants,IRMAA,irmaa_tier2_mfj_base_year' not in generated
