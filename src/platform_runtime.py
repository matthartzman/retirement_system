from __future__ import annotations
"""Single source of truth for platform roots.

``package_root`` is where the code and read-only reference assets live;
``workspace_root`` is where writable data (``input/``, ``output/``,
``local_state/``, ``saved_plans/``) lives. By default the two are identical.
Setting ``RETIREMENT_SYSTEM_WORKSPACE_ROOT`` (an absolute path) redirects only
the writable tree.

The module imports nothing from the rest of the application so that any module
can consult it without risking an import cycle.
"""

import os
import sys
from pathlib import Path

WORKSPACE_SUBDIRS = ("input", "output", "local_state", "saved_plans")

WORKSPACE_ROOT_ENV = "RETIREMENT_SYSTEM_WORKSPACE_ROOT"
NO_AUTO_OPEN_ENV = "RETIREMENT_SYSTEM_NO_AUTO_OPEN"


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


def workspace_root() -> Path:
    """Directory that holds all writable data.

    Honors ``RETIREMENT_SYSTEM_WORKSPACE_ROOT`` when set to a non-empty value.
    Defaults to :func:`package_root`.
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
    :func:`workspace_root`.
    """
    p = Path(value)
    return p if p.is_absolute() else workspace_root() / p


def ensure_workspace_dirs() -> Path:
    """Create the standard writable subdirectories and return the workspace root."""
    root = workspace_root()
    for name in WORKSPACE_SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def can_open_browser() -> bool:
    """True when the host can open a system web browser (auto-open not suppressed)."""
    return not _env_flag(NO_AUTO_OPEN_ENV)


def capabilities() -> dict:
    """Snapshot of the platform capability flags, for diagnostics/metadata."""
    return {
        "is_frozen": is_frozen(),
        "package_root": str(package_root()),
        "workspace_root": str(workspace_root()),
        "can_open_browser": can_open_browser(),
    }


def _env_flag(name: str) -> bool:
    value = (os.getenv(name) or "").strip().lower()
    return value in {"1", "yes", "y", "true", "t", "on"}
