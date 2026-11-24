"""Refuse to follow links inside a user's folder.

A worker account has Modify on its own folder, and creating a directory junction needs no privilege, so a
user can point ``local_state`` (or ``input``, or a log folder) at another user's data. The gateway's own
jobs run with far more access than any worker (backup, restore, migrate-all, log housekeeping); they must
check with :func:`has_reparse_point` before reading or writing a path under a user's folder.

``has_reparse_point`` looks at names, so it is only a first filter. Code that then reads, writes or moves the file
must hold :func:`pinned` around the work (SEC-02), which verifies the open handle and keeps the folder chain from
being swapped while the job runs.
"""
from __future__ import annotations

import errno
import ntpath
import os
import stat
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Protocol

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


# ---- open-by-handle (SEC-02): no gap between the check and the use ------------------------------------
# ``has_reparse_point`` looks at names. Between that look and the open, a worker (who may rewrite its own folder)
# can swap a folder for a junction. ``pinned`` instead opens the path once, never following a link in the last
# component, checks the OPEN handle (not a link; its final path is inside the root) and keeps the handle open while
# the caller works. On Windows an open handle without FILE_SHARE_DELETE stops that file or folder, and each folder
# above it, from being renamed or replaced, so the verified location is the one used. Windows behaviour cannot be
# exercised on Linux: the pure comparison and the POSIX implementation are tested, the Windows calls by fakes.


class UnsafePathError(OSError):
    """The path is a link, or resolves outside the folder it must stay in."""


class _PathOps(Protocol):
    def open(self, path: str) -> object: ...
    def is_link(self, handle: object) -> bool: ...
    def final_path(self, handle: object, path: str) -> str: ...
    def close(self, handle: object) -> None: ...


class _WindowsOps:
    def open(self, path: str) -> object:
        from . import winapi  # noqa: PLC0415

        return winapi.open_without_following(path)

    def is_link(self, handle: object) -> bool:
        from . import winapi  # noqa: PLC0415

        return bool(winapi.handle_attributes(handle) & _REPARSE)  # type: ignore[arg-type]

    def final_path(self, handle: object, path: str) -> str:
        from . import winapi  # noqa: PLC0415

        return winapi.final_path_of_handle(handle)  # type: ignore[arg-type]

    def close(self, handle: object) -> None:
        from . import winapi  # noqa: PLC0415

        winapi.close_file_handle(handle)  # type: ignore[arg-type]


class _PosixOps:
    """``O_NOFOLLOW`` refuses a link as the last component; the open descriptor's own path is read back."""

    def open(self, path: str) -> object:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            return os.open(path, flags)
        except OSError as exc:
            if exc.errno in (errno.ELOOP, getattr(errno, "EMLINK", errno.ELOOP)):
                raise UnsafePathError(exc.errno, "the path is a link", path) from exc
            raise

    def is_link(self, handle: object) -> bool:
        return stat.S_ISLNK(os.fstat(handle).st_mode)  # type: ignore[arg-type]

    def final_path(self, handle: object, path: str) -> str:
        try:
            return os.readlink(f"/proc/self/fd/{handle}")
        except OSError:  # no /proc: fall back to resolving the name (weaker, but still catches a swapped folder)
            return os.path.realpath(path)

    def close(self, handle: object) -> None:
        os.close(handle)  # type: ignore[arg-type]


def _ops() -> _PathOps:
    return _WindowsOps() if sys.platform == "win32" else _PosixOps()


def final_path_inside(final: str, root_final: str, *, windows: bool | None = None) -> bool:
    """True when ``final`` is ``root_final`` or lies under it (a name comparison of two RESOLVED paths)."""
    windows = (sys.platform == "win32") if windows is None else windows
    mod = ntpath if windows else os.path
    a, b = mod.normcase(mod.normpath(final)), mod.normcase(mod.normpath(root_final))
    if a == b:
        return True
    sep = "\\" if windows else "/"
    return a.startswith(b if b.endswith(sep) else b + sep)


@contextmanager
def pinned(path: Path | str, root: Path | str, *, ops: _PathOps | None = None) -> Iterator[str]:
    """Verify ``path`` through an open handle and keep it open for the ``with`` body; yields the verified real path.

    Raises :class:`UnsafePathError` when the path (or ``root``) is a link, or its real path is outside ``root``;
    ``FileNotFoundError`` and other ``OSError`` pass through unchanged."""
    ops = ops or _ops()
    path_s, root_s = os.path.abspath(path), os.path.abspath(root)
    root_h = ops.open(root_s)
    try:
        if ops.is_link(root_h):
            raise UnsafePathError(0, "the folder is a link", root_s)
        root_final = ops.final_path(root_h, root_s)
        handle = ops.open(path_s)
        try:
            if ops.is_link(handle):
                raise UnsafePathError(0, "the path is a link", path_s)
            final = ops.final_path(handle, path_s)
            if not final_path_inside(final, root_final):
                raise UnsafePathError(0, "the path resolves outside its folder", path_s)
            yield final
        finally:
            ops.close(handle)
    finally:
        ops.close(root_h)
