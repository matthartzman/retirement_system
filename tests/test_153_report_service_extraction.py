from pathlib import Path
import json


def test_report_service_exists_and_is_runtime_independent():
    service = Path("src/server_services/report_service.py").read_text(encoding="utf-8")
    assert "def detailed_results_payload" in service
    assert "def downloadable_artifact" in service
    assert "def read_history_payload" in service
    assert "def append_history_payload" in service
    assert "def local_output_file_payload" in service
    assert "@app.route" not in service
    assert "request.args" not in service
    assert "jsonify" not in service
    assert "send_file" not in service


def test_workbook_routes_delegate_report_and_history_logic_to_service():
    routes = Path("src/server/workbook_routes.py").read_text(encoding="utf-8")
    assert "report_service.detailed_results_payload(" in routes
    assert "report_service.downloadable_artifact(" in routes
    assert "report_service.read_history_payload(" in routes
    assert "report_service.append_history_payload(" in routes
    assert "report_service.local_output_file_payload(" in routes
    assert "def _history_path" not in routes
    assert "workbook_detailed_results" not in routes
    assert "workbook_detailed_index" not in routes
    assert "workbook_detailed_sheet" not in routes


def test_report_service_history_contract_round_trips(tmp_path):
    from src.server_services import report_service

    payload, status = report_service.read_history_payload(tmp_path)
    assert status == 200
    assert payload == []

    payload, status = report_service.append_history_payload(tmp_path, {"run": 1})
    assert status == 200
    assert payload["success"] is True
    assert payload["count"] == 1

    payload, status = report_service.read_history_payload(tmp_path)
    assert status == 200
    assert payload == [{"run": 1}]
    assert json.loads((tmp_path / "run_history.json").read_text(encoding="utf-8")) == [{"run": 1}]


def test_report_service_local_output_file_security(tmp_path):
    from src.server_services import report_service

    good = tmp_path / "report.txt"
    good.write_text("ok", encoding="utf-8")
    payload, status = report_service.local_output_file_payload(tmp_path, "report.txt")
    assert status == 200
    assert payload["success"] is True

    payload, status = report_service.local_output_file_payload(tmp_path, "../report.txt")
    assert status == 403
    assert payload["success"] is False
