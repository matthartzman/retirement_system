from pathlib import Path

from src.roth_ui_build_guard import (
    canonicalize_roth_rows,
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


def test_roth_controls_are_canonicalized_in_the_plan_rows_before_storage():
    from src.stores import PlanStore

    with PlanStore.open() as store:
        store.set_value("Withdrawal Policy", "Roth Conversion", "roth_conversion_policy", "Fill to 22% bracket")
        store.set_value("Withdrawal Policy", "Roth Conversion", "roth_target_bracket_rate", "22% bracket")
        store.set_value("Withdrawal Policy", "Roth Conversion", "irmaa_guardrail_mode", "Warn only")
        assert canonicalize_roth_rows(store) == 3
        roth = store.sectioned_data()["Withdrawal Policy"]["Roth Conversion"]
        assert roth == {"roth_conversion_policy": "fill_to_bracket", "roth_target_bracket_rate": "22.00%",
                        "irmaa_guardrail_mode": "WARN_ONLY"}


def test_engine_parse_uses_roth_handoff_helpers():
    src = (ROOT / "src/data_io.py").read_text(encoding="utf-8")
    assert "normalize_roth_policy" in src
    assert "percent_to_float" in src
    assert "normalize_irmaa_guardrail_mode" in src
    # roth_policy_lock itself is set in src/parsing/roth_conversion_policy.py
    # (ticket 312 extraction) rather than inline in src/data_io.py; data_io
    # still re-exports parse_roth_conversion_policy for backward compat.
    roth_policy_module = (ROOT / "src/parsing/roth_conversion_policy.py").read_text(encoding="utf-8")
    assert "roth_policy_lock" in roth_policy_module





def test_api_build_reads_the_servers_plan_file_and_no_plan_folder_is_synced_before_a_build():
    routes = (ROOT / "src/server/workbook_routes.py").read_text(encoding="utf-8")
    assert routes.count("plan_db_env(env)") >= 2  # the build subprocess reads the server's plan file
    assert "SKIP_PLAN_DATA_ENV_SYNC" not in routes and not (ROOT / "src/local_plan_data_sync.py").exists()


def test_every_plan_write_path_canonicalizes_roth_controls_in_the_rows():
    active = (ROOT / "src/active_plan.py").read_text(encoding="utf-8")
    assert "canonicalize_roth_rows(store)" in active
