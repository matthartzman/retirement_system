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
except ImportError:  # direct file loading fallback
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
except ImportError:  # direct execution fallback
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
except ImportError:
    from src import allocation_policy as allocation_policy_mod

try:
    from .. import plan_data_backfill
except ImportError:
    from src import plan_data_backfill

try:
    from .. import platform_runtime
except ImportError:  # direct execution fallback
    from src import platform_runtime

# BASE_DIR is the code/package root: reference_data/, frontend static assets,
# system_config.csv, and tools/build_workbook.py live here. WORKSPACE_ROOT is
# where writable data (input/, output/, local_state/, saved_plans/) lives — the
# same directory on desktop, app-private storage on mobile.
BASE_DIR = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = platform_runtime.workspace_root()
DEFAULT_CSV_PATH = WORKSPACE_ROOT / "input" / "client_data.csv"
SCHEMA_PATH = BASE_DIR / "reference_data" / "schema.csv"
BUILD_SCRIPT = BASE_DIR / "tools" / "build_workbook.py"
app = Flask(__name__, static_folder=str(BASE_DIR))
RUNTIME_CONFIG = load_runtime_config()
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
    return p if p.is_absolute() else WORKSPACE_ROOT / p

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
    return p if p.is_absolute() else WORKSPACE_ROOT / p



# Cache key -> (source mtime_ns, source size) for the last-written target,
# so a request doesn't re-parse/rewrite system_config.active.csv when the
# source system_config.csv hasn't changed since the previous request.
_REQUEST_SYSTEM_CONFIG_CSV_CACHE: dict[str, tuple[int, int]] = {}


def _request_system_config_csv() -> Path:
    """Create a per-request system_config.csv copy for subprocess builds/tools.

    The transform below is deterministic given the source file's content (it
    always sets the same runtime path values), so a request can safely reuse
    the target written by a previous request as long as the source hasn't
    changed and the target still exists.
    """
    source = _system_config_path()
    target = _workspace_output() / "system_config.active.csv"

    source_fingerprint = None
    if source.exists():
        stat = source.stat()
        source_fingerprint = (stat.st_mtime_ns, stat.st_size)
        cache_key = str(target)
        if (
            source_fingerprint is not None
            and _REQUEST_SYSTEM_CONFIG_CSV_CACHE.get(cache_key) == source_fingerprint
            and target.exists()
        ):
            return target

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
    if source_fingerprint is not None:
        _REQUEST_SYSTEM_CONFIG_CSV_CACHE[str(target)] = source_fingerprint
    else:
        _REQUEST_SYSTEM_CONFIG_CSV_CACHE.pop(str(target), None)
    return target


# Local auth-identity helpers (_bootstrap_workspace, _bootstrap_client,
# _candidate_token, _html_request, _public_path, _has_bearer_or_api_header,
# _cookie_secure_for_request, _set_auth_cookie, _clear_auth_cookie,
# _identity_from_token, _authorized_and_identity, _current_user,
# _workspace_id, _client_id, _workspace_output) and audit-log helpers
# (_audit, _admin_change_log_path_for, _last_build_metadata_path_for,
# _row_key_for_change, _summarize_csv_row_changes, _record_admin_config_change,
# _admin_changes_between, _read_last_build_timestamp,
# _write_last_build_metadata) now live in security_audit.py, combined into
# one file due to bidirectional call coupling between the two clusters.
try:
    from .security_audit import *  # noqa: F401,F403
except ImportError:
    from src.server.security_audit import *  # noqa: F401,F403


def _spending_budget_csv_path() -> Path:
    return BASE_DIR / "input" / "client_spending_budget.csv"


def _read_csv_rows_safe(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.reader(f))


