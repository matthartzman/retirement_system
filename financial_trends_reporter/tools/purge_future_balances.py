#!/usr/bin/env python3
"""Remove balance rows dated in the future from the Monarch balances database.

An import from before the F-02 date bound could leave rows dated years ahead (one 2099 row deactivates every other
account and collapses net worth). Dry run by default: it lists what would go. ``--apply`` first copies the whole
database into ``data/snapshots/`` (SQLite backup API), then deletes the rows and recomputes each account's first and
last seen and its active flag. Rows dated today or tomorrow are never touched.

  python financial_trends_reporter/tools/purge_future_balances.py            # preview
  python financial_trends_reporter/tools/purge_future_balances.py --apply    # do it
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _APP_ROOT.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from financial_trends_reporter.balance_store import default_db_path, purge_future_rows  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(default_db_path(_APP_ROOT)), help="balances database (default: the app's own)")
    ap.add_argument("--today", help="treat this ISO date as today (testing)")
    ap.add_argument("--apply", action="store_true", help="delete the rows (default is a preview)")
    args = ap.parse_args(argv)
    if not Path(args.db).is_file():
        ap.error(f"no database at {args.db}")
    today = date.fromisoformat(args.today) if args.today else None
    res = purge_future_rows(args.db, today=today, apply=args.apply)
    verb = "removed" if res["applied"] else "would remove"
    print(f"{verb} {res['rows']} row(s) dated after {res['ceiling']}; dates: {', '.join(res['dates'][:10]) or '-'}"
          f"{' ...' if len(res['dates']) > 10 else ''}; accounts: {len(res['accounts'])}")
    if res["applied"] and res["snapshot"]:
        print(f"snapshot of the database before the purge: {res['snapshot']}")
    if not args.apply and res["rows"]:
        print("preview only; re-run with --apply to delete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
