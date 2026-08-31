"""Two real workbook builds a week apart produce a comparable KPI series
(Wave 1 item 1.15 -- documentation/reports/SYSTEM_REVIEW_2026-08-31.md,
finding F13, and the §3.2 cross-cutting note explaining why this must land
*before* the four items that move the headline probability of success).

Deliberately NOT built on the shared conftest.built_workbook_dir/
built_workbook_path fixtures: those build once per test SESSION into the
shared test workspace's local_state db under a single fixed
RETIREMENT_SYSTEM_FROZEN_TODAY, and this test genuinely needs two builds
under two *different* frozen dates landing in a database this test can make
exact assertions against -- a configuration the shared fixture cannot
provide. Per CLAUDE.md's Testing Discipline ("When your test genuinely needs
a different module configuration... scope your own build to a
module-or-narrower fixture so it's still paid for once per file, not once
per test, and mark it slow regardless"), the two builds are scoped to one
module-level fixture shared by every test in this file, and every test using
it is marked slow.

Building into its own throwaway workspace (rather than the shared session
workspace) also makes this test immune to the KPI-snapshot retention cap:
other slow tests building concurrently under -n auto write into the SHARED
session workspace's local_state db, and with DEFAULT_KPI_SNAPSHOT_RETENTION
== 10 a large parallel sweep (e.g. test_all_modules_off_build_functional.py's
~24 builds) could prune this test's own rows out from under it before it
gets to assert on them, if it shared that database.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from src import local_store, platform_runtime
from src.config_backend import export_client_json_yaml

ROOT = Path(__file__).resolve().parents[1]
_FROZEN_PLAN_DIR = ROOT / "tests" / "fixtures" / "sample_plan_frozen"

# A week apart, and deliberately distinct from tests/conftest.py's shared
# session date (FROZEN_PLAN_TODAY = "2026-08-04") so a snapshot written by
# some other test into a different database is never mistakable for one of
# these two rows.
BUILD_DATE_A = "2026-09-07"
BUILD_DATE_B = "2026-09-14"
BUILD_ID_A = "kpi_archive_test_build_a"
BUILD_ID_B = "kpi_archive_test_build_b"


def _seed_workspace(workspace_root: Path) -> None:
    """Populate an isolated workspace the same way tests/conftest.py seeds
    the shared session workspace: the committed frozen sample plan, not the
    live input/ (which changes under real usage and isn't safe to assert
    dollar figures against)."""
    for name in platform_runtime.WORKSPACE_SUBDIRS:
        (workspace_root / name).mkdir(parents=True, exist_ok=True)
    input_dir = workspace_root / "input"
    for f in sorted(_FROZEN_PLAN_DIR.iterdir()):
        if f.is_file():
            shutil.copy(f, input_dir / f.name)
    export_client_json_yaml(input_dir / "client_data.csv", input_dir)


def _run_build(workspace_root: Path, output_dir: Path, *, frozen_today: str, build_id: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["RETIREMENT_SYSTEM_WORKSPACE_ROOT"] = str(workspace_root)
    env["RETIREMENT_SYSTEM_OUTPUT_DIR"] = str(output_dir)
    env["RETIREMENT_SYSTEM_APP_MODE"] = "LOCAL"
    env["RETIREMENT_SYSTEM_WORKSPACE_ID"] = "local"
    env["RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS"] = "1"
    env["RETIREMENT_SYSTEM_FROZEN_TODAY"] = frozen_today
    env["RETIREMENT_SYSTEM_BUILD_ID"] = build_id
    env.setdefault("RETIREMENT_MC_SIMS", "16")
    env.setdefault("RETIREMENT_MC_SENSITIVITY_SIMS", "3")
    result = subprocess.run(
        [sys.executable, "tools/build_workbook.py"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=180,
    )
    assert result.returncode == 0, (result.stdout + result.stderr)[-4000:]
    return result


@pytest.fixture(scope="module")
def two_kpi_builds(tmp_path_factory):
    workspace_root = tmp_path_factory.mktemp("kpi_archive_ws")
    _seed_workspace(workspace_root)
    out_a = tmp_path_factory.mktemp("kpi_archive_build_a")
    out_b = tmp_path_factory.mktemp("kpi_archive_build_b")
    _run_build(workspace_root, out_a, frozen_today=BUILD_DATE_A, build_id=BUILD_ID_A)
    _run_build(workspace_root, out_b, frozen_today=BUILD_DATE_B, build_id=BUILD_ID_B)
    return {
        "db_path": workspace_root / "local_state" / "retirement_system_v10.db",
        "out_a": out_a,
        "out_b": out_b,
    }


@pytest.mark.slow
def test_each_build_writes_its_own_plan_summary(two_kpi_builds):
    """Sanity check the fixture itself before trusting the snapshot
    assertions built on top of it."""
    summary_a = json.loads((two_kpi_builds["out_a"] / "plan_summary.json").read_text(encoding="utf-8"))
    summary_b = json.loads((two_kpi_builds["out_b"] / "plan_summary.json").read_text(encoding="utf-8"))
    assert summary_a["build_id"] == BUILD_ID_A
    assert summary_b["build_id"] == BUILD_ID_B


@pytest.mark.slow
def test_two_builds_a_week_apart_produce_two_retrievable_kpi_snapshots(two_kpi_builds):
    db_path = two_kpi_builds["db_path"]

    snapshots = local_store.list_kpi_snapshots(limit=10, db_path=db_path)

    assert len(snapshots) == 2
    build_ids = {s["build_id"] for s in snapshots}
    assert build_ids == {BUILD_ID_A, BUILD_ID_B}
    dates = {s["created_at"] for s in snapshots}
    assert dates == {f"{BUILD_DATE_A}T00:00:00Z", f"{BUILD_DATE_B}T00:00:00Z"}


@pytest.mark.slow
def test_archived_kpi_values_match_each_builds_own_plan_summary(two_kpi_builds):
    db_path = two_kpi_builds["db_path"]
    summary_a = json.loads((two_kpi_builds["out_a"] / "plan_summary.json").read_text(encoding="utf-8"))
    summary_b = json.loads((two_kpi_builds["out_b"] / "plan_summary.json").read_text(encoding="utf-8"))

    snap_a = local_store.get_kpi_snapshot_by_build_id(BUILD_ID_A, db_path=db_path)
    snap_b = local_store.get_kpi_snapshot_by_build_id(BUILD_ID_B, db_path=db_path)

    assert snap_a is not None and snap_b is not None
    for snap, summary in ((snap_a, summary_a), (snap_b, summary_b)):
        assert snap["probability_of_success"] == pytest.approx(summary["mc_success"])
        assert snap["terminal_nw_deterministic"] == pytest.approx(summary["terminal_nw"])
        assert snap["lifetime_tax"] == pytest.approx(summary["lifetime_tax"])
        assert snap["lcv"] == pytest.approx(summary["lcv"])
        assert snap["eltr"] == pytest.approx(summary["eltr"])
        assert snap["fcv"] == pytest.approx(summary["fcv"])
        assert snap["eftr"] == pytest.approx(summary["eftr"])
        assert snap["total_roth_conversions"] == pytest.approx(summary["total_roth_conversions"])
        assert snap["after_tax_terminal_nw"] == pytest.approx(summary["after_tax_terminal_nw"])


@pytest.mark.slow
def test_compare_kpi_snapshots_diffs_the_two_builds(two_kpi_builds):
    db_path = two_kpi_builds["db_path"]
    snap_a = local_store.get_kpi_snapshot_by_build_id(BUILD_ID_A, db_path=db_path)
    snap_b = local_store.get_kpi_snapshot_by_build_id(BUILD_ID_B, db_path=db_path)

    diff = local_store.compare_kpi_snapshots(from_id=snap_a["snapshot_id"], to_id=snap_b["snapshot_id"], db_path=db_path)

    assert diff is not None
    assert diff["success"] is True
    assert diff["schema"] == "kpi_snapshot_compare_v1"
    assert diff["from"]["build_id"] == BUILD_ID_A
    assert diff["to"]["build_id"] == BUILD_ID_B
    for key in local_store.KPI_SNAPSHOT_METRICS:
        entry = diff["diff"][key]
        assert entry["from"] == snap_a.get(key)
        assert entry["to"] == snap_b.get(key)
        if isinstance(entry["from"], (int, float)) and isinstance(entry["to"], (int, float)) and entry["from"]:
            assert entry["delta"] == pytest.approx(entry["to"] - entry["from"])
            assert entry["pct_change"] == pytest.approx(entry["delta"] / entry["from"])

    # Also defaults to "most recent two" when no ids are given.
    default_diff = local_store.compare_kpi_snapshots(db_path=db_path)
    assert default_diff is not None
    assert default_diff["from"]["build_id"] == BUILD_ID_A
    assert default_diff["to"]["build_id"] == BUILD_ID_B


@pytest.mark.slow
def test_kpi_snapshot_route_helpers_see_the_same_series(two_kpi_builds):
    """The /api/kpi-snapshots* routes (src/server/workbook_routes.py) are
    thin wrappers around list_kpi_snapshots()/compare_kpi_snapshots() with a
    db_path resolved by _sqlite_db() -- exercise those same entry points
    directly against this fixture's db to keep the route wiring honest
    without standing up a full Flask test client for a Wave-1-scoped view."""
    db_path = two_kpi_builds["db_path"]

    snapshots = local_store.list_kpi_snapshots(limit=5, db_path=db_path)
    assert len(snapshots) == 2

    compared = local_store.compare_kpi_snapshots(db_path=db_path)
    assert compared["schema"] == "kpi_snapshot_compare_v1"
