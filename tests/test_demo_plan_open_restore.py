"""#240: Open Demo Plan / Open Current Plan toggle.

Exercises DemoPlanService in full isolation (tmp_path DBs/dirs, no real
input/ or local_state/ touched -- these must never be mutated by a test run)
following the same pattern test_152_backend_service_extraction_continuation.py
uses for PlanFileService: a tiny throwaway sqlite DB with a single marker
row, swapped around by the service under test.
"""
import dataclasses
import sqlite3
from pathlib import Path

from src.server_services.demo_plan_service import (
    TEXT_BACKUP_FILES,
    DemoPlanService,
    DemoPlanServiceContext,
)
from src.server_services.plan_file_service import PlanFileService, PlanFileServiceContext

SEED = "client_spending_budget.recovery_seed.csv"


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
    # Every TEXT_BACKUP_FILES entry gets a fixture, matching the real
    # input/demo/ -- the service adds them to the applied list itself, so a
    # missing one here would show up as an unexpected "skipped" entry.
    for name in TEXT_BACKUP_FILES:
        (demo_dir / name).write_text(f"demo {name}\n", encoding="utf-8")
    # client_income.csv intentionally has no demo counterpart -- exercises "skipped".
    _make_db(active_db, "real-plan")

    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    audits = []
    written: dict[str, str] = {}
    # client_data.csv lives only on disk in the real app (never in the DB) --
    # model that here with a plain dict standing in for the on-disk file.
    disk_files = {
        "client_data.csv": real_client_data,
        **{name: f"real {name}\n" for name in TEXT_BACKUP_FILES},
    }

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
    # The recovery seed is outside plan_data_csv_files; the service adds it.
    assert disk_files[SEED] == f"demo {SEED}\n"

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
    assert not (active_db.parent / f"{SEED}.before_demo").exists()
    assert not (active_db.parent / "demo_mode_marker.json").exists()
    assert any(event == "demo_plan_restored" for event, _ in audits)

    # Idempotent: a second click with nothing left to restore is a no-op.
    assert service.restore_current_payload() == {"success": True, "restored": False}


def test_demo_swaps_and_restores_the_budget_recovery_seed(tmp_path):
    """client_spending_budget.recovery_seed.csv is not in PLAN_DATA_CSV_FILES,
    so neither the caller's file list nor materialize() covers it -- yet
    spending_tracker.load_unified_budget() merges it into the budget whenever
    the category rows total zero. Left alone it would pull the advisor's real
    annualized actuals (down to named categories) into the demo household's
    budget, so the service applies the demo copy and restores the real one."""
    assert SEED in TEXT_BACKUP_FILES
    service, active_db, _demo_dir, _audits, _written, _mat, disk_files, _sync = _make_service(tmp_path)

    service.open_demo_payload()
    assert disk_files[SEED] == f"demo {SEED}\n"
    seed_backup = active_db.parent / f"{SEED}.before_demo"
    assert seed_backup.read_text(encoding="utf-8") == f"real {SEED}\n"

    # A second open must not overwrite the real seed's backup with demo content.
    service.open_demo_payload()
    assert seed_backup.read_text(encoding="utf-8") == f"real {SEED}\n"

    _make_db(active_db, "demo-state")
    service.restore_current_payload()
    assert disk_files[SEED] == f"real {SEED}\n"
    assert not seed_backup.exists()


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


def test_demo_open_swaps_ytd_actual_spending_too():
    """#248: Open Demo Plan wrote every core plan-data file (household,
    income/annuities, holdings, ...) but the demo's plan_data_csv_files list
    stopped at PLAN_DATA_CSV_FILES, omitting YTD_PLAN_DATA_FILES
    (ytd_transactions.csv, ytd_account_setup.csv, ytd_import_history.csv).
    Restore already treats YTD files as part of the swap (_materialize()'s
    file list includes YTD_PLAN_DATA_FILES); open must match, or "Actual
    Spending (This Year)" keeps showing the advisor's real transactions
    while every other screen shows the demo household."""
    routes = Path("src/server/plan_routes.py").read_text(encoding="utf-8")
    demo_block_start = routes.index("def _demo_plan_feature_service()")
    demo_block = routes[demo_block_start:demo_block_start + 1200]
    assert "plan_data_csv_files=PLAN_DATA_CSV_FILES + YTD_PLAN_DATA_FILES" in demo_block, (
        "Open Demo Plan's file list must include YTD_PLAN_DATA_FILES so "
        "ytd_transactions.csv is swapped along with the rest of the demo "
        "household, not left showing the real advisor's transactions."
    )


def test_demo_ytd_fixture_files_exist_and_are_fictional():
    """The demo files added for #248 must exist, use the demo household's
    account naming, and not contain the real plan's merchant/account names."""
    demo_dir = Path("input") / "demo"
    for name in ("ytd_transactions.csv", "ytd_account_setup.csv", "ytd_import_history.csv"):
        p = demo_dir / name
        assert p.exists(), f"input/demo/{name} is missing"
        text = p.read_text(encoding="utf-8-sig")
        assert text.strip(), f"input/demo/{name} is empty"
        for real_marker in ("Max and Benny", "Hartzman", "RedMane"):
            assert real_marker not in text, f"input/demo/{name} leaks real data: {real_marker!r}"


