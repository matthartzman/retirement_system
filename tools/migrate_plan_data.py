#!/usr/bin/env python3
"""Phase C: Plan data schema migration (v0 → v1).

Safely migrates v0 plan files to v1 (unified spending model, healthcare terminology).

Usage:
    python tools/migrate_plan_data.py input/client_data.csv
    python tools/migrate_plan_data.py --verify                    # Check status
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def get_schema_version(file_path: Path) -> str | None:
    """Check schema version of a plan file."""
    if not file_path.exists():
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for _ in range(100):
                line = f.readline()
                if not line or 'schema_version' in line:
                    return 'v1' if 'schema_version' in line else 'v0'
        return 'v0'
    except Exception:
        return None


def create_plan_metadata(csv_file: Path) -> dict:
    """Create or update plan metadata with schema version."""
    metadata_file = csv_file.parent / 'plan_metadata.json'

    if metadata_file.exists():
        try:
            return json.loads(metadata_file.read_text())
        except Exception:
            pass

    return {
        'schema_version': 'v1',
        'migration_timestamp': datetime.now().isoformat(),
        'migrator_version': '1.0',
    }


def migrate_plan_file(csv_file: Path, backup: bool = True) -> bool:
    """Migrate a single plan CSV file from v0 to v1."""
    if not csv_file.exists():
        print(f"✗ File not found: {csv_file}")
        return False

    current = get_schema_version(csv_file)
    if current == 'v1':
        print(f"✓ Already v1: {csv_file}")
        return True

    # Create backup
    if backup:
        backup_file = csv_file.with_suffix(csv_file.suffix + '.v0.backup')
        if not backup_file.exists():
            try:
                backup_file.write_bytes(csv_file.read_bytes())
                print(f"✓ Backup: {backup_file.name}")
            except Exception as e:
                print(f"✗ Backup failed: {e}")
                return False

    # Add schema version marker to CSV
    try:
        content = csv_file.read_text(encoding='utf-8')
        if 'schema_version' not in content:
            lines = content.split('\n')
            # Add schema_version row after header if in section format
            if lines and 'section' in lines[0].lower():
                insert_idx = 1
                while insert_idx < len(lines) and lines[insert_idx].strip():
                    insert_idx += 1
                lines.insert(insert_idx, 'plan_metadata,schema_version,,v1')
                content = '\n'.join(lines)
            csv_file.write_text(content, encoding='utf-8')
        print(f"✓ Migrated to v1: {csv_file.name}")

        # Create metadata file
        metadata = create_plan_metadata(csv_file)
        metadata_file = csv_file.parent / 'plan_metadata.json'
        metadata_file.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        print(f"✓ Metadata: {metadata_file.name}")

        return True
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Phase C: Migrate plan data schema v0 → v1')
    parser.add_argument('file', nargs='?', help='CSV file to migrate')
    parser.add_argument('--verify', action='store_true', help='Check status only')
    parser.add_argument('--all', action='store_true', help='Migrate all files in input/')
    parser.add_argument('--no-backup', action='store_true', help='Skip backups')

    args = parser.parse_args()

    if not args.file and not args.all and not args.verify:
        parser.print_help()
        return 1

    success = 0
    failed = 0

    if args.verify:
        if args.file:
            status = get_schema_version(Path(args.file))
            print(f"{args.file}: {status or 'unknown'}")
        elif args.all:
            input_dir = ROOT / 'input'
            for csv_file in sorted(input_dir.glob('client*.csv')):
                status = get_schema_version(csv_file)
                print(f"{csv_file.name}: {status or 'unknown'}")
        return 0

    if args.file:
        if migrate_plan_file(Path(args.file), backup=not args.no_backup):
            success += 1
        else:
            failed += 1
    elif args.all:
        input_dir = ROOT / 'input'
        for csv_file in sorted(input_dir.glob('client*.csv')):
            if migrate_plan_file(csv_file, backup=not args.no_backup):
                success += 1
            else:
                failed += 1

    print(f"\n{'='*50}")
    print(f"Result: {success} migrated, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
