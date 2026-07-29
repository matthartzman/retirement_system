"""#240: a demo-session grid edit must not survive "Open Current Plan".

test_demo_plan_open_restore.py exercises DemoPlanService in full isolation
with a mocked dict standing in for both the sqlite DB and disk files -- that
harness is structurally blind to this bug, because the bug is specifically
about the *real* config_backend.materialize_workspace_files() silently
no-op'ing when the SQLite client_files table has no row for a file, which a
plain dict can never reproduce. This test exercises the real sqlite DB (via
src.config_backend.set_client_file/get_client_file/materialize_workspace_files)
and real disk files instead, redirecting platform_runtime.workspace_root() to
tmp_path so it can never touch the repo's real input/ (see
memory/testing notes: pytest must not mutate live input/ files).

Repro (matches the live-server repro from the ticket): edit a plan-data field
only through ConfigService.update_config_rows_payload (the Save Changes grid
endpoint), back up the DB the way Open Demo Plan does, overwrite the field
with fictional demo content, edit the same field again through the grid
while "in the demo" (a natural thing for an advisor exploring the demo to
do), then restore the DB backup and materialize() disk mirrors from it the
way Open Current Plan does. The real pre-demo value must come back, not the
demo-session grid edit.
"""
import gc
import shutil
import sqlite3
from pathlib import Path

from src.config_backend import get_client_file, materialize_workspace_files, set_client_file
from src.server_services.config_service import ConfigService, ConfigServiceContext

FILE_NAME = "client_household.csv"


def _checkpoint(db_path: Path) -> None:
    """Mirrors DemoPlanService._checkpoint_sqlite / plan_file_service's
    _checkpoint_sqlite: the DB runs in WAL mode (config_backend.init_sqlite),
    so a committed write can still live only in the "-wal" sidecar file. A
    plain file copy of just the ".db" file, without checkpointing first,
    silently drops those writes -- fold the WAL back into the main file
    before treating a copy as a real snapshot."""
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def _discard_sidecars(db_path: Path) -> None:
    """Mirrors plan_file_service._remove_sidecars' intent -- a stale "-wal"
    left next to a just-restored ".db" file gets replayed on the next
    connection, silently reapplying whatever was in the old WAL and undoing
    the restore. Rather than racing an OS-level unlink against the file lock
    Windows can briefly hold after set_client_file/get_client_file's
    unclosed connections (config_backend relies on GC there, same as
    production), checkpoint(TRUNCATE) the WAL down to zero bytes instead:
    an empty WAL has nothing left to replay, so it's neutralized without
    needing exclusive delete access to the sidecar file at all.
    """
    gc.collect()
    _checkpoint(db_path)


def _backup_db(db_path: Path, backup_path: Path) -> None:
    _discard_sidecars(db_path)
    shutil.copy2(str(db_path), str(backup_path))


def _restore_db(backup_path: Path, db_path: Path) -> None:
    _discard_sidecars(db_path)
    shutil.copy2(str(backup_path), str(db_path))
    _discard_sidecars(db_path)


def _write_plan_data_file(name: str, content: str, *, db_path: Path, disk_dir: Path) -> Path:
    """Faithful stand-in for app_core._write_plan_data_file's essential
    invariant under test: the SQLite client_files row is canonical and is
    written first, disk is the mirror. This is exactly the invariant #240's
    fix (routing config_service's grid save through write_plan_data_file
    instead of the disk-only write_client_rows) restores."""
    set_client_file(name, content, db_path=db_path)
    path = disk_dir / name
    path.write_text(content, encoding="utf-8")
    return path


def _make_config_service(db_path: Path, disk_dir: Path) -> ConfigService:
    return ConfigService(ConfigServiceContext(
        version="9",
        base_dir=disk_dir,
        csv_path=disk_dir / "client_data.csv",
        plan_data_csv_files=[FILE_NAME],
        client_data_csv_file_set={FILE_NAME},
        plan_data_path=lambda n, *a, **k: disk_dir / n,
        client_csv_rows=lambda: [
            {"row_index": 0, "source_file": FILE_NAME, "source_row_index": 0, "columns": []},
            {"row_index": 1, "source_file": FILE_NAME, "source_row_index": 1, "columns": []},
        ],
        csv_rows_payload=lambda: {"rows": [], "schema_count": 0},
        read_schema_map=lambda: {},
        write_plan_data_file=lambda n, c: _write_plan_data_file(n, c, db_path=db_path, disk_dir=disk_dir),
        load_active_config=lambda: ({}, {"backend": "CSV"}),
        runtime_config=lambda: type("Cfg", (), {"sqlite_db": str(db_path), "config_backend": "CSV"})(),
        normalize_date_for_csv=lambda v: v,
        sync_config_backends=lambda: {"success": True},
    ))


