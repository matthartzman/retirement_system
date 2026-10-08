from __future__ import annotations

"""Build snapshot and output fingerprint contract.

The snapshot is stored with the build's results (``build_results.snapshot_json`` in the plan
file): reproducibility metadata for the workbook/report outputs, without changing any report format.
"""

from datetime import datetime, UTC
import hashlib
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .active_plan import build_part_record
from .version import VERSION

SNAPSHOT_SCHEMA = "build_snapshot_v1"
SNAPSHOT_DB_FILENAME = "plan_database_snapshot.rpx"


def sha256_file(path: str | Path) -> str:
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_record(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {
        "file": path.name,
        "exists": path.exists() and path.is_file(),
        "path": str(path),
    }
    if record["exists"]:
        stat = path.stat()
        record.update({
            "bytes": stat.st_size,
            "sha256": sha256_file(path),
            "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        })
    return record




def _checkpoint_sqlite(path: Path) -> None:
    if not path.exists():
        return
    try:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("PRAGMA wal_checkpoint(FULL)")
        finally:
            conn.close()
    except Exception:
        # A locked database should not fail the report build; the file record below
        # still documents whether the active database was readable.
        pass


def checkpoint_sqlite_database(sqlite_db_path: str | Path | None) -> None:
    """Flush the WAL into the main database file, if there is one to flush.

    A WAL checkpoint touches the main .db file's mtime even when the plan's
    logical content hasn't changed. capture_sqlite_database_snapshot() (below)
    needs the checkpoint immediately before it copies the DB for the .rpx
    snapshot, but that copy happens at the very end of the build pipeline --
    after retirement_plan.xlsx, the PDF, the HTML dashboard, and the other
    essential artifacts are already written. Bumping the DB's mtime that late
    made every one of those artifacts look "stale" (older than the DB) the
    moment a build finished, per src/server_services/build_service.py's
    mtime-based staleness check -- which in turn kept
    lastBuildOk/downloadWithBuild() from ever firing the actual file
    download. Callers should invoke this once, early, before any output
    artifact is written; the later checkpoint inside
    capture_sqlite_database_snapshot() then finds nothing new to flush and is
    a no-op.
    """
    if sqlite_db_path:
        _checkpoint_sqlite(Path(sqlite_db_path))


def capture_sqlite_database_snapshot(sqlite_db_path: str | Path | None, output_dir: str | Path, *, filename: str = SNAPSHOT_DB_FILENAME) -> dict[str, Any]:
    """Copy the active SQLite plan database beside the output package.

    This is the database half of ``build_snapshot_v1``.  It makes report
    packages reproducible even after the working local database changes.  The
    function is intentionally conservative: it checkpoints the source DB when
    possible, copies one immutable ``.rpx`` file into the output directory, and
    returns normal file metadata.
    """
    if not sqlite_db_path:
        return {"exists": False, "reason": "sqlite_db_path_not_provided", "file": filename}
    source = Path(sqlite_db_path)
    out = Path(output_dir)
    target = out / filename
    if not source.exists() or not source.is_file():
        return {"exists": False, "reason": "sqlite_db_missing", "path": str(source), "file": filename}
    out.mkdir(parents=True, exist_ok=True)
    _checkpoint_sqlite(source)
    shutil.copy2(str(source), str(target))
    record = _file_record(target)
    record.update({"source_path": str(source), "snapshot_role": "sqlite_database_copy"})
    return record


def compare_snapshot_to_current(snapshot: dict[str, Any], *, sqlite_db_path: str | Path | None = None) -> dict[str, Any]:
    """Compare a parsed build snapshot to the current plan file: by the plan-state digest (plan
    rows and datasets, so the build results stored in the same file do not count), else by file hash."""
    current_record: dict[str, Any] = {}
    if sqlite_db_path:
        current_record = _file_record(Path(sqlite_db_path))
    snap_record = (snapshot or {}).get("sqlite_database_snapshot") or (snapshot or {}).get("sqlite_database") or {}
    snap_state = str((snapshot or {}).get("plan_state") or "")
    current_state = ""
    if snap_state and current_record.get("exists"):
        from .active_plan import plan_state  # noqa: PLC0415

        try:
            current_state = plan_state(sqlite_db_path)
        except Exception:
            current_state = ""
    if snap_state and current_state:
        snap_hash, current_hash = snap_state, current_state
    else:
        snap_hash = str(snap_record.get("sha256") or "")
        current_hash = str(current_record.get("sha256") or "")
    return {
        "success": True,
        "schema": "plan_snapshot_compare_v1",
        "snapshot_schema": (snapshot or {}).get("schema", ""),
        "snapshot_build_id": (snapshot or {}).get("build_id", ""),
        "snapshot_generated_at": (snapshot or {}).get("generated_at", ""),
        "snapshot_database": snap_record,
        "current_database": current_record,
        "database_matches": bool(snap_hash and current_hash and snap_hash == current_hash),
        "hashes_available": bool(snap_hash and current_hash),
    }


def restore_sqlite_database_from_snapshot(snapshot: dict[str, Any] | None, active_sqlite_db_path: str | Path, *, output_dir: str | Path | None = None, backup_suffix: str | None = None, migrate: Any = None) -> dict[str, Any]:
    """Restore the plan file copy referenced by a build snapshot (WP4.5: the snapshot's
    database copy is the plan file the build read).

    The current plan file is copied to ``*.before_snapshot_restore_<ts>`` before
    replacement.  The caller is responsible for exposing this only in local,
    trusted desktop contexts.
    """
    if not snapshot or snapshot.get("schema") != SNAPSHOT_SCHEMA:
        return {"success": False, "error": "Build snapshot is missing or not build_snapshot_v1."}
    snap_record = snapshot.get("sqlite_database_snapshot") or {}
    out_dir = Path(output_dir) if output_dir is not None else Path(".")
    db_copy = Path(str(snap_record.get("path") or out_dir / SNAPSHOT_DB_FILENAME))
    if not db_copy.is_absolute():
        db_copy = out_dir / db_copy
    if not db_copy.exists() or not db_copy.is_file():
        return {"success": False, "error": "Snapshot database copy is missing.", "snapshot_database_path": str(db_copy)}
    expected_hash = str(snap_record.get("sha256") or "")
    actual_hash = sha256_file(db_copy)
    if expected_hash and actual_hash != expected_hash:
        return {"success": False, "error": "Snapshot database hash mismatch.", "expected_sha256": expected_hash, "actual_sha256": actual_hash}
    active = Path(active_sqlite_db_path)
    backup_path = None
    if active.exists():
        stamp = backup_suffix or datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_path = active.with_name(active.name + f".before_snapshot_restore_{stamp}")
    # The build results live in the plan file the copy predates: carry the current ones over.
    from .active_plan import read_build_results, write_build_results  # noqa: PLC0415

    carried = read_build_results(path=active)
    # Shared validated replacement (WI-201): integrity/table check, verified
    # checkpoint, SQLite-API backup, atomic replace, sidecar cleanup.
    from .plan_db_replace import PLAN_FILE_TABLES, replace_active_db, validate_plan_file  # noqa: PLC0415

    replaced = replace_active_db(db_copy, active, backup_path=backup_path, required_tables=PLAN_FILE_TABLES,
                                 validate=validate_plan_file, migrate=migrate)
    if not replaced.get("success"):
        return {"success": False, "error": replaced.get("error", "Snapshot restore failed.")}
    if carried:
        write_build_results(carried["build_id"], path=active, plan_state=carried["plan_state"],
                            **{k: carried[k] for k in ("summary", "explorer", "package", "snapshot") if carried[k]})
    return {
        "success": True,
        "schema": "plan_snapshot_restore_v1",
        "restored_from": str(snapshot.get("build_id") or ""),
        "restored_database": str(db_copy),
        "active_database": str(active),
        "backup_database": str(backup_path) if backup_path else "",
        "sha256": actual_hash,
    }

def make_build_snapshot(
    output_dir: str | Path,
    *,
    build_id: str = "",
    plan_input_fingerprint: dict[str, Any] | None = None,
    plan_state: str = "",
    summary: dict[str, Any] | None = None,
    explorer: dict[str, Any] | None = None,
    output_files: Iterable[str] | None = None,
    system_config_path: str | Path | None = None,
    pricing: dict[str, Any] | None = None,
    sqlite_db_path: str | Path | None = None,
) -> dict[str, Any]:
    """The build snapshot document (the caller stores it in ``build_results``); copies the plan
    file beside the outputs as ``plan_database_snapshot.rpx``."""
    out = Path(output_dir)
    files = list(output_files or [
        "retirement_plan.xlsx",
        "retirement_dashboard.html",
    ])
    artifacts = [_file_record(out / name) for name in files]
    artifacts.append(build_part_record("explorer", explorer or {}))
    artifacts.append(build_part_record("summary", summary or {}))
    artifacts.append(build_part_record("pricing", pricing or {}))
    system_config = _file_record(Path(system_config_path)) if system_config_path else {}
    pricing_diagnostics = build_part_record("pricing", pricing or {})
    sqlite_database = _file_record(Path(sqlite_db_path)) if sqlite_db_path else {}
    sqlite_database_snapshot = capture_sqlite_database_snapshot(sqlite_db_path, out) if sqlite_db_path else {"exists": False, "reason": "sqlite_db_path_not_provided", "file": SNAPSHOT_DB_FILENAME}
    return {
        "success": True,
        "schema": SNAPSHOT_SCHEMA,
        "version": VERSION,
        "build_id": build_id,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": "sqlite_snapshot",
        "input_fingerprint": plan_input_fingerprint or {},
        "plan_state": plan_state,
        "system_config": system_config,
        "pricing_diagnostics": pricing_diagnostics,
        "sqlite_database": sqlite_database,
        "sqlite_database_snapshot": sqlite_database_snapshot,
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
        "summary": summary or {},
        "environment": {
            "python": os.environ.get("PYTHON_VERSION", ""),
            "build_started_at_ts": os.environ.get("RETIREMENT_SYSTEM_BUILD_STARTED_AT_TS", ""),
        },
    }
