from __future__ import annotations
"""Version v10 local-only stdlib dashboard and API.

The packaged server is for single-machine desktop use: it uses the local SQLite plan store as source of truth, materializes import/export adapters as needed, and writes generated files to output/, and does not expose public-hosting, client-registry, or browser-login modes.
"""

import csv
import html as html_lib
import hashlib
import hmac
import io
import json
import os
import re
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from collections import defaultdict, deque
from pathlib import Path

try:
    from ..http_runtime.wsgi_facade import (
        Flask,
        HTTPException,
        ProxyFix,
        Response,
        g,
        jsonify,
        make_response,
        redirect,
        request,
        send_file,
        send_from_directory,
        url_for,
    )
except Exception:  # direct file loading fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.http_runtime.wsgi_facade import (
        Flask,
        HTTPException,
        ProxyFix,
        Response,
        g,
        jsonify,
        make_response,
        redirect,
        request,
        send_file,
        send_from_directory,
        url_for,
    )

try:
    from ..schema_registry import load_schema as _load_schema_registry, validate_value as _schema_validate_value
    from ..runtime_config import load_runtime_config
    from ..system_config import load_system_config, setting as system_config_setting
    from ..security import append_audit_event, constant_time_token_ok, extract_bearer_or_header, get_server_token, redact_text, sha256_fingerprint
    from ..permissions import UserContext, require as require_permission, user_from_headers
    from ..secrets_store import encryption_status, require_secure_master_key, set_secret
    from ..workspace_context import sanitize_id, workspace_file, workspace_output_dir
    from ..roth_ui_build_guard import canonicalize_roth_csv_content, normalize_roth_csv_value
    from .plan_data_files import (
        CLIENT_DATA_CSV_FILES,
        CLIENT_DATA_CSV_FILE_SET,
        CLIENT_DATA_DERIVED_FILES,
        CLIENT_DATA_DERIVED_FILE_SET,
        CLIENT_DATA_PART_FILES,
        PLAN_DATA_CSV_FILES,
        PLAN_DATA_CSV_FILE_SET,
        PLAN_DATA_DERIVED_FILES,
        PLAN_DATA_FILES,
        PLAN_DATA_FILE_SET,
        SYSTEM_REFERENCE_FILES,
        UI_NAMES,
        YTD_PLAN_DATA_FILES,
    )
    from ..config_backend import (
        DEFAULT_DB,
        append_audit_event_sqlite,
        get_client,
        get_client_file,
        init_sqlite,
        load_active_config,
        load_csv,
        export_client_json_yaml,
        import_csv_to_sqlite,
        lookup_api_token,
        materialize_workspace_files,
        set_client_file,
        sync_clients_csv_to_sqlite,
        upsert_client,
    )
except Exception:  # direct execution fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.schema_registry import load_schema as _load_schema_registry, validate_value as _schema_validate_value
    from src.runtime_config import load_runtime_config
    from src.system_config import load_system_config, setting as system_config_setting
    from src.security import append_audit_event, constant_time_token_ok, extract_bearer_or_header, get_server_token, redact_text, sha256_fingerprint
    from src.permissions import UserContext, require as require_permission, user_from_headers
    from src.secrets_store import encryption_status, require_secure_master_key, set_secret
    from src.workspace_context import sanitize_id, workspace_file, workspace_output_dir
    from src.roth_ui_build_guard import canonicalize_roth_csv_content, normalize_roth_csv_value
    from src.server.plan_data_files import (
        CLIENT_DATA_CSV_FILES,
        CLIENT_DATA_CSV_FILE_SET,
        CLIENT_DATA_DERIVED_FILES,
        CLIENT_DATA_DERIVED_FILE_SET,
        CLIENT_DATA_PART_FILES,
        PLAN_DATA_CSV_FILES,
        PLAN_DATA_CSV_FILE_SET,
        PLAN_DATA_DERIVED_FILES,
        PLAN_DATA_FILES,
        PLAN_DATA_FILE_SET,
        SYSTEM_REFERENCE_FILES,
        UI_NAMES,
        YTD_PLAN_DATA_FILES,
    )
    from src.config_backend import (
        DEFAULT_DB,
        append_audit_event_sqlite,
        get_client,
        get_client_file,
        init_sqlite,
        load_active_config,
        load_csv,
        export_client_json_yaml,
        import_csv_to_sqlite,
        lookup_api_token,
        materialize_workspace_files,
        set_client_file,
        sync_clients_csv_to_sqlite,
        upsert_client,
    )

# Persistent multi-user build queue removed from local-only package; /api/build/start uses in-memory progress only.

try:
    from .. import allocation_policy as allocation_policy_mod
except Exception:
    from src import allocation_policy as allocation_policy_mod

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CSV_PATH = BASE_DIR / "input" / "client_data.csv"
SCHEMA_PATH = BASE_DIR / "reference_data" / "schema.csv"
BUILD_SCRIPT = BASE_DIR / "tools" / "build_workbook.py"
app = Flask(__name__, static_folder=str(BASE_DIR))
RUNTIME_CONFIG = load_runtime_config()
_LOGIN_ATTEMPTS = defaultdict(deque)
_LOGIN_WINDOW_SECONDS = 15 * 60
_LOGIN_MAX_FAILURES = 10
if getattr(RUNTIME_CONFIG, "reverse_proxy_enabled", False):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)



# UI regression markers retained for allocation backfill tests:
# optimizer_override_pct DEFAULT_ALLOCATION_TARGETS asset_class_optimizer_controls.csv

def _package_instance_payload(version: str | None = None) -> dict:
    """Return an identifier for the exact package root serving this process."""
    try:
        root = str(BASE_DIR.resolve())
    except Exception:
        root = str(BASE_DIR)
    version_text = str(version or "")
    try:
        package_instance_id = hashlib.sha256(f"{version_text}|{root}".encode("utf-8")).hexdigest()[:16]
    except Exception:
        package_instance_id = ""
    return {"package_root": root, "package_instance_id": package_instance_id}

def _configured_plan_csv_path(cfg=None) -> Path:
    cfg = cfg or RUNTIME_CONFIG
    raw = getattr(cfg, "config_file", "") or "input/client_data.csv"
    p = Path(raw)
    return p if p.is_absolute() else BASE_DIR / p

CSV_PATH = _configured_plan_csv_path(RUNTIME_CONFIG)


@app.errorhandler(Exception)
def _json_unhandled_error(exc):
    """Return API failures as JSON so the UI does not show raw framework HTML."""
    if isinstance(exc, HTTPException):
        return exc
    try:
        app.logger.exception("Unhandled API error", exc_info=exc)
    except Exception:
        pass
    message = f"{exc.__class__.__name__}: {exc}" if str(exc) else exc.__class__.__name__
    return jsonify({"success": False, "error": message}), 500




def _runtime_security_startup_findings(cfg=None) -> list[str]:
    """Local-only package: no public-hosting startup security modes remain."""
    return []

def enforce_startup_security(cfg=None) -> None:
    return None

def _runtime_config():
    try:
        return load_runtime_config()
    except Exception:
        return RUNTIME_CONFIG


def _sqlite_db() -> Path:
    cfg = _runtime_config()
    p = Path(cfg.sqlite_db or DEFAULT_DB)
    return p if p.is_absolute() else BASE_DIR / p


def _request_system_config_csv() -> Path:
    """Create a per-request system_config.csv copy for subprocess builds/tools."""
    source = _system_config_path()
    target = _workspace_output() / "system_config.active.csv"
    rows = []
    if source.exists():
        with source.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    if not rows:
        rows = [["section", "subsection", "label", "value", "units", "notes"]]

    def set_value(section: str, subsection: str, label: str, value: str) -> None:
        nonlocal rows
        for row in rows:
            while len(row) < 6:
                row.append("")
            if row[0] == section and row[1] == subsection and row[2] == label:
                row[3] = value
                return
        rows.append([section, subsection, label, value, "", "Per-request runtime value."])

    plan_dir = "input"
    set_value("System Configuration", "Runtime", "config_file", f"{plan_dir}/client_data.csv")
    set_value("System Configuration", "Runtime", "json_config_file", f"{plan_dir}/client_data.json")
    set_value("System Configuration", "Runtime", "yaml_config_file", f"{plan_dir}/client_data.yaml")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)
    return target


def _bootstrap_workspace() -> str:
    return "local"


def _bootstrap_client() -> str:
    return "local"


def _candidate_token() -> str:
    header_token = extract_bearer_or_header(request.headers)
    if header_token:
        return header_token
    cfg = _runtime_config()
    return str(request.cookies.get(cfg.session_cookie_name, "") or "").strip()


def _html_request() -> bool:
    accept = str(request.headers.get("Accept", ""))
    return "text/html" in accept or request.path in {"/", "/admin", "/login"}


def _public_path() -> bool:
    path = request.path or ""
    if path == "/api/ping":
        return True
    if path in {"/login", "/api/auth/login", "/api/auth/logout", "/api/auth/session"}:
        return True
    if path.startswith("/frontend/assets/"):
        return True
    return False








def _has_bearer_or_api_header() -> bool:
    return bool(str(request.headers.get("Authorization", "")).strip() or str(request.headers.get("X-API-Token", "")).strip())




def _cookie_secure_for_request(cfg) -> bool:
    return bool(cfg.session_cookie_secure or request.is_secure or str(request.headers.get("X-Forwarded-Proto", "")).lower() == "https")


def _set_auth_cookie(response, token: str):
    cfg = _runtime_config()
    response.set_cookie(
        cfg.session_cookie_name,
        token,
        max_age=int(cfg.session_max_age_hours * 3600),
        httponly=True,
        secure=_cookie_secure_for_request(cfg),
        samesite=cfg.session_cookie_samesite,
    )
    return response


def _clear_auth_cookie(response):
    cfg = _runtime_config()
    response.delete_cookie(cfg.session_cookie_name)
    return response


def _identity_from_token(token: str) -> tuple[bool, UserContext | None]:
    if not token:
        return False, None
    cfg = _runtime_config()
    token_row = lookup_api_token(token, _sqlite_db())
    if token_row:
        return True, UserContext(
            user_id=str(token_row.get("user_id") or "api-user"),
            email=str(token_row.get("email") or token_row.get("user_id") or "api-user"),
            role=str(token_row.get("role") or cfg.default_role),
            workspace_id=sanitize_id(token_row.get("workspace_id") or cfg.workspace_id),
        )
    expected = get_server_token()
    if constant_time_token_ok(token, expected):
        return True, UserContext(user_id="server-token", email="server-token", role=cfg.default_role, workspace_id=sanitize_id(cfg.workspace_id))
    return False, None


def _authorized_and_identity() -> tuple[bool, UserContext | None]:
    return True, None


