from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Iterable

from .. import active_plan
from src.plan_file_io import atomic_write
from ..engine_defaults import ENGINE_DEFAULT_ROWS, ENGINE_SECTIONS
from ..system_config import save_settings_rows, settings_rows

# The System Configuration editor's file name (admin CSV editor, backup zip). There is no such
# file any more (WP8.1): runtime rows are app.db settings, engine rows are active-plan rows.
SYSTEM_CONFIG_FILE_NAME = "system_config.csv"

# ARC-006 / WI-206: provider API keys belong in the local secret store, never
# in the runtime settings (app.db, which also lands in the admin CSV backup
# zip as system_config.csv). Rows with these labels are diverted on save.
SECRET_CONFIG_LABELS = frozenset({"fmp_api_key", "alpha_vantage_api_key"})


def divert_secret_rows(rows: list[list[str]], set_secret_fn=None) -> tuple[list[list[str]], list[str]]:
    """Move non-empty values of SECRET_CONFIG_LABELS rows into the secret store.

    Returns ``(rows, stored_names)`` where the diverted rows have a blank value
    cell. Values are never logged or returned. ``rows`` is not mutated.
    """
    if set_secret_fn is None:
        from ..secrets_store import set_secret as set_secret_fn
    out: list[list[str]] = []
    stored: list[str] = []
    for row in rows:
        row = list(row)
        if len(row) > 3 and str(row[2]).strip() in SECRET_CONFIG_LABELS and str(row[3]).strip():
            name = str(row[2]).strip()
            set_secret_fn(name, str(row[3]).strip())
            row[3] = ""
            if name not in stored:
                stored.append(name)
        out.append(row)
    return out, stored


def read_csv_rows(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.reader(f))


def write_csv_rows(path: Path, rows: Iterable[Iterable[Any]]) -> None:
    with atomic_write(path) as f:
        csv.writer(f, lineterminator="\n").writerows(rows)


def _engine_rows() -> list[list[str]]:
    """The engine knobs as editor rows: the active plan's value, else the code default."""
    data = active_plan.active_plan_data()
    rows = []
    for sec, sub, lbl, default, units, notes in ENGINE_DEFAULT_ROWS:
        value = data.get(sec, {}).get(sub, {}).get(lbl, default)
        rows.append([sec, sub, lbl, value, units, notes])
    return rows


def system_config_rows(app_db: Path | None = None) -> list[list[str]]:
    """Header, the runtime settings (app.db), then the engine knobs (active plan)."""
    return settings_rows(app_db) + _engine_rows()


def _rows_csv(rows: list[list[str]]) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue()


def system_config_payload(system_config_path: Path) -> dict[str, Any]:
    """``system_config_path`` is the app.db holding the runtime settings."""
    rows = system_config_rows(system_config_path)
    return {
        "success": True,
        "path": str(system_config_path),
        "rows": rows,
        "csv_content": _rows_csv(rows),
    }


def _save_engine_rows(rows: list[list[str]]) -> None:
    """Write the engine-knob rows whose value differs from what the plan computes with."""
    defaults = {r[:3]: r for r in ENGINE_DEFAULT_ROWS}
    data = active_plan.active_plan_data()
    changes = []
    for row in rows:
        key = tuple(str(c).strip() for c in row[:3])
        if key not in defaults:
            continue
        new = str(row[3]) if len(row) > 3 else ""
        current = data.get(key[0], {}).get(key[1], {}).get(key[2], defaults[key][3])
        if new != current:
            changes.append((key, new))
    if not changes:
        return
    with active_plan.edit_active_plan() as edit:
        for (sec, sub, lbl), value in changes:
            _d = defaults[(sec, sub, lbl)]
            edit.store.set_value(sec, sub, lbl, value, units=_d[4], notes=_d[5])


def save_system_config(body: dict[str, Any], system_config_path: Path) -> tuple[dict[str, Any], int, list[list[str]], list[list[str]]]:
    """Save editor rows: runtime rows to the app.db settings, engine rows to the active plan."""
    content = body.get("csv_content") if isinstance(body, dict) else None
    rows = body.get("rows") if isinstance(body, dict) else None
    before_rows = system_config_rows(system_config_path)
    if content is None and not isinstance(rows, list):
        return {"success": False, "error": "csv_content or rows required"}, 400, before_rows, before_rows
    if content is not None:
        rows = list(csv.reader(io.StringIO(str(content))))
    rows, stored = divert_secret_rows([list(r) for r in rows if isinstance(r, (list, tuple))])
    engine = [r for r in rows if r and str(r[0]).strip() in ENGINE_SECTIONS]
    runtime = [r for r in rows if not (r and str(r[0]).strip() in ENGINE_SECTIONS)]
    save_settings_rows(runtime, system_config_path)
    _save_engine_rows(engine)
    after_rows = system_config_rows(system_config_path)
    payload: dict[str, Any] = {"success": True, "path": str(system_config_path)}
    if stored:
        payload["secrets_stored"] = stored
    return payload, 200, before_rows, after_rows


