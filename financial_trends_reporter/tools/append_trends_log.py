#!/usr/bin/env python3
"""Headless weekday-5pm financial trends log job (ticket 306).

Run by a Windows Task Scheduler entry, Monday-Friday at 5pm (see
tools/launchers/register_trends_report_task.ps1), or manually for a one-off
snapshot. Computes YTD expenses by category, holdings value/performance,
net worth, and cashflow from the retirement_system workspace and appends
(or overwrites today's existing line in) the JSONL trend log.

Usage:
  python financial_trends_reporter/tools/append_trends_log.py --retirement-system-dir PATH
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _APP_ROOT.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from financial_trends_reporter.trends_job import run  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--retirement-system-dir",
        default=str(_REPO_ROOT),
        help="retirement_system workspace root (contains input/, local_state/); defaults to this repo's own root",
    )
    args = parser.parse_args(argv)
    result = run(Path(args.retirement_system_dir))
    print(result)
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
