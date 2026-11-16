"""The gateway's health report: what an admin (or ``ops health``) needs to see at a glance.

Names no folder paths and no user data: volumes are labelled ``data`` and ``backups``.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Callable

LOW_FREE_FRACTION = 0.10
LOW_FREE_BYTES = 5 * 1024**3
BACKUP_STALE_FACTOR = 2.0


def disk_report(path: Path | None) -> dict | None:
    if path is None:
        return None
    probe = Path(path)
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        usage = shutil.disk_usage(probe)
    except OSError:
        return {"error": "unavailable"}
    free_fraction = usage.free / usage.total if usage.total else 0.0
    return {"free_bytes": usage.free, "total_bytes": usage.total, "free_fraction": round(free_fraction, 4),
            "low": usage.free < LOW_FREE_BYTES or free_fraction < LOW_FREE_FRACTION}


def build_health(*, started_at: float, schema_version: int | None, workers_running: int | None,
                 build_running: int | None, build_waiting: int | None, data_root: Path | None,
                 backup_dir: Path | None, backups=None, backup_interval: float = 86400.0,
                 clock: Callable[[], float] = time.time) -> dict:
    now = clock()
    warnings: list[str] = []
    data_disk, backup_disk = disk_report(data_root), disk_report(backup_dir)
    for label, disk in (("data", data_disk), ("backup", backup_disk)):
        if disk and disk.get("low"):
            warnings.append(f"low free space on the {label} volume")
    backup: dict
    if backups is None:
        backup = {"configured": False}
        warnings.append("no backups are configured")
    else:
        last = backups.last_result()
        newest = backups.newest_full_epoch() if hasattr(backups, "newest_full_epoch") else None
        age = (now - newest) if newest else None
        backup = {"configured": True, "last_run_at": last.get("at"), "last_ok": last.get("ok"),
                  "last_users": last.get("users"), "last_errors": len(last.get("errors") or []),
                  "newest_archive_age_seconds": round(age) if age is not None else None}
        if last.get("ok") is False:
            warnings.append("the last backup reported errors")
        if age is None or age > backup_interval * BACKUP_STALE_FACTOR:
            warnings.append("there is no recent complete backup")
    return {"status": "warning" if warnings else "ok", "warnings": warnings,
            "uptime_seconds": round(now - started_at), "schema_version": schema_version,
            "workers": {"running": workers_running},
            "build_queue": {"running": build_running, "waiting": build_waiting},
            "disk": {"data": data_disk, "backups": backup_disk}, "backup": backup}
