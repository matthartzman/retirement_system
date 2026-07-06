#!/usr/bin/env python3
"""Create a timestamped ZIP backup of the whole project into OneDrive.

This is the off-site safety net now that the working copy lives on the local
C: drive (outside OneDrive) to avoid OneDrive sync corruption.  It is invoked
automatically at the end of every build by ``build.py`` ("backup after every
rebuild"), and can also be run by hand:

    python tools/backup_to_onedrive.py

Backup destination is resolved in this order:
  1. env var  RP_BACKUP_DIR                      (explicit override)
  2. <OneDriveCommercial or OneDrive>/5-Personal/Hartzman Vault/Retirement Planning/Backups
  3. a local fallback under the current user's home directory, so this script
     never fails or requires machine-specific configuration

The zip contains EVERYTHING including the built exe (dist/), per the chosen
backup policy.  Only throwaway caches are skipped (see EXCLUDE_DIRS).
"""
from __future__ import annotations

import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Directory names skipped anywhere in the tree.  These are pure regenerable
# caches / intermediate build artifacts -- never user data.  dist/ (the built
# exe) is intentionally NOT excluded.
EXCLUDE_DIRS = {"build", "__pycache__", ".pytest_cache", ".git"}

# Keep at most this many backups in the destination; older ones are pruned.
KEEP_LAST = 10

BACKUP_PREFIX = "retirement_v10_"


def resolve_backup_dir() -> Path:
    override = os.environ.get("RP_BACKUP_DIR")
    if override:
        return Path(override)

    onedrive = os.environ.get("OneDriveCommercial") or os.environ.get("OneDrive")
    if onedrive:
        candidate = (
            Path(onedrive)
            / "5-Personal"
            / "Hartzman Vault"
            / "Retirement Planning"
            / "Backups"
        )
        # Only accept it if the OneDrive "Retirement Planning" parent exists.
        if candidate.parent.parent.exists():
            return candidate

    # Last-resort fallback: a local, portable location under the current
    # user's home directory. Works on any machine/OS with no configuration.
    return Path.home() / "RetirementPlannerBackups"


def iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        # prune excluded dirs in place so os.walk doesn't descend into them
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            yield Path(dirpath) / name


def prune_old(backup_dir: Path) -> None:
    zips = sorted(
        backup_dir.glob(f"{BACKUP_PREFIX}*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for stale in zips[KEEP_LAST:]:
        try:
            stale.unlink()
            print(f"  pruned old backup: {stale.name}")
        except OSError as exc:  # noqa: BLE001
            print(f"  could not prune {stale.name}: {exc}", file=sys.stderr)


def main() -> int:
    backup_dir = resolve_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_path = backup_dir / f"{BACKUP_PREFIX}{stamp}.zip"
    tmp_path = final_path.with_suffix(".zip.tmp")

    print(f"Backing up {PROJECT_ROOT}")
    print(f"        -> {final_path}")

    count = 0
    total = 0
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for fpath in iter_files(PROJECT_ROOT):
                # never include a backup-in-progress if root ever overlapped
                if fpath == tmp_path:
                    continue
                arc = Path("Version 10") / fpath.relative_to(PROJECT_ROOT)
                try:
                    zf.write(fpath, arc.as_posix())
                    count += 1
                    total += fpath.stat().st_size
                except (OSError, PermissionError) as exc:  # noqa: BLE001
                    print(f"  skipped (locked?): {fpath.name}: {exc}", file=sys.stderr)
        tmp_path.replace(final_path)
    except Exception as exc:  # noqa: BLE001
        print(f"Backup FAILED: {exc}", file=sys.stderr)
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        return 1

    size_mb = final_path.stat().st_size / (1024 * 1024)
    print(
        f"Backup complete: {count} files, {total / (1024*1024):.1f} MB source "
        f"-> {size_mb:.1f} MB zip"
    )
    prune_old(backup_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
