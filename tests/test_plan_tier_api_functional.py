"""WP5.1: ``POST /api/plan/tier`` (with its ``preview`` dry run), ``POST /api/plan/feature`` and
the plan profile / tier presets in the ``GET /api/config/rows`` payload.

Both writes go through ``app_core._edit_active_plan`` (one rows transaction on the plan file,
the strategy endpoints' edit context); a preview reads only.
"""
from __future__ import annotations

import pytest

from src import module_catalog as mc
from src.api_contracts import validate_payload
from src.server import app, plan_routes
from src.server_services.plan_tier_service import entered_value
from tests.plan_fixture import make_plan

HEADERS = {"X-User-Role": "admin"}


@pytest.fixture
def ws(tmp_path, monkeypatch):
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_CONFIG_FILE", raising=False)
    for var in ("RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES", "RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES",
                "RETIREMENT_SYSTEM_FORCE_ALL_MODULES"):
        monkeypatch.delenv(var, raising=False)
    return plan


@pytest.fixture
def client(ws):
    return app.test_client()


@pytest.fixture
def events(monkeypatch):
    out: list = []
    monkeypatch.setattr(plan_routes, "_audit", lambda event, details=None: out.append((event, details)))
    return out


def _post(client, path, body):
    resp = client.post(path, headers=HEADERS, json=body)
    return resp.status_code, resp.get_json()


def _revision(ws):
    with ws.store(readonly=True) as store:
        return store.revision()


def test_config_rows_payload_carries_the_profile_and_the_presets(ws, client):
    out = client.get("/api/config/rows", headers=HEADERS).get_json()
    profile = out["plan_profile"]
    assert profile["tier"] == "expert" and profile["tier_stored"] is False
    assert profile["label"] == ("Expert (customized)" if profile["customized"] else "Expert")
    presets = out["tier_presets"]
    assert presets["default"] == "expert" and presets["switchable"] == mc.switchable_keys()
    assert [t["key"] for t in presets["tiers"]] == list(mc.TIERS)
    for t in presets["tiers"]:
        assert set(t["features"]) == mc.tier_preset(t["key"])
        assert t["label"] == mc.TIER_LABELS[t["key"]] and t["description"]


def test_preview_answers_what_would_change_and_writes_nothing(ws, client, events):
    # turn a section-owning feature on first, so the preview has entered rows to report
    assert _post(client, "/api/plan/feature", {"key": "existing_life_insurance", "on": True})[0] == 200
    revision = _revision(ws)
    events.clear()
    status, out = _post(client, "/api/plan/tier", {"tier": "simple", "preview": True})
    assert status == 200 and out["success"] and out["preview"] is True
    assert validate_payload("POST", "/api/plan/tier", out) == []
    assert _revision(ws) == revision and events == []
    with ws.store(readonly=True) as store:
        changes = mc.tier_changes(store, "simple")
        insurance_rows = sum(1 for r in store.rows("Insurance In Force") if entered_value(r["value"]))
    assert out["current"]["tier"] == "expert"
    assert [f["key"] for f in out["turn_on"]] == changes["turn_on"]
    off = {f["key"]: f for f in out["turn_off"]}
    assert list(off) == changes["turn_off"]
    assert off["existing_life_insurance"]["entered_rows"] == insurance_rows > 0
    assert off["estate_legacy_plan"]["entered_rows"] is None  # a page-owning module: counted by the page
    assert off["spending_tracker_ytd"]["engine_participation"] is True
    assert {f["key"] for f in out["engine_ignored"]} == {k for k, f in off.items() if f["engine_participation"]}
    assert "spending_tracker_ytd" in {f["key"] for f in out["engine_ignored"]}
    assert out["unchanged"] is False and out["label"] == "Simple"


def test_apply_writes_the_tier_and_the_switches_in_one_edit(ws, client, events):
    status, out = _post(client, "/api/plan/tier", {"tier": "standard"})
    assert status == 200 and out["preview"] is False
    assert validate_payload("POST", "/api/plan/tier", out) == []
    assert out["profile"] == {"tier": "standard", "tier_stored": True, "customized": False,
                              "label": "Standard", "differing": []}
    assert out["revision"] == _revision(ws)
    with ws.store(readonly=True) as store:
        assert mc.plan_tier(store) == "standard"
        for key in mc.switchable_keys():
            assert mc.stored_switch(store, key) == (key in mc.tier_preset("standard")), key
    (event, details), = events
    assert event == "plan_tier_applied" and details["tier"] == "standard"
    assert details["turned_off"] == [f["key"] for f in out["turn_off"]]
    # the grid payload now reads the new profile; a second pick of the same tier changes nothing
    assert client.get("/api/config/rows", headers=HEADERS).get_json()["plan_profile"]["label"] == "Standard"
    status, again = _post(client, "/api/plan/tier", {"tier": "standard", "preview": True})
    assert again["unchanged"] is True and again["turn_on"] == again["turn_off"] == []


def test_a_feature_override_customizes_the_tier(ws, client, events):
    _post(client, "/api/plan/tier", {"tier": "simple"})
    events.clear()
    status, out = _post(client, "/api/plan/feature", {"key": "planning_workbench", "on": True})
    assert status == 200 and validate_payload("POST", "/api/plan/feature", out) == []
    assert out["profile"]["label"] == "Simple (customized)" and out["profile"]["differing"] == ["planning_workbench"]
    assert events == [("plan_feature_set", {"key": "planning_workbench", "on": True, "revision": out["revision"]})]
    # "Reset to Simple preset" is the same pick again
    status, out = _post(client, "/api/plan/tier", {"tier": "simple"})
    assert [f["key"] for f in out["turn_off"]] == ["planning_workbench"]
    assert out["profile"]["customized"] is False


@pytest.mark.parametrize("path, body, error", [
    ("/api/plan/tier", {"tier": "gold"}, "tier must be one of"),
    ("/api/plan/tier", {}, "tier must be one of"),
    ("/api/plan/tier", {"tier": "simple", "preview": "yes"}, "preview must be true or false"),
    ("/api/plan/feature", {"key": "heloc", "on": "TRUE"}, "on must be true or false"),
    ("/api/plan/feature", {"key": "no_such_feature", "on": True}, "unknown feature"),
    ("/api/plan/feature", {"key": "net_worth", "on": False}, "always-on core"),
    ("/api/plan/feature", {"key": "spending_summary", "on": False}, "no switch of its own"),
])
def test_bad_requests_are_refused_and_write_nothing(ws, client, events, path, body, error):
    revision = _revision(ws)
    status, out = _post(client, path, body)
    assert status == 400 and out["success"] is False and error in out["error"]
    assert _revision(ws) == revision and events == []



def test_config_rows_carry_min_tier(ws, client):
    """WP5.2: every catalogued row serves its reference.db min_tier; rows the catalog
    does not list serve an empty tier (always shown)."""
    from src.stores.ref_getters.schema_fields import TIERS
    rows = client.get("/api/config/rows", headers=HEADERS).get_json()["rows"]
    tiers = {r["min_tier"] for r in rows}
    assert tiers <= set(TIERS) | {""}
    assert tiers & set(TIERS)
