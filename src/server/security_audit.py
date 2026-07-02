from __future__ import annotations
"""Local auth-identity and audit-logging helpers.

Extracted from app_core.py (see documentation/SYSTEM_REVIEW_AND_REFACTOR_PLAN.md
Phase 2 "Gap 2"). These two clusters were originally investigated as separate
extraction candidates, but a call-graph pass showed bidirectional coupling
(`_security_gate`/`_require` call `_audit`; `_audit`/`_record_admin_config_change`
call `_current_user`), so they are combined into one module to avoid a
circular import between two new files.

Imports `app_core` as a module (not specific names), matching the pattern
already used by csv_migration.py and by
src/projection_stages/deterministic_engine.py for planning_engines.py: this
file is itself imported back into app_core.py (`from .security_audit import
*`), so any direct `from .app_core import X` here would deadlock at import
time. Names referenced via `_app_core.X` are only ever resolved inside
function bodies (at call time, once both modules have finished loading).

`_security_gate` (the `@app.before_request` hook) and `_local_cors` (the
`@app.after_request` hook) deliberately stay in app_core.py rather than
moving here: both are decorator-registered against the `app` object at
import time, and moving them would add import-order risk to the single most
security-critical code path in the server for no maintainability benefit.
"""

import json
import time
from pathlib import Path

try:
    from ..http_runtime.wsgi_facade import request
    from ..security import constant_time_token_ok, extract_bearer_or_header, get_server_token, redact_text
    from ..permissions import UserContext
    from ..workspace_context import sanitize_id, workspace_output_dir
    from ..config_backend import append_audit_event_sqlite, lookup_api_token
except Exception:  # direct execution fallback
    from src.http_runtime.wsgi_facade import request
    from src.security import constant_time_token_ok, extract_bearer_or_header, get_server_token, redact_text
    from src.permissions import UserContext
    from src.workspace_context import sanitize_id, workspace_output_dir
    from src.config_backend import append_audit_event_sqlite, lookup_api_token

from . import app_core as _app_core


def _bootstrap_workspace() -> str:
    return "local"


def _bootstrap_client() -> str:
    return "local"


def _candidate_token() -> str:
    header_token = extract_bearer_or_header(request.headers)
    if header_token:
        return header_token
    cfg = _app_core._runtime_config()
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
    cfg = _app_core._runtime_config()
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
    cfg = _app_core._runtime_config()
    response.delete_cookie(cfg.session_cookie_name)
    return response


def _identity_from_token(token: str) -> tuple[bool, UserContext | None]:
    if not token:
        return False, None
    cfg = _app_core._runtime_config()
    token_row = lookup_api_token(token, _app_core._sqlite_db())
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
    out = workspace_output_dir(_workspace_id(), _app_core.BASE_DIR)
    out.mkdir(parents=True, exist_ok=True)
    return out


def _audit(event: str, details: dict | None = None) -> None:
    cfg = _app_core._runtime_config()
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
            append_audit_event_sqlite(event, details, workspace_id=user.workspace_id, user_id=user.user_id, db_path=_app_core._sqlite_db())
        except Exception:
            pass


def _admin_change_log_path_for(workspace_id: str | None = None) -> Path:
    """Local admin/config change log used by Build Impact."""
    tid = sanitize_id(workspace_id or _workspace_id())
    out = workspace_output_dir(tid, _app_core.BASE_DIR)
    out.mkdir(parents=True, exist_ok=True)
    return out / "admin_config_change_log.json"


def _last_build_metadata_path_for(workspace_id: str | None = None) -> Path:
    tid = sanitize_id(workspace_id or _workspace_id())
    out = workspace_output_dir(tid, _app_core.BASE_DIR)
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


# Python's default `from X import *` skips underscore-prefixed names; every
# function here is underscore-prefixed by this codebase's convention, and
# app_core.py needs all of them via `from .security_audit import *` to
# preserve its own `from .app_core import *` contract with plan_routes.py /
# workbook_routes.py / admin_routes.py / base_routes.py unchanged. Matches
# the same override app_core.py itself uses at its own end.
__all__ = [name for name in globals() if not name.startswith("__")]
