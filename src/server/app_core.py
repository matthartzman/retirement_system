from __future__ import annotations
"""Version v11 local-only stdlib dashboard and API.

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
from contextlib import contextmanager
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
    from ..secrets_store import encryption_status, set_secret  # require_secure_master_key: system review 4.5, its one call site (SaaS-only) removed
    from ..workspace_context import sanitize_id, workspace_file, workspace_output_dir
    from ..blank_plan import blank_plan_rows
    from ..roth_ui_build_guard import normalize_roth_csv_value
    from ..us_states import state_abbr_choice_options, state_name_choice_options
    from ..plan_file_io import atomic_write, plan_file_lock, write_text_atomic
    from .plan_data_files import (
        PLAN_DATA_CSV_FILES,
        PLAN_DATA_FILES,
        PLAN_DATA_FILE_SET,
        RETIRED_PLAN_PART_FILES,
        SYSTEM_REFERENCE_FILES,
        UI_NAMES,
        YTD_PLAN_DATA_FILES,
    )
    from ..active_plan import PROTECTED_PLAN_KEYS, active_plan_store, edit_active_plan, peek_plan_data
    from ..config_backend import (
        DEFAULT_DB,
        append_audit_event_sqlite,
        get_client,
        get_client_file,
        init_sqlite,
        load_active_config,
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
    from src.secrets_store import encryption_status, set_secret
    from src.workspace_context import sanitize_id, workspace_file, workspace_output_dir
    from src.blank_plan import blank_plan_rows
    from src.roth_ui_build_guard import normalize_roth_csv_value
    from src.plan_file_io import atomic_write, plan_file_lock, write_text_atomic
    from src.us_states import state_abbr_choice_options, state_name_choice_options
    from src.server.plan_data_files import (
        PLAN_DATA_CSV_FILES,
        PLAN_DATA_FILES,
        PLAN_DATA_FILE_SET,
        RETIRED_PLAN_PART_FILES,
        SYSTEM_REFERENCE_FILES,
        UI_NAMES,
        YTD_PLAN_DATA_FILES,
    )
    from src.active_plan import PROTECTED_PLAN_KEYS, active_plan_store, edit_active_plan, peek_plan_data
    from src.config_backend import (
        DEFAULT_DB,
        append_audit_event_sqlite,
        get_client,
        get_client_file,
        init_sqlite,
        load_active_config,
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
    from ..plan_data_registry import RetiredPlanDataFile
except ImportError:
    from src import plan_data_backfill
    from src.plan_data_registry import RetiredPlanDataFile

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




def _runtime_config():
    try:
        return load_runtime_config()
    except Exception:
        return RUNTIME_CONFIG


def _sqlite_db() -> Path:
    # Deliberately calls platform_runtime.workspace_root() fresh on every call rather than the
    # module-level WORKSPACE_ROOT constant (frozen at this module's own import time): a caller
    # that redirects the workspace AFTER app_core has already been imported (e.g.
    # tests/conftest.py's RETIREMENT_SYSTEM_WORKSPACE_ROOT isolation) would otherwise resolve
    # against the stale, pre-redirect workspace while config_backend.resolve_path() (also a
    # fresh call) resolves against the current one.
    cfg = _runtime_config()
    p = Path(cfg.sqlite_db or DEFAULT_DB)
    return p if p.is_absolute() else platform_runtime.workspace_root() / p



# Cache key -> (source mtime_ns, source size) for the last-written target,
# so a request doesn't re-parse/rewrite system_config.active.csv when the
# source system_config.csv hasn't changed since the previous request.
_REQUEST_SYSTEM_CONFIG_CSV_CACHE: dict[str, tuple[int, int]] = {}


def _request_system_config_csv() -> Path:
    """Create a per-request system_config.csv copy for subprocess builds/tools.

    The copy is deterministic given the source file's content, so a request can safely
    reuse the target written by a previous request as long as the source hasn't changed
    and the target still exists.
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

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)
    if source_fingerprint is not None:
        _REQUEST_SYSTEM_CONFIG_CSV_CACHE[str(target)] = source_fingerprint
    else:
        _REQUEST_SYSTEM_CONFIG_CSV_CACHE.pop(str(target), None)
    return target


# Local auth-identity helpers and audit-log helpers live in security_audit.py,
# combined into one file due to bidirectional call coupling between the two
# clusters (see that file's own top-of-file comment). Several more names are
# defined there too (_bootstrap_workspace, _bootstrap_client,
# _candidate_token, _admin_change_log_path_for, _last_build_metadata_path_for,
# _row_key_for_change, _summarize_csv_row_changes) but are used only internally within
# security_audit.py's own functions -- never re-exported here, since nothing
# outside that file needs them (system review 4.9, verified via AST analysis
# of every name app_core.py/admin_routes.py/base_routes.py/workbook_routes.py/
# plan_routes.py actually load that isn't locally defined or otherwise
# imported). _has_bearer_or_api_header used to be in that unused bucket too
# (ARC-010, same review) until ARC-001's CSRF/Origin gate below started using
# it to exempt bearer/API-token clients, which are not cookie-auto-attached
# and so are not CSRF targets.
try:
    from .security_audit import (
        _admin_changes_between,
        _audit,
        _bootstrap_workspace,
        _authorized_and_identity,
        _client_id,
        _csrf_token_for_current_request,
        _current_user,
        _has_bearer_or_api_header,
        _html_request,
        _public_path,
        _read_last_build_timestamp,
        _record_admin_config_change,
        _workspace_id,
        _workspace_output,
        _write_last_build_metadata,
    )
