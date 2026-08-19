"""Ticket 287: the at-rest migration must cover DB snapshots, not just input/*.csv.

The DB is canonical -- ``local_store.latest_sectioned_data()`` reads
``plan_snapshots.sectioned_json`` directly. Before this ticket the at-rest
migration rewrote only ``input/*.csv``, so every snapshot (including the newest
one actually served at runtime) kept its legacy shape and was re-normalized on
every single load, forever.

Kept in its own module rather than appended to ``test_plan_data_migration.py``
because that file already defines a ``_sectioned(content)`` helper with a
different signature; two helpers of the same name in one module is exactly the
kind of quiet shadowing that makes a test assert something other than what its
name claims.
"""
from __future__ import annotations

import json
import sqlite3

import pytest


def _seed_snapshots(db, rows):
    """Insert ``(snapshot_id, created_at, sectioned_dict)`` rows into a fresh store."""
    from src.local_store import init_local_store

    init_local_store(db)
    with sqlite3.connect(db) as con:
        for snapshot_id, created_at, sectioned in rows:
            con.execute(
                "INSERT INTO plan_snapshots(snapshot_id, created_at, source, input_json,"
                " sectioned_json, input_sha256) VALUES(?,?,?,?,?,?)",
                (snapshot_id, created_at, "test", "{}", json.dumps(sectioned), "x" * 8),
            )


def _snapshot(db, snapshot_id):
    with sqlite3.connect(db) as con:
        row = con.execute(
            "SELECT sectioned_json FROM plan_snapshots WHERE snapshot_id=?",
            (snapshot_id,),
        ).fetchone()
    return json.loads(row[0])


def _legacy():
    return {"Household": {"": {"husband_name": "Matt"}}}


def _empty_input(tmp_path):
    work = tmp_path / "input"
    work.mkdir()
    return work


def test_every_snapshot_is_migrated_not_only_the_latest(tmp_path):
    """The reason this ticket exists. An older snapshot is restorable, so leaving
    it legacy after the version is stamped lets a restore resurrect shapes the
    gate believes are gone -- permanently, because the gate then skips the store.
    """
    from src.plan_data_migration import migrate_plan_data_at_rest

    db = tmp_path / "s.sqlite"
    _seed_snapshots(db, [
        ("old", "2026-01-01T00:00:00Z", _legacy()),
        ("mid", "2026-02-01T00:00:00Z", _legacy()),
        ("new", "2026-03-01T00:00:00Z", _legacy()),
    ])

    report = migrate_plan_data_at_rest(_empty_input(tmp_path), db_path=db)

    assert report["snapshots"] == 3, "every snapshot row must migrate, not just the newest"
    for snapshot_id in ("old", "mid", "new"):
        household = _snapshot(db, snapshot_id)["Household"][""]
        assert "member_1_name" in household, f"snapshot {snapshot_id} was left un-migrated"
        assert "husband_name" not in household


def test_snapshot_migration_preserves_which_snapshot_is_latest(tmp_path):
    """``latest_sectioned_data()`` orders by ``created_at DESC, rowid DESC``. That
    rowid tie-break is deliberate and load-bearing for same-second saves, so the
    sweep must not disturb which row wins -- especially when created_at ties.
    """
    from src.local_store import latest_sectioned_data
    from src.plan_data_migration import migrate_plan_data_at_rest

    db = tmp_path / "s.sqlite"
    same_second = "2026-05-05T00:00:00Z"
    _seed_snapshots(db, [
        ("first", same_second, {"Household": {"": {"husband_name": "First"}}}),
        ("second", same_second, {"Household": {"": {"husband_name": "Second"}}}),
    ])
    before = latest_sectioned_data(db)["Household"][""]["husband_name"]
    assert before == "Second", "precondition: the higher rowid wins the created_at tie"

    migrate_plan_data_at_rest(_empty_input(tmp_path), db_path=db)

    after = latest_sectioned_data(db)["Household"][""]
    assert after["member_1_name"] == "Second", "the sweep changed which snapshot is latest"


def test_snapshot_migration_preserves_current_key_wins(tmp_path):
    """``migrate_rows`` semantics are load-bearing: a legacy row colliding with an
    existing current row is DROPPED, never overwritten. The snapshot path must
    not weaken that.
    """
    from src.plan_data_migration import migrate_plan_data_at_rest

    db = tmp_path / "s.sqlite"
    _seed_snapshots(db, [(
        "collide", "2026-01-01T00:00:00Z",
        {"Household": {"": {"member_1_name": "Current", "husband_name": "Legacy"}}},
    )])

    migrate_plan_data_at_rest(_empty_input(tmp_path), db_path=db)

    household = _snapshot(db, "collide")["Household"][""]
    assert household["member_1_name"] == "Current", "the legacy row overwrote the current one"
    assert "husband_name" not in household


