from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Iterable

from .. import active_plan
from ..plan_data_registry import SYSTEM_REFERENCE_FILES
from src.plan_file_io import atomic_write, plan_file_lock, write_text_atomic
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


def normalize_reference_file_name(file_name: str) -> str:
    name = Path(str(file_name or "")).name
    if name not in set(SYSTEM_REFERENCE_FILES):
        raise ValueError("Unsupported system/reference file")
    return name


def reference_file_path(base_dir: Path, file_name: str) -> Path:
    return base_dir / "reference_data" / normalize_reference_file_name(file_name)


def admin_csv_path(kind: str, file_name: str, *, base_dir: Path, system_config_path: Path) -> Path:
    kind_norm = str(kind or "").strip().lower()
    name = Path(str(file_name or "")).name
    if kind_norm == "system":
        if name != SYSTEM_CONFIG_FILE_NAME:
            raise ValueError("Unsupported system CSV file")
        return system_config_path  # the app.db holding the runtime settings
    # No "plan" kind: the plan data is the plan file's rows (WP4.5), edited in the app.
    if kind_norm == "reference":
        return reference_file_path(base_dir, name)
    raise ValueError("Unsupported admin CSV kind")


def csv_file_payload(kind: str, file_name: str, *, base_dir: Path, system_config_path: Path) -> dict[str, Any]:
    p = admin_csv_path(kind, file_name, base_dir=base_dir, system_config_path=system_config_path)
    if str(kind or "").strip().lower() == "system":
        payload = system_config_payload(system_config_path)
        return {**payload, "kind": "system", "file": SYSTEM_CONFIG_FILE_NAME,
                "bytes": len(payload["csv_content"].encode("utf-8"))}
    text = p.read_text(encoding="utf-8-sig") if p.exists() else ""
    return {
        "success": True,
        "kind": str(kind).lower(),
        "file": p.name,
        "path": str(p),
        "rows": read_csv_rows(p),
        "csv_content": text,
        "bytes": p.stat().st_size if p.exists() else 0,
    }


def save_csv_file(kind: str, file_name: str, body: dict[str, Any], *, base_dir: Path, system_config_path: Path) -> tuple[dict[str, Any], int, list[list[str]], list[list[str]]]:
    p = admin_csv_path(kind, file_name, base_dir=base_dir, system_config_path=system_config_path)
    if str(kind or "").strip().lower() == "system":
        payload, status, before_rows, after_rows = save_system_config(body, system_config_path)
        if status == 200:
            payload = {**payload, "kind": "system", "file": SYSTEM_CONFIG_FILE_NAME}
        return payload, status, before_rows, after_rows
    with plan_file_lock(p):
        before_rows = read_csv_rows(p) if p.exists() else []
        content = body.get("csv_content") if isinstance(body, dict) else None
        rows = body.get("rows") if isinstance(body, dict) else None
        stored: list[str] = []
        if content is not None:
            write_text_atomic(p, str(content))
        elif isinstance(rows, list):
            write_csv_rows(p, rows)
        else:
            return {"success": False, "error": "csv_content or rows required"}, 400, before_rows, before_rows
        after_rows = read_csv_rows(p) if p.exists() else []
    payload = {"success": True, "kind": str(kind).lower(), "file": p.name, "path": str(p)}
    if stored:
        payload["secrets_stored"] = stored
    return payload, 200, before_rows, after_rows


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


def reference_files_payload(base_dir: Path) -> dict[str, Any]:
    out: list[dict[str, Any]] = []
    for name in SYSTEM_REFERENCE_FILES:
        p = reference_file_path(base_dir, name)
        out.append({"name": name, "path": str(p), "available": p.exists(), "bytes": p.stat().st_size if p.exists() else 0})
    return {"success": True, "files": out}


def read_reference_file(base_dir: Path, file_name: str) -> tuple[str | dict[str, Any], int, dict[str, str]]:
    p = reference_file_path(base_dir, file_name)
    if not p.exists():
        return {"success": False, "error": "Reference file not found"}, 404, {}
    return p.read_text(encoding="utf-8-sig"), 200, {"Content-Type": "text/csv; charset=utf-8"}


def save_reference_file(base_dir: Path, file_name: str, content: str) -> tuple[dict[str, Any], list[list[str]], list[list[str]]]:
    p = reference_file_path(base_dir, file_name)
    with plan_file_lock(p):
        before_rows = read_csv_rows(p) if p.exists() else []
        write_text_atomic(p, str(content or ""))
        after_rows = read_csv_rows(p) if p.exists() else []
    return {"success": True, "file": p.name, "path": str(p), "bytes": len(str(content or ""))}, before_rows, after_rows


def csv_backup_zip(base_dir: Path, system_config_path: Path) -> tuple[dict[str, Any], int]:
    """Zip every plan-data, reference, and system CSV for recovery/backup.

    Discovers files by globbing input/*.csv and reference_data/*.csv (plus
    the runtime settings and engine knobs as system_config.csv) rather than relying on a fixed list, so
    the backup stays exhaustive as new CSVs are added over time.
    """
    import io
    import zipfile
    from datetime import datetime

    entries: list[tuple[str, Path | str]] = []
    for p in sorted((base_dir / "input").glob("*.csv")):
        entries.append((f"input/{p.name}", p))
    for p in sorted((base_dir / "reference_data").glob("*.csv")):
        entries.append((f"reference_data/{p.name}", p))
    entries.append((SYSTEM_CONFIG_FILE_NAME, _rows_csv(system_config_rows(system_config_path))))

    if not entries:
        return {"success": False, "error": "No CSV files were found to back up."}, 404

    buf = io.BytesIO()
    included: list[str] = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, path in entries:
            if isinstance(path, str):
                zf.writestr(arcname, path)
            else:
                zf.write(path, arcname)
            included.append(arcname)
        manifest = (
            f"CSV backup generated {datetime.now().isoformat(timespec='seconds')}\n"
            f"{len(included)} file(s) included:\n" + "\n".join(included) + "\n"
        )
        zf.writestr("BACKUP_MANIFEST.txt", manifest)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return {
        "success": True,
        "filename": f"csv_backup_{timestamp}.zip",
        "data": buf.getvalue(),
        "included": included,
    }, 200


CSV_BACKUP_PLAN_DATA_FILES = ["client_holdings.csv", "ytd_transactions.csv", "target_allocation.csv"]


def build_csv_backup_zip(base_dir: Path) -> tuple[bytes, str]:
    """Bundle holdings, transactions, target allocation, and reference-data CSVs for backup/external review."""
    import io
    import zipfile
    from datetime import datetime, timezone

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        from ..plan_datasets import DATASET_BY_FILE, active_dataset_text

        for name in CSV_BACKUP_PLAN_DATA_FILES:
            if name in DATASET_BY_FILE:  # a table of the active plan file
                text = active_dataset_text(DATASET_BY_FILE[name])
                if text is not None:
                    zf.writestr(name, text)
                continue
            p = base_dir / "input" / name
            if p.exists():
                zf.write(p, arcname=name)
        for name in SYSTEM_REFERENCE_FILES:
            p = reference_file_path(base_dir, name)
            if p.exists():
                zf.write(p, arcname=f"reference_data/{name}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return buf.getvalue(), f"plan_data_csv_backup_{stamp}.zip"


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