def _spending_budget_save_result(save_fn):
    """Run a budget-save call and record the before/after diff to Build Impact."""
    budget_path = _spending_budget_csv_path()
    before_rows = _read_csv_rows_safe(budget_path)
    payload, status = save_fn()
    after_rows = _read_csv_rows_safe(budget_path)
    change_event = _record_admin_config_change("spending_budget", budget_path.name, str(budget_path), before_rows, after_rows)
    if isinstance(payload, dict) and change_event:
        payload["change_event"] = change_event
    return jsonify(payload), status




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
    source_dir = WORKSPACE_ROOT / "input"
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
    return workspace_file(name, _workspace_id(), WORKSPACE_ROOT, prefer_existing=prefer_existing)



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
    # The SQLite plan store is the canonical source of truth for Plan Data. Read
    # it first. The on-disk input/*.csv are import/export mirrors, used only to
    # bootstrap the DB on a fresh checkout / first run / folder import — when we
    # read a CSV for that reason we lazily seed the DB so subsequent reads are
    # DB-canonical. client_data.csv is the sectioned anchor and is not stored in
    # the DB (it is always materialized on disk).
    if name != "client_data.csv":
        content = get_client_file(name, _workspace_id(), _client_id(), _sqlite_db())
        if content is not None:
            return content
    path = _plan_data_path(name, prefer_existing=True)
    if path.exists():
        csv_content = path.read_text(encoding="utf-8-sig")
        if name != "client_data.csv":
            try:
                set_client_file(name, csv_content, _workspace_id(), _client_id(), _current_user().user_id, _sqlite_db())
            except Exception as exc:
                _audit("plan_data_db_bootstrap_warning", {"file": name, "error": str(exc)})
        return csv_content
    return None


def _write_plan_data_file(file_name: str, content: str, *, preserve_protected: bool = True) -> Path:
    name = _normalize_plan_data_file_name(file_name)
    path = _plan_data_path(name, prefer_existing=False)
    if name in CLIENT_DATA_CSV_FILE_SET:
        content = canonicalize_roth_csv_content(content)
    if preserve_protected and name in CLIENT_DATA_CSV_FILE_SET and path.exists():
        try:
            content = _merge_protected_client_data_values(content, path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            _audit("protected_client_data_merge_warning", {"file": name, "error": str(exc)})
    # The SQLite plan store is canonical: write it first, authoritatively. The
    # on-disk CSV is then written as an import/export mirror (folder
    # download/portability; the build materializes plan data from the DB).
    # client_data.csv is the sectioned anchor and is not stored in the DB.
    if name != "client_data.csv":
        try:
            set_client_file(name, content, _workspace_id(), _client_id(), _current_user().user_id, _sqlite_db())
        except Exception as exc:
            _audit("plan_data_db_write_warning", {"file": name, "error": str(exc)})
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    return path





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


SSA44_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Model Constants", "IRMAA", "h_ssa44_relief_year", "", "year", "First year Member 1's IRMAA surcharge is suppressed following an approved Form SSA-44 life-changing-event appeal. Blank = none filed. Base Part B/D/G premiums are still owed; only the surcharge is relieved. An appeal outcome is granted case-by-case and is never guaranteed — enter this only for an appeal already approved."],
    ["Model Constants", "IRMAA", "w_ssa44_relief_year", "", "year", "First year Member 2's IRMAA surcharge is suppressed following an approved Form SSA-44 life-changing-event appeal. Blank = none filed. Base Part B/D/G premiums are still owed; only the surcharge is relieved. An appeal outcome is granted case-by-case and is never guaranteed — enter this only for an appeal already approved."],
]
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

