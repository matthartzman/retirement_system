from pathlib import Path
import sqlite3

from src.build_snapshot import sha256_file, write_build_snapshot


def test_ytd_and_plan_file_services_exist_and_are_runtime_independent():
    ytd = Path("src/server_services/ytd_service.py").read_text(encoding="utf-8")
    plan_file = Path("src/server_services/plan_file_service.py").read_text(encoding="utf-8")
    assert "class YtdService" in ytd
    assert "YtdServiceContext" in ytd
    assert "@app.route" not in ytd
    assert "request.get_json" not in ytd
    assert "class PlanFileService" in plan_file
    assert "PlanFileServiceContext" in plan_file
    assert "@app.route" not in plan_file
    assert "request.get_json" not in plan_file


def test_plan_routes_delegate_ytd_and_plan_file_logic_to_services():
    routes = Path("src/server/plan_routes.py").read_text(encoding="utf-8")
    assert "def _ytd_feature_service()" in routes
    assert "YtdServiceContext" in routes
    assert ".status_payload()" in routes
    assert ".upload_transactions(" in routes
    assert ".bulk_save_transactions(" in routes
    assert "def _plan_file_feature_service()" in routes
    assert "PlanFileServiceContext" in routes
    assert ".exit_snapshot()" in routes
    assert ".save_as(" in routes
    assert ".load_file(" in routes
    assert ".snapshot_compare_payload(" in routes
    assert ".snapshot_restore_payload(" in routes
    assert "read_build_snapshot(" not in routes
    assert "restore_sqlite_database_from_snapshot(" not in routes
    # The old inline implementation should not own the heavy copy/recovery loops.
    assert "legacy_account_setup_candidates" not in routes
    assert "retirement_system_v10.db.before_load" not in routes


def test_plan_file_service_has_load_file_safety_contracts():
    text = Path("src/server_services/plan_file_service.py").read_text(encoding="utf-8")
    assert "Saved plan file not found" in text
    assert "retirement_system_v10.db.before_load_" in text
    assert "wal_checkpoint(FULL)" in text
    assert "wal_checkpoint(TRUNCATE)" in text
    assert "-wal" in text and "-shm" in text
    assert "plan_loaded_file" in text


def _make_db(path: Path, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS marker (value TEXT)")
        conn.execute("DELETE FROM marker")
        conn.execute("INSERT INTO marker(value) VALUES (?)", (marker,))
        conn.commit()
    finally:
        conn.close()


def test_plan_file_service_owns_snapshot_compare_and_restore(tmp_path):
    from src.server_services.plan_file_service import PlanFileService, PlanFileServiceContext

    active_db = tmp_path / "local_state" / "retirement_system_v10.db"
    source_db = tmp_path / "snapshot_source.rpx"
    output = tmp_path / "output"
    audits = []
    _make_db(active_db, "active")
    _make_db(source_db, "snapshot")
    write_build_snapshot(output, build_id="phase3", sqlite_db_path=source_db, output_files=[])

    service = PlanFileService(PlanFileServiceContext(
        sqlite_db=lambda: active_db,
        audit=lambda event, payload: audits.append((event, payload)),
        output_dir=lambda: output,
    ))

    compare, compare_status = service.snapshot_compare_payload({})
    assert compare_status == 200
    assert compare["schema"] == "plan_snapshot_compare_v1"
    assert compare["database_matches"] is False

    restored, restore_status = service.snapshot_restore_payload({"backup_suffix": "phase3"})
    assert restore_status == 200
    assert restored["schema"] == "plan_snapshot_restore_v1"
    assert Path(restored["backup_database"]).exists()
    assert sha256_file(active_db) == sha256_file(source_db)
    assert audits and audits[-1][0] == "plan_snapshot_restored"


def test_build_job_service_owns_async_build_orchestration_contract():
    service = Path("src/server_services/build_job_service.py").read_text(encoding="utf-8")
    assert "class BuildJobRegistry" in service
    assert "def run_build_progress_job" in service
    assert "subprocess.Popen" in service
    assert "stderr=subprocess.STDOUT" in service
    assert "def build_progress_from_line" in service
    assert "def build_error_message" in service
    assert "@app.route" not in service
    assert "request.get_json" not in service


def test_workbook_routes_keep_thin_build_job_adapter():
    routes = Path("src/server/workbook_routes.py").read_text(encoding="utf-8")
    assert "_BUILD_JOBS = build_job_service.BuildJobRegistry()" in routes
    assert "build_job_service.run_build_progress_job(" in routes
    assert "_BUILD_JOBS.create(job_id" in routes
    assert "_BUILD_JOBS.prune_older_than(3600)" in routes
    assert "_BUILD_PROGRESS_LOCK" not in routes
    assert "_BUILD_PROGRESS_JOBS" not in routes