except ImportError:
    from src.server.security_audit import (
        _admin_changes_between,
        _audit,
        _bootstrap_workspace,
        _authorized_and_identity,
        _client_id,
        _csrf_token_for_current_request,
        _current_user,
        _has_bearer_or_api_header,
        _html_request,
        _public_path,
        _read_last_build_timestamp,
        _record_admin_config_change,
        _workspace_id,
        _workspace_output,
        _write_last_build_metadata,
    )


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

    workspace = "local"
    client = "local"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)
    return target

def _normalize_plan_data_file_name(file_name: str) -> str:
    name = Path(str(file_name or "")).name
    if name in RETIRED_PLAN_PART_FILES:
        raise RetiredPlanDataFile(
            "The plan data is stored in the plan file, not in CSV, JSON or YAML files. "
            "Import and export of plan CSV files returns with the CSV import/export feature.")
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
    with atomic_write(path) as f:
        csv.writer(f, lineterminator="\n").writerows(rows)

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


def _blank_hsa_schedule_csv(content: str) -> str:
    rows = list(csv.reader(io.StringIO(content or "")))
    header = rows[0] if rows else ["year", "optimizer_amount", "override_amount", "locked", "note"]
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerow(header)
    return out.getvalue()


def _make_blank_plan_files() -> dict[str, str]:
    """The flat datasets a new plan starts empty (holdings, liabilities, HSA schedule), from the
    workspace's current files (their header is kept). The sectioned plan rows are blanked by
    ``blank_plan.blank_plan_rows``; every other flat file is left as it is."""
    source_dir = WORKSPACE_ROOT / "input"
    blankers = {
        "client_holdings.csv": _blank_holdings_csv,
        "client_liabilities.csv": _blank_liabilities_csv,
        "client_hsa_schedule.csv": _blank_hsa_schedule_csv,
    }
    files: dict[str, str] = {}
    for name, blank in blankers.items():
        src = source_dir / name
        files[name] = blank(src.read_text(encoding="utf-8-sig") if src.exists() else "")
    return files


def _blank_plan_rows(*, ytd_blend_enabled: bool | None = None) -> int:
    """Start New Plan on the plan rows: clear the household's facts in one edit transaction
    (``blank_plan.blank_plan_rows``). A blank plan clears the retirement dates on purpose, so
    the protected-value rule is off. Returns the number of values cleared."""
    with edit_active_plan(protect_values=False) as edit:
        return blank_plan_rows(edit.store, ytd_blend_enabled=ytd_blend_enabled)


def _protected_client_data_status() -> dict:
    """Non-secret preservation status for validation/UI diagnostics: whether each retirement
    date is on file. Reads the active plan's rows without creating or writing the plan file."""
    data = peek_plan_data()
    present = {
        label: bool(str(data.get(section, {}).get(subsection, {}).get(label, "")).strip())
        for section, subsection, label in PROTECTED_PLAN_KEYS
    }
    return {
        "member_1_retirement_date_present": present.get("member_1_retirement_date", False),
        "member_2_retirement_date_present": present.get("member_2_retirement_date", False),
    }


def _plan_data_path(file_name: str, prefer_existing: bool = True) -> Path:
    name = _normalize_plan_data_file_name(file_name)
    return workspace_file(name, _workspace_id(), WORKSPACE_ROOT, prefer_existing=prefer_existing)


def _read_plan_data_file(file_name: str) -> str | None:
    name = _normalize_plan_data_file_name(file_name)
    # The legacy local database's client_files holds the flat datasets' text (holdings,
    # spending, YTD ...) until WP6 moves them into the plan file. Read it first; the on-disk
    # input/*.csv is used only to bootstrap it on a fresh checkout / first run, and when we
    # read a CSV for that reason we lazily seed the DB so subsequent reads are DB-canonical.
    content = get_client_file(name, _workspace_id(), _client_id(), _sqlite_db())
    if content is not None:
        return content
    path = _plan_data_path(name, prefer_existing=True)
    if path.exists():
        csv_content = path.read_text(encoding="utf-8-sig")
        try:
            set_client_file(name, csv_content, _workspace_id(), _client_id(), _current_user().user_id, _sqlite_db())
        except Exception as exc:
            _audit("plan_data_db_bootstrap_warning", {"file": name, "error": str(exc)})
        return csv_content
    return None


def _write_plan_data_file(file_name: str, content: str) -> Path:
    """Write one flat dataset file (client_files first, then the on-disk copy)."""
    name = _normalize_plan_data_file_name(file_name)
    path = _plan_data_path(name, prefer_existing=False)
    with plan_file_lock(path):
        try:
            set_client_file(name, content, _workspace_id(), _client_id(), _current_user().user_id, _sqlite_db())
        except Exception as exc:
            _audit("plan_data_db_write_warning", {"file": name, "error": str(exc)})
        write_text_atomic(path, content)
    return path


