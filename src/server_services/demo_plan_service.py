from __future__ import annotations

"""Feature-owned Open Demo Plan / Open Current Plan logic (ticket #240).

Route modules adapt permissions and request bodies. This service owns the
demo-plan swap-in/swap-out semantics: a one-time DB backup, applying the
input/demo/*.csv fixture through the real plan-data write path, and
restoring the pre-demo DB from that backup. The backup file's existence is
the sole source of truth for whether a demo is currently active -- no other
flag (in-memory or marker file) is ever trusted for that decision, so a
crash or restart can't cause the real backup to be silently clobbered.

client_data.csv (and its derived .json/.yaml) is the one plan-data file that
lives only on disk, never in the SQLite DB (see app_core._read_plan_data_file /
_write_plan_data_file) -- so it is NOT restored by swapping the DB back. It
gets its own small text backup alongside the DB backup for that reason.

TEXT_BACKUP_FILES are the same story for a different reason: they are read by
the app but are not in PLAN_DATA_CSV_FILES, so neither the caller's file list
nor the restore-side materialize() covers them, yet leaving the real file in
place during a demo leaks real plan data. Each one is applied from input/demo/
on open and restored from its own text backup, exactly like client_data.csv:

  * client_spending_budget.recovery_seed.csv --
    spending_tracker.load_unified_budget() silently merges this into the
    budget whenever the category rows total zero, which would pull the
    advisor's own annualized actuals into the demo household's budget.
  * spending_category_map.csv -- the transaction category vocabulary
    (spending_tracker/import_preview read it). The real one names the
    advisor's own categories and note counterparty, so a demo left the real
    "Gifts - Family 12", "Cubs Tickets" and "RedMane Annual Note P&I" on the
    spending screens while every other screen showed the demo household.
  * spending_budget.csv -- group-level budget percentages seeded from the
    advisor's actual transaction history.
  * client_spending_rules.csv -- merchant/category mapping rules. input/demo/
    already shipped a fictionalized copy of this one, but nothing applied it.

DEMO_SLOT_DIR (local_state/demo_plan/) is the persistent working copy of the
demo, distinct from the read-only input/demo/ fixtures shipped in the repo.
open_demo_payload() prefers a file in the slot over the matching input/demo/
fixture, per file (not per directory), so a slot missing one file still
falls back to the fixture for just that file. restore_current_payload()
captures the demo's live state into the slot before swapping the real DB
back, so edits made during a demo session persist into the next Open Demo
Plan instead of being discarded. The slot has no reset mechanism yet in this
file -- see the follow-up PR for "Reset Demo to Defaults".
"""

import json
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

JsonDict = dict[str, Any]
CLIENT_DATA_CSV = "client_data.csv"
TEXT_BACKUP_FILES = (
    "client_spending_budget.recovery_seed.csv",
    "client_spending_rules.csv",
    "spending_category_map.csv",
    "spending_budget.csv",
)
DEMO_SLOT_DIR = "demo_plan"


@dataclass(frozen=True)
class DemoPlanServiceContext:
    sqlite_db: Callable[[], Path]
    demo_dir: Callable[[], Path]
    plan_data_csv_files: list[str]
    read_plan_data_file: Callable[[str], str | None]
    write_plan_data_file: Callable[[str, str], Path]
    sync_config_backends: Callable[[], Any]
    ensure_user_ui_plan_data_rows: Callable[[], None]
    load_saved_db: Callable[[dict[str, Any]], dict[str, Any]]
    materialize: Callable[[], None]
    audit: Callable[[str, dict[str, Any]], None] | None = None
    demo_slot_dir: Callable[[], Path] | None = None