def _current_user() -> UserContext:
    return UserContext(user_id="local", email="local", role="advisor", workspace_id="local")


def _workspace_id() -> str:
    return "local"


def _client_id() -> str:
    return "local"


def _workspace_output() -> Path:
    out = workspace_output_dir(_workspace_id(), BASE_DIR)
    out.mkdir(parents=True, exist_ok=True)
    return out


def _audit(event: str, details: dict | None = None) -> None:
    cfg = _runtime_config()
    details = details or {}
    user = _current_user() if request else UserContext()
    if cfg.audit_log_enabled:
        try:
            audit_path = _workspace_output() / "audit_log.jsonl"
            payload = {"event": event, "details": details, "workspace_id": user.workspace_id, "user_id": user.user_id, "timestamp": time.time()}
            line = json.dumps(payload, sort_keys=True, default=str)
            if cfg.redact_secrets_in_logs:
                line = redact_text(line)
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            with audit_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
        try:
            append_audit_event_sqlite(event, details, workspace_id=user.workspace_id, user_id=user.user_id, db_path=_sqlite_db())
        except Exception:
            pass





def _admin_change_log_path_for(workspace_id: str | None = None) -> Path:
    """Local admin/config change log used by Build Impact."""
    tid = sanitize_id(workspace_id or _workspace_id())
    out = workspace_output_dir(tid, BASE_DIR)
    out.mkdir(parents=True, exist_ok=True)
    return out / "admin_config_change_log.json"


def _last_build_metadata_path_for(workspace_id: str | None = None) -> Path:
    tid = sanitize_id(workspace_id or _workspace_id())
    out = workspace_output_dir(tid, BASE_DIR)
    out.mkdir(parents=True, exist_ok=True)
    return out / "last_build_metadata.json"


def _row_key_for_change(row: list[str], index: int) -> str:
    vals = [str(x) for x in row]
    if len(vals) >= 4 and vals[0].strip().lower() == "system configuration":
        return " / ".join([vals[0].strip(), vals[1].strip(), vals[2].strip()])
    if len(vals) >= 4 and vals[0].strip() and vals[2].strip():
        return " / ".join([vals[0].strip(), vals[1].strip(), vals[2].strip()])
    return f"row {index + 1}"


def _summarize_csv_row_changes(before_rows: list[list[str]], after_rows: list[list[str]], limit: int = 40) -> tuple[list[dict], int]:
    """Return compact row/value changes between two CSV row lists."""
    changes: list[dict] = []
    max_len = max(len(before_rows), len(after_rows))
    for i in range(max_len):
        before = before_rows[i] if i < len(before_rows) else []
        after = after_rows[i] if i < len(after_rows) else []
        if before == after:
            continue
        # Prefer value-column differences for section/subsection/label/value settings.
        if len(before) >= 4 and len(after) >= 4 and before[:3] == after[:3]:
            before_value = before[3] if len(before) > 3 else ""
            after_value = after[3] if len(after) > 3 else ""
            if before_value != after_value:
                changes.append({
                    "label": _row_key_for_change(after, i),
                    "before": before_value,
                    "after": after_value,
                    "row_index": i,
                })
                continue
        changes.append({
            "label": _row_key_for_change(after or before, i),
            "before": ", ".join(str(x) for x in before[:6]) if before else "row added",
            "after": ", ".join(str(x) for x in after[:6]) if after else "row removed",
            "row_index": i,
        })
    return changes[:limit], len(changes)


def _record_admin_config_change(kind: str, file_name: str, path: str, before_rows: list[list[str]], after_rows: list[list[str]], workspace_id: str | None = None) -> dict | None:
    """Append a local admin change event if a CSV actually changed."""
    changes, count = _summarize_csv_row_changes(before_rows or [], after_rows or [])
    if count <= 0:
        return None
    user = _current_user() if request else UserContext()
    event = {
        "timestamp": time.time(),
        "kind": str(kind or "").lower(),
        "file": Path(str(file_name or "")).name,
        "path": str(path or ""),
        "changed_by": getattr(user, "email", "") or getattr(user, "user_id", "") or "admin",
        "change_count": count,
        "changes": changes,
    }
    p = _admin_change_log_path_for(workspace_id or getattr(user, "workspace_id", None))
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    except Exception:
        data = []
    data.append(event)
    data = data[-250:]
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return event


def _admin_changes_between(workspace_id: str | None = None, after_ts: float | None = None, before_ts: float | None = None) -> list[dict]:
    """Admin/config changes after `after_ts` and up to `before_ts` for Build Impact."""
    p = _admin_change_log_path_for(workspace_id)
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    except Exception:
        return []
    out = []
    for ev in data:
        try:
            ts = float(ev.get("timestamp", 0))
        except Exception:
            ts = 0.0
        if after_ts is not None and ts <= float(after_ts):
            continue
        if before_ts is not None and ts > float(before_ts):
            continue
        out.append(ev)
    return out


def _read_last_build_timestamp(workspace_id: str | None = None) -> float:
    p = _last_build_metadata_path_for(workspace_id)
    try:
        return float((json.loads(p.read_text(encoding="utf-8")) or {}).get("finished_at_ts") or 0)
    except Exception:
        return 0.0


def _write_last_build_metadata(workspace_id: str | None, payload: dict) -> None:
    p = _last_build_metadata_path_for(workspace_id)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _make_request_system_config_csv_for(workspace: str, client: str, out_dir: Path) -> Path:
    """Thread-safe version of _request_system_config_csv for async build jobs."""
    source = _system_config_path()
    target = out_dir / "system_config.active.csv"
    rows: list[list[str]] = []
    if source.exists():
        with source.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    if not rows:
        rows = [["section", "subsection", "label", "value", "units", "notes"]]

    def set_value(section: str, subsection: str, label: str, value: str) -> None:
        for row in rows:
            while len(row) < 6:
                row.append("")
            if row[0] == section and row[1] == subsection and row[2] == label:
                row[3] = value
                return
        rows.append([section, subsection, label, value, "", "Per-request runtime value."])

    workspace = "local"
    client = "local"
    plan_dir = "input"
    set_value("System Configuration", "Runtime", "config_file", f"{plan_dir}/client_data.csv")
    set_value("System Configuration", "Runtime", "json_config_file", f"{plan_dir}/client_data.json")
    set_value("System Configuration", "Runtime", "yaml_config_file", f"{plan_dir}/client_data.yaml")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)
    return target

def _normalize_plan_data_file_name(file_name: str) -> str:
    name = Path(str(file_name or "")).name
    if name not in PLAN_DATA_FILE_SET:
        raise ValueError("Unsupported Plan Data file")
    return name


def _normalize_reference_file_name(file_name: str) -> str:
    name = Path(str(file_name or "")).name
    if name not in set(SYSTEM_REFERENCE_FILES):
        raise ValueError("Unsupported system/reference file")
    return name


def _reference_file_path(file_name: str) -> Path:
    return BASE_DIR / "reference_data" / _normalize_reference_file_name(file_name)


def _read_csv_rows_file(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.reader(f))


def _write_csv_rows_file(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)
    tmp.replace(path)

def _system_config_path() -> Path:
    return BASE_DIR / "system_config.csv"


def _set_system_config_values(updates: dict[tuple[str, str, str], str]) -> None:
    """Update value cells in system_config.csv, adding rows when needed."""
    p = _system_config_path()
    rows = _read_csv_rows_file(p)
    if not rows:
        rows = [["section", "subsection", "label", "value", "units", "notes"]]
    while len(rows[0]) < 6:
        rows[0].append("")
    for (section, subsection, label), value in updates.items():
        found = False
        for row in rows[1:]:
            while len(row) < 6:
                row.append("")
            if row[0] == section and row[1] == subsection and row[2] == label:
                row[3] = str(value)
                found = True
                break
        if not found:
            rows.append([section, subsection, label, str(value), "", "Set by Admin operating mode."])
    _write_csv_rows_file(p, rows)


USER_DATA_BLANK_FILES = {
    "client_household.csv",
    "client_income.csv",
    "client_spending.csv",
    "client_assets.csv",
    "client_insurance_estate.csv",
}


def _blank_user_data_csv(content: str) -> str:
    """Keep row metadata but blank the value column for user-entered plan facts."""
    rows = list(csv.reader(io.StringIO(content or "")))
    out_rows = []
    for i, row in enumerate(rows):
        row = list(row)
        if not row:
            out_rows.append(row)
            continue
        first = str(row[0] or "").strip()
        is_header = i == 0 and any(str(c).strip().lower() == "value" for c in row)
        is_comment = first.startswith("#")
        if not is_header and not is_comment and len(row) >= 4:
            row[3] = ""
        out_rows.append(row)
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(out_rows)
    return out.getvalue()


def _blank_holdings_csv(content: str) -> str:
    rows = list(csv.reader(io.StringIO(content or "")))
    header = rows[0] if rows else ["account", "symbol", "purchase_date", "shares", "purchase_price", "lot_type", "note"]
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerow(header)
    return out.getvalue()


def _blank_liabilities_csv(content: str) -> str:
    rows = list(csv.reader(io.StringIO(content or "")))
    header = rows[0] if rows else ["liability_id", "type", "label", "balance", "interest_rate", "monthly_payment", "start_year", "payoff_year", "notes"]
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerow(header)
    return out.getvalue()


def _make_blank_plan_files() -> dict[str, str]:
    """Create a blank-client-data Plan Data set from packaged templates."""
    source_dir = BASE_DIR / "input"
    files: dict[str, str] = {}
    for name in PLAN_DATA_CSV_FILES:
        src = source_dir / name
        text = src.read_text(encoding="utf-8-sig") if src.exists() else ""
        if name in USER_DATA_BLANK_FILES:
            text = _blank_user_data_csv(text)
        elif name == "client_holdings.csv":
            text = _blank_holdings_csv(text)
        elif name == "client_liabilities.csv":
            text = _blank_liabilities_csv(text)
        files[name] = text
    return files



PROTECTED_CLIENT_DATA_KEYS = {
    ("Household", "", "member_1_retirement_date"),
    ("Household", "", "member_2_retirement_date"),
}


def _client_data_key(row: list[str]) -> tuple[str, str, str] | None:
    if len(row) < 3:
        return None
    return (str(row[0] or "").strip(), str(row[1] or "").strip(), str(row[2] or "").strip())


