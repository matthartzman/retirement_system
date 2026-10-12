"""The plan registry and the active plan (design F section 5A, WP8.4).

Every plan is its own file: the user's plan, ``demo.rpx``, any saved case. ``app.db``
``plan_registry`` lists the known plan files (path, name, kind, last opened) and
``active_plan`` names the one in use; :func:`active_plan_file` is what
``active_plan.active_plan_path()`` returns when ``RETIREMENT_SYSTEM_PLAN_DB`` does not override it.
Nothing here copies, swaps or restores a plan file: switching plans only changes the active row.

First run (no active plan): the workspace's ``plan.rpx`` is registered as kind ``user`` and
activated, keeping the id the per-plan output folder was already named after (the ``plan_id``
in the file's meta, else the file stem, see :func:`file_plan_id`), so outputs under
``output/plans/<plan_id>/`` stay reachable.

The demo plan is ``<workspace>/demo.rpx`` with the fixed id ``demo`` (outputs in
``output/plans/demo/``). Opening it records the plan to return to (``DEMO_RETURN_KEY``);
Exit demo switches back to that plan.

The active record is cached per ``app.db`` path and invalidated by every write made here and
by any change of the ``app.db`` / ``-wal`` file stamps (another process writing app.db).
"""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any

from . import app_state, platform_runtime

DEMO_PLAN_ID = "demo"
DEMO_FILE_NAME = "demo.rpx"
DEMO_PLAN_NAME = "Demo plan (Alex & Morgan)"
DEFAULT_PLAN_NAME = "My Plan"
DEMO_RETURN_KEY = "plans.demo_return_to"
PLAN_ID_META_KEY = "plan_id"

_LOCK = threading.RLock()
_CACHE: dict[str, tuple[Any, dict[str, Any]]] = {}


class PlanRegistryError(ValueError):
    """A registry operation that cannot be done (unknown plan, unusable file, active plan)."""


# ------------------------------------------------------------------------------ helpers
def _norm(path: str | Path) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(Path(path).expanduser()))))


def _stamp(path: Path) -> tuple[Any, ...]:
    out: list[Any] = []
    for p in (path, Path(str(path) + "-wal")):
        try:
            st = p.stat()
            out.append((st.st_mtime_ns, st.st_size))
        except OSError:
            out.append(None)
    return tuple(out)


def invalidate() -> None:
    with _LOCK:
        _CACHE.clear()


def workspace_plan_file() -> Path:
    from .active_plan import PLAN_FILE_NAME  # noqa: PLC0415 - active_plan imports this module lazily
    return platform_runtime.workspace_root() / PLAN_FILE_NAME


def demo_plan_file() -> Path:
    return platform_runtime.workspace_root() / DEMO_FILE_NAME


def file_plan_id(path: str | Path) -> str:
    """The id a plan file names its output folder by when it is not registered: the ``plan_id``
    in its meta, else its stem (``plan.rpx`` -> ``plan``), made safe as a folder name."""
    from . import active_plan  # noqa: PLC0415

    p = Path(path)
    stored = None
    if p.is_file():
        try:
            with active_plan.PlanStore.open(p, create=False, readonly=True) as store:
                stored = store.get_meta(PLAN_ID_META_KEY)
        except Exception:  # noqa: BLE001 - not a plan file (yet): fall back to the stem
            stored = None
    for candidate in (stored, p.stem):
        text = re.sub(r"[^A-Za-z0-9_-]+", "-", str(candidate or "")).strip("-_")[:64]
        try:
            return active_plan.validate_plan_id(text)
        except Exception:  # noqa: BLE001
            continue
    return "plan"


def check_plan_file(path: str | Path) -> str | None:
    """Error message when ``path`` is not a usable plan file, else None (an older plan file is
    brought to the current schema, as opening it would)."""
    from .plan_db_replace import PLAN_FILE_TABLES, validate_plan_db, validate_plan_file  # noqa: PLC0415

    p = Path(path)
    if not p.is_file():
        return f"Plan file not found: {p}"
    return validate_plan_db(p, PLAN_FILE_TABLES) or validate_plan_file(p)


def _find(store: Any, path: str | Path) -> dict[str, Any] | None:
    key = _norm(path)
    return next((r for r in store.list_plans() if _norm(r["path"]) == key), None)


def _free_id(store: Any, wanted: str | None) -> str | None:
    if not wanted:
        return None
    try:
        store.get_plan(wanted)
    except LookupError:
        return wanted
    return None  # taken: register_plan picks a fresh id


def _bootstrap(store: Any) -> dict[str, Any]:
    """No active plan: the most recently opened user plan, else the workspace ``plan.rpx``
    (registered as kind ``user`` under its existing output-folder id)."""
    users = [r for r in store.list_plans("user") if r["last_opened"]]
    if users:
        return store.set_active_plan(users[0]["plan_id"])
    plan_file = workspace_plan_file()
    rec = _find(store, plan_file)
    if rec is None:
        rec = store.register_plan(plan_file, DEFAULT_PLAN_NAME, "user",
                                  plan_id=_free_id(store, file_plan_id(plan_file)))
    return store.set_active_plan(rec["plan_id"])