class DemoPlanService:
    """Framework-neutral owner for Open Demo Plan / Open Current Plan."""

    def __init__(self, context: DemoPlanServiceContext):
        self.context = context

    def _audit(self, event: str, details: dict[str, Any] | None = None) -> None:
        if self.context.audit:
            self.context.audit(event, details or {})

    def _backup_path(self) -> Path:
        return Path(str(self.context.sqlite_db()) + ".before_demo")

    def _file_backup_path(self, name: str) -> Path:
        return self.context.sqlite_db().parent / f"{name}.before_demo"

    def _client_data_backup_path(self) -> Path:
        return self._file_backup_path(CLIENT_DATA_CSV)

    def _slot_dir(self) -> Path:
        if self.context.demo_slot_dir is not None:
            return self.context.demo_slot_dir()
        return self.context.sqlite_db().parent / DEMO_SLOT_DIR

    def _demo_file_names(self) -> list[str]:
        """Every file Open Demo Plan applies, in order, without duplicates."""
        names: list[str] = []
        for name in [*self.context.plan_data_csv_files, *TEXT_BACKUP_FILES]:
            if name not in names:
                names.append(name)
        return names

    def _marker_path(self) -> Path:
        return self.context.sqlite_db().parent / "demo_mode_marker.json"

    def _read_marker(self) -> dict[str, Any]:
        try:
            return json.loads(self._marker_path().read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _checkpoint_sqlite(self, db_path: Path) -> None:
        if not db_path.exists():
            return
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
        except Exception:
            pass

    def is_active(self) -> bool:
        return self._backup_path().exists()

    def status_payload(self) -> JsonDict:
        active = self.is_active()
        marker = self._read_marker() if active else {}
        return {"success": True, "active": active, "opened_at": marker.get("opened_at")}

    def open_demo_payload(self) -> JsonDict:
        backup = self._backup_path()
        dest = Path(self.context.sqlite_db())
        if not backup.exists():
            # First open this session: snapshot the real DB (and the
            # disk-only client_data.csv, which the DB backup can't cover)
            # before touching anything. If a backup is already present, a
            # demo is already active -- re-applying demo files below must
            # not overwrite either backup.
            if dest.exists():
                self._checkpoint_sqlite(dest)
                shutil.copy2(str(dest), str(backup))
            for name in (CLIENT_DATA_CSV, *TEXT_BACKUP_FILES):
                try:
                    real_content = self.context.read_plan_data_file(name)
                    if real_content is not None:
                        self._file_backup_path(name).write_text(real_content, encoding="utf-8")
                except Exception as exc:
                    self._audit("demo_plan_text_backup_warning", {"file": name, "error": str(exc)})
            try:
                self._marker_path().write_text(
                    json.dumps({"opened_at": time.strftime("%Y-%m-%dT%H:%M:%S")}),
                    encoding="utf-8",
                )
            except Exception as exc:
                self._audit("demo_plan_marker_warning", {"error": str(exc)})
            self._audit("demo_plan_backup_created", {"backup": str(backup)})

        demo_dir = self.context.demo_dir()
        slot_dir = self._slot_dir()
        written: list[dict[str, Any]] = []
        skipped: list[str] = []
        for name in self._demo_file_names():
            # Per-file, not per-directory: a fixture added to input/demo/ in a
            # later release is still picked up for a user who already has a
            # slot but has never seen that particular file before.
            slot_src = slot_dir / name
            from_slot = slot_src.exists()
            src = slot_src if from_slot else demo_dir / name
            if not src.exists():
                skipped.append(name)
                continue
            content = src.read_text(encoding="utf-8-sig")
            path = self.context.write_plan_data_file(name, content)
            written.append({
                "name": name, "path": str(path), "bytes": len(content),
                "source": "slot" if from_slot else "fixture",
            })

        try:
            self.context.ensure_user_ui_plan_data_rows()
        except Exception as exc:
            self._audit("demo_plan_ui_row_warning", {"error": str(exc)})
        try:
            self.context.sync_config_backends()
        except Exception as exc:
            self._audit("demo_plan_sync_warning", {"error": str(exc)})

        self._audit("demo_plan_opened", {"files": [w["name"] for w in written], "skipped": skipped})
        return {"success": True, "files": written, "skipped": skipped}

    def restore_current_payload(self) -> JsonDict:
        backup = self._backup_path()
        if not backup.exists():
            return {"success": True, "restored": False}

        # Capture the demo's CURRENT state into its persistent slot before
        # swapping the DB back, so edits made during this demo session
        # survive into the next Open Demo Plan instead of being discarded.
        # Must run strictly after the is_active() check above (a demo is
        # active here) and must never be fatal -- a capture problem must not
        # block the user from getting their real plan back.
        slot_dir = self._slot_dir()
        for name in self._demo_file_names():
            try:
                content = self.context.read_plan_data_file(name)
                if content is not None:
                    slot_dir.mkdir(parents=True, exist_ok=True)
                    (slot_dir / name).write_text(content, encoding="utf-8")
            except Exception as exc:
                self._audit("demo_plan_capture_warning", {"file": name, "error": str(exc)})

        result = self.context.load_saved_db({"path": str(backup)})
        if not result.get("success"):
            self._audit("demo_plan_restore_failed", {"error": result.get("error")})
            return {
                "success": False,
                "error": result.get("error") or "Could not restore your plan.",
                "restored": False,
            }

        try:
            self.context.materialize()
        except Exception as exc:
            self._audit("demo_plan_materialize_warning", {"error": str(exc)})

        client_data_backup = self._client_data_backup_path()
        if client_data_backup.exists():
            try:
                real_client_data = client_data_backup.read_text(encoding="utf-8")
                self.context.write_plan_data_file(CLIENT_DATA_CSV, real_client_data)
                # client_data.json/.yaml are derived from client_data.csv --
                # regenerate them now that the real CSV is back, or they'd
                # keep showing demo values until the next unrelated save.
                sync_result = self.context.sync_config_backends() or {}
                derived = sync_result.get("derived") or {}
                # sync_config_backends() only rewrites the derived files on
                # disk. But _read_plan_data_file seeds a DB-cached copy of a
                # file the first time anything GETs it while it's missing
                # from the DB -- so if client_data.json/.yaml was ever read
                # while demo content was still on disk (e.g. a page open
                # mid-demo), the DB now holds a stale demo copy a disk-only
                # rewrite can't reach. Push the regenerated content through
                # the real write path too so any such cache entry is
                # overwritten with the restored data.
                for derived_name in ("client_data.json", "client_data.yaml"):
                    derived_path = derived.get(derived_name)
                    if derived_path and Path(derived_path).exists():
                        self.context.write_plan_data_file(derived_name, Path(derived_path).read_text(encoding="utf-8"))
            except Exception as exc:
                self._audit("demo_plan_client_data_restore_warning", {"error": str(exc)})
            try:
                client_data_backup.unlink()
            except Exception:
                pass

        # Files outside PLAN_DATA_CSV_FILES that materialize() cannot bring
        # back -- restore them from the text backup taken on open, or the
        # demo's fixture would stay behind as the advisor's live data.
        for name in TEXT_BACKUP_FILES:
            text_backup = self._file_backup_path(name)
            if not text_backup.exists():
                continue
            try:
                self.context.write_plan_data_file(name, text_backup.read_text(encoding="utf-8"))
            except Exception as exc:
                self._audit("demo_plan_text_restore_warning", {"file": name, "error": str(exc)})
            try:
                text_backup.unlink()
            except Exception:
                pass

        try:
            backup.unlink()
        except Exception:
            pass
        try:
            self._marker_path().unlink()
        except Exception:
            pass

        self._audit("demo_plan_restored", {"backup": str(backup)})
        return {"success": True, "restored": True}
