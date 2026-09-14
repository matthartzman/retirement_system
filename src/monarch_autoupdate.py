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
SETTINGS_FILENAME = "monarch_autoupdate.json"
STATUS_FILENAME = "monarch_autoupdate_status.json"
DEFAULT_SOURCE_DIR = "Monarch Extractor/output"


@dataclass(frozen=True)
class AutoUpdatePolicy:
    enabled: bool = False
    source_dir: str = DEFAULT_SOURCE_DIR
    field_map_path: str = ""  # "" = use the shipped default (src/monarch_field_map.json)

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "source_dir": self.source_dir,
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
    return Path(base_dir) / "local_state" / SETTINGS_FILENAME


def status_path(base_dir: str | Path) -> Path:
    return Path(base_dir) / "local_state" / STATUS_FILENAME


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


class SourceDirOutsideWorkspaceError(ValueError):
    """Raised when a policy's source_dir would resolve outside the workspace root.

    System review 2026-09-07 SEC-2: `source_dir` used to be accepted with no
    confinement check at all. Because `resolve_source_dir` feeds directly
    into a subprocess interpreter lookup (`monarch_autoimport_job.py`'s
    `_resolve_extractor_python`, which executes `<source_dir's parent>/.venv/
    .../python.exe`), an unconfined path let the `/api/plan/monarch-
    autoupdate/config` route (which passes request bodies straight through
    to `save_policy`) select an arbitrary interpreter to execute.
    """


def _confine_to_workspace(base_dir: str | Path, raw: str) -> Path:
    base = Path(base_dir).resolve()
    p = Path(raw).expanduser()
    resolved = (p if p.is_absolute() else (base / p)).resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise SourceDirOutsideWorkspaceError(
            f"source_dir must resolve to a path inside the workspace root ({base}); got {resolved}"
        ) from None
    return resolved


def resolve_source_dir(base_dir: str | Path, policy: dict[str, Any] | AutoUpdatePolicy | None = None) -> Path:
    raw = DEFAULT_SOURCE_DIR
    if isinstance(policy, AutoUpdatePolicy):
        raw = policy.source_dir
    elif isinstance(policy, dict):
        raw = str(policy.get("source_dir") or DEFAULT_SOURCE_DIR)
    return _confine_to_workspace(base_dir, raw)


def normalize_policy(data: dict[str, Any] | None = None, *, base_dir: str | Path | None = None) -> AutoUpdatePolicy:
    data = data or {}
    source_dir = str(data.get("source_dir") or DEFAULT_SOURCE_DIR).strip() or DEFAULT_SOURCE_DIR
    if base_dir is not None:
        # Validate confinement eagerly (at save time) rather than only at
        # resolve/execution time, so a bad value is rejected with a clear
        # error instead of silently persisted and only failing later.
        _confine_to_workspace(base_dir, source_dir)
    field_map_path = str(data.get("field_map_path") or "").strip()
    return AutoUpdatePolicy(
        enabled=bool(data.get("enabled", False)),
        source_dir=source_dir,
        field_map_path=field_map_path,
    )


def load_policy(base_dir: str | Path) -> dict[str, Any]:
    path = settings_path(base_dir)
    raw: dict[str, Any] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
    # Not confinement-checked on load: a value already on disk must still be
    # readable (e.g. to display it back for correction) even if it would now
    # be rejected on save; only save_policy (new/updated values) enforces it.
    policy = normalize_policy(raw.get("policy") if isinstance(raw.get("policy"), dict) else raw)
    return {"schema": SCHEMA, "policy": policy.as_dict(), "settings_path": str(path)}


def save_policy(base_dir: str | Path, updates: dict[str, Any]) -> dict[str, Any]:
    """Raises SourceDirOutsideWorkspaceError if `updates` sets a `source_dir`
    that would resolve outside the workspace root."""
    current = load_policy(base_dir)["policy"]
    merged = dict(current)
    for key in ("enabled", "source_dir", "field_map_path"):
        if key in updates:
            merged[key] = updates[key]
    policy = normalize_policy(merged, base_dir=base_dir)
    payload = {"schema": SCHEMA, "policy": policy.as_dict(), "updated_at": iso_utc()}
    path = settings_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return load_policy(base_dir)


def load_status(base_dir: str | Path) -> dict[str, Any] | None:
    path = status_path(base_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if data.get("schema") == STATUS_SCHEMA else None


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
    """Write the "mark the update as complete" status file for one run."""
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
    path = status_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _run_registration_script(script: Path, action: str) -> dict[str, Any]:
    if not script.exists():
        return {"attempted": False, "success": False, "error": f"Registration script not found: {script}"}
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Action", action],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return {"attempted": True, "success": proc.returncode == 0, "error": None if proc.returncode == 0 else proc.stderr.strip()}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"attempted": True, "success": False, "error": str(exc)}


def register_scheduled_task(base_dir: str | Path, enabled: bool) -> dict[str, Any]:
    """Best-effort sync of the OS-level Task Scheduler entries with the
    in-app toggle, via the PowerShell helper scripts.

    Registers/unregisters *two* tasks, not one: the downstream import
    (tools/monarch_autoimport.py, 4am) and the extractor itself (Monarch
    Extractor/run_monarch.ps1, 3:30am -- see that script's own header for
    why this one exists). Before 2026-09, only the import task was wired
    to this toggle; the extractor was never scheduled anywhere, so nothing
    ever refreshed the data the import job reads. Both are now driven by
    the same toggle so enabling "Monarch auto-update" always yields a
    complete, self-refreshing pipeline rather than half of one.

    Never raises: a registration failure (non-Windows dev machine, no
    PowerShell, insufficient privilege) must not block saving the toggle
    itself -- the caller surfaces {"attempted", "success", "error"} to the
    UI's status chip instead.
    """
    if sys.platform != "win32":
        return {"attempted": False, "success": False, "error": "Not running on Windows; scheduled-task registration skipped."}
    action = "Register" if enabled else "Unregister"
    results = {
        "extract": _run_registration_script(
            Path(base_dir) / "Monarch Extractor" / "register_monarch_extract_task.ps1", action
        ),
        "import": _run_registration_script(
            Path(base_dir) / "tools" / "launchers" / "register_monarch_autoimport_task.ps1", action
        ),
    }
    attempted = any(r["attempted"] for r in results.values())
    success = attempted and all(r["success"] for r in results.values() if r["attempted"])
    errors = [f"{name}: {r['error']}" for name, r in results.items() if r["attempted"] and not r["success"]]
    return {
        "attempted": attempted,
        "success": success,
        "error": "; ".join(errors) or None,
        "details": results,
    }