SS_FRA_AGE_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Social Security", "Member 1", "fra_age", "0", "number", "Full Retirement Age (SSA), in years, e.g. 66.67 for 66 years 8 months. 0 auto-derives from date of birth (67 for birth year 1960 or later); otherwise enter 60-70."],
    ["Social Security", "Member 2", "fra_age", "0", "number", "Full Retirement Age (SSA), in years, e.g. 66.67 for 66 years 8 months. 0 auto-derives from date of birth (67 for birth year 1960 or later); otherwise enter 60-70."],
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
    ["Asset Allocation Policy", "Global", "allocation_selection_mode", "user_target", "choice", "user_target | optimizer_recommendation | max_sharpe | tangency | real_loss_aware; Choose whether the plan uses user-specified target_pct allocation rows, the risk-tolerance-driven optimizer/max-Sharpe recommendation, the unconstrained tangency portfolio, or the holding-period real-loss-aware blend."],
    ["Asset Allocation Policy", "Global", "holding_period_allocation_enabled", "NO", "yes/no", "Off by default. When YES, the optimizer/max-Sharpe recommendation modes nudge near-term (0-2yr) withdrawal-derived balance toward Cash and durable (16+yr) balance toward growth classes, using this household's own projected withdrawal schedule. Has no effect on user_target or tangency modes; selecting allocation_selection_mode=real_loss_aware enables the same discovery automatically."],
    ["Asset Allocation Policy", "Global", "holding_period_floor_strength", "100%", "percent", "Only used when holding_period_allocation_enabled is YES. Scales how strongly the near-term/long-horizon floors are applied; 100% applies the full floor, 0% disables it without turning the feature off."],
    ["Asset Allocation Policy", "Global", "real_loss_aware_risk_aversion", "3.0", "decimal", "Only used when allocation_selection_mode is real_loss_aware. Mean-variance risk-aversion coefficient for each holding-period bucket's solve."],
    ["Asset Allocation Policy", "Global", "real_loss_aware_weight", "1.0", "decimal", "Only used when allocation_selection_mode is real_loss_aware. Scales the added real-loss-probability penalty relative to variance in each holding-period bucket's solve; higher values weight the real-loss curves more heavily versus expected return/variance."],
    ["Asset Class Assumptions", "Global", "capital_market_assumption_horizon_years", "30", "choice", "Supported values: 1|3|5|10|20|25|30. Planning horizon for allocation optimizer assumptions. Ignored when capital_market_assumption_horizon_source is auto_from_withdrawals."],
    ["Asset Class Assumptions", "Global", "capital_market_assumption_horizon_source", "manual", "choice", "manual (default) uses the horizon above. auto_from_withdrawals derives the effective horizon from this household's own projected withdrawal schedule instead."],
    ["Asset Class Assumptions", "Global", "capital_market_assumption_preset", "BASELINE", "choice", "CONSERVATIVE, BASELINE, or AGGRESSIVE. Shifts return/volatility assumptions before per-asset overrides."],
]

CORE_SPENDING_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Cashflow", "Spending", "core_spending_growth_mode", "cpi", "choice", "cpi | manual_override; Choose whether core spending increases with general CPI or a manual spending-specific rate."],
    ["Cashflow", "Spending", "core_spending_manual_growth_rate", "0.00%", "percent", "Annual core-spending increase used only when core_spending_growth_mode is manual_override."],
]

MORTGAGE_RE_TAX_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Cashflow", "Mortgage", "annual_real_estate_taxes", "0", "USD", "Annual real-estate/property tax cash-flow amount; shown with Mortgage and RE Tax instead of core spending."],
    ["Cashflow", "Mortgage", "real_estate_tax_annual_adjustment_pct", "2.50%", "percent", "Annual percentage adjustment applied to real-estate/property taxes in the cash-flow forecast."],
]