# ------------------------------------------------------------------------- the active plan
def active_record() -> dict[str, Any]:
    """The active plan's registry record (registering the workspace plan on first use)."""
    path = app_state.app_store_path()
    key = str(path)
    with _LOCK:
        hit = _CACHE.get(key)
        if hit is not None and hit[0] == _stamp(path):
            return dict(hit[1])
        with app_state.open_app_store(path) as store:
            rec = store.active_plan() or _bootstrap(store)
        _CACHE[key] = (_stamp(path), dict(rec))
        return dict(rec)


def active_plan_file() -> Path:
    return Path(active_record()["path"])


def active_plan_id() -> str:
    return str(active_record()["plan_id"])


def is_demo_active() -> bool:
    return active_record().get("kind") == "demo"


def plan_id_for_path(path: str | Path) -> str | None:
    """The registry id of the plan file at ``path`` (read only; None when not registered or
    when there is no app.db yet)."""
    store_path = app_state.app_store_path()
    if not store_path.is_file():
        return None
    try:
        with app_state.open_app_store(store_path, readonly=True) as store:
            rec = _find(store, path)
    except Exception:  # noqa: BLE001 - an app.db this code cannot read: not registered
        return None
    return None if rec is None else str(rec["plan_id"])


# --------------------------------------------------------------------------- operations
def list_plans() -> list[dict[str, Any]]:
    """Registered plans (most recently opened first) with ``active`` and ``exists`` flags."""
    active = active_record()
    with app_state.open_app_store() as store:
        plans = store.list_plans()
    return [dict(r, active=r["plan_id"] == active["plan_id"], exists=Path(r["path"]).is_file()) for r in plans]


def get_plan(plan_id: str) -> dict[str, Any]:
    with app_state.open_app_store() as store:
        try:
            return store.get_plan(plan_id)
        except (LookupError, ValueError) as exc:
            raise PlanRegistryError(str(exc)) from exc


def register_plan_file(path: str | Path, *, name: str | None = None, kind: str = "user",
                       plan_id: str | None = None) -> dict[str, Any]:
    """Register a plan file (the existing record when its path is already registered)."""
    p = Path(os.path.abspath(str(Path(path).expanduser())))
    with _LOCK, app_state.open_app_store() as store:
        rec = _find(store, p)
        if rec is None:
            rec = store.register_plan(p, (name or p.stem or DEFAULT_PLAN_NAME).strip() or DEFAULT_PLAN_NAME, kind,
                                      plan_id=_free_id(store, plan_id) if plan_id else None)
        invalidate()
        return rec


def activate(plan_id: str, *, check: bool = True) -> dict[str, Any]:
    """Make a registered plan the active one. Opening the demo from a non-demo plan records
    that plan as the one Exit demo returns to."""
    with _LOCK:
        current = active_record()
        rec = get_plan(plan_id)
        if check:
            error = check_plan_file(rec["path"])
            if error:
                raise PlanRegistryError(error)
        with app_state.open_app_store() as store:
            if rec["kind"] == "demo" and current["kind"] != "demo":
                store.set_setting(DEMO_RETURN_KEY, current["plan_id"])
            rec = store.set_active_plan(plan_id)
        invalidate()
        return rec


def rename(plan_id: str, name: str) -> dict[str, Any]:
    text = str(name or "").strip()
    if not text:
        raise PlanRegistryError("A plan name is required.")
    with _LOCK, app_state.open_app_store() as store:
        try:
            rec = store.update_plan(plan_id, name=text)
        except (LookupError, ValueError) as exc:
            raise PlanRegistryError(str(exc)) from exc
        invalidate()
        return rec


def forget(plan_id: str) -> None:
    """Remove a plan from the registry; its file is untouched. The active plan cannot be forgotten."""
    with _LOCK, app_state.open_app_store() as store:
        try:
            store.remove_plan(plan_id)
        except (LookupError, ValueError) as exc:
            raise PlanRegistryError(str(exc)) from exc
        if store.get_setting(DEMO_RETURN_KEY) == plan_id:
            store.delete_setting(DEMO_RETURN_KEY)
        invalidate()


def demo_return_plan_id() -> str | None:
    """The plan Exit demo goes back to: the one recorded when the demo was opened, else the most
    recently opened non-demo plan (None when there is none)."""
    with app_state.open_app_store() as store:
        wanted = store.get_setting(DEMO_RETURN_KEY)
        plans = store.list_plans()
    ids = {r["plan_id"] for r in plans if r["kind"] != "demo"}
    if wanted in ids:
        return str(wanted)
    rest = [r for r in plans if r["kind"] != "demo"]
    return str(rest[0]["plan_id"]) if rest else None


def same_path(a: str | Path, b: str | Path) -> bool:
    return _norm(a) == _norm(b)
