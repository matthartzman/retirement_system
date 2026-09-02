"""Cross-layer integration tests: route handler -> service -> engine ->
serialized response, without spawning the workbook-build subprocess (item
2.12, finding Q7).

The suite has strong golden-master coverage of the engine itself and strong
route-level smoke coverage of individual endpoints, but almost nothing
exercises the full chain a real browser request takes: Flask-free local
route registry -> server_services/*.py -> the deterministic engine or an
optimizer -> the exact JSON a caller gets back. A service-layer contract
break (a service passing the wrong shape to an engine function, or dropping
a field the frontend depends on) can slip through both of those layers
tested in isolation. These tests catch that class of failure directly,
using ``src.server.app`` (app_core.py's stdlib local route-registry test
client -- the same one desktop mode routes fetch() calls through, per
documentation/CLAUDE.md's "Local server" section) against the real
conftest.py-staged test workspace.
"""
from __future__ import annotations

import src.server.app_core as app_core
from src.server import app

HEADERS = {"X-User-Role": "admin"}


def _client():
    return app.test_client()


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/config/rows -> config_service.config_rows_payload() -> load_active_config()
# ─────────────────────────────────────────────────────────────────────────────

def test_config_rows_route_returns_real_schema_backed_rows():
    resp = _client().get("/api/config/rows", headers=HEADERS)
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["schema_count"] > 0
    assert len(payload["rows"]) > 0
    # Every row on this contract carries section/subsection/label -- the
    # frontend's sortRowsByDependency() and renderFieldGroups() both require
    # this shape; a service-layer bug that dropped one silently breaks the
    # whole dashboard nav, not just one field.
    sample = payload["rows"][0]
    assert {"section", "subsection", "label", "row_index"} <= sample.keys()


def test_config_backends_route_reports_sqlite_as_the_active_runtime_backend():
    # Ties directly to item 2.4: config_backend.py's load_active_config() no
    # longer supports JSON/YAML as a live backend, so the route that reports
    # which backend is active must say SQLITE for the shipped default
    # config, not silently report a retired one.
    resp = _client().get("/api/config/backends", headers=HEADERS)
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["active_backend"] == "SQLITE"


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/config/rows -> update_config_rows_payload() -> CSV + SQLite ->
# GET /api/config/rows: a real save must round-trip through every layer.
# ─────────────────────────────────────────────────────────────────────────────

def test_config_rows_save_and_readback_round_trips_through_every_layer():
    client = _client()
    rows = client.get("/api/config/rows", headers=HEADERS).get_json()["rows"]
    row_index = next(
        r["row_index"] for r in rows
        if r["section"] == "Other Assets" and r["subsection"] == "Home"
        and r["label"] == "value_as_of_plan_start"
    )
    original_value = next(r["value"] for r in rows if r["row_index"] == row_index)

    # A distinctive figure vanishingly unlikely to already be the plan's
    # value -- and distinct from the one
    # test_sync_config_backends_snapshot_freshness_regression.py uses, so a
    # crash mid-test in either file can't mask the other's restore.
    NEW_HOME_VALUE = 1_923_411
    try:
        saved = client.post(
            "/api/config/rows",
            json={"updates": [{"row_index": row_index, "value": f"${NEW_HOME_VALUE:,}"}], "sync": True},
            headers=HEADERS,
        )
        assert saved.status_code == 200, saved.get_data(as_text=True)
        assert saved.get_json()["success"] is True

        rows_after = client.get("/api/config/rows", headers=HEADERS).get_json()["rows"]
        value_after = next(r["value"] for r in rows_after if r["row_index"] == row_index)
        assert str(NEW_HOME_VALUE) in str(value_after).replace(",", "").replace("$", ""), (
            f"GET /api/config/rows served {value_after!r} after a save wrote "
            f"{NEW_HOME_VALUE} -- the route's read path disagrees with its own write path."
        )
    finally:
        client.post(
            "/api/config/rows",
            json={"updates": [{"row_index": row_index, "value": original_value}], "sync": True},
            headers=HEADERS,
        )


