from pathlib import Path

from src.active_plan import read_build_results, write_build_results
from src.build_snapshot import make_build_snapshot


def test_ytd_and_plan_file_services_exist_and_are_runtime_independent():
    ytd = Path("src/server_services/ytd_service.py").read_text(encoding="utf-8")
    plan_file = Path("src/server_services/plan_file_service.py").read_text(encoding="utf-8")
    assert "class YtdService" in ytd
    assert "YtdServiceContext" in ytd
    assert "class PlanFileService" in plan_file
    assert "PlanFileServiceContext" in plan_file
    # HTTP-runtime-independence itself is asserted once, for every service
    # module, by the AST-based check in test_service_extraction_functional.py.


def test_plan_routes_delegate_ytd_and_plan_file_logic_to_services():
    routes = Path("src/server/plan_routes.py").read_text(encoding="utf-8")
    assert "def _ytd_feature_service()" in routes
    assert "YtdServiceContext" in routes
    assert ".status_payload(period=period)" in routes
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
    assert ".before_load_" in text
    assert "wal_checkpoint(FULL)" in text
    assert "wal_checkpoint(TRUNCATE)" in text
    assert "-wal" in text and "-shm" in text
    assert "plan_loaded_file" in text


def _make_db(path: Path, marker: str) -> None:
    """A plan file (``PlanStore``) holding one marker row: snapshots and Load operate on it."""
    from src.stores import PlanStore

    path.parent.mkdir(parents=True, exist_ok=True)
    with PlanStore.open(path) as store:
        store.set_value("Marker", "", "value", marker)


def test_plan_file_service_owns_snapshot_compare_and_restore(tmp_path):
    from src.server_services.plan_file_service import PlanFileService, PlanFileServiceContext

    active_db = tmp_path / "plan.rpx"
    source_db = tmp_path / "snapshot_source.rpx"
    output = tmp_path / "output"
    audits = []
    _make_db(active_db, "active")
    _make_db(source_db, "snapshot")
    snapshot = make_build_snapshot(output, build_id="phase3", sqlite_db_path=source_db, output_files=[])
    write_build_results("phase3", path=active_db, snapshot=snapshot)

    service = PlanFileService(PlanFileServiceContext(
        sqlite_db=lambda: tmp_path / "local_state" / "retirement_system_v10.db",
        plan_db=lambda: active_db,
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
    from src.stores import PlanStore

    with PlanStore.open(active_db, create=False, readonly=True) as store:
        assert store.sectioned_data()["Marker"][""]["value"] == "snapshot"
    assert read_build_results(path=active_db)["build_id"] == "phase3"  # the build results are carried over
    assert audits and audits[-1][0] == "plan_snapshot_restored"


def test_build_job_service_owns_async_build_orchestration_contract():
    service = Path("src/server_services/build_job_service.py").read_text(encoding="utf-8")
    assert "class BuildJobRegistry" in service
    assert "def run_build_progress_job" in service
    assert "subprocess.Popen" in service
    assert "stderr=subprocess.STDOUT" in service
    assert "def build_progress_from_line" in service
    assert "def build_error_message" in service
    # HTTP-runtime-independence itself is asserted once, for every service
    # module, by the AST-based check in test_service_extraction_functional.py.


def test_workbook_routes_keep_thin_build_job_adapter():
    routes = Path("src/server/workbook_routes.py").read_text(encoding="utf-8")
    assert "_BUILD_JOBS = build_job_service.BuildJobRegistry()" in routes
    assert "build_job_service.run_build_progress_job(" in routes
    assert "_BUILD_JOBS.create(job_id" in routes
    assert "_BUILD_JOBS.prune_older_than(3600)" in routes
    assert "_BUILD_PROGRESS_LOCK" not in routes
    assert "_BUILD_PROGRESS_JOBS" not in routes
