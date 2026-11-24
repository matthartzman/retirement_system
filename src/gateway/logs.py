"""Worker log housekeeping.

A worker's console log (``local_state/logs/worker_console.log``) is replaced at each start (the last run is kept
as ``.1``) but can grow inside one long run.  The gateway cannot rename a running worker's open file, so it only
trims logs whose worker is not running, and removes rotated copies older than the retention.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Callable, Iterable

from . import fsguard

log = logging.getLogger("retirement.gateway.logs")
CONSOLE_LOG = Path("local_state") / "logs" / "worker_console.log"
MAX_CONSOLE_BYTES = 5 * 1024 * 1024
KEEP_ROTATED_DAYS = 14.0


def _trim_one(path: Path, max_bytes: int) -> bool:
    """Keep the tail of an oversized log, through ONE open handle (no second lookup of the name)."""
    with open(path, "r+b") as fh:
        size = os.fstat(fh.fileno()).st_size
        if size <= max_bytes:
            return False
        fh.seek(max(0, size - max_bytes // 2))  # the tail only: never the whole file
        data = fh.read()
        fh.seek(0)
        fh.write(b"[older output trimmed by the gateway]\n" + data)
        fh.truncate()
    return True


def prune_worker_logs(data_root: Path, is_running: Callable[[int], bool], *, max_bytes: int = MAX_CONSOLE_BYTES,
                      keep_days: float = KEEP_ROTATED_DAYS, now: float | None = None) -> dict:
    """Trim oversized console logs of stopped workers (keep the tail) and drop old rotated copies."""
    now = time.time() if now is None else now
    trimmed, removed = 0, 0
    users = Path(data_root) / "users"
    if not users.is_dir():
        return {"trimmed": 0, "removed": 0}
    for folder in users.iterdir():
        if not folder.name.isdigit():
            continue
        uid = int(folder.name)
        current = folder / CONSOLE_LOG
        rotated = current.with_name(current.name + ".1")
        if fsguard.has_reparse_point(current, folder):
            log.warning("log housekeeping skipped user %s: a link inside the workspace", uid)
            continue
        try:
            # SEC-02: the folder is verified through an open handle that stays open while its files are touched
            with fsguard.pinned(current.parent, folder):
                if rotated.is_file() and now - rotated.stat().st_mtime > keep_days * 86400 and not is_running(uid):
                    rotated.unlink()
                    removed += 1
                if current.is_file() and not is_running(uid):
                    with fsguard.pinned(current, folder):  # the file itself is verified and held, too
                        if _trim_one(current, max_bytes):
                            trimmed += 1
        except fsguard.UnsafePathError:
            log.warning("log housekeeping skipped user %s: a link inside the workspace", uid)
        except FileNotFoundError:
            continue  # no log folder yet
        except OSError as exc:
            log.warning("log housekeeping for user %s failed: %s", uid, type(exc).__name__)
    return {"trimmed": trimmed, "removed": removed}


def start_housekeeping(data_root: Path, is_running: Callable[[int], bool], stop, *, every: float = 3600.0) -> "object":
    import threading  # noqa: PLC0415

    def loop() -> None:
        while not stop.wait(every):
            try:
                prune_worker_logs(data_root, is_running)
            except Exception as exc:  # noqa: BLE001
                log.error("log housekeeping failed: %s", type(exc).__name__)

    t = threading.Thread(target=loop, name="gateway-log-housekeeping", daemon=True)
    t.start()
    return t


__all__: Iterable[str] = ["prune_worker_logs", "start_housekeeping"]