def build_csv_backup_zip(base_dir: Path | None = None) -> tuple[bytes, str]:
    """The active plan's CSV set as one zip: the same bytes as ``GET /api/export/plan-set``."""
    from datetime import datetime, timezone

    from .. import csv_exchange
    from ..active_plan import active_plan_store

    with active_plan_store(readonly=True) as store:
        data = csv_exchange.export_plan_set(store)
    return data, f"plan_data_csv_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip"


def diagnostics_payload(output_dir: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    row = active_plan.read_build_results() or {}
    for name, part in (("pricing_diagnostics", "pricing"), ("plan_summary", "summary")):
        doc = row.get(part) or None
        files.append({"name": name, "path": "build_results (plan file)", "available": bool(doc),
                      "bytes": len(json.dumps(doc)) if doc else 0, "json": doc})
    return {"success": True, "output_dir": str(output_dir), "files": files}


# The WebView2 disk-cache/compiled-code directories under the pywebview
# profile (src/desktop_app.py's storage_path). Deliberately excludes "Local
# Storage", "Network" (cookies/site data), "Sessions", and everything else in
# the profile -- this clears rendering/HTTP/bytecode caches only, never the
# app's own persisted state (Build History, workbench nav, etc).
_WEBVIEW_CACHE_DIR_NAMES = (
    "Cache", "Code Cache", "GPUCache", "DawnGraphiteCache", "DawnWebGPUCache", "Shared Dictionary",
)


def clear_webview_disk_cache(base_dir: Path) -> dict[str, Any]:
    """Best-effort clear of the desktop app's WebView2 render/HTTP cache.

    Windows holds these files open for as long as the WebView2 process is
    alive, so a directory can fail to delete while the app window that made
    this very request is still running -- that's reported per-directory
    rather than raising, since a partial clear is still useful and the
    caller (the admin UI) tells the user to fully close and reopen the app
    to finish clearing anything left over.
    """
    import shutil

    profile_dir = base_dir / "local_state" / "webview" / "EBWebView" / "Default"
    if not profile_dir.exists():
        return {"success": True, "cleared": [], "skipped": [], "note": "No WebView2 profile found (server/browser mode, or the desktop app has not run yet)."}
    cleared: list[str] = []
    skipped: list[dict[str, str]] = []
    for name in _WEBVIEW_CACHE_DIR_NAMES:
        d = profile_dir / name
        if not d.exists():
            continue
        try:
            shutil.rmtree(d)
            cleared.append(name)
        except OSError as exc:
            skipped.append({"name": name, "error": str(exc)})
    return {"success": True, "cleared": cleared, "skipped": skipped}


def server_status_payload(*, version: str, cfg: Any, system_config_path: Path) -> dict[str, Any]:
    modes = {
        "LOCAL": {
            "title": "Local desktop",
            "description": "Single-machine desktop use. Binds to 127.0.0.1, uses the local SQLite database as source of truth, and writes generated reports to output/.",
            "host": "127.0.0.1",
            "auth": "No browser login or API token required",
            "command": "tools/launchers/start_ui.bat or python tools/launchers/START_UI.py",
        },
    }
    return {
        "success": True,
        "version": version,
        "running": True,
        "app_mode": "LOCAL",
        "host": getattr(cfg, "dashboard_host", "127.0.0.1"),
        "port": getattr(cfg, "dashboard_port", 5050),
        "public_base_url": "",
        "reverse_proxy_enabled": False,
        "force_https": False,
        "system_config": str(system_config_path),
        "modes": modes,
        "commands": {
            "open_ui_local": "tools/launchers/start_ui.bat or python tools/launchers/START_DESKTOP.py",
            "local_dev": "python tools/run_dev_server.py",
        },
        "note": "Local-only desktop package. Advanced hosting and multi-client administration are not included.",
    }


def local_mode_updates() -> dict[tuple[str, str, str], str]:
    return {
        ("System Configuration", "Runtime", "app_mode"): "LOCAL",
        ("System Configuration", "Dashboard", "host"): "127.0.0.1",
        ("System Configuration", "Runtime", "output_dir"): "output",
    }

