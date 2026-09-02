#!/usr/bin/env python3
"""Headless daily Monarch auto-import job (ticket 305).

Run by a Windows Task Scheduler entry at 4am (see
tools/launchers/register_monarch_autoimport_task.ps1), or manually for a
one-off catch-up import (`--force` runs even if the in-app toggle is off).
Does NOT require the desktop app or its HTTP server to be running.

Steps:
  1. Load the auto-update policy (local_state/monarch_autoupdate.json).
     Skip if disabled and --force was not passed.
  2. OneDrive-truncation guard on every source CSV before reading any of them.
  3. Read + map every *.csv in the Monarch Extractor's output folder.
  4. Upsert (replace changed / add new / no-op unchanged) into
     input/ytd_transactions.csv, keyed on the stored Monarch id.
  5. Push the updated YTD CSVs into the SQLite plan-data store so the running
     desktop app (which reads the DB first) sees the update.
  6. Archive consumed source files (if the policy says to) and write the
     "mark the update as complete" status file + an ytd_import_history.csv row.

Usage: python tools/monarch_autoimport.py [--base-dir PATH] [--force]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import monarch_autoupdate as mau  # noqa: E402
from src import monarch_db_sync  # noqa: E402
from src import monarch_import as mi  # noqa: E402
from src import onedrive_guard  # noqa: E402
from src import ytd_tracking as ytd  # noqa: E402


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


def run(base_dir: Path, *, force: bool = False) -> dict[str, Any]:
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
        # Nothing usable this run -- not necessarily a failure (an empty
        # output folder is the normal "nothing new today" state), but any
        # per-file mapping errors are still surfaced, not swallowed.
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-dir", default=str(Path(__file__).resolve().parent.parent), help="Workspace root (contains input/, local_state/)")
    parser.add_argument("--force", action="store_true", help="Run even if the in-app auto-update toggle is disabled")
    args = parser.parse_args(argv)
    result = run(Path(args.base_dir), force=args.force)
    print(result)
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
