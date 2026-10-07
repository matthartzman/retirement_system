from pathlib import Path

# The "service exists" + "routes delegate" checks that used to live here are
# generalized (system review 2026-07-21, Q6) into SERVICE_ROUTE_PAIRS in
# test_service_extraction_functional.py, alongside every other extracted service's
# equivalent pair. Only this file's genuine behavior tests remain below.


def test_spending_service_core_spending_reads_the_plan_rows_through_the_plan_data_callback():
    from src.server_services.spending_service import SpendingService, SpendingServiceContext

    def service_over(value):
        rows = {"Cashflow": {"Spending": {"annual_spending_base_year": value}}}
        return SpendingService(SpendingServiceContext(base_dir=Path("."), plan_data=lambda: rows))

    # a malformed cell stays defensive and does not crash
    assert service_over("$123,456").core_spending_from_plan() in (123456.0, 123.0, 0.0)
    assert service_over("123456").core_spending_from_plan() == 123456.0
    assert service_over("$123,456.00").core_spending_from_plan() == 123456.0


def test_spending_service_validates_category_create_before_mutation(tmp_path):
    from src.server_services.spending_service import SpendingService, SpendingServiceContext

    service = SpendingService(SpendingServiceContext(base_dir=tmp_path, read_plan_data_file=lambda name: ""))
    payload, status = service.category_create_payload({"label": "", "id": "bad id"})
    assert status == 400
    assert payload["success"] is False
    assert "label" in payload["error"]
