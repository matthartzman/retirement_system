from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_core_spending_step_has_growth_mode_and_relevant_rates():
    js = (ROOT / 'frontend/js/dashboard.js').read_text(encoding="utf-8")
    assert "core_spending_growth_mode" in js
    assert "core_spending_manual_growth_rate" in js
    assert "coreSpendingGrowthMode" in js
    assert 'mode === "manual_override"\n      ? [\n          "core_spending_growth_mode",\n          "annual_spending_base_year",\n          "spending_freeze_year",\n          "core_spending_manual_growth_rate"' in js
    assert ': [\n          "core_spending_growth_mode",\n          "annual_spending_base_year",\n          "spending_freeze_year",\n          "inflation_general"' in js


def test_clean_forward_schema_removed_old_roth_and_planned_spending_aliases():
    schema = (ROOT / 'reference_data/schema.csv').read_text(encoding="utf-8")
    data_io = (ROOT / 'src/data_io.py').read_text(encoding="utf-8")
    app_core = (ROOT / 'src/server/app_core.py').read_text(encoding="utf-8")
    assert 'roth_conversion_target_bracket_base_year' not in schema
    assert 'roth_conversion_target_bracket_base_year' not in data_io
    assert 'roth_conversion_target_bracket_base_year' not in app_core
    assert 'roth_irmaa_cap,boolean' not in schema
    assert 'Travel & Extras' not in data_io
    assert 'Travel & Extras' not in app_core


def test_spending_growth_engine_uses_manual_factor_for_core_spending_only():
    engine = (ROOT / 'src/planning_engines.py').read_text(encoding="utf-8")
    assert "def _spending_factor(year):" in engine
    assert "core_spending_growth_mode') == 'manual_override'" in engine
    assert "spend = c['spend_base'] * _spending_factor(year)" in engine
    assert "spend = c['spend_base'] * _spending_factor(c['spending_freeze_yr'])" in engine


def test_summary_exposes_spending_assumptions_heard():
    builder = (ROOT / 'src/reporting/workbook_builder.py').read_text(encoding="utf-8")
    assert 'def _build_spending_heard(c):' in builder
