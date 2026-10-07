from __future__ import annotations

"""Feature-owned Plan Data file service helpers.

Route modules adapt permissions, request bodies, and HTTP response objects.  This
service owns request-independent Plan Data lifecycle behavior: the inventory and read/write
of the flat dataset files (holdings, spending, YTD ...; the sectioned plan data is the plan
file's rows and has no file form since WP4.5), blank-plan creation (the sectioned rows
through ``blank_plan_rows``, the flat files through ``make_blank_plan_files``) and the
protected-data/SQLite backup seams.
"""

import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..plan_data_registry import RetiredPlanDataFile

JsonDict = dict[str, Any]
AuditFn = Callable[[str, dict[str, Any] | None], None]


@dataclass(frozen=True)
class PlanDataFileServiceContext:
    plan_data_files: list[str]
    sqlite_db: Callable[[], Path]
    plan_db: Callable[[], Path]
    normalize_plan_data_file_name: Callable[[str], str]
    read_plan_data_file: Callable[[str], str | None]
    write_plan_data_file: Callable[[str, str], Path]
    make_blank_plan_files: Callable[[], dict[str, str]]
    blank_plan_rows: Callable[..., int]
    protected_client_data_status: Callable[..., dict[str, Any]]
    ensure_user_ui_plan_data_rows: Callable[[], None]
    audit: AuditFn | None = None


class PlanDataFileService:
    """Framework-neutral owner for Plan Data file routes."""

    def __init__(self, context: PlanDataFileServiceContext):
        self.context = context

    def _audit(self, event: str, details: dict[str, Any] | None = None) -> None:
        if self.context.audit:
            self.context.audit(event, details or {})

    def files_payload(self) -> tuple[JsonDict, int]:
        files = []
        for name in self.context.plan_data_files:
            content = self.context.read_plan_data_file(name)
            files.append({"name": name, "available": content is not None, "bytes": len(content or "")})
        return {"success": True, "files": files, "protected_client_data": self.context.protected_client_data_status()}, 200

    @staticmethod
    def _backup_file(dest: Path, tag: str) -> str | None:
        """Copy a SQLite file (WAL checkpointed first) to ``<name>.<tag>_<stamp>``."""
        if not dest.exists():
            return None
        stamp = time.strftime("%Y%m%d_%H%M%S")
        snap = Path(str(dest) + f".{tag}_{stamp}")
        try:
            conn = sqlite3.connect(str(dest))
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
        except Exception:
            pass
        shutil.copy2(str(dest), str(snap))
        return str(snap)

    def _backup_current_database(self) -> str | None:
        """Back up the plan file (the rows a blank plan clears) and the legacy database (the
        flat datasets it blanks) before anything is cleared. Returns the legacy backup path."""
        plan_backup = self._backup_file(Path(self.context.plan_db()), "before_blank")
        if plan_backup:
            self._audit("blank_plan_plan_file_backup", {"backup": plan_backup})
        return self._backup_file(Path(self.context.sqlite_db()), "before_blank")

    def start_blank_payload(self, *, ytd_blend_enabled: bool | None = None) -> tuple[JsonDict, int]:
        try:
            backup = self._backup_current_database()
            if backup:
                self._audit("blank_plan_backup", {"backup": backup})
        except Exception as exc:
            self._audit("blank_plan_backup_warning", {"error": str(exc)})
        cleared = self.context.blank_plan_rows(ytd_blend_enabled=ytd_blend_enabled)
        if ytd_blend_enabled is not None:
            self._audit("blank_plan_ytd_blend_choice", {"ytd_blend_enabled": bool(ytd_blend_enabled)})
        files = self.context.make_blank_plan_files()
        written = []
        for name, content in files.items():
            path = self.context.write_plan_data_file(name, content)
            written.append({"name": name, "path": str(path), "bytes": len(content)})
        try:
            self.context.ensure_user_ui_plan_data_rows()
        except Exception as exc:
            self._audit("blank_plan_ui_row_warning", {"error": str(exc)})
        self._audit("blank_plan_started", {"files": [w["name"] for w in written], "plan_values_cleared": cleared})
        return {"success": True, "files": written, "plan_values_cleared": cleared, "source": "blank_plan_defaults"}, 200

    def get_file_payload(self, file_name: str) -> tuple[JsonDict, int]:
        try:
            name = self.context.normalize_plan_data_file_name(file_name)
            try:
                self.context.ensure_user_ui_plan_data_rows()
            except Exception:
                # Read endpoints should not fail just because the UI-row mirror
                # cannot be refreshed; save endpoints still surface write errors.
                pass
            content = self.context.read_plan_data_file(name)
        except RetiredPlanDataFile as exc:
            return {"success": False, "error": str(exc)}, 410
        except ValueError as exc:
            return {"success": False, "error": str(exc)}, 400
        if content is None:
            return {"success": False, "error": "Plan Data file not found"}, 404
        return {"success": True, "file": name, "content": content, "content_type": "text/csv; charset=utf-8"}, 200

    def save_file_payload(self, file_name: str, content: str) -> tuple[JsonDict, int]:
        try:
            name = self.context.normalize_plan_data_file_name(file_name)
            path = self.context.write_plan_data_file(name, str(content))
            self.context.ensure_user_ui_plan_data_rows()
        except RetiredPlanDataFile as exc:
            return {"success": False, "error": str(exc)}, 410
        except ValueError as exc:
            return {"success": False, "error": str(exc)}, 400
        except PermissionError as exc:
            return {"success": False, "error": f"Could not write {Path(file_name).name}. Close the CSV if it is open in Excel, check folder permissions, and try again. Details: {exc}"}, 500
        except Exception as exc:
            return {"success": False, "error": f"Could not save {Path(file_name).name}: {exc}"}, 500
        self._audit("plan_data_file_saved", {"file": name, "bytes": len(str(content)), "path": str(path)})
        return {"success": True, "file": name, "path": str(path), "bytes": len(str(content))}, 200
