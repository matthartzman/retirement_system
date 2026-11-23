#!/usr/bin/env python3
"""Create a timestamped ZIP backup of the project (code, docs, build tooling) for off-site safekeeping.

This is the off-site safety net now that the working copy lives on the local C: drive (outside OneDrive) to avoid
OneDrive sync corruption. It is invoked automatically at the end of every build by ``build.py`` and can be run by
hand:

    python tools/backup_to_onedrive.py                       # code and tooling only (the safe default)
    python tools/backup_to_onedrive.py --include-data        # ALSO plan and financial data, ENCRYPTED

By default nothing that holds household data goes into the archive (X-13): identity and app databases, ``*.rpx``
plan files (and their version copies), ``balances.csv``, ``monarch_balances*``, ``financial_trends_log*`` and the
whole ``local_state/`` folder are skipped. ``--include-data`` adds them and then writes an ENCRYPTED archive
(``.zip.enc``: AES-256-GCM through ``src/gateway/backup_crypto.py``, key derived from a passphrase with scrypt); the
passphrase is read from ``--passphrase-file`` or asked for twice. Without a passphrase the run refuses, so a
data-bearing zip is never written in the clear. ``--decrypt <file> <out.zip>`` reverses it.

Backup destination is resolved in this order:
  1. env var  RP_BACKUP_DIR                       (explicit override)
  2. <OneDriveCommercial or OneDrive>/Retirement Planning/Backups, when that "Retirement Planning" folder exists
  3. a local fallback under the current user's home directory, so this script never fails or needs configuration
"""
from __future__ import annotations

import argparse
import fnmatch
import getpass
import hashlib
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Directory names skipped anywhere in the tree.  "build", "__pycache__",
# ".pytest_cache" and ".git" are pure regenerable caches / intermediate build
# artifacts.  "monarch-browser" and ".venv" are added per system review
# 2026-09-07 SEC-3: "monarch-browser" is the Monarch Extractor's Playwright
# persistent profile directory (Monarch Extractor/monarch-browser/) -- it
# holds a live, replayable browser login session, not project data, and
# .gitignore already excludes it from git for the same reason. ".venv" is a
# regenerable virtualenv that can appear under "Monarch Extractor/" too.
# dist/ (the built exe) is intentionally NOT excluded.
EXCLUDE_DIRS = {"build", "__pycache__", ".pytest_cache", ".git", "monarch-browser", ".venv"}

# Individual files (relative to PROJECT_ROOT, forward-slash) skipped
# regardless of directory. System review 2026-09-07 SEC-3: this is the
# plaintext secrets store (API keys, etc.) -- see src/secrets_store.py -- and
# should not leave the machine in an unencrypted, indefinitely-retained
# rolling backup archive.
EXCLUDE_FILES = {"local_state/secrets.local.json"}

# X-13: household data. Skipped unless --include-data (and then the archive is encrypted).
DATA_DIRS = {"local_state"}
DATA_FILE_PATTERNS = ("identity.db", "app.db", "*.rpx", "*.rpx.*", "balances.csv", "monarch_balances*",
                      "financial_trends_log*")

ENC_MAGIC = b"RPZP1\n"
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 1

# Keep at most this many backups in the destination; older ones are pruned.
KEEP_LAST = 10

BACKUP_PREFIX = "retirement_v10_"


def resolve_backup_dir() -> Path:
    override = os.environ.get("RP_BACKUP_DIR")
    if override:
        return Path(override)

    onedrive = os.environ.get("OneDriveCommercial") or os.environ.get("OneDrive")
    if onedrive:
        candidate = Path(onedrive) / "Retirement Planning" / "Backups"
        # Only accept it if the OneDrive "Retirement Planning" folder already exists (never create it).
        if candidate.parent.exists():
            return candidate

    # Last-resort fallback: a local, portable location under the current user's home directory.
    return Path.home() / "RetirementPlannerBackups"


def is_data_file(name: str) -> bool:
    return any(fnmatch.fnmatchcase(name.lower(), pat) for pat in DATA_FILE_PATTERNS)


def iter_files(root: Path, include_data: bool = False):
    excluded_dirs = EXCLUDE_DIRS if include_data else EXCLUDE_DIRS | DATA_DIRS
    for dirpath, dirnames, filenames in os.walk(root):
        # prune excluded dirs in place so os.walk doesn't descend into them
        dirnames[:] = [d for d in dirnames if d not in excluded_dirs]
        for name in filenames:
            fpath = Path(dirpath) / name
            if fpath.relative_to(root).as_posix() in EXCLUDE_FILES:
                continue
            if not include_data and is_data_file(name):
                continue
            yield fpath


def derive_key(passphrase: str, salt: bytes) -> bytes:
    return hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32,
                          maxmem=128 * 1024 * 1024)


