#!/usr/bin/env python3
"""Remove bad snapshots (e.g. taken while plan tables were empty) from the trends log.

Dry run by default; add --apply to rewrite. The original is kept as <log>.bak.

  python financial_trends_reporter/tools/prune_trends_log.py 2026-10-08 2026-10-12          # preview
  python financial_trends_reporter/tools/prune_trends_log.py 2026-10-08 2026-10-12 --apply  # do it
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

from financial_trends_reporter.trends_log import default_log_path, prune_entries  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("start", help="first as_of_date to remove (YYYY-MM-DD)")
    ap.add_argument("end", nargs="?", help="last as_of_date to remove (default: same as start)")
    ap.add_argument("--log", default=str(default_log_path(_APP_ROOT)), help="log file (default: the app's own)")
    ap.add_argument("--apply", action="store_true", help="rewrite the log (default is a preview)")
    args = ap.parse_args(argv)
    try:
        date.fromisoformat(args.start)
        date.fromisoformat(args.end or args.start)
    except ValueError:
        ap.error("dates must be YYYY-MM-DD")
    if not Path(args.log).is_file():
        ap.error(f"no log at {args.log}")
    hit = prune_entries(args.log, args.start, args.end, dry_run=not args.apply)
    verb = "removed" if args.apply else "would remove"
    print(f"{verb} {len(hit)} entr{'y' if len(hit) == 1 else 'ies'}: {', '.join(hit) or '-'}")
    if args.apply and hit:
        print(f"backup: {args.log}.bak")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
