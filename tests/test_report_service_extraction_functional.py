from pathlib import Path
import json

# The "service exists" + "routes delegate" checks that used to live here are
# generalized (system review 2026-07-21, Q6) into SERVICE_ROUTE_PAIRS in
# test_service_extraction_functional.py, alongside every other extracted service's
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


def test_workbook_download_filename_uses_default_root_and_timestamp(tmp_path):
    import datetime
    from src.server_services import report_service

    config_path = tmp_path / "system_config.csv"  # does not exist -> defaults
    name = report_service.workbook_download_filename(
        now=datetime.datetime(2026, 9, 10, 14, 32), config_path=config_path
    )
    assert name == "Retirement Workbook 20260910 1432.xlsx"


def test_workbook_download_filename_uses_configured_root(tmp_path):
    import datetime
    from src.system_config import upsert_system_setting
    from src.server_services import report_service

    config_path = tmp_path / "system_config.csv"
    upsert_system_setting(config_path, "Downloads", "filename_root", "Smith Family Plan")
    name = report_service.workbook_download_filename(
        now=datetime.datetime(2026, 1, 2, 9, 5), config_path=config_path
    )
    assert name == "Smith Family Plan 20260102 0905.xlsx"


def test_workbook_download_settings_round_trip(tmp_path):
    from src.server_services import report_service

    config_path = tmp_path / "system_config.csv"
    payload = report_service.workbook_download_settings_payload(config_path)
    assert payload == {
        "success": True,
        "filename_root": "Retirement Workbook",
        "desktop_download_folder": "",
    }

    saved, status = report_service.save_workbook_download_settings(
        {"filename_root": "My Plan", "desktop_download_folder": "D:/Reports"}, config_path
    )
    assert status == 200
    assert saved["filename_root"] == "My Plan"
    assert saved["desktop_download_folder"] == "D:/Reports"

    reread = report_service.workbook_download_settings_payload(config_path)
    assert reread == saved


def test_save_workbook_download_settings_rejects_blank_filename_root(tmp_path):
    from src.server_services import report_service

    config_path = tmp_path / "system_config.csv"
    payload, status = report_service.save_workbook_download_settings({"filename_root": "   "}, config_path)
    assert status == 400
    assert payload["success"] is False
