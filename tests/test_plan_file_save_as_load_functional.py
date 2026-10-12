"""WP4.5 / WP8.4: Save As and Load Saved Plan are plan registry operations over plan files.

Save As copies the active plan file to a new path and registers it (activating it unless told
not to); Load Saved Plan registers the chosen file and makes it the active plan, leaving the
previous plan file untouched. ``mode: "restore"`` replaces the active plan file's contents
through the validated ``plan_db_replace`` path (backup, sidecar cleanup). Either way the engine
and build read the loaded rows straight away: no CSV rebuild or sync step.
"""
from __future__ import annotations



import pytest

from src import active_plan, plan_registry
from src.config_backend import load_active_config
from src.server import app
from src.sqlite_util import connect as closing_connect
from tests.plan_fixture import make_plan

HEADERS = {"X-User-Role": "admin"}
KEY = ("Other Assets", "Home", "value_as_of_plan_start")


def _row(client):
    rows = client.get("/api/config/rows", headers=HEADERS).get_json()["rows"]
    return next(r for r in rows if (r["section"], r["subsection"], r["label"]) == KEY)


def _save(client, row_index, value):
    resp = client.post("/api/config/rows", headers=HEADERS,
                       json={"updates": [{"row_index": row_index, "value": value}]})
    assert resp.status_code == 200 and resp.get_json()["success"] is True, resp.get_data(as_text=True)


def _active_value():
    data, _ = load_active_config()
    return data[KEY[0]][KEY[1]][KEY[2]]


@pytest.fixture
def own_workspace(tmp_path, monkeypatch):
    """A workspace of this test's own: Load Saved Plan replaces the plan file, which Windows
    refuses while another test process has the shared session plan open."""
    ws = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(ws.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    return ws


def test_load_saved_plan_opens_the_saved_file_as_the_active_plan(own_workspace, tmp_path):
    client = app.test_client()
    row = _row(client)
    original = row["value"]
    saved_file = tmp_path / "saved_plan.rpx"
    resp = client.post("/api/plan/save-as", headers=HEADERS, json={"path": str(saved_file), "activate": False})
    assert resp.get_json()["success"] is True and saved_file.is_file()
    assert active_plan.active_plan_path() == own_workspace.plan_db  # recorded, not activated
    assert plan_registry.plan_id_for_path(saved_file)

    _save(client, row["row_index"], "$1,234,567")
    assert _active_value().replace(",", "").replace("$", "") == "1234567"

    payload = client.post("/api/plan/load-file", headers=HEADERS, json={"path": str(saved_file)}).get_json()
    assert payload["success"] is True, payload
    assert payload["plan"]["path"] == str(saved_file) and payload["backup"] is None
    assert active_plan.active_plan_path() == saved_file
    assert _active_value() == original, "the build would still read the plan from before the load"
    assert _row(client)["value"] == original
    # the plan that was active before is untouched (no copy over it, no backup beside it)
    with own_workspace.store() as store:
        assert store.sectioned_data()[KEY[0]][KEY[1]][KEY[2]].replace(",", "").replace("$", "") == "1234567"
    assert not list(own_workspace.root.glob("plan.rpx.before_load_*"))


def test_save_as_activates_the_copy_by_default(own_workspace, tmp_path):
    target = tmp_path / "My Copy.rpx"
    out = app.test_client().post("/api/plan/save-as", headers=HEADERS, json={"path": str(target)}).get_json()
    assert out["success"] is True and out["activated"] is True and out["plan"]["name"] == "My Copy"
    assert active_plan.active_plan_path() == target
    assert _active_value() == own_workspace.store_data()[KEY[0]][KEY[1]][KEY[2]]


def test_restore_mode_replaces_the_active_plan_file_through_the_validated_swap(own_workspace, tmp_path):
    client = app.test_client()
    row = _row(client)
    original = row["value"]
    saved_file = tmp_path / "saved_plan.rpx"
    assert client.post("/api/plan/save-as", headers=HEADERS,
                       json={"path": str(saved_file), "activate": False}).get_json()["success"] is True
    _save(client, row["row_index"], "$1,234,567")
    payload = client.post("/api/plan/load-file", headers=HEADERS,
                          json={"path": str(saved_file), "mode": "restore"}).get_json()
    assert payload["success"] is True, payload
    assert payload["backup"] and payload["backup"].startswith("plan.rpx.before_load_")
    assert (own_workspace.root / payload["backup"]).is_file()
    assert active_plan.active_plan_path() == own_workspace.plan_db
    assert _active_value() == original
    # no sidecar of the replaced file is left behind, and the file is an ordinary plan file
    assert not (own_workspace.root / "plan.rpx-wal").exists() or (own_workspace.root / "plan.rpx-wal").stat().st_size == 0
    with closing_connect(own_workspace.plan_db) as con:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_load_saved_plan_refuses_a_file_that_is_not_a_plan_file(own_workspace, tmp_path):
    client = app.test_client()
    before = own_workspace.store_data()
    legacy = tmp_path / "legacy.db"
    with closing_connect(legacy) as con:  # a legacy database: client_files only
        con.execute("CREATE TABLE client_files(file_name TEXT PRIMARY KEY, content TEXT)")
    for bad in (legacy, tmp_path / "missing.rpx"):
        out = client.post("/api/plan/load-file", headers=HEADERS, json={"path": str(bad)}).get_json()
        assert out["success"] is False and out["error"]
    garbage = tmp_path / "garbage.rpx"
    garbage.write_bytes(b"not a database at all")
    assert client.post("/api/plan/load-file", headers=HEADERS, json={"path": str(garbage)}).get_json()["success"] is False
    assert own_workspace.store_data() == before
    assert active_plan.active_plan_path() == own_workspace.plan_db


def test_load_saved_plan_applies_the_row_renames_of_an_older_plan(own_workspace, tmp_path):
    """A plan saved by an older version arrives with legacy keys; the migration that follows the
    switch renames them in the opened plan's rows (the current key wins)."""
    from src.stores import PlanStore

    old = tmp_path / "old.rpx"
    with PlanStore.open(old) as store:
        store.insert_row("Household", label="husband_name", value="Legacy Name")
        store.insert_row("Household", label="state", value="IL")
    out = app.test_client().post("/api/plan/load-file", headers=HEADERS, json={"path": str(old)}).get_json()
    assert out["success"] is True and active_plan.active_plan_path() == old
    assert active_plan.peek_plan_data()["Household"] == {"": {"member_1_name": "Legacy Name", "state": "IL"}}


def test_exit_snapshot_keeps_a_versioned_copy_of_the_plan_file(own_workspace):
    out = app.test_client().post("/api/plan/exit-snapshot", headers=HEADERS).get_json()
    assert out["success"] is True and out["plan_snapshot"].startswith("plan.rpx.version_")
    copy = own_workspace.root / out["plan_snapshot"]
    from src.stores import PlanStore
    with PlanStore.open(copy, create=False, readonly=True) as store:
        assert store.sectioned_data() == own_workspace.store_data()
