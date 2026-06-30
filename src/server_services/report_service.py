from __future__ import annotations

"""Feature-owned report/download/history service helpers.

This module keeps report-result behavior independent from the HTTP runtime.  It
knows how to locate build artifacts, read the Results Explorer workbook model,
and manage the small local build-history file.  Route modules remain responsible
for permissions, request parsing, JSON/file response serialization, and audits.
"""

import json
from pathlib import Path
from typing import Any

try:
    from ..report_package import REPORT_PACKAGE_FILENAME, REPORT_PACKAGE_SCHEMA, read_report_package
except Exception:  # pragma: no cover - direct execution fallback
    from src.report_package import REPORT_PACKAGE_FILENAME, REPORT_PACKAGE_SCHEMA, read_report_package


def resolve_output_file(output_dir: Path, name: str, fallback_output_dir: Path | None = None) -> Path:
    """Return the preferred existing output file path, or the primary path.

    The returned path may not exist; callers can use this for consistent error
    messages without duplicating local/non-local fallback rules in route files.
    """
    primary = output_dir / name
    if primary.exists() or fallback_output_dir is None:
        return primary
    fallback = fallback_output_dir / name
    return fallback if fallback.exists() else primary


def downloadable_artifact(name: str, output_dir: Path, fallback_output_dir: Path | None = None) -> tuple[dict[str, Any], int]:
    path = resolve_output_file(output_dir, name, fallback_output_dir)
    if path.exists() and path.is_file():
        return {"success": True, "path": str(path), "name": name}, 200
    return {"success": False, "error": f"{name} not found; run build first", "name": name, "path": str(path)}, 404


def detailed_results_payload(
    *,
    output_dir: Path,
    fallback_output_dir: Path | None = None,
    mode: str = "full",
    sheet_name: str = "",
) -> tuple[dict[str, Any], int]:
    try:
        try:
            from ..detailed_results import workbook_detailed_results, workbook_detailed_index, workbook_detailed_sheet
        except Exception:  # pragma: no cover - direct execution fallback
            from src.detailed_results import workbook_detailed_results, workbook_detailed_index, workbook_detailed_sheet

        workbook_path = resolve_output_file(output_dir, "retirement_plan.xlsx", fallback_output_dir)
        if mode == "index":
            payload = workbook_detailed_index(workbook_path)
        elif mode == "sheet":
            payload = workbook_detailed_sheet(workbook_path, sheet_name or "")
        else:
            payload = workbook_detailed_results(workbook_path)
    except Exception as exc:
        return {"success": False, "error": str(exc), "sheets": [], "categories": []}, 500
    return payload, 200 if payload.get("success") else 404


def report_package_payload(output_dir: Path, fallback_output_dir: Path | None = None) -> tuple[dict[str, Any], int]:
    path = resolve_output_file(output_dir, REPORT_PACKAGE_FILENAME, fallback_output_dir)
    package = read_report_package(path)
    if package:
        return package, 200
    return {
        "success": False,
        "schema": REPORT_PACKAGE_SCHEMA,
        "error": f"{REPORT_PACKAGE_FILENAME} not found; run build first",
        "path": str(path),
    }, 404


def history_path(output_dir: Path) -> Path:
    return output_dir / "run_history.json"


def read_history_payload(output_dir: Path) -> tuple[list[Any], int]:
    p = history_path(output_dir)
    if not p.exists():
        return [], 200
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else [], 200
    except Exception:
        return [], 200


def append_history_payload(output_dir: Path, entry: Any, *, limit: int = 50) -> tuple[dict[str, Any], int]:
    try:
        p = history_path(output_dir)
        current, _ = read_history_payload(output_dir)
        current.append(entry if isinstance(entry, dict) else {"value": entry})
        current = current[-max(1, int(limit)):]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(current, indent=2), encoding="utf-8")
        return {"success": True, "count": len(current), "path": str(p)}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def local_output_file_payload(output_dir: Path, filename: str) -> tuple[dict[str, Any], int]:
    """Validate that a requested file is inside output_dir and exists."""
    root = output_dir.resolve()
    requested = (root / filename).resolve()
    try:
        requested.relative_to(root)
    except Exception:
        return {"success": False, "error": "Only local output files may be served", "filename": filename}, 403
    if not requested.exists() or not requested.is_file():
        return {"success": False, "error": "File not found", "filename": filename, "path": str(requested)}, 404
    return {"success": True, "path": str(requested), "filename": filename, "root": str(root)}, 200
