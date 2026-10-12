"""WP9.3: /api/import/preview|commit and /api/export/<dataset|plan-set> over csv_exchange."""
from __future__ import annotations

import base64
import io
import zipfile

import pytest

from src.server import app
from tests.plan_fixture import make_plan

HEADERS = {"X-User-Role": "admin"}
HOLDINGS = "account,symbol,purchase_date,shares,purchase_price,lot_type,note\nIRA,ZZZQ,2020-01-01,10,100,,\n"


@pytest.fixture
def client(tmp_path, monkeypatch):
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    return app.test_client()


def test_preview_does_not_write_and_commit_does(client):
    body = {"dataset": "holdings", "csv_text": HOLDINGS}
    prev = client.post("/api/import/preview", headers=HEADERS, json=body).get_json()
    assert prev["success"] and prev["committed"] is False and prev["preview"]["rows_incoming"] == 1
    assert "ZZZQ" not in client.get("/api/export/holdings", headers=HEADERS).get_data(as_text=True)
    done = client.post("/api/import/commit", headers=HEADERS, json=body).get_json()
    assert done["committed"] is True
    assert "ZZZQ" in client.get("/api/export/holdings", headers=HEADERS).get_data(as_text=True)


def test_plan_set_zip_round_trip_and_errors(client):
    resp = client.get("/api/export/plan-set", headers=HEADERS)
    assert resp.status_code == 200 and resp.mimetype == "application/zip"
    assert zipfile.ZipFile(io.BytesIO(resp.get_data())).namelist()
    b64 = base64.b64encode(resp.get_data()).decode()
    out = client.post("/api/import/commit", headers=HEADERS, json={"dataset": "plan-set", "zip_base64": b64}).get_json()
    assert out["success"] and out["errors"] == 0
    assert client.get("/api/export/nope", headers=HEADERS).status_code == 404
    assert client.post("/api/import/preview", headers=HEADERS, json={"dataset": "holdings"}).status_code == 400
