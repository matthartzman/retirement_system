"""#240: Open Demo Plan / Open Current Plan toggle.

Exercises DemoPlanService in full isolation (tmp_path DBs/dirs, no real
input/ or local_state/ touched -- these must never be mutated by a test run)
following the same pattern test_152_backend_service_extraction_continuation.py
uses for PlanFileService: a tiny throwaway sqlite DB with a single marker
row, swapped around by the service under test.
"""
import re
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


def _make_service(tmp_path: Path, *, real_client_data: str = "real client_data.csv content\n"):
    active_db = tmp_path / "local_state" / "retirement_system_v10.db"
    demo_dir = tmp_path / "input" / "demo"
    demo_dir.mkdir(parents=True, exist_ok=True)
    (demo_dir / "client_household.csv").write_text("demo household content\n", encoding="utf-8")
    (demo_dir / "client_data.csv").write_text("demo client_data.csv content\n", encoding="utf-8")
    # client_income.csv intentionally has no demo counterpart -- exercises "skipped".
    _make_db(active_db, "real-plan")

    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    audits = []
    written: dict[str, str] = {}
    # client_data.csv lives only on disk in the real app (never in the DB) --
    # model that here with a plain dict standing in for the on-disk file.
    disk_files = {"client_data.csv": real_client_data}

    def read_plan_data_file(name: str):
        return disk_files.get(name)

    def write_plan_data_file(name: str, content: str):
        written[name] = content
        disk_files[name] = content
        return tmp_path / "input" / name

    plan_file_service = PlanFileService(PlanFileServiceContext(
        sqlite_db=lambda: active_db,
        audit=lambda event, payload: audits.append((event, payload)),
        retention_count=10,
    ))

    materialized = {"count": 0}
    sync_calls = {"count": 0}

    def sync_config_backends():
        # Real export_client_json_yaml() derives client_data.json/.yaml from
        # whatever client_data.csv currently holds on disk -- mirror that so
        # the restore path's re-push of the derived files is meaningfully
        # exercised, not just a no-op stub.
        sync_calls["count"] += 1
        json_path = input_dir / "client_data.json"
        yaml_path = input_dir / "client_data.yaml"
        content = disk_files.get("client_data.csv", "")
        json_path.write_text(content, encoding="utf-8")
        yaml_path.write_text(content, encoding="utf-8")
        return {
            "success": True,
            "derived": {"client_data.json": str(json_path), "client_data.yaml": str(yaml_path)},
        }

    service = DemoPlanService(DemoPlanServiceContext(
        sqlite_db=lambda: active_db,
        demo_dir=lambda: demo_dir,
        plan_data_csv_files=["client_data.csv", "client_household.csv", "client_income.csv"],
        read_plan_data_file=read_plan_data_file,
        write_plan_data_file=write_plan_data_file,
        sync_config_backends=sync_config_backends,
        ensure_user_ui_plan_data_rows=lambda: None,
        load_saved_db=plan_file_service.load_file,
        materialize=lambda: materialized.__setitem__("count", materialized["count"] + 1),
        audit=lambda event, payload: audits.append((event, payload)),
    ))
    return service, active_db, demo_dir, audits, written, materialized, disk_files, sync_calls


def test_status_is_inactive_before_any_demo_is_opened(tmp_path):
    service, *_ = _make_service(tmp_path)
    assert service.status_payload() == {"success": True, "active": False, "opened_at": None}


def test_open_demo_writes_available_files_reports_skipped_and_backs_up_once(tmp_path):
    service, active_db, demo_dir, audits, written, _materialized, disk_files, _sync = _make_service(tmp_path)

    result = service.open_demo_payload()

    assert result["success"] is True
    assert written["client_household.csv"] == "demo household content\n"
    assert disk_files["client_data.csv"] == "demo client_data.csv content\n"
    assert result["skipped"] == ["client_income.csv"]

    backup = Path(str(active_db) + ".before_demo")
    assert backup.exists()
    assert _read_marker(backup) == "real-plan"

    client_data_backup = active_db.parent / "client_data.csv.before_demo"
    assert client_data_backup.read_text(encoding="utf-8") == "real client_data.csv content\n"

    marker_json = active_db.parent / "demo_mode_marker.json"
    assert marker_json.exists()

    status = service.status_payload()
    assert status["active"] is True
    assert status["opened_at"]
    assert any(event == "demo_plan_opened" for event, _ in audits)


