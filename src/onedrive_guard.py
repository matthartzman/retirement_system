from __future__ import annotations

"""Guard against reading OneDrive-truncated/not-fully-synced files.

Both scheduled headless jobs (Monarch auto-import, the financial trends
reporter) read files under paths that are commonly OneDrive-synced on
Windows (e.g. C:\\RetirementPlanning\\...). A file that OneDrive has not
finished downloading, or a write caught mid-sync, can appear as a
zero-byte file or a cloud-only placeholder rather than failing to open --
importing that silently would corrupt or truncate plan data. Both scripts
must run this check before reading anything.
"""

import os
from pathlib import Path

# Windows FILE_ATTRIBUTE_* flags that mark a OneDrive/Files-On-Demand
# placeholder that has not been fully downloaded to disk.
_FILE_ATTRIBUTE_OFFLINE = 0x1000
_FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000
_FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x40000
_PLACEHOLDER_ATTRS = _FILE_ATTRIBUTE_OFFLINE | _FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | _FILE_ATTRIBUTE_RECALL_ON_OPEN


def is_onedrive_placeholder(path: str | Path) -> bool:
    """True if `path` is a Windows cloud-only placeholder not yet downloaded.

    Always False on non-Windows platforms (there is no equivalent attribute
    to check, and this repo's dev/CI environment is not Windows).
    """
    if os.name != "nt":
        return False
    try:
        attrs = os.stat(path).st_file_attributes  # type: ignore[attr-defined]
    except (OSError, AttributeError):
        return False
    return bool(attrs & _PLACEHOLDER_ATTRS)


def check_file_is_safe_to_read(path: str | Path) -> str | None:
    """Return an error message if `path` looks truncated/not-fully-synced, else None."""
    p = Path(path)
    if not p.exists():
        return f"File does not exist: {p}"
    try:
        size = p.stat().st_size
    except OSError as exc:
        return f"Could not stat file: {p} ({exc})"
    if size == 0:
        return f"File is zero bytes (likely a OneDrive sync placeholder or a truncated write): {p}"
    if is_onedrive_placeholder(p):
        return f"File is a OneDrive cloud-only placeholder, not fully downloaded: {p}"
    return None


def check_files_safe_to_read(paths: list[str | Path]) -> list[str]:
    """Return one error message per unsafe file in `paths` (empty if all clear)."""
    errors: list[str] = []
    for p in paths:
        err = check_file_is_safe_to_read(p)
        if err:
            errors.append(err)
    return errors
