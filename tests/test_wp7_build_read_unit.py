"""WP7.1: the build reads the plan file through one read transaction (``active_plan.build_read``).

Inside the block every active-plan reader (rows, flat datasets, fingerprint) sees the state the
build started from, even when another connection edits the plan; the build's own write moves
the view forward; other threads are never pinned; the requested revision travels in the env.
"""
from __future__ import annotations

import threading

from src import active_plan
from src.active_plan import PLAN_DB_ENV, PLAN_REVISION_ENV, build_read, plan_db_env
from src.stores import PlanStore
from tests.plan_fixture import make_plan, write_plan_dataset


def _use(plan, monkeypatch):
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.setenv(PLAN_DB_ENV, str(plan.plan_db))
    monkeypatch.delenv(PLAN_REVISION_ENV, raising=False)


def _other_writer_edits(plan):
    with PlanStore.open(plan.plan_db, create=False) as store:
        row = store.all_rows()[0]
        store.set_row(row["row_id"], value=str(row["value"]) + "-edited")
    write_plan_dataset(plan.root, "client_liabilities.csv", "Name,Balance\nEdited,1\n")


def test_reads_inside_the_build_see_one_state(tmp_path, monkeypatch):
    plan = make_plan(tmp_path)
    _use(plan, monkeypatch)
    before_rows = active_plan.active_plan_data()
    before_liab = active_plan.active_dataset_text("liabilities")
    with build_read() as read:
        start_revision = read.revision
        _other_writer_edits(plan)
        assert active_plan.active_plan_data() == before_rows
        assert active_plan.peek_plan_data() == before_rows
        assert active_plan.active_dataset_text("liabilities") == before_liab
        assert active_plan.plan_file_fingerprint(plan.plan_db)[0] == start_revision
    # after the block the reader opens the file again and sees the edit
    assert active_plan.active_plan_data() != before_rows
    assert "Edited" in (active_plan.active_dataset_text("liabilities") or "")


def test_the_builds_own_write_is_visible(tmp_path, monkeypatch):
    plan = make_plan(tmp_path)
    _use(plan, monkeypatch)
    with build_read():
        active_plan.write_active_dataset("hsa_schedule", "year,amount\n2030,5\n")
        assert "2030" in (active_plan.active_dataset_text("hsa_schedule") or "")
        assert active_plan.active_hsa_schedule_saved()


def test_other_threads_are_not_pinned(tmp_path, monkeypatch):
    plan = make_plan(tmp_path)
    _use(plan, monkeypatch)
    seen = {}
    with build_read():
        _other_writer_edits(plan)
        t = threading.Thread(target=lambda: seen.setdefault("text", active_plan.active_dataset_text("liabilities")))
        t.start()
        t.join()
    assert "Edited" in (seen["text"] or "")


def test_release_unpins_and_revision_env_round_trip(tmp_path, monkeypatch):
    plan = make_plan(tmp_path)
    _use(plan, monkeypatch)
    env = plan_db_env({})
    assert env[PLAN_DB_ENV] == str(plan.plan_db)
    monkeypatch.setenv(PLAN_REVISION_ENV, env[PLAN_REVISION_ENV])
    with build_read() as read:
        assert read.revision == env[PLAN_REVISION_ENV] and not read.stale
        read.release()
        _other_writer_edits(plan)
        assert "Edited" in active_plan.active_dataset_text("liabilities")  # reads the file again
    monkeypatch.setenv(PLAN_REVISION_ENV, "0" * 64)
    with build_read() as read:
        assert read.stale
