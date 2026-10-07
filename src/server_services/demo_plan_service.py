from __future__ import annotations

"""Feature-owned Open Demo Plan / Open Current Plan logic (ticket #240).

Route modules adapt permissions and request bodies. This service owns the
demo-plan swap-in/swap-out semantics: a one-time backup of the plan file and the legacy
database, applying the demo household, and restoring the pre-demo files from those backups.
The backup file's existence is the sole source of truth for whether a demo is currently
active -- no other flag (in-memory or marker file) is ever trusted for that decision, so a
crash or restart can't cause the real backup to be silently clobbered.

WP4.5: the sectioned plan data is the plan file's rows, so the demo swaps PLAN FILES: Open
Demo copies ``plan.rpx`` to ``plan.rpx.before_demo``, builds the demo plan file (a copy of the
slot's file when there is one, else the ``input/demo`` CSV set read once through the
``csv_exchange`` importer) and replaces the active plan with it through the validated
``plan_db_replace`` path; Open Current Plan puts the backup back the same way. No plan CSV
file is written or read at runtime. WP8.4 replaces this swap with the plan registry (a demo
plan file beside the real one).

The flat datasets (holdings, liabilities, spending, YTD ... ) still live in the legacy local
database's ``client_files`` until WP6, so they ride along as before: the legacy database is
backed up and restored beside the plan file, and every flat demo file is applied through the
real plan-data write path.

TEXT_BACKUP_FILES are read by the app but are not in PLAN_DATA_CSV_FILES, so neither the
caller's file list nor the restore-side materialize() covers them, yet leaving the real file
in place during a demo leaks real plan data. Each one is applied from input/demo/ on open and
restored from its own text backup:

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

The demo slot (local_state/demo_plan/, see DEMO_SLOT_DIR): Open Current Plan
used to simply discard whatever was in the demo when it swapped the real files
back. Restore now captures the demo's live state into this slot first (the demo plan file as
``plan.rpx`` and each flat file), and Open Demo Plan prefers a file from the slot over its
input/demo/ counterpart, so edits made during one demo session are still there the next
time the demo is opened. input/demo/ itself is never written to -- it stays the pristine
first-run seed, and "Reset Demo to Defaults" just deletes the slot so the next open falls back
to it.
"""

import json
import os
import shutil
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..active_plan import build_plan_file_from_csv_folder, ensure_plan_file
from ..plan_db_replace import PLAN_FILE_TABLES, copy_sqlite_file, replace_active_db, validate_plan_file

JsonDict = dict[str, Any]
TEXT_BACKUP_FILES = (
    "client_spending_budget.recovery_seed.csv",
    "client_spending_rules.csv",
    "spending_category_map.csv",
    "spending_budget.csv",
)
# Persistent home for demo edits, under the DB's parent (local_state/). Kept
# separate from input/demo/ (which ships in the repo and must stay pristine
# for the anti-leak tests) and from the live plan slot.
DEMO_SLOT_DIR = "demo_plan"
# The demo plan file's name inside the slot.
SLOT_PLAN_FILE = "plan.rpx"


@dataclass(frozen=True)
class DemoPlanServiceContext:
    sqlite_db: Callable[[], Path]
    plan_db: Callable[[], Path]
    demo_dir: Callable[[], Path]
    plan_data_csv_files: list[str]
    read_plan_data_file: Callable[[str], str | None]
    write_plan_data_file: Callable[[str, str], Path]
    ensure_user_ui_plan_data_rows: Callable[[], None]
    materialize: Callable[[], None]
    audit: Callable[[str, dict[str, Any]], None] | None = None
    demo_slot_dir: Callable[[], Path] | None = None
    # read_plan_data_file is DB-first (see app_core._read_plan_data_file) -- correct for the
    # TEXT_BACKUP_FILES restore path above. Capture reads the on-disk copy, the same thing the
    # flat-file editors write, or an edit made during a demo could be dropped from the slot.
    # Defaulted so existing constructions/tests are unaffected; falls back to
    # read_plan_data_file when not supplied.
    read_plan_data_disk_file: Callable[[str], str | None] | None = None


