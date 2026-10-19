from __future__ import annotations

"""Opt-in Monarch auto-update policy + run status (ticket 305).

Shaped after src/local_backup_scheduler.py's policy-file pattern for
consistency. Unlike that scheduler, the actual daily trigger is external
(Windows Task Scheduler invoking tools/monarch_autoimport.py headlessly at
4am) -- this module only owns the enabled/config state and the last-run
status, not the timing itself.
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "monarch_autoupdate_v1"
STATUS_SCHEMA = "monarch_autoupdate_status_v1"
POLICY_SETTING = "monarch_autoupdate.policy"
STATUS_SETTING = "monarch_autoupdate.status"
LEGACY_SETTINGS_FILENAME = "monarch_autoupdate.json"  # older installs; read once
LEGACY_STATUS_FILENAME = "monarch_autoupdate_status.json"
DEFAULT_SOURCE_DIR = "Monarch Extractor/output"  # relative to the workspace; only the fallback
DEFAULT_RUN_TIME = "04:00"
BALANCES_STATUS_SETTING = "monarch_autoupdate.balances_status"


@dataclass(frozen=True)
class AutoUpdatePolicy:
    enabled: bool = True
    source_dir: str = ""  # absolute path; "" = the shipped default folder under the workspace
    field_map_path: str = ""  # "" = use the shipped default (from reference database)
    run_time: str = DEFAULT_RUN_TIME  # 24h HH:MM, the daily Task Scheduler time
    transactions: bool = True  # step 1: import transactions
    balances: bool = True  # step 2: import account balances

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "source_dir": self.source_dir,
            "run_time": self.run_time,
            "transactions": self.transactions,
            "balances": self.balances,
            "field_map_path": self.field_map_path,
        }


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(dt: datetime | None = None) -> str:
    dt = dt or now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def settings_path(base_dir: str | Path) -> Path:
    """The ``app.db`` holding the policy and status (WP8.3: no monarch_autoupdate*.json)."""
    from .app_state import app_store_path_for

    return app_store_path_for(base_dir)


def _read_setting(base_dir: str | Path, key: str, legacy_name: str) -> Any:
    """``key`` from app.db, else the one-time read of an older install's ``local_state/<legacy_name>``."""
    try:
        from .app_state import open_app_store

        path = settings_path(base_dir)
        if path.exists():
            with open_app_store(path, readonly=True) as store:
                value = store.get_setting(key)
            if value is not None:
                return value
    except Exception:
        return None
    try:
        return json.loads((Path(base_dir) / "local_state" / legacy_name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_setting(base_dir: str | Path, key: str, value: Any) -> None:
    from .app_state import open_app_store

    with open_app_store(settings_path(base_dir)) as store:
        store.set_setting(key, value)


# 2026-09 outage: RetirementSystem_MonarchAutoImport only reads whatever CSVs
# already exist in Monarch Extractor/output -- nothing scheduled the actual
# scrape (Monarch Extractor/run_monarch.ps1) that produces them, so it went
# stale for over a week while the import job kept reporting success ("no new
# rows" looks identical to "extractor is broken" from the import job's own
# status alone). EXTRACTOR_STALE_HOURS is deliberately looser than the daily
# schedule to avoid false alarms from one slow/retried run.
EXTRACTOR_STALE_HOURS = 36


def extractor_raw_dir(base_dir: str | Path) -> Path:
    """Where the Monarch Extractor itself (not the downstream import job)
    writes one file per scrape attempt. Fixed relative to base_dir --
    independent of the policy's (user-configurable) source_dir, which only
    ever names the *output* folder the import job reads from."""
    return Path(base_dir) / "Monarch Extractor" / "raw"


def get_extractor_freshness(base_dir: str | Path, *, now: datetime | None = None) -> dict[str, Any]:
    """Report when the extractor's scrape step last actually produced
    anything, independent of whether the downstream auto-import job found
    new rows to consume. See EXTRACTOR_STALE_HOURS for why this exists."""
    raw_dir = extractor_raw_dir(base_dir)
    files = list(raw_dir.glob("*.csv")) if raw_dir.exists() else []
    now = now or now_utc()
    if not files:
        return {
            "last_extract_at": None,
            "age_hours": None,
            "stale": True,
            "stale_after_hours": EXTRACTOR_STALE_HOURS,
        }
    newest_mtime = max(f.stat().st_mtime for f in files)
    last_extract_dt = datetime.fromtimestamp(newest_mtime, tz=timezone.utc)
    age_hours = (now - last_extract_dt).total_seconds() / 3600
    return {
        "last_extract_at": iso_utc(last_extract_dt),
        "age_hours": round(age_hours, 1),
        "stale": age_hours > EXTRACTOR_STALE_HOURS,
        "stale_after_hours": EXTRACTOR_STALE_HOURS,
    }


class SourceDirNotAbsoluteError(ValueError):
    """Raised when a policy's source_dir is not a full absolute path."""


# Kept so older callers/imports keep working; the folder is no longer confined to the workspace.
SourceDirOutsideWorkspaceError = SourceDirNotAbsoluteError


def default_source_dir(base_dir: str | Path) -> str:
    return str((Path(base_dir) / DEFAULT_SOURCE_DIR).resolve())


def _normalize_run_time(raw: Any) -> str:
    text = str(raw or "").strip() or DEFAULT_RUN_TIME
    try:
        hh, mm = text.split(":")
        if len(hh) not in (1, 2) or len(mm) != 2 or not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
            raise ValueError
    except ValueError:
        raise ValueError(f"run_time must be 24-hour HH:MM; got {text!r}") from None
    return f"{int(hh):02d}:{mm}"


def resolve_source_dir(base_dir: str | Path, policy: dict[str, Any] | AutoUpdatePolicy | None = None) -> Path:
    raw = ""
    if isinstance(policy, AutoUpdatePolicy):
        raw = policy.source_dir
    elif isinstance(policy, dict):
        raw = str(policy.get("source_dir") or "")
    p = Path(raw).expanduser() if raw else Path(default_source_dir(base_dir))
    return p if p.is_absolute() else (Path(base_dir) / p).resolve()


def normalize_policy(data: dict[str, Any] | None = None, *, strict: bool = False) -> AutoUpdatePolicy:
    """``strict`` (save time) rejects a relative source folder and a bad run time;
    loading is lenient so an older stored value can still be displayed and corrected."""
    data = data or {}
    source_dir = str(data.get("source_dir") or "").strip()
    if strict and source_dir and not Path(source_dir).expanduser().is_absolute():
        raise SourceDirNotAbsoluteError(f"source_dir must be a full absolute path; got {source_dir!r}")
    try:
        run_time = _normalize_run_time(data.get("run_time"))
    except ValueError:
        if strict:
            raise
        run_time = DEFAULT_RUN_TIME
    return AutoUpdatePolicy(
        enabled=bool(data.get("enabled", True)),
        source_dir=source_dir,
        field_map_path=str(data.get("field_map_path") or "").strip(),
        run_time=run_time,
        transactions=bool(data.get("transactions", True)),
        balances=bool(data.get("balances", True)),
    )


def load_policy(base_dir: str | Path) -> dict[str, Any]:
    raw = _read_setting(base_dir, POLICY_SETTING, LEGACY_SETTINGS_FILENAME)
    if not isinstance(raw, dict):
        raw = {}
    policy = normalize_policy(raw.get("policy") if isinstance(raw.get("policy"), dict) else raw)
    out = policy.as_dict()
    out["source_dir"] = str(resolve_source_dir(base_dir, policy))  # always shown as a full path
    return {"schema": SCHEMA, "policy": out, "settings_path": str(settings_path(base_dir))}


def save_policy(base_dir: str | Path, updates: dict[str, Any]) -> dict[str, Any]:
    """Raises SourceDirNotAbsoluteError for a relative ``source_dir``, ValueError for a bad ``run_time``."""
    merged = dict(load_policy(base_dir)["policy"])
    for key in ("enabled", "source_dir", "field_map_path", "run_time", "transactions", "balances"):
        if key in updates:
            merged[key] = updates[key]
    policy = normalize_policy(merged, strict=True)
    payload = {"schema": SCHEMA, "policy": policy.as_dict(), "updated_at": iso_utc()}
    _write_setting(base_dir, POLICY_SETTING, payload)
    return load_policy(base_dir)


def load_status(base_dir: str | Path) -> dict[str, Any] | None:
    data = _read_setting(base_dir, STATUS_SETTING, LEGACY_STATUS_FILENAME)
    return data if isinstance(data, dict) and data.get("schema") == STATUS_SCHEMA else None


def write_status(
    base_dir: str | Path,
    *,
    success: bool,
    files_consumed: list[str] | None = None,
    rows_added: int = 0,
    rows_updated: int = 0,
    rows_skipped: int = 0,
    errors: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Record the "mark the update as complete" status for one run."""
    payload = {
        "schema": STATUS_SCHEMA,
        "last_run_at": iso_utc(now),
        "success": bool(success),
        "files_consumed": list(files_consumed or []),
        "rows_added": int(rows_added),
        "rows_updated": int(rows_updated),
        "rows_skipped": int(rows_skipped),
        "errors": list(errors or []),
    }
    _write_setting(base_dir, STATUS_SETTING, payload)
    return payload


def load_balances_status(base_dir: str | Path) -> dict[str, Any] | None:
    data = _read_setting(base_dir, BALANCES_STATUS_SETTING, "")
    return data if isinstance(data, dict) else None


def write_balances_status(base_dir: str | Path, *, success: bool, status: str, detail: str = "",
                          now: datetime | None = None) -> dict[str, Any]:
    payload = {"last_run_at": iso_utc(now), "success": bool(success), "status": status, "detail": detail}
    _write_setting(base_dir, BALANCES_STATUS_SETTING, payload)
    return payload


def _run_registration_script(script: Path, action: str, start_time: str | None = None) -> dict[str, Any]:
    if not script.exists():
        return {"attempted": False, "success": False, "error": f"Registration script not found: {script}"}
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Action", action]
            + (["-StartTime", start_time] if start_time and action == "Register" else []),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return {"attempted": True, "success": proc.returncode == 0, "error": None if proc.returncode == 0 else proc.stderr.strip()}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"attempted": True, "success": False, "error": str(exc)}


def register_scheduled_task(base_dir: str | Path, enabled: bool, run_time: str = DEFAULT_RUN_TIME) -> dict[str, Any]:
    """Best-effort sync of the OS-level Task Scheduler entry with the in-app
    flag and run time, via the PowerShell helper script. One daily entry runs
    both import steps (transactions, then account balances).

    The task that produces the files is outside this app and is neither
    registered nor removed here.

    Never raises: a registration failure (non-Windows dev machine, no
    PowerShell, insufficient privilege) must not block saving the setting
    itself -- the caller surfaces {"attempted", "success", "error"} to the UI.
    """
    if sys.platform != "win32":
        return {"attempted": False, "success": False, "error": "Not running on Windows; scheduled-task registration skipped."}
    action = "Register" if enabled else "Unregister"
    result = _run_registration_script(
        Path(base_dir) / "tools" / "launchers" / "register_monarch_autoimport_task.ps1", action, _normalize_run_time(run_time)
    )
    return {**result, "details": {"import": result}}
