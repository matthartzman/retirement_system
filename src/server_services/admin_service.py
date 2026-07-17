from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

try:
    from ..server.plan_data_files import SYSTEM_REFERENCE_FILES
except Exception:  # pragma: no cover - direct execution fallback
    from src.server.plan_data_files import SYSTEM_REFERENCE_FILES

ADMIN_PLAN_DATA_FILES = {
    "client_household.csv", "client_income.csv", "client_spending.csv", "client_assets.csv",
    "client_policy.csv", "client_insurance_estate.csv", "client_business.csv", "client_optional_functions.csv",
    "asset_class_optimizer_controls.csv", "client_holdings.csv", "client_liabilities.csv", "target_allocation.csv", "client_data.csv",
}


def read_csv_rows(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.reader(f))


def write_csv_rows(path: Path, rows: Iterable[Iterable[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)
    tmp.replace(path)


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
        if name != "system_config.csv":
            raise ValueError("Unsupported system CSV file")
        return system_config_path
    if kind_norm == "plan":
        if name not in ADMIN_PLAN_DATA_FILES:
            raise ValueError("Unsupported Plan Data CSV file")
        return base_dir / "input" / name
    if kind_norm == "reference":
        return reference_file_path(base_dir, name)
    raise ValueError("Unsupported admin CSV kind")


def csv_file_payload(kind: str, file_name: str, *, base_dir: Path, system_config_path: Path) -> dict[str, Any]:
    p = admin_csv_path(kind, file_name, base_dir=base_dir, system_config_path=system_config_path)
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
    before_rows = read_csv_rows(p) if p.exists() else []
    content = body.get("csv_content") if isinstance(body, dict) else None
    rows = body.get("rows") if isinstance(body, dict) else None
    if content is not None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(content), encoding="utf-8")
    elif isinstance(rows, list):
        write_csv_rows(p, rows)
    else:
        return {"success": False, "error": "csv_content or rows required"}, 400, before_rows, before_rows
    after_rows = read_csv_rows(p) if p.exists() else []
    payload = {"success": True, "kind": str(kind).lower(), "file": p.name, "path": str(p)}
    return payload, 200, before_rows, after_rows


def system_config_payload(system_config_path: Path) -> dict[str, Any]:
    return {
        "success": True,
        "path": str(system_config_path),
        "rows": read_csv_rows(system_config_path),
        "csv_content": system_config_path.read_text(encoding="utf-8-sig") if system_config_path.exists() else "",
    }


def save_system_config(body: dict[str, Any], system_config_path: Path) -> tuple[dict[str, Any], int, list[list[str]], list[list[str]]]:
    before_rows = read_csv_rows(system_config_path) if system_config_path.exists() else []
    content = body.get("csv_content") if isinstance(body, dict) else None
    rows = body.get("rows") if isinstance(body, dict) else None
    if content is not None:
        system_config_path.parent.mkdir(parents=True, exist_ok=True)
        system_config_path.write_text(str(content), encoding="utf-8")
    elif isinstance(rows, list):
        write_csv_rows(system_config_path, rows)
    else:
        return {"success": False, "error": "csv_content or rows required"}, 400, before_rows, before_rows
    after_rows = read_csv_rows(system_config_path) if system_config_path.exists() else []
    return {"success": True, "path": str(system_config_path)}, 200, before_rows, after_rows


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
    before_rows = read_csv_rows(p) if p.exists() else []
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(content or ""), encoding="utf-8")
    after_rows = read_csv_rows(p) if p.exists() else []
    return {"success": True, "file": p.name, "path": str(p), "bytes": len(str(content or ""))}, before_rows, after_rows


def csv_backup_zip(base_dir: Path, system_config_path: Path) -> tuple[dict[str, Any], int]:
    """Zip every plan-data, reference, and system CSV for recovery/backup.

    Discovers files by globbing input/*.csv and reference_data/*.csv (plus
    the top-level system_config.csv) rather than relying on a fixed list, so
    the backup stays exhaustive as new CSVs are added over time.
    """
    import io
    import zipfile
    from datetime import datetime

    entries: list[tuple[str, Path]] = []
    for p in sorted((base_dir / "input").glob("*.csv")):
        entries.append((f"input/{p.name}", p))
    for p in sorted((base_dir / "reference_data").glob("*.csv")):
        entries.append((f"reference_data/{p.name}", p))
    if system_config_path.exists():
        entries.append(("system_config.csv", system_config_path))

    if not entries:
        return {"success": False, "error": "No CSV files were found to back up."}, 404

    buf = io.BytesIO()
    included: list[str] = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, path in entries:
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
        for name in CSV_BACKUP_PLAN_DATA_FILES:
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
    for name in ["pricing_diagnostics.json", "plan_summary.json", "forecast_package.json"]:
        p = output_dir / name
        payload: Any = None
        if p.exists():
            try:
                payload = json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception:
                payload = {"raw": p.read_text(encoding="utf-8-sig", errors="ignore")[:4000]}
        files.append({"name": name, "path": str(p), "available": p.exists(), "bytes": p.stat().st_size if p.exists() else 0, "json": payload})
    return {"success": True, "output_dir": str(output_dir), "files": files}


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
        ("System Configuration", "Runtime", "config_file"): "input/client_data.csv",
        ("System Configuration", "Runtime", "json_config_file"): "input/client_data.json",
        ("System Configuration", "Runtime", "yaml_config_file"): "input/client_data.yaml",
        ("System Configuration", "Runtime", "output_dir"): "output",
    }

