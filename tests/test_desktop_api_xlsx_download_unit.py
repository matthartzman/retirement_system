"""Ticket <workbook-filename>: the desktop app's generic binary-download
fallback used to write every workbook to a random OS temp file
(tempfile.NamedTemporaryFile) and open it via os.startfile -- the file was
never saved anywhere the user could find it again, and Excel's title bar
showed the cryptic temp name. _convert() now saves an .xlsx response under
its real Content-Disposition filename in the configured (or default
Downloads) folder instead.

DesktopApi.__init__() builds a full Flask app/test client, which _convert()
doesn't need -- these tests construct a bare instance via __new__ to keep
this focused and fast, matching the "pure function under test" scope the
method actually has once you set aside the JS-bridge plumbing around it.
"""
from pathlib import Path
from unittest.mock import patch

import pytest


def _bare_desktop_api():
    from src.desktop_api import DesktopApi

    return object.__new__(DesktopApi)


class _FakeResponse:
    def __init__(self, content_type: str, data: bytes, filename: str, status_code: int = 200):
        self.content_type = content_type
        self._data = data
        self.status_code = status_code
        self.headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

    def get_data(self) -> bytes:
        return self._data


def test_xlsx_response_is_saved_under_its_real_filename_in_the_default_folder(tmp_path, monkeypatch):
    from src import system_config

    monkeypatch.setattr(system_config, "load_system_config", lambda *a, **k: {})
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    api = _bare_desktop_api()
    resp = _FakeResponse(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        b"fake xlsx bytes",
        "Retirement Workbook 20260910 1432.xlsx",
    )
    with patch.object(api, "_open_path") as mock_open:
        result = api._convert(resp)

    dest = downloads / "Retirement Workbook 20260910 1432.xlsx"
    assert dest.exists()
    assert dest.read_bytes() == b"fake xlsx bytes"
    assert result == {"success": True, "opened": True, "path": str(dest)}
    mock_open.assert_called_once_with(dest)


def test_xlsx_response_uses_the_configured_folder_when_valid(tmp_path, monkeypatch):
    from src import system_config

    configured = tmp_path / "MyReports"
    configured.mkdir()
    monkeypatch.setattr(
        system_config,
        "load_system_config",
        lambda *a, **k: {"System Configuration": {"Downloads": {"desktop_download_folder": str(configured)}}},
    )

    api = _bare_desktop_api()
    resp = _FakeResponse("application/vnd.ms-excel", b"bytes", "Retirement Workbook 20260910 1432.xlsx")
    with patch.object(api, "_open_path") as mock_open:
        result = api._convert(resp)

    dest = configured / "Retirement Workbook 20260910 1432.xlsx"
    assert dest.exists()
    assert result["path"] == str(dest)
    mock_open.assert_called_once_with(dest)


def test_xlsx_response_falls_back_to_downloads_when_configured_folder_is_invalid(tmp_path, monkeypatch):
    from src import system_config

    monkeypatch.setattr(
        system_config,
        "load_system_config",
        lambda *a, **k: {"System Configuration": {"Downloads": {"desktop_download_folder": str(tmp_path / "does_not_exist")}}},
    )
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    api = _bare_desktop_api()
    resp = _FakeResponse("application/vnd.ms-excel", b"bytes", "Retirement Workbook 20260910 1432.xlsx")
    with patch.object(api, "_open_path"):
        result = api._convert(resp)

    assert result["path"] == str(downloads / "Retirement Workbook 20260910 1432.xlsx")


def test_non_xlsx_binary_response_still_uses_the_old_tempfile_fallback(monkeypatch):
    api = _bare_desktop_api()
    resp = _FakeResponse("application/pdf", b"pdf bytes", "report.pdf")
    with patch.object(api, "_open_path") as mock_open:
        result = api._convert(resp)

    assert result["success"] is True
    assert result["opened"] is True
    assert "path" not in result  # unchanged behavior: no path reported for the tempfile fallback
    (opened_path,), _ = mock_open.call_args
    assert opened_path.suffix == ".pdf"
    assert opened_path.read_bytes() == b"pdf bytes"


def test_json_and_text_responses_are_unaffected():
    api = _bare_desktop_api()
    resp = _FakeResponse("application/json", b'{"success": true, "value": 1}', "")
    assert api._convert(resp) == {"success": True, "value": 1}