def test_open_demo_twice_does_not_reclobber_either_backup(tmp_path):
    service, active_db, demo_dir, audits, written, _materialized, disk_files, _sync = _make_service(tmp_path)

    service.open_demo_payload()
    # Simulate the live DB/client_data.csv now actually holding demo-state
    # content, as they would after write_plan_data_file's real writes.
    _make_db(active_db, "demo-state")
    disk_files["client_data.csv"] = "demo client_data.csv content\n"

    service.open_demo_payload()

    backup = Path(str(active_db) + ".before_demo")
    assert _read_marker(backup) == "real-plan", "second Open Demo Plan click must not overwrite the real DB backup"
    client_data_backup = active_db.parent / "client_data.csv.before_demo"
    assert client_data_backup.read_text(encoding="utf-8") == "real client_data.csv content\n", \
        "second Open Demo Plan click must not overwrite the real client_data.csv backup"


def test_restore_current_when_no_demo_is_active_is_a_safe_noop(tmp_path):
    service, *_ = _make_service(tmp_path)
    assert service.restore_current_payload() == {"success": True, "restored": False}


def test_restore_current_swaps_db_and_client_data_csv_back_and_clears_backups(tmp_path):
    service, active_db, demo_dir, audits, written, materialized, disk_files, sync_calls = _make_service(tmp_path)

    service.open_demo_payload()
    _make_db(active_db, "demo-state")  # live DB now diverged from the backup
    disk_files["client_data.csv"] = "demo client_data.csv content\n"
    sync_calls["count"] = 0

    result = service.restore_current_payload()

    assert result == {"success": True, "restored": True}
    assert _read_marker(active_db) == "real-plan"
    # client_data.csv is disk-only (never in the DB) -- restoring the DB alone
    # can't bring it back, so restore must write it back explicitly and
    # regenerate its .json/.yaml derivatives via sync_config_backends.
    assert disk_files["client_data.csv"] == "real client_data.csv content\n"
    assert sync_calls["count"] == 1
    # Regenerating client_data.json/.yaml on disk isn't enough by itself:
    # _read_plan_data_file seeds a DB-cached copy the first time anything
    # GETs a file missing from the DB, so a page opened mid-demo could have
    # already cached the demo version. Restore must push the regenerated
    # content through write_plan_data_file too, to overwrite any such entry.
    assert written["client_data.json"] == "real client_data.csv content\n"
    assert written["client_data.yaml"] == "real client_data.csv content\n"
    assert materialized["count"] == 1
    assert not Path(str(active_db) + ".before_demo").exists()
    assert not (active_db.parent / "client_data.csv.before_demo").exists()
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
    assert "read_plan_data_file=_read_plan_data_file" in routes
    # Demo data must fully replace plan-data fields, not merge in the real
    # user's protected values (e.g. retirement dates) -- see app_core.py's
    # PROTECTED_CLIENT_DATA_KEYS / _merge_protected_client_data_values.
    assert "preserve_protected=False" in routes


def test_plan_routes_demo_restore_materialize_excludes_ytd_files():
    """Open Demo Plan never swaps YTD data (no input/demo/ytd_transactions.csv,
    and DemoPlanServiceContext.plan_data_csv_files never includes it), so YTD
    stays real and editable for the whole demo window. Restore's materialize()
    call must therefore NOT include YTD_PLAN_DATA_FILES -- re-materializing a
    file the demo never swapped would silently clobber a real YTD edit saved
    mid-demo with the pre-demo DB backup's stale content (see
    test_demo_restore_materialize_scoped_to_swapped_files_preserves_concurrent_ytd_edit
    for the failure this prevents). This is deliberately narrower than
    /api/plan/load-file's materialize call, which swaps in a genuinely
    different plan and must re-materialize YTD too.
    """
    routes = Path("src/server/plan_routes.py").read_text(encoding="utf-8")

    def _top_level_function_block(marker: str) -> str:
        rest = routes.split(marker, 1)[1]
        m = re.search(r"^def \w", rest, re.MULTILINE)
        return rest[: m.start()] if m else rest

    demo_section = _top_level_function_block("def _demo_plan_feature_service()")
    assert "materialize_workspace_files(" in demo_section
    assert "YTD_PLAN_DATA_FILES" not in demo_section
    assert "PLAN_DATA_CSV_FILES" in demo_section

    load_file_section = _top_level_function_block("def plan_load_file()")
    assert "YTD_PLAN_DATA_FILES" in load_file_section, \
        "plan_load_file swaps in a different plan and must still re-materialize YTD"