def _merge_protected_client_data_values(incoming: str, fallback: str | None) -> str:
    """Prevent blank incoming saves from erasing local retirement dates.

    Folder load/save can involve a browser-local folder plus the app working copy.
    For these easy-to-lose fields, a non-empty value already present in the
    local/app copy wins over a blank value in the incoming payload. A user can
    still replace a value by entering another non-empty value. API keys and
    other system settings are no longer stored in client_data.csv.
    """
    if not fallback:
        return incoming
    try:
        incoming_rows = list(csv.reader(io.StringIO(incoming)))
        fallback_rows = list(csv.reader(io.StringIO(fallback)))
    except Exception:
        return incoming
    fallback_values: dict[tuple[str, str, str], str] = {}
    for row in fallback_rows:
        key = _client_data_key(row)
        if key in PROTECTED_CLIENT_DATA_KEYS:
            value = row[3] if len(row) > 3 else ""
            if str(value).strip():
                fallback_values[key] = value
    if not fallback_values:
        return incoming
    changed = False
    for row in incoming_rows:
        key = _client_data_key(row)
        if key in fallback_values:
            while len(row) < 4:
                row.append("")
            if not str(row[3] or "").strip():
                row[3] = fallback_values[key]
                changed = True
    if not changed:
        return incoming
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(incoming_rows)
    return out.getvalue()


def _protected_client_data_status(content: str | None = None) -> dict:
    """Return non-secret preservation status for validation/UI diagnostics."""
    sources: list[str] = []
    if content is not None:
        sources.append(content)
    else:
        for name in CLIENT_DATA_CSV_FILES:
            path = _plan_data_path(name)
            if path.exists():
                sources.append(path.read_text(encoding="utf-8-sig"))
    values: dict[tuple[str, str, str], str] = {}
    for source in sources:
        rows = list(csv.reader(io.StringIO(source or "")))
        for row in rows:
            key = _client_data_key(row)
            if key in PROTECTED_CLIENT_DATA_KEYS:
                values[key] = row[3] if len(row) > 3 else ""
    return {
        "member_1_retirement_date_present": bool(str(values.get(("Household", "", "member_1_retirement_date"), "")).strip()),
        "member_2_retirement_date_present": bool(str(values.get(("Household", "", "member_2_retirement_date"), "")).strip()),
    }


def _plan_data_path(file_name: str, prefer_existing: bool = True) -> Path:
    name = _normalize_plan_data_file_name(file_name)
    if name in CLIENT_DATA_CSV_FILE_SET:
        return CSV_PATH if name == "client_data.csv" else CSV_PATH.parent / name
    if name in CLIENT_DATA_DERIVED_FILE_SET:
        return CSV_PATH.parent / name
    return workspace_file(name, _workspace_id(), BASE_DIR, prefer_existing=prefer_existing)



def _apply_plan_data_payload(plan_data_files: dict) -> dict:
    """Write a client-supplied Plan Data snapshot before a build.

    The UI uses this when a user has selected a local Plan Data folder. It
    forces the build endpoint to start from the latest local-disk CSV contents
    rather than whatever the server working copy happened to contain.
    """
    if not isinstance(plan_data_files, dict):
        return {"files": [], "bytes": 0}
    written = []
    total = 0
    missing_required = []
    for required in ("client_data.csv", "client_holdings.csv"):
        if required not in plan_data_files:
            missing_required.append(required)
    if missing_required:
        raise ValueError("Missing required local Plan Data file(s): " + ", ".join(missing_required))
    for raw_name, raw_content in plan_data_files.items():
        name = _normalize_plan_data_file_name(raw_name)
        content = "" if raw_content is None else str(raw_content)
        path = _write_plan_data_file(name, content)
        written.append({"file": name, "path": str(path), "bytes": len(content)})
        total += len(content)
    try:
        _ensure_user_ui_plan_data_rows()
    except Exception as exc:
        _audit("plan_data_payload_ui_row_warning", {"error": str(exc)})
    try:
        _sync_config_backends()
    except Exception as exc:
        _audit("plan_data_payload_sync_warning", {"error": str(exc)})
    return {"files": written, "bytes": total}

def _read_plan_data_file(file_name: str) -> str | None:
    name = _normalize_plan_data_file_name(file_name)
    # The on-disk Plan Data CSV is the local working copy. Prefer it over the
    # optional SQLite mirror so a locked/stale database cannot make the UI load
    # an older copy after a folder import.
    path = _plan_data_path(name, prefer_existing=True)
    if path.exists():
        return path.read_text(encoding="utf-8-sig")
    if name != "client_data.csv":
        content = get_client_file(name, _workspace_id(), _client_id(), _sqlite_db())
        if content is not None:
            return content
    return None


def _write_plan_data_file(file_name: str, content: str, *, preserve_protected: bool = True) -> Path:
    name = _normalize_plan_data_file_name(file_name)
    path = _plan_data_path(name, prefer_existing=False)
    if name in CLIENT_DATA_CSV_FILE_SET:
        content = canonicalize_roth_csv_content(content)
        content, removed = _strip_deprecated_allocation_count_csv(content)
        if removed:
            _audit("deprecated_allocation_count_rows_stripped", {"file": name, "removed": removed})
        content, removed_home = _strip_retired_scenario_home_csv(content)
        if removed_home:
            _audit("retired_scenario_home_rows_stripped", {"file": name, "removed": removed_home})
    if preserve_protected and name in CLIENT_DATA_CSV_FILE_SET and path.exists():
        try:
            content = _merge_protected_client_data_values(content, path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            _audit("protected_client_data_merge_warning", {"file": name, "error": str(exc)})
    if name in CLIENT_DATA_CSV_FILE_SET:
        content, removed = _strip_deprecated_allocation_count_csv(content)
        if removed:
            _audit("deprecated_allocation_count_rows_stripped_after_merge", {"file": name, "removed": removed})
        content, removed_home = _strip_retired_scenario_home_csv(content)
        if removed_home:
            _audit("retired_scenario_home_rows_stripped_after_merge", {"file": name, "removed": removed_home})
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    if name != "client_data.csv":
        try:
            set_client_file(name, content, _workspace_id(), _client_id(), _current_user().user_id, _sqlite_db())
        except Exception as exc:
            # SQLite is only a mirror for these Plan Data files in local mode.
            # Folder loading should not fail just because the mirror database is
            # locked, read-only, or from an older package.
            _audit("plan_data_sqlite_mirror_warning", {"file": name, "error": str(exc)})
    return path





DEPRECATED_ALLOCATION_COUNT_LABELS = {
    "_".join(parts)
    for parts in [
        ("count", "social", "security", "toward", "fixed", "income", "target"),
        ("count", "pension", "toward", "fixed", "income", "target"),
        ("count", "annuity", "toward", "fixed", "income", "target"),
        ("count", "note", "receivable", "toward", "fixed", "income", "target"),
        ("count", "home", "equity", "toward", "reit", "target"),
    ]
}

RETIRED_SCENARIO_HOME_ROW_KEYS = {
    ("Scenarios", "Sell Home", "home_sale_price"),
    ("Scenarios", "Sell Home", "home_basis"),
    ("Scenarios", "Sell Home", "home_value"),
    ("Scenarios", "Sell Home", "house_value"),
    ("Scenarios", "Sell Home", "value_as_of_plan_start"),
    ("Scenarios", "Sell Home", "current_home_value"),
    ("Scenarios", "Sell Home", "current_value"),
    ("Scenarios", "Sell Home", "market_value"),
}


# Generic "drop rows matching a predicate" primitives shared by every
# retired/deprecated Plan Data row migration below. Each migration only
# needs to supply its own row-matching predicate.
def _strip_rows_matching(rows: list[list[str]], predicate) -> tuple[list[list[str]], int]:
    kept: list[list[str]] = []
    removed = 0
    for row in rows:
        if predicate(row):
            removed += 1
            continue
        kept.append(row)
    return kept, removed


def _strip_csv_rows_matching(content: str, predicate) -> tuple[str, int]:
    source = io.StringIO(content or "")
    rows = list(csv.reader(source))
    kept, removed = _strip_rows_matching(rows, predicate)
    if not removed:
        return content, 0
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(kept)
    return out.getvalue(), removed


def _purge_rows_matching_from_plan_data(predicate) -> int:
    removed_total = 0
    for name in CLIENT_DATA_CSV_FILES:
        path = _plan_data_path(name, prefer_existing=True)
        if not path.exists():
            continue
        rows = _csv_read_rows(path)
        kept, removed = _strip_rows_matching(rows, predicate)
        if removed:
            _csv_write_rows(path, kept)
            removed_total += removed
    return removed_total


def _is_retired_scenario_home_row(row: list[str]) -> bool:
    cols = list(row) + [""] * 3
    key = (str(cols[0]).strip(), str(cols[1]).strip(), str(cols[2]).strip())
    return key in RETIRED_SCENARIO_HOME_ROW_KEYS


def _strip_retired_scenario_home_rows(rows: list[list[str]]) -> tuple[list[list[str]], int]:
    return _strip_rows_matching(rows, _is_retired_scenario_home_row)


def _strip_retired_scenario_home_csv(content: str) -> tuple[str, int]:
    return _strip_csv_rows_matching(content, _is_retired_scenario_home_row)


def _purge_retired_scenario_home_rows_from_plan_data() -> int:
    return _purge_rows_matching_from_plan_data(_is_retired_scenario_home_row)


def _is_deprecated_allocation_count_row(row: list[str]) -> bool:
    cols = list(row) + [""] * 3
    return (
        str(cols[0]).strip() == "Model Constants"
        and str(cols[1]).strip() == "Allocation"
        and str(cols[2]).strip() in DEPRECATED_ALLOCATION_COUNT_LABELS
    )


def _strip_deprecated_allocation_count_rows(rows: list[list[str]]) -> tuple[list[list[str]], int]:
    return _strip_rows_matching(rows, _is_deprecated_allocation_count_row)


def _strip_deprecated_allocation_count_csv(content: str) -> tuple[str, int]:
    return _strip_csv_rows_matching(content, _is_deprecated_allocation_count_row)


def _purge_deprecated_allocation_count_rows_from_plan_data() -> int:
    return _purge_rows_matching_from_plan_data(_is_deprecated_allocation_count_row)


def _csv_read_rows(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.reader(f))


def _csv_write_rows(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)
    tmp.replace(path)


def _ensure_header(rows: list[list[str]]) -> list[list[str]]:
    header = ["section", "subsection", "label", "value", "units", "notes"]
    if not rows:
        return [header]
    first = [str(x or "").strip().lower() for x in rows[0][:3]]
    if first[:3] != ["section", "subsection", "label"]:
        return [header, *rows]
    while len(rows[0]) < 6:
        rows[0].append("")
    rows[0][:6] = header
    return rows


def _row_key(row: list[str]) -> tuple[str, str, str]:
    cols = list(row) + [""] * 6
    return (str(cols[0]).strip(), str(cols[1]).strip(), str(cols[2]).strip())


ROTH_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Model Constants", "Roth Conversion", "roth_conv_window_end_offset", "-1", "years", "CONV_END_YR = H_RMD_start_yr + this offset; default -1 ends voluntary conversions the year before RMDs."],
    ["Model Constants", "IRMAA", "irmaa_annual_inflator", "2.00%", "pct", "Annual IRMAA threshold inflation rate used when projecting Medicare premium guardrails."],
    ["Withdrawal Policy", "Roth Conversion", "roth_conversion_policy", "optimize_terminal_tax", "choice", "optimize_terminal_tax | fill_to_bracket | fill_to_irmaa | fixed_dollar | none; high-level policy for voluntary conversions."],
    ["Withdrawal Policy", "Roth Conversion", "roth_bracket_strategy", "OPTIMIZER_CHOOSES", "choice", "NONE | FILL_CURRENT_BRACKET | FILL_TARGET_BRACKET | PARTIAL_TARGET_BRACKET | IRMAA_GUARDED | SURVIVOR_TAX_AWARE | RMD_REDUCTION | LEGACY_TARGETED | OPTIMIZER_CHOOSES | FIXED_DOLLAR; strategy family considered by the Roth optimizer."],
    ["Withdrawal Policy", "Roth Conversion", "roth_objective_mode", "BALANCED_RETIREMENT", "choice", "BALANCED_RETIREMENT | MINIMIZE_LIFETIME_TAX | MAXIMIZE_TERMINAL_NET_WORTH | LEGACY_OPTIMIZED | ESTATE_TAX_AWARE | CUSTOM_WEIGHTED; objective used to rank Roth conversion candidates."],
    ["Withdrawal Policy", "Roth Conversion", "estate_tax_objective_mode", "BALANCED", "choice", "OFF | MONITOR_ONLY | BALANCED | STRONG; whether projected estate-tax exposure affects Roth strategy scoring."],
    ["Withdrawal Policy", "Roth Conversion", "roth_headroom_usage_pct", "95.00%", "percent", "Percentage of available tax-bracket headroom to use; 95% leaves margin below the threshold."],
    ["Withdrawal Policy", "Roth Conversion", "roth_target_bracket_rate", "22.00%", "choice", "10.00% | 12.00% | 22.00% | 24.00% | 32.00% | 35.00% | 37.00%; Target marginal bracket ceiling used by bracket-fill policies."],
    ["Withdrawal Policy", "Roth Conversion", "roth_irmaa_target_tier", "TIER_2", "choice", "TIER_1 | TIER_2 | TIER_3 | TIER_4 | TIER_5; IRMAA cap tier used by Roth conversion guardrails. UI labels show MFJ and Single dollar thresholds from annual tax data."],
    ["Withdrawal Policy", "Roth Conversion", "irmaa_guardrail_mode", "AVOID_NEXT_TIER", "choice", "IGNORE | WARN_ONLY | AVOID_NEXT_TIER | AVOID_TIER_2_OR_ABOVE | CUSTOM_MAGI_CAP; Medicare threshold guardrail for Roth conversions."],
    ["Withdrawal Policy", "Roth Conversion", "roth_irmaa_headroom_usage_pct", "95.00%", "percent", "Percentage of available IRMAA headroom to use before stopping voluntary conversions."],
    ["Withdrawal Policy", "Roth Conversion", "roth_fixed_annual_amount", "$50,000 ", "dollars", "Annual amount used only when roth_conversion_policy is fixed_dollar."],
    ["Withdrawal Policy", "Roth Conversion", "max_annual_conversion_pct_of_traditional_ira", "20.00%", "percent", "Maximum voluntary conversion in a year as a percentage of starting traditional IRA/pre-tax balances."],
    ["Withdrawal Policy", "Roth Conversion", "max_conversion_years", "10", "years", "Maximum number of years in the voluntary conversion window, also bounded by the RMD-age window."],
    ["Withdrawal Policy", "Roth Conversion", "roth_optimize_terminal_weight", "1.00", "number", "Weight on after-tax terminal net worth in the optimizer objective."],
    ["Withdrawal Policy", "Roth Conversion", "roth_optimize_lifetime_tax_weight", "0.25", "number", "Weight on lifetime tax penalty in the optimizer objective."],
    ["Withdrawal Policy", "Roth Conversion", "roth_optimize_terminal_pretax_tax_rate", "24.00%", "percent", "After-tax haircut applied to terminal pre-tax balances for objective scoring."],
    ["Withdrawal Policy", "Roth Conversion", "legacy_objective_mode", "BALANCED", "choice", "OFF | LOW | BALANCED | STRONG; adds future-tax and inheritance-burden weighting to Roth conversion optimization."],
    ["Withdrawal Policy", "Roth Conversion", "future_tax_rate_stress_pct", "10.00%", "percent", "Additional future ordinary-tax-rate stress used only for scoring Roth conversion candidates."],
    ["Withdrawal Policy", "Roth Conversion", "future_tax_risk_weight", "0.35", "number", "Weight on reducing future pre-tax IRA exposure if tax rates rise faster than modeled."],
    ["Withdrawal Policy", "Roth Conversion", "inheritance_tax_burden_weight", "0.25", "number", "Weight on reducing ordinary-income tax burden heirs may inherit with pre-tax retirement assets."],
    ["Withdrawal Policy", "Roth Conversion", "heir_ordinary_tax_rate_assumption_pct", "24.00%", "percent", "Assumed ordinary-income tax rate heirs may pay on inherited pre-tax retirement distributions."],
    ["Withdrawal Policy", "Roth Conversion", "pre_tax_bequest_penalty_pct", "15.00%", "percent", "Objective haircut applied to terminal pre-tax balances to reflect inheritance tax burden."],
    ["Withdrawal Policy", "Roth Conversion", "roth_bequest_preference_bonus_pct", "5.00%", "percent", "Objective bonus for terminal Roth balances left to heirs or future-self tax flexibility."],
    ["Withdrawal Policy", "Roth Conversion", "survivor_tax_risk_weight", "0.25", "number", "Weight on reducing pre-tax exposure during years when one spouse may face single-filer tax compression."],
]



