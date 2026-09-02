from __future__ import annotations

"""The Monarch auto-import job logic (ticket 305), importable both from the
headless CLI entry point (tools/monarch_autoimport.py, run by Windows Task
Scheduler at 4am) and from the server's "run now" route
(src/server/plan_routes.py), so a manual in-app trigger and the unattended
scheduled run share one code path.
"""

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import monarch_autoupdate as mau
from . import monarch_db_sync
from . import monarch_import as mi
from . import onedrive_guard
from . import ytd_tracking as ytd


def _archive_consumed_files(source_dir: Path, filenames: list[str]) -> None:
    if not filenames:
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = source_dir / "imported" / stamp
    archive_dir.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        src = source_dir / name
        if src.exists():
            shutil.move(str(src), str(archive_dir / name))


def run(base_dir: str | Path, *, force: bool = False) -> dict[str, Any]:
    base_dir = Path(base_dir)
    loaded = mau.load_policy(base_dir)
    policy = loaded["policy"]
    if not policy["enabled"] and not force:
        return {"success": True, "skipped": True, "skip_reason": "disabled"}

    field_map = mi.load_field_map(policy["field_map_path"] or None)
    source_dir = mau.resolve_source_dir(base_dir, policy)

    if source_dir.exists():
        guard_errors = onedrive_guard.check_files_safe_to_read(sorted(source_dir.glob("*.csv")))
        if guard_errors:
            status = mau.write_status(base_dir, success=False, errors=guard_errors)
            return {"success": False, "status": status}

    result = mi.read_monarch_output_folder(source_dir, field_map)
    file_errors = [f"{name}: {'; '.join(msgs)}" for name, msgs in result["errors"].items()]

    if not result["rows"] and not result["files_consumed"]:
        status = mau.write_status(base_dir, success=not file_errors, errors=file_errors)
        return {"success": not file_errors, "skipped": True, "skip_reason": "no_rows", "status": status}

    input_dir = base_dir / "input"
    upsert_result = ytd.upsert_transactions_by_monarch_id(input_dir, result["rows"])

    db_path = base_dir / "local_state" / "retirement_system_v10.db"
    monarch_db_sync.sync_ytd_files_to_db(input_dir, db_path)

    if policy["archive_consumed_files"]:
        _archive_consumed_files(source_dir, result["files_consumed"])

    status = mau.write_status(
        base_dir,
        success=True,
        files_consumed=result["files_consumed"],
        rows_added=upsert_result["added"],
        rows_updated=upsert_result["updated"],
        rows_skipped=upsert_result["skipped"],
        errors=file_errors,
    )
    return {"success": True, "upsert": upsert_result, "status": status}
