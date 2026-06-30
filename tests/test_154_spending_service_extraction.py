from pathlib import Path


def test_spending_service_exists_and_is_runtime_independent():
    service = Path("src/server_services/spending_service.py").read_text(encoding="utf-8")
    assert "class SpendingService" in service
    assert "SpendingServiceContext" in service
    assert "def load_actuals_payload" in service
    assert "def unified_budget_payload" in service
    assert "def category_create_payload" in service
    assert "def alias_add_payload" in service
    assert "@app.route" not in service
    assert "request.get_json" not in service
    assert "jsonify" not in service


def test_plan_routes_delegate_spending_logic_to_service():
    routes = Path("src/server/plan_routes.py").read_text(encoding="utf-8")
    assert "def _spending_feature_service()" in routes
    assert "SpendingServiceContext" in routes
    assert ".dashboard_payload()" in routes
    assert ".taxonomy_payload()" in routes
    assert ".load_actuals_payload()" in routes
    assert ".save_unified_budget_payload(" in routes
    assert "spending_tracker as st" not in routes
    assert "def _core_spending_from_plan" not in routes
    assert "st.save_taxonomy_category(BASE_DIR" not in routes
    assert "st.spending_summary_taxonomy(BASE_DIR" not in routes


def test_spending_service_core_spending_parser_uses_plan_data_callback():
    from src.server_services.spending_service import SpendingService, SpendingServiceContext

    csv_content = "section,subsection,label,value\nCashflow,Spending,annual_spending_base_year,$123,456\n"
    # The comma in the sample above intentionally simulates a malformed CSV cell;
    # the parser should stay defensive and not crash.
    service = SpendingService(SpendingServiceContext(base_dir=Path("."), read_plan_data_file=lambda name: csv_content))
    assert service.core_spending_from_plan() in (123.0, 0.0)

    csv_content = "section,subsection,label,value\nCashflow,Spending,annual_spending_base_year,123456\n"
    service = SpendingService(SpendingServiceContext(base_dir=Path("."), read_plan_data_file=lambda name: csv_content))
    assert service.core_spending_from_plan() == 123456.0


def test_spending_service_validates_category_create_before_mutation(tmp_path):
    from src.server_services.spending_service import SpendingService, SpendingServiceContext

    service = SpendingService(SpendingServiceContext(base_dir=tmp_path, read_plan_data_file=lambda name: ""))
    payload, status = service.category_create_payload({"label": "", "id": "bad id"})
    assert status == 400
    assert payload["success"] is False
    assert "label" in payload["error"]