MONTE_CARLO_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Model Constants", "Monte Carlo", "mc_engine_mode", "advanced_exact_scalar", "choice", "advanced_exact_scalar | quick_vectorized; User UI toggle: Complex/Advanced Exact Scalar is slower and advisor-ready; Simple/Quick Vectorized is faster and approximate for diagnostics."],
]



HSA_WITHDRAWAL_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["HSA Policy", "Withdrawals", "hsa_withdrawal_mode", "spend_as_needed", "choice", "spend_as_needed | annual_pct | smooth_window; default spend_as_needed uses HSA only when needed before Roth. annual_pct draws the configured percentage each active year. smooth_window spreads balance across start/end years."],
    ["HSA Policy", "Withdrawals", "hsa_annual_spend_pct", "10.00%", "percent", "Annual HSA draw percentage used only when hsa_withdrawal_mode is annual_pct."],
    ["HSA Policy", "Withdrawals", "hsa_withdrawal_start_year", "", "year", "Optional first year for annual_pct or smooth_window HSA draw policy. Leave blank to avoid a scheduled draw."],
    ["HSA Policy", "Withdrawals", "hsa_withdrawal_end_year", "", "year", "Optional last year for annual_pct or smooth_window HSA draw policy. Leave blank to avoid a scheduled draw."],
]

SOCIAL_SECURITY_FUNDING_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Social Security", "Funding Discount", "ss_funding_discount_year", "2032", "year", "First year Social Security gross benefits are reduced for trust-fund underfunding stress. Default 2032."],
    ["Social Security", "Funding Discount", "ss_funding_discount_pct", "22.00%", "percent", "Percentage reduction to gross Social Security benefits from the funding-discount year onward. Default 22%."],
]

HEALTHCARE_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Wellness", "Medicare", "part_g_base_premium_monthly", "$0", "dollars", "Current monthly Medicare Supplement Plan G / Medigap-style premium per Medicare-enrolled person. Enter $0 if no supplement is modeled."],
]

HELOC_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["HELOC", "Setup", "heloc_enabled", "No", "yes/no", "Enable the HELOC strategy. When Yes, the projection draws from the HELOC during the draw period to fund large discretionary spending instead of liquidating portfolio assets."],
    ["HELOC", "Setup", "heloc_credit_limit", "$0", "dollars", "Maximum HELOC credit line available. The projection will not borrow beyond this amount."],
    ["HELOC", "Setup", "heloc_draw_end_year", "0", "year", "Last year the HELOC can be drawn. After this year no new borrowing occurs; the outstanding balance accrues interest until repaid at home sale."],
    ["HELOC", "Setup", "heloc_initial_rate_pct", "8.50%", "percent", "Starting annual interest rate on the HELOC balance (variable rate). Interest is paid from cash flow each year."],
    ["HELOC", "Setup", "heloc_rate_drift_bps_yr", "25", "number", "Annual rate increase in basis points per year (e.g. 25 = +0.25%/yr). Models a rising-rate environment over the draw period."],
]


ALLOCATION_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Asset Allocation Policy", "Global", "allocation_selection_mode", "user_target", "choice", "user_target | optimizer_recommendation; Choose whether the plan uses user-specified target_pct allocation rows or the allocation optimizer recommendation."],
]

def _ensure_allocation_ui_plan_data_rows() -> None:
    """Materialize the current-schema allocation mode row used by the User UI.

    Clean-forward package note: this creates only the canonical current row; it
    does not read or translate retired scenario aliases.
    """
    policy_path = _plan_data_path("client_policy.csv", prefer_existing=False)
    rows = _ensure_header(_csv_read_rows(policy_path))
    seen = {_row_key(r) for r in rows[1:]}
    additions = [list(row) for row in ALLOCATION_UI_PLAN_DATA_ROWS if _row_key(row) not in seen]
    if not additions:
        return
    insert_at = len(rows)
    for i, row in enumerate(rows[1:], start=1):
        sec = str(row[0] if row else "").strip()
        if sec in {"Asset Class Optimizer Controls", "Withdrawal Policy", "Model Constants", "Forced Actions", "Scenarios"}:
            insert_at = i
            break
    rows[insert_at:insert_at] = additions
    _csv_write_rows(policy_path, rows)

CORE_SPENDING_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Cashflow", "Spending", "core_spending_growth_mode", "cpi", "choice", "cpi | manual_override; Choose whether core spending increases with general CPI or a manual spending-specific rate."],
    ["Cashflow", "Spending", "core_spending_manual_growth_rate", "0.00%", "percent", "Annual core-spending increase used only when core_spending_growth_mode is manual_override."],
]

