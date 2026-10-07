"""Sectioned Plan Data form payloads over the active plan's rows (WP4.2).

``GET`` returns ``PlanStore.sectioned_data()``; ``POST`` replaces the plan's rows with the
posted sections; ``PATCH`` sets one subsection's values by key (``PlanStore.set_value``).
Until WP4.3 unifies these with the grid's row store, a later CSV write still overwrites
form edits through ``_sync_config_backends`` (as it overwrote the old snapshot).
"""
from __future__ import annotations

from typing import Any

from ..active_plan import active_plan_store

SCHEMA = "plan_forms_v1"
BACKEND = "sqlite"


def get_forms_payload() -> dict[str, Any]:
    with active_plan_store() as store:
        sections = store.sectioned_data()
    return {"success": True, "schema": SCHEMA, "backend": BACKEND, "sections": sections}


def save_forms_payload(sections: Any) -> tuple[dict[str, Any], int]:
    if not isinstance(sections, dict):
        return {"success": False, "error": "sections must be an object"}, 400
    with active_plan_store() as store:
        with store.transaction():
            store.clear_rows()
            for section, subsections in sections.items():
                for subsection, values in (subsections or {}).items():
                    for label, value in (values or {}).items():
                        store.insert_row(str(section), subsection=str(subsection), label=str(label),
                                         value=str(value))
        revision = store.revision()
        data = store.sectioned_data()
    return {"success": True, "backend": BACKEND, "revision": revision, "sections": data}, 200


def patch_forms_payload(section_path: str, values: Any) -> tuple[dict[str, Any], int]:
    parts = [p for p in str(section_path).split("/") if p]
    if len(parts) < 2:
        return {"success": False, "error": "section path must include section/subsection"}, 400
    if not isinstance(values, dict):
        return {"success": False, "error": "values must be an object"}, 400
    section, subsection = parts[0], parts[1]
    with active_plan_store() as store:
        with store.transaction():
            for label, value in values.items():
                store.set_value(section, subsection, str(label), str(value))
        revision = store.revision()
        current = store.sectioned_data().get(section, {}).get(subsection, {})
    return {"success": True, "backend": BACKEND, "revision": revision, "section": section,
            "subsection": subsection, "values": current}, 200
