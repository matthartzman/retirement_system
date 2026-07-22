from pathlib import Path

# The "service exists" + "routes delegate" checks that used to live here are
# generalized (system review 2026-07-21, Q6) into SERVICE_ROUTE_PAIRS in
# test_126_service_extraction.py, alongside every other extracted service's
# equivalent pair. Only this file's genuine behavior tests remain below.


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