MORTGAGE_RE_TAX_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Cashflow", "Mortgage", "annual_real_estate_taxes", "0", "USD", "Annual real-estate/property tax cash-flow amount; shown with Mortgage and RE Tax instead of core spending."],
    ["Cashflow", "Mortgage", "real_estate_tax_annual_adjustment_pct", "2.50%", "percent", "Annual percentage adjustment applied to real-estate/property taxes in the cash-flow forecast."],
]

def _ensure_row_in_csv(file_name: str, canonical_row: list[str], *, insert_after: tuple[str, str] | None = None) -> bool:
    """Ensure a canonical Plan Data row exists in the forward schema.

    This is not a previous-name alias. It creates the current-schema rows needed by
    the User UI after a user imports an older-but-valid Plan Data folder.
    """
    path = _plan_data_path(file_name, prefer_existing=False)
    rows = _ensure_header(_csv_read_rows(path))
    key = _row_key(canonical_row)
    if key in {_row_key(r) for r in rows[1:]}:
        return False
    insert_at = len(rows)
    if insert_after:
        want_sec, want_sub = insert_after
        for i, row in enumerate(rows[1:], start=1):
            sec = str(row[0] if row else "").strip()
            sub = str(row[1] if len(row) > 1 else "").strip()
            if sec == want_sec and sub == want_sub:
                insert_at = i + 1
    rows[insert_at:insert_at] = [list(canonical_row)]
    _csv_write_rows(path, rows)
    return True


def _ensure_core_spending_ui_plan_data_rows() -> None:
    for row in CORE_SPENDING_UI_PLAN_DATA_ROWS:
        _ensure_row_in_csv("client_spending.csv", list(row), insert_after=("Cashflow", "Spending"))
    for row in MORTGAGE_RE_TAX_UI_PLAN_DATA_ROWS:
        _ensure_row_in_csv("client_spending.csv", list(row), insert_after=("Cashflow", "Mortgage"))
    _ensure_row_in_csv(
        "client_household.csv",
        ["Economic Assumptions", "", "inflation_general", "2.50%", "pct", "General CPI inflation used when core_spending_growth_mode is cpi."],
        insert_after=("Economic Assumptions", ""),
    )
    _ensure_row_in_csv(
        "client_policy.csv",
        ["Model Constants", "Retirement", "spending_freeze_year", "2040", "year", "Year after which core spending stops increasing; grouped with Spending / Core spending in the User UI."],
        insert_after=("Model Constants", "Retirement"),
    )


def _ensure_user_ui_plan_data_rows() -> None:
    """Materialize forward-schema rows that the guided User UI depends on.

    Folder imports and browser saves can bring in valid model inputs that lack
    newer UI control rows. The UI should never hide a new control merely because
    the imported folder predates that control. This function writes canonical
    current-schema rows only; it does not read previous-name aliases.
    """
    _ensure_allocation_ui_plan_data_rows()
    _ensure_monte_carlo_ui_plan_data_rows()
    _ensure_roth_ui_plan_data_rows()
    _ensure_hsa_withdrawal_ui_plan_data_rows()
    _ensure_social_security_funding_ui_plan_data_rows()
    _ensure_wellness_ui_plan_data_rows()
    _ensure_heloc_ui_plan_data_rows()
    _ensure_core_spending_ui_plan_data_rows()
    removed = _purge_retired_scenario_home_rows_from_plan_data()
    if removed:
        _audit("retired_scenario_home_rows_purged", {"removed": removed})


def _ensure_hsa_withdrawal_ui_plan_data_rows() -> None:
    policy_path = _plan_data_path("client_assets.csv", prefer_existing=False)
    rows = _ensure_header(_csv_read_rows(policy_path))
    seen = {_row_key(r) for r in rows[1:]}
    additions = [list(row) for row in HSA_WITHDRAWAL_UI_PLAN_DATA_ROWS if _row_key(row) not in seen]
    if not additions:
        return
    insert_at = len(rows)
    for i, row in enumerate(rows[1:], start=1):
        sec = str(row[0] if row else "").strip()
        if sec in {"Education Funding", "Equity Compensation", "Note Receivable", "Hybrid LTC"}:
            insert_at = i
            break
    rows[insert_at:insert_at] = additions
    _csv_write_rows(policy_path, rows)

def _ensure_social_security_funding_ui_plan_data_rows() -> None:
    income_path = _plan_data_path("client_income.csv", prefer_existing=False)
    rows = _ensure_header(_csv_read_rows(income_path))
    seen = {_row_key(r) for r in rows[1:]}
    additions = [list(row) for row in SOCIAL_SECURITY_FUNDING_UI_PLAN_DATA_ROWS if _row_key(row) not in seen]
    if not additions:
        return
    insert_at = len(rows)
    for i, row in enumerate(rows[1:], start=1):
        if str(row[0] if row else "").strip() == "Income Streams":
            insert_at = i
            break
    rows[insert_at:insert_at] = additions
    _csv_write_rows(income_path, rows)


def _ensure_wellness_ui_plan_data_rows() -> None:
    household_path = _plan_data_path("client_household.csv", prefer_existing=False)
    rows = _ensure_header(_csv_read_rows(household_path))
    seen = {_row_key(r) for r in rows[1:]}
    additions = [list(row) for row in HEALTHCARE_UI_PLAN_DATA_ROWS if _row_key(row) not in seen]
    if not additions:
        return
    insert_at = len(rows)
    for i, row in enumerate(rows[1:], start=1):
        if str(row[0] if row else "").strip() == "Wellness" and str(row[1] if len(row) > 1 else "").strip() == "Out-of-Pocket":
            insert_at = i
            break
    rows[insert_at:insert_at] = additions
    _csv_write_rows(household_path, rows)


def _ensure_heloc_ui_plan_data_rows() -> None:
    """Backfill HELOC strategy rows into client_policy.csv for existing plans."""
    policy_path = _plan_data_path("client_policy.csv", prefer_existing=False)
    rows = _ensure_header(_csv_read_rows(policy_path))
    seen = {_row_key(r) for r in rows[1:]}
    additions = [list(row) for row in HELOC_UI_PLAN_DATA_ROWS if _row_key(row) not in seen]
    if not additions:
        return
    # Insert before Withdrawal Policy or at end
    insert_at = len(rows)
    for i, row in enumerate(rows[1:], start=1):
        sec = str(row[0] if row else "").strip()
        if sec in {"Withdrawal Policy", "Model Constants", "Scenarios"}:
            insert_at = i
            break
    rows[insert_at:insert_at] = additions
    _csv_write_rows(policy_path, rows)


def _ensure_monte_carlo_ui_plan_data_rows() -> None:
    """Backfill the User UI Monte Carlo engine toggle into Plan Data.

    Older Plan Data folders often rely on the schema/default value for
    mc_engine_mode. The engine can run that default, but the User UI has no
    editable row to render, so the Simple vs Complex toggle appears missing.
    Add only the missing row and never overwrite an existing user choice.
    """
    policy_path = _plan_data_path("client_policy.csv", prefer_existing=False)
    rows = _ensure_header(_csv_read_rows(policy_path))
    seen = {_row_key(r) for r in rows[1:]}
    additions = [list(row) for row in MONTE_CARLO_UI_PLAN_DATA_ROWS if _row_key(row) not in seen]
    if not additions:
        return
    insert_at = len(rows)
    for i, row in enumerate(rows[1:], start=1):
        sec = str(row[0] if row else "").strip()
        sub = str(row[1] if len(row) > 1 else "").strip()
        if (sec == "Model Constants" and sub in {"Roth Conversion", "IRMAA"}) or sec in {"Withdrawal Policy", "Forced Actions", "Scenarios"}:
            insert_at = i
            break
    rows[insert_at:insert_at] = additions
    _csv_write_rows(policy_path, rows)


def _ensure_roth_ui_plan_data_rows() -> None:
    """Backfill Roth conversion UI controls into older or blank Plan Data.

    The secure package intentionally excludes the input folder, and many existing
    older Plan Data folders may predate the latest Roth controls. Without
    these rows, the User UI can only show the forced conversion row. This routine
    creates missing CSV-backed controls without overwriting existing values.
    """
    policy_path = _plan_data_path("client_policy.csv", prefer_existing=False)
    rows = _ensure_header(_csv_read_rows(policy_path))
    seen = {_row_key(r) for r in rows[1:]}
    additions = [list(row) for row in ROTH_UI_PLAN_DATA_ROWS if _row_key(row) not in seen]
    if not additions:
        return

    # Keep Roth controls near the rest of client policy instead of appending them
    # after scenarios when possible. Insert before the first forced-action or
    # scenario row; otherwise append at the end.
    insert_at = len(rows)
    for i, row in enumerate(rows[1:], start=1):
        sec = str(row[0] if row else "").strip()
        if sec in {"Forced Actions", "Scenarios"}:
            insert_at = i
            break
    rows[insert_at:insert_at] = additions
    _csv_write_rows(policy_path, rows)





def _client_csv_rows() -> list[dict]:
    """Return combined UI rows from the client-data manifest plus split files."""
    entries: list[dict] = []
    global_idx = 0
    for name in CLIENT_DATA_CSV_FILES:
        path = _plan_data_path(name)
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8-sig") as f:
            for source_idx, cols in enumerate(csv.reader(f)):
                entries.append({
                    "row_index": global_idx,
                    "source_file": name,
                    "source_row_index": source_idx,
                    "columns": cols,
                })
                global_idx += 1
    return entries


def _client_section_path(section: str, fallback_file: str = "client_data.csv") -> Path:
    """Find the split client CSV that already contains a section."""
    target = str(section or "").strip()
    for name in CLIENT_DATA_PART_FILES:
        path = _plan_data_path(name)
        if not path.exists():
            continue
        try:
            with path.open(newline="", encoding="utf-8-sig") as f:
                for row in csv.reader(f):
                    if row and str(row[0] or "").strip() == target:
                        return path
        except Exception:
            continue
    return _plan_data_path(fallback_file)


def _read_client_section_rows(section: str, fallback_file: str = "client_data.csv") -> list[list[str]]:
    path = _client_section_path(section, fallback_file)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.reader(f))


