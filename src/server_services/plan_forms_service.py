from __future__ import annotations

from pathlib import Path
from typing import Any


def _store():
    try:
        from ..local_store import import_sectioned_plan, latest_plan_snapshot, latest_sectioned_data
    except Exception:  # pragma: no cover - direct execution fallback
        from src.local_store import import_sectioned_plan, latest_plan_snapshot, latest_sectioned_data
    return latest_sectioned_data, import_sectioned_plan, latest_plan_snapshot


def get_forms_payload(db_path: Path) -> dict[str, Any]:
    latest_sectioned_data, _, _ = _store()
    return {"success": True, "schema": "plan_forms_v1", "backend": "sqlite", "sections": latest_sectioned_data(db_path)}


def save_forms_payload(sections: Any, db_path: Path) -> tuple[dict[str, Any], int]:
    if not isinstance(sections, dict):
        return {"success": False, "error": "sections must be an object"}, 400
    _, import_sectioned_plan, latest_plan_snapshot = _store()
    snapshot_id = import_sectioned_plan(sections, source="db_form", db_path=db_path)
    return {"success": True, "backend": "sqlite", "snapshot_id": snapshot_id, "snapshot": latest_plan_snapshot(db_path)}, 200


def patch_forms_payload(section_path: str, values: Any, db_path: Path) -> tuple[dict[str, Any], int]:
    parts = [p for p in str(section_path).split("/") if p]
    if len(parts) < 2:
        return {"success": False, "error": "section path must include section/subsection"}, 400
    if not isinstance(values, dict):
        return {"success": False, "error": "values must be an object"}, 400
    section, subsection = parts[0], parts[1]
    latest_sectioned_data, import_sectioned_plan, _ = _store()
    data = latest_sectioned_data(db_path)
    data.setdefault(section, {}).setdefault(subsection, {}).update({str(k): str(v) for k, v in values.items()})
    snapshot_id = import_sectioned_plan(data, source="db_form_patch", db_path=db_path)
    return {"success": True, "backend": "sqlite", "snapshot_id": snapshot_id, "section": section, "subsection": subsection, "values": data[section][subsection]}, 200
