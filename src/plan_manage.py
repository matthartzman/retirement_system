"""Create, duplicate, rename and delete plans in one workspace (multi-user multiple-plans design).

Plan ids are server-assigned (uuid4 hex) and name the file (``plans/<id>.rpx``); the display name is
shown only and never reaches a path. Every operation takes a ``plan_id`` and resolves it through the
user's own registry, so an unknown, malformed or foreign id gets the one uniform :data:`NOT_FOUND`
error. A registry path outside the workspace is refused as if the plan did not exist.
"""
from __future__ import annotations

import shutil
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from . import app_state, plan_limits, plan_registry, platform_runtime
from .plan_db_replace import copy_sqlite_file, remove_sidecars

NOT_FOUND = "That plan was not found."
MAX_NAME = 60
SOURCES = ("blank", "demo")
_ERR = plan_registry.PlanRegistryError


# ------------------------------------------------------------------------------ names
def normalize_name(text: Any) -> str:
    """NFC, no control/format characters (bidi overrides included), whitespace collapsed, 1-60 long."""
    raw = unicodedata.normalize("NFC", str(text if text is not None else ""))
    kept = "".join(" " if ch.isspace() else ch for ch in raw if ch.isspace() or unicodedata.category(ch)[0] != "C")
    name = " ".join(kept.split())[:MAX_NAME].strip()
    if not name:
        raise _ERR("A plan name is required.")
    return name


def _taken(exclude: str | None = None) -> set[str]:
    return {str(p["name"]).casefold() for p in plan_registry.list_plans() if p["plan_id"] != exclude}


def unique_name(wanted: str, taken: set[str]) -> str:
    base = wanted
    n = 2
    while wanted.casefold() in taken:
        suffix = f" ({n})"
        wanted = base[: MAX_NAME - len(suffix)] + suffix
        n += 1
    return wanted


# ------------------------------------------------------------------------------ lookup
def _workspace() -> Path:
    return platform_runtime.workspace_root()


def _inside(path: Path) -> bool:
    try:
        return path.resolve().is_relative_to(_workspace().resolve())
    except OSError:
        return False


def _record(plan_id: Any) -> dict[str, Any]:
    """The registry record, or the uniform NOT_FOUND error (bad id, unknown id, path outside the workspace)."""
    try:
        rec = plan_registry.get_plan(plan_id)  # validates the id's shape
    except (_ERR, TypeError, ValueError):
        raise _ERR(NOT_FOUND) from None
    if not _inside(Path(rec["path"])):
        raise _ERR(NOT_FOUND)
    return rec


def plan_file_for(plan_id: Any) -> Path:
    """The file of a registered plan inside the workspace (for download), else NOT_FOUND."""
    path = Path(_record(plan_id)["path"])
    if not path.is_file():
        raise _ERR(NOT_FOUND)
    return path


# ------------------------------------------------------------------------------ create / duplicate
def _plans_dir() -> Path:
    d = _workspace() / "plans"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _register_new(tmp: Path, plan_id: str, name: str) -> dict[str, Any]:
    dest = _plans_dir() / f"{plan_id}.rpx"
    remove_sidecars(tmp)
    tmp.replace(dest)
    try:
        return plan_registry.register_plan_file(dest, name=name, kind="user", plan_id=plan_id)
    except Exception:
        dest.unlink(missing_ok=True)
        raise


def create_plan(name: Any, source: Any) -> dict[str, Any]:
    """A new plan from the shipped demo seed: ``demo`` keeps the sample household, ``blank`` clears it.
    Returns the new registry record (not activated: the caller switches to it)."""
    if source not in SOURCES:
        raise _ERR("source must be blank or demo")
    wanted = normalize_name(name)
    seed = platform_runtime.demo_seed_path()
    if not seed.is_file():
        raise _ERR("The sample plan is missing from this install.")
    with plan_registry._LOCK:
        plan_limits.check_can_add_plan(extra_bytes=seed.stat().st_size)
        plan_id = uuid.uuid4().hex
        tmp = _plans_dir() / f"{plan_id}.rpx.new"
        try:
            shutil.copyfile(seed, tmp)
            if source == "blank":
                from .active_plan import PlanStore  # noqa: PLC0415
                from .blank_plan import blank_plan_rows  # noqa: PLC0415
                from .roth_ui_build_guard import canonicalize_roth_rows  # noqa: PLC0415

                with PlanStore.open(tmp, create=False) as store:
                    with store.transaction():
                        blank_plan_rows(store)
                        canonicalize_roth_rows(store)
            rec = _register_new(tmp, plan_id, unique_name(wanted, _taken()))
        finally:
            tmp.unlink(missing_ok=True)
            remove_sidecars(tmp)
        plan_limits.invalidate()
        return rec


def duplicate_plan(plan_id: Any, name: Any = None) -> dict[str, Any]:
    """An independent copy of a registered plan (SQLite backup API). Does not change the active plan."""
    with plan_registry._LOCK:
        src = _record(plan_id)
        src_path = Path(src["path"])
        if not src_path.is_file():
            raise _ERR(NOT_FOUND)
        wanted = normalize_name(name) if name not in (None, "") else normalize_name(f"{src['name']} (copy)")
        plan_limits.check_can_add_plan(extra_bytes=src_path.stat().st_size)
        new_id = uuid.uuid4().hex
        tmp = _plans_dir() / f"{new_id}.rpx.new"
        try:
            copy_sqlite_file(src_path, tmp)
            rec = _register_new(tmp, new_id, unique_name(wanted, _taken()))
        finally:
            tmp.unlink(missing_ok=True)
            remove_sidecars(tmp)
        plan_limits.invalidate()
        return rec


# ------------------------------------------------------------------------------ rename / delete
def rename_plan(plan_id: Any, name: Any) -> dict[str, Any]:
    with plan_registry._LOCK:
        rec = _record(plan_id)
        wanted = normalize_name(name)
        if wanted.casefold() in _taken(exclude=rec["plan_id"]):
            raise _ERR("You already have a plan with that name.")
        return plan_registry.rename(rec["plan_id"], wanted)


def delete_plan(plan_id: Any, *, confirm_name: Any, build_running: bool = False) -> None:
    """Hard delete: the plan file, its sidecars, its outputs and its registry row. Refused for the
    active plan, the demo, a plan while a build runs, the user's last plan, and a wrong typed name."""
    with plan_registry._LOCK:
        rec = _record(plan_id)
        if rec["kind"] == "demo":
            raise _ERR("The demo plan cannot be deleted.")
        if rec["plan_id"] == plan_registry.active_record()["plan_id"]:
            raise _ERR("This is the active plan. Switch to another plan first.")
        if build_running:
            raise _ERR("A build is running. Wait for it to finish, then delete the plan.")
        if " ".join(str(confirm_name or "").split()).casefold() != str(rec["name"]).casefold():
            raise _ERR("Type the plan's name exactly to confirm.")
        if sum(1 for p in plan_registry.list_plans() if p["kind"] != "demo") <= 1:
            raise _ERR("This is your last plan, so it cannot be deleted.")
        path = Path(rec["path"])
        for suffix in ("", "-wal", "-shm"):
            path.with_name(path.name + suffix).unlink(missing_ok=True)
        outputs = _workspace() / "output" / "plans" / rec["plan_id"]
        if outputs.is_dir() and not outputs.is_symlink() and _inside(outputs):
            shutil.rmtree(outputs, ignore_errors=True)
        plan_registry.forget(rec["plan_id"])
        plan_limits.invalidate()
