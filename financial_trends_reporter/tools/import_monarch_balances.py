#!/usr/bin/env python3
"""Headless import of the Monarch Extractor's balances.csv into the balance store.

Run right after monarch_balances.py in the 03:30 extraction chain (run_monarch.ps1), and
also by the trends job so an update picks up a fresh file. Stdlib only.

Usage: python financial_trends_reporter/tools/import_monarch_balances.py [--retirement-system-dir PATH]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _APP_ROOT.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from financial_trends_reporter.app_sync import sync_from_app  # noqa: E402
from financial_trends_reporter.balance_store import default_db_path, default_source_path, import_balances  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--retirement-system-dir", default=str(_REPO_ROOT))
    args = parser.parse_args(argv)
    db = default_db_path(_APP_ROOT)
    result = import_balances(db, default_source_path(args.retirement_system_dir))
    print(result)
    print({"app_sync": sync_from_app(db, args.retirement_system_dir)})  # best effort; never changes the exit code
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
