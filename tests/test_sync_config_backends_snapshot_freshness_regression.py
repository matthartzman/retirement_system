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

Checks both `local_store.plan_snapshots` directly (the exact table that went
stale) and `load_active_config()` itself (what a real build actually calls) --
the latter only became a reliable check for this test workspace after fixing
conftest.py's own import-ordering bug (it imported src.config_backend, which
caches platform_runtime.workspace_root() into module-level constants at
import time, before setting RETIREMENT_SYSTEM_WORKSPACE_ROOT).

Deliberately fast (no subprocess build, no `@pytest.mark.slow`): the
original regression was ONLY caught by the slow, full-FILE run of
tests/test_e2e_build_journey.py (it doesn't reproduce standalone, per the
revert commit), so the "not slow" tier had no guard against it recurring.
"""
from __future__ import annotations

import src.server.app_core as app_core
from src.config_backend import load_active_config
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
    # This POST goes through the real save-plan-data route against the
    # shared workspace conftest.py stages for the whole test session, not an
    # isolated tmp_path -- without restoring the pre-edit value afterward,
    # this test permanently corrupts the home value every later test in the
    # same pytest process sees, regardless of pass/fail. Confirmed directly:
    # tests/test_withdrawal_sequencing_comparison_regression.py's own
    # "current plan is highest terminal net worth" assertion started failing
    # with different (real, non-flaky) numbers once this test ran first and
    # left NEW_HOME_VALUE (1,847,213) behind as the household's "original"
    # home value for the rest of the run.
    original_value = next(r["value"] for r in rows if r["row_index"] == row_index)

    # A distinctive figure vanishingly unlikely to already be the plan's value.
    NEW_HOME_VALUE = 1_847_213
    try:
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

        def _stripped(v):
            return str(v).replace(",", "").replace("$", "")

        # plan_snapshots is what load_sqlite() -> local_store.latest_sectioned_data()
        # reads; it must reflect the value just saved, not whatever the last
        # import_csv_to_sqlite() call happened to hold.
        snapshot_data = latest_sectioned_data(app_core._sqlite_db())
        snapshot_value = snapshot_data.get("Other Assets", {}).get("Home", {}).get("value_as_of_plan_start")
        assert snapshot_value is not None, (
            "plan_snapshots has no value_as_of_plan_start at all -- "
            f"Other Assets/Home section was: {snapshot_data.get('Other Assets', {}).get('Home', {})}"
        )
        assert str(NEW_HOME_VALUE) in _stripped(snapshot_value), (
            f"plan_snapshots returned a STALE value ({snapshot_value!r}) after a real save "
            f"wrote {NEW_HOME_VALUE} -- local_store.plan_snapshots was not refreshed. "
            "This is the Wave 4.11 regression: _sync_config_backends() must still call "
            "import_csv_to_sqlite()."
        )

        # load_active_config() is the actual call site a real build uses
        # (workbook_builder.main()) -- check it directly too, not just the
        # underlying table, so this test fails the same way a real build would.
        active_data, _meta = load_active_config()
        active_value = active_data.get("Other Assets", {}).get("Home", {}).get("value_as_of_plan_start")
        assert active_value is not None, (
            "load_active_config() has no value_as_of_plan_start at all -- "
            f"Other Assets/Home section was: {active_data.get('Other Assets', {})}"
        )
        assert str(NEW_HOME_VALUE) in _stripped(active_value), (
            f"load_active_config() returned a STALE value ({active_value!r}) after a real "
            f"save wrote {NEW_HOME_VALUE} -- a real build would have served the old figure."
        )
    finally:
        restored = client.post(
            "/api/config/rows",
            json={"updates": [{"row_index": row_index, "value": original_value}], "sync": True},
            headers=HEADERS,
        )
        assert restored.status_code == 200, restored.get_data(as_text=True)
