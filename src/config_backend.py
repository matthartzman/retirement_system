from __future__ import annotations
"""Local-only configuration backends for v10.

The runtime source of truth is the local SQLite plan store. CSV/JSON/YAML are
lossless import/export adapters for portability and transition from older
folders. Compatibility functions keep older route call sites working, but all
identity/client arguments are ignored and resolved to the single local plan.
"""

import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Tuple, Optional as _Optional, List as _List

try:
    from .system_config import discover_system_config_csv, load_system_config, system_setting
    from . import platform_runtime
    from .plan_data_registry import (
        CLIENT_DATA_PART_FILES,
        client_data_part_stems,
        client_data_suffixed_files,
    )
except Exception:
    from src.system_config import discover_system_config_csv, load_system_config, system_setting
    from src import platform_runtime
    from src.plan_data_registry import (
        CLIENT_DATA_PART_FILES,
        client_data_part_stems,
        client_data_suffixed_files,
    )

# PROJECT_ROOT stays the code/package root (read-only assets). Writable data
# (input/, local_state/) hangs off the workspace root, which equals the package
# root on desktop and app-private storage on mobile.
PROJECT_ROOT = platform_runtime.package_root()
_WORKSPACE_ROOT = platform_runtime.workspace_root()
DEFAULT_CSV = _WORKSPACE_ROOT / "input" / "client_data.csv"
DEFAULT_JSON = _WORKSPACE_ROOT / "input" / "client_data.json"
DEFAULT_YAML = _WORKSPACE_ROOT / "input" / "client_data.yaml"
DEFAULT_DB = _WORKSPACE_ROOT / "local_state" / "retirement_system_v10.db"
DEFAULT_CLIENTS_CSV = _WORKSPACE_ROOT / "local_state" / "local_plan_registry.csv"
SettingMap = Dict[str, Dict[str, Dict[str, str]]]

CLIENT_DATA_PART_STEMS = client_data_part_stems()
CLIENT_DATA_JSON_FILES = client_data_suffixed_files(".json")
CLIENT_DATA_YAML_FILES = client_data_suffixed_files(".yaml")

_YEAR_LABEL_PATTERNS = [
    (re.compile(r"^annual_401k_limit_\d{4}$"), "annual_401k_limit_base_year"),
    (re.compile(r"^annual_spending_\d{4}$"), "annual_spending_base_year"),
    (re.compile(r"^balance_\d{1,2}_\d{1,2}_\d{4}$"), "balance_as_of_plan_start"),
    (re.compile(r"^value_\d{1,2}_\d{1,2}_\d{4}$"), "value_as_of_plan_start"),
    (re.compile(r"^family_annual_limit_\d{4}$"), "family_annual_limit_base_year"),
    (re.compile(r"^self_only_annual_limit_\d{4}$"), "self_only_annual_limit_base_year"),
    (re.compile(r"^coverage_\d{4}_family_months$"), "coverage_base_year_family_months"),
    (re.compile(r"^coverage_\d{4}_self_only_months$"), "coverage_base_year_self_only_months"),
    (re.compile(r"^ss_wage_base_\d{4}$"), "ss_wage_base_base_year"),
    (re.compile(r"^irmaa_tier2_mfj_\d{4}$"), "irmaa_tier2_mfj_base_year"),
    (re.compile(r"^ltcg_0pct_top_mfj_\d{4}$"), "ltcg_0pct_top_mfj_base_year"),
    (re.compile(r"^ltcg_15pct_top_mfj_\d{4}$"), "ltcg_15pct_top_mfj_base_year"),
    (re.compile(r"^part_b_premium_\d{4}$"), "part_b_base_premium_monthly"),
    (re.compile(r"^part_d_premium_\d{4}$"), "part_d_base_premium_monthly"),
    (re.compile(r"^annual_premium_\d{4}$"), "annual_premium_base_year"),
]
SYSTEM_CONFIG_SECTIONS = {"Market Pricing", "Plan Settings", "Asset Class Assumptions", "Asset Correlations"}



_RETIRED_SCENARIO_HOME_LABELS = {
    "home_sale_price",
    "home_basis",
    "home_value",
    "house_value",
    "value_as_of_plan_start",
    "current_home_value",
    "current_value",
    "market_value",
}


