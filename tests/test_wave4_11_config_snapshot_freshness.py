"""Wave 4.11 regression guard (system review 2026-08-04, `csv-roundtrip-on-every-save`).

`_sync_config_backends()` must re-import the on-disk CSV into local_store's
typed sectioned snapshot (`plan_snapshots`), or `load_active_config()` --
what a real build reads via `workbook_builder.main()` -- silently serves a
stale plan after any edit.

This is the exact bug the original Wave 4.11 attempt introduced (commit
f454117, reverted at 7d1ca0f): the trace "every real write caller already
writes the DB first" checked `client_files` (written by
`_write_plan_data_file()`), not the SEPARATE `local_store.plan_snapshots`
table, which only `import_csv_to_sqlite()` refreshes -- see the long comment
on `_sync_config_backends()` in src/server/app_core.py for the full root
cause (two independent SQLite stores).

This checks `local_store.plan_snapshots` directly (via the same
`_sqlite_db()` path resolution `_sync_config_backends()` itself uses) rather
than going through `load_active_config()`: that function's own bootstrap-CSV
discovery (`discover_bootstrap_csv()`) does not honor the
RETIREMENT_SYSTEM_WORKSPACE_ROOT test-workspace redirect conftest.py sets up
(a separate, pre-existing test-infrastructure gap, not this regression), so
calling it directly from a test reads the real repo's DB rather than the
isolated test one. Checking plan_snapshots directly is also more precise --
it is the exact table that went stale.

Deliberately fast (no subprocess build, no `@pytest.mark.slow`): the
original regression was ONLY caught by the slow, full-FILE run of
tests/test_e2e_build_journey.py (it doesn't reproduce standalone, per the
revert commit), so the "not slow" tier had no guard against it recurring.
"""
from __future__ import annotations

import src.server.app_core as app_core
from src.local_store import latest_sectioned_data
from src.server import app

HEADERS = {"X-User-Role": "admin"}


def test_sync_config_backends_keeps_plan_snapshots_fresh():
    client = app.test_client()

    rows_resp = client.get("/api/config/rows", headers=HEADERS)
    assert rows_resp.status_code == 200
    rows = rows_resp.get_json()["rows"]

    row_index = next(
        r["row_index"] for r in rows
        if r["section"] == "Other Assets" and r["subsection"] == "Home"
        and r["label"] == "value_as_of_plan_start"
    )

    # A distinctive figure vanishingly unlikely to already be the plan's value.
    NEW_HOME_VALUE = 1_847_213
    saved = client.post(
        "/api/config/rows",
        json={
            "updates": [{"row_index": row_index, "value": f"${NEW_HOME_VALUE:,}"}],
            "sync": True,
        },
        headers=HEADERS,
    )
    assert saved.status_code == 200, saved.get_data(as_text=True)
    assert saved.get_json()["success"] is True

    # plan_snapshots is what workbook_builder.main() -> load_active_config()
    # -> load_sqlite() reads for a real build; it must reflect the value just
    # saved, not whatever the last import_csv_to_sqlite() call happened to hold.
    data = latest_sectioned_data(app_core._sqlite_db())
    home_section = data.get("Other Assets", {}).get("Home", {})
    saved_value = home_section.get("value_as_of_plan_start")
    assert saved_value is not None, (
        "plan_snapshots has no value_as_of_plan_start at all -- "
        f"Other Assets/Home section was: {home_section}"
    )
    assert str(NEW_HOME_VALUE) in str(saved_value).replace(",", "").replace("$", ""), (
        f"plan_snapshots returned a STALE value ({saved_value!r}) after a real save "
        f"wrote {NEW_HOME_VALUE} -- local_store.plan_snapshots was not refreshed. "
        "This is the Wave 4.11 regression: _sync_config_backends() must still call "
        "import_csv_to_sqlite()."
    )
