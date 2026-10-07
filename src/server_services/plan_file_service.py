from __future__ import annotations

"""Feature-owned Plan file save/load/snapshot logic.

The HTTP layer is responsible for request parsing and permissions. This service
owns SQLite file checkpoint/copy/retention semantics so desktop save/load logic
is not buried in route modules.

WP4.5: Save As, Load Saved Plan and snapshot restore operate on the plan file itself
(``plan.rpx``: ``PlanStore``'s ``plan_rows``, revisions and meta), copied or replaced through
``plan_db_replace`` (validated, backed up, atomic) with no CSV step. The legacy local
database (``sqlite_db``: the flat datasets' ``client_files``, audit and build history) is no
longer part of a saved plan until WP6 moves those datasets into the plan file; the exit
snapshot still keeps a versioned copy of both.
"""

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..plan_db_replace import PLAN_FILE_TABLES, copy_sqlite_file, replace_active_db, validate_plan_file
from ..build_snapshot import (
    SNAPSHOT_FILENAME,
    compare_snapshot_to_current,
    read_build_snapshot,
    restore_sqlite_database_from_snapshot,
)


@dataclass(frozen=True)
class PlanFileServiceContext:
    sqlite_db: Callable[[], Path]
    plan_db: Callable[[], Path]
    audit: Callable[[str, dict[str, Any]], None]
    retention_count: int = 10
    output_dir: Callable[[], Path] | None = None
    # Runs the at-rest plan-data migration against the freshly replaced plan file.
    migrate: Callable[[Path], Any] | None = None


def _sidecar_paths(db_path: Path) -> list[Path]:
    return [Path(str(db_path) + suffix) for suffix in ("-wal", "-shm")]


def _checkpoint_sqlite(db_path: Path, *, truncate: bool = False) -> None:
    if not db_path.exists():
        return
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)" if truncate else "PRAGMA wal_checkpoint(FULL)")
        finally:
            conn.close()
    except Exception:
        pass


def _remove_sidecars(db_path: Path) -> int:
    removed = 0
    for path in _sidecar_paths(db_path):
        try:
            if path.exists():
                path.unlink()
                removed += 1
        except Exception:
            pass
    return removed


class PlanFileService:
    def __init__(self, ctx: PlanFileServiceContext):
        self.ctx = ctx

    def _requested_build_snapshot_path(self, body: dict[str, Any] | None = None) -> Path:
        body = body or {}
        raw = str(body.get("snapshot_path") or "").strip()
        if raw:
            return Path(raw).expanduser()
        if self.ctx.output_dir is None:
            return Path(SNAPSHOT_FILENAME)
        return self.ctx.output_dir() / SNAPSHOT_FILENAME

    def exit_snapshot(self) -> dict[str, Any]:
        """A versioned copy of the legacy database and of the plan file; each keeps the last
        ``retention_count``."""
        src = self.ctx.sqlite_db()
        plan = self.ctx.plan_db()
        if not src.exists() and not plan.exists():
            return {"success": True, "message": "No database to snapshot"}
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out: dict[str, Any] = {"success": True}
        pruned = 0
        if src.exists():
            _checkpoint_sqlite(src)
            snapshot_name = f"retirement_system_v10.db.version_{ts}"
            shutil.copy2(str(src), str(src.parent / snapshot_name))
            pruned += self._prune_backups(src.parent, "retirement_system_v10.db.version_*")
            out["snapshot"] = snapshot_name
        if plan.exists():
            plan_snapshot = f"{plan.name}.version_{ts}"
            copy_sqlite_file(plan, plan.parent / plan_snapshot)
            pruned += self._prune_backups(plan.parent, f"{plan.name}.version_*")
            out["plan_snapshot"] = plan_snapshot
        self.ctx.audit("exit_snapshot_created", {"snapshot": out.get("snapshot"), "plan_snapshot": out.get("plan_snapshot"), "pruned": pruned})
        return out

    def save_as(self, body: dict[str, Any]) -> dict[str, Any]:
        """Copy the plan file to a user-chosen path (a consistent copy through the SQLite
        backup API; the WAL is folded in)."""
        dest_path = str(body.get("path", "")).strip()
        if not dest_path:
            return {"success": False, "error": "No path provided"}
        src = self.ctx.plan_db()
        if not src.exists():
            return {"success": False, "error": "No active plan file found"}
        dest = Path(dest_path).expanduser()
        copy_sqlite_file(src, dest)
        self.ctx.audit("plan_saved_as", {"dest": str(dest)})
        return {"success": True}

    def load_file(self, body: dict[str, Any]) -> dict[str, Any]:
        """Replace the plan file with a user-chosen plan file (validated first; the current
        plan is backed up to ``<plan>.before_load_<ts>``)."""
        src_raw = str(body.get("path", "")).strip()
        if not src_raw:
            return {"success": False, "error": "No path provided"}
        src = Path(src_raw).expanduser()
        if not src.exists() or not src.is_file():
            return {"success": False, "error": "Saved plan file not found"}
        dest = self.ctx.plan_db()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{dest.name}.before_load_{ts}"
        backup = dest.parent / backup_name
        result = replace_active_db(src, dest, backup_path=backup, required_tables=PLAN_FILE_TABLES,
                                   validate=validate_plan_file, migrate=self.ctx.migrate)
        if not result.get("success"):
            return {"success": False, "error": result.get("error", "Could not load plan file")}
        pruned = self._prune_backups(dest.parent, f"{dest.name}.before_load_*")
        self.ctx.audit(
            "plan_loaded_file",
            {"source": str(src), "backup": backup_name if backup.exists() else None, "sidecars_removed": result.get("sidecars_removed", 0), "pruned": pruned},
        )
        return {"success": True, "backup": backup_name if backup.exists() else None}

    def _prune_backups(self, directory: Path, pattern: str) -> int:
        """Keep only the most recent retention_count snapshots matching pattern.

        Recovery backups like before_load_* accumulate one per Load Saved Plan
        action; without pruning they grow unbounded over years of normal use.
        """
        snapshots = sorted(directory.glob(pattern), key=lambda p: p.name)
        pruned = 0
        for old in snapshots[:-max(1, int(self.ctx.retention_count or 10))]:
            try:
                old.unlink()
                pruned += 1
            except Exception:
                pass
        return pruned

    def snapshot_compare_payload(self, body: dict[str, Any] | None = None) -> tuple[dict[str, Any], int]:
        snapshot_path = self._requested_build_snapshot_path(body)
        snapshot = read_build_snapshot(snapshot_path)
        if not snapshot:
            return {"success": False, "error": "Build snapshot not found or invalid.", "snapshot_path": str(snapshot_path)}, 404
        payload = compare_snapshot_to_current(snapshot, sqlite_db_path=self.ctx.plan_db())
        payload["snapshot_path"] = str(snapshot_path)
        return payload, 200

    def snapshot_restore_payload(self, body: dict[str, Any] | None = None) -> tuple[dict[str, Any], int]:
        body = body or {}
        snapshot_path = self._requested_build_snapshot_path(body)
        payload = restore_sqlite_database_from_snapshot(
            snapshot_path,
            self.ctx.plan_db(),
            backup_suffix=str(body.get("backup_suffix") or "").strip() or None,
            migrate=self.ctx.migrate,
        )
        if payload.get("success"):
            self.ctx.audit("plan_snapshot_restored", {"snapshot_path": str(snapshot_path), "backup_database": payload.get("backup_database")})
            return payload, 200
        return payload, 400
