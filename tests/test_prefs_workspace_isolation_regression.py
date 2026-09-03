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
    client = app.test_client()
    workspace_root = app_core.WORKSPACE_ROOT
    base_dir = app_core.BASE_DIR

    prefs_path = workspace_root / "data" / "prefs.json"
    original = prefs_path.read_text("utf-8") if prefs_path.exists() else None
    try:
        resp = client.post(
            "/api/prefs",
            json={"rpAutoLoad": True, "_probe": "workspace-isolation-regression"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        assert prefs_path.exists(), (
            f"expected prefs to be written under WORKSPACE_ROOT ({workspace_root}), "
            "but no data/prefs.json appeared there"
        )
        written = json.loads(prefs_path.read_text("utf-8"))
        assert written.get("_probe") == "workspace-isolation-regression"

        if base_dir != workspace_root:
            base_dir_prefs = base_dir / "data" / "prefs.json"
            if base_dir_prefs.exists():
                base_contents = json.loads(base_dir_prefs.read_text("utf-8"))
                assert base_contents.get("_probe") != "workspace-isolation-regression", (
                    "prefs write leaked into BASE_DIR's data/prefs.json instead of "
                    "staying under WORKSPACE_ROOT"
                )

        get_resp = client.get("/api/prefs", headers=HEADERS)
        assert get_resp.status_code == 200
        assert get_resp.get_json()["prefs"].get("_probe") == "workspace-isolation-regression"
    finally:
        if original is not None:
            prefs_path.write_text(original, "utf-8")
        elif prefs_path.exists():
            os.remove(prefs_path)
