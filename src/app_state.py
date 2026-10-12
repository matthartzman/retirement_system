"""Where this install's ``app.db`` lives, and the one way to open it (WP8.1).

``app.db`` (``AppStore``) holds per-install state that survives plan swaps: the runtime
settings first (``system_config``), the registry and preferences later in WP8. No config file
locates it: ``$RETIREMENT_SYSTEM_APP_DB`` (``APP_DB_ENV``; relative is taken against the
workspace root) or ``<workspace>/local_state/app.db``. The server passes the resolved path to
its build and tool subprocesses (``app_db_env``) so they read the same settings.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from . import platform_runtime
from .stores import AppStore

APP_DB_ENV = "RETIREMENT_SYSTEM_APP_DB"
APP_DB_FILE_NAME = "app.db"


def app_store_path() -> Path:
    """``$RETIREMENT_SYSTEM_APP_DB`` or ``<workspace>/local_state/app.db`` (resolved per call)."""
    raw = str(os.environ.get(APP_DB_ENV, "") or "").strip()
    root = platform_runtime.workspace_root()
    if raw:
        p = Path(raw).expanduser()
        return p if p.is_absolute() else root / p
    return root / "local_state" / APP_DB_FILE_NAME


def open_app_store(path: str | Path | None = None, *, readonly: bool = False) -> AppStore:
    """Open ``app.db`` (created when missing unless ``readonly``). Close it after use."""
    p = Path(path) if path is not None else app_store_path()
    if not readonly:
        p.parent.mkdir(parents=True, exist_ok=True)
    return AppStore.open(p, create=not readonly, readonly=readonly)


def app_store_path_for(base_dir: str | Path | None) -> Path:
    """The ``app.db`` for a caller that is handed a workspace folder.

    The install's own workspace (or no folder) gets ``app_store_path()``, so the env override
    applies; any other folder (a test's temp dir) gets its own ``<folder>/local_state/app.db``.
    """
    if base_dir is None:
        return app_store_path()
    base = Path(base_dir)
    try:
        if base.resolve() == platform_runtime.workspace_root().resolve():
            return app_store_path()
    except OSError:
        pass
    return base / "local_state" / APP_DB_FILE_NAME


def app_db_env(env: dict[str, Any]) -> dict[str, Any]:
    """Point a subprocess environment at this process's ``app.db``; returns ``env``."""
    env[APP_DB_ENV] = str(app_store_path())
    return env