def test_demo_edits_persist_across_a_restore_and_reopen(tmp_path):
    """Editing the demo (a write during an active demo) and then restoring
    must capture that edit into the persistent slot, so the next Open Demo
    Plan reseeds from the edited state, not the shipped fixture."""
    service, active_db, demo_dir, audits, written, _mat, disk_files, _sync = _make_service(tmp_path)

    service.open_demo_payload()
    disk_files["client_household.csv"] = "EDITED household content\n"

    _make_db(active_db, "demo-state")
    service.restore_current_payload()

    slot_dir = active_db.parent / "demo_plan"
    assert (slot_dir / "client_household.csv").read_text(encoding="utf-8") == "EDITED household content\n"

    # Prove the next open reads from the SLOT, not a leftover harness value.
    disk_files.pop("client_household.csv", None)
    written.clear()
    result = service.open_demo_payload()
    assert written["client_household.csv"] == "EDITED household content\n"
    hh_entry = next(w for w in result["files"] if w["name"] == "client_household.csv")
    assert hh_entry["source"] == "slot"


def test_restore_when_inactive_does_not_create_or_touch_the_slot(tmp_path):
    service, active_db, *_ = _make_service(tmp_path)
    slot_dir = active_db.parent / "demo_plan"
    result = service.restore_current_payload()
    assert result == {"success": True, "restored": False}
    assert not slot_dir.exists()


def test_a_capture_failure_does_not_block_restoring_the_real_plan(tmp_path):
    service, active_db, demo_dir, audits, written, materialized, disk_files, sync_calls = _make_service(tmp_path)

    service.open_demo_payload()
    _make_db(active_db, "demo-state")
    disk_files["client_data.csv"] = "demo client_data.csv content\n"

    real_read = service.context.read_plan_data_file

    def raising_read(name):
        if name == "client_household.csv":
            raise RuntimeError("boom")
        return real_read(name)

    # DemoPlanServiceContext is a frozen dataclass -- rebuild it with the
    # raising reader rather than mutating a frozen field.
    service.context = dataclasses.replace(service.context, read_plan_data_file=raising_read)

    result = service.restore_current_payload()

    assert result == {"success": True, "restored": True}
    assert any(event == "demo_plan_capture_warning" for event, _ in audits)
    # The real plan still came back despite the capture failure.
    assert disk_files["client_data.csv"] == "real client_data.csv content\n"


def test_slot_missing_a_file_falls_back_to_the_fixture_for_that_file_only(tmp_path):
    service, active_db, demo_dir, audits, written, _mat, disk_files, _sync = _make_service(tmp_path)

    service.open_demo_payload()
    disk_files["client_household.csv"] = "EDITED household content\n"
    _make_db(active_db, "demo-state")
    service.restore_current_payload()

    slot_dir = active_db.parent / "demo_plan"
    assert (slot_dir / "client_household.csv").exists()
    # Simulate a fixture added to input/demo/ after the slot was already
    # captured -- e.g. a new plan-data file shipped in a later release that
    # this user's existing slot has never seen.
    (demo_dir / "client_income.csv").write_text("demo income content\n", encoding="utf-8")

    disk_files.pop("client_household.csv", None)
    written.clear()
    result = service.open_demo_payload()

    # client_household.csv comes from the slot (the edit survives)...
    assert written["client_household.csv"] == "EDITED household content\n"
    # ...but client_income.csv, absent from the slot, falls back to the
    # fixture instead of being skipped.
    assert written["client_income.csv"] == "demo income content\n"
    assert "client_income.csv" not in result["skipped"]
    hh_entry = next(w for w in result["files"] if w["name"] == "client_household.csv")
    income_entry = next(w for w in result["files"] if w["name"] == "client_income.csv")
    assert hh_entry["source"] == "slot"
    assert income_entry["source"] == "fixture"


def test_plan_routes_wire_the_demo_slot_and_reset_endpoint():
    routes = Path("src/server/plan_routes.py").read_text(encoding="utf-8")
    assert "demo_slot_dir=" in routes
    assert "/api/plan/reset-demo" in routes
    assert ".reset_demo_payload()" in routes


def test_reset_demo_deletes_the_slot_so_next_open_reseeds_from_fixtures(tmp_path):
    service, active_db, demo_dir, audits, written, _mat, disk_files, _sync = _make_service(tmp_path)

    service.open_demo_payload()
    disk_files["client_household.csv"] = "EDITED household content\n"
    _make_db(active_db, "demo-state")
    service.restore_current_payload()

    slot_dir = active_db.parent / "demo_plan"
    assert slot_dir.exists()

    result = service.reset_demo_payload()
    assert result == {"success": True, "reset": True}
    assert not slot_dir.exists()

    disk_files.pop("client_household.csv", None)
    written.clear()
    service.open_demo_payload()
    assert written["client_household.csv"] == "demo household content\n"


def test_reset_demo_refuses_while_a_demo_is_active(tmp_path):
    service, active_db, *_ = _make_service(tmp_path)
    service.open_demo_payload()
    result = service.reset_demo_payload()
    assert result["success"] is False
    assert "error" in result