def _crypto():
    """src/gateway/backup_crypto.py (AES-256-GCM, chunked, authenticated); imported lazily so the plain backup needs
    no third-party package."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from src.gateway import backup_crypto  # noqa: PLC0415

    return backup_crypto


def open_encrypted_sink(path: Path, passphrase: str):
    """A writable stream that encrypts everything written to it into ``path``; returns (writer, file handle)."""
    bc = _crypto()
    salt = os.urandom(16)
    fh = open(path, "wb")
    fh.write(ENC_MAGIC + salt)
    return bc.EncryptingWriter(fh, derive_key(passphrase, salt)), fh


def decrypt_file(src: Path, dest: Path, passphrase: str) -> None:
    bc = _crypto()
    with open(src, "rb") as fh:
        head = fh.read(len(ENC_MAGIC) + 16)
        if not head.startswith(ENC_MAGIC) or len(head) != len(ENC_MAGIC) + 16:
            raise ValueError("not an encrypted project backup")
        reader = bc.DecryptingReader(fh, bc.KeyRing(derive_key(passphrase, head[len(ENC_MAGIC):])))
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            with open(tmp, "wb") as out:
                while chunk := reader.read(1024 * 1024):
                    out.write(chunk)
            reader.verify_to_end()
            tmp.replace(dest)
        finally:
            tmp.unlink(missing_ok=True)


def read_passphrase(path: Path | None) -> str:
    if path is not None:
        value = path.read_text(encoding="utf-8").strip("\r\n")
    else:
        value = getpass.getpass("Backup passphrase: ")
        if getpass.getpass("Repeat it: ") != value:
            raise ValueError("the passphrases do not match")
    if len(value) < 12:
        raise ValueError("use a passphrase of at least 12 characters")
    return value


def prune_old(backup_dir: Path) -> None:
    zips = sorted(
        [*backup_dir.glob(f"{BACKUP_PREFIX}*.zip"), *backup_dir.glob(f"{BACKUP_PREFIX}*.zip.enc")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for stale in zips[KEEP_LAST:]:
        try:
            stale.unlink()
            print(f"  pruned old backup: {stale.name}")
        except OSError as exc:  # noqa: BLE001
            print(f"  could not prune {stale.name}: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Back up the project (data only with --include-data, then encrypted).")
    ap.add_argument("--include-data", action="store_true",
                    help="also archive plan and financial data; the archive is then encrypted")
    ap.add_argument("--passphrase-file", type=Path, help="file whose first line is the passphrase (default: ask)")
    ap.add_argument("--decrypt", nargs=2, metavar=("ENCRYPTED", "OUT_ZIP"), type=Path,
                    help="decrypt an encrypted backup to a zip and exit")
    args = ap.parse_args(argv)
    if args.decrypt:
        try:
            decrypt_file(args.decrypt[0], args.decrypt[1], read_passphrase(args.passphrase_file)
                         if args.passphrase_file else getpass.getpass("Backup passphrase: "))
        except Exception as exc:  # noqa: BLE001
            print(f"Decrypt FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(f"Decrypted to {args.decrypt[1]}")
        return 0
    passphrase = None
    if args.include_data:
        if args.passphrase_file is None and not sys.stdin.isatty():
            print("--include-data needs --passphrase-file when there is no terminal: a data backup is never written "
                  "in the clear.", file=sys.stderr)
            return 2
        try:
            passphrase = read_passphrase(args.passphrase_file)
        except (OSError, ValueError) as exc:
            print(f"Refused: {exc}", file=sys.stderr)
            return 2

    backup_dir = resolve_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = ".zip.enc" if passphrase else ".zip"
    final_path = backup_dir / f"{BACKUP_PREFIX}{stamp}{suffix}"
    tmp_path = final_path.with_name(final_path.name + ".tmp")

    print(f"Backing up {PROJECT_ROOT}" + ("" if args.include_data else " (code and tooling only; no household data)"))
    print(f"        -> {final_path}")

    count = 0
    total = 0
    try:
        if passphrase:
            sink, raw = open_encrypted_sink(tmp_path, passphrase)
            target = sink
        else:
            raw, sink, target = None, None, tmp_path
        try:
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
                for fpath in iter_files(PROJECT_ROOT, include_data=args.include_data):
                    # never include a backup-in-progress if root ever overlapped
                    if fpath == tmp_path:
                        continue
                    arc = Path(PROJECT_ROOT.name) / fpath.relative_to(PROJECT_ROOT)
                    try:
                        zf.write(fpath, arc.as_posix())
                        count += 1
                        total += fpath.stat().st_size
                    except (OSError, PermissionError) as exc:  # noqa: BLE001
                        print(f"  skipped (locked?): {fpath.name}: {exc}", file=sys.stderr)
            if sink is not None:
                sink.finish()
        finally:
            if raw is not None:
                raw.close()
        tmp_path.replace(final_path)
    except Exception as exc:  # noqa: BLE001
        print(f"Backup FAILED: {exc}", file=sys.stderr)
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        return 1

    size_mb = final_path.stat().st_size / (1024 * 1024)
    print(
        f"Backup complete: {count} files, {total / (1024*1024):.1f} MB source "
        f"-> {size_mb:.1f} MB {'encrypted ' if passphrase else ''}archive"
    )
    prune_old(backup_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
