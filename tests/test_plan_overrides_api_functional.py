"""WP4.5: the three override-table routes store rows in the plan (and refuse CSV bodies)."""
from __future__ import annotations

import pytest

from src import optimization as opt
from src.config_backend import load_active_config
from src.server import app
from tests.plan_fixture import make_plan

HEADERS = {"X-User-Role": "admin"}
CLASS = next(iter(opt._BASE_ASSET_CLASSES))
OTHER = list(opt._BASE_ASSET_CLASSES)[1]


@pytest.fixture
def ws(tmp_path, monkeypatch):
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    return plan


def _post(path, body):
    resp = app.test_client().post(path, headers=HEADERS, json=body)
    return resp.status_code, resp.get_json()


def test_capital_market_rows_are_stored_validated_and_cleared(ws):
    rows = [{"horizon_years": "30", "preset": "BASELINE", "asset_class": CLASS, "expected_return": "9%", "volatility": "17%"}]
    assert _post("/api/capital-market/assumptions", {"rows": rows}) == (200, {"success": True, "count": 1})
    assert ws.store_data()["Custom Capital Market"]["row_1"]["expected_return"] == "9%"
    assert load_active_config()[0]["Custom Capital Market"]["row_1"]["asset_class"] == CLASS
    status, out = _post("/api/capital-market/assumptions", {"rows": [{"asset_class": "Nope", "expected_return": "x"}]})
    assert status == 400 and len(out["errors"]) == 2
    assert ws.store_data()["Custom Capital Market"]["row_1"]["expected_return"] == "9%"  # a refused post changes nothing
    assert _post("/api/capital-market/assumptions", {"rows": []}) == (200, {"success": True, "count": 0})
    assert "Custom Capital Market" not in ws.store_data()


def test_correlation_and_real_loss_rows(ws):
    status, out = _post("/api/capital-market/correlations", {"rows": [
        {"asset_class_a": CLASS, "asset_class_b": OTHER, "correlation": "0.5"}]})
    assert (status, out["count"]) == (200, 1) and ws.store_data()["Custom Correlations"]["row_1"]["correlation"] == "0.5"
    status, out = _post("/api/capital-market/real-loss-curves", {"rows": [
        {"curve_name": "Blend", "holding_years": "10", "real_loss_prob": "12%"}]})
    assert (status, out["count"]) == (200, 1)
    assert ws.store_data()["Custom Real Loss Curves"]["row_1"] == {
        "curve_name": "Blend", "holding_years": "10", "real_loss_prob": "12%"}


def test_a_csv_body_or_no_rows_is_refused(ws):
    status, out = _post("/api/capital-market/assumptions", {"csv_content": "a,b\n1,2\n"})
    assert status == 410 and "rows" in out["error"] and not out["success"]
    status, out = _post("/api/capital-market/correlations", {})
    assert status == 400 and "rows is required" in out["error"]
    assert not ({"Custom Capital Market", "Custom Correlations"} & set(ws.store_data()))