def _write_client_rows(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    tmp.replace(path)

def _read_schema_map() -> dict:
    return _load_schema_registry()


def _classify_config_row(section: str, subsection: str, label: str) -> str:
    sec = (section or "").strip()
    sub = (subsection or "").strip().lower()
    if sec == "Market Pricing":
        return "market_pricing"
    if sec == "Asset Class Assumptions":
        return "asset_assumptions"
    if sec == "Asset Allocation Policy":
        return "allocation_controls"
    if sec == "System Configuration":
        if sub in {"saas", "security"}:
            return sub
        return "runtime"
    if sec == "Model Constants" and sub == "allocation":
        return "allocation_controls"
    return sec.lower().replace(" ", "_") or "config"


def _import_tax_tables_for_choices():
    try:
        from .. import taxes as _taxes
    except Exception:  # pragma: no cover - direct execution fallback
        from src import taxes as _taxes
    return _taxes


def _pct_choice_value(rate: float) -> str:
    return f"{float(rate) * 100:.2f}%"

def _federal_bracket_choice_options(filing: str = "MFJ") -> list[dict]:
    try:
        _taxes = _import_tax_tables_for_choices()
        brackets = _taxes.FEDERAL_BRACKETS_BASE_YEAR.get(filing, _taxes.FEDERAL_BRACKETS_BASE_YEAR.get("MFJ", []))
        year = getattr(_taxes, "FEDERAL_BRACKETS_VALUE_YEAR", "base")
        out = []
        for _low, high, rate in brackets:
            if high == float("inf"):
                label = f"{int(rate * 100)}% bracket — top bracket ({year} tax table)"
            else:
                label = f"{int(rate * 100)}% bracket — top ${high:,.0f} taxable income ({filing}, {year} table)"
            out.append({"value": _pct_choice_value(rate), "label": label})
        return out
    except Exception:
        return [{"value": v, "label": v.replace(".00%", "%") + " bracket"} for v in ["10.00%","12.00%","22.00%","24.00%","32.00%","35.00%","37.00%"]]


def _irmaa_tier_choice_options(value_mode: str = "tier", filing: str = "MFJ") -> list[dict]:
    try:
        _taxes = _import_tax_tables_for_choices()
        mfj = _taxes.IRMAA_TIERS_BASE_YEAR.get("MFJ", [])
        single = _taxes.IRMAA_TIERS_BASE_YEAR.get("Single", [])
        year = getattr(_taxes, "IRMAA_TIERS_VALUE_YEAR", "base")
        out = []
        for idx, item in enumerate(mfj, start=1):
            threshold = float(item[0])
            single_threshold = float(single[idx-1][0]) if idx-1 < len(single) else threshold / 2
            value = f"TIER_{idx}" if value_mode == "tier" else str(int(threshold))
            out.append({
                "value": value,
                "label": f"Tier {idx} — MFJ ${threshold:,.0f} / Single ${single_threshold:,.0f} MAGI ({year} IRMAA table)",
            })
        return out
    except Exception:
        vals=[(1,212000,106000),(2,268000,133000),(3,335000,167000),(4,402000,200000),(5,750000,500000)]
        return [{"value": (f"TIER_{i}" if value_mode=="tier" else str(mfj)), "label": f"Tier {i} — MFJ ${mfj:,.0f} / Single ${sgl:,.0f} MAGI"} for i,mfj,sgl in vals]


def _pipe_choice_options(text: str) -> list[dict]:
    raw = str(text or "")
    if "|" not in raw:
        return []
    candidate = raw.split(";", 1)[0]
    parts = [p.strip() for p in candidate.split("|") if p.strip()]
    out=[]
    seen=set()
    for part in parts:
        key=part.lower()
        if key in seen:
            continue
        seen.add(key); out.append({"value": part, "label": part.replace("_", " ")})
    return out


def _choice_options_for_config_row(section: str, subsection: str, label: str, units: str, notes: str, spec: dict) -> list[dict]:
    lbl = (label or "").strip()
    fixed = {
        "filing_status": ["MFJ", "Single", "HOH", "MFS"],
        "survivor_filing_status": ["Single", "HOH", "MFS"],
        "net_worth_method": ["pv_through_mortality_age", "cumulative_at_death"],
        "allocation_selection_mode": ["user_target", "optimizer_recommendation"],
        "selection_action": ["include", "exclude", "consider_alternate_first"],
        "roth_conversion_policy": ["optimize_terminal_tax", "fill_to_bracket", "fill_to_irmaa", "fixed_dollar", "none"],
        "roth_bracket_strategy": ["NONE", "FILL_CURRENT_BRACKET", "FILL_TARGET_BRACKET", "PARTIAL_TARGET_BRACKET", "IRMAA_GUARDED", "SURVIVOR_TAX_AWARE", "RMD_REDUCTION", "LEGACY_TARGETED", "OPTIMIZER_CHOOSES", "FIXED_DOLLAR"],
        "roth_objective_mode": ["BALANCED_RETIREMENT", "MINIMIZE_LIFETIME_TAX", "MAXIMIZE_TERMINAL_NET_WORTH", "LEGACY_OPTIMIZED", "ESTATE_TAX_AWARE", "CUSTOM_WEIGHTED"],
        "estate_tax_objective_mode": ["OFF", "MONITOR_ONLY", "BALANCED", "STRONG"],
        "irmaa_guardrail_mode": ["IGNORE", "WARN_ONLY", "AVOID_NEXT_TIER", "AVOID_TIER_2_OR_ABOVE", "CUSTOM_MAGI_CAP"],
        "legacy_objective_mode": ["OFF", "LOW", "BALANCED", "STRONG"],
        "hsa_withdrawal_mode": ["spend_as_needed", "annual_pct", "smooth_window"],
        "core_spending_growth_mode": ["cpi", "manual_override"],
    }
    if lbl == "core_spending_growth_mode":
        return [
            {"value": "cpi", "label": "Use CPI / General Inflation"},
            {"value": "manual_override", "label": "Manual spending increase override"},
        ]
    if lbl == "mc_engine_mode":
        return [
            {"value": "quick_vectorized", "label": "Simple — Quick Vectorized (faster, approximate)"},
            {"value": "advanced_exact_scalar", "label": "Complex — Advanced Exact Scalar (slower, advisor-ready)"},
        ]
    if lbl == "roth_target_bracket_rate":
        return _federal_bracket_choice_options("MFJ")
    if lbl == "roth_irmaa_target_tier":
        return _irmaa_tier_choice_options("tier")
    if lbl in fixed:
        return [{"value": v, "label": v.replace("_", " ")} for v in fixed[lbl]]
    typ = str((spec or {}).get("type") or "").lower()
    if typ == "boolean" or str(units or "").strip().lower() in {"yes/no", "true/false", "boolean"}:
        return [{"value": "TRUE", "label": "TRUE"}, {"value": "FALSE", "label": "FALSE"}]
    if typ == "choice" or str(units or "").strip().lower() == "choice":
        return _pipe_choice_options((spec or {}).get("description", "")) or _pipe_choice_options(notes)
    return []

def _csv_rows_payload() -> dict:
    _ensure_user_ui_plan_data_rows()
    schema = _read_schema_map()
    rows = []
    for entry in _client_csv_rows():
        idx = int(entry["row_index"])
        source_idx = int(entry["source_row_index"])
        source_file = str(entry["source_file"])
        cols = list(entry["columns"])
        raw = ",".join(cols)
        while len(cols) < 6:
            cols.append("")
        section, subsection, label, value, units, notes = [str(x or "") for x in cols[:6]]
        is_header = source_idx == 0 and section.lower() == "section"
        is_comment = section.strip().startswith("#") or (not section.strip() and not label.strip())
        spec = schema.get((section.strip(), subsection.strip(), label.strip()), {})
        choice_options = _choice_options_for_config_row(section, subsection, label, units, notes, spec)
        rows.append({
            "row_index": idx,
            "source_file": source_file,
            "source_row_index": source_idx,
            "columns": cols,
            "raw": raw,
            "section": section.strip(),
            "subsection": subsection.strip(),
            "label": label.strip(),
            "value": value.strip(),
            "units": units.strip(),
            "notes": notes.strip(),
            "is_header": is_header,
            "is_comment": is_comment,
            "schema": spec,
            "choice_options": choice_options,
            "group": _classify_config_row(section, subsection, label),
        })
    return {"rows": rows, "schema_count": len(schema)}



TRAVEL_EXTRA_TYPES = [
    "Wedding",
    "Large Gifts",
    "Other",
]


def _fmt_money_for_csv(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        num = float(text.replace("$", "").replace(",", ""))
        return f"${num:,.0f}"
    except Exception:
        return text


def _normalize_date_for_csv(value: str) -> str:
    """Normalize common user-entered dates to YYYY-MM-DD for browser date fields."""
    text = str(value or "").strip()
    if not text:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text
    m = re.match(r"^(\d{4})[\/-](\d{1,2})[\/-](\d{1,2})$", text)
    if m:
        return f"{m.group(1).zfill(4)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    m = re.match(r"^(\d{1,2})[\/-](\d{1,2})[\/-](\d{2,4})$", text)
    if m:
        y = m.group(3)
        if len(y) == 2:
            y = ("19" if int(y) > 40 else "20") + y
        return f"{y.zfill(4)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
    if re.match(r"^\d{4}$", text):
        return f"{text}-01-01"
    return text


LARGE_DISCRETIONARY_SUBSECTION = "Large Discretionary Expenses"


def _is_large_discretionary_subsection(subsection: str) -> bool:
    return str(subsection or "").strip() == LARGE_DISCRETIONARY_SUBSECTION


def _normalize_large_discretionary_type(value: str) -> str:
    text = str(value or "").strip()
    low = text.lower().replace("_", " ").replace("-", " ")
    if low in {"wedding", "weddings", "children weddings", "child wedding"}:
        return "Wedding"
    if low in {"large gift", "large gifts", "major gift", "major gifts", "significant gifts"}:
        return "Large Gifts"
    # Travel and home improvement are no longer Large Discretionary types.
    if low in {"vacation", "vacations", "travel", "travel and vacations", "home projects", "home project", "home improvement", "home improvements", "capital improvements"}:
        return "Other"
    return text or "Other"


def _large_discretionary_expenses_from_csv_rows(rows: list[list[str]]) -> list[dict]:
    """Read canonical Cashflow / Large Discretionary Expenses rows for the User UI."""
    def col(row, idx, default=""):
        return (row[idx] if len(row) > idx else default) or ""

    grouped: dict[str, dict] = {}
    for row in rows[1:]:
        sec, sub, label, value, units, notes = [col(row, i) for i in range(6)]
        if sec.strip() != "Cashflow" or not _is_large_discretionary_subsection(sub):
            continue
        m = re.match(r"extra_(\d+)_(type|amount|year|start_year|end_year|comment)$", label.strip())
        if not m:
            continue
        grouped.setdefault(m.group(1), {})[m.group(2)] = value.strip()
    out = []
    for idx in sorted(grouped, key=lambda x: int(x)):
        item = grouped[idx]
        if not any(str(item.get(k, "")).strip() for k in ("type", "amount", "year", "start_year", "end_year", "comment")):
            continue
        out.append({
            "type": _normalize_large_discretionary_type(item.get("type", "Other")),
            "amount": item.get("amount", ""),
            "year": item.get("year", ""),
            "start_year": item.get("start_year", ""),
            "end_year": item.get("end_year", ""),
            "comment": item.get("comment", ""),
        })
    return out


def _large_discretionary_rows_from_plan_spending_csv() -> list[list[str]]:
    """Return canonical planned-spending rows from client_spending.csv."""
    out = [["section", "subsection", "label", "value", "units", "notes"]]
    path = _plan_data_path("client_spending.csv")
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            cols = list(row) + [""] * 6
            if str(cols[0]).strip() == "Cashflow" and _is_large_discretionary_subsection(str(cols[1])):
                out.append(cols[:6])
    return out


def _large_discretionary_expenses_from_plan_data() -> list[dict]:
    return _large_discretionary_expenses_from_csv_rows(_large_discretionary_rows_from_plan_spending_csv())


def _travel_extra_rows(events: list[dict]) -> list[list[str]]:
    rows = [
        ["", "", "", "", "", "", "", ""],
        ["# -- Large Discretionary Expenses: one-time and repeatable lifestyle/large-event spending --", "", "", "", "", "", "", ""],
    ]
    for i, event in enumerate(events, 1):
        typ = _normalize_large_discretionary_type(event.get("type") or "Other")
        amount = _fmt_money_for_csv(event.get("amount"))
        year = str(event.get("year") or "").strip()
        start = str(event.get("start_year") or "").strip()
        end = str(event.get("end_year") or "").strip()
        comment = str(event.get("comment") or "").strip()
        rows.extend([
            ["Cashflow", "Large Discretionary Expenses", f"extra_{i}_type", typ, "", "Category selected in the UI", "", ""],
            ["Cashflow", "Large Discretionary Expenses", f"extra_{i}_amount", amount, "USD", "Annual amount if repeatable; one-time amount if year is used", "", ""],
            ["Cashflow", "Large Discretionary Expenses", f"extra_{i}_year", year, "year", "Use for a one-time extra; leave blank for repeatable extras", "", ""],
            ["Cashflow", "Large Discretionary Expenses", f"extra_{i}_start_year", start, "year", "First year for repeatable extras", "", ""],
            ["Cashflow", "Large Discretionary Expenses", f"extra_{i}_end_year", end, "year", "Last year for repeatable extras", "", ""],
            ["Cashflow", "Large Discretionary Expenses", f"extra_{i}_comment", comment, "", "User note for this item", "", ""],
        ])
    rows.append(["", "", "", "", "", "", "", ""])
    return rows


def _replace_large_discretionary_expenses(events: list[dict]) -> None:
    path = _client_section_path("Cashflow", "client_spending.csv")
    if path.exists():
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    else:
        rows = [["section", "subsection", "label", "value", "units", "notes"]]
    while rows and not any(str(c).strip() for c in rows[-1]):
        rows.pop()
    indices = [i for i, r in enumerate(rows) if len(r) >= 2 and str(r[0]).strip() == "Cashflow" and _is_large_discretionary_subsection(str(r[1]))]
    insert_at = min(indices) if indices else None
    new_rows = []
    for i, r in enumerate(rows):
        if i in indices:
            continue
        if len(r) >= 1 and str(r[0]).startswith("# -- Large Discretionary Expenses"):
            continue
        new_rows.append(r)
    if insert_at is None:
        insert_at = len(new_rows)
        for i, r in enumerate(new_rows):
            if len(r) >= 2 and str(r[0]).strip() == "Cashflow" and str(r[1]).strip() == "Post-House-Sale Rent":
                insert_at = i + 1
    normalized = _travel_extra_rows(events)
    new_rows[insert_at:insert_at] = normalized
    _write_client_rows(path, new_rows)


# ---------------------------------------------------------------------------
# Spending Budget per-line table (#95): flat, addable/deletable budget lines
# stored like client_holdings.csv (on disk + client_files mirror, no YAML).
# Columns: section,line_id,label,category_id,start_year,end_year,one_time_year,
#          amount_per_year,mode,notes
# ---------------------------------------------------------------------------

SPENDING_BUDGET_LINES_FILE = "client_spending_budget_lines.csv"
SPENDING_BUDGET_LINE_COLUMNS = [
    "section", "line_id", "label", "category_id", "start_year", "end_year",
    "one_time_year", "amount_per_year", "mode", "notes",
]
# Canonical section ids surfaced on the Spending Budget page.
SPENDING_BUDGET_SECTIONS = [
    "large_discretionary", "home_improvement", "travel", "gifts_charity",
]


def _spending_budget_lines_default_csv() -> str:
    """Seed defaults from the existing extra_N rows + a Gifts/Charity summary line.

    Used by "Reload defaults" and when no on-disk/mirror file exists yet.
    """
    out = [",".join(SPENDING_BUDGET_LINE_COLUMNS)]
    events = _large_discretionary_expenses_from_plan_data()
    counters = {s: 0 for s in SPENDING_BUDGET_SECTIONS}
    prefix = {
        "large_discretionary": "ld", "home_improvement": "hi",
        "travel": "tr", "gifts_charity": "gc",
    }
    def _emit(section, label, category_id, start, end, one_time, amount, mode, notes):
        counters[section] = counters.get(section, 0) + 1
        line_id = f"{prefix.get(section, 'bl')}_{counters[section]}"
        cells = [section, line_id, label, category_id,
                 str(start or ""), str(end or ""), str(one_time or ""),
                 str(amount or ""), mode, notes]
        out.append(",".join('"%s"' % c if ("," in c or '"' in c) else c for c in cells))
    for ev in events:
        typ = _normalize_large_discretionary_type(ev.get("type") or "Other")
        low = typ.strip().lower()
        amount = str(ev.get("amount") or "").replace("$", "").replace(",", "").strip()
        one_time = str(ev.get("year") or "").strip()
        start = str(ev.get("start_year") or "").strip()
        end = str(ev.get("end_year") or "").strip()
        comment = str(ev.get("comment") or "").strip()
        if low in {"home improvement", "home improvements", "home projects", "home project"}:
            section = "home_improvement"
            category_id = "home_improvement"
        elif low in {"travel", "vacation", "vacations"}:
            section = "travel"
            category_id = "recurring_travel"
        else:
            section = "large_discretionary"
            category_id = "weddings" if low in {"wedding", "weddings"} else ""
        _emit(section, comment or typ, category_id, start, end, one_time, amount, "detail", "Seeded from large discretionary extras")
    # Gifts/Charity: seed a summary line from annual charitable giving (#94c)
    giving = ""
    try:
        content = _read_plan_data_file("client_spending.csv")
        if content:
            for r in csv.DictReader(io.StringIO(content)):
                if (str(r.get("section", "")).strip() == "Cashflow"
                        and str(r.get("subsection", "")).strip().lower() == "spending"
                        and str(r.get("label", "")).strip() == "annual_charitable_giving_high"):
                    giving = str(r.get("value", "") or "").replace("$", "").replace(",", "").strip()
                    break
    except Exception:
        giving = ""
    _emit("gifts_charity", "Charitable Giving", "charitable_donations", "", "", "", giving or "", "summary", "Seeded from annual charitable giving")
    return "\n".join(out) + "\n"


def _read_spending_budget_lines_csv() -> str:
    """Return the budget-lines CSV content (on-disk first, then SQLite mirror, then seed)."""
    content = _read_plan_data_file(SPENDING_BUDGET_LINES_FILE)
    if content is not None and content.strip():
        return content
    return _spending_budget_lines_default_csv()


def _parse_spending_budget_lines(content: str) -> list[dict]:
    rows = []
    if not content:
        return rows
    for r in csv.DictReader(io.StringIO(content)):
        section = str(r.get("section", "") or "").strip()
        if not section:
            continue
        rows.append({
            "section": section,
            "line_id": str(r.get("line_id", "") or "").strip(),
            "label": str(r.get("label", "") or "").strip(),
            "category_id": str(r.get("category_id", "") or "").strip(),
            "start_year": str(r.get("start_year", "") or "").strip(),
            "end_year": str(r.get("end_year", "") or "").strip(),
            "one_time_year": str(r.get("one_time_year", "") or "").strip(),
            "amount_per_year": str(r.get("amount_per_year", "") or "").strip(),
            "mode": (str(r.get("mode", "") or "").strip().lower() or "detail"),
            "notes": str(r.get("notes", "") or "").strip(),
        })
    return rows


def _serialize_spending_budget_lines(lines: list[dict]) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(SPENDING_BUDGET_LINE_COLUMNS)
    for i, ln in enumerate(lines, 1):
        if not isinstance(ln, dict):
            continue
        section = str(ln.get("section", "") or "").strip()
        if not section:
            continue
        amount = str(ln.get("amount_per_year", "") or "").replace("$", "").replace(",", "").strip()
        line_id = str(ln.get("line_id", "") or "").strip() or f"bl_{i}"
        mode = (str(ln.get("mode", "") or "").strip().lower() or "detail")
        w.writerow([
            section, line_id,
            str(ln.get("label", "") or "").strip(),
            str(ln.get("category_id", "") or "").strip(),
            str(ln.get("start_year", "") or "").strip(),
            str(ln.get("end_year", "") or "").strip(),
            str(ln.get("one_time_year", "") or "").strip(),
            amount, mode,
            str(ln.get("notes", "") or "").strip(),
        ])
    return out.getvalue()


def _write_spending_budget_lines(content: str) -> Path:
    """Persist budget lines to disk + SQLite client_files mirror (like holdings)."""
    return _write_plan_data_file(SPENDING_BUDGET_LINES_FILE, content)




def _pre_tax_account_options_from_holdings() -> list[str]:
    """Return pre-tax account ids that can source forced Roth conversions."""
    path = _plan_data_path("client_holdings.csv", prefer_existing=False)
    accounts = set()
    if path.exists():
        with path.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                acct = str(r.get("account") or "").strip()
                low = acct.lower()
                if acct and ("_ira" in low or "_401k" in low or "_403b" in low or "_sep" in low) and "roth" not in low:
                    accounts.add(acct)
    return sorted(accounts)


def _forced_roth_conversions_from_csv_rows(rows: list[list[str]]) -> list[dict]:
    """Read forced Roth conversions from the normalized source-account/year/amount table."""
    def col(row, idx, default=""):
        return (row[idx] if len(row) > idx else default) or ""
    grouped: dict[str, dict] = {}
    for row in rows[1:]:
        sec, sub, label, value = [col(row, i).strip() for i in range(4)]
        if sec != "Forced Actions":
            continue
        if re.match(r"^Roth Conversion \d+$", sub, re.I):
            grouped.setdefault(sub, {})[label] = value
    out=[]
    for sub in sorted(grouped, key=lambda x: int(re.search(r"\d+", x).group(0)) if re.search(r"\d+", x) else 0):
        rec=grouped[sub]
        out.append({
            "source_account": str(rec.get("source_account", "")).strip(),
            "year": str(rec.get("year", "")).strip(),
            "amount": str(rec.get("amount", "")).strip(),
        })
    return out


def _forced_roth_conversion_rows(conversions: list[dict]) -> list[list[str]]:
    rows = [["", "", "", "", "", "", "", ""], ["# -- Forced Roth Conversions: source account, year, and amount --", "", "", "", "", "", "", ""]]
    account_choices = " | ".join(_pre_tax_account_options_from_holdings()) or "Member_1_IRA | Member_2_IRA | Member_1_401k"
    for i, conv in enumerate(conversions, 1):
        acct = str(conv.get("source_account") or "").strip()
        year = str(conv.get("year") or "").strip()
        amount = _fmt_money_for_csv(conv.get("amount"))
        if not any([acct, year, amount]):
            continue
        rows.extend([
            ["Forced Actions", f"Roth Conversion {i}", "source_account", acct, "choice", f"{account_choices}; pre-tax account to convert from", "", ""],
            ["Forced Actions", f"Roth Conversion {i}", "year", year, "year", "Calendar year the forced conversion is applied", "", ""],
            ["Forced Actions", f"Roth Conversion {i}", "amount", amount, "USD", "Dollar amount to convert from the selected account to that owner’s Roth account", "", ""],
        ])
    rows.append(["", "", "", "", "", "", "", ""])
    return rows


def _replace_forced_roth_conversions(conversions: list[dict]) -> None:
    path = _client_section_path("Forced Actions", "client_policy.csv")
    rows = _ensure_header(_csv_read_rows(path))
    while rows and not any(str(c).strip() for c in rows[-1]):
        rows.pop()
    remove=set()
    for i, r in enumerate(rows):
        if not r:
            continue
        if str(r[0]).startswith("# -- Forced Roth Conversions"):
            remove.add(i)
        elif len(r) >= 1 and str(r[0]).strip() == "Forced Actions":
            remove.add(i)
    insert_at = min(remove) if remove else None
    new_rows = [r for i, r in enumerate(rows) if i not in remove]
    if insert_at is None:
        insert_at = len(new_rows)
        for i, r in enumerate(new_rows):
            if len(r) >= 1 and str(r[0]).strip() == "Scenarios":
                insert_at = i
                break
    normalized = _forced_roth_conversion_rows(conversions)
    new_rows[insert_at:insert_at] = normalized
    _write_client_rows(path, new_rows)

def _liquidity_buffers_from_csv_rows(rows: list[list[str]]) -> list[dict]:
    """Read normalized Liquidity Buffer rows."""
    def col(row, idx, default=""):
        return (row[idx] if len(row) > idx else default) or ""

    normalized: dict[str, dict] = {}
    for row in rows[1:]:
        sec, sub, label, value = [col(row, i).strip() for i in range(4)]
        if sec == "Liquidity Buffer" and re.match(r"buffer_\d+", sub):
            normalized.setdefault(sub, {})[label] = value
    if normalized:
        out = []
        for key in sorted(normalized, key=lambda x: int(re.search(r"\d+", x).group(0)) if re.search(r"\d+", x) else 0):
            rec = normalized[key]
            if any(str(rec.get(k, "")).strip() for k in ("start_year", "end_year", "years_of_expenses", "years_of_expenses_in_trust")):
                out.append({
                    "start_year": rec.get("start_year", ""),
                    "end_year": rec.get("end_year", ""),
                    "years_of_expenses": rec.get("years_of_expenses", rec.get("years_of_expenses_in_trust", "")),
                    "reserve_account": rec.get("reserve_account", rec.get("preserve_account", "Taxable/Trust")) or "Taxable/Trust",
                })
        return out

    return []


def _liquidity_buffer_rows(buffers: list[dict]) -> list[list[str]]:
    rows = [
        ["", "", "", "", "", "", "", ""],
        ["# -- Liquidity Buffer: year-ranged reserve rules --", "", "", "", "", "", "", ""],
    ]
    for i, b in enumerate(buffers, 1):
        start = str(b.get("start_year") or "").strip()
        end = str(b.get("end_year") or "").strip()
        yrs = str(b.get("years_of_expenses") or "0").strip() or "0"
        acct = str(b.get("reserve_account") or b.get("preserve_account") or "Taxable/Trust").strip() or "Taxable/Trust"
        rows.extend([
            ["Liquidity Buffer", f"buffer_{i}", "start_year", start, "year", "First year this reserve rule applies; blank means plan start", "", ""],
            ["Liquidity Buffer", f"buffer_{i}", "end_year", end, "year", "Last year this reserve rule applies; blank means open-ended", "", ""],
            ["Liquidity Buffer", f"buffer_{i}", "years_of_expenses", yrs, "years", "Years of expenses to retain as a reserve; default is 0", "", ""],
            ["Liquidity Buffer", f"buffer_{i}", "reserve_account", acct, "choice", "Taxable/Trust | Roth | IRA | HSA | Cash; account bucket intended to preserve the reserve for this row", "", ""],
        ])
    rows.append(["", "", "", "", "", "", "", ""])
    return rows


def _replace_liquidity_buffers(buffers: list[dict]) -> None:
    path = _client_section_path("Liquidity Buffer", "client_assets.csv")
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    while rows and not any(str(c).strip() for c in rows[-1]):
        rows.pop()
    indices = []
    for i, r in enumerate(rows):
        if not r:
            continue
        if str(r[0]).startswith("# -- Liquidity Buffer"):
            indices.append(i)
        elif len(r) >= 1 and str(r[0]).strip() == "Liquidity Buffer":
            indices.append(i)
    insert_at = min(indices) if indices else None
    new_rows = [r for i, r in enumerate(rows) if i not in set(indices)]
    if insert_at is None:
        insert_at = len(new_rows)
        for i, r in enumerate(new_rows):
            if len(r) >= 1 and str(r[0]).strip() == "Other Assets":
                insert_at = i + 1
    normalized = _liquidity_buffer_rows(buffers)
    new_rows[insert_at:insert_at] = normalized
    _write_client_rows(path, new_rows)

def _sync_config_backends() -> dict:
    try:
        derived = export_client_json_yaml(CSV_PATH, CSV_PATH.parent)
        db_path = import_csv_to_sqlite(CSV_PATH, _sqlite_db(), workspace_id=_workspace_id())
        return {"success": True, "derived": derived, "json": derived.get("client_data.json"), "yaml": derived.get("client_data.yaml")}
    except Exception as exc:
        return {"success": False, "error": str(exc), "trace": traceback.format_exc()}


def _permission_denied_html(message: str, permission: str):
    safe_message = html_lib.escape(str(message or "Permission denied"))
    safe_permission = html_lib.escape(str(permission or ""))
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Admin permission required</title>
<style>body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#f7f4ed;color:#1f2937;margin:0;padding:42px}}.card{{max-width:760px;margin:0 auto;background:#fff;border:1px solid #e6dcc8;border-radius:16px;padding:26px;box-shadow:0 12px 36px rgba(0,0,0,.08)}}h1{{margin-top:0;color:#7f1d1d}}code{{background:#f1eee6;border:1px solid #e6dcc8;border-radius:6px;padding:2px 6px}}a{{color:#1f4f8f;font-weight:800}}</style>
</head><body><div class="card"><h1>Admin permission required</h1><p>{safe_message}</p><p>Required permission: <code>{safe_permission}</code></p><p>This local desktop package should grant admin permissions automatically. If you see this page, restart the UI from the updated package.</p><p><a href="/">Return to client UI</a></p></div></body></html>""", 403

def _require(permission: str):
    try:
        require_permission(_current_user(), permission)
        return None
    except PermissionError as exc:
        _audit("permission_denied", {"path": request.path, "permission": permission, "error": str(exc)})
        if _html_request() and not str(request.path or "").startswith("/api/"):
            return _permission_denied_html(str(exc), permission)
        return jsonify({"success": False, "error": str(exc)}), 403


def _remote_addr_key() -> str:
    forwarded = str(request.headers.get("X-Forwarded-For", "") or "").split(",", 1)[0].strip()
    return forwarded or str(request.remote_addr or "unknown")


def _login_rate_limited(key: str) -> bool:
    now = time.time()
    attempts = _LOGIN_ATTEMPTS[key]
    while attempts and now - attempts[0] > _LOGIN_WINDOW_SECONDS:
        attempts.popleft()
    return len(attempts) >= _LOGIN_MAX_FAILURES


def _record_login_failure(key: str) -> None:
    attempts = _LOGIN_ATTEMPTS[key]
    attempts.append(time.time())


def _clear_login_failures(key: str) -> None:
    _LOGIN_ATTEMPTS.pop(key, None)


@app.before_request
def _security_gate():
    if request.method == "OPTIONS":
        return None
    cfg = _runtime_config()
    if cfg.force_https and not request.is_secure and str(request.headers.get("X-Forwarded-Proto", "")).lower() != "https":
        if request.method in {"GET", "HEAD"} and not request.path.startswith("/api/"):
            target = request.url.replace("http://", "https://", 1)
            return redirect(target, code=302)
        return jsonify({"success": False, "error": "HTTPS is required"}), 426
    if _public_path():
        return None
    if cfg.is_saas:
        try:
            require_secure_master_key(cfg.app_mode)
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500
    ok, identity = _authorized_and_identity()
    if cfg.is_saas and not ok:
        _audit("request_denied", {"path": request.path, "reason": "missing_or_invalid_token"})
        if _html_request() and not request.path.startswith("/api/"):
            return redirect("/login?next=" + request.path, code=302)
        return jsonify({"success": False, "error": "Unauthorized", "login_url": "/login"}), 401
    if identity:
        g.user_context = identity
    # Local-only package: no cookie-authenticated public-hosting mode remains.
    # API clients using Authorization/X-API-Token are not browser-cookie based and
    # remain compatible with automation scripts.


@app.after_request
def _local_cors(response):
    # Allow the local static UI opened via file:// or /frontend to call the local API.
    # Local UI is served from the same origin; avoid broad CORS by default.
    try:
        cfg = _runtime_config()
        if not cfg.is_saas:
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-API-Token, X-User-Id, X-User-Email, X-User-Role, X-Workspace-Id, X-Client-Id"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        else:
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("Referrer-Policy", "same-origin")
            response.headers.setdefault("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
            if request.is_secure or str(request.headers.get("X-Forwarded-Proto", "")).lower() == "https":
                response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    except Exception:
        pass
    return response


# Export private helper names to route modules using star imports.
__all__ = [name for name in globals() if not name.startswith("__")]

