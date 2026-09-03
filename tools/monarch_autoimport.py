#!/usr/bin/env python3
"""Headless daily Monarch auto-import job (ticket 305).

Run by a Windows Task Scheduler entry at 4am (see
tools/launchers/register_monarch_autoimport_task.ps1), or manually for a
one-off catch-up import (`--force` runs even if the in-app toggle is off).
Does NOT require the desktop app or its HTTP server to be running.

The actual job logic lives in src/monarch_autoimport_job.py, shared with the
server's "run now" route so a manual in-app trigger and this scheduled run
take the same code path.

Steps: load the auto-update policy -> OneDrive-truncation guard on every
source CSV -> read + map every *.csv in the Monarch Extractor's output
folder -> upsert into ytd_transactions.csv keyed on the stored Monarch id ->
push the updated YTD CSVs into the SQLite plan-data store (the app's
canonical storage; a headless script has no Flask request context to go
through the normal save path) -> archive consumed source files -> write the
"mark the update as complete" status file + an ytd_import_history.csv row.

Usage: python tools/monarch_autoimport.py [--base-dir PATH] [--force]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.monarch_autoimport_job import run  # noqa: E402


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