QCD_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Cashflow", "Charitable Giving", "qcd_enabled", "FALSE", "bool", "Enable Qualified Charitable Distributions: each member's own IRA can send money straight to charity, excluded from AGI, once age 70 1/2-eligible."],
    ["Cashflow", "Charitable Giving", "h_qcd_annual_amount", "$0", "USD", "Member 1's annual QCD amount. Capped at that year's own RMD (phase-1 scope) and at the statutory per-person QCD limit."],
    ["Cashflow", "Charitable Giving", "w_qcd_annual_amount", "$0", "USD", "Member 2's annual QCD amount. Capped at that year's own RMD (phase-1 scope) and at the statutory per-person QCD limit."],
    ["Cashflow", "Charitable Giving", "h_qcd_start_year", "", "year", "Optional override for the first year Member 1's QCD applies. Blank = the year they turn age 70 1/2-eligible."],
    ["Cashflow", "Charitable Giving", "h_qcd_end_year", "", "year", "Optional last year Member 1's QCD applies. Blank = continues through plan end."],
    ["Cashflow", "Charitable Giving", "w_qcd_start_year", "", "year", "Optional override for the first year Member 2's QCD applies. Blank = the year they turn age 70 1/2-eligible."],
    ["Cashflow", "Charitable Giving", "w_qcd_end_year", "", "year", "Optional last year Member 2's QCD applies. Blank = continues through plan end."],
]

DAF_APPRECIATED_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["DAF", "Settings", "contribution_is_appreciated", "FALSE", "bool", "TRUE if the DAF contribution is appreciated securities rather than cash: limits the year's deductible amount to 30% of AGI instead of 60%, with any excess carried forward up to 5 years."],
]

TLH_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Withdrawal Policy", "Tax-Loss Harvesting", "tlh_policy", "off", "choice",
     "off | analyze_only | apply. off ignores tax-loss harvesting. analyze_only surfaces opportunities on the Tax-Loss Harvesting sheet without changing the projection. apply harvests qualifying loss lots each year inside the projection so terminal net worth and lifetime tax reflect the strategy."],
    ["Withdrawal Policy", "Tax-Loss Harvesting", "tlh_min_loss_dollars", "$500", "USD",
     "Minimum dollar loss on a lot before it is worth harvesting (avoids trivial trades)."],
    ["Withdrawal Policy", "Tax-Loss Harvesting", "tlh_min_loss_pct", "5.00%", "percent",
     "Minimum loss as a percentage of the lot's cost basis before harvesting (avoids near-breakeven lots)."],
    ["Withdrawal Policy", "Tax-Loss Harvesting", "tlh_annual_ceiling", "$0", "USD",
     "Maximum harvested loss per year (0 = unlimited)."],
    ["Withdrawal Policy", "Tax-Loss Harvesting", "tlh_transaction_cost_bps", "2", "number",
     "Round-trip trading cost, in basis points (hundredths of a percent) of harvested market value — not a dollar amount. 2 bps = 0.02%; 100 bps = 1%. A typical low-cost brokerage trade is 0-5 bps."],
    ["Withdrawal Policy", "Tax-Loss Harvesting", "tlh_fraction_sold_before_death", "50.00%", "percent",
     "Fraction of the lower-basis replacement expected to be sold (and its larger gain taxed) before basis step-up at death. Lower values make harvesting more permanently valuable."],
]

