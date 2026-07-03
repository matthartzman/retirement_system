from __future__ import annotations
"""Phase 2 (Android app shell): src/android_api.py — the third transport onto
the same local route registry src/desktop_api.py uses, adapted for the
Chaquopy/WebView bridge (base64 binary payloads, configure()-driven workspace
root + mobile platform flag instead of PyWebView window/file-dialog calls).
"""

import base64
import json
import os

import pytest

import src.android_api as android_api
import src.platform_runtime as platform_runtime


@pytest.fixture(autouse=True)
def _reset_android_api():
    # android_api.configure() writes os.environ directly (that's the whole
    # point — it's what a real Chaquopy host would do), so cleanup here uses
    # plain os.environ save/restore rather than monkeypatch.setenv/delenv:
    # monkeypatch's own undo stack would otherwise replay a *restore* of
    # whatever delenv captured mid-test, re-leaking the workspace-root
    # override into every test that runs afterward in the same process.
    android_api._instance = None
    saved = {
        platform_runtime.PLATFORM_ENV: os.environ.pop(platform_runtime.PLATFORM_ENV, None),
        platform_runtime.WORKSPACE_ROOT_ENV: os.environ.pop(platform_runtime.WORKSPACE_ROOT_ENV, None),
    }
    yield
    android_api._instance = None
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_configure_sets_mobile_platform_and_workspace_root(tmp_path):
    android_api.configure(str(tmp_path))
    assert platform_runtime.platform_name() == "android"
    assert platform_runtime.is_mobile() is True
    assert platform_runtime.workspace_root() == tmp_path
    # This is what makes the Phase 0 BuildRunner pick the in-process path
    # with zero Android-specific build code.
    assert platform_runtime.build_mode() == "inprocess"


def test_get_api_returns_a_process_lifetime_singleton(tmp_path):
    android_api.configure(str(tmp_path))
    api1 = android_api.get_api()
    api2 = android_api.get_api()
    assert api1 is api2
    assert isinstance(api1, android_api.AndroidApi)


def test_request_dispatches_get_through_the_route_registry(tmp_path):
    android_api.configure(str(tmp_path))
    result = android_api.get_api().request("GET", "/api/runtime")
    assert result.get("success") is not False


def test_request_json_round_trips_the_same_result(tmp_path):
    android_api.configure(str(tmp_path))
    api = android_api.get_api()
    direct = api.request("GET", "/api/runtime")
    via_json = json.loads(api.request_json("GET", "/api/runtime"))
    assert via_json == direct


def test_request_rejects_unsupported_method(tmp_path):
    android_api.configure(str(tmp_path))
    result = android_api.get_api().request("PURGE", "/api/runtime")
    assert result == {"success": False, "error": "Unsupported method: PURGE"}


def test_shutdown_urls_short_circuit_without_hitting_the_route_registry(tmp_path):
    android_api.configure(str(tmp_path))
    api = android_api.get_api()
    assert api.request("POST", "/api/shutdown") == {"success": True}
    assert api.request("POST", "/api/admin/server/shutdown") == {"success": True}


class _FakeResponse:
    def __init__(self, status_code, content_type, data, headers=None):
        self.status_code = status_code
        self.content_type = content_type
        self._data = data
        self.headers = headers or {}

    def get_data(self):
        return self._data


def test_convert_json_response(tmp_path):
    android_api.configure(str(tmp_path))
    api = android_api.get_api()
    resp = _FakeResponse(200, "application/json", b'{"success": true, "x": 1}')
    assert api._convert(resp) == {"success": True, "x": 1}


def test_convert_text_response(tmp_path):
    android_api.configure(str(tmp_path))
    api = android_api.get_api()
    resp = _FakeResponse(200, "text/csv", b"a,b\n1,2\n")
    result = api._convert(resp)
    assert result["success"] is True
    assert result["_text"] == "a,b\n1,2\n"
    assert result["_content_type"] == "text/csv"


def test_convert_binary_response_base64_encodes_and_captures_filename(tmp_path):
    android_api.configure(str(tmp_path))
    api = android_api.get_api()
    raw = b"\x00\x01binarydata"
    resp = _FakeResponse(
        200,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        raw,
        headers={"Content-Disposition": 'attachment; filename="plan.xlsx"'},
    )
    result = api._convert(resp)
    assert result["success"] is True
    assert base64.b64decode(result["_binary"]) == raw
    assert result["_filename"] == "plan.xlsx"


def test_convert_server_error_returns_json_body(tmp_path):
    android_api.configure(str(tmp_path))
    api = android_api.get_api()
    resp = _FakeResponse(500, "application/json", b'{"success": false, "error": "boom"}')
    assert api._convert(resp) == {"success": False, "error": "boom"}
