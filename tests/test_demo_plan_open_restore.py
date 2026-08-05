"""#240: Open Demo Plan / Open Current Plan toggle.

Exercises DemoPlanService in full isolation (tmp_path DBs/dirs, no real
input/ or local_state/ touched -- these must never be mutated by a test run)
following the same pattern test_backend_service_extraction_continuation_regression.py
uses for PlanFileService: a tiny throwaway sqlite DB with a single marker
row, swapped around by the service under test.
"""
import dataclasses
import sqlite3
from pathlib import Path

from src.server_services.demo_plan_service import (
    DEMO_SLOT_DIR,
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
    demo_block = routes[demo_block_start:demo_block_start + 2000]
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


# --- Persistent demo slot (editable, persistent demo plan) ---------------
#
# The slot (local_state/demo_plan/, DEMO_SLOT_DIR) is not passed explicitly
# in _make_service -- DemoPlanServiceContext.demo_slot_dir defaults to None,
# which the service resolves to sqlite_db().parent / DEMO_SLOT_DIR, i.e.
# active_db.parent / DEMO_SLOT_DIR here. Tests below compute that same path
# to inspect the slot rather than threading a new fixture param through
# every existing call site.


def test_slot_captures_edits_on_restore_and_reapplies_on_next_open(tmp_path):
    """An edit made while the demo is open (a Save Changes write, modeled
    here by mutating disk_files directly) must survive Open Current Plan and
    reappear -- sourced from the slot, not the shipped fixture -- the next
    time Open Demo Plan runs."""
    service, active_db, demo_dir, audits, written, materialized, disk_files, sync_calls = _make_service(tmp_path)

    service.open_demo_payload()
    disk_files["client_household.csv"] = "edited household content\n"

    service.restore_current_payload()

    slot_dir = active_db.parent / DEMO_SLOT_DIR
    assert (slot_dir / "client_household.csv").read_text(encoding="utf-8") == "edited household content\n"

    result = service.open_demo_payload()
    assert disk_files["client_household.csv"] == "edited household content\n"
    entry = next(w for w in result["files"] if w["name"] == "client_household.csv")
    assert entry["source"] == "slot"


def test_reset_demo_deletes_slot_and_next_open_falls_back_to_fixture(tmp_path):
    service, active_db, demo_dir, audits, written, materialized, disk_files, sync_calls = _make_service(tmp_path)

    service.open_demo_payload()
    disk_files["client_household.csv"] = "edited household content\n"
    service.restore_current_payload()

    slot_dir = active_db.parent / DEMO_SLOT_DIR
    assert slot_dir.exists()

    result = service.reset_demo_payload()
    assert result == {"success": True, "reset": True}
    assert not slot_dir.exists()
    assert any(event == "demo_plan_slot_reset" for event, _ in audits)

    result = service.open_demo_payload()
    assert disk_files["client_household.csv"] == "demo household content\n"
    entry = next(w for w in result["files"] if w["name"] == "client_household.csv")
    assert entry["source"] == "demo"


def test_reset_demo_refused_while_demo_is_active(tmp_path):
    """Closing the demo re-captures its current state into the slot, so a
    reset while it's open would just be immediately undone -- refuse it and
    tell the advisor to close the demo first, rather than silently no-op or
    (worse) delete a slot the close is about to recreate."""
    service, active_db, demo_dir, audits, written, materialized, disk_files, sync_calls = _make_service(tmp_path)
    service.open_demo_payload()

    result = service.reset_demo_payload()

    assert result["success"] is False
    assert "error" in result
    assert not (active_db.parent / DEMO_SLOT_DIR).exists()


def test_capture_never_runs_when_no_demo_is_active(tmp_path):
    service, active_db, demo_dir, audits, written, materialized, disk_files, sync_calls = _make_service(tmp_path)

    result = service.restore_current_payload()

    assert result == {"success": True, "restored": False}
    assert not (active_db.parent / DEMO_SLOT_DIR).exists()


def test_capture_failure_is_non_fatal_and_still_restores_the_real_plan(tmp_path):
    """Capture must never block getting the real plan back -- the single most
    important invariant in the restore path. A read failure for one file is
    audited and that file is skipped; every other file still restores."""
    service, active_db, demo_dir, audits, written, materialized, disk_files, sync_calls = _make_service(tmp_path)
    service.open_demo_payload()
    disk_files["client_household.csv"] = "edited household content\n"

    def raising_read(name):
        if name == "client_household.csv":
            raise RuntimeError("disk full")
        return disk_files.get(name)

    broken_service = DemoPlanService(dataclasses.replace(service.context, read_plan_data_file=raising_read))

    result = broken_service.restore_current_payload()

    assert result == {"success": True, "restored": True}
    assert any(event == "demo_plan_capture_warning" for event, _ in audits)
    slot_dir = active_db.parent / DEMO_SLOT_DIR
    assert not (slot_dir / "client_household.csv").exists()
    assert _read_marker(active_db) == "real-plan"


def test_slot_missing_one_file_falls_back_to_demo_fixture_for_that_file_only(tmp_path):
    """A fixture added to input/demo/ in a later release must still be picked
    up per-file by a user who already has a slot but not that file yet."""
    service, active_db, demo_dir, audits, written, materialized, disk_files, sync_calls = _make_service(tmp_path)
    service.open_demo_payload()
    disk_files["client_household.csv"] = "edited household content\n"
    service.restore_current_payload()

    slot_dir = active_db.parent / DEMO_SLOT_DIR
    (slot_dir / "client_data.csv").unlink()

    result = service.open_demo_payload()

    assert disk_files["client_household.csv"] == "edited household content\n"
    assert disk_files["client_data.csv"] == "demo client_data.csv content\n"
    by_name = {w["name"]: w["source"] for w in result["files"]}
    assert by_name["client_household.csv"] == "slot"
    assert by_name["client_data.csv"] == "demo"


def test_capture_never_writes_back_into_the_demo_fixture_directory(tmp_path):
    """The slot is a separate directory from input/demo/ -- capturing a demo
    edit must never touch the shipped fixtures, or the anti-leak tests in
    test_demo_plan_data_is_fictional.py (which read input/demo/ directly)
    could start seeing captured session data instead of the fictional seed."""
    service, active_db, demo_dir, audits, written, materialized, disk_files, sync_calls = _make_service(tmp_path)
    original_fixture = (demo_dir / "client_household.csv").read_text(encoding="utf-8")

    service.open_demo_payload()
    disk_files["client_household.csv"] = "edited household content\n"
    service.restore_current_payload()

    assert (demo_dir / "client_household.csv").read_text(encoding="utf-8") == original_fixture


def test_capture_prefers_the_disk_mirror_over_the_db_reader(tmp_path):
    """config_service.update_config_rows_payload (Save Changes on the Plan
    Data grid) writes ordinary fields straight to the on-disk CSV mirror and
    never touches the DB row read_plan_data_file prefers -- if capture used
    read_plan_data_file, a field edited through the grid during a demo would
    be silently dropped from the slot. read_plan_data_disk_file must win
    whenever the context supplies one."""
    service, active_db, demo_dir, audits, written, materialized, disk_files, sync_calls = _make_service(tmp_path)
    service.open_demo_payload()

    disk_only = {"client_household.csv": "grid-edited household content\n"}
    disk_reader_context = dataclasses.replace(
        service.context, read_plan_data_disk_file=lambda name: disk_only.get(name)
    )
    service_with_disk_reader = DemoPlanService(disk_reader_context)

    service_with_disk_reader.restore_current_payload()

    slot_dir = active_db.parent / DEMO_SLOT_DIR
    assert (slot_dir / "client_household.csv").read_text(encoding="utf-8") == "grid-edited household content\n"


def test_plan_routes_wire_reset_demo_endpoint():
    routes = Path("src/server/plan_routes.py").read_text(encoding="utf-8")
    assert '@app.route("/api/plan/reset-demo", methods=["POST"])' in routes
    assert ".reset_demo_payload()" in routes


def test_plan_routes_wire_the_disk_accurate_capture_reader():
    routes = Path("src/server/plan_routes.py").read_text(encoding="utf-8")
    assert "read_plan_data_disk_file=_read_plan_data_disk_file" in routes


def test_every_text_backup_file_passes_the_write_allowlist():
    """Every TEXT_BACKUP_FILES entry must be in app_core's PLAN_DATA_FILE_SET
    (see src/server/plan_data_files.py's DEMO_TEXT_BACKUP_FILES) or
    _normalize_plan_data_file_name rejects it with "Unsupported Plan Data
    file" the moment open_demo_payload's per-file loop calls
    context.write_plan_data_file -- and since that call has no try/except,
    Open Demo Plan fails outright (after already backing up the real plan
    and swapping every earlier file in the list) instead of just skipping
    the missing fixture like a genuinely absent file would."""
    from src.server.plan_data_files import PLAN_DATA_FILE_SET

    missing = [name for name in TEXT_BACKUP_FILES if name not in PLAN_DATA_FILE_SET]
    assert not missing, f"TEXT_BACKUP_FILES entries missing from PLAN_DATA_FILE_SET: {missing}"
