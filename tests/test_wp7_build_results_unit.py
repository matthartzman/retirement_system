"""WP7.2: ``build_results`` rows of the plan file replace the JSON sidecars."""
import pytest

from src.active_plan import (
    PLAN_DB_ENV, clear_build_results, ensure_plan_file, latest_build_stamp, plan_state, read_build_results,
    write_build_results,
)
from src.build_snapshot import compare_snapshot_to_current, make_build_snapshot
from src.server_services import build_service
from src.stores import PlanStore, ValidationError
from src.stores.build_results import RETENTION


@pytest.fixture
def plan(tmp_path, monkeypatch):
    path = tmp_path / "plan.rpx"
    monkeypatch.setenv(PLAN_DB_ENV, str(path))
    ensure_plan_file(path)
    return path


def test_parts_merge_into_one_row_and_read_back_parsed(plan):
    write_build_results("b1", summary={"qc_result": "QC: 1 / 1 PASS", "x": 1.5})
    write_build_results("b1", plan_state="s", explorer={"schema": "m"})

    row = read_build_results("b1")

    assert row["summary"] == {"qc_result": "QC: 1 / 1 PASS", "x": 1.5}
    assert row["explorer"] == {"schema": "m"}
    assert row["package"] == {} and row["snapshot"] == {}
    assert row["plan_state"] == "s"


def test_latest_build_wins_and_old_rows_are_pruned(plan):
    for i in range(RETENTION + 2):
        write_build_results(f"b{i}", summary={"i": i})
    write_build_results("b0", summary={"i": "rewritten"})  # a rewrite is the newest write

    assert read_build_results()["build_id"] == "b0"
    assert read_build_results("b1") is None  # pruned
    assert latest_build_stamp()[0] == "b0"
    assert clear_build_results() == RETENTION
    assert read_build_results() is None


def test_no_results_without_a_plan_file(tmp_path):
    assert read_build_results(path=tmp_path / "missing.rpx") is None
    assert latest_build_stamp(tmp_path / "missing.rpx") is None


def test_store_rejects_unknown_parts_and_empty_ids(plan):
    with PlanStore.open(plan) as store:
        with pytest.raises(ValidationError):
            store.build_results.put("b", nope={})
        with pytest.raises(ValidationError):
            store.build_results.put("", summary={})


def test_interpret_build_result_reads_the_row_of_this_build(plan):
    write_build_results("old", summary={"qc_result": "QC: 3 / 3 PASS", "build_id": "old"})
    write_build_results("new", summary={"qc_result": "QC: 3 / 3 PASS", "build_id": "new"})

    ok = build_service.interpret_build_result(returncode=0, stdout="", build_id="new")
    missing = build_service.interpret_build_result(returncode=0, stdout="QC: 3 / 3 PASS", build_id="other")

    assert ok.success and ok.summary["build_id"] == "new" and not ok.stale_summary
    assert not missing.success and missing.stale_summary


def test_snapshot_compare_ignores_the_results_stored_in_the_same_file(plan, tmp_path):
    state = plan_state(plan)
    snapshot = make_build_snapshot(tmp_path / "out", build_id="b", plan_state=state, sqlite_db_path=plan, output_files=[])
    write_build_results("b", plan_state=state, snapshot=snapshot)

    assert compare_snapshot_to_current(snapshot, sqlite_db_path=plan)["database_matches"] is True

    with PlanStore.open(plan) as store:
        store.set_value("Marker", "", "value", "edited")
    assert compare_snapshot_to_current(snapshot, sqlite_db_path=plan)["database_matches"] is False
