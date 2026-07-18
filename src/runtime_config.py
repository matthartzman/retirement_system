from __future__ import annotations
"""Local runtime configuration from system_config.csv."""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Dict

try:
    from .system_config import DEFAULT_SYSTEM_CONFIG_CSV, load_system_config, system_setting
except ImportError:
    from src.system_config import DEFAULT_SYSTEM_CONFIG_CSV, load_system_config, system_setting

LOCAL = "LOCAL"
LAN = "LAN"  # deprecated: local-only package
SAAS = "SAAS"  # deprecated: local-only package
VALID_APP_MODES = {LOCAL}


def _clean_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    text = str(value).strip().upper()
    if text in {"YES", "Y", "TRUE", "T", "ON", "1"}:
        return True
    if text in {"NO", "N", "FALSE", "F", "OFF", "0"}:
        return False
    return default


def _clean_text(value: object, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _env_text(name: str, current: str) -> str:
    value = os.getenv(name)
    return _clean_text(value, current) if value is not None else current


def _env_bool(name: str, current: bool) -> bool:
    value = os.getenv(name)
    return _clean_bool(value, current) if value is not None else current


def load_client_settings(path: str | Path | None = None) -> Dict[str, Dict[str, Dict[str, str]]]:
    return load_system_config(path)


def setting(data: Dict[str, Dict[str, Dict[str, str]]], section: str, subsection: str, label: str, default: str = "") -> str:
    return data.get(section, {}).get(subsection, {}).get(label, default)


@dataclass(frozen=True)
class RuntimeConfig:
    app_mode: str = LOCAL
    workspace_id: str = "local"
    client_id: str = "local"
    require_api_token: bool = False
    allow_unauthenticated_saas: bool = False
    lan_auth_opt_out_ack: bool = False
    audit_log_enabled: bool = False
    redact_secrets_in_logs: bool = True
    allow_csv_write: bool = True
    allow_downloads: bool = True
    secure_packaging_profile: str = "ADVISOR_SAFE"
    max_build_seconds: int = 1800
    default_role: str = "advisor"
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 5050
    config_backend: str = "CSV"
    config_file: str = "input/client_data.csv"
    json_config_file: str = "input/client_data.json"
    yaml_config_file: str = "input/client_data.yaml"
    sqlite_db: str = "local_state/retirement_system_v10.db"
    clients_file: str = ""
    output_dir: str = ""
    secrets_store: str = "local_state/secrets.db"
    master_key: str = ""
    server_api_token: str = ""
    build_queue_enabled: bool = False
    local_plan_data_dir: str = ""
    server_side_path_roots: str = ""
    reverse_proxy_enabled: bool = False
    force_https: bool = False
    public_base_url: str = ""
    trusted_proxy: str = "127.0.0.1"
    session_cookie_name: str = "rs_v81_token"
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "Lax"
    session_max_age_hours: int = 12
    system_config_csv: str = str(DEFAULT_SYSTEM_CONFIG_CSV)

    @property
    def is_saas(self) -> bool:
        return self.app_mode == SAAS

    @property
    def is_lan(self) -> bool:
        return self.app_mode == LAN


def load_runtime_config(path: str | Path | None = None) -> RuntimeConfig:
    data = load_system_config(path)
    app_mode = _clean_text(system_setting(data, "Runtime", "app_mode", LOCAL), LOCAL).upper()
    if app_mode not in VALID_APP_MODES:
        app_mode = LOCAL
    app_mode = LOCAL

    workspace_id = "local"
    client_id = "local"
    allow_unauthenticated_saas = False
    require_api_token = False
    lan_auth_opt_out_ack = False
    audit_log_enabled = False

    try:
        max_build_seconds = int(float(
            os.getenv("RETIREMENT_SYSTEM_MAX_BUILD_SECONDS")
            or system_setting(data, "Runtime", "max_build_seconds", system_setting(data, "SaaS", "max_build_seconds", "1800"))
        ))
    except Exception:
        max_build_seconds = 1800
    # Keep a floor to avoid accidental instant failures while still allowing users to raise the limit for large exact-scalar builds.
    max_build_seconds = max(30, max_build_seconds)

    default_role = system_setting(data, "Security", "default_role", "advisor").strip().lower() or "advisor"
    if default_role not in {"admin", "advisor", "analyst", "viewer"}:
        default_role = "advisor"

    try:
        dashboard_port = int(float(os.getenv("RETIREMENT_SYSTEM_DASHBOARD_PORT") or system_setting(data, "Dashboard", "port", "5050")))
    except Exception:
        dashboard_port = 5050

    reverse_proxy_enabled = False
    force_https = False
    public_base_url = ""
    trusted_proxy = "127.0.0.1"
    cookie_name = system_setting(data, "Security", "session_cookie_name", "rs_v81_token") or "rs_v81_token"
    secure_raw = str(system_setting(data, "Security", "session_cookie_secure", "AUTO") or "AUTO").strip().upper()
    session_cookie_secure = force_https if secure_raw == "AUTO" else _clean_bool(secure_raw, False)
    samesite = (system_setting(data, "Security", "session_cookie_samesite", "Lax") or "Lax").strip().capitalize()
    if samesite not in {"Lax", "Strict", "None"}:
        samesite = "Lax"
    try:
        session_max_age_hours = int(float(system_setting(data, "Security", "session_max_age_hours", "12")))
    except Exception:
        session_max_age_hours = 12
    session_max_age_hours = max(1, min(168, session_max_age_hours))

    return RuntimeConfig(
        app_mode=app_mode,
        workspace_id=workspace_id,
        client_id=client_id,
        require_api_token=require_api_token,
        allow_unauthenticated_saas=allow_unauthenticated_saas,
        lan_auth_opt_out_ack=lan_auth_opt_out_ack,
        audit_log_enabled=audit_log_enabled,
        redact_secrets_in_logs=True,
        allow_csv_write=True,
        allow_downloads=True,
        secure_packaging_profile="LOCAL_ONLY",
        max_build_seconds=max_build_seconds,
        default_role=default_role,
        dashboard_host=_env_text("RETIREMENT_SYSTEM_DASHBOARD_HOST", system_setting(data, "Dashboard", "host", "127.0.0.1") or "127.0.0.1"),
        dashboard_port=dashboard_port,
        config_backend=(system_setting(data, "Runtime", "config_backend", "CSV") or "CSV").upper(),
        config_file=_env_text("RETIREMENT_SYSTEM_CONFIG_FILE", system_setting(data, "Runtime", "config_file", "input/client_data.csv") or "input/client_data.csv"),
        json_config_file=_env_text("RETIREMENT_SYSTEM_JSON_CONFIG_FILE", system_setting(data, "Runtime", "json_config_file", "input/client_data.json") or "input/client_data.json"),
        yaml_config_file=_env_text("RETIREMENT_SYSTEM_YAML_CONFIG_FILE", system_setting(data, "Runtime", "yaml_config_file", "input/client_data.yaml") or "input/client_data.yaml"),
        sqlite_db=_env_text("RETIREMENT_SYSTEM_SQLITE_DB", system_setting(data, "Runtime", "sqlite_db", "local_state/retirement_system_v10.db") or "local_state/retirement_system_v10.db"),
        clients_file="",
        output_dir=_env_text("RETIREMENT_SYSTEM_OUTPUT_DIR", system_setting(data, "Runtime", "output_dir", "") or ""),
        secrets_store=system_setting(data, "Security", "secrets_store", "local_state/secrets.db") or "local_state/secrets.db",
        master_key=system_setting(data, "Security", "master_key", "") or "",
        server_api_token=system_setting(data, "Security", "server_api_token", "") or "",
        build_queue_enabled=_clean_bool(system_setting(data, "Build Queue", "enabled", "NO"), False),
        local_plan_data_dir=_env_text("RETIREMENT_SYSTEM_PLAN_DATA_DIR", system_setting(data, "Runtime", "local_plan_data_dir", "") or ""),
        server_side_path_roots="",
        reverse_proxy_enabled=reverse_proxy_enabled,
        force_https=force_https,
        public_base_url=public_base_url,
        trusted_proxy=trusted_proxy,
        session_cookie_name=cookie_name,
        session_cookie_secure=session_cookie_secure,
        session_cookie_samesite=samesite,
        session_max_age_hours=session_max_age_hours,
        system_config_csv=str(DEFAULT_SYSTEM_CONFIG_CSV),
    )
