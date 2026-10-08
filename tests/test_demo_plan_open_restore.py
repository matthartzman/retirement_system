"""#240: Open Demo Plan / Open Current Plan toggle (WP4.5: the demo swaps plan FILES).

Exercises DemoPlanService in full isolation (tmp_path plan file, legacy database and folders,
no real input/ or local_state/ touched -- these must never be mutated by a test run). The plan
file is a real ``PlanStore`` holding a marker row; the legacy database is a tiny sqlite file with
``client_files`` and a marker, swapped around by the service under test. The demo household is
built from the demo folder's CSV set through the ``csv_exchange`` importer.
"""
import dataclasses
import sqlite3
from pathlib import Path

import pytest

from src.server_services.demo_plan_service import (
    DEMO_SLOT_DIR,
    SLOT_PLAN_FILE,
    DemoPlanService,
    DemoPlanServiceContext,
)
from src.stores import PlanStore

SEED = "client_spending_budget.recovery_seed.csv"
REAL_SEED_ROWS = [{"kind": "category", "key": "real_cat", "label": "Real", "annual_budget": "999"}]
HEADER = "section,subsection,label,value,units,notes\n"
FLAT = ["client_holdings.csv", "client_liabilities.csv", "ytd_transactions.csv"]


def _make_plan(path: Path, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with PlanStore.open(path) as store:
        store.set_value("Marker", "", "value", marker)
        if marker == "real-plan":  # the advisor's own budget recovery seed (a plan revision)
            store.spending.set_recovery_seed(REAL_SEED_ROWS)


def _seed_keys(path: Path) -> list[str]:
    with PlanStore.open(path, create=False, readonly=True) as store:
        return [r["key"] for r in store.spending.recovery_seed()]


def _plan_marker(path: Path):
    with PlanStore.open(path, create=False, readonly=True) as store:
        return store.sectioned_data().get("Marker", {}).get("", {}).get("value")


def _plan_view(path: Path):
    with PlanStore.open(path, create=False, readonly=True) as store:
        return store.sectioned_data()


def _make_db(path: Path, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS client_files(file_name TEXT PRIMARY KEY, content TEXT)")
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
    plan_db = tmp_path / "plan.rpx"
    demo_dir = tmp_path / "input" / "demo"
    demo_dir.mkdir(parents=True, exist_ok=True)
    # The demo household's plan rows come from the plan CSV set (read once by the importer).
    (demo_dir / "client_household.csv").write_text(
        HEADER + "Household,,member_1_name,Demo Person,text,\nHousehold,,state,TX,text,\n", encoding="utf-8")
    (demo_dir / "client_data.csv").write_text(HEADER + "Scenarios,Base,growth,1,pct,\n", encoding="utf-8")
    # The flat datasets get a fixture, matching the real input/demo/ (a missing one would show up
    # as a "skipped" entry). The demo's budget recovery seed is read once, with the plan CSV set,
    # into the demo plan file as a plan revision.
    (demo_dir / "client_holdings.csv").write_text("demo holdings content\n", encoding="utf-8")
    (demo_dir / "ytd_transactions.csv").write_text("demo ytd content\n", encoding="utf-8")
    (demo_dir / SEED).write_text("kind,key,label,annual_budget\ncategory,demo_cat,Demo,10\n", encoding="utf-8")
    # client_liabilities.csv intentionally has no demo counterpart -- exercises "skipped".
    _make_db(active_db, "real-legacy")
    _make_plan(plan_db, "real-plan")

    audits = []
    written: dict[str, str] = {}
    disk_files = {
        "client_holdings.csv": "real holdings\n",
        "ytd_transactions.csv": "real ytd\n",
    }

    def read_plan_data_file(name: str):
        return disk_files.get(name)

    def write_plan_data_file(name: str, content: str):
        written[name] = content
        disk_files[name] = content
        return tmp_path / "input" / name

    materialized = {"count": 0}
    service = DemoPlanService(DemoPlanServiceContext(
        sqlite_db=lambda: active_db,
        plan_db=lambda: plan_db,
        demo_dir=lambda: demo_dir,
        plan_data_csv_files=FLAT,
        read_plan_data_file=read_plan_data_file,
        write_plan_data_file=write_plan_data_file,
        ensure_user_ui_plan_data_rows=lambda: None,
        materialize=lambda: materialized.__setitem__("count", materialized["count"] + 1),
        audit=lambda event, payload: audits.append((event, payload)),
    ))
    return service, active_db, plan_db, demo_dir, audits, written, materialized, disk_files


def test_status_is_inactive_before_any_demo_is_opened(tmp_path):
    service, *_ = _make_service(tmp_path)
    assert service.status_payload() == {"success": True, "active": False, "opened_at": None}


def test_open_demo_swaps_the_plan_file_writes_flat_files_reports_skipped_and_backs_up_once(tmp_path):
    service, active_db, plan_db, demo_dir, audits, written, _mat, disk_files = _make_service(tmp_path)

    result = service.open_demo_payload()

    assert result["success"] is True
    # the plan rows are the demo household, built through the importer; nothing is written as a CSV
    assert _plan_view(plan_db) == {"Household": {"": {"member_1_name": "Demo Person", "state": "TX"}},
                                   "Scenarios": {"Base": {"growth": "1"}}}
    plan_entry = next(w for w in result["files"] if w["name"] == "plan.rpx")
    assert plan_entry["source"] == "demo" and plan_entry["path"] == str(plan_db)
    assert "client_household.csv" not in written and "client_data.csv" not in written
    assert written["client_holdings.csv"] == "demo holdings content\n"
    assert result["skipped"] == ["client_liabilities.csv"]
    # The recovery seed rides in the demo plan file as a plan revision; no file is written for it.
    assert SEED not in written and _seed_keys(plan_db) == ["demo_cat"]

    plan_backup = Path(str(plan_db) + ".before_demo")
    assert plan_backup.exists() and _plan_marker(plan_backup) == "real-plan"
    legacy_backup = Path(str(active_db) + ".before_demo")
    assert legacy_backup.exists() and _read_marker(legacy_backup) == "real-legacy"
    assert (active_db.parent / "demo_mode_marker.json").exists()

    status = service.status_payload()
    assert status["active"] is True and status["opened_at"]
    assert any(event == "demo_plan_opened" for event, _ in audits)


def test_open_demo_twice_does_not_reclobber_either_backup(tmp_path):
    service, active_db, plan_db, *_ = _make_service(tmp_path)

    service.open_demo_payload()
    _make_db(active_db, "demo-state")
    with PlanStore.open(plan_db) as store:  # the live plan now holds demo-state edits
        store.set_value("Household", "", "member_1_name", "Edited In Demo")

    service.open_demo_payload()

    assert _plan_marker(Path(str(plan_db) + ".before_demo")) == "real-plan", \
        "second Open Demo Plan click must not overwrite the real plan backup"
    assert _read_marker(Path(str(active_db) + ".before_demo")) == "real-legacy", \
        "second Open Demo Plan click must not overwrite the real database backup"


def test_open_demo_on_a_fresh_workspace_backs_up_an_empty_plan(tmp_path):
    service, active_db, plan_db, *_ = _make_service(tmp_path)
    plan_db.unlink()
    service.open_demo_payload()
    backup = Path(str(plan_db) + ".before_demo")
    assert backup.exists() and _plan_view(backup) == {}
    assert service.restore_current_payload() == {"success": True, "restored": True}
    assert _plan_view(plan_db) == {}


def test_restore_current_when_no_demo_is_active_is_a_safe_noop(tmp_path):
    service, *_ = _make_service(tmp_path)
    assert service.restore_current_payload() == {"success": True, "restored": False}


def test_restore_current_swaps_the_plan_file_and_database_back_and_clears_backups(tmp_path):
    service, active_db, plan_db, demo_dir, audits, written, materialized, disk_files = _make_service(tmp_path)

    service.open_demo_payload()
    _make_db(active_db, "demo-state")  # live legacy DB now diverged from the backup

    result = service.restore_current_payload()

    assert result == {"success": True, "restored": True}
    assert _plan_marker(plan_db) == "real-plan" and "Household" not in _plan_view(plan_db)
    assert _read_marker(active_db) == "real-legacy"
    assert materialized["count"] == 1
    assert not Path(str(plan_db) + ".before_demo").exists()
    assert not Path(str(active_db) + ".before_demo").exists()
    assert not (active_db.parent / "demo_mode_marker.json").exists()
    assert any(event == "demo_plan_restored" for event, _ in audits)

    # Idempotent: a second click with nothing left to restore is a no-op.
    assert service.restore_current_payload() == {"success": True, "restored": False}


def test_a_restore_that_cannot_validate_the_backup_changes_nothing(tmp_path):
    service, active_db, plan_db, *_ = _make_service(tmp_path)
    service.open_demo_payload()
    Path(str(plan_db) + ".before_demo").write_bytes(b"not a database")

    result = service.restore_current_payload()

    assert result["success"] is False and result["restored"] is False and result["error"]
    assert _plan_view(plan_db)["Household"][""]["member_1_name"] == "Demo Person"  # still the demo
    assert service.status_payload()["active"] is True


def test_demo_swaps_and_restores_the_budget_recovery_seed(tmp_path):
    """The budget recovery seed is a plan revision of the plan file (WP6.3c), so the plan-file swap
    carries it: spending_tracker.load_unified_budget() merges it into the budget whenever the
    category rows total zero, which would pull the advisor's real annualized actuals into the demo
    household's budget -- so the demo plan has its own seed and the real one comes back with the
    real plan file. No file is backed up, applied or restored for it."""
    service, active_db, plan_db, _demo_dir, _audits, written, _mat, _disk = _make_service(tmp_path)
    assert _seed_keys(plan_db) == ["real_cat"]

    service.open_demo_payload()
    assert _seed_keys(plan_db) == ["demo_cat"]
    # A second open must not replace the real seed held by the plan backup.
    service.open_demo_payload()
    assert _seed_keys(Path(str(plan_db) + ".before_demo")) == ["real_cat"]

    _make_db(active_db, "demo-state")
    service.restore_current_payload()
    assert _seed_keys(plan_db) == ["real_cat"]
    assert SEED not in written
    assert not (active_db.parent / f"{SEED}.before_demo").exists()


def test_the_real_demo_folder_builds_the_demo_plan_equal_to_the_loader(tmp_path):
    """The shipped input/demo household is the demo plan's seed: the importer's rows equal the
    legacy loader's view (what ``tests.plan_fixture.make_plan('demo')`` also guarantees)."""
    from src.data_io import load_csv
    from src.plan_label_rules import dropped_at_load

    service, active_db, plan_db, *_ = _make_service(tmp_path)
    real_demo = Path("input") / "demo"
    service = DemoPlanService(dataclasses.replace(service.context, demo_dir=lambda: real_demo, plan_data_csv_files=[]))
    service.open_demo_payload()
    view = _plan_view(plan_db)
    expected = load_csv(real_demo / "client_data.csv")
    assert view == expected
    assert not any(dropped_at_load(s, sub, lbl) for s, subs in view.items() for sub, vals in subs.items() for lbl in vals)


def test_plan_routes_wire_demo_plan_service():
    routes = Path("src/server/plan_routes.py").read_text(encoding="utf-8")
    assert "def _demo_plan_feature_service()" in routes
    assert "DemoPlanServiceContext" in routes
    assert ".status_payload()" in routes
    assert ".open_demo_payload()" in routes
    assert ".restore_current_payload()" in routes
    assert "read_plan_data_file=_read_plan_data_file" in routes
    assert "plan_db=active_plan_path" in routes
    # Demo data replaces the plan file as a whole: no field-by-field merge with the real plan, and
    # no CSV step in either direction.
    assert "_sync_config_backends" not in routes and "preserve_protected" not in routes


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
    assert "PLAN_DATA_CSV_FILES + YTD_PLAN_DATA_FILES" in demo_block and "plan_data_csv_files=_FILE_BACKED_PLAN_DATA_FILES" in demo_block, (
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
    """An edit made while the demo is open (a plan edit, or a flat file edit modeled by mutating
    disk_files) must survive Open Current Plan and reappear -- sourced from the slot, not the
    shipped fixture -- the next time Open Demo Plan runs."""
    service, active_db, plan_db, demo_dir, audits, written, materialized, disk_files = _make_service(tmp_path)

    service.open_demo_payload()
    with PlanStore.open(plan_db) as store:
        store.set_value("Household", "", "member_1_name", "Edited In Demo")
    disk_files["client_holdings.csv"] = "edited holdings content\n"

    service.restore_current_payload()

    slot_dir = active_db.parent / DEMO_SLOT_DIR
    assert (slot_dir / "client_holdings.csv").read_text(encoding="utf-8") == "edited holdings content\n"
    assert _plan_view(slot_dir / SLOT_PLAN_FILE)["Household"][""]["member_1_name"] == "Edited In Demo"
    assert _plan_marker(plan_db) == "real-plan"

    result = service.open_demo_payload()
    assert _plan_view(plan_db)["Household"][""]["member_1_name"] == "Edited In Demo"
    assert disk_files["client_holdings.csv"] == "edited holdings content\n"
    by_name = {w["name"]: w["source"] for w in result["files"]}
    assert by_name["plan.rpx"] == "slot" and by_name["client_holdings.csv"] == "slot"


def test_reset_demo_deletes_slot_and_next_open_falls_back_to_fixture(tmp_path):
    service, active_db, plan_db, demo_dir, audits, written, materialized, disk_files = _make_service(tmp_path)

    service.open_demo_payload()
    with PlanStore.open(plan_db) as store:
        store.set_value("Household", "", "member_1_name", "Edited In Demo")
    disk_files["client_holdings.csv"] = "edited holdings content\n"
    service.restore_current_payload()

    slot_dir = active_db.parent / DEMO_SLOT_DIR
    assert slot_dir.exists()

    result = service.reset_demo_payload()
    assert result == {"success": True, "reset": True}
    assert not slot_dir.exists()
    assert any(event == "demo_plan_slot_reset" for event, _ in audits)

    result = service.open_demo_payload()
    assert _plan_view(plan_db)["Household"][""]["member_1_name"] == "Demo Person"
    assert disk_files["client_holdings.csv"] == "demo holdings content\n"
    by_name = {w["name"]: w["source"] for w in result["files"]}
    assert by_name["plan.rpx"] == "demo" and by_name["client_holdings.csv"] == "demo"


def test_reset_demo_refused_while_demo_is_active(tmp_path):
    """Closing the demo re-captures its current state into the slot, so a
    reset while it's open would just be immediately undone -- refuse it and
    tell the advisor to close the demo first, rather than silently no-op or
    (worse) delete a slot the close is about to recreate."""
    service, active_db, *_ = _make_service(tmp_path)
    service.open_demo_payload()

    result = service.reset_demo_payload()

    assert result["success"] is False
    assert "error" in result
    assert not (active_db.parent / DEMO_SLOT_DIR).exists()


def test_capture_never_runs_when_no_demo_is_active(tmp_path):
    service, active_db, *_ = _make_service(tmp_path)

    result = service.restore_current_payload()

    assert result == {"success": True, "restored": False}
    assert not (active_db.parent / DEMO_SLOT_DIR).exists()


def test_capture_failure_is_non_fatal_and_still_restores_the_real_plan(tmp_path):
    """Capture must never block getting the real plan back -- the single most
    important invariant in the restore path. A read failure for one file is
    audited and that file is skipped; every other file still restores."""
    service, active_db, plan_db, demo_dir, audits, written, materialized, disk_files = _make_service(tmp_path)
    service.open_demo_payload()
    disk_files["client_holdings.csv"] = "edited holdings content\n"

    def raising_read(name):
        if name == "client_holdings.csv":
            raise RuntimeError("disk full")
        return disk_files.get(name)

    broken_service = DemoPlanService(dataclasses.replace(service.context, read_plan_data_file=raising_read))

    result = broken_service.restore_current_payload()

    assert result == {"success": True, "restored": True}
    assert any(event == "demo_plan_capture_warning" for event, _ in audits)
    slot_dir = active_db.parent / DEMO_SLOT_DIR
    assert not (slot_dir / "client_holdings.csv").exists()
    assert (slot_dir / SLOT_PLAN_FILE).exists()  # the plan file was captured regardless
    assert _plan_marker(plan_db) == "real-plan" and _read_marker(active_db) == "real-legacy"


def test_a_slot_plan_file_that_is_not_a_plan_is_refused_and_leaves_the_real_plan(tmp_path):
    service, active_db, plan_db, *_ = _make_service(tmp_path)
    slot_dir = active_db.parent / DEMO_SLOT_DIR
    slot_dir.mkdir(parents=True)
    (slot_dir / SLOT_PLAN_FILE).write_bytes(b"garbage")

    with pytest.raises(Exception):
        service.open_demo_payload()

    assert _plan_marker(plan_db) == "real-plan"


def test_slot_missing_one_flat_file_falls_back_to_demo_fixture_for_that_file_only(tmp_path):
    """A fixture added to input/demo/ in a later release must still be picked
    up per-file by a user who already has a slot but not that file yet."""
    service, active_db, plan_db, demo_dir, audits, written, materialized, disk_files = _make_service(tmp_path)
    service.open_demo_payload()
    disk_files["client_holdings.csv"] = "edited holdings content\n"
    disk_files["ytd_transactions.csv"] = "edited ytd content\n"
    service.restore_current_payload()

    slot_dir = active_db.parent / DEMO_SLOT_DIR
    (slot_dir / "ytd_transactions.csv").unlink()

    result = service.open_demo_payload()

    assert disk_files["client_holdings.csv"] == "edited holdings content\n"
    assert disk_files["ytd_transactions.csv"] == "demo ytd content\n"
    by_name = {w["name"]: w["source"] for w in result["files"]}
    assert by_name["client_holdings.csv"] == "slot"
    assert by_name["ytd_transactions.csv"] == "demo"


def test_capture_never_writes_back_into_the_demo_fixture_directory(tmp_path):
    """The slot is a separate directory from input/demo/ -- capturing a demo
    edit must never touch the shipped fixtures, or the anti-leak tests in
    test_demo_plan_data_is_fictional.py (which read input/demo/ directly)
    could start seeing captured session data instead of the fictional seed."""
    service, active_db, plan_db, demo_dir, audits, written, materialized, disk_files = _make_service(tmp_path)
    original = {p.name: p.read_bytes() for p in demo_dir.iterdir()}

    service.open_demo_payload()
    with PlanStore.open(plan_db) as store:
        store.set_value("Household", "", "member_1_name", "Edited In Demo")
    disk_files["client_holdings.csv"] = "edited holdings content\n"
    service.restore_current_payload()

    assert {p.name: p.read_bytes() for p in demo_dir.iterdir()} == original


def test_capture_prefers_the_disk_mirror_over_the_db_reader(tmp_path):
    """A flat file edited through the ordinary UI writes the on-disk copy and never touches the DB
    row read_plan_data_file prefers -- if capture used read_plan_data_file, an edit made during a
    demo would be silently dropped from the slot. read_plan_data_disk_file must win whenever the
    context supplies one."""
    service, active_db, *_ = _make_service(tmp_path)
    service.open_demo_payload()

    disk_only = {"client_holdings.csv": "grid-edited holdings content\n"}
    disk_reader_context = dataclasses.replace(
        service.context, read_plan_data_disk_file=lambda name: disk_only.get(name)
    )
    service_with_disk_reader = DemoPlanService(disk_reader_context)

    service_with_disk_reader.restore_current_payload()

    slot_dir = active_db.parent / DEMO_SLOT_DIR
    assert (slot_dir / "client_holdings.csv").read_text(encoding="utf-8") == "grid-edited holdings content\n"


def test_plan_routes_wire_reset_demo_endpoint():
    routes = Path("src/server/plan_routes.py").read_text(encoding="utf-8")
    assert '@app.route("/api/plan/reset-demo", methods=["POST"])' in routes
    assert ".reset_demo_payload()" in routes


def test_plan_routes_capture_no_disk_copy():
    """WP7.1: every flat dataset travels with the plan file swap, so the routes wire no on-disk
    capture reader (the service falls back to the plan-table reader)."""
    routes = Path("src/server/plan_routes.py").read_text(encoding="utf-8")
    assert "_read_plan_data_disk_file" not in routes


def test_every_spending_table_file_passes_the_write_allowlist():
    """The spending set's files (now plan tables) must stay in app_core's PLAN_DATA_FILE_SET, or
    _normalize_plan_data_file_name rejects them with "Unsupported Plan Data file" the moment
    open_demo_payload's per-file loop calls context.write_plan_data_file for them."""
    from src.plan_data_registry import PLAN_TABLE_DATASET_FILES
    from src.server.plan_data_files import PLAN_DATA_FILE_SET

    missing = [n for n in PLAN_TABLE_DATASET_FILES if n not in PLAN_DATA_FILE_SET]
    assert not missing, f"plan table dataset files missing from PLAN_DATA_FILE_SET: {missing}"


def test_demo_open_and_exit_run_the_migrate_hook_after_each_swap(tmp_path):
    """migrate_plan_file's contract: it runs after every plan file swap (demo open and demo exit too)."""
    service, active_db, plan_db, *_ = _make_service(tmp_path)
    swapped = []
    service = DemoPlanService(dataclasses.replace(
        service.context, migrate=lambda path: swapped.append((Path(path), _plan_view(Path(path))))))
    service.open_demo_payload()
    assert swapped and swapped[-1][0] == plan_db and swapped[-1][1]["Household"][""]["member_1_name"] == "Demo Person"
    service.restore_current_payload()
    assert len(swapped) == 2 and swapped[-1][1] == {"Marker": {"": {"value": "real-plan"}}}


def test_the_routes_wire_the_migrate_hook_into_the_demo_service():
    from src.server import plan_routes
    assert plan_routes._demo_plan_feature_service().context.migrate is plan_routes._migrate_after_db_replace