def test_dry_run_reports_without_writing_snapshots_or_stamping(tmp_path):
    from src.plan_data_migration import migrate_plan_data_at_rest, stored_schema_version

    db = tmp_path / "s.sqlite"
    _seed_snapshots(db, [("a", "2026-01-01T00:00:00Z", _legacy())])

    report = migrate_plan_data_at_rest(_empty_input(tmp_path), db_path=db, dry_run=True)

    assert report["snapshots"] == 1, "a dry run must still report what would change"
    assert "husband_name" in _snapshot(db, "a")["Household"][""], "dry run wrote to the DB"
    assert stored_schema_version(db_path=db) == 0, "dry run stamped the schema version"


def test_snapshot_migration_is_idempotent(tmp_path):
    from src.plan_data_migration import migrate_plan_data_at_rest

    db = tmp_path / "s.sqlite"
    _seed_snapshots(db, [("a", "2026-01-01T00:00:00Z", _legacy())])
    work = _empty_input(tmp_path)

    first = migrate_plan_data_at_rest(work, db_path=db)
    second = migrate_plan_data_at_rest(work, db_path=db)

    assert first["snapshots"] == 1
    assert second["skipped"] is True
    assert second["snapshots"] == 0


def test_a_failed_sweep_does_not_stamp_the_version(tmp_path, monkeypatch):
    """Atomicity at the caller boundary. Stamping over a sweep that died would mean
    the un-migrated remainder is skipped forever, and the store would report
    "migrated" while still holding legacy shapes.
    """
    import src.local_store as local_store
    from src.plan_data_migration import migrate_plan_data_at_rest, stored_schema_version

    db = tmp_path / "s.sqlite"
    _seed_snapshots(db, [
        ("a", "2026-01-01T00:00:00Z", _legacy()),
        ("b", "2026-02-01T00:00:00Z", _legacy()),
    ])

    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated DB failure mid-sweep")

    monkeypatch.setattr(local_store, "rewrite_sectioned_snapshots", boom)

    report = migrate_plan_data_at_rest(_empty_input(tmp_path), db_path=db)

    assert stored_schema_version(db_path=db) == 0, (
        "the version was stamped over a sweep that never completed"
    )
    assert report["snapshots"] == 0
    assert "husband_name" in _snapshot(db, "a")["Household"][""], (
        "rows changed despite the sweep failing"
    )
    # Final-review finding (2026-08-19): a failed sweep used to be silently
    # indistinguishable from "nothing needed migrating" -- same report shape,
    # no way to tell the two apart from the return value. That is what let a
    # persistently-failing sweep retry forever with nothing visible saying so.
    assert "error" in report, "a failed sweep must be reported, not silently indistinguishable from success"
    assert "simulated DB failure mid-sweep" in report["error"]


def test_successful_sweep_reports_no_error_key(tmp_path):
    """The 'error' key's absence, not a falsy value, is the success signal --
    report.get("error") must be the only check a caller needs."""
    import src.local_store as local_store
    from src.plan_data_migration import migrate_plan_data_at_rest

    db = tmp_path / "s.sqlite"
    _seed_snapshots(db, [("a", "2026-01-01T00:00:00Z", _legacy())])

    report = migrate_plan_data_at_rest(_empty_input(tmp_path), db_path=db)

    assert "error" not in report


def test_partial_sweep_rolls_back_rather_than_half_migrating(tmp_path):
    """One transaction: if the transform raises on the second row, the first row's
    UPDATE must roll back with it. A half-migrated store is the worst outcome --
    it looks fine and is silently inconsistent.
    """
    from src.local_store import rewrite_sectioned_snapshots
    from src.plan_data_migration import migrate_sectioned_data

    db = tmp_path / "s.sqlite"
    _seed_snapshots(db, [
        ("a", "2026-01-01T00:00:00Z", _legacy()),
        ("b", "2026-02-01T00:00:00Z", _legacy()),
    ])
    calls = {"n": 0}

    def transform(data):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated failure on the second row")
        return migrate_sectioned_data(data)

    with pytest.raises(RuntimeError):
        rewrite_sectioned_snapshots(transform, db_path=db)

    with sqlite3.connect(db) as con:
        bodies = [r[0] for r in con.execute("SELECT sectioned_json FROM plan_snapshots")]
    assert all("husband_name" in body for body in bodies), (
        "a partial sweep left some rows migrated -- the transaction did not roll back"
    )


def test_sweep_is_a_no_op_when_the_store_does_not_exist(tmp_path):
    """Startup must never be fatal: a missing store is the first-run case."""
    from src.local_store import rewrite_sectioned_snapshots
    from src.plan_data_migration import migrate_sectioned_data

    assert rewrite_sectioned_snapshots(
        migrate_sectioned_data, db_path=tmp_path / "does_not_exist.sqlite"
    ) == 0
