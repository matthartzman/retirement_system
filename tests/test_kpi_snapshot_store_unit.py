"""Unit coverage for the KPI snapshot archive (Wave 1 item 1.15 --
documentation/reports/SYSTEM_REVIEW_2026-08-31.md, finding F13 and the §3.2
cross-cutting note on why a snapshot series must exist before the engine/
policy changes that move "probability of success").

These exercise src.local_store's save/list/get/compare/prune functions
directly against a throwaway SQLite file -- no workbook build, no subprocess
-- mirroring the style of test_snapshot_and_backup_retention_regression.py's
coverage of the sibling result_snapshots table. The full build-time wiring
(workbook_builder.py calling save_kpi_snapshot() at the end of a real build,
and the /api/kpi-snapshots* routes) is covered separately by
test_kpi_snapshot_archive_functional.py, which is slow because it spawns two
real workbook builds.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src import local_store


def _count(db: Path) -> int:
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT COUNT(*) FROM kpi_snapshots").fetchone()[0]
    finally:
        con.close()


def _sample_kpis(i: int) -> dict:
    return {
        "probability_of_success": 0.90 + i * 0.001,
        "terminal_nw_deterministic": 1_000_000.0 + i,
        "terminal_nw_mc_median": 950_000.0 + i,
        "terminal_nw_mc_p10": 500_000.0 + i,
        "terminal_nw_mc_p90": 1_500_000.0 + i,
        "lifetime_tax": 200_000.0 + i,
        "lcv": 3_000_000.0 + i,
        "eltr": 0.18,
        "fcv": 3_200_000.0 + i,
        "eftr": 0.20,
        "total_roth_conversions": 50_000.0 + i,
        "after_tax_terminal_nw": 900_000.0 + i,
    }


def test_save_and_get_kpi_snapshot_round_trips(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    snapshot_id = local_store.save_kpi_snapshot(
        _sample_kpis(0), build_id="build-1", created_at="2026-08-04T00:00:00Z", db_path=db
    )

    fetched = local_store.get_kpi_snapshot(snapshot_id, db_path=db)

    assert fetched is not None
    assert fetched["build_id"] == "build-1"
    assert fetched["created_at"] == "2026-08-04T00:00:00Z"
    assert fetched["probability_of_success"] == pytest.approx(0.90)
    assert fetched["terminal_nw_deterministic"] == pytest.approx(1_000_000.0)


def test_get_kpi_snapshot_by_build_id(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    local_store.save_kpi_snapshot(_sample_kpis(0), build_id="build-a", created_at="2026-08-04T00:00:00Z", db_path=db)
    local_store.save_kpi_snapshot(_sample_kpis(1), build_id="build-b", created_at="2026-08-11T00:00:00Z", db_path=db)

    by_id = local_store.get_kpi_snapshot_by_build_id("build-b", db_path=db)

    assert by_id is not None
    assert by_id["build_id"] == "build-b"
    assert by_id["created_at"] == "2026-08-11T00:00:00Z"


def test_list_kpi_snapshots_orders_newest_first(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    local_store.save_kpi_snapshot(_sample_kpis(0), build_id="build-a", created_at="2026-08-04T00:00:00Z", db_path=db)
    local_store.save_kpi_snapshot(_sample_kpis(1), build_id="build-b", created_at="2026-08-11T00:00:00Z", db_path=db)

    snapshots = local_store.list_kpi_snapshots(db_path=db)

    assert [s["build_id"] for s in snapshots] == ["build-b", "build-a"]


def test_kpi_snapshots_are_capped_at_retention(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    for i in range(local_store.DEFAULT_KPI_SNAPSHOT_RETENTION + 15):
        local_store.save_kpi_snapshot(_sample_kpis(i), build_id=f"build-{i}", created_at=f"2026-08-{(i % 28) + 1:02d}T00:00:00Z", db_path=db)

    assert _count(db) == local_store.DEFAULT_KPI_SNAPSHOT_RETENTION


def test_explicit_prune_trims_existing_backlog(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    for i in range(20):
        local_store.save_kpi_snapshot(_sample_kpis(i), build_id=f"build-{i}", created_at=f"2026-08-{(i % 28) + 1:02d}T00:00:00Z", db_path=db)

    removed = local_store.prune_kpi_snapshots(keep=3, db_path=db)

    assert _count(db) == 3
    assert removed == local_store.DEFAULT_KPI_SNAPSHOT_RETENTION - 3


def test_prune_kpi_snapshots_is_safe_on_missing_db(tmp_path: Path) -> None:
    assert local_store.prune_kpi_snapshots(db_path=tmp_path / "nope.db") == 0


def test_compare_kpi_snapshots_computes_delta_and_pct_change(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    id_a = local_store.save_kpi_snapshot(_sample_kpis(0), build_id="build-a", created_at="2026-08-04T00:00:00Z", db_path=db)
    id_b = local_store.save_kpi_snapshot(
        {**_sample_kpis(0), "probability_of_success": 0.95, "lifetime_tax": 180_000.0},
        build_id="build-b", created_at="2026-08-11T00:00:00Z", db_path=db,
    )

    diff = local_store.compare_kpi_snapshots(from_id=id_a, to_id=id_b, db_path=db)

    assert diff is not None
    assert diff["success"] is True
    assert diff["schema"] == "kpi_snapshot_compare_v1"
    assert diff["from"]["build_id"] == "build-a"
    assert diff["to"]["build_id"] == "build-b"
    prob = diff["diff"]["probability_of_success"]
    assert prob["from"] == pytest.approx(0.90)
    assert prob["to"] == pytest.approx(0.95)
    assert prob["delta"] == pytest.approx(0.05)
    assert prob["pct_change"] == pytest.approx(0.05 / 0.90)
    tax = diff["diff"]["lifetime_tax"]
    assert tax["delta"] == pytest.approx(180_000.0 - 200_000.0)


def test_compare_kpi_snapshots_defaults_to_the_two_most_recent(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    local_store.save_kpi_snapshot(_sample_kpis(0), build_id="build-a", created_at="2026-08-04T00:00:00Z", db_path=db)
    local_store.save_kpi_snapshot(_sample_kpis(1), build_id="build-b", created_at="2026-08-11T00:00:00Z", db_path=db)

    diff = local_store.compare_kpi_snapshots(db_path=db)

    assert diff is not None
    assert diff["from"]["build_id"] == "build-a"
    assert diff["to"]["build_id"] == "build-b"


def test_compare_kpi_snapshots_returns_none_with_fewer_than_two(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    local_store.save_kpi_snapshot(_sample_kpis(0), build_id="build-a", created_at="2026-08-04T00:00:00Z", db_path=db)

    assert local_store.compare_kpi_snapshots(db_path=db) is None


def test_compare_kpi_snapshots_falls_back_to_recent_when_an_id_is_unresolved(tmp_path: Path) -> None:
    """An unresolved id falls back to the most recent snapshots rather than
    hard-failing, same as omitting it -- it only returns None when there
    still aren't two snapshots to compare (see the test below)."""
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    local_store.save_kpi_snapshot(_sample_kpis(0), build_id="build-a", created_at="2026-08-04T00:00:00Z", db_path=db)
    local_store.save_kpi_snapshot(_sample_kpis(1), build_id="build-b", created_at="2026-08-11T00:00:00Z", db_path=db)

    diff = local_store.compare_kpi_snapshots(from_id="does-not-exist", db_path=db)

    assert diff is not None
    assert diff["from"]["build_id"] == "build-a"
    assert diff["to"]["build_id"] == "build-b"


def test_compare_kpi_snapshots_returns_none_when_unresolved_id_leaves_fewer_than_two(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    local_store.save_kpi_snapshot(_sample_kpis(0), build_id="build-a", created_at="2026-08-04T00:00:00Z", db_path=db)

    assert local_store.compare_kpi_snapshots(from_id="does-not-exist", db_path=db) is None
