from __future__ import annotations

"""Crash-safe, concurrency-safe replacement of plan data files.

The dashboard is served by ``ThreadingHTTPServer`` (one thread per request) and
several endpoints rewrite the same plan CSV -- ``input/client_assets.csv`` is
touched by the other-asset, note-receivable and 529 add endpoints alike.  Two
protections live here, and both are needed:

``atomic_write``
    Writes through a *uniquely named* temp file in the target directory, then
    replaces the target.  Every writer used to derive its temp path as
    ``<name>.tmp``, a pure function of the target, so concurrent writers opened
    the very same file.  On Windows the first writer's ``os.replace`` then
    failed with ``WinError 32`` because the other thread still held the source
    handle open; on POSIX the rename succeeded and quietly published a file
    with two writers' rows interleaved.

``plan_file_lock``
    A per-path *reentrant* lock.  Atomic replacement alone only makes each
    write individually safe -- it does not make a read-modify-write cycle safe.
    Two endpoints that both read the pre-edit snapshot each write back their
    own version, so the later write drops the earlier one's addition.  Callers
    therefore hold this lock across the whole read-modify-write.  It is
    reentrant because ``atomic_write`` re-acquires the same path's lock inside
    a caller that already holds it.

Locks are per resolved path so that unrelated plan files stay independent, and
this is a *within-process* guard: it does not coordinate with other processes
(the build subprocess reads plan data but does not rewrite it concurrently).
"""

import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any, Iterator

_LOCK_REGISTRY_GUARD = threading.Lock()
_LOCK_REGISTRY: dict[str, threading.RLock] = {}


def _lock_key(path: Path) -> str:
    # normcase so Windows' case-insensitive paths map to one lock; abspath
    # rather than resolve() so a not-yet-created file still keys correctly.
    return os.path.normcase(os.path.abspath(str(path)))


@contextmanager
def plan_file_lock(path: Path | str) -> Iterator[None]:
    """Serialise access to one plan file across request threads.

    Hold this across an entire read-modify-write, not just the write, or
    concurrent edits will still clobber each other.
    """
    key = _lock_key(Path(path))
    with _LOCK_REGISTRY_GUARD:
        lock = _LOCK_REGISTRY.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCK_REGISTRY[key] = lock
    with lock:
        yield


@contextmanager
def atomic_write(
    path: Path | str,
    *,
    encoding: str = "utf-8",
    newline: str | None = "",
) -> Iterator[IO[Any]]:
    """Yield a handle whose contents replace ``path`` atomically on clean exit.

    ``newline=""`` (the default) suits the ``csv`` module, which emits its own
    line terminator.  Pass ``newline=None`` to keep ``Path.write_text``'s
    translation of ``"\\n"`` to ``os.linesep``.

    If the body raises, the target is left untouched and the temp file removed.
    """
    target = Path(path)
    with plan_file_lock(target):
        target.parent.mkdir(parents=True, exist_ok=True)
        # A unique temp name per write is what stops concurrent writers from
        # sharing one temp file; mkstemp also creates it exclusively.
        fd, tmp_name = tempfile.mkstemp(
            dir=str(target.parent), prefix=f"{target.name}.", suffix=".tmp"
        )
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            with tmp.open("w", encoding=encoding, newline=newline) as handle:
                yield handle
            os.replace(tmp, target)
        except BaseException:
            try:
                tmp.unlink()
            except OSError:  # pragma: no cover - best-effort cleanup
                pass
            raise


def write_text_atomic(path: Path | str, content: str, *, encoding: str = "utf-8") -> Path:
    """``Path.write_text`` equivalent, atomic and lock-guarded.

    Keeps ``write_text``'s newline translation (``newline=None``) so callers
    that already compensate for it are unaffected.
    """
    target = Path(path)
    with atomic_write(target, encoding=encoding, newline=None) as handle:
        handle.write(content)
    return target
