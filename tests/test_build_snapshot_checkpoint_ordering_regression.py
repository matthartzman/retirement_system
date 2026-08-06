"""Reported live: "Download Workbook" did nothing (no file, no error) and the
app kept showing the build as stale even right after a successful rebuild.

Root cause: capture_sqlite_database_snapshot() (called at the very end of
workbook_builder.main(), inside write_build_snapshot()) checkpoints the WAL
into the live SQLite .db file immediately before copying it for the .rpx
snapshot. A WAL checkpoint touches the main .db file's mtime even when the
plan's logical content hasn't changed. Because that checkpoint happened
AFTER retirement_plan.xlsx/the PDF/the HTML dashboard/plan_summary.json were
already written, the DB's mtime ended up newer than every one of them --
src/server_services/build_service.py's build_preflight_payload() flags any
essential artifact older than the DB as stale, so `current` came back False
for the build that had JUST finished. The frontend's runBuild() re-derives
lastBuildOk from that `current` flag right after a successful build
(dashboard_decomp_row_model.js's refreshBuildStatus(), called from
runBuild()), silently overwriting the `lastBuildOk = true` the success path
had just set -- so downloadWithBuild() never called downloadFile().

Fix: checkpoint_sqlite_database() is now called once, early, in
workbook_builder.main() -- before any output artifact is written -- so by
the time the artifacts are written they are naturally newer than the
checkpoint-bumped DB. The later checkpoint inside
capture_sqlite_database_snapshot() then has nothing new to flush.
"""
import time
import sqlite3

from src.build_snapshot import checkpoint_sqlite_database


def _open_wal_db_with_uncheckpointed_write(path):
    """Returns an OPEN connection with a committed write still sitting only
    in the -wal sidecar file, not yet folded into the main .db file. Closing
    a connection triggers SQLite's own implicit checkpoint-on-close, which
    would flush the write before this test ever calls
    checkpoint_sqlite_database() -- so the connection must stay open and be
    closed by the caller only after that call."""
    con = sqlite3.connect(str(path))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t(x)")
    con.commit()
    time.sleep(1.1)  # push the main file's mtime measurably into the past
    con.execute("INSERT INTO t VALUES (1)")
    con.commit()
    return con


def test_checkpointing_after_the_artifact_is_written_reproduces_the_regression(tmp_path):
    """This is the OLD, buggy order (capture_sqlite_database_snapshot() ran
    at the end of the build, after every essential artifact). Demonstrating
    it still goes stale here proves the checkpoint call genuinely moves the
    DB's mtime forward when there is real pending WAL data to flush -- not a
    tautology of wall-clock ordering."""
    db_path = tmp_path / "plan.db"
    con = _open_wal_db_with_uncheckpointed_write(db_path)
    try:
        artifact = tmp_path / "retirement_plan.xlsx"
        artifact.write_bytes(b"workbook-bytes")
        artifact_mtime = artifact.stat().st_mtime

        time.sleep(1.1)
        checkpoint_sqlite_database(db_path)

        assert db_path.stat().st_mtime > artifact_mtime, (
            "checkpointing after the artifact was written should leave the "
            "DB newer than the artifact -- this is the exact condition that "
            "made build_preflight_payload() call a freshly finished build "
            "stale"
        )
    finally:
        con.close()


def test_checkpointing_before_the_artifact_is_written_avoids_the_regression(tmp_path):
    """The FIXED order: checkpoint_sqlite_database() runs before any output
    artifact is written (workbook_builder.main(), see the source-order test
    below), so the artifact -- written after -- is never older than the DB."""
    db_path = tmp_path / "plan.db"
    con = _open_wal_db_with_uncheckpointed_write(db_path)
    try:
        checkpoint_sqlite_database(db_path)
        checkpoint_mtime = db_path.stat().st_mtime

        time.sleep(1.1)
        artifact = tmp_path / "retirement_plan.xlsx"
        artifact.write_bytes(b"workbook-bytes")

        assert artifact.stat().st_mtime >= checkpoint_mtime, (
            "an artifact written after checkpoint_sqlite_database() must "
            "not be older than the DB, or build_preflight_payload() will "
            "call the build that just produced it stale"
        )
    finally:
        con.close()


def test_checkpoint_sqlite_database_is_a_safe_noop_for_missing_or_none_path(tmp_path):
    checkpoint_sqlite_database(None)
    checkpoint_sqlite_database(tmp_path / "does_not_exist.db")


def test_workbook_builder_checkpoints_before_writing_any_output_artifact():
    """Source-order guard: the checkpoint call must appear before the first
    output-artifact write in workbook_builder.main(), not after. This is the
    actual ordering the runtime bug depended on -- a real build+status check
    (test_e2e_build_journey.py) would eventually re-catch a regression here
    too, but only on the slow tier and only indirectly."""
    src = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "src" / "reporting" / "workbook_builder.py"
    ).read_text(encoding="utf-8")
    main_start = src.index("\ndef main():")
    checkpoint_call_pos = src.index("checkpoint_sqlite_database(", main_start)
    first_artifact_write_pos = src.index("Saving workbook to", main_start)
    assert checkpoint_call_pos < first_artifact_write_pos, (
        "checkpoint_sqlite_database() must run before the workbook (and every "
        "other essential output artifact) is written -- moving it later "
        "reintroduces the false-stale regression"
    )
