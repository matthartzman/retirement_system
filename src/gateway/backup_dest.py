"""Where backups may be written: the confinement review for the one server-side path an admin sets.

The destination is configured only in the service config file (Windows administrators), never through a web
route. It must be an absolute local folder that is not inside the data root, the install folder, a user
profile folder or a synced folder (OneDrive, Dropbox, Google Drive, iCloud, Box), and not the key file's folder.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

SYNC_MARKERS = re.compile(r"^(onedrive\b.*|dropbox.*|google ?drive.*|icloud ?drive.*|box( sync)?|my drive|sync)$", re.I)
SYNC_ENV = ("OneDrive", "OneDriveConsumer", "OneDriveCommercial", "DROPBOX", "GoogleDrive")


class BackupDestinationError(ValueError):
    """The destination is not an acceptable place for backups."""


def default_backup_dir() -> Path:
    base = os.environ.get("ProgramData") or r"C:\ProgramData"
    return Path(base) / "RetirementPlannerGateway" / "backups"


def profiles_root() -> Path:
    return Path(os.environ.get("SystemDrive", "C:") + "\\Users")


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _resolve(path: Path) -> Path:
    return Path(os.path.realpath(str(path)))


def validate_backup_destination(value: str | os.PathLike, *, data_root: Path | None = None,
                                install_dir: Path | None = None, key_file: Path | None = None) -> Path:
    """Return the resolved destination or raise :class:`BackupDestinationError` saying why not."""
    text = os.fspath(value)
    if not text.strip() or "\x00" in text:
        raise BackupDestinationError("the backup destination is empty")
    if text.startswith("\\\\") or text.startswith("//"):
        raise BackupDestinationError("a network share is not accepted as the backup destination")
    raw = Path(text)
    if not raw.is_absolute():
        raise BackupDestinationError("the backup destination must be an absolute path")
    if ".." in raw.parts:
        raise BackupDestinationError("the backup destination must not contain '..'")
    dest = _resolve(raw)
    if dest == Path(dest.anchor):
        raise BackupDestinationError("a drive root is not accepted as the backup destination")
    for name in SYNC_ENV:
        root = os.environ.get(name)
        if root and _inside(dest, _resolve(Path(root))):
            raise BackupDestinationError("the backup destination is inside a synced folder (" + name + ")")
    if any(SYNC_MARKERS.match(part) for part in dest.parts[1:]):
        raise BackupDestinationError("the backup destination looks like a synced folder (OneDrive, Dropbox, ...)")
    if _inside(dest, _resolve(profiles_root())):
        raise BackupDestinationError("the backup destination must not be inside a user profile folder")
    for label, other in (("the data folder", data_root), ("the install folder", install_dir)):
        if other is not None:
            resolved = _resolve(Path(other))
            if _inside(dest, resolved) or _inside(resolved, dest):
                raise BackupDestinationError(f"the backup destination must be separate from {label}")
    if key_file is not None and _inside(_resolve(Path(key_file)), dest):
        raise BackupDestinationError("the backup key must be kept outside the backup folder")
    if dest.exists() and not dest.is_dir():
        raise BackupDestinationError("the backup destination exists and is not a folder")
    return dest


def validate_key_location(key_file: Path, *, backup_dir: Path | None, data_root: Path | None = None,
                          install_dir: Path | None = None) -> Path:
    """The key file must be outside the backup folder, the data root and any synced folder."""
    key = _resolve(Path(key_file))
    if not Path(key_file).is_absolute():
        raise BackupDestinationError("the backup key path must be absolute")
    for name in SYNC_ENV:
        root = os.environ.get(name)
        if root and _inside(key, _resolve(Path(root))):
            raise BackupDestinationError("the backup key must not be kept in a synced folder (" + name + ")")
    if any(SYNC_MARKERS.match(part) for part in key.parts[1:-1]):
        raise BackupDestinationError("the backup key must not be kept in a synced folder")
    for label, other in (("the backup folder", backup_dir), ("the data folder", data_root),
                         ("the install folder", install_dir)):
        if other is not None and _inside(key, _resolve(Path(other))):
            raise BackupDestinationError(f"the backup key must be kept outside {label}")
    return key