def test_demo_grid_edit_does_not_survive_restore_of_real_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))

    db_path = tmp_path / "retirement_system_v10.db"
    disk_dir = tmp_path / "input"
    disk_dir.mkdir(parents=True)
    service = _make_config_service(db_path, disk_dir)

    def row(value: str) -> str:
        return (
            "section,subsection,label,value,units,notes\n"
            f"Household,,client_name,{value},,\n"
        )

    (disk_dir / FILE_NAME).write_text(row("Placeholder"), encoding="utf-8")

    # The advisor's real edit, made only through the grid-save path.
    result, status = service.update_config_rows_payload(
        {"updates": [{"row_index": 1, "value": "Real Advisor Name"}]}, allow_csv_write=True
    )
    assert status == 200 and result["success"]

    # The fix under test: the grid save must reach the canonical DB row, not
    # just the disk mirror -- otherwise materialize() below has nothing
    # correct to restore from.
    db_content = get_client_file(FILE_NAME, db_path=db_path)
    assert db_content is not None and "Real Advisor Name" in db_content

    # Open Demo Plan: back up the real DB (mirrors DemoPlanService.open_demo_payload),
    # then overwrite the field with fictional demo content through the same
    # canonical write path the real demo-open flow uses.
    backup_path = Path(str(db_path) + ".before_demo")
    _backup_db(db_path, backup_path)
    _write_plan_data_file(FILE_NAME, row("Fictional Demo Name"), db_path=db_path, disk_dir=disk_dir)

    # While "in the demo", the advisor edits the same field via the grid --
    # the exact repro step from the ticket.
    result, status = service.update_config_rows_payload(
        {"updates": [{"row_index": 1, "value": "Accidental Demo Edit"}]}, allow_csv_write=True
    )
    assert status == 200 and result["success"]
    assert "Accidental Demo Edit" in (disk_dir / FILE_NAME).read_text(encoding="utf-8")

    # Open Current Plan: restore the real DB backup, then materialize() disk
    # mirrors from it -- the exact step that silently no-op'd pre-fix when
    # the DB had no row for a grid-only-edited file.
    _restore_db(backup_path, db_path)
    materialize_workspace_files(db_path=db_path, file_names=[FILE_NAME], overwrite_existing=True)

    restored = (disk_dir / FILE_NAME).read_text(encoding="utf-8")
    assert "Real Advisor Name" in restored, (
        "Open Current Plan must restore the advisor's real pre-demo edit, not "
        "leave a demo-session grid edit behind on disk (#240)"
    )
    assert "Accidental Demo Edit" not in restored
    assert "Fictional Demo Name" not in restored


def test_demo_grid_edit_leak_reproduces_without_the_fix(tmp_path, monkeypatch):
    """Sanity check that this harness actually catches the bug: with a
    disk-only write path (the pre-fix behavior -- DB row never created for a
    grid-only-edited file), materialize() must leave the demo edit in place,
    proving the assertions above are not vacuously true."""
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))

    db_path = tmp_path / "retirement_system_v10.db"
    disk_dir = tmp_path / "input"
    disk_dir.mkdir(parents=True)

    def row(value: str) -> str:
        return (
            "section,subsection,label,value,units,notes\n"
            f"Household,,client_name,{value},,\n"
        )

    # Pre-fix write path: disk only, DB client_files row never created.
    (disk_dir / FILE_NAME).write_text(row("Real Advisor Name"), encoding="utf-8")
    assert get_client_file(FILE_NAME, db_path=db_path) is None

    backup_path = Path(str(db_path) + ".before_demo")
    # DB must exist to be copied; create it via a set_client_file call for an
    # unrelated file so the schema exists, matching the real DB always having
    # other tables/rows by the time a demo is opened.
    set_client_file("unrelated.csv", "x", db_path=db_path)
    _backup_db(db_path, backup_path)

    (disk_dir / FILE_NAME).write_text(row("Accidental Demo Edit"), encoding="utf-8")

    _restore_db(backup_path, db_path)
    materialize_workspace_files(db_path=db_path, file_names=[FILE_NAME], overwrite_existing=True)

    leaked = (disk_dir / FILE_NAME).read_text(encoding="utf-8")
    assert "Accidental Demo Edit" in leaked, (
        "this harness should reproduce #240 when the DB row is missing -- if "
        "it doesn't, the test above may be passing for the wrong reason"
    )