class DemoPlanService:
    """Framework-neutral owner for Open Demo Plan / Open Current Plan."""

    def __init__(self, context: DemoPlanServiceContext):
        self.context = context

    def _audit(self, event: str, details: dict[str, Any] | None = None) -> None:
        if self.context.audit:
            self.context.audit(event, details or {})

    def _backup_path(self) -> Path:
        """The pre-demo copy of the plan file: its existence is what ``is_active`` means."""
        return Path(str(self.context.plan_db()) + ".before_demo")

    def _legacy_backup_path(self) -> Path:
        """The pre-demo copy of the legacy local database (the flat datasets' ``client_files``)."""
        return Path(str(self.context.sqlite_db()) + ".before_demo")

    def _file_backup_path(self, name: str) -> Path:
        return self.context.sqlite_db().parent / f"{name}.before_demo"

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

    def _seed_plan_file(self, slot_dir: Path, demo_dir: Path, dest: Path) -> str:
        """Build the demo plan file at ``dest``: a copy of the slot's plan file, else the
        ``input/demo`` CSV set read through the importer. Returns "slot" or "demo"."""
        slot_plan = slot_dir / SLOT_PLAN_FILE
        if slot_plan.is_file():
            copy_sqlite_file(slot_plan, dest)
            return "slot"
        if not build_plan_file_from_csv_folder(dest, demo_dir):
            raise FileNotFoundError(f"no demo plan rows found in {demo_dir}")
        return "demo"

    def open_demo_payload(self) -> JsonDict:
        backup = self._backup_path()
        plan_db = Path(self.context.plan_db())
        dest = Path(self.context.sqlite_db())
        if not backup.exists():
            # First open this session: snapshot the real plan file and legacy DB (and the
            # disk-only text files) before touching anything. If a backup is already present,
            # a demo is already active -- re-applying demo files below must not overwrite
            # any backup.
            ensure_plan_file(plan_db)  # a fresh workspace: an empty plan to back up
            copy_sqlite_file(plan_db, backup)
            if dest.exists():
                self._checkpoint_sqlite(dest)
                shutil.copy2(str(dest), str(self._legacy_backup_path()))
            for name in TEXT_BACKUP_FILES:
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

        # The plan rows: build the demo plan file beside the active one and swap it in.
        fd, tmp_name = tempfile.mkstemp(dir=str(plan_db.parent), prefix=plan_db.name + ".", suffix=".demo")
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            plan_source = self._seed_plan_file(slot_dir, demo_dir, tmp)
            replaced = replace_active_db(tmp, plan_db, required_tables=PLAN_FILE_TABLES, validate=validate_plan_file)
        finally:
            tmp.unlink(missing_ok=True)
        if not replaced.get("success"):
            raise RuntimeError(replaced.get("error") or "Could not apply the demo plan")
        written.append({"name": plan_db.name, "path": str(plan_db), "bytes": plan_db.stat().st_size, "source": plan_source})

        for name in self._demo_file_names():
            # Prefer the persistent slot per file, not per directory -- a
            # fixture added to input/demo/ in a later release must still be
            # picked up by a user who already has a slot but not that file.
            slot_src = slot_dir / name
            demo_src = demo_dir / name
            if slot_src.exists():
                src, source = slot_src, "slot"
            elif demo_src.exists():
                src, source = demo_src, "demo"
            else:
                skipped.append(name)
                continue
            content = src.read_text(encoding="utf-8-sig")
            path = self.context.write_plan_data_file(name, content)
            written.append({"name": name, "path": str(path), "bytes": len(content), "source": source})

        try:
            self.context.ensure_user_ui_plan_data_rows()
        except Exception as exc:
            self._audit("demo_plan_ui_row_warning", {"error": str(exc)})

        self._audit("demo_plan_opened", {"files": [w["name"] for w in written], "skipped": skipped})
        return {"success": True, "files": written, "skipped": skipped}

    def _capture_demo_slot(self) -> None:
        """Persist the demo's current state into the slot before the DB
        swap-back below discards it, so the next Open Demo Plan resumes where
        this session left off instead of re-seeding from input/demo/. Must
        never block the restore -- a capture failure is audited and that file
        is skipped, exactly like the existing text-backup failures. Only
        called while is_active() (restore_current_payload returns early
        otherwise), so this never runs against a real (non-demo) plan."""
        slot_dir = self._slot_dir()
        read_disk = self.context.read_plan_data_disk_file or self.context.read_plan_data_file
        try:
            slot_dir.mkdir(parents=True, exist_ok=True)
            copy_sqlite_file(self.context.plan_db(), slot_dir / SLOT_PLAN_FILE)
        except Exception as exc:
            self._audit("demo_plan_capture_warning", {"file": SLOT_PLAN_FILE, "error": str(exc)})
        for name in self._demo_file_names():
            try:
                content = read_disk(name)
                if content is None:
                    continue
                slot_dir.mkdir(parents=True, exist_ok=True)
                (slot_dir / name).write_text(content, encoding="utf-8")
            except Exception as exc:
                self._audit("demo_plan_capture_warning", {"file": name, "error": str(exc)})

    def reset_demo_payload(self) -> JsonDict:
        """Delete the persistent demo slot so the next Open Demo Plan re-seeds
        from the shipped input/demo/ fixtures. Refused while a demo is open --
        closing it would immediately re-capture the very state being reset,
        so this is only ever reachable from the real plan."""
        if self.is_active():
            return {
                "success": False,
                "error": "Close the demo (Open Current Plan) before resetting it.",
            }
        slot_dir = self._slot_dir()
        if slot_dir.exists():
            shutil.rmtree(slot_dir)
        self._audit("demo_plan_slot_reset", {"slot": str(slot_dir)})
        return {"success": True, "reset": True}

    def restore_current_payload(self) -> JsonDict:
        backup = self._backup_path()
        if not backup.exists():
            return {"success": True, "restored": False}

        self._capture_demo_slot()

        plan_db = Path(self.context.plan_db())
        result = replace_active_db(backup, plan_db, required_tables=PLAN_FILE_TABLES, validate=validate_plan_file)
        if not result.get("success"):
            self._audit("demo_plan_restore_failed", {"error": result.get("error")})
            return {
                "success": False,
                "error": result.get("error") or "Could not restore your plan.",
                "restored": False,
            }
        legacy_backup = self._legacy_backup_path()
        if legacy_backup.exists():
            legacy = replace_active_db(legacy_backup, Path(self.context.sqlite_db()))
            if not legacy.get("success"):
                self._audit("demo_plan_restore_legacy_warning", {"error": legacy.get("error")})
            else:
                try:
                    legacy_backup.unlink()
                except Exception:
                    pass

        try:
            self.context.materialize()
        except Exception as exc:
            self._audit("demo_plan_materialize_warning", {"error": str(exc)})

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
