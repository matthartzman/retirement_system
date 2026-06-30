from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.local_plan_data_sync import sync_plan_data_from_folder


def main() -> None:
    parser = argparse.ArgumentParser(description="Load local Plan Data CSVs into the app working copy before a build.")
    parser.add_argument("folder", help="Folder containing client_data.csv, client_holdings.csv, and optional Plan Data CSVs")
    parser.add_argument("--allow-missing-required", action="store_true", help="Do not fail if client_data.csv or client_holdings.csv is missing")
    args = parser.parse_args()
    result = sync_plan_data_from_folder(args.folder, ROOT, require_required=not args.allow_missing_required)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
