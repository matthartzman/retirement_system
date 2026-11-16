"""Refuse to follow links inside a user's folder.

A worker account has Modify on its own folder, and creating a directory junction needs no privilege, so a
user can point ``local_state`` (or ``input``, or a log folder) at another user's data. The gateway's own
jobs run with far more access than any worker (backup, restore, migrate-all, log housekeeping); they must
check with :func:`has_reparse_point` before reading or writing a path under a user's folder.
"""
from __future__ import annotations

import os
from pathlib import Path

_REPARSE = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT: junctions, symlinks and mount points


def _is_link(path: Path) -> bool:
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return False
    if getattr(st, "st_file_attributes", 0) & _REPARSE:
        return True
    return path.is_symlink()


def has_reparse_point(path: Path | str, root: Path | str) -> bool:
    """True when ``path`` or any folder between it and ``root`` (``root`` itself included) is a link.

    A path that is not under ``root`` is treated as unsafe. A missing component is not a link.
    """
    p, r = Path(os.path.abspath(path)), Path(os.path.abspath(root))
    try:
        parts = p.relative_to(r).parts
    except ValueError:
        return True
    cur = r
    if _is_link(cur):
        return True
    for part in parts:
        cur = cur / part
        if _is_link(cur):
            return True
    return False


def remove_reparse_points(root: Path | str) -> list[str]:
    """Delete every link (junction or symlink) under ``root``, never following one; returns what was removed.

    Run before an elevated ``icacls /reset /T`` over a worker-writable tree: that command follows links and would
    rewrite the permissions of whatever a worker pointed one at. Removing a link deletes the link only.
    """
    removed: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        for name in list(dirnames) + list(filenames):
            p = Path(dirpath) / name
            if not _is_link(p):
                continue
            try:
                os.rmdir(p) if (p.is_dir() or name in dirnames) else os.unlink(p)
            except OSError:
                os.unlink(p)
            removed.append(str(p))
            if name in dirnames:
                dirnames.remove(name)
    return removed
