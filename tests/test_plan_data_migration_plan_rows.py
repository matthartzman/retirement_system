"""Ticket 287, since WP4.2: the at-rest migration covers the plan file's rows, not only
input/*.csv.

The plan file is canonical: ``load_active_config()`` reads ``plan_rows`` of the active
plan (``src/active_plan.py``). Ticket 287 made the at-rest migration sweep the old
sectioned SQLite snapshots for the same reason; WP4.2 retired those snapshots, so the
sweep now migrates the plan file's rows in place (``_migrate_plan_file_rows``).
"""
from __future__ import annotations

import pytest

from src.stores import PlanStore


def _plan(path, rows):
    with PlanStore.open(path) as store:
        for section, subsection, label, value in rows:
            store.insert_row(section, subsection=subsection, label=label, value=value)
    return path


def _rows(path):
    with PlanStore.open(path, readonly=True) as store:
        return [(r["row_id"], r["section"], r["subsection"], r["label"], r["value"]) for r in store.all_rows()]


def _legacy_rows():
    return [("Household", "", "husband_name", "Matt"), ("Household", "", "wife_name", "Pat")]


def _empty_input(tmp_path):
    work = tmp_path / "input"
    work.mkdir()
    return work


def test_plan_rows_are_migrated_in_place_keeping_row_ids(tmp_path):
    from src.plan_data_migration import migrate_plan_data_at_rest

    plan = _plan(tmp_path / "plan.rpx", _legacy_rows())
    before = _rows(plan)
    report = migrate_plan_data_at_rest(_empty_input(tmp_path), db_path=tmp_path / "s.sqlite", plan_path=plan)

    assert report["plan_rows"] == 2 and "error" not in report
    after = _rows(plan)
    assert [r[3] for r in after] == ["member_1_name", "member_2_name"]
    assert [r[0] for r in after] == [r[0] for r in before], "a renamed row must keep its row_id"
    with PlanStore.open(plan, readonly=True) as store:
        assert store.sectioned_data() == {"Household": {"": {"member_1_name": "Matt", "member_2_name": "Pat"}}}


def test_plan_row_migration_preserves_current_key_wins(tmp_path):
    """``migrate_rows`` semantics are load-bearing: a legacy row colliding with an existing
    current row is DROPPED, never overwritten."""
    from src.plan_data_migration import migrate_plan_data_at_rest

    plan = _plan(tmp_path / "plan.rpx", [("Household", "", "member_1_name", "Current"),
                                         ("Household", "", "husband_name", "Legacy")])
    migrate_plan_data_at_rest(_empty_input(tmp_path), db_path=tmp_path / "s.sqlite", plan_path=plan)

    with PlanStore.open(plan, readonly=True) as store:
        assert store.sectioned_data() == {"Household": {"": {"member_1_name": "Current"}}}


def test_dry_run_reports_without_writing_plan_rows_or_stamping(tmp_path):
    from src.plan_data_migration import migrate_plan_data_at_rest, stored_schema_version

    db = tmp_path / "s.sqlite"
    plan = _plan(tmp_path / "plan.rpx", _legacy_rows())
    before = _rows(plan)
    report = migrate_plan_data_at_rest(_empty_input(tmp_path), db_path=db, dry_run=True, plan_path=plan)

    assert report["plan_rows"] == 2, "a dry run must still report what would change"
    assert _rows(plan) == before, "dry run wrote to the plan file"
    assert stored_schema_version(db_path=db) == 0, "dry run stamped the schema version"


def test_plan_row_migration_is_idempotent(tmp_path):
    from src.plan_data_migration import migrate_plan_data_at_rest

    db = tmp_path / "s.sqlite"
    plan = _plan(tmp_path / "plan.rpx", _legacy_rows())
    work = _empty_input(tmp_path)

    first = migrate_plan_data_at_rest(work, db_path=db, plan_path=plan)
    second = migrate_plan_data_at_rest(work, db_path=db, plan_path=plan)

    assert first["plan_rows"] == 2
    assert second["skipped"] is True and second["plan_rows"] == 0


def test_a_failed_sweep_does_not_stamp_the_version(tmp_path, monkeypatch):
    """Stamping over a sweep that died would mean the un-migrated remainder is skipped
    forever, and the store would report "migrated" while still holding legacy shapes."""
    import src.plan_data_migration as pdm

    db = tmp_path / "s.sqlite"
    plan = _plan(tmp_path / "plan.rpx", _legacy_rows())
    before = _rows(plan)

    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated store failure mid-sweep")

    monkeypatch.setattr(pdm, "_migrate_plan_file_rows", boom)
    report = pdm.migrate_plan_data_at_rest(_empty_input(tmp_path), db_path=db, plan_path=plan)

    assert pdm.stored_schema_version(db_path=db) == 0, "the version was stamped over a sweep that never completed"
    assert report["plan_rows"] == 0
    assert _rows(plan) == before
    assert "simulated store failure mid-sweep" in report["error"]


def test_partial_sweep_rolls_back_rather_than_half_migrating(tmp_path, monkeypatch):
    """One transaction: if the second rename fails, the first must roll back with it."""
    import src.plan_data_migration as pdm

    plan = _plan(tmp_path / "plan.rpx", _legacy_rows())
    before = _rows(plan)
    real_set_row = PlanStore.set_row
    calls = {"n": 0}

    def failing_set_row(self, row_id, **fields):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated failure on the second row")
        return real_set_row(self, row_id, **fields)

    monkeypatch.setattr(PlanStore, "set_row", failing_set_row)
    with pytest.raises(RuntimeError):
        pdm._migrate_plan_file_rows(plan, dry_run=False)
    monkeypatch.undo()
    assert _rows(plan) == before, "a partial sweep left some rows migrated"


def test_sweep_is_a_no_op_when_the_plan_file_does_not_exist(tmp_path):
    """Startup must never be fatal: a missing plan file is the first-run case."""
    from src.plan_data_migration import _migrate_plan_file_rows

    missing = tmp_path / "does_not_exist.rpx"
    assert _migrate_plan_file_rows(missing, dry_run=False) == 0
    assert not missing.exists()