# A7: PLAN_DATA_BACKFILL_ENTRIES replaces twelve near-identical
# _ensure_*_ui_plan_data_rows functions (each: read a CSV, compute missing
# canonical rows, find an insertion point, splice, write back) with one
# declarative table over plan_data_backfill.apply_backfill's batched engine.
# Order matches the original _ensure_user_ui_plan_data_rows call sequence,
# since entries sharing a file are applied in list order against the same
# growing in-memory rows (see apply_backfill's docstring) - reordering this
# list can change which anchor a later same-file entry sees.
PLAN_DATA_BACKFILL_ENTRIES: list[plan_data_backfill.BackfillEntry] = [
    plan_data_backfill.BackfillEntry(
        "client_policy.csv", ALLOCATION_UI_PLAN_DATA_ROWS,
        plan_data_backfill.insert_before(plan_data_backfill.section_is(
            "Asset Class Optimizer Controls", "Withdrawal Policy", "Model Constants", "Forced Actions", "Scenarios")),
    ),
    plan_data_backfill.BackfillEntry(
        "client_policy.csv", MONTE_CARLO_UI_PLAN_DATA_ROWS,
        plan_data_backfill.insert_before(lambda row: (
            (str(row[0] if row else "").strip() == "Model Constants"
             and str(row[1] if len(row) > 1 else "").strip() in {"Roth Conversion", "IRMAA"})
            or str(row[0] if row else "").strip() in {"Withdrawal Policy", "Forced Actions", "Scenarios"}
        )),
    ),
    plan_data_backfill.BackfillEntry(
        "client_policy.csv", ROTH_UI_PLAN_DATA_ROWS,
        plan_data_backfill.insert_before(plan_data_backfill.section_is("Forced Actions", "Scenarios")),
    ),
    plan_data_backfill.BackfillEntry(
        "client_policy.csv", SSA44_UI_PLAN_DATA_ROWS,
        plan_data_backfill.insert_before(plan_data_backfill.section_is("Forced Actions", "Scenarios")),
    ),
    plan_data_backfill.BackfillEntry(
        "client_assets.csv", HSA_WITHDRAWAL_UI_PLAN_DATA_ROWS,
        plan_data_backfill.insert_before(plan_data_backfill.section_is(
            "Education Funding", "Equity Compensation", "Note Receivable", "Hybrid LTC")),
    ),
    plan_data_backfill.BackfillEntry(
        "client_income.csv", SOCIAL_SECURITY_FUNDING_UI_PLAN_DATA_ROWS,
        plan_data_backfill.insert_before(plan_data_backfill.section_is("Income Streams")),
    ),
    plan_data_backfill.BackfillEntry(
        "client_household.csv", SS_FRA_AGE_UI_PLAN_DATA_ROWS,
        plan_data_backfill.insert_before(lambda row: (
            str(row[0] if row else "").strip() == "Social Security"
            and str(row[2] if len(row) > 2 else "").strip() == "spousal_benefits_enabled"
        )),
    ),
    plan_data_backfill.BackfillEntry(
        "client_household.csv", HEALTHCARE_UI_PLAN_DATA_ROWS,
        plan_data_backfill.insert_before(plan_data_backfill.section_subsection_is("Wellness", "Out-of-Pocket")),
    ),
    plan_data_backfill.BackfillEntry(
        "client_policy.csv", HELOC_UI_PLAN_DATA_ROWS,
        plan_data_backfill.insert_before(plan_data_backfill.section_is("Withdrawal Policy", "Model Constants", "Scenarios")),
    ),
    plan_data_backfill.BackfillEntry(
        "client_spending.csv", CORE_SPENDING_UI_PLAN_DATA_ROWS,
        plan_data_backfill.insert_after_last(plan_data_backfill.section_subsection_is("Cashflow", "Spending")),
    ),
    plan_data_backfill.BackfillEntry(
        "client_spending.csv", MORTGAGE_RE_TAX_UI_PLAN_DATA_ROWS,
        plan_data_backfill.insert_after_last(plan_data_backfill.section_subsection_is("Cashflow", "Mortgage")),
    ),
    plan_data_backfill.BackfillEntry(
        "client_spending.csv", QCD_UI_PLAN_DATA_ROWS,
        plan_data_backfill.insert_after_last(plan_data_backfill.section_subsection_is("Cashflow", "Spending")),
    ),
    plan_data_backfill.BackfillEntry(
        "client_assets.csv", DAF_APPRECIATED_UI_PLAN_DATA_ROWS,
        plan_data_backfill.insert_after_last(plan_data_backfill.section_subsection_is("DAF", "Settings")),
    ),
    plan_data_backfill.BackfillEntry(
        "client_household.csv",
        [["Economic Assumptions", "", "inflation_general", "2.50%", "pct", "General CPI inflation used when core_spending_growth_mode is cpi."]],
        plan_data_backfill.insert_after_last(plan_data_backfill.section_subsection_is("Economic Assumptions", "")),
    ),
    plan_data_backfill.BackfillEntry(
        "client_policy.csv",
        [["Model Constants", "Retirement", "spending_freeze_year", "2040", "year", "Year after which core spending stops increasing; grouped with Spending / Core spending in the User UI."]],
        plan_data_backfill.insert_after_last(plan_data_backfill.section_subsection_is("Model Constants", "Retirement")),
    ),
    plan_data_backfill.BackfillEntry(
        "client_household.csv",
        [["Economic Assumptions", "", "reinvest_dividends_default", "NO", "yes/no",
          "Global switch: reinvest every investment account's dividends/interest into the same holding instead of letting them convert to cash inside the account. When YES, this applies to every investment account and the per-account overrides below are ignored."]],
        plan_data_backfill.insert_after_last(plan_data_backfill.section_subsection_is("Economic Assumptions", "")),
    ),
    plan_data_backfill.BackfillEntry(
        "client_household.csv",
        [["Economic Assumptions", "", "cash_yield_rate", "2.00%", "pct",
          "Growth rate applied to dividends/interest that convert to cash inside an account (Reinvest Dividends = NO) instead of compounding with the rest of the holding."]],
        plan_data_backfill.insert_after_last(plan_data_backfill.section_subsection_is("Economic Assumptions", "")),
    ),
    plan_data_backfill.BackfillEntry(
        "client_policy.csv",
        lambda target_dir: [
            ["Account Policy", acct, "reinvest_dividends", "", "yes/no",
             "Per-account override of Economic Assumptions/reinvest_dividends_default. Leave blank to inherit the global switch. Ignored while the global switch is YES."]
            for acct in _investment_account_ids_from_holdings(target_dir)
        ],
        plan_data_backfill.insert_before(plan_data_backfill.section_is("HELOC")),
    ),
    plan_data_backfill.BackfillEntry(
        "client_policy.csv", TLH_UI_PLAN_DATA_ROWS,
        plan_data_backfill.insert_after_last(plan_data_backfill.section_subsection_is("Withdrawal Policy", "Identity")),
    ),
]