SSA44_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Model Constants", "IRMAA", "h_ssa44_relief_year", "", "year", "First year Member 1's IRMAA surcharge is suppressed following an approved Form SSA-44 life-changing-event appeal. Blank = none filed. Base Part B/D/G premiums are still owed; only the surcharge is relieved. An appeal outcome is granted case-by-case and is never guaranteed — enter this only for an appeal already approved."],
    ["Model Constants", "IRMAA", "w_ssa44_relief_year", "", "year", "First year Member 2's IRMAA surcharge is suppressed following an approved Form SSA-44 life-changing-event appeal. Blank = none filed. Base Part B/D/G premiums are still owed; only the surcharge is relieved. An appeal outcome is granted case-by-case and is never guaranteed — enter this only for an appeal already approved."],
]
ROTH_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Model Constants", "Roth Conversion", "roth_conv_window_end_offset", "-1", "years", "CONV_END_YR = H_RMD_start_yr + this offset; default -1 ends voluntary conversions the year before RMDs."],
    ["Withdrawal Policy", "Roth Conversion", "roth_conversion_policy", "optimize_terminal_tax", "choice", "optimize_terminal_tax | fill_to_bracket | fill_to_irmaa | fixed_dollar | none; high-level policy for voluntary conversions."],
    ["Withdrawal Policy", "Roth Conversion", "roth_bracket_strategy", "OPTIMIZER_CHOOSES", "choice", "NONE | FILL_CURRENT_BRACKET | FILL_TARGET_BRACKET | PARTIAL_TARGET_BRACKET | IRMAA_GUARDED | SURVIVOR_TAX_AWARE | RMD_REDUCTION | LEGACY_TARGETED | OPTIMIZER_CHOOSES | FIXED_DOLLAR | PHASE_VARYING; strategy family considered by the Roth optimizer."],
    ["Withdrawal Policy", "Roth Conversion", "roth_objective_mode", "BALANCED_RETIREMENT", "choice", "BALANCED_RETIREMENT | MINIMIZE_LIFETIME_TAX | MAXIMIZE_TERMINAL_NET_WORTH | LEGACY_OPTIMIZED | ESTATE_TAX_AWARE | CUSTOM_WEIGHTED; objective used to rank Roth conversion candidates."],
    ["Withdrawal Policy", "Roth Conversion", "estate_tax_objective_mode", "BALANCED", "choice", "OFF | MONITOR_ONLY | BALANCED | STRONG; whether projected estate-tax exposure affects Roth strategy scoring."],
    ["Withdrawal Policy", "Roth Conversion", "roth_headroom_usage_pct", "95.00%", "percent", "Percentage of available tax-bracket headroom to use; 95% leaves margin below the threshold."],
    ["Withdrawal Policy", "Roth Conversion", "roth_target_bracket_rate", "22.00%", "choice", "10.00% | 12.00% | 22.00% | 24.00% | 32.00% | 35.00% | 37.00%; Target marginal bracket ceiling used by bracket-fill policies."],
    ["Withdrawal Policy", "Roth Conversion", "roth_phase_first_bracket_rate", "24.00%", "choice", "10.00% | 12.00% | 22.00% | 24.00% | 32.00% | 35.00% | 37.00%; PHASE_VARYING strategy only -- bracket rate to fill until the first Social Security claim year."],
    ["Withdrawal Policy", "Roth Conversion", "roth_phase_second_bracket_rate", "22.00%", "choice", "10.00% | 12.00% | 22.00% | 24.00% | 32.00% | 35.00% | 37.00%; PHASE_VARYING strategy only -- bracket rate for the next phase (second SS claim year if roth_phase_count is 3, otherwise the window end)."],
    ["Withdrawal Policy", "Roth Conversion", "roth_phase_third_bracket_rate", "12.00%", "choice", "10.00% | 12.00% | 22.00% | 24.00% | 32.00% | 35.00% | 37.00%; PHASE_VARYING strategy only -- bracket rate for the final phase through the conversion window end. Unused when roth_phase_count is 2."],
    ["Withdrawal Policy", "Roth Conversion", "roth_phase_count", "3", "choice", "2 | 3; PHASE_VARYING strategy only -- number of rate phases. 2 steps down once, at the first SS claim year. 3 steps down twice, at each spouse's SS claim year (degrades to 2 automatically for a single-member household or same-year claimants)."],
    ["Withdrawal Policy", "Roth Conversion", "roth_irmaa_target_tier", "TIER_2", "choice", "TIER_1 | TIER_2 | TIER_3 | TIER_4 | TIER_5; IRMAA cap tier used by Roth conversion guardrails. UI labels show MFJ and Single dollar thresholds from annual tax data."],
    ["Withdrawal Policy", "Roth Conversion", "irmaa_guardrail_mode", "AVOID_NEXT_TIER", "choice", "IGNORE | WARN_ONLY | AVOID_NEXT_TIER | AVOID_TIER_2_OR_ABOVE | CUSTOM_MAGI_CAP; Medicare threshold guardrail for Roth conversions."],
    ["Withdrawal Policy", "Roth Conversion", "roth_irmaa_headroom_usage_pct", "95.00%", "percent", "Percentage of available IRMAA headroom to use before stopping voluntary conversions."],
    ["Withdrawal Policy", "Roth Conversion", "roth_bracket_guardrail", "TRUE", "boolean", "TRUE | FALSE; cap voluntary conversions at the room left in the target tax bracket. Turn off to let the other active guardrails alone limit conversions."],
    ["Withdrawal Policy", "Roth Conversion", "roth_aca_guardrail", "TRUE", "boolean", "TRUE | FALSE; in ACA bridge years, cap conversions so income stays under the limit where premium credits shrink. Turning it off can cost premium credits; it does not change how credits are modeled."],
    ["Withdrawal Policy", "Roth Conversion", "roth_ltcg_guardrail", "TRUE", "boolean", "TRUE | FALSE; cap voluntary conversions at the top of your current 0%/15% long-term-capital-gain rate band so they do not push qualified dividends/gains into a higher rate. Applies to fill_to_bracket and fill_to_irmaa. The smallest active cap always wins, so this can bind before your target bracket."],
    ["Withdrawal Policy", "Roth Conversion", "roth_ltcg_band", "auto", "choice", "auto | 0% | 15%; which long-term capital gain rate band conversions must stay within. auto uses the band your income is in."],
    ["Withdrawal Policy", "Roth Conversion", "roth_ltcg_headroom_usage_pct", "95.00%", "percent", "Percentage of available LTCG rate-band headroom to use; only applies when roth_ltcg_guardrail is TRUE."],
    ["Withdrawal Policy", "Roth Conversion", "roth_niit_guardrail", "TRUE", "boolean", "TRUE | FALSE; cap voluntary conversions at the 3.8% Net Investment Income Tax threshold when you have investment income. Applies to fill_to_bracket and fill_to_irmaa. The smallest active cap always wins, so this can bind before your target bracket."],
    ["Withdrawal Policy", "Roth Conversion", "roth_niit_headroom_usage_pct", "95.00%", "percent", "Percentage of available NIIT-threshold headroom to use; only applies when roth_niit_guardrail is TRUE."],
    ["Withdrawal Policy", "Roth Conversion", "roth_fixed_annual_amount", "$50,000 ", "dollars", "Annual amount used only when roth_conversion_policy is fixed_dollar."],
    ["Withdrawal Policy", "Roth Conversion", "max_annual_conversion_pct_of_traditional_ira", "20.00%", "percent", "Maximum voluntary conversion in a year as a percentage of starting traditional IRA/pre-tax balances."],
    ["Withdrawal Policy", "Roth Conversion", "max_conversion_years", "10", "years", "Maximum number of years in the voluntary conversion window, also bounded by the RMD-age window."],
    ["Withdrawal Policy", "Roth Conversion", "roth_optimize_terminal_weight", "1.00", "number", "Weight on after-tax terminal net worth in the optimizer objective."],
    ["Withdrawal Policy", "Roth Conversion", "roth_optimize_lifetime_tax_weight", "0.25", "number", "Weight on lifetime tax penalty in the optimizer objective."],
    ["Withdrawal Policy", "Roth Conversion", "roth_optimize_terminal_pretax_tax_rate", "24.00%", "percent", "Haircut on end-of-plan pre-tax balances: the tax rate subtracted from pre-tax money left at the end of the plan, because heirs owe income tax on it."],
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
    ["Model Constants", "Monte Carlo", "mc_engine_mode", "quick_vectorized", "choice", "advanced_exact_scalar | quick_vectorized; User UI toggle: Complex/Advanced Exact Scalar is slower and advisor-ready; Simple/Quick Vectorized is faster and approximate for diagnostics."],
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

