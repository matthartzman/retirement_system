"""Process-wide accessor for the shipped ``reference.db`` (WP3.1).

``reference()`` returns one shared, read-only ``RefData``: opened lazily on first
use, its content hash verified once, then reused by every thread (``RefData``
serializes queries under its own lock). Path resolution, first match wins:

1. ``set_reference_for_tests(path)`` -- test hook; ``None`` clears it.
2. ``$RETIREMENT_REFERENCE_DB`` -- explicit override (developer runs, tooling).
3. ``<package_root>/src/reference/reference.db`` -- the committed, shipped file.
   ``platform_runtime.package_root()`` resolves to the bundle root when frozen,
   and the PyInstaller spec bundles all of ``src/`` as data, so the same relative
   path works from source and from the frozen app.

A missing or tampered file raises ``RefDataError``; there is no fallback to the
old ``reference_data/`` files (one source of truth, no coexistence).
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

from .. import platform_runtime
from .ref_data import RefData

REFERENCE_DB_ENV = "RETIREMENT_REFERENCE_DB"
SHIPPED_RELATIVE_PATH = Path("src") / "reference" / "reference.db"

_lock = threading.Lock()
_handle: RefData | None = None
_test_path: Path | None = None


def shipped_reference_path() -> Path:
    """Where the committed / bundled reference.db lives."""
    return platform_runtime.package_root() / SHIPPED_RELATIVE_PATH


def reference_path() -> Path:
    """The path ``reference()`` opens (test hook, then env override, then shipped file)."""
    if _test_path is not None:
        return _test_path
    override = (os.getenv(REFERENCE_DB_ENV) or "").strip()
    return Path(override) if override else shipped_reference_path()


def reference() -> RefData:
    """The shared, hash-verified reference handle (opened on first call)."""
    global _handle
    handle = _handle
    if handle is not None and not handle.closed:
        return handle
    with _lock:
        if _handle is None or _handle.closed:
            _handle = RefData.open(reference_path(), verify=True)
        return _handle


def set_reference_for_tests(path: str | Path | None) -> None:
    """Point ``reference()`` at ``path`` (``None`` restores normal resolution).

    Closes the current shared handle so the next ``reference()`` call reopens
    (and re-verifies) from the new location.
    """
    global _handle, _test_path
    with _lock:
        if _handle is not None:
            _handle.close()
        _handle = None
        _test_path = None if path is None else Path(path)
