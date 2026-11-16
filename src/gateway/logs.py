"""Worker log housekeeping.

A worker's console log (``local_state/logs/worker_console.log``) is replaced at each start (the last run is kept
as ``.1``) but can grow inside one long run.  The gateway cannot rename a running worker's open file, so it only
trims logs whose worker is not running, and removes rotated copies older than the retention.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, Iterable

log = logging.getLogger("retirement.gateway.logs")
CONSOLE_LOG = Path("local_state") / "logs" / "worker_console.log"
MAX_CONSOLE_BYTES = 5 * 1024 * 1024
KEEP_ROTATED_DAYS = 14.0


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
        try:
            if rotated.is_file() and now - rotated.stat().st_mtime > keep_days * 86400 and not is_running(uid):
                rotated.unlink()
                removed += 1
            if current.is_file() and current.stat().st_size > max_bytes and not is_running(uid):
                data = current.read_bytes()[-max_bytes // 2:]
                current.write_bytes(b"[older output trimmed by the gateway]\n" + data)
                trimmed += 1
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
