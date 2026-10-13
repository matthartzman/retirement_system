from __future__ import annotations

"""Feature-owned Plan file save/load/snapshot logic.

The HTTP layer is responsible for request parsing and permissions. This service
owns SQLite file checkpoint/copy/retention semantics so desktop save/load logic
is not buried in route modules.

WP8.4 (design F section 5A): Save As and Load Saved Plan are plan-registry operations over plan
files. Save As copies the active plan file to a new path, registers it and (by default) makes
it the active plan; Load Saved Plan registers the chosen file and activates it. Neither touches
the other plan files. Restoring a backup or a saved copy INTO the active plan file
(``load_file`` with ``mode: "restore"``, and snapshot restore) keeps ``plan_db_replace``'s
validate-then-swap path (validated copy, ``before_load`` backup, atomic replace). The exit
snapshot still keeps a versioned copy of the plan file and of the legacy database.
"""

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .. import plan_registry
from ..plan_db_replace import PLAN_FILE_TABLES, copy_sqlite_file, remove_sidecars, replace_active_db, validate_plan_file
from ..active_plan import read_build_results
from ..build_snapshot import (
    compare_snapshot_to_current,
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
    # Runs on a plan file that just became the active plan (Save As, Load Saved Plan).
    after_switch: Callable[[Path], Any] | None = None


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

    def _build_snapshot(self, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """The stored build snapshot of ``body['build_id']`` (the latest build when not given)."""
        build_id = str((body or {}).get("build_id") or "").strip() or None
        row = read_build_results(build_id, path=self.ctx.plan_db())
        return dict((row or {}).get("snapshot") or {})

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

    def _plan_view(self, rec: dict[str, Any]) -> dict[str, Any]:
        return {k: rec.get(k) for k in ("plan_id", "name", "kind", "path", "last_opened")}

    def _switch_to(self, plan_id: str) -> dict[str, Any]:
        rec = plan_registry.activate(plan_id)
        if self.ctx.after_switch is not None:
            try:
                self.ctx.after_switch(Path(rec["path"]))
            except Exception as exc:  # noqa: BLE001 - never undoes a completed switch
                self.ctx.audit("plan_after_switch_warning", {"path": rec["path"], "error": str(exc)})
        return rec

    def save_as(self, body: dict[str, Any]) -> dict[str, Any]:
        """Copy the active plan file to a user-chosen path (a consistent copy through the SQLite
        backup API; the WAL is folded in), register the copy as a user plan and, unless
        ``activate`` is false, make it the active plan."""
        dest_path = str(body.get("path", "")).strip()
        if not dest_path:
            return {"success": False, "error": "No path provided"}
        src = self.ctx.plan_db()
        if not src.exists():
            return {"success": False, "error": "No active plan file found"}
        dest = Path(dest_path).expanduser()
        if not dest.is_absolute():
            dest = Path.cwd() / dest
        same = plan_registry.same_path(src, dest)
        if not same:
            other = next((r for r in plan_registry.list_plans() if plan_registry.same_path(r["path"], dest)), None)
            if other is not None:  # never overwrite another registered plan (demo, a saved case)
                return {"success": False, "error": f"{dest} is already the plan \"{other['name']}\". Choose a different file name."}
            remove_sidecars(dest)  # a stale -wal/-shm beside an overwritten file must not be replayed
            copy_sqlite_file(src, dest)
        name = str(body.get("name") or "").strip() or dest.stem
        rec = plan_registry.register_plan_file(dest, name=name)
        activate = body.get("activate", True) not in (False, "false", "0", 0)
        if activate and not same:  # a copy of the plan in use: nothing to migrate or backfill
            rec = plan_registry.activate(rec["plan_id"])
        self.ctx.audit("plan_saved_as", {"dest": str(dest), "plan_id": rec["plan_id"], "activated": bool(activate)})
        return {"success": True, "plan": self._plan_view(rec), "activated": bool(activate)}

    def load_file(self, body: dict[str, Any]) -> dict[str, Any]:
        """Load Saved Plan. ``mode: "open"`` (default): register the chosen plan file and make it
        the active plan (no copy; the current plan file is untouched). ``mode: "restore"``: replace
        the ACTIVE plan file's contents with the chosen file (a backup or saved copy), validated
        first, the current plan backed up to ``<plan>.before_load_<ts>``."""
        src_raw = str(body.get("path", "")).strip()
        if not src_raw:
            return {"success": False, "error": "No path provided"}
        src = Path(src_raw).expanduser()
        if not src.exists() or not src.is_file():
            return {"success": False, "error": "Saved plan file not found"}
        if str(body.get("mode") or "open").strip().lower() == "restore":
            return self._restore_into_active(src)
        error = plan_registry.check_plan_file(src)
        if error:
            return {"success": False, "error": error}
        name = str(body.get("name") or "").strip() or None
        rec = plan_registry.register_plan_file(src, name=name)
        try:
            rec = self._switch_to(rec["plan_id"])
        except plan_registry.PlanRegistryError as exc:
            return {"success": False, "error": str(exc)}
        self.ctx.audit("plan_loaded_file", {"source": str(src), "plan_id": rec["plan_id"]})
        return {"success": True, "plan": self._plan_view(rec), "backup": None}

    def _restore_into_active(self, src: Path) -> dict[str, Any]:
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
            "plan_restored_file",
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
        snapshot = self._build_snapshot(body)
        if not snapshot:
            return {"success": False, "error": "Build snapshot not found or invalid."}, 404
        payload = compare_snapshot_to_current(snapshot, sqlite_db_path=self.ctx.plan_db())
        return payload, 200

    def snapshot_restore_payload(self, body: dict[str, Any] | None = None) -> tuple[dict[str, Any], int]:
        body = body or {}
        payload = restore_sqlite_database_from_snapshot(
            self._build_snapshot(body),
            self.ctx.plan_db(),
            output_dir=self.ctx.output_dir() if self.ctx.output_dir is not None else None,
            backup_suffix=str(body.get("backup_suffix") or "").strip() or None,
            migrate=self.ctx.migrate,
        )
        if payload.get("success"):
            self.ctx.audit("plan_snapshot_restored", {"build_id": payload.get("restored_from"), "backup_database": payload.get("backup_database")})
            return payload, 200
        return payload, 400