def _is_retired_scenario_home_key(section: object, subsection: object, label: object) -> bool:
    return _clean(section) == "Scenarios" and _clean(subsection) == "Sell Home" and _clean(label) in _RETIRED_SCENARIO_HOME_LABELS

def _clean(x: object) -> str:
    return str(x or "").strip()


def _normalize_label(label: object) -> str:
    text = _clean(label)
    for pattern, replacement in _YEAR_LABEL_PATTERNS:
        if pattern.match(text):
            return replacement
    return text


def _add(result: SettingMap, section: object, subsection: object, label: object, value: object) -> None:
    sec, sub, lbl = _clean(section), _clean(subsection), _normalize_label(label)
    if not sec or sec.startswith("#") or not lbl or lbl.lower() == "label":
        return
    if _is_retired_scenario_home_key(sec, sub, lbl):
        return
    result.setdefault(sec, {}).setdefault(sub, {})[lbl] = _clean(value)


def setting(data: SettingMap, section: str, subsection: str, label: str, default: str = "") -> str:
    return data.get(section, {}).get(subsection, {}).get(label, default)


def _client_data_csv_paths(path: str | Path) -> list[Path]:
    p = Path(path)
    paths: list[Path] = []
    if p.exists():
        paths.append(p)
    if p.name == "client_data.csv":
        for name in CLIENT_DATA_PART_FILES:
            part = p.parent / name
            if part.exists():
                paths.append(part)
    return paths


def _client_data_structured_paths(path: str | Path, suffix: str) -> list[Path]:
    p = Path(path)
    paths = [p]
    if p.name == f"client_data{suffix}":
        for stem in CLIENT_DATA_PART_STEMS:
            part = p.parent / f"{stem}{suffix}"
            if part.exists():
                paths.append(part)
    return paths


def _load_csv_file(path: str | Path, result: SettingMap | None = None) -> SettingMap:
    result = result if result is not None else {}
    p = Path(path)
    if not p.exists():
        return result
    with p.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            _add(result, row.get("section"), row.get("subsection"), row.get("label"), row.get("value"))
    return result


def load_csv(path: str | Path = DEFAULT_CSV) -> SettingMap:
    result: SettingMap = {}
    p = Path(path)
    for csv_path in _client_data_csv_paths(p):
        _load_csv_file(csv_path, result)
    return result


def _add_mapping(out: SettingMap, obj: object) -> SettingMap:
    if isinstance(obj, dict):
        for sec, subs in obj.items():
            if isinstance(subs, dict):
                for sub, labels in subs.items():
                    if isinstance(labels, dict):
                        for label, value in labels.items():
                            _add(out, sec, sub, label, value)
    return out


def save_json(data: SettingMap, path: str | Path = DEFAULT_JSON) -> Path:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return p


def load_json(path: str | Path = DEFAULT_JSON) -> SettingMap:
    out: SettingMap = {}
    for json_path in _client_data_structured_paths(path, ".json"):
        if json_path.exists():
            _add_mapping(out, json.loads(json_path.read_text(encoding="utf-8")))
    return out


def save_yaml(data: SettingMap, path: str | Path = DEFAULT_YAML) -> Path:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml  # type: ignore
        p.write_text(yaml.safe_dump(data, sort_keys=True, allow_unicode=True), encoding="utf-8")
    except Exception:
        p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return p


def load_yaml(path: str | Path = DEFAULT_YAML) -> SettingMap:
    out: SettingMap = {}
    for yaml_path in _client_data_structured_paths(path, ".yaml"):
        if not yaml_path.exists():
            continue
        try:
            import yaml  # type: ignore
            obj = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except Exception:
            obj = json.loads(yaml_path.read_text(encoding="utf-8"))
        _add_mapping(out, obj)
    return out


