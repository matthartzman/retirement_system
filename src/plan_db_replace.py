"""Single validated path for replacing the active plan file (the SQLite ``plan.rpx``).

System review 2026-09-25, WI-201 (closes ARC-005 and QA-004).  Load Saved Plan
(``PlanFileService.load_file``), snapshot restore
(``build_snapshot.restore_sqlite_database_from_snapshot``) and the demo swap used to implement
DB replacement separately, with non-overlapping safeguards: one validated
nothing and removed WAL sidecars, the other checked a hash but left a stale
``-wal`` beside the replaced file.  All go through :func:`replace_active_db`.

WP4.5: the file replaced is the plan file (``active_plan.active_plan_path()``), not the
legacy local database. :func:`validate_plan_file` is the plan-file check (the tables of
``PlanStore`` and an open through ``PlanStore``, which also upgrades the incoming copy).
Callers close every ``PlanStore`` they hold before replacing the file (an open connection
blocks the replace on Windows).

Order of operations (nothing touches the active DB until every check passes):

1. Copy ``src`` to a temp file beside the active DB (never mutate the source).
2. Validate the copy: SQLite header, ``PRAGMA integrity_check`` and the
   required tables.
3. ``PRAGMA wal_checkpoint(TRUNCATE)`` the active DB and verify the busy flag
   is clear -- a busy checkpoint means WAL frames are not in the main file, so
   the backup would silently lose them.
4. Back the active DB up with the SQLite backup API (WAL-consistent).
5. Remove sidecars, ``os.replace`` the temp file, remove sidecars again.
6. Optionally run the plan-data migration (caller-supplied, never fatal).
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable

SQLITE_HEADER = b"SQLite format 3\x00"

# ``client_files`` is created by config_backend.init_sqlite for the legacy local database.
DEFAULT_REQUIRED_TABLES: tuple[str, ...] = ("client_files",)
# The tables of a plan file (``PlanStore`` schema v1).
PLAN_FILE_TABLES: tuple[str, ...] = ("plan_rows", "plan_revisions", "revision_rows", "plan_meta")


def sidecar_paths(db_path: Path) -> list[Path]:
    return [Path(str(db_path) + suffix) for suffix in ("-wal", "-shm")]


def remove_sidecars(db_path: Path) -> int:
    removed = 0
    for path in sidecar_paths(db_path):
        try:
            if path.exists():
                path.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def validate_plan_db(path: Path, required_tables: Iterable[str] = DEFAULT_REQUIRED_TABLES) -> str | None:
    """Return an error message if ``path`` is not a healthy plan DB, else None."""
    try:
        with path.open("rb") as handle:
            if handle.read(len(SQLITE_HEADER)) != SQLITE_HEADER:
                return "The selected file is not a SQLite plan database."
    except OSError as exc:
        return f"Could not read the selected file: {exc}"
    try:
        conn = sqlite3.connect(str(path))
        try:
            rows = conn.execute("PRAGMA integrity_check").fetchall()
            if [r[0] for r in rows] != ["ok"]:
                return "The selected plan database failed its integrity check."
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return f"The selected file is not a readable plan database: {exc}"
    missing = [t for t in required_tables if t not in tables]
    if missing:
        return "The selected file is not a plan database (missing table: " + ", ".join(missing) + ")."
    return None


def validate_plan_file(path: Path) -> str | None:
    """``replace_active_db``'s ``validate`` hook for a plan file: the file must open as a
    ``PlanStore`` (right application id, a schema version this code can use; an older plan
    is upgraded in place, the incoming temp copy only). Returns an error message or None."""
    from .stores import PlanStore

    try:
        PlanStore.open(path, create=False).close()
    except Exception as exc:  # noqa: BLE001 - a StoreError, or any sqlite error on a file that is no database
        return f"The selected file is not a usable plan file: {exc}"
    return None


def copy_sqlite_file(src: Path | str, dest: Path | str) -> None:
    """Copy a SQLite database (WAL included) to ``dest`` through the SQLite backup API and
    an atomic replace, so ``dest`` is a consistent, self-contained file."""
    src_p, dest_p = Path(src), Path(dest)
    dest_p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(dest_p.parent), prefix=dest_p.name + ".", suffix=".tmp")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        _backup_with_api(src_p, tmp)
        os.replace(str(tmp), str(dest_p))
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def _checkpoint_truncate(db_path: Path) -> str | None:
    """Truncate the WAL; return an error string if the checkpoint was blocked."""
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None  # unreadable active DB: nothing to preserve, replacement may proceed
    if row and int(row[0]) != 0:
        return "The active plan database is busy (another process holds it open); nothing was changed. Close other work and try again."
    return None


def _backup_with_api(active: Path, backup_path: Path) -> None:
    src = sqlite3.connect(str(active))
    try:
        dst = sqlite3.connect(str(backup_path))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def replace_active_db(
    src: Path | str,
    active: Path | str,
    *,
    backup_path: Path | str | None = None,
    required_tables: Iterable[str] = DEFAULT_REQUIRED_TABLES,
    validate: Callable[[Path], str | None] | None = None,
    migrate: Callable[[Path], Any] | None = None,
) -> dict[str, Any]:
    """Validate ``src`` and atomically make it the active plan DB.

    Returns ``{"success": False, "error": ...}`` with the active DB untouched
    on any validation or busy-checkpoint failure.  On success returns
    ``{"success": True, "backup": <path or None>, "sidecars_removed": n,
    "migration": <result or None>}``.
    """
    src_p = Path(src)
    active_p = Path(active)
    if not src_p.exists() or not src_p.is_file():
        return {"success": False, "error": "Saved plan file not found"}
    active_p.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(dir=str(active_p.parent), prefix=active_p.name + ".", suffix=".incoming")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copyfile(str(src_p), str(tmp))
        error = validate_plan_db(tmp, required_tables)
        if not error and validate is not None:
            error = validate(tmp)
        if error:
            return {"success": False, "error": error}
        backup: Path | None = None
        if active_p.exists():
            error = _checkpoint_truncate(active_p)
            if error:
                return {"success": False, "error": error}
            if backup_path is not None:
                backup = Path(backup_path)
                try:
                    _backup_with_api(active_p, backup)
                except sqlite3.Error:
                    shutil.copy2(str(active_p), str(backup))
        removed = remove_sidecars(active_p)
        os.replace(str(tmp), str(active_p))
        removed += remove_sidecars(active_p)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass

    migration = None
    if migrate is not None:
        try:
            migration = migrate(active_p)
        except Exception as exc:  # noqa: BLE001 - migration must never undo a completed replace
            migration = {"error": str(exc)}
    return {"success": True, "backup": str(backup) if backup else None, "sidecars_removed": removed, "migration": migration}
