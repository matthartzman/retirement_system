"""Scheduled, consistent backups of every user's plan files and the gateway database.

Each set is written to ``<dest>/<UTC stamp>.partial`` and renamed when complete, so a
crash never leaves a half set that looks finished.  SQLite files are copied with the
backup API, which gives a consistent copy while a worker is writing.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

log = logging.getLogger("retirement.gateway.backups")

_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
_PARTIAL_SUFFIX = ".partial"
_STALE_PARTIAL_SECONDS = 86400
_CHECK_SECONDS = 60.0


def _stamp_to_epoch(name: str) -> float | None:
    try:
        parsed = datetime.strptime(name, _STAMP_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return parsed.timestamp()


def _copy_sqlite(source: Path, target: Path) -> None:
    """Copy one SQLite database with the backup API (consistent under concurrent writes)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{quote(source.as_posix())}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


class BackupScheduler:
    def __init__(
        self,
        *,
        data_root: Path,
        gateway_db: Path | None,
        dest: Path,
        user_ids: Callable[[], Iterable[int]],
        interval_seconds: float = 86400,
        keep: int = 14,
        clock: Callable[[], float] = time.time,
        secure_dir: Callable[[Path], None] | None = None,
    ) -> None:
        self._data_root = Path(data_root)
        self._gateway_db = Path(gateway_db) if gateway_db is not None else None
        self._dest = Path(dest)
        self._user_ids = user_ids
        self._interval = float(interval_seconds)
        self._keep = max(1, int(keep))
        self._clock = clock
        self._secure_dir = secure_dir
        self._secured = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: dict = {"at": None, "folder": None, "users": 0, "errors": []}
        self._last_stamp_name: str | None = None

    # ------------------------------------------------------------------ helpers
    def _prepare_dest(self) -> None:
        self._dest.mkdir(parents=True, exist_ok=True)
        if self._secure_dir is not None and not self._secured:
            self._secure_dir(self._dest)
            self._secured = True

    def _new_stamp(self) -> str:
        base = self._clock()
        name = datetime.fromtimestamp(base, tz=timezone.utc).strftime(_STAMP_FORMAT)
        # Two sets in the same second must not collide.
        bump = 0
        while (
            (self._dest / name).exists()
            or (self._dest / (name + _PARTIAL_SUFFIX)).exists()
            or name == self._last_stamp_name
        ):
            bump += 1
            name = datetime.fromtimestamp(base + bump, tz=timezone.utc).strftime(_STAMP_FORMAT)
        self._last_stamp_name = name
        return name

    def _copy_user(self, user_id: int, set_dir: Path) -> None:
        user_root = self._data_root / "users" / str(int(user_id))
        out = set_dir / "users" / str(int(user_id))
        plan = user_root / "plan.rpx"
        app_db = user_root / "local_state" / "app.db"
        if plan.is_file():
            _copy_sqlite(plan, out / "plan.rpx")
        if app_db.is_file():
            _copy_sqlite(app_db, out / "app.db")

    def complete_sets(self) -> list[Path]:
        if not self._dest.is_dir():
            return []
        found = [
            p
            for p in self._dest.iterdir()
            if p.is_dir() and not p.name.endswith(_PARTIAL_SUFFIX) and _stamp_to_epoch(p.name) is not None
        ]
        return sorted(found, key=lambda p: p.name)

    def _newest_age_start(self) -> float | None:
        sets = self.complete_sets()
        if not sets:
            return None
        return _stamp_to_epoch(sets[-1].name)

    def _prune(self, just_made: Path) -> None:
        sets = self.complete_sets()
        excess = len(sets) - self._keep
        for old in sets:
            if excess <= 0:
                break
            if old == just_made:
                continue
            shutil.rmtree(old, ignore_errors=True)
            excess -= 1
        now = self._clock()
        for p in self._dest.iterdir():
            if p.is_dir() and p.name.endswith(_PARTIAL_SUFFIX):
                try:
                    age = now - p.stat().st_mtime
                except OSError:
                    continue
                if age > _STALE_PARTIAL_SECONDS:
                    shutil.rmtree(p, ignore_errors=True)

    # --------------------------------------------------------------- public API
    def run_once(self) -> Path:
        with self._lock:
            self._prepare_dest()
            stamp = self._new_stamp()
            partial = self._dest / (stamp + _PARTIAL_SUFFIX)
            final = self._dest / stamp
            partial.mkdir(parents=True)
            errors: list[str] = []
            users = 0
            try:
                ids = list(self._user_ids())
            except Exception as exc:  # noqa: BLE001 - reported, never fatal
                ids = []
                errors.append(f"could not list users: {type(exc).__name__}")
                log.error("backup could not list users: %s", type(exc).__name__)
            for uid in ids:
                try:
                    self._copy_user(uid, partial)
                    users += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"user {uid}: {type(exc).__name__}")
                    log.error("backup of user %s failed: %s", uid, type(exc).__name__)
            if self._gateway_db is not None and self._gateway_db.is_file():
                try:
                    _copy_sqlite(self._gateway_db, partial / "gateway.db")
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"gateway.db: {type(exc).__name__}")
                    log.error("backup of gateway.db failed: %s", type(exc).__name__)
            partial.rename(final)
            try:
                self._prune(final)
            except OSError as exc:
                errors.append(f"retention: {type(exc).__name__}")
                log.error("backup retention failed: %s", type(exc).__name__)
            self._last = {
                "at": self._clock(),
                "folder": str(final),
                "users": users,
                "errors": errors,
            }
            log.info("backup set %s: %d users, %d errors", final.name, users, len(errors))
            return final

    def backup_user(self, user_id: int, into: Path | None = None) -> Path:
        """Back up one user's files; default into a fresh complete set folder."""
        if into is not None:
            self._copy_user(user_id, Path(into))
            return Path(into)
        with self._lock:
            self._prepare_dest()
            stamp = self._new_stamp()
            partial = self._dest / (stamp + _PARTIAL_SUFFIX)
            partial.mkdir(parents=True)
            self._copy_user(user_id, partial)
            final = self._dest / stamp
            partial.rename(final)
            return final

    def last_result(self) -> dict:
        return dict(self._last, errors=list(self._last["errors"]))

    def _due(self) -> bool:
        newest = self._newest_age_start()
        if newest is None:
            return True
        return self._clock() - newest >= self._interval

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self._due():
                    self.run_once()
            except Exception as exc:  # noqa: BLE001
                log.error("scheduled backup failed: %s", type(exc).__name__)
            self._stop.wait(min(_CHECK_SECONDS, max(0.05, self._interval)))

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="gateway-backups", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=30)
        self._thread = None
