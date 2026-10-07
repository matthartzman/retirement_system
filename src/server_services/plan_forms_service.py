"""Sectioned Plan Data form payloads over the active plan's rows (WP4.2, unified in WP4.3).

The forms and the grid (``/api/config/rows``) read and write the same ``plan_rows``. ``GET``
returns ``PlanStore.sectioned_data()`` after the CSV-set bridge ran (``refresh``), as the
grid does. ``POST`` replaces the plan's content with the posted sections by key (a posted
key keeps its row and ``row_id``; a key not posted is deleted; a new key is appended to its
section); ``PATCH`` sets one subsection's values by key (``PlanStore.set_value``). Both go
through the server's edit context (``app_core._edit_active_plan``), the same one the grid
uses: one transaction, and every touched key is written back into the plan CSV set, so a
later CSV write or bridge run keeps the form edit instead of overwriting it.

Keys and values follow the CSV path's rules: cells stripped, year-stamped labels stored
under their canonical name, and the rows the CSV path never keeps (``label`` header rows,
retired ``Scenarios / Sell Home`` labels) skipped and reported (``plan_label_rules``);
Roth/IRMAA values canonical (``normalize_roth_csv_value``).
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Callable

from ..active_plan import active_plan_store
from ..csv_exchange import PlanCsvError
from ..plan_label_rules import canonical_label, dropped_at_load
from ..roth_ui_build_guard import normalize_roth_csv_value

SCHEMA = "plan_forms_v1"
BACKEND = "sqlite"

Key = tuple[str, str, str]
EditPlan = Callable[[], AbstractContextManager[Any]]


def _key(section: Any, subsection: Any, label: Any) -> Key | None:
    """The stored key of a posted field, or ``None`` for one the CSV path would not keep."""
    sec, sub, lbl = str(section or "").strip(), str(subsection or "").strip(), canonical_label(label)
    if not sec or sec.startswith("#") or not lbl or dropped_at_load(sec, sub, lbl):
        return None
    return (sec, sub, lbl)


def _value(key: Key, value: Any) -> str:
    return normalize_roth_csv_value(*key, "" if value is None else value).strip()


def get_forms_payload(refresh: Callable[[], Any] | None = None) -> dict[str, Any]:
    if refresh is not None:
        refresh()
    with active_plan_store() as store:
        sections = store.sectioned_data()
    return {"success": True, "schema": SCHEMA, "backend": BACKEND, "sections": sections}


def save_forms_payload(sections: Any, *, edit_plan: EditPlan) -> tuple[dict[str, Any], int]:
    if not isinstance(sections, dict):
        return {"success": False, "error": "sections must be an object"}, 400
    wanted: dict[Key, str] = {}
    skipped: list[dict[str, str]] = []
    for section, subsections in sections.items():
        if not isinstance(subsections, dict):
            return {"success": False, "error": f"section {section!r} must be an object"}, 400
        for subsection, values in subsections.items():
            if not isinstance(values, dict):
                return {"success": False, "error": f"{section}/{subsection} must be an object"}, 400
            for label, value in values.items():
                key = _key(section, subsection, label)
                if key is None:
                    skipped.append({"section": str(section), "subsection": str(subsection), "label": str(label)})
                else:
                    wanted[key] = _value(key, value)
    try:
        with edit_plan() as edit:
            store, kept = edit.store, set()
            for row in store.all_rows():
                key = (row["section"], row["subsection"], row["label"])
                if key not in wanted:
                    store.delete_row(row["row_id"])
                    continue
                kept.add(key)
                if row["value"] != wanted[key]:
                    store.set_row(row["row_id"], value=wanted[key])
            for key, value in wanted.items():
                if key not in kept:
                    store.insert_row(key[0], subsection=key[1], label=key[2], value=value)
    except PlanCsvError as exc:
        return {"success": False, "error": f"Plan Data could not be saved: {exc}"}, 409
    with active_plan_store() as store:
        data = store.sectioned_data()
    return {"success": True, "backend": BACKEND, "revision": edit.revision, "sections": data,
            "skipped": skipped}, 200


def patch_forms_payload(section_path: str, values: Any, *, edit_plan: EditPlan) -> tuple[dict[str, Any], int]:
    parts = [p for p in str(section_path).split("/") if p]
    if len(parts) < 2:
        return {"success": False, "error": "section path must include section/subsection"}, 400
    if not isinstance(values, dict):
        return {"success": False, "error": "values must be an object"}, 400
    section, subsection = parts[0].strip(), parts[1].strip()
    skipped: list[str] = []
    try:
        with edit_plan() as edit:
            for label, value in values.items():
                key = _key(section, subsection, label)
                if key is None:
                    skipped.append(str(label))
                else:
                    edit.store.set_value(*key, _value(key, value))
    except PlanCsvError as exc:
        return {"success": False, "error": f"Plan Data could not be saved: {exc}"}, 409
    with active_plan_store() as store:
        current = store.sectioned_data().get(section, {}).get(subsection, {})
    return {"success": True, "backend": BACKEND, "revision": edit.revision, "section": section,
            "subsection": subsection, "values": current, "skipped": skipped}, 200
