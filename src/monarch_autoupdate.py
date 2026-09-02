from __future__ import annotations

"""Opt-in Monarch auto-update policy + run status (ticket 305).

Shaped after src/local_backup_scheduler.py's policy-file pattern for
consistency. Unlike that scheduler, the actual daily trigger is external
(Windows Task Scheduler invoking tools/monarch_autoimport.py headlessly at
4am) -- this module only owns the enabled/config state and the last-run
status, not the timing itself.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "monarch_autoupdate_v1"
STATUS_SCHEMA = "monarch_autoupdate_status_v1"
SETTINGS_FILENAME = "monarch_autoupdate.json"
STATUS_FILENAME = "monarch_autoupdate_status.json"
DEFAULT_SOURCE_DIR = "../Monarch Extractor/output"


@dataclass(frozen=True)
class AutoUpdatePolicy:
    enabled: bool = False
    source_dir: str = DEFAULT_SOURCE_DIR
    field_map_path: str = ""  # "" = use the shipped default (src/monarch_field_map.json)
    archive_consumed_files: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "source_dir": self.source_dir,
            "field_map_path": self.field_map_path,
            "archive_consumed_files": self.archive_consumed_files,
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


def resolve_source_dir(base_dir: str | Path, policy: dict[str, Any] | AutoUpdatePolicy | None = None) -> Path:
    raw = DEFAULT_SOURCE_DIR
    if isinstance(policy, AutoUpdatePolicy):
        raw = policy.source_dir
    elif isinstance(policy, dict):
        raw = str(policy.get("source_dir") or DEFAULT_SOURCE_DIR)
    p = Path(raw).expanduser()
    return p if p.is_absolute() else (Path(base_dir) / p).resolve()


def normalize_policy(data: dict[str, Any] | None = None) -> AutoUpdatePolicy:
    data = data or {}
    source_dir = str(data.get("source_dir") or DEFAULT_SOURCE_DIR).strip() or DEFAULT_SOURCE_DIR
    field_map_path = str(data.get("field_map_path") or "").strip()
    return AutoUpdatePolicy(
        enabled=bool(data.get("enabled", False)),
        source_dir=source_dir,
        field_map_path=field_map_path,
        archive_consumed_files=bool(data.get("archive_consumed_files", True)),
    )


def load_policy(base_dir: str | Path) -> dict[str, Any]:
    path = settings_path(base_dir)
    raw: dict[str, Any] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
    policy = normalize_policy(raw.get("policy") if isinstance(raw.get("policy"), dict) else raw)
    return {"schema": SCHEMA, "policy": policy.as_dict(), "settings_path": str(path)}


def save_policy(base_dir: str | Path, updates: dict[str, Any]) -> dict[str, Any]:
    current = load_policy(base_dir)["policy"]
    merged = dict(current)
    for key in ("enabled", "source_dir", "field_map_path", "archive_consumed_files"):
        if key in updates:
            merged[key] = updates[key]
    policy = normalize_policy(merged)
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
