from __future__ import annotations

"""Build snapshot and output fingerprint contract.

This sidecar is intentionally additive: it records reproducibility metadata
beside existing workbook/report outputs without changing any report format.
"""

from datetime import datetime, UTC
import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .version import VERSION

SNAPSHOT_FILENAME = "build_snapshot.json"
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
    """Compare a parsed build snapshot to the current local SQLite database."""
    current_record: dict[str, Any] = {}
    if sqlite_db_path:
        current_record = _file_record(Path(sqlite_db_path))
    snap_record = (snapshot or {}).get("sqlite_database_snapshot") or (snapshot or {}).get("sqlite_database") or {}
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


def restore_sqlite_database_from_snapshot(snapshot_path: str | Path, active_sqlite_db_path: str | Path, *, backup_suffix: str | None = None) -> dict[str, Any]:
    """Restore the SQLite database copy referenced by a build snapshot.

    The current active DB is copied to ``*.before_snapshot_restore_<ts>`` before
    replacement.  The caller is responsible for exposing this only in local,
    trusted desktop contexts.
    """
    snapshot_file = Path(snapshot_path)
    snapshot = read_build_snapshot(snapshot_file)
    if not snapshot:
        return {"success": False, "error": "Snapshot file is missing or not build_snapshot_v1."}
    snap_record = snapshot.get("sqlite_database_snapshot") or {}
    db_copy = Path(str(snap_record.get("path") or snapshot_file.parent / SNAPSHOT_DB_FILENAME))
    if not db_copy.is_absolute():
        db_copy = snapshot_file.parent / db_copy
    if not db_copy.exists() or not db_copy.is_file():
        return {"success": False, "error": "Snapshot database copy is missing.", "snapshot_database_path": str(db_copy)}
    expected_hash = str(snap_record.get("sha256") or "")
    actual_hash = sha256_file(db_copy)
    if expected_hash and actual_hash != expected_hash:
        return {"success": False, "error": "Snapshot database hash mismatch.", "expected_sha256": expected_hash, "actual_sha256": actual_hash}
    active = Path(active_sqlite_db_path)
    active.parent.mkdir(parents=True, exist_ok=True)
    backup_path = None
    if active.exists():
        stamp = backup_suffix or datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_path = active.with_name(active.name + f".before_snapshot_restore_{stamp}")
        _checkpoint_sqlite(active)
        shutil.copy2(str(active), str(backup_path))
    shutil.copy2(str(db_copy), str(active))
    return {
        "success": True,
        "schema": "plan_snapshot_restore_v1",
        "restored_from": str(snapshot_file),
        "restored_database": str(db_copy),
        "active_database": str(active),
        "backup_database": str(backup_path) if backup_path else "",
        "sha256": actual_hash,
    }

def write_build_snapshot(
    output_dir: str | Path,
    *,
    build_id: str = "",
    plan_input_fingerprint: dict[str, Any] | None = None,
    summary: dict[str, Any] | None = None,
    output_files: Iterable[str] | None = None,
    system_config_path: str | Path | None = None,
    pricing_diagnostics_path: str | Path | None = None,
    sqlite_db_path: str | Path | None = None,
) -> dict[str, Any]:
    out = Path(output_dir)
    files = list(output_files or [
        "retirement_plan.xlsx",
        "retirement_dashboard.html",
        "results_explorer_model.json",
        "plan_summary.json",
        "pricing_diagnostics.json",
    ])
    artifacts = [_file_record(out / name) for name in files]
    system_config = _file_record(Path(system_config_path)) if system_config_path else {}
    pricing_diagnostics = _file_record(Path(pricing_diagnostics_path)) if pricing_diagnostics_path else _file_record(out / "pricing_diagnostics.json")
    sqlite_database = _file_record(Path(sqlite_db_path)) if sqlite_db_path else {}
    sqlite_database_snapshot = capture_sqlite_database_snapshot(sqlite_db_path, out) if sqlite_db_path else {"exists": False, "reason": "sqlite_db_path_not_provided", "file": SNAPSHOT_DB_FILENAME}
    snapshot = {
        "success": True,
        "schema": SNAPSHOT_SCHEMA,
        "version": VERSION,
        "build_id": build_id,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": "sqlite_snapshot",
        "input_fingerprint": plan_input_fingerprint or {},
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
    out.mkdir(parents=True, exist_ok=True)
    (out / SNAPSHOT_FILENAME).write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    return snapshot


def read_build_snapshot(path: str | Path) -> dict[str, Any] | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("schema") != SNAPSHOT_SCHEMA:
        return None
    return data
