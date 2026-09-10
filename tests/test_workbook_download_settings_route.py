from pathlib import Path

from src.server import app
import src.server.workbook_routes as workbook_routes


HEADERS = {"X-User-Role": "admin"}


def _write_bytes(path: Path, payload: bytes = b"fake xlsx") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def test_xlsx_download_sends_a_real_filename_via_content_disposition(monkeypatch, tmp_path):
    output = tmp_path / "output"
    _write_bytes(output / "retirement_plan.xlsx")
    monkeypatch.setattr(workbook_routes, "_workspace_output", lambda: output)
    monkeypatch.setenv("RETIREMENT_SYSTEM_SYSTEM_CONFIG_CSV", str(tmp_path / "system_config.csv"))

    client = app.test_client()
    response = client.get("/api/xlsx", headers=HEADERS)

    assert response.status_code == 200
    disposition = response.headers.get("Content-Disposition", "")
    assert "retirement_plan.xlsx" not in disposition
    assert "Retirement Workbook" in disposition
    assert ".xlsx" in disposition


def test_workbook_download_settings_get_returns_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("RETIREMENT_SYSTEM_SYSTEM_CONFIG_CSV", str(tmp_path / "system_config.csv"))
    client = app.test_client()
    response = client.get("/api/settings/workbook-download", headers=HEADERS)
    assert response.status_code == 200
    body = response.get_json()
    assert body["filename_root"] == "Retirement Workbook"
    assert body["desktop_download_folder"] == ""


def test_workbook_download_settings_post_persists_and_affects_the_download_name(monkeypatch, tmp_path):
    monkeypatch.setenv("RETIREMENT_SYSTEM_SYSTEM_CONFIG_CSV", str(tmp_path / "system_config.csv"))
    output = tmp_path / "output"
    _write_bytes(output / "retirement_plan.xlsx")
    monkeypatch.setattr(workbook_routes, "_workspace_output", lambda: output)
    client = app.test_client()

    post = client.post(
        "/api/settings/workbook-download",
        json={"filename_root": "Smith Family Plan", "desktop_download_folder": "D:/Reports"},
        headers=HEADERS,
    )
    assert post.status_code == 200
    assert post.get_json()["filename_root"] == "Smith Family Plan"

    get_again = client.get("/api/settings/workbook-download", headers=HEADERS)
    assert get_again.get_json() == {
        "success": True,
        "filename_root": "Smith Family Plan",
        "desktop_download_folder": "D:/Reports",
    }

    download = client.get("/api/xlsx", headers=HEADERS)
    assert "Smith Family Plan" in download.headers.get("Content-Disposition", "")


def test_workbook_download_settings_post_rejects_blank_filename_root(monkeypatch, tmp_path):
    monkeypatch.setenv("RETIREMENT_SYSTEM_SYSTEM_CONFIG_CSV", str(tmp_path / "system_config.csv"))
    client = app.test_client()
    response = client.post("/api/settings/workbook-download", json={"filename_root": "   "}, headers=HEADERS)
    assert response.status_code == 400
    assert response.get_json()["success"] is False