def test_config_rows_save_rejects_non_list_updates_without_crashing():
    """Deliberately broken service-layer contract: `updates` sent as a dict
    instead of a list. The service must reject it with a clean 400, not a
    500 traceback -- catches the class of bug the review's Q5/Q7 findings
    describe (a malformed request reaching the engine layer unvalidated)."""
    resp = _client().post(
        "/api/config/rows",
        json={"updates": {"row_index": 0, "value": "x"}},
        headers=HEADERS,
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/allocation-preview -> config_service.allocation_preview_payload()
# -> prepare_config_from_sectioned_data() -> optimization.compute_optimal_allocation()
# ─────────────────────────────────────────────────────────────────────────────

def test_allocation_preview_route_returns_real_engine_computed_targets():
    resp = _client().post(
        "/api/allocation-preview",
        json={"mode": "optimizer_recommendation"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    targets = payload["selected_total_targets"]
    assert targets, "expected compute_optimal_allocation to return nonzero allocation targets"
    # The response mixes parent asset classes with their own sub-allocations
    # in one flat dict (e.g. "Bonds/Fixed Income" alongside "Bonds",
    # "TIPS", ...), so the values don't sum to 1.0 -- but every individual
    # weight must still be a sane fraction, and at least one real,
    # well-known asset class must carry a nonzero weight (not an empty stub
    # or every key zeroed out).
    assert all(0.0 <= v <= 1.0 for v in targets.values()), targets
    assert targets.get("US Large Cap", 0.0) > 0.0, targets


def test_allocation_preview_route_optimizer_and_user_modes_diverge_when_configured():
    client = _client()
    optimizer = client.post(
        "/api/allocation-preview", json={"mode": "optimizer_recommendation"}, headers=HEADERS,
    ).get_json()
    user = client.post(
        "/api/allocation-preview", json={"mode": "user_specified"}, headers=HEADERS,
    ).get_json()
    assert optimizer["success"] is True
    assert user["success"] is True
    # Both modes must independently reach compute_optimal_allocation with a
    # real force_mode, not both silently falling through to the same
    # default -- the response's own reported policy mode must reflect what
    # was actually requested.
    assert optimizer["selected_policy_mode"] != user["selected_policy_mode"] or (
        optimizer["selected_total_targets"] != user["selected_total_targets"]
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/daf/recommendation -> config_service.daf_recommendation_payload()
# -> daf_optimizer.recommend_daf_contribution()
# ─────────────────────────────────────────────────────────────────────────────

def test_daf_recommendation_route_returns_a_real_bounded_computed_amount():
    resp = _client().post("/api/daf/recommendation", json={}, headers=HEADERS)
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    # recommend_daf_contribution caps the recommendation within the IRS AGI
    # ceiling (60% cash / 30% appreciated) -- a broken service-layer call
    # (e.g. passing the wrong cfg, or not passing `rows`) would show up here
    # as either a crash (already caught by status_code) or an absurd
    # (negative, or unbounded) figure.
    amount = payload.get("recommended_amount", payload.get("amount"))
    assert amount is not None
    assert amount >= 0


def test_daf_recommendation_route_respects_appreciated_flag_end_to_end():
    client = _client()
    cash_only = client.post("/api/daf/recommendation", json={"appreciated": False}, headers=HEADERS).get_json()
    appreciated = client.post("/api/daf/recommendation", json={"appreciated": True}, headers=HEADERS).get_json()
    assert cash_only["success"] is True
    assert appreciated["success"] is True
    # recommend_daf_contribution uses a 60%-of-AGI ceiling for cash vs. a
    # 30%-of-AGI ceiling for appreciated holdings -- the route must pass the
    # request body's `appreciated` flag through to the engine call, not
    # silently default it (a service-layer bug that ignored the request
    # body would make both calls report the same 0.60 ceiling).
    assert cash_only["agi_limit_pct"] == 0.60
    assert appreciated["agi_limit_pct"] == 0.30


# ─────────────────────────────────────────────────────────────────────────────
# Permission gate: route -> _require() -> service is never reached when
# denied. Confirms the gate actually runs before the engine layer, not after.
# ─────────────────────────────────────────────────────────────────────────────

def test_config_rows_write_is_denied_without_write_permission(monkeypatch):
    def _deny(user, permission):
        if permission == "write_config":
            raise PermissionError("write_config denied for test")

    monkeypatch.setattr(app_core, "require_permission", _deny)
    resp = _client().post(
        "/api/config/rows",
        json={"updates": [{"row_index": 0, "value": "x"}]},
        headers=HEADERS,
    )
    assert resp.status_code == 403
    payload = resp.get_json()
    assert payload["success"] is False