def _flatten(data: SettingMap) -> Iterable[Tuple[str, str, str, str]]:
    for s, subs in data.items():
        for ss, labels in subs.items():
            for k, v in labels.items():
                yield s, ss, k, v


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
    with sqlite3.connect(p) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("""CREATE TABLE IF NOT EXISTS settings(
            section TEXT NOT NULL,
            subsection TEXT NOT NULL,
            label TEXT NOT NULL,
            value TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(section, subsection, label)
        )""")
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
        con.execute("""CREATE TABLE IF NOT EXISTS build_jobs(
            job_id TEXT PRIMARY KEY,
            status TEXT,
            request_json TEXT,
            result_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            started_at TEXT,
            finished_at TEXT,
            error TEXT
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


def import_csv_to_sqlite(csv_path: str | Path = DEFAULT_CSV, db_path: str | Path = DEFAULT_DB, workspace_id: str = "local") -> Path:
    data = load_csv(csv_path)
    if not data:
        raise FileNotFoundError(f"No Plan Data CSV rows found at {csv_path} or split Plan Data files beside it.")
    p = init_sqlite(db_path)
    with sqlite3.connect(p) as con:
        con.execute("DELETE FROM settings")
        for s, ss, k, v in _flatten(data):
            con.execute("INSERT OR REPLACE INTO settings(section, subsection, label, value) VALUES(?,?,?,?)", (s, ss, k, v))
    try:
        from .local_store import import_sectioned_plan
        import_sectioned_plan(data, source="csv_import", db_path=p)
    except Exception:
        pass
    return p


def load_sqlite(db_path: str | Path = DEFAULT_DB, workspace_id: str = "local") -> SettingMap:
    p = resolve_path(db_path, DEFAULT_DB)
    if not p.exists():
        return {}
    # v10 canonical: the latest typed plan snapshot is the sole source of truth.
    # The pre-v1.0 key-value `settings` table read fallback was removed with the
    # drop of pre-v1.0 plan support — the snapshot is written on every import, and
    # a missing snapshot falls through to a fresh CSV re-import in
    # load_active_config rather than reading legacy rows.
    try:
        from .local_store import latest_sectioned_data
        return latest_sectioned_data(p) or {}
    except Exception:
        return {}


def load_config(backend: str = "SQLITE", path: str | Path | None = None, workspace_id: str = "local") -> SettingMap:
    b = (backend or "SQLITE").strip().upper()
    if b == "JSON":
        return load_json(resolve_path(path, DEFAULT_JSON))
    if b == "YAML":
        return load_yaml(resolve_path(path, DEFAULT_YAML))
    if b == "CSV":
        return load_csv(resolve_path(path, DEFAULT_CSV))
    return load_sqlite(resolve_path(path, DEFAULT_DB))


def discover_bootstrap_csv() -> Path:
    return discover_system_config_csv()


def load_active_config(cli_backend: str | None = None, cli_path: str | Path | None = None, workspace_id: str | None = None) -> Tuple[SettingMap, Dict[str, str]]:
    bootstrap_csv = discover_bootstrap_csv()
    bootstrap = load_system_config(bootstrap_csv)
    sqlite_db = setting(bootstrap, "System Configuration", "Runtime", "sqlite_db", str(DEFAULT_DB)) or str(DEFAULT_DB)
    backend = (cli_backend or setting(bootstrap, "System Configuration", "Runtime", "config_backend", "SQLITE") or "SQLITE").upper()
    if cli_path:
        config_ref = str(cli_path)
    elif backend == "JSON":
        config_ref = setting(bootstrap, "System Configuration", "Runtime", "json_config_file", "input/client_data.json")
    elif backend == "YAML":
        config_ref = setting(bootstrap, "System Configuration", "Runtime", "yaml_config_file", "input/client_data.yaml")
    elif backend == "CSV":
        config_ref = setting(bootstrap, "System Configuration", "Runtime", "config_file", "input/client_data.csv") or "input/client_data.csv"
    else:
        backend = "SQLITE"
        config_ref = sqlite_db
        db_path = resolve_path(sqlite_db, DEFAULT_DB)
        if not db_path.exists() or not load_sqlite(db_path):
            # One-time migration/bootstrap from previous-format CSV files.
            csv_ref = setting(bootstrap, "System Configuration", "Runtime", "config_file", "input/client_data.csv") or "input/client_data.csv"
            csv_path = resolve_path(csv_ref, DEFAULT_CSV)
            if csv_path.exists():
                import_csv_to_sqlite(csv_path, db_path)
    data = _merge_system_config_sections(load_config(backend, config_ref), bootstrap)
    return data, {"backend": backend, "path": str(resolve_path(config_ref, DEFAULT_DB)), "bootstrap_csv": str(bootstrap_csv), "sqlite_db": str(resolve_path(sqlite_db, DEFAULT_DB)), "workspace_id": "local", "client_id": "local"}


def export_client_json_yaml(csv_anchor: str | Path = DEFAULT_CSV, output_dir: str | Path | None = None) -> dict[str, str]:
    anchor = Path(csv_anchor)
    out_dir = Path(output_dir) if output_dir is not None else anchor.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    data = load_csv(anchor)
    written = {}
    for path in (save_json(data, out_dir / "client_data.json"), save_yaml(data, out_dir / "client_data.yaml")):
        written[path.name] = str(path)
    return written


def export_default_configs() -> None:
    export_client_json_yaml(DEFAULT_CSV, DEFAULT_CSV.parent)
    import_csv_to_sqlite(DEFAULT_CSV, DEFAULT_DB)

# Compatibility functions for older route call sites. They are local-only and do not create hosted identities.
def token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()

def create_user(*args, **kwargs) -> dict:
    return {"user_id": "local", "email": "local", "role": "advisor", "active": 1}

def create_api_token(*args, **kwargs) -> dict:
    return {"token": "", "token_hash": "", "user_id": "local", "role": "advisor"}

def lookup_api_token(*args, **kwargs) -> _Optional[dict]:
    return None

def append_audit_event_sqlite(event: str, details: dict | None = None, workspace_id: str = "local", user_id: str = "local", db_path: str | Path = DEFAULT_DB) -> None:
    p = init_sqlite(db_path)
    with sqlite3.connect(p) as con:
        con.execute("INSERT INTO audit_events(user_id,event,details_json) VALUES(?,?,?)", ("local", event, json.dumps(details or {}, sort_keys=True, default=str)))

def load_clients_csv(*args, **kwargs) -> list[dict]:
    return [{"client_id": "local", "display_name": "Local Plan", "active": 1, "config_backend": "SQLITE", "config_ref": str(DEFAULT_DB)}]

def upsert_client(row: dict, db_path: str | Path = DEFAULT_DB) -> dict:
    return {"client_id": "local", "display_name": row.get("display_name", "Local Plan"), "active": 1, "config_backend": "SQLITE", "config_ref": str(DEFAULT_DB)}

def sync_clients_csv_to_sqlite(*args, **kwargs) -> int:
    return 1

def list_clients(*args, **kwargs) -> list[dict]:
    return load_clients_csv()

def get_client(client_id: str = "local", db_path: str | Path = DEFAULT_DB) -> _Optional[dict]:
    return load_clients_csv()[0]

def set_client_file(file_name: str, content: str, workspace_id: str = "local", client_id: str = "local", updated_by: str = "local", db_path: str | Path = DEFAULT_DB) -> None:
    p = init_sqlite(db_path)
    name = Path(file_name).name
    with sqlite3.connect(p) as con:
        con.execute("INSERT OR REPLACE INTO client_files(file_name, content, updated_by) VALUES(?,?,?)", (name, content, "local"))

def get_client_file(file_name: str, workspace_id: str = "local", client_id: str = "local", db_path: str | Path = DEFAULT_DB) -> _Optional[str]:
    p = resolve_path(db_path, DEFAULT_DB)
    if not p.exists():
        return None
    with sqlite3.connect(p) as con:
        row = con.execute("SELECT content FROM client_files WHERE file_name=?", (Path(file_name).name,)).fetchone()
    return row[0] if row else None

def materialize_workspace_files(workspace_id: str = "local", client_id: str = "local", db_path: str | Path = DEFAULT_DB, file_names: _Optional[_List[str]] = None, overwrite_existing: bool = False) -> Path:
    out_dir = platform_runtime.workspace_root() / "input"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in file_names or ["client_holdings.csv", "target_allocation.csv", "manual_pricing_validation.csv", "client_spending_taxonomy.csv", "client_spending_aliases.csv", "client_spending_budget.csv", "client_spending_budget_lines.csv"]:
        dest = out_dir / Path(name).name
        if dest.exists() and not overwrite_existing:
            continue
        content = get_client_file(name, db_path=db_path)
        if content is not None:
            dest.write_text(content, encoding="utf-8")
    return out_dir
