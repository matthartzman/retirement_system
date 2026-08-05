from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_core_spending_page_has_inline_growth_controls_without_extra_heading():
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    assert "coreSpendingGrowthPanel" not in js
    assert "Use CPI / General Inflation" in js
    assert "Manual spending increase override" in js
    assert "Core Spending Base" in js
    assert "Core Spending Increase Stops" in js
    assert "Core Spending Increase Method" in js
    assert "Stop Increasing Core Spending After Year" not in js
    assert "Annual Spending Base Year" not in js


def test_backend_materializes_forward_schema_rows_on_sync_and_load():
    app_core = (ROOT / "src/server/app_core.py").read_text(encoding="utf-8")
    workbook_routes = (ROOT / "src/server/workbook_routes.py").read_text(encoding="utf-8")
    assert "def _ensure_user_ui_plan_data_rows" in app_core
    assert "core_spending_growth_mode" in app_core
    assert "core_spending_manual_growth_rate" in app_core
    assert "_ensure_user_ui_plan_data_rows()" in workbook_routes


def test_core_spending_tokens_in_dashboard():
    a = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    for token in ["Core Spending Base", "Core Spending Increase Stops", "core_spending_growth_mode", "core_spending_manual_growth_rate"]:
        assert token in a