def test_demo_restore_materialize_scoped_to_swapped_files_preserves_concurrent_ytd_edit(tmp_path, monkeypatch):
    """End-to-end (real materialize_workspace_files, real SQLite client_files
    table -- nothing mocked) regression test for the data-integrity bug: a
    real YTD transaction category, edited and saved while a demo happens to
    be open, must survive Open Current Plan. Before the fix, restore's
    materialize() call included YTD_PLAN_DATA_FILES, which unconditionally
    overwrote ytd_transactions.csv on disk with the pre-demo DB backup's
    content -- discarding the edit without any error or warning.
    """
    import src.config_backend as config_backend
    from src.config_backend import get_client_file, materialize_workspace_files, set_client_file
    from src.server.plan_data_files import PLAN_DATA_CSV_FILES

    monkeypatch.setattr(config_backend, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config_backend.platform_runtime, "workspace_root", lambda: tmp_path)
    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True)
    demo_dir = input_dir / "demo"
    demo_dir.mkdir()

    db_path = tmp_path / "local_state" / "retirement_system_v10.db"
    real_ytd = "Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n2026-01-05,Becca Hartzman,Large Gifts,Venmo,Becca Hartzman,First half,-5000,,Shared\n"
    real_aliases = "match_value,match_field,exact,priority,category_id,source\nLarge Gifts,category,1,60,significant_gifts,user\n"
    set_client_file("ytd_transactions.csv", real_ytd, db_path=db_path)
    set_client_file("client_spending_aliases.csv", real_aliases, db_path=db_path)
    (input_dir / "ytd_transactions.csv").write_text(real_ytd, encoding="utf-8")
    (input_dir / "client_spending_aliases.csv").write_text(real_aliases, encoding="utf-8")

    demo_aliases = "match_value,match_field,exact,priority,category_id,source\nGifts - Other,category,1,50,gifts_other,seed\n"
    (demo_dir / "client_spending_aliases.csv").write_text(demo_aliases, encoding="utf-8")

    plan_file_service = PlanFileService(PlanFileServiceContext(
        sqlite_db=lambda: db_path,
        audit=lambda event, payload: None,
        retention_count=10,
    ))

    def write_plan_data_file(name, content):
        if name != "client_data.csv":
            set_client_file(name, content, db_path=db_path)
        path = input_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def read_plan_data_file(name):
        return get_client_file(name, db_path=db_path)

    def materialize_swapped_files_only():
        # Mirrors the fixed plan_routes.py::_demo_plan_feature_service()
        # _materialize() closure -- PLAN_DATA_CSV_FILES only, no YTD.
        materialize_workspace_files(
            db_path=db_path,
            file_names=[n for n in PLAN_DATA_CSV_FILES if n != "client_data.csv"],
            overwrite_existing=True,
        )

    service = DemoPlanService(DemoPlanServiceContext(
        sqlite_db=lambda: db_path,
        demo_dir=lambda: demo_dir,
        plan_data_csv_files=PLAN_DATA_CSV_FILES,
        read_plan_data_file=read_plan_data_file,
        write_plan_data_file=write_plan_data_file,
        sync_config_backends=lambda: {"success": True, "derived": {}},
        ensure_user_ui_plan_data_rows=lambda: None,
        load_saved_db=plan_file_service.load_file,
        materialize=materialize_swapped_files_only,
        audit=lambda event, payload: None,
    ))

    service.open_demo_payload()
    assert (input_dir / "client_spending_aliases.csv").read_text(encoding="utf-8") == demo_aliases

    # While the demo is open, YTD stays real/live (never swapped) -- simulate
    # a genuine user edit landing through the normal YTD save path (mirrors
    # ytd_service.bulk_save_transactions: write disk, then mirror to SQLite).
    edited_ytd = real_ytd.replace("Large Gifts", "Gifts - Family 12")
    (input_dir / "ytd_transactions.csv").write_text(edited_ytd, encoding="utf-8")
    set_client_file("ytd_transactions.csv", edited_ytd, db_path=db_path)

    service.restore_current_payload()

    assert (input_dir / "client_spending_aliases.csv").read_text(encoding="utf-8") == real_aliases
    assert (input_dir / "ytd_transactions.csv").read_text(encoding="utf-8") == edited_ytd, \
        "restore must not discard a real YTD edit saved while the demo was open"


