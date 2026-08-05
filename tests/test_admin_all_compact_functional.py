from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN_HTML = ROOT / "frontend" / "admin.html"
ADMIN_JS = ROOT / "frontend" / "js" / "admin.js"
ADMIN_ROUTES = ROOT / "src" / "server" / "admin_routes.py"


def test_admin_console_exposes_governance_reference_and_diagnostic_areas_only():
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    for label in [
        "Global optimizer and rebalancing governance",
        "Pricing / market data",
        "ETF universe / replacements",
        "Tax constants and source governance",
        "Workbook build diagnostics",
        "Tax-law update dashboard",
        "Local reports",
    ]:
        assert label in html
    assert "COLUMN_HELPERS" in html
    assert "Compact table view" in html
    assert "Advanced raw CSV" in html


def test_admin_compact_editors_exclude_client_plan_data_files():
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    for file_name in [
        "system_config.csv",
        "security_master.csv",
        "capital_market_assumptions.csv",
        "asset_correlations.csv",
        "tax_constants.csv",
        "state_tax.csv",
    ]:
        assert file_name in html
    for file_name in [
        "target_allocation.csv",
        "asset_class_optimizer_controls.csv",
        "client_policy.csv",
        "client_holdings.csv",
        "client_assets.csv",
        "client_household.csv",
        "client_income.csv",
        "client_spending.csv",
        "client_insurance_estate.csv",
        "client_optional_functions.csv",
    ]:
        assert f"file:'{file_name}'" not in html
    assert "Client-specific Plan Data is read-only here" in html


def test_admin_routes_still_support_reference_csv_and_read_only_local_diagnostics():
    routes = ADMIN_ROUTES.read_text(encoding="utf-8")
    assert "/api/admin/csv-file/<kind>/<path:file_name>" in routes
    assert "admin_diagnostics" in routes
    assert "removed-client-registry" not in routes
    assert "ADMIN_PLAN_DATA_FILES" in routes
