#!/usr/bin/env python3
"""Build the standalone exe, then back the whole project up to OneDrive.

This is the single entry point for "rebuild":

    python build.py            # build + OneDrive backup
    python build.py --no-backup  # build only (skip the backup step)

It runs PyInstaller against retirement_planner.spec (onedir layout, output at
dist/retirement_planner/retirement_planner.exe) and, on success, invokes
tools/backup_to_onedrive.py so a timestamped zip lands in the OneDrive
"Retirement Planning/Backups" folder after every rebuild.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = ROOT / "retirement_planner.spec"
BACKUP_SCRIPT = ROOT / "tools" / "backup_to_onedrive.py"


def run(cmd: list[str], cwd: Path) -> int:
    print(f"\n>>> {' '.join(cmd)}\n")
    return subprocess.run(cmd, cwd=str(cwd)).returncode


def main() -> int:
    do_backup = "--no-backup" not in sys.argv[1:]

    if not SPEC.exists():
        print(f"Spec file not found: {SPEC}", file=sys.stderr)
        return 1

    print("=" * 60)
    print("  BUILD: PyInstaller")
    print("=" * 60)
    rc = run([sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm"], ROOT)
    if rc != 0:
        print(f"\nBUILD FAILED (PyInstaller exit code {rc}). Skipping backup.", file=sys.stderr)
        return rc

    exe = ROOT / "dist" / "retirement_planner" / "retirement_planner.exe"
    if not exe.exists():
        print(f"\nBuild reported success but exe is missing: {exe}", file=sys.stderr)
        return 1
    print(f"\nBuild OK: {exe}")

    if not do_backup:
        print("Skipping OneDrive backup (--no-backup).")
        return 0

    print("\n" + "=" * 60)
    print("  BACKUP: zip -> OneDrive")
    print("=" * 60)
    rc = run([sys.executable, str(BACKUP_SCRIPT)], ROOT)
    if rc != 0:
        # A failed backup should not mask a successful build, but surface it.
        print(f"\nWARNING: build succeeded but backup failed (exit code {rc}).", file=sys.stderr)
        return rc

    print("\nAll done: build + OneDrive backup complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
