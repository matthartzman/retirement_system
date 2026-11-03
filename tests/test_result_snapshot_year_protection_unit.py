"""Retention keeps the newest saved run of each plan and projection year, so a December run survives until the January close."""
from pathlib import Path

import itertools

import pytest

from src import cash_year_close as cyc, local_store


@pytest.fixture(autouse=True)
def ticking_clock(monkeypatch):
    """created_at has second precision; give every save its own second so 'newest' is well defined."""
    n = itertools.count()
    monkeypatch.setattr(local_store, "now_utc", lambda: "2026-12-01T00:%02d:%02dZ" % divmod(next(n), 60))


def run(year, n):
    return {"projection_rows": [{"year": year, "_account_withdrawals": {"A_IRA": float(n)}}], "n": n}


def years(db, plan):
    return sorted(s["result"]["projection_rows"][0]["year"] for s in local_store.list_result_snapshots(db, plan_id=plan))


def test_the_newest_run_of_an_earlier_year_survives_pruning(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    local_store.save_result_snapshot(run(2026, 0), plan_snapshot_id="plan_a", db_path=db)            # the December run
    for i in range(1, local_store.DEFAULT_RESULT_SNAPSHOT_RETENTION + 5):                              # many January builds
        local_store.save_result_snapshot(run(2027, i), plan_snapshot_id="plan_a", db_path=db)
    snaps = local_store.list_result_snapshots(db, plan_id="plan_a")
    assert len(snaps) == local_store.DEFAULT_RESULT_SNAPSHOT_RETENTION + 1
    assert 2026 in years(db, "plan_a")
    assert cyc.pick_snapshot(snaps, 2026)["result"]["n"] == 0


def test_only_the_newest_run_per_plan_and_year_is_protected(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    for i in range(3):
        local_store.save_result_snapshot(run(2026, i), plan_snapshot_id="plan_a", db_path=db)
    local_store.save_result_snapshot(run(2026, 9), plan_snapshot_id="plan_b", db_path=db)
    for i in range(10, 10 + local_store.DEFAULT_RESULT_SNAPSHOT_RETENTION):
        local_store.save_result_snapshot(run(2027, i), plan_snapshot_id="plan_c", db_path=db)
    a = [s["result"]["n"] for s in local_store.list_result_snapshots(db, plan_id="plan_a")]
    assert a == [2]                                                  # the newest 2026 run of plan_a, not its older ones
    assert [s["result"]["n"] for s in local_store.list_result_snapshots(db, plan_id="plan_b")] == [9]


def test_runs_without_a_plan_id_or_projection_rows_are_not_protected(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    local_store.save_result_snapshot(run(2026, 0), db_path=db)                                          # legacy: no plan id
    local_store.save_result_snapshot({"n": "no rows"}, plan_snapshot_id="plan_a", db_path=db)
    for i in range(local_store.DEFAULT_RESULT_SNAPSHOT_RETENTION):
        local_store.save_result_snapshot(run(2027, i + 1), plan_snapshot_id="plan_a", db_path=db)
    assert local_store.list_result_snapshots(db, plan_id=None)[-1]["result"].get("n") != 0
    assert len(local_store.list_result_snapshots(db)) == local_store.DEFAULT_RESULT_SNAPSHOT_RETENTION
