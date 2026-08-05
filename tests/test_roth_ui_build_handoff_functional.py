from pathlib import Path

from src.roth_ui_build_guard import (
    canonicalize_roth_csv_content,
    is_explicit_user_roth_policy,
    normalize_irmaa_guardrail_mode,
    normalize_percent_display,
    normalize_roth_policy,
    percent_to_float,
    strategy_for_roth_policy,
)

ROOT = Path(__file__).resolve().parents[1]


def test_roth_ui_values_normalize_to_engine_values():
    assert normalize_roth_policy("Fill to 22% bracket") == "fill_to_bracket"
    assert normalize_roth_policy("Optimizer chooses") == "optimize_terminal_tax"
    assert normalize_irmaa_guardrail_mode("Warn only") == "WARN_ONLY"
    assert normalize_percent_display("22% bracket — top $201,050 taxable income") == "22.00%"
    assert percent_to_float("22.00%") == 0.22
    assert is_explicit_user_roth_policy("fill_to_bracket")
    assert strategy_for_roth_policy("fill_to_bracket") == "FILL_TARGET_BRACKET"


def test_roth_csv_content_is_canonicalized_before_storage():
    csv_text = "section,subsection,label,value,units,notes\nWithdrawal Policy,Roth Conversion,roth_conversion_policy,Fill to 22% bracket,choice,\nWithdrawal Policy,Roth Conversion,roth_target_bracket_rate,22% bracket,choice,\nWithdrawal Policy,Roth Conversion,irmaa_guardrail_mode,Warn only,choice,\n"
    out = canonicalize_roth_csv_content(csv_text)
    assert ",roth_conversion_policy,fill_to_bracket," in out
    assert ",roth_target_bracket_rate,22.00%," in out
    assert ",irmaa_guardrail_mode,WARN_ONLY," in out




def test_engine_parse_uses_roth_handoff_helpers():
    src = (ROOT / "src/data_io.py").read_text(encoding="utf-8")
    assert "normalize_roth_policy" in src
    assert "percent_to_float" in src
    assert "normalize_irmaa_guardrail_mode" in src
    assert "roth_policy_lock" in src





def test_api_build_disables_command_line_local_plan_data_resync():
    routes = (ROOT / "src/server/workbook_routes.py").read_text(encoding="utf-8")
    assert routes.count('RETIREMENT_SYSTEM_SKIP_PLAN_DATA_ENV_SYNC') >= 2
    sync = (ROOT / "src/local_plan_data_sync.py").read_text(encoding="utf-8")
    assert 'RETIREMENT_SYSTEM_SKIP_PLAN_DATA_ENV_SYNC' in sync
    assert 'return None' in sync


def test_external_plan_data_path_save_canonicalizes_roth_controls():
    routes = (ROOT / "src/server/app_core.py").read_text(encoding="utf-8")
    assert "canonicalize_roth_csv_content" in routes
