from __future__ import annotations
"""Single source of truth for platform roots and capabilities.

Historically the package hard-coded two assumptions that do not hold on a
mobile (Android) host:

1. Writable data (``input/``, ``output/``, ``local_state/``, ``saved_plans/``)
   lives in the same directory as the code. On Android the code ships read-only
   inside the APK while writable data must live under the app-private
   ``filesDir``.
2. The process can spawn a second Python interpreter (subprocess builds) and
   open a system web browser. Neither is possible inside an Android WebView
   shell.

This module centralizes both concerns. ``package_root`` is where the code and
read-only reference assets live; ``workspace_root`` is where writable data
lives. By default the two are identical, so desktop/server behavior is
unchanged. Setting ``RETIREMENT_SYSTEM_WORKSPACE_ROOT`` (an absolute path)
redirects only the writable tree — this is what an Android host points at its
``filesDir``.

The module imports nothing from the rest of the application so that any module
can consult it without risking an import cycle.
"""

import os
import sys
from pathlib import Path

# Writable subdirectories that hang off the workspace root. Kept here so the
# Android first-run seeding step and the desktop packaging step agree on the
# set of directories a workspace must contain.
WORKSPACE_SUBDIRS = ("input", "output", "local_state", "saved_plans")

WORKSPACE_ROOT_ENV = "RETIREMENT_SYSTEM_WORKSPACE_ROOT"
PLATFORM_ENV = "RETIREMENT_SYSTEM_PLATFORM"
BUILD_MODE_ENV = "RETIREMENT_SYSTEM_BUILD_MODE"
NO_AUTO_OPEN_ENV = "RETIREMENT_SYSTEM_NO_AUTO_OPEN"

_MOBILE_PLATFORMS = frozenset({"android", "ios", "mobile"})


def package_root() -> Path:
    """Directory that holds the code and read-only reference assets.

    Resolves to the project root (the parent of ``src/``) both from source and
    when frozen, matching the existing ``Path(__file__).resolve().parents[1]``
    convention used across the codebase.
    """
    return Path(__file__).resolve().parents[1]


def is_frozen() -> bool:
    """True when running from a PyInstaller (or similar) frozen bundle."""
    return bool(getattr(sys, "frozen", False))


def platform_name() -> str:
    """Lowercased platform identifier from the environment (default 'desktop')."""
    return (os.getenv(PLATFORM_ENV) or "desktop").strip().lower() or "desktop"


def is_mobile() -> bool:
    """True on hosts (Android/iOS) that cannot spawn processes or open a browser."""
    return platform_name() in _MOBILE_PLATFORMS


def workspace_root() -> Path:
    """Directory that holds all writable data.

    Honors ``RETIREMENT_SYSTEM_WORKSPACE_ROOT`` when set to a non-empty value so
    a mobile host can point the writable tree at its app-private storage.
    Defaults to :func:`package_root`, preserving desktop/server behavior.
    """
    override = (os.getenv(WORKSPACE_ROOT_ENV) or "").strip()
    if override:
        return Path(override).expanduser()
    return package_root()


def workspace_subdir(name: str, *, create: bool = False) -> Path:
    """Return ``workspace_root()/name``, optionally creating it."""
    path = workspace_root() / name
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_workspace_path(value: str | Path) -> Path:
    """Resolve a possibly-relative writable path against the workspace root.

    Absolute paths are returned unchanged; relative paths are joined onto
    :func:`workspace_root`. Mirrors the ``p if p.is_absolute() else root / p``
    pattern the path helpers used to inline against a per-module PROJECT_ROOT.
    """
    p = Path(value)
    return p if p.is_absolute() else workspace_root() / p


def ensure_workspace_dirs() -> Path:
    """Create the standard writable subdirectories and return the workspace root."""
    root = workspace_root()
    for name in WORKSPACE_SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def can_subprocess() -> bool:
    """True when the host can spawn a second interpreter for subprocess builds.

    False on mobile hosts, where builds must run in-process on a worker thread.
    """
    return not is_mobile()


def can_open_browser() -> bool:
    """True when the host can open a system web browser.

    False on mobile hosts and whenever auto-open has been explicitly suppressed.
    """
    if is_mobile():
        return False
    return not _env_flag(NO_AUTO_OPEN_ENV)


def build_mode() -> str:
    """Selected workbook-build execution mode: ``'subprocess'`` or ``'inprocess'``.

    Defaults to subprocess (current desktop behavior) whenever the host can
    spawn a process. An explicit ``RETIREMENT_SYSTEM_BUILD_MODE`` overrides the
    capability-derived default.
    """
    override = (os.getenv(BUILD_MODE_ENV) or "").strip().lower()
    if override in {"subprocess", "inprocess"}:
        return override
    return "subprocess" if can_subprocess() else "inprocess"


def capabilities() -> dict:
    """Snapshot of the platform capability flags, for diagnostics/metadata."""
    return {
        "platform": platform_name(),
        "is_mobile": is_mobile(),
        "is_frozen": is_frozen(),
        "package_root": str(package_root()),
        "workspace_root": str(workspace_root()),
        "can_subprocess": can_subprocess(),
        "can_open_browser": can_open_browser(),
        "build_mode": build_mode(),
    }


def _env_flag(name: str) -> bool:
    value = (os.getenv(name) or "").strip().lower()
    return value in {"1", "yes", "y", "true", "t", "on"}
