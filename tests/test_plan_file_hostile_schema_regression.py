"""S-03: an untrusted `.rpx` cannot run its own triggers or views inside the app.

A crafted plan file may carry triggers (which fire on the app's own writes and during in-place upgrades) and views.
The application schema has none, so opening refuses any, before any migration or write; connections are opened with
`trusted_schema=OFF`, `cell_size_check=ON` and SQLite's defensive mode where the build supports it.
"""
from __future__ import annotations

import hashlib
import sqlite3

import pytest

from src import plan_registry
from src.plan_db_replace import PLAN_FILE_TABLES, validate_plan_db
from src.stores import PlanStore
from src.stores.db import StoreError
from src.stores.plan_store import PLAN_SCHEMA_VERSION

TRIGGER = ("CREATE TRIGGER evil AFTER INSERT ON plan_rows BEGIN "
           "UPDATE plan_rows SET value = 'TAMPERED' WHERE section = 'victim'; END")
VIEW = "CREATE VIEW sneaky AS SELECT * FROM plan_rows"


def _plan(path, extra_sql=None):
    store = PlanStore.open(path)
    store.insert_row("victim", label="x", value="original")
    store.close()
    if extra_sql:
        con = sqlite3.connect(path)
        con.execute(extra_sql)
        con.commit()
        con.close()
    return path


def _digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_clean_plan_still_opens_and_is_hardened(tmp_path):
    path = _plan(tmp_path / "ok.rpx")
    store = PlanStore.open(path, create=False)
    try:
        con = store._con
        assert con.execute("PRAGMA trusted_schema").fetchone()[0] == 0
        assert con.execute("PRAGMA cell_size_check").fetchone()[0] == 1
        if hasattr(con, "getconfig"):
            assert con.getconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE) is True
    finally:
        store.close()
    assert plan_registry.check_plan_file(path) is None


def test_the_reproduction_is_real_without_the_guard(tmp_path):
    """Plain sqlite3 (no guard) runs the trigger on an ordinary insert: this is the behaviour the guard must prevent."""
    path = _plan(tmp_path / "evil.rpx", TRIGGER)
    con = sqlite3.connect(path)
    con.execute("INSERT INTO plan_rows (section, subsection, label, value, units, notes, sort_order) "
                "VALUES ('victim', '', 'y', 'new', '', '', 5)")
    values = {r[0] for r in con.execute("SELECT value FROM plan_rows WHERE section = 'victim'")}
    con.close()
    assert values == {"TAMPERED"}


@pytest.mark.parametrize("sql,kind", [(TRIGGER, "trigger"), (VIEW, "view")])
def test_foreign_triggers_and_views_are_refused_at_open(tmp_path, sql, kind):
    path = _plan(tmp_path / "evil.rpx", sql)
    with pytest.raises(StoreError, match=kind):
        PlanStore.open(path, create=False)
    with pytest.raises(StoreError, match=kind):
        PlanStore.open(path, create=False, readonly=True)
    assert kind in (plan_registry.check_plan_file(path) or "")


def test_the_trigger_never_fires_because_the_open_is_refused(tmp_path):
    path = _plan(tmp_path / "evil.rpx", TRIGGER)
    before = _digest(path)
    with pytest.raises(StoreError):
        PlanStore.open(path, create=False)
    assert _digest(path) == before  # nothing written: no migration, no journal-mode change that alters content


def test_an_old_plan_with_a_trigger_is_refused_before_the_upgrade_runs(tmp_path):
    path = _plan(tmp_path / "old.rpx", TRIGGER)
    con = sqlite3.connect(path)
    con.execute(f"PRAGMA user_version = {PLAN_SCHEMA_VERSION - 1}")
    con.commit()
    con.close()
    with pytest.raises(StoreError, match="trigger"):
        PlanStore.open(path, create=False)
    con = sqlite3.connect(path)
    assert con.execute("PRAGMA user_version").fetchone()[0] == PLAN_SCHEMA_VERSION - 1  # the migration never started
    con.close()


def test_read_only_validation_refuses_hostile_objects_and_never_modifies_the_file(tmp_path):
    path = _plan(tmp_path / "evil.rpx", TRIGGER)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=DELETE")
    con.close()
    before = _digest(path)
    error = validate_plan_db(path, PLAN_FILE_TABLES)
    assert error and "trigger" in error
    assert _digest(path) == before
