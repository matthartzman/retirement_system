from __future__ import annotations

"""Feature-owned Plan file save/load/snapshot logic.

The HTTP layer is responsible for request parsing and permissions. This service
owns SQLite file checkpoint/copy/retention semantics so desktop save/load logic
is not buried in route modules.
"""

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

try:
    from ..build_snapshot import (
        SNAPSHOT_FILENAME,
        compare_snapshot_to_current,
        read_build_snapshot,
        restore_sqlite_database_from_snapshot,
    )
except Exception:  # pragma: no cover - direct execution fallback
    from src.build_snapshot import (
        SNAPSHOT_FILENAME,
        compare_snapshot_to_current,
        read_build_snapshot,
        restore_sqlite_database_from_snapshot,
    )


@dataclass(frozen=True)
class PlanFileServiceContext:
    sqlite_db: Callable[[], Path]
    audit: Callable[[str, dict[str, Any]], None]
    retention_count: int = 10
    output_dir: Callable[[], Path] | None = None


def _sidecar_paths(db_path: Path) -> list[Path]:
    return [Path(str(db_path) + suffix) for suffix in ("-wal", "-shm")]


def _checkpoint_sqlite(db_path: Path, *, truncate: bool = False) -> None:
    if not db_path.exists():
        return
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)" if truncate else "PRAGMA wal_checkpoint(FULL)")
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
        src = self.ctx.sqlite_db()
        if not src.exists():
            return {"success": True, "message": "No database to snapshot"}
        _checkpoint_sqlite(src)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_name = f"retirement_system_v10.db.version_{ts}"
        snapshot_path = src.parent / snapshot_name
        shutil.copy2(str(src), str(snapshot_path))
        pruned = self._prune_backups(src.parent, "retirement_system_v10.db.version_*")
        self.ctx.audit("exit_snapshot_created", {"snapshot": snapshot_name, "pruned": pruned})
        return {"success": True, "snapshot": snapshot_name}

    def save_as(self, body: dict[str, Any]) -> dict[str, Any]:
        dest_path = str(body.get("path", "")).strip()
        if not dest_path:
            return {"success": False, "error": "No path provided"}
        src = self.ctx.sqlite_db()
        if not src.exists():
            return {"success": False, "error": "No active plan database found"}
        _checkpoint_sqlite(src)
        dest = Path(dest_path).expanduser()
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))
        self.ctx.audit("plan_saved_as", {"dest": str(dest)})
        return {"success": True}

    def load_file(self, body: dict[str, Any]) -> dict[str, Any]:
        src_raw = str(body.get("path", "")).strip()
        if not src_raw:
            return {"success": False, "error": "No path provided"}
        src = Path(src_raw).expanduser()
        if not src.exists() or not src.is_file():
            return {"success": False, "error": "Saved plan file not found"}
        dest = self.ctx.sqlite_db()
        dest.parent.mkdir(parents=True, exist_ok=True)
        _checkpoint_sqlite(dest)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"retirement_system_v10.db.before_load_{ts}"
        backup = dest.parent / backup_name
        if dest.exists():
            shutil.copy2(str(dest), str(backup))
        pruned = self._prune_backups(dest.parent, "retirement_system_v10.db.before_load_*")
        sidecars_removed = _remove_sidecars(dest)
        shutil.copy2(str(src), str(dest))
        _remove_sidecars(dest)
        _checkpoint_sqlite(dest, truncate=True)
        self.ctx.audit(
            "plan_loaded_file",
            {"source": str(src), "backup": backup_name if backup.exists() else None, "sidecars_removed": sidecars_removed, "pruned": pruned},
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
        payload = compare_snapshot_to_current(snapshot, sqlite_db_path=self.ctx.sqlite_db())
        payload["snapshot_path"] = str(snapshot_path)
        return payload, 200

    def snapshot_restore_payload(self, body: dict[str, Any] | None = None) -> tuple[dict[str, Any], int]:
        body = body or {}
        snapshot_path = self._requested_build_snapshot_path(body)
        payload = restore_sqlite_database_from_snapshot(
            snapshot_path,
            self.ctx.sqlite_db(),
            backup_suffix=str(body.get("backup_suffix") or "").strip() or None,
        )
        if payload.get("success"):
            self.ctx.audit("plan_snapshot_restored", {"snapshot_path": str(snapshot_path), "backup_database": payload.get("backup_database")})
            return payload, 200
        return payload, 400