SS_CLAIM_DATE_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Social Security", "Member 1", "claim_date", "", "date", "Month and year Social Security benefits start for member 1 (claim age is calculated from this and date of birth). Leave blank to default to age 70, claimed in this person's own birth month."],
    ["Social Security", "Member 2", "claim_date", "", "date", "Month and year Social Security benefits start for member 2 (claim age is calculated from this and date of birth). Leave blank to default to age 70, claimed in this person's own birth month."],
]

HEALTHCARE_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Wellness", "Medicare", "part_g_base_premium_monthly", "$0", "dollars", "Current monthly Medicare Supplement Plan G / Medigap-style premium per Medicare-enrolled person. Enter $0 if no supplement is modeled."],
]

FORMER_SPOUSE_UI_PLAN_DATA_ROWS: list[list[str]] = [
    ["Estate Planning", "Step-Up", "former_spouse_name", "", "text", "Optional name used only by the Beneficiary & Titling Audit (Sheet 14) to flag a former spouse still named as a beneficiary on any account."],
]

# Item 4.7 (P8): per-account beneficiary and titling. Subsection = account id
# from client_holdings.csv (e.g. "Member_1_IRA"), mirroring the "Account
# Policy"/reinvest_dividends per-account backfill below. Consumed by
# beneficiary_titling_audit/_account_basis_step_fraction/
# _survivor_bonus_step_fraction in src/planning_engines.py (see
# src/data_io.py's parse_advanced_modules for the CSV section shape).
def _account_titling_ui_plan_data_rows(target_dir: Path) -> list[list[str]]:
    return [
        row
        for acct in _all_account_ids_from_holdings(target_dir)
        for row in (
            ["Account Titling", acct, "primary_beneficiary", "", "text",
             "Name of the primary beneficiary on file for this account. Reviewed by the Beneficiary & Titling Audit (Sheet 14)."],
            ["Account Titling", acct, "contingent_beneficiary", "", "text",
             "Name of the contingent (backup) beneficiary on file for this account."],
            ["Account Titling", acct, "titling", "", "choice",
             "INDIVIDUAL | JTWROS | TENANTS_IN_COMMON | COMMUNITY_PROPERTY | SEPARATE_PROPERTY | TRUST_TITLED | TOD_POD; How this account is titled. Drives this account's own basis step-up/survivor-bonus fraction instead of the household-wide property regime, and flags JTWROS/community-property review prompts on Sheet 14. Leave blank to use the household default."],
            ["Account Titling", acct, "trust_see_through", "FALSE", "bool",
             "TRUE if a trust named as beneficiary qualifies as a see-through trust for RMD purposes (avoids the Sheet 14 trust_no_see_through flag)."],
        )
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

# #295: QLAC (Qualified Longevity Annuity Contract) -- one slot per member,
# alongside the existing fixed annuity/pension slots this section already
# carries (Member N Single/Joint Annuity, Member 2 Pension). Disabled by
# default (enabled=FALSE), so backfilling these rows into every existing
# plan changes nothing about that plan's projection until a user opts in.
def _qlac_ui_plan_data_rows(member: str) -> list[list[str]]:
    sub = f"Member {member} QLAC"
    return [
        ["Income Streams", sub, "qlac_enabled", "FALSE", "bool",
         "Enable a Qualified Longevity Annuity Contract for this person -- a deferred-income annuity bought with pre-tax retirement dollars whose premium is excluded from this person's RMD-divisor balance once purchased (IRC Sec. 401(a)(9)(H))."],
        ["Income Streams", sub, "premium", "$0", "USD",
         "Purchase premium. Capped at the statutory aggregate limit (2025: $210,000, indexed annually) regardless of what's entered here -- the projection engine enforces the cap even if this field is set higher."],
        ["Income Streams", sub, "qlac_source_account", "", "text",
         "Traditional IRA/401(k)/403(b)/SEP-IRA account id the premium is paid from (e.g. Member_1_IRA). Must be a pre-tax account -- a QLAC cannot be funded from a Roth or taxable account."],
        ["Income Streams", sub, "purchase_year", "", "year",
         "Year the premium is actually paid. Blank = plan start."],
        ["Income Streams", sub, "first_payment", "", "date",
         "Year QLAC income begins. Must be no later than the year this person turns 85 (IRC Sec. 401(a)(9)(H)(iv))."],
        ["Income Streams", sub, "initial_guaranteed_income_payment", "$0", "USD",
         "Guaranteed monthly QLAC payment starting in the first-payment year (from the carrier's quote). A QLAC has no dividend/cash component, so this is the payment for the life of the contract, before any COLA."],
        ["Income Streams", sub, "death_benefit_pct", "0.00%", "percent",
         "Optional return-of-premium death benefit: share of unpaid premium returned to beneficiaries if this person dies before recovering the full premium in payments. 0% = no death benefit (higher payout rate); not yet reflected in terminal net worth."],
    ]

QLAC_UI_PLAN_DATA_ROWS: list[list[str]] = _qlac_ui_plan_data_rows("1") + _qlac_ui_plan_data_rows("2")

# A7: PLAN_DATA_BACKFILL_ENTRIES replaces twelve near-identical
# _ensure_*_ui_plan_data_rows functions with one declarative table over
# plan_data_backfill.apply_backfill (WP4.4c: on the plan rows, no CSV files). An entry is
# (rows, anchor): where its rows go inside their section; no anchor = the end of the section.
# Order matches the original call sequence, since entries are applied in list order against the
# same growing rows (see apply_backfill's docstring) - reordering this list can change which
# anchor a later entry in the same section sees.
_BF = plan_data_backfill
_AFTER_ECONOMIC_ASSUMPTIONS = _BF.after_last(_BF.subsection_is(""))
PLAN_DATA_BACKFILL_ENTRIES: list[plan_data_backfill.BackfillEntry] = [
    _BF.BackfillEntry(ALLOCATION_UI_PLAN_DATA_ROWS),
    _BF.BackfillEntry(MONTE_CARLO_UI_PLAN_DATA_ROWS, _BF.before_first(_BF.subsection_is("Roth Conversion", "IRMAA"))),
    _BF.BackfillEntry(ROTH_UI_PLAN_DATA_ROWS),
    _BF.BackfillEntry(SSA44_UI_PLAN_DATA_ROWS),
    _BF.BackfillEntry(HSA_WITHDRAWAL_UI_PLAN_DATA_ROWS),
    _BF.BackfillEntry(SOCIAL_SECURITY_FUNDING_UI_PLAN_DATA_ROWS),
    _BF.BackfillEntry(QLAC_UI_PLAN_DATA_ROWS, _BF.before_first(_BF.subsection_is("Joint-and-Survivor Percentage"))),
    _BF.BackfillEntry(SS_CLAIM_DATE_UI_PLAN_DATA_ROWS, _BF.before_first(_BF.label_is("claim_age"))),
    _BF.BackfillEntry(SS_FRA_AGE_UI_PLAN_DATA_ROWS, _BF.before_first(_BF.label_is("spousal_benefits_enabled"))),
    _BF.BackfillEntry(HEALTHCARE_UI_PLAN_DATA_ROWS, _BF.before_first(_BF.subsection_is("Out-of-Pocket"))),
    _BF.BackfillEntry(HELOC_UI_PLAN_DATA_ROWS),
    _BF.BackfillEntry(CORE_SPENDING_UI_PLAN_DATA_ROWS, _BF.after_last(_BF.subsection_is("Spending"))),
    _BF.BackfillEntry(MORTGAGE_RE_TAX_UI_PLAN_DATA_ROWS, _BF.after_last(_BF.subsection_is("Mortgage"))),
    _BF.BackfillEntry(QCD_UI_PLAN_DATA_ROWS, _BF.after_last(_BF.subsection_is("Spending"))),
    _BF.BackfillEntry(DAF_APPRECIATED_UI_PLAN_DATA_ROWS, _BF.after_last(_BF.subsection_is("Settings"))),
    _BF.BackfillEntry(FORMER_SPOUSE_UI_PLAN_DATA_ROWS, _BF.after_last(_BF.subsection_is("Step-Up"))),
    _BF.BackfillEntry(_account_titling_ui_plan_data_rows),
    _BF.BackfillEntry(
        [["Economic Assumptions", "", "inflation_general", "2.50%", "pct", "General CPI inflation used when core_spending_growth_mode is cpi."]],
        _AFTER_ECONOMIC_ASSUMPTIONS,
    ),
    _BF.BackfillEntry(
        [["Model Constants", "Retirement", "spending_freeze_year", "2040", "year", "Year after which core spending stops increasing; grouped with Spending / Core spending in the User UI."]],
        _BF.after_last(_BF.subsection_is("Retirement")),
    ),
    _BF.BackfillEntry(
        [["Economic Assumptions", "", "reinvest_dividends_default", "NO", "yes/no",
          "Global switch: reinvest every investment account's dividends/interest into the same holding instead of letting them convert to cash inside the account. When YES, this applies to every investment account and the per-account overrides below are ignored."]],
        _AFTER_ECONOMIC_ASSUMPTIONS,
    ),
    _BF.BackfillEntry(
        [["Economic Assumptions", "", "tax_law_scenario", "current_law", "choice",
          "current_law | higher_rates. higher_rates taxes federal ordinary income at pre-2018 rates from the start year (a stress; thresholds unchanged)."],
         ["Economic Assumptions", "", "higher_rates_start_year", "", "year",
          "First year the higher_rates stress applies. Blank = the first plan year."]],
        _AFTER_ECONOMIC_ASSUMPTIONS,
    ),
    _BF.BackfillEntry(
        [["Economic Assumptions", "", "state_income_tax_rate", "", "pct",
          "Override for state income-tax rate. Blank = Auto: the residence state's own rules. A value taxes state income at this flat rate (state retirement and Social Security exemptions still apply)."]],
        _AFTER_ECONOMIC_ASSUMPTIONS,
    ),
    _BF.BackfillEntry(
        [["Economic Assumptions", "", "cash_yield_rate", "2.00%", "pct",
          "Growth rate applied to dividends/interest that convert to cash inside an account (Reinvest Dividends = NO) instead of compounding with the rest of the holding."]],
        _AFTER_ECONOMIC_ASSUMPTIONS,
    ),
    _BF.BackfillEntry(
        lambda target_dir: [
            ["Account Policy", acct, "reinvest_dividends", "", "yes/no",
             "Per-account override of Economic Assumptions/reinvest_dividends_default. Leave blank to inherit the global switch. Ignored while the global switch is YES."]
            for acct in _investment_account_ids_from_holdings(target_dir)
        ],
    ),
    _BF.BackfillEntry(TLH_UI_PLAN_DATA_ROWS, _BF.after_last(_BF.subsection_is("Identity"))),
]


def _plan_input_dir() -> Path:
    """The workspace folder of the flat datasets (``client_holdings.csv`` ...): the one place
    the per-account backfill rows are read from."""
    return platform_runtime.workspace_root() / "input"


def _ensure_user_ui_plan_data_rows() -> None:
    """Materialize forward-schema rows that the guided User UI depends on.

    A plan can lack newer UI control rows (it predates that control). The UI should never
    hide a new control merely because the plan predates it. This function adds canonical
    current-schema rows only; it does not read previous-name aliases, and never changes a row
    the plan already holds.

    Works on the active plan's rows (``plan_data_backfill.apply_backfill`` in one
    ``_edit_active_plan`` transaction). A plan with every row already there is only read; a
    plan with no rows is left alone (nothing to backfill into).
    """
    with _read_active_plan() as store:
        if not store.section_order() or not plan_data_backfill.pending_rows(store, PLAN_DATA_BACKFILL_ENTRIES, _plan_input_dir()):
            return
    with _edit_active_plan() as edit:
        plan_data_backfill.apply_backfill(edit.store, PLAN_DATA_BACKFILL_ENTRIES, _plan_input_dir())


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
        vals=[(1,212000,106000),(2,266000,133000),(3,334000,167000),(4,400000,200000),(5,750000,500000)]
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
        "roth_bracket_strategy": ["NONE", "FILL_CURRENT_BRACKET", "FILL_TARGET_BRACKET", "PARTIAL_TARGET_BRACKET", "IRMAA_GUARDED", "SURVIVOR_TAX_AWARE", "RMD_REDUCTION", "LEGACY_TARGETED", "OPTIMIZER_CHOOSES", "FIXED_DOLLAR", "PHASE_VARYING"],
        "roth_objective_mode": ["BALANCED_RETIREMENT", "MINIMIZE_LIFETIME_TAX", "MAXIMIZE_TERMINAL_NET_WORTH", "LEGACY_OPTIMIZED", "ESTATE_TAX_AWARE", "CUSTOM_WEIGHTED"],
        "estate_tax_objective_mode": ["OFF", "MONITOR_ONLY", "BALANCED", "STRONG"],
        "irmaa_guardrail_mode": ["IGNORE", "WARN_ONLY", "AVOID_NEXT_TIER", "AVOID_TIER_2_OR_ABOVE", "CUSTOM_MAGI_CAP"],
        "legacy_objective_mode": ["OFF", "LOW", "BALANCED", "STRONG"],
        "hsa_withdrawal_mode": ["spend_as_needed", "annual_pct", "smooth_window", "optimize"],
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
    if lbl == "hsa_withdrawal_mode":
        # Item 291-adjacent fix (2026-08-20): hsa_withdrawal_mode was left in
        # the plain-string `fixed` dict below, so it fell through to the
        # generic `v.replace("_", " ")` auto-label -- "spend as needed",
        # "annual pct", "optimize" with no capitalization. Verified live in
        # the browser: choice_options is what the frontend actually renders
        # from (dashboard.js's own fixed[label] entry for this same field is
        # unreachable dead code, since Array.isArray(r.choice_options) always
        # wins first -- see choiceOptions() in frontend/js/dashboard.js).
        return [
            {"value": "spend_as_needed", "label": "Spend as needed"},
            {"value": "annual_pct", "label": "Annual percentage"},
            {"value": "smooth_window", "label": "Smooth window"},
            {"value": "optimize", "label": "Optimizer"},
        ]
    if lbl == "capital_market_assumption_horizon_source":
        # Same failure mode as hsa_withdrawal_mode above: this field's schema
        # description reads "manual|auto_from_withdrawals. auto_from_withdrawals
        # derives the effective horizon from..." with no semicolon before the
        # trailing prose, so the generic _pipe_choice_options() fallback below
        # split on "|" and kept the ENTIRE second sentence as the option's
        # value/label -- "auto_from_withdrawals. auto_from_withdrawals derives
        # the effective horizon from this household's own projected withdrawal
        # schedule instead of the manual horizon_years value." That garbage
        # string then gets silently persisted to client_policy.csv on save
        # (schema_registry's choice-type validation doesn't check enum
        # membership), which data_io.py's exact `== 'auto_from_withdrawals'`
        # check never matches -- so the feature silently no-ops instead of
        # activating. dashboard.js's own fixed[label] entry for this field is
        # unreachable dead code for the same reason noted above.
        return [
            {"value": "manual", "label": "Manual (use the horizon selected above)"},
            {"value": "auto_from_withdrawals", "label": "Auto-derive from projected withdrawals"},
        ]
    if lbl == "roth_target_bracket_rate":
        return _federal_bracket_choice_options("MFJ")
    if lbl == "roth_irmaa_target_tier":
        return _irmaa_tier_choice_options("tier")
    if lbl in ("state", "residence_state"):
        return state_name_choice_options()
    if lbl == "target_state":
        return state_abbr_choice_options()
    if lbl in fixed:
        return [{"value": v, "label": v.replace("_", " ")} for v in fixed[lbl]]
    typ = str((spec or {}).get("type") or "").lower()
    if typ == "boolean" or str(units or "").strip().lower() in {"yes/no", "true/false", "boolean"}:
        return [{"value": "TRUE", "label": "TRUE"}, {"value": "FALSE", "label": "FALSE"}]
    if typ == "choice" or str(units or "").strip().lower() == "choice":
        return _pipe_choice_options((spec or {}).get("description", "")) or _pipe_choice_options(notes)
    return []

def _csv_rows_payload() -> dict:
    """The grid's rows (``GET /api/config/rows``, build preflight): the active plan's rows.

    WP4.3: one row per ``plan_rows`` row in display order (sections by creation, rows by
    ``sort_order``); ``row_index`` is the row's ``row_id``, stable while the row exists, and
    what ``update_config_rows_payload`` writes by. The GET-time backfill runs first, so the
    rows include what it added. ``revision`` is ``PlanStore.revision()`` of the rows served.
    """
    _ensure_user_ui_plan_data_rows()
    schema = _read_schema_map()
    with active_plan_store() as store:
        order = {section: i for i, section in enumerate(store.section_order())}
        plan_rows = sorted(store.all_rows(), key=lambda r: (order[r["section"]], r["sort_order"], r["row_id"]))
        revision = store.revision()
    rows = []
    for r in plan_rows:
        section, subsection, label = r["section"], r["subsection"], r["label"]
        spec = schema.get((section, subsection, label), {})
        rows.append({
            "row_index": r["row_id"],
            "section": section,
            "subsection": subsection,
            "label": label,
            "value": r["value"],
            "units": r["units"],
            "notes": r["notes"],
            "schema": spec,
            "choice_options": _choice_options_for_config_row(section, subsection, label, r["units"], r["notes"], spec),
            "group": _classify_config_row(section, subsection, label),
        })
    return {"rows": rows, "schema_count": len(schema), "revision": revision}


def _edit_active_plan(**kwargs):
    """The row writers' edit context (the strategy endpoints, the UI-row backfill): one
    transaction on the active plan's rows (``active_plan.edit_active_plan``)."""
    return edit_active_plan(**kwargs)


def _edit_active_plan_protected():
    """The edit context of the config grid and ``/api/plan/forms``: ``_edit_active_plan`` with the
    protected retirement dates kept (``active_plan.PROTECTED_PLAN_KEYS``) -- the one rule the
    retired file writer applied, and only to those saves."""
    return edit_active_plan(protect_values=True)


@contextmanager
def _read_active_plan():
    """The strategy endpoints' read context: the open active-plan store."""
    with active_plan_store() as store:
        yield store


TRAVEL_EXTRA_TYPES = [
    "Wedding",
    "Large Gifts",
    "Other",
]


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
            # One century rule shared with the engine's date reader (WI-401).
            from ..plan_dates import expand_two_digit_year
            y = str(expand_two_digit_year(int(y)))
        return f"{y.zfill(4)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
    if re.match(r"^\d{4}$", text):
        return f"{text}-01-01"
    return text


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


def _all_account_ids_from_holdings(holdings_dir: Path | None = None) -> list[str]:
    """Return every account id present in client_holdings.csv, with no type
    exclusions (unlike _investment_account_ids_from_holdings, which drops
    checking/529 accounts as irrelevant to dividend reinvestment). Item 4.7
    (P8) beneficiary/titling review applies to every account type -- checking
    accounts commonly carry their own TOD/POD designation -- so every
    account needs an Account Titling backfill row.
    """
    path = (holdings_dir / "client_holdings.csv") if holdings_dir is not None else _plan_data_path("client_holdings.csv", prefer_existing=False)
    accounts = set()
    if path.exists():
        with path.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                acct = str(r.get("account") or "").strip()
                if acct:
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


def _origin_or_referer_netloc(value: str) -> str:
    return value.split("://", 1)[-1].rstrip("/").split("/", 1)[0]


def _cross_site_request() -> bool:
    """True if this request names a different host than the one it hit.

    Mirrors financial_trends_reporter/main.py's own Origin allow-list
    (ARC-4, system review 2026-09-07): a request naming a different Origin
    (or, lacking that, a different Referer host) than this server's own Host
    is cross-site; one carrying neither header -- ordinary same-origin
    navigation/fetch in most browsers, and every non-browser local script --
    is not flagged as cross-site on that basis alone.
    """
    host = str(request.headers.get("Host", "") or "")
    origin = str(request.headers.get("Origin", "") or "")
    if origin:
        return _origin_or_referer_netloc(origin) != host
    referer = str(request.headers.get("Referer", "") or "")
    if referer:
        return _origin_or_referer_netloc(referer) != host
    return False


def _csrf_and_origin_gate():
    """ARC-001 (system review 2026-09-25): server mode issued an
    X-CSRF-Token (see _csrf_token_for_current_request / base_routes.py's
    login and session endpoints) but never checked it, and had no
    Origin/Referer/Host allow-list at all -- a cross-site page (a plain
    auto-submitting form needs no JavaScript and no CORS preflight) could
    POST/PUT/DELETE any non-GET route and overwrite plan data, exfiltrate a
    full DB copy, or swap in an attacker-controlled database.

    A request naming a foreign Origin/Referer is always rejected. One naming
    neither -- which includes every existing same-origin browser request and
    non-browser automation script -- is rejected only once it also fails a
    same-origin-scoped CSRF token check; this keeps a foreign-origin request
    (which always carries an Origin header in current browsers, even for a
    same-site POST) from being let through by a missing token alone, while
    not requiring every non-browser caller to start minting tokens it has no
    way to fetch. A request carrying its own bearer-style credential
    (Authorization / X-API-Token) is not cookie/browser-auto-attached and so
    is not a CSRF target regardless of Origin -- and a cross-origin page
    cannot itself attach an arbitrary Authorization header without a CORS
    preflight this server never grants (see the SEC-1 comment above).
    """
    if _cross_site_request():
        return jsonify({"success": False, "error": "Cross-origin requests are not allowed"}), 403
    has_origin_evidence = bool(request.headers.get("Origin") or request.headers.get("Referer"))
    if not has_origin_evidence or _has_bearer_or_api_header():
        return None
    token = str(request.headers.get("X-CSRF-Token", "") or "")
    if not token or not constant_time_token_ok(token, _csrf_token_for_current_request()):
        return jsonify({"success": False, "error": "Missing or invalid CSRF token"}), 403
    if request.path.startswith("/api/") and request.get_data():
        content_type = str(request.headers.get("Content-Type", "") or "").split(";", 1)[0].strip().lower()
        if content_type not in {"application/json", "text/plain"}:
            return jsonify({"success": False, "error": "Unsupported Content-Type"}), 403
    return None


@app.before_request
def _security_gate():
    if request.method == "OPTIONS":
        return None
    if _public_path():
        return None
    # The desktop bridge (DesktopApi.request in src/desktop_api.py) dispatches
    # every call in-process through this same app's test_client() and never
    # opens a real socket -- there is no network boundary for a remote page
    # to cross -- so it is marked exempt once, at construction, rather than
    # guessed at here from header shape (it sends neither an Origin/Referer
    # nor a CSRF token, since headers are never forwarded across the bridge).
    if request.method not in {"GET", "HEAD"} and not getattr(app, "_no_http_transport", False):
        denied = _csrf_and_origin_gate()
        if denied:
            return denied
    # System review 4.5: this package only ever ships as LOCAL (VALID_APP_MODES
    # = {LOCAL} in runtime_config.py; load_runtime_config() hardcodes
    # app_mode = LOCAL unconditionally), so the token-auth rejection this
    # gate performed only in SaaS mode could never fire -- removed rather
    # than left as unreachable dead code. _authorized_and_identity() is
    # still called: its identity (when present, e.g. from a valid
    # X-User-* header) still populates g.user_context for _require()'s
    # role-based permission checks below, which remain fully enforced.
    _ok, identity = _authorized_and_identity()
    if identity:
        g.user_context = identity
    # Local-only package: no cookie-authenticated public-hosting mode remains.
    # API clients using Authorization/X-API-Token are not browser-cookie based and
    # remain compatible with automation scripts.


# System review 2026-09-07 SEC-1: a wildcard `Access-Control-Allow-Origin: *`
# used to be set here unconditionally, on the theory that a `file://`-opened
# copy of the frontend needed cross-origin access to the local API. The
# frontend is actually always served same-origin, from this same server, at
# /frontend/<path> (see base_routes.py). Same-origin requests need no CORS
# headers at all, and a wildcard ACAO instead let *any* web page the user's
# browser had open read every API response -- full read/write of the
# household's plan data -- since _security_gate() enforces no auth in LOCAL
# mode. No replacement CORS handling is added: nothing legitimate needs it.


# Export private helper names to route modules using star imports.
__all__ = [name for name in globals() if not name.startswith("__")]

