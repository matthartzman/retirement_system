"""The download name root goes into a Content-Disposition header: control characters and quotes must not survive."""
from __future__ import annotations

from src.server_services import report_service


def test_control_characters_and_quotes_are_stripped_from_the_filename_root(tmp_path):
    cfg = tmp_path / "app.db"
    payload, status = report_service.save_workbook_download_settings(
        {"filename_root": "Plan\"\r\nSet-Cookie: x=1\r\n\r\n<b>\\/"}, cfg)
    assert status == 200
    root = payload["filename_root"]
    assert not any(c in root for c in "\r\n\"\\/\x00") and root.strip()


def test_a_root_that_is_only_control_characters_is_refused(tmp_path):
    payload, status = report_service.save_workbook_download_settings({"filename_root": "\r\n\x00"}, tmp_path / "app.db")
    assert status == 400
