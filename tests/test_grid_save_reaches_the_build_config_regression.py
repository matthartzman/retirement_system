"""Wave 4.11 regression guard (system review 2026-08-04, `csv-roundtrip-on-every-save`), kept
for the plan file (WP4.5 deleted the CSV bridge it originally guarded).

A grid save must reach the plan file's rows, and so `load_active_config()` -- what a real build
reads via `workbook_builder.main()` -- or a build silently serves a stale plan after an edit.

Checks both the plan file's rows directly (the store the build reads) and
`load_active_config()` itself (what a real build actually calls). Deliberately fast (no
subprocess build, no `@pytest.mark.slow`).
"""
from __future__ import annotations

import pytest

from src.active_plan import active_plan_store
from src.config_backend import load_active_config
from src.server import app

HEADERS = {"X-User-Role": "admin"}


@pytest.fixture
def own_workspace(tmp_path, monkeypatch):
    """WP4.3: a workspace of this test's own. The shared session workspace is shared by
    every xdist worker, and other tests save the same Home value concurrently."""
    from tests.plan_fixture import make_plan
    ws = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(ws.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    return ws


def test_a_grid_save_keeps_the_plan_file_and_the_build_config_fresh(own_workspace):
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
            json={"updates": [{"row_index": row_index, "value": f"${NEW_HOME_VALUE:,}"}]},
            headers=HEADERS,
        )
        assert saved.status_code == 200, saved.get_data(as_text=True)
        assert saved.get_json()["success"] is True

        def _stripped(v):
            return str(v).replace(",", "").replace("$", "")

        # The plan file's rows are what load_active_config() reads; they must
        # reflect the value just saved.
        with active_plan_store(readonly=True) as store:
            snapshot_data = store.sectioned_data()
        snapshot_value = snapshot_data.get("Other Assets", {}).get("Home", {}).get("value_as_of_plan_start")
        assert snapshot_value is not None, (
            "the plan file has no value_as_of_plan_start at all -- "
            f"Other Assets/Home section was: {snapshot_data.get('Other Assets', {}).get('Home', {})}"
        )
        assert str(NEW_HOME_VALUE) in _stripped(snapshot_value), (
            f"the plan file returned a STALE value ({snapshot_value!r}) after a real save "
            f"wrote {NEW_HOME_VALUE} -- its rows were not refreshed. This is the Wave 4.11 "
            "regression: a save must reach the rows the build reads."
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
            json={"updates": [{"row_index": row_index, "value": original_value}]},
            headers=HEADERS,
        )
        assert restored.status_code == 200, restored.get_data(as_text=True)
