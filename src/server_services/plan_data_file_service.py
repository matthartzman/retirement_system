from __future__ import annotations

"""Feature-owned Plan Data file service helpers.

Route modules adapt permissions, request bodies, and HTTP response objects.  This
service owns request-independent Plan Data folder lifecycle behavior: inventory,
blank-plan creation, file read/write normalization, and protected-data/SQLite
backup seams.
"""

import csv
import io
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

JsonDict = dict[str, Any]
AuditFn = Callable[[str, dict[str, Any] | None], None]


def _set_csv_row_value(content: str, section: str, subsection: str, label: str, value: str) -> str:
    """Set the value column of a single section/subsection/label CSV row in place.

    Used to stamp an explicit choice (e.g. ytd_blend_enabled) onto a freshly
    blanked Plan Data file, since the blank template otherwise leaves the
    value column empty for every row.
    """
    rows = list(csv.reader(io.StringIO(content or "")))
    changed = False
    for row in rows:
        if len(row) >= 4 and str(row[0]).strip() == section and str(row[1]).strip() == subsection and str(row[2]).strip() == label:
            row[3] = value
            changed = True
    if not changed:
        return content
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(rows)
    return out.getvalue()


@dataclass(frozen=True)
class PlanDataFileServiceContext:
    plan_data_files: list[str]
    client_data_csv_file_set: set[str]
    sqlite_db: Callable[[], Path]
    normalize_plan_data_file_name: Callable[[str], str]
    read_plan_data_file: Callable[[str], str | None]
    write_plan_data_file: Callable[[str, str], Path]
    make_blank_plan_files: Callable[[], dict[str, str]]
    protected_client_data_status: Callable[..., dict[str, Any]]
    ensure_user_ui_plan_data_rows: Callable[[], None]
    sync_config_backends: Callable[[], Any]
    write_blank_plan_data_file: Callable[[str, str], Path] | None = None
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

    def _backup_current_database(self) -> str | None:
        dest = Path(self.context.sqlite_db())
        if not dest.exists():
            return None
        stamp = time.strftime("%Y%m%d_%H%M%S")
        snap = Path(str(dest) + f".before_blank_{stamp}")
        try:
            conn = sqlite3.connect(str(dest))
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
        except Exception:
            pass
        shutil.copy2(str(dest), str(snap))
        return str(snap)

    def start_blank_payload(self, *, ytd_blend_enabled: bool | None = None) -> tuple[JsonDict, int]:
        try:
            backup = self._backup_current_database()
            if backup:
                self._audit("blank_plan_backup", {"backup": backup})
        except Exception as exc:
            self._audit("blank_plan_backup_warning", {"error": str(exc)})
        files = self.context.make_blank_plan_files()
        if ytd_blend_enabled is not None and "client_spending.csv" in files:
            files["client_spending.csv"] = _set_csv_row_value(
                files["client_spending.csv"], "Cashflow", "Spending", "ytd_blend_enabled",
                "TRUE" if ytd_blend_enabled else "FALSE",
            )
            self._audit("blank_plan_ytd_blend_choice", {"ytd_blend_enabled": bool(ytd_blend_enabled)})
        written = []
        for name, content in files.items():
            writer = self.context.write_blank_plan_data_file or self.context.write_plan_data_file
            path = writer(name, content)
            written.append({"name": name, "path": str(path), "bytes": len(content)})
        try:
            self.context.ensure_user_ui_plan_data_rows()
        except Exception as exc:
            self._audit("blank_plan_ui_row_warning", {"error": str(exc)})
        try:
            self.context.sync_config_backends()
        except Exception as exc:
            self._audit("blank_plan_sync_warning", {"error": str(exc)})
        self._audit("blank_plan_started", {"files": [w["name"] for w in written]})
        return {"success": True, "files": written, "source": "blank_plan_defaults"}, 200

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
        except ValueError as exc:
            return {"success": False, "error": str(exc)}, 400
        if content is None:
            return {"success": False, "error": "Plan Data file not found"}, 404
        content_type = "application/json; charset=utf-8" if name.endswith(".json") else ("text/yaml; charset=utf-8" if name.endswith((".yaml", ".yml")) else "text/csv; charset=utf-8")
        return {"success": True, "file": name, "content": content, "content_type": content_type}, 200

    def save_file_payload(self, file_name: str, content: str) -> tuple[JsonDict, int]:
        try:
            name = self.context.normalize_plan_data_file_name(file_name)
            path = self.context.write_plan_data_file(name, str(content))
            self.context.ensure_user_ui_plan_data_rows()
        except ValueError as exc:
            return {"success": False, "error": str(exc)}, 400
        except PermissionError as exc:
            return {"success": False, "error": f"Could not write {Path(file_name).name}. Close the CSV if it is open in Excel, check folder permissions, and try again. Details: {exc}"}, 500
        except Exception as exc:
            return {"success": False, "error": f"Could not save {Path(file_name).name}: {exc}"}, 500
        self._audit("plan_data_file_saved", {"file": name, "bytes": len(str(content)), "path": str(path)})
        sync_result = self.context.sync_config_backends() if name in self.context.client_data_csv_file_set else None
        return {"success": True, "file": name, "path": str(path), "bytes": len(str(content)), "sync": sync_result}, 200
