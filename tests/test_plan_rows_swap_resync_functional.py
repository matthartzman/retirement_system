"""WP4.2: Save As / Load Saved Plan keep the plan rows the build reads in step.

The engine and the build read the active plan file's rows. Load Saved Plan swaps the
legacy database and rebuilds the CSV set from its ``client_files``; the plan rows must
follow, or a build after a load would still see the plan from before the load.
"""
from __future__ import annotations

import pytest

import src.server.app_core as app_core
from src.config_backend import load_active_config
from src.server import app
from tests.plan_fixture import make_plan

HEADERS = {"X-User-Role": "admin"}
KEY = ("Other Assets", "Home", "value_as_of_plan_start")


def _row(client):
    rows = client.get("/api/config/rows", headers=HEADERS).get_json()["rows"]
    return next(r for r in rows if (r["section"], r["subsection"], r["label"]) == KEY)


def _save(client, row_index, value):
    resp = client.post("/api/config/rows", headers=HEADERS,
                       json={"updates": [{"row_index": row_index, "value": value}], "sync": True})
    assert resp.status_code == 200 and resp.get_json()["success"] is True, resp.get_data(as_text=True)


def _active_value():
    data, _ = load_active_config()
    return data[KEY[0]][KEY[1]][KEY[2]]


@pytest.fixture
def own_workspace(tmp_path, monkeypatch):
    """A workspace of this test's own: Load Saved Plan replaces the legacy database
    file, which Windows refuses while another test process has the shared session
    database open."""
    ws = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(ws.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.setattr(app_core, "CSV_PATH", ws.input_dir / "client_data.csv")
    assert app_core._sync_config_backends()["success"] is True  # creates the legacy database
    return ws


def test_load_saved_plan_brings_the_plan_rows_back_to_the_saved_plan(own_workspace, tmp_path):
    client = app.test_client()
    row = _row(client)
    original = row["value"]
    saved_file = tmp_path / "saved_plan.rpx"
    resp = client.post("/api/plan/save-as", headers=HEADERS, json={"path": str(saved_file)})
    assert resp.get_json()["success"] is True and saved_file.is_file()

    _save(client, row["row_index"], "$1,234,567")
    assert _active_value().replace(",", "").replace("$", "") == "1234567"

    resp = client.post("/api/plan/load-file", headers=HEADERS, json={"path": str(saved_file)})
    payload = resp.get_json()
    assert payload["success"] is True, payload
    assert "sync_warning" not in payload
    assert _active_value() == original, "the build would still read the plan from before the load"
    assert _row(client)["value"] == original
