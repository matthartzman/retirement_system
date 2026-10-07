#!/usr/bin/env python3
from __future__ import annotations
"""Synchronize the local plan file and the JSON/YAML mirrors from the Plan Data CSV set.

Split client_*.csv files are still the files the writers edit (until WP4.3-4.5);
client_data.csv is the anchor. This tool carries the CSV set into the active plan file
(``plan.rpx``, the rows the engine reads; WP4.2) and rewrites the JSON/YAML mirrors.
P3.5 deletes it.

Run from project root:
    python tools/sync_config_backends.py
"""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.active_plan import active_plan_path, sync_active_plan_from_csv  # noqa: E402
from src.config_backend import DEFAULT_CSV, export_client_json_yaml  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync the Plan Data CSV set into the plan file and JSON/YAML mirrors.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="Plan Data anchor CSV (client_data.csv)")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = Path(__file__).resolve().parent.parent / csv_path
    if not csv_path.exists():
        raise SystemExit(f"CSV config not found: {csv_path}")

    synced = sync_active_plan_from_csv(csv_path.parent)
    exports = export_client_json_yaml(synced.data, csv_path.parent)

    print("Configuration sync complete")
    print(f"  Source CSV: {csv_path}")
    for name, path in sorted(exports.items()):
        print(f"  {name}: {path}")
    print(f"  Plan file:  {active_plan_path()} {synced.counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
