from pathlib import Path
import json

# The "service exists" + "routes delegate" checks that used to live here are
# generalized (system review 2026-07-21, Q6) into SERVICE_ROUTE_PAIRS in
# test_126_service_extraction.py, alongside every other extracted service's
# equivalent pair. Only this file's genuine behavior tests remain below.


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
