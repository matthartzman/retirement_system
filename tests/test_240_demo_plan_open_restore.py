"""#240: Open Demo Plan / Open Current Plan toggle.

Exercises DemoPlanService in full isolation (tmp_path DBs/dirs, no real
input/ or local_state/ touched -- these must never be mutated by a test run)
following the same pattern test_152_backend_service_extraction_continuation.py
uses for PlanFileService: a tiny throwaway sqlite DB with a single marker
row, swapped around by the service under test.
"""
import sqlite3
from pathlib import Path

from src.server_services.demo_plan_service import DemoPlanService, DemoPlanServiceContext
from src.server_services.plan_file_service import PlanFileService, PlanFileServiceContext


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


def _read_marker(path: Path) -> str:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("SELECT value FROM marker").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _make_service(tmp_path: Path):
    active_db = tmp_path / "local_state" / "retirement_system_v10.db"
    demo_dir = tmp_path / "input" / "demo"
    demo_dir.mkdir(parents=True, exist_ok=True)
    (demo_dir / "client_household.csv").write_text("demo household content\n", encoding="utf-8")
    # client_income.csv intentionally has no demo counterpart -- exercises "skipped".
    _make_db(active_db, "real-plan")

    audits = []
    written: dict[str, str] = {}

    def write_plan_data_file(name: str, content: str):
        written[name] = content
        return tmp_path / "input" / name

    plan_file_service = PlanFileService(PlanFileServiceContext(
        sqlite_db=lambda: active_db,
        audit=lambda event, payload: audits.append((event, payload)),
        retention_count=10,
    ))

    materialized = {"count": 0}

    service = DemoPlanService(DemoPlanServiceContext(
        sqlite_db=lambda: active_db,
        demo_dir=lambda: demo_dir,
        plan_data_csv_files=["client_household.csv", "client_income.csv"],
        read_plan_data_file=lambda name: None,
        write_plan_data_file=write_plan_data_file,
        sync_config_backends=lambda: {"success": True},
        ensure_user_ui_plan_data_rows=lambda: None,
        load_saved_db=plan_file_service.load_file,
        materialize=lambda: materialized.__setitem__("count", materialized["count"] + 1),
        audit=lambda event, payload: audits.append((event, payload)),
    ))
    return service, active_db, demo_dir, audits, written, materialized


def test_status_is_inactive_before_any_demo_is_opened(tmp_path):
    service, *_ = _make_service(tmp_path)
    assert service.status_payload() == {"success": True, "active": False, "opened_at": None}


def test_open_demo_writes_available_files_reports_skipped_and_backs_up_once(tmp_path):
    service, active_db, demo_dir, audits, written, _ = _make_service(tmp_path)

    result = service.open_demo_payload()

    assert result["success"] is True
    assert written["client_household.csv"] == "demo household content\n"
    assert result["skipped"] == ["client_income.csv"]

    backup = Path(str(active_db) + ".before_demo")
    assert backup.exists()
    assert _read_marker(backup) == "real-plan"

    marker_json = active_db.parent / "demo_mode_marker.json"
    assert marker_json.exists()

    status = service.status_payload()
    assert status["active"] is True
    assert status["opened_at"]
    assert any(event == "demo_plan_opened" for event, _ in audits)


def test_open_demo_twice_does_not_reclobber_the_real_backup(tmp_path):
    service, active_db, demo_dir, audits, written, _ = _make_service(tmp_path)

    service.open_demo_payload()
    # Simulate the live DB now actually holding demo-state content, as it
    # would after write_plan_data_file's real DB writes.
    _make_db(active_db, "demo-state")

    service.open_demo_payload()

    backup = Path(str(active_db) + ".before_demo")
    assert _read_marker(backup) == "real-plan", "second Open Demo Plan click must not overwrite the real backup"


def test_restore_current_when_no_demo_is_active_is_a_safe_noop(tmp_path):
    service, *_ = _make_service(tmp_path)
    assert service.restore_current_payload() == {"success": True, "restored": False}


def test_restore_current_swaps_db_back_and_clears_backup(tmp_path):
    service, active_db, demo_dir, audits, written, materialized = _make_service(tmp_path)

    service.open_demo_payload()
    _make_db(active_db, "demo-state")  # live DB now diverged from the backup

    result = service.restore_current_payload()

    assert result == {"success": True, "restored": True}
    assert _read_marker(active_db) == "real-plan"
    assert materialized["count"] == 1
    assert not Path(str(active_db) + ".before_demo").exists()
    assert not (active_db.parent / "demo_mode_marker.json").exists()
    assert any(event == "demo_plan_restored" for event, _ in audits)

    # Idempotent: a second click with nothing left to restore is a no-op.
    assert service.restore_current_payload() == {"success": True, "restored": False}


def test_plan_routes_wire_demo_plan_service_with_protected_fields_bypassed():
    routes = Path("src/server/plan_routes.py").read_text(encoding="utf-8")
    assert "def _demo_plan_feature_service()" in routes
    assert "DemoPlanServiceContext" in routes
    assert ".status_payload()" in routes
    assert ".open_demo_payload()" in routes
    assert ".restore_current_payload()" in routes
    # Demo data must fully replace plan-data fields, not merge in the real
    # user's protected values (e.g. retirement dates) -- see app_core.py's
    # PROTECTED_CLIENT_DATA_KEYS / _merge_protected_client_data_values.
    assert "preserve_protected=False" in routes
