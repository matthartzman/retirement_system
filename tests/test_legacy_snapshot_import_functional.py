"""WI-038: snapshots, price history, freezes and build events move from the legacy
``retirement_system_v10.db`` into ``app.db`` once, and the legacy file is never written again."""
from __future__ import annotations

import sqlite3

from src import local_store
from src.portfolio_analytics import load_latest_snapshots, pricing_freeze_status
from src.stores import AppStore


def _legacy(path):
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE kpi_snapshots(snapshot_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, build_id TEXT,
        probability_of_success REAL, kpi_json TEXT NOT NULL);
    INSERT INTO kpi_snapshots VALUES('k1','2026-08-04T00:00:00Z','b1',0.9,'{"probability_of_success":0.9}');
    CREATE TABLE price_snapshots(snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT, workspace_id TEXT, symbol TEXT,
        price REAL, source TEXT, status TEXT, as_of TEXT);
    INSERT INTO price_snapshots(workspace_id,symbol,price,source,status,as_of) VALUES('local','VTI',250.0,'cache','OK','2026-08-01');
    CREATE TABLE pricing_snapshot_freezes(workspace_id TEXT PRIMARY KEY, active INTEGER, frozen_at TEXT, source TEXT, snapshot_json TEXT);
    INSERT INTO pricing_snapshot_freezes VALUES('local',1,'2026-08-02','x','{"symbols":{"VTI":{"price":250.0}}}');
    CREATE TABLE local_settings(key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL);
    INSERT INTO local_settings VALUES('plan_data_schema_version','7','2026-08-01');
    CREATE TABLE build_events(event_id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, build_id TEXT, stage TEXT, event_type TEXT, detail_json TEXT);
    INSERT INTO build_events(created_at,build_id,stage,event_type,detail_json) VALUES('2026-08-01','b1','s','e','{}');
    """)
    con.commit()
    con.close()


def test_legacy_rows_import_once_and_legacy_file_is_untouched(tmp_path):
    legacy = tmp_path / "retirement_system_v10.db"
    _legacy(legacy)
    before = legacy.read_bytes()
    app_db = tmp_path / "app.db"

    assert local_store.get_kpi_snapshot("k1", db_path=app_db)["build_id"] == "b1"
    assert local_store.get_local_setting("plan_data_schema_version", 0, db_path=app_db) == 7
    assert load_latest_snapshots(db_path=app_db)["VTI"]["price"] == 250.0
    freeze = pricing_freeze_status(db_path=app_db)
    assert freeze["active"] and freeze["prices"] == {"VTI": 250.0}

    # A second pass imports nothing more, new writes land in app.db only.
    local_store.save_kpi_snapshot({"probability_of_success": 0.8}, build_id="b2", created_at="2026-09-01T00:00:00Z", db_path=app_db)
    local_store.append_build_event("s", "e", {}, build_id="b2", db_path=app_db)
    con = sqlite3.connect(app_db)
    assert con.execute("SELECT count(*) FROM kpi_snapshots").fetchone()[0] == 2
    assert con.execute("SELECT count(*) FROM build_events").fetchone()[0] == 2
    con.close()
    assert legacy.read_bytes() == before
    with AppStore.open(app_db) as store:
        assert store.get_setting(local_store.LEGACY_IMPORT_KEY) is True
