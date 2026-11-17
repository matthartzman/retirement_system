"""Per-user plan-count cap and disk quota for the multi-user server (P7-O5).

The gateway passes ``RETIREMENT_SYSTEM_MAX_PLANS`` and ``RETIREMENT_SYSTEM_USER_DISK_QUOTA_MB`` to each
worker. Unset, ``0`` or unparsable means unlimited (the desktop app). The guard is checked where a plan
is added (create, duplicate, upload) and at build start; it is a guard, not an accounting system.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from . import plan_registry, platform_runtime

MAX_PLANS_ENV = "RETIREMENT_SYSTEM_MAX_PLANS"
QUOTA_ENV = "RETIREMENT_SYSTEM_USER_DISK_QUOTA_MB"
_TTL = 5.0
_MIB = 1024 * 1024
_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, int]] = {}


class PlanLimitError(ValueError):
    """A plan-count or disk limit was reached; the message is safe to show the user."""


def _int_env(name: str) -> int:
    try:
        return max(0, int(str(os.environ.get(name) or "").strip() or 0))
    except ValueError:
        return 0


def max_plans() -> int:
    return _int_env(MAX_PLANS_ENV)


def quota_mb() -> int:
    return _int_env(QUOTA_ENV)


def invalidate() -> None:
    with _LOCK:
        _CACHE.clear()


def _walk_bytes(root: Path) -> int:
    total = 0
    stack = [root]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def disk_used_bytes() -> int:
    root = platform_runtime.workspace_root()
    key = str(root)
    now = time.monotonic()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit is not None and now - hit[0] < _TTL:
            return hit[1]
    used = _walk_bytes(root)
    with _LOCK:
        _CACHE[key] = (now, used)
    return used


def _counted_plans() -> list[dict]:
    return [p for p in plan_registry.list_plans() if p.get("kind") != "demo"]


def check_can_add_plan(extra_bytes: int = 0) -> None:
    cap = max_plans()
    if cap and len(_counted_plans()) >= cap:
        raise PlanLimitError(f"You have {cap} plans, the limit. Delete one first.")
    quota = quota_mb()
    if quota and disk_used_bytes() + max(0, int(extra_bytes)) > quota * _MIB:
        raise PlanLimitError(f"Your {quota} MB of disk space is full. Delete a plan to free some.")


def check_can_build() -> None:
    quota = quota_mb()
    if quota and disk_used_bytes() > quota * _MIB:
        raise PlanLimitError(f"Your {quota} MB of disk space is full. Delete a plan to free some before building.")


def _orphan_bytes() -> int:
    registered = {os.path.normcase(os.path.abspath(str(p["path"]))) for p in plan_registry.list_plans()}
    folder = platform_runtime.workspace_root() / "saved_plans"
    total = 0
    if folder.is_dir():
        for f in folder.glob("*.rpx"):
            if os.path.normcase(os.path.abspath(str(f))) not in registered and f.is_file():
                total += f.stat().st_size
    return total


def usage() -> dict:
    used = disk_used_bytes()
    return {"max_plans": max_plans(), "plan_count": len(_counted_plans()), "disk_quota_mb": quota_mb(),
            "disk_used_mb": round(used / _MIB, 2), "orphan_mb": round(_orphan_bytes() / _MIB, 3)}
