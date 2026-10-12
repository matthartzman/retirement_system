"""Regression guard: /api/prefs must read/write under WORKSPACE_ROOT, not
BASE_DIR (the code/package root).

Root cause of a real, previously "already documented but unresolved" E2E
flake (workbook-format-tab-focus.spec.js intermittently stuck on "Loading
plan"): src/server/base_routes.py's get_prefs()/save_prefs() passed BASE_DIR
(src/server/app_core.py's package root) to base_service.read_prefs/
save_prefs instead of WORKSPACE_ROOT. tools/e2e_server.py isolates input/,
output/, local_state/, and saved_plans/ under a throwaway temp workspace via
RETIREMENT_SYSTEM_WORKSPACE_ROOT, but prefs fell through that isolation and
read the real, checked-in data/prefs.json (rpAutoLoad: true, this
developer's own desktop preference). That made every E2E page load kick off
an unwanted auto-load (frontend/js/dashboard.js's boot queueMicrotask chain)
racing the test's own explicit "Open Current Plan" load -- the exact
"some OTHER loadAll trigger this suite doesn't control" race
tests/e2e/helpers.js's triggerBuildAndWaitForOverlay comment already
diagnosed but could not identify.
"""
from __future__ import annotations

import json
import os

import src.server.app_core as app_core
from src.server import app

HEADERS = {"X-User-Role": "admin"}


def test_prefs_round_trip_stays_under_workspace_root_not_base_dir():
    """Prefs live in the workspace's app.db (WP8.3), never in BASE_DIR."""
    from src.app_state import app_store_path_for, open_app_store
    from src.server_services.base_service import PREFS_SETTING

    client = app.test_client()
    workspace_root = app_core.WORKSPACE_ROOT
    base_dir = app_core.BASE_DIR
    db_path = app_store_path_for(workspace_root)
    with open_app_store(db_path) as store:
        original = store.get_setting(PREFS_SETTING)
    try:
        resp = client.post(
            "/api/prefs",
            json={"rpAutoLoad": True, "_probe": "workspace-isolation-regression"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        with open_app_store(db_path, readonly=True) as store:
            assert store.get_setting(PREFS_SETTING).get("_probe") == "workspace-isolation-regression"

        if base_dir != workspace_root:
            base_db = app_store_path_for(base_dir)
            if base_db.exists():
                with open_app_store(base_db, readonly=True) as store:
                    assert (store.get_setting(PREFS_SETTING) or {}).get("_probe") != "workspace-isolation-regression"

        get_resp = client.get("/api/prefs", headers=HEADERS)
        assert get_resp.status_code == 200
        assert get_resp.get_json()["prefs"].get("_probe") == "workspace-isolation-regression"
    finally:
        with open_app_store(db_path) as store:
            if original is None:
                store.delete_setting(PREFS_SETTING)
            else:
                store.set_setting(PREFS_SETTING, original)
