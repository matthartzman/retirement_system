#!/usr/bin/env python3
from __future__ import annotations
"""Synchronize v10 local Plan Data configuration backends.

Split client_*.csv files are the portable, human-editable Plan Data adapters
because they preserve section comments, units, and notes. client_data.csv is a
manifest/anchor file. This tool exports the current CSV settings to JSON, YAML,
and SQLite so local backends have the same values.

Run from project root:
    python tools/sync_config_backends.py

Optional:
    python tools/sync_config_backends.py --workspace-id demo
"""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config_backend import (  # noqa: E402
    DEFAULT_DB,
    DEFAULT_CSV,
    DEFAULT_JSON,
    DEFAULT_YAML,
    import_csv_to_sqlite,
    load_csv,
    save_json,
    save_yaml,
    init_sqlite,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync split client Plan Data CSVs to JSON/YAML/SQLite backends.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="Canonical CSV config path")
    parser.add_argument("--json", default=str(DEFAULT_JSON), help="JSON export path")
    parser.add_argument("--yaml", default=str(DEFAULT_YAML), help="YAML export path")
    parser.add_argument("--sqlite-db", default=str(DEFAULT_DB), help="SQLite backend path")
    parser.add_argument("--workspace-id", default="local", help="SQLite workspace_id to sync")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = Path(__file__).resolve().parent.parent / csv_path
    if not csv_path.exists():
        raise SystemExit(f"CSV config not found: {csv_path}")

    data = load_csv(csv_path)
    json_path = save_json(data, args.json)
    yaml_path = save_yaml(data, args.yaml)
    db_path = init_sqlite(args.sqlite_db)
    import_csv_to_sqlite(csv_path, db_path, workspace_id=args.workspace_id)

    print("Configuration sync complete")
    print(f"  Source CSV: {csv_path}")
    print(f"  JSON:       {json_path}")
    print(f"  YAML:       {yaml_path}")
    print(f"  SQLite:     {db_path} workspace_id={args.workspace_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