def test_demo_restore_materialize_including_ytd_files_clobbers_concurrent_ytd_edit(tmp_path, monkeypatch):
    """Companion to the previous test: proves *why* the fix matters by
    reproducing the pre-fix bug directly -- same scenario, but materialize()
    uses the old (buggy) file list that includes YTD_PLAN_DATA_FILES. That
    must silently discard the concurrent YTD edit, confirming this is exactly
    the failure mode the fix in plan_routes.py::_demo_plan_feature_service
    closes.
    """
    import src.config_backend as config_backend
    from src.config_backend import get_client_file, materialize_workspace_files, set_client_file
    from src.server.plan_data_files import PLAN_DATA_CSV_FILES, YTD_PLAN_DATA_FILES

    monkeypatch.setattr(config_backend, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config_backend.platform_runtime, "workspace_root", lambda: tmp_path)
    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True)
    demo_dir = input_dir / "demo"
    demo_dir.mkdir()

    db_path = tmp_path / "local_state" / "retirement_system_v10.db"
    real_ytd = "Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n2026-01-05,Becca Hartzman,Large Gifts,Venmo,Becca Hartzman,First half,-5000,,Shared\n"
    set_client_file("ytd_transactions.csv", real_ytd, db_path=db_path)
    (input_dir / "ytd_transactions.csv").write_text(real_ytd, encoding="utf-8")
    (demo_dir / "client_data.csv").write_text("demo\n", encoding="utf-8")

    plan_file_service = PlanFileService(PlanFileServiceContext(
        sqlite_db=lambda: db_path,
        audit=lambda event, payload: None,
        retention_count=10,
    ))

    def write_plan_data_file(name, content):
        if name != "client_data.csv":
            set_client_file(name, content, db_path=db_path)
        path = input_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def read_plan_data_file(name):
        return get_client_file(name, db_path=db_path)

    def materialize_pre_fix_buggy():
        materialize_workspace_files(
            db_path=db_path,
            file_names=[n for n in PLAN_DATA_CSV_FILES if n != "client_data.csv"] + YTD_PLAN_DATA_FILES,
            overwrite_existing=True,
        )

    service = DemoPlanService(DemoPlanServiceContext(
        sqlite_db=lambda: db_path,
        demo_dir=lambda: demo_dir,
        plan_data_csv_files=PLAN_DATA_CSV_FILES,
        read_plan_data_file=read_plan_data_file,
        write_plan_data_file=write_plan_data_file,
        sync_config_backends=lambda: {"success": True, "derived": {}},
        ensure_user_ui_plan_data_rows=lambda: None,
        load_saved_db=plan_file_service.load_file,
        materialize=materialize_pre_fix_buggy,
        audit=lambda event, payload: None,
    ))

    service.open_demo_payload()

    edited_ytd = real_ytd.replace("Large Gifts", "Gifts - Family 12")
    (input_dir / "ytd_transactions.csv").write_text(edited_ytd, encoding="utf-8")
    set_client_file("ytd_transactions.csv", edited_ytd, db_path=db_path)

    service.restore_current_payload()

    result = (input_dir / "ytd_transactions.csv").read_text(encoding="utf-8")
    assert result == real_ytd, "demonstrates the pre-fix bug: the concurrent edit is silently discarded"
    assert result != edited_ytd
