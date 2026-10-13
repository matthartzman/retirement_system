from __future__ import annotations
"""Local-only configuration backend for v11.

The plan rows are read from the active plan file (``plan.rpx``, ``src/active_plan.py``):
``load_active_config`` returns its sectioned view with the runtime Market Pricing settings
(``app.db``, ``system_config``) and the engine-knob code defaults (``engine_defaults``) merged in.
Nothing mirrors plan data into CSV, JSON or YAML files any more (WP4.5); CSV import/export
is ``csv_exchange`` (WP9). The legacy local database (``init_sqlite``) still holds the
flat datasets' text (``client_files``: holdings, spending, YTD ...), audit events and build
history until WP6/WP8. Compatibility functions keep older route call sites working, but all
identity/client arguments are ignored and resolved to the single local plan.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Tuple, Optional as _Optional

from .engine_defaults import with_engine_defaults
from .system_config import load_system_config
from . import platform_runtime
from .sqlite_util import connect as closing_connect

# PROJECT_ROOT stays the code/package root (read-only assets). Writable data
# (input/, local_state/) hangs off the workspace root, which equals the package
# root on desktop and app-private storage on mobile.
PROJECT_ROOT = platform_runtime.package_root()
_WORKSPACE_ROOT = platform_runtime.workspace_root()
DEFAULT_DB = _WORKSPACE_ROOT / "local_state" / "retirement_system_v10.db"
SettingMap = Dict[str, Dict[str, Dict[str, str]]]

# Runtime settings (app.db) the engine reads from the plan view; they win over plan rows.
SYSTEM_CONFIG_SECTIONS = {"Market Pricing"}
# The backend name the config payloads report: the plan file is a SQLite database.
ACTIVE_BACKEND = "SQLITE"


def setting(data: SettingMap, section: str, subsection: str, label: str, default: str = "") -> str:
    return data.get(section, {}).get(subsection, {}).get(label, default)


def _merge_system_config_sections(data: SettingMap, system_data: SettingMap) -> SettingMap:
    merged: SettingMap = {sec: {sub: dict(vals) for sub, vals in subs.items()} for sec, subs in data.items()}
    for sec in SYSTEM_CONFIG_SECTIONS:
        if sec in system_data:
            merged.setdefault(sec, {})
            for sub, values in system_data[sec].items():
                merged[sec].setdefault(sub, {}).update(values)
    return merged


def resolve_path(path: str | Path | None, default: Path) -> Path:
    if not path:
        return default
    p = Path(path)
    return p if p.is_absolute() else platform_runtime.workspace_root() / p


def init_sqlite(db_path: str | Path = DEFAULT_DB) -> Path:
    p = resolve_path(db_path, DEFAULT_DB)
    p.parent.mkdir(parents=True, exist_ok=True)
    with closing_connect(p) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("""CREATE TABLE IF NOT EXISTS client_files(
            file_name TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            updated_by TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS audit_events(
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'local',
            event TEXT,
            details_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS price_snapshots(
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT DEFAULT 'local',
            symbol TEXT,
            price REAL,
            source TEXT,
            status TEXT DEFAULT 'OK',
            as_of TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        cols = [r[1] for r in con.execute("PRAGMA table_info(price_snapshots)").fetchall()]
        if "workspace_id" not in cols:
            con.execute("ALTER TABLE price_snapshots ADD COLUMN workspace_id TEXT DEFAULT 'local'")
    return p


def load_active_config() -> Tuple[SettingMap, Dict[str, str]]:
    """The active plan's sectioned rows with runtime settings and engine defaults, plus meta.

    Reads ``plan_rows`` of the active plan file (``active_plan.active_plan_data``), overlays the
    runtime Market Pricing settings and fills every engine knob the plan does not hold from
    ``engine_defaults``. ``meta['sqlite_db']`` is still the legacy local database
    (``client_files`` of the flat datasets, KPI and build history); ``meta['plan_db']`` is the
    plan file the build checkpoints and snapshots; ``meta['app_db']`` the settings database.
    """
    from .active_plan import active_plan_data, active_plan_path
    from .app_state import app_store_path
    app_db = app_store_path()
    system_data = load_system_config(app_db)
    # A relative default, joined against the LIVE workspace root on every call.
    _default_sqlite_db_rel = "local_state/retirement_system_v10.db"
    sqlite_db = setting(system_data, "System Configuration", "Runtime", "sqlite_db", _default_sqlite_db_rel) or _default_sqlite_db_rel
    plan_db = active_plan_path()
    data = with_engine_defaults(_merge_system_config_sections(active_plan_data(), system_data))
    return data, {"backend": ACTIVE_BACKEND, "path": str(plan_db), "plan_db": str(plan_db),
                  "app_db": str(app_db), "sqlite_db": str(resolve_path(sqlite_db, DEFAULT_DB)),
                  "workspace_id": "local", "client_id": "local"}


# Compatibility functions for older route call sites. They are local-only and do not create hosted identities.
def token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()

def create_user(*args, **kwargs) -> dict:
    return {"user_id": "local", "email": "local", "role": "advisor", "active": 1}

def create_api_token(*args, **kwargs) -> dict:
    return {"token": "", "token_hash": "", "user_id": "local", "role": "advisor"}

def lookup_api_token(*args, **kwargs) -> _Optional[dict]:
    return None

def set_client_file(file_name: str, content: str, workspace_id: str = "local", client_id: str = "local", updated_by: str = "local", db_path: str | Path = DEFAULT_DB) -> None:
    p = init_sqlite(db_path)
    name = Path(file_name).name
    with closing_connect(p) as con:
        con.execute("INSERT OR REPLACE INTO client_files(file_name, content, updated_by) VALUES(?,?,?)", (name, content, "local"))

def get_client_file(file_name: str, workspace_id: str = "local", client_id: str = "local", db_path: str | Path = DEFAULT_DB) -> _Optional[str]:
    p = resolve_path(db_path, DEFAULT_DB)
    if not p.exists():
        return None
    with closing_connect(p) as con:
        row = con.execute("SELECT content FROM client_files WHERE file_name=?", (Path(file_name).name,)).fetchone()
    return row[0] if row else None