def _ensure_user_ui_plan_data_rows() -> None:
    """Materialize forward-schema rows that the guided User UI depends on.

    Folder imports and browser saves can bring in valid model inputs that lack
    newer UI control rows. The UI should never hide a new control merely because
    the imported folder predates that control. This function writes canonical
    current-schema rows only; it does not read previous-name aliases.

    A7: delegates to plan_data_backfill.apply_backfill against this process's
    real Plan Data directory (CSV_PATH.parent - the same directory every
    _plan_data_path(name, prefer_existing=False) call below used to resolve
    to for these files). No pytest guard: the engine only ever touches
    target_dir/file_name, so a test passing a tmp_path never reaches the live
    input/ directory - the guard existed only because the old per-function
    implementation resolved that path itself.
    """
    plan_data_backfill.apply_backfill(CSV_PATH.parent, PLAN_DATA_BACKFILL_ENTRIES)





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
    except ImportError:  # pragma: no cover - direct execution fallback
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


def _investment_account_ids_from_holdings(holdings_dir: Path | None = None) -> list[str]:
    """Return every investment account id that carries dividend/interest yield
    assumptions: taxable/Trust, IRA, 401k, Roth, and HSA (mirrors invest_ids
    in src/core.py — everything except checking/cash and 529 accounts, which
    aren't retirement/brokerage holdings).

    ``holdings_dir``: read client_holdings.csv from this directory instead of
    resolving it via _plan_data_path (A7 - lets the dividend-reinvestment
    backfill entry read from the same target_dir it writes into, rather than
    a second, independently-resolved path). Defaults to the live workspace
    for any other caller.
    """
    path = (holdings_dir / "client_holdings.csv") if holdings_dir is not None else _plan_data_path("client_holdings.csv", prefer_existing=False)
    accounts = set()
    excluded_tokens = ("_checking", "_529")
    if path.exists():
        with path.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                acct = str(r.get("account") or "").strip()
                if not acct:
                    continue
                low = acct.lower()
                if any(tok in low for tok in excluded_tokens):
                    continue
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

