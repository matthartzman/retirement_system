"""Opt-in local backup scheduler for the v10 desktop/local planner.

The scheduler is intentionally opportunistic: the UI or routes call it after
save/build events or when the user clicks "Back up now". It does not run a
background thread and it does not mutate plan data beyond writing retention-
limited backup copies.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any

SCHEMA = "local_backup_scheduler_v1"
SETTINGS_FILENAME = "backup_scheduler.json"
DEFAULT_BACKUP_DIR = "saved_plans/auto_backups"
DEFAULT_RETENTION_COUNT = 7
VALID_CADENCES = {"daily", "per_build"}


@dataclass(frozen=True)
class BackupPolicy:
    enabled: bool = False
    cadence: str = "daily"
    retention_count: int = DEFAULT_RETENTION_COUNT
    backup_dir: str = DEFAULT_BACKUP_DIR

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "cadence": self.cadence,
            "retention_count": self.retention_count,
            "backup_dir": self.backup_dir,
        }


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def utc_stamp(dt: datetime | None = None) -> str:
    dt = dt or now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%d_%H%M%S")


def iso_utc(dt: datetime | None = None) -> str:
    dt = dt or now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def settings_path(base_dir: str | Path) -> Path:
    return Path(base_dir) / "local_state" / SETTINGS_FILENAME


def resolve_backup_dir(base_dir: str | Path, policy: dict[str, Any] | BackupPolicy | None = None) -> Path:
    raw = DEFAULT_BACKUP_DIR
    if isinstance(policy, BackupPolicy):
        raw = policy.backup_dir
    elif isinstance(policy, dict):
        raw = str(policy.get("backup_dir") or DEFAULT_BACKUP_DIR)
    p = Path(raw).expanduser()
    return p if p.is_absolute() else Path(base_dir) / p


def normalize_policy(data: dict[str, Any] | None = None) -> BackupPolicy:
    data = data or {}
    cadence = str(data.get("cadence") or "daily").strip().lower()
    if cadence not in VALID_CADENCES:
        cadence = "daily"
    try:
        retention = int(data.get("retention_count", DEFAULT_RETENTION_COUNT))
    except Exception:
        retention = DEFAULT_RETENTION_COUNT
    retention = max(1, min(60, retention))
    backup_dir = str(data.get("backup_dir") or DEFAULT_BACKUP_DIR).strip() or DEFAULT_BACKUP_DIR
    return BackupPolicy(
        enabled=bool(data.get("enabled", False)),
        cadence=cadence,
        retention_count=retention,
        backup_dir=backup_dir,
    )


def load_policy(base_dir: str | Path) -> dict[str, Any]:
    path = settings_path(base_dir)
    raw: dict[str, Any] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
    policy = normalize_policy(raw.get("policy") if isinstance(raw.get("policy"), dict) else raw)
    return {
        "schema": SCHEMA,
        "policy": policy.as_dict(),
        "settings_path": str(path),
    }


def save_policy(base_dir: str | Path, updates: dict[str, Any]) -> dict[str, Any]:
    current = load_policy(base_dir)["policy"]
    merged = dict(current)
    for key in ("enabled", "cadence", "retention_count", "backup_dir"):
        if key in updates:
            merged[key] = updates[key]
    policy = normalize_policy(merged)
    payload = {"schema": SCHEMA, "policy": policy.as_dict(), "updated_at": iso_utc()}
    path = settings_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return load_policy(base_dir)


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def checkpoint_sqlite(db_path: str | Path) -> None:
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("PRAGMA wal_checkpoint(FULL)")
        finally:
            conn.close()
    except Exception:
        # Backups should still proceed for plain database files or locked WALs.
        return


def _read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") == SCHEMA:
            return data
    except Exception:
        return None
    return None


def list_backups(base_dir: str | Path, policy: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    policy = policy or load_policy(base_dir)["policy"]
    bdir = resolve_backup_dir(base_dir, policy)
    backups: list[dict[str, Any]] = []
    if not bdir.exists():
        return backups
    for manifest_path in sorted(bdir.glob("*.manifest.json")):
        data = _read_manifest(manifest_path)
        if not data:
            continue
        db_file = bdir / str(data.get("filename") or "")
        data = dict(data)
        data["manifest_path"] = str(manifest_path)
        data["path"] = str(db_file)
        data["exists"] = db_file.exists()
        backups.append(data)
    backups.sort(key=lambda x: str(x.get("created_at") or ""))
    return backups


def latest_backup(base_dir: str | Path, policy: dict[str, Any] | None = None) -> dict[str, Any] | None:
    backups = list_backups(base_dir, policy)
    return backups[-1] if backups else None


def is_due(base_dir: str | Path, policy: dict[str, Any], now: datetime | None = None) -> tuple[bool, str]:
    if not bool(policy.get("enabled")):
        return False, "disabled"
    latest = latest_backup(base_dir, policy)
    if not latest:
        return True, "no_previous_backup"
    cadence = str(policy.get("cadence") or "daily")
    if cadence == "per_build":
        return True, "per_build"
    now = now or now_utc()
    created = str(latest.get("created_at") or "")
    today = iso_utc(now)[:10]
    if not created.startswith(today):
        return True, "daily_window"
    return False, "already_backed_up_today"


def scheduler_status(base_dir: str | Path, db_path: str | Path, now: datetime | None = None) -> dict[str, Any]:
    loaded = load_policy(base_dir)
    policy = loaded["policy"]
    backups = list_backups(base_dir, policy)
    due, reason = is_due(base_dir, policy, now=now)
    db = Path(db_path)
    return {
        "schema": SCHEMA,
        "success": True,
        "policy": policy,
        "settings_path": loaded["settings_path"],
        "backup_dir": str(resolve_backup_dir(base_dir, policy)),
        "source_db": str(db),
        "source_db_exists": db.exists(),
        "backup_count": len(backups),
        "latest_backup": backups[-1] if backups else None,
        "due": due,
        "due_reason": reason,
    }


def _backup_filename(db_path: Path, stamp: str) -> str:
    stem = db_path.stem or "retirement_system_v10"
    return f"{stem}.auto_{stamp}.rpx"


def prune_backups(base_dir: str | Path, policy: dict[str, Any]) -> list[str]:
    retention = normalize_policy(policy).retention_count
    backups = list_backups(base_dir, policy)
    pruned: list[str] = []
    for item in backups[:-retention]:
        for key in ("path", "manifest_path"):
            p = Path(str(item.get(key) or ""))
            if p.exists():
                try:
                    p.unlink()
                    pruned.append(str(p))
                except Exception:
                    pass
    return pruned


def run_backup(
    base_dir: str | Path,
    db_path: str | Path,
    trigger: str = "manual",
    force: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or now_utc()
    status = scheduler_status(base_dir, db_path, now=now)
    policy = status["policy"]
    if not force and not status["due"]:
        return {**status, "created": False, "skipped": True, "skip_reason": status["due_reason"]}
    if not force and not bool(policy.get("enabled")):
        return {**status, "created": False, "skipped": True, "skip_reason": "disabled"}

    src = Path(db_path)
    if not src.exists():
        return {**status, "success": False, "created": False, "error": "Source SQLite database does not exist."}

    bdir = resolve_backup_dir(base_dir, policy)
    bdir.mkdir(parents=True, exist_ok=True)
    checkpoint_sqlite(src)
    stamp = utc_stamp(now)
    filename = _backup_filename(src, stamp)
    target = bdir / filename
    # Avoid collision in rapid tests/manual clicks.
    suffix = 1
    while target.exists():
        filename = _backup_filename(src, f"{stamp}_{suffix}")
        target = bdir / filename
        suffix += 1
    shutil.copy2(str(src), str(target))
    digest = sha256_file(target)
    manifest = {
        "schema": SCHEMA,
        "created_at": iso_utc(now),
        "trigger": str(trigger or "manual"),
        "filename": filename,
        "source_db": str(src),
        "size_bytes": target.stat().st_size,
        "sha256": digest,
        "policy": dict(policy),
    }
    manifest_path = target.with_suffix(target.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    pruned = prune_backups(base_dir, policy)
    refreshed = scheduler_status(base_dir, db_path, now=now)
    return {
        **refreshed,
        "created": True,
        "skipped": False,
        "backup": {**manifest, "path": str(target), "manifest_path": str(manifest_path), "exists": True},
        "pruned": pruned,
        "pruned_count": len(pruned),
    }
