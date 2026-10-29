"""Recent Projections view: the build's projection_tables.json for the active plan.

The file sits beside the plan's latest retirement_plan.xlsx; the plan file's latest build snapshot
names that workbook, so a workspace with several plans shows the active one's. Parsed once per
file mtime. Missing, unreadable or an unknown schema all read as ``{"missing": True}`` (the page
shows its rebuild prompt).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from src.active_plan import plan_path_for_workspace, plan_state, read_build_results

FILE_NAME = "projection_tables.json"
SCHEMA = "projection_tables/1"
_WORKBOOK = "retirement_plan.xlsx"

_cache: dict[Path, tuple[int, dict]] = {}
_lock = threading.Lock()


def locate(retirement_system_dir: Path, results: dict | None = None) -> Path | None:
    """``projection_tables.json`` beside the active plan's latest workbook, or None."""
    if results is None:
        results = read_build_results(path=plan_path_for_workspace(retirement_system_dir)) or {}
    artifacts = (results.get("snapshot") or {}).get("artifacts") or []
    workbook = next((a.get("path") for a in artifacts if a.get("file") == _WORKBOOK and a.get("path")), None)
    if not workbook:
        return None
    path = Path(workbook).parent / FILE_NAME
    return path if path.is_file() else None


def _read(path: Path) -> dict | None:
    mtime = path.stat().st_mtime_ns
    with _lock:
        hit = _cache.get(path)
        if hit and hit[0] == mtime:
            return hit[1]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    with _lock:
        _cache[path] = (mtime, doc)
    return doc


def _plan_changed(plan: Path, results: dict) -> bool:
    """The plan's inputs differ from what the latest build read. (Not the plan file's mtime: the
    build itself writes its results into the plan file after the workbook.)"""
    recorded = results.get("plan_state") or ""
    if not recorded:
        return False
    try:
        return plan_state(plan) != recorded
    except Exception:  # noqa: BLE001 - an unreadable plan can't be compared; don't cry wolf
        return False


def load(retirement_system_dir: Path) -> dict[str, Any]:
    plan = plan_path_for_workspace(retirement_system_dir)
    results = read_build_results(path=plan) or {}
    path = locate(retirement_system_dir, results)
    doc = _read(path) if path else None
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        return {"missing": True}
    years = [r.get("year") for r in ((doc.get("tables") or {}).get("net_worth") or {}).get("rows") or []]
    return {**doc, "plan_changed": _plan_changed(plan, results),
            "plan_first_year": min(years) if years else None, "plan_last_year": max(years) if years else None}
