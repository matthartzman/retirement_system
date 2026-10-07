"""WP4.5: Save As and Load Saved Plan operate on the plan file itself.

Save As copies ``plan.rpx``; Load Saved Plan replaces it through the validated
``plan_db_replace`` path (backup, sidecar cleanup) and the engine and build read the loaded rows
straight away: there is no CSV rebuild or sync step between the swap and the next read.
"""
from __future__ import annotations



import pytest

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


def test_load_saved_plan_brings_the_plan_rows_back_to_the_saved_plan(own_workspace, tmp_path):
    client = app.test_client()
    row = _row(client)
    original = row["value"]
    saved_file = tmp_path / "saved_plan.rpx"
    resp = client.post("/api/plan/save-as", headers=HEADERS, json={"path": str(saved_file)})
    assert resp.get_json()["success"] is True and saved_file.is_file()

    _save(client, row["row_index"], "$1,234,567")
    assert _active_value().replace(",", "").replace("$", "") == "1234567"

    resp = client.post("/api/plan/load-file", headers=HEADERS, json={"path": str(saved_file)})
    payload = resp.get_json()
    assert payload["success"] is True, payload
    assert payload["backup"] and payload["backup"].startswith("plan.rpx.before_load_")
    assert (own_workspace.root / payload["backup"]).is_file()
    assert _active_value() == original, "the build would still read the plan from before the load"
    assert _row(client)["value"] == original
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


def test_load_saved_plan_applies_the_row_renames_of_an_older_plan(own_workspace, tmp_path):
    """A plan saved by an older version arrives with legacy keys; the migration that follows the
    swap renames them in the loaded rows (the current key wins)."""
    from src.stores import PlanStore

    old = tmp_path / "old.rpx"
    with PlanStore.open(old) as store:
        store.insert_row("Household", label="husband_name", value="Legacy Name")
        store.insert_row("Household", label="state", value="IL")
    out = app.test_client().post("/api/plan/load-file", headers=HEADERS, json={"path": str(old)}).get_json()
    assert out["success"] is True
    assert own_workspace.store_data() == {"Household": {"": {"member_1_name": "Legacy Name", "state": "IL"}}}


def test_exit_snapshot_keeps_a_versioned_copy_of_the_plan_file(own_workspace):
    out = app.test_client().post("/api/plan/exit-snapshot", headers=HEADERS).get_json()
    assert out["success"] is True and out["plan_snapshot"].startswith("plan.rpx.version_")
    copy = own_workspace.root / out["plan_snapshot"]
    from src.stores import PlanStore
    with PlanStore.open(copy, create=False, readonly=True) as store:
        assert store.sectioned_data() == own_workspace.store_data()
