"""Encrypted backup archives of ``data/users/`` and ``gateway.db``: write, verify, list, restore, schedule.

One ``<UTC stamp>.rpbak`` file per set (see ``backup_crypto`` for the format).  Plaintext never touches the
disk: each SQLite file is copied with the backup API into memory and streamed through a tar writer into the
encryptor.  A set is verified by reading it back before it is renamed from ``.partial``.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import sqlite3
import tarfile
import threading
import time
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from .backup_crypto import (BackupCryptoError, CorruptBackupError, DecryptingReader, EncryptingWriter,
                            WrongKeyError)

log = logging.getLogger("retirement.gateway.backup_store")

STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
SUFFIX = ".rpbak"
PARTIAL = ".partial"
_FULL_RE = re.compile(r"^(\d{8}T\d{6}Z)\.rpbak$")
_USER_RE = re.compile(r"^(\d{8}T\d{6}Z)\.user(\d+)\.rpbak$")
_USER_MEMBERS = {"plan.rpx": "plan.rpx", "app.db": Path("local_state") / "app.db"}
_MEMBER_RE = re.compile(r"^users/(\d+)/(plan\.rpx|app\.db)$")
ALLOWED_OTHER = {"gateway.db", "manifest.json"}
_CHECK_SECONDS = 60.0


class RestoreError(RuntimeError):
    """A restore was refused or failed; nothing was changed unless the message says it was rolled back."""


def _epoch(stamp: str) -> float:
    return datetime.strptime(stamp, STAMP_FORMAT).replace(tzinfo=timezone.utc).timestamp()


def sqlite_bytes(path: Path) -> bytes:
    """A consistent image of one SQLite file, taken with the backup API (safe while a worker writes)."""
    src = sqlite3.connect(f"file:{quote(Path(path).as_posix())}?mode=ro", uri=True)
    try:
        mem = sqlite3.connect(":memory:")
        try:
            src.backup(mem)
            return mem.serialize()
        finally:
            mem.close()
    finally:
        src.close()


def _add(tar: tarfile.TarFile, name: str, data: bytes, mtime: float) -> None:
    info = tarfile.TarInfo(name)
    info.size, info.mtime, info.mode = len(data), int(mtime), 0o600
    tar.addfile(info, io.BytesIO(data))


def write_archive(dest: Path, master: bytes, *, data_root: Path, user_ids: Iterable[int],
                  gateway_db: Path | None, now: float, label: str = "full") -> tuple[Path, dict]:
    """Write one archive file at ``dest`` (atomically, verified); returns (path, report)."""
    dest = Path(dest)
    partial = dest.with_name(dest.name + PARTIAL)
    errors: list[str] = []
    members: list[str] = []
    users: list[int] = []
    try:
        with open(partial, "wb") as sink:
            writer = EncryptingWriter(sink, master)
            with tarfile.open(fileobj=writer, mode="w|", format=tarfile.PAX_FORMAT) as tar:
                for uid in user_ids:
                    root = Path(data_root) / "users" / str(int(uid))
                    got = False
                    for member, rel in _USER_MEMBERS.items():
                        src = root / rel
                        if not src.is_file():
                            continue
                        try:
                            _add(tar, f"users/{int(uid)}/{member}", sqlite_bytes(src), now)
                            members.append(f"users/{int(uid)}/{member}")
                            got = True
                        except Exception as exc:  # noqa: BLE001 - reported per user, never fatal
                            errors.append(f"user {uid} {member}: {type(exc).__name__}")
                            log.error("backup of user %s %s failed: %s", uid, member, type(exc).__name__)
                    if got:
                        users.append(int(uid))
                if gateway_db is not None and Path(gateway_db).is_file():
                    try:
                        _add(tar, "gateway.db", sqlite_bytes(gateway_db), now)
                        members.append("gateway.db")
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"gateway.db: {type(exc).__name__}")
                        log.error("backup of gateway.db failed: %s", type(exc).__name__)
                manifest = {"format": 1, "label": label, "created_utc": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                            "users": users, "members": members, "errors": errors}
                _add(tar, "manifest.json", json.dumps(manifest).encode("utf-8"), now)
            writer.finish()
            sink.flush()
            os.fsync(sink.fileno())
        verify_archive(partial, master)  # a set that cannot be read back is not a success
        os.replace(partial, dest)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return dest, {"users": users, "errors": errors, "members": members}


def _open_tar(path: Path, master: bytes):
    fh = open(path, "rb")  # noqa: SIM115 - closed by the caller via the returned pair
    try:
        reader = DecryptingReader(fh, master)
        return fh, reader, tarfile.open(fileobj=reader, mode="r|")
    except BaseException:
        fh.close()
        raise


def verify_archive(path: Path, master: bytes) -> dict:
    """Authenticate the whole archive and return its manifest; raises WrongKeyError / CorruptBackupError."""
    fh, reader, tar = _open_tar(Path(path), master)
    manifest = None
    try:
        for member in tar:
            if member.name == "manifest.json":
                manifest = json.loads(tar.extractfile(member).read().decode("utf-8"))
            else:
                tar.extractfile(member).read() if member.isfile() else None
        reader.verify_to_end()
    except BackupCryptoError:
        raise
    except (tarfile.TarError, ValueError, EOFError, OSError) as exc:
        raise CorruptBackupError(f"the archive contents are damaged ({type(exc).__name__})") from None
    finally:
        tar.close()
        fh.close()
    if manifest is None:
        raise CorruptBackupError("the archive has no manifest")
    return manifest


def workspace_in_use(workspace: Path) -> bool:
    """True when a live worker owns this workspace (its port file names a running process)."""
    port_file = Path(workspace) / "local_state" / "worker.port.json"
    if not port_file.is_file():
        return False
    try:
        pid = int(json.loads(port_file.read_text(encoding="utf-8")).get("pid"))
    except (OSError, ValueError, TypeError):
        return False
    from src.remote_worker import _parent_alive  # noqa: PLC0415

    return _parent_alive(pid)


def restore_user(archive: Path, master: bytes, *, data_root: Path, user_id: int, stamp: str | None = None) -> dict:
    """Replace one user's ``plan.rpx`` and ``app.db`` from the archive; no other user is touched.

    The whole archive is authenticated first.  The user's current files are moved aside as
    ``*.before-restore-<stamp>`` (kept until you delete them) and the restored files swapped in.
    """
    uid = int(user_id)
    workspace = Path(data_root) / "users" / str(uid)
    manifest = verify_archive(archive, master)
    wanted = [m for m in manifest.get("members", []) if _MEMBER_RE.match(m) and m.split("/")[1] == str(uid)]
    if not wanted:
        raise RestoreError(f"the archive holds no files for user {uid}")
    if workspace_in_use(workspace):
        raise RestoreError(f"user {uid}'s worker is running; stop the gateway service first")
    stamp = stamp or datetime.now(timezone.utc).strftime(STAMP_FORMAT)
    staging = workspace.parent / f".restore-{uid}-{stamp}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    restored: list[str] = []
    try:
        fh, reader, tar = _open_tar(Path(archive), master)
        try:
            for member in tar:
                m = _MEMBER_RE.match(member.name)
                if not m or int(m.group(1)) != uid or not member.isfile():
                    continue
                target = staging / m.group(2)
                with open(target, "wb") as out:
                    shutil.copyfileobj(tar.extractfile(member), out)
            reader.verify_to_end()
        finally:
            tar.close()
            fh.close()
        moved: list[tuple[Path, Path]] = []
        try:
            for member, rel in _USER_MEMBERS.items():
                new = staging / member
                if not new.is_file():
                    continue
                live = workspace / rel
                live.parent.mkdir(parents=True, exist_ok=True)
                for suffix in ("", "-wal", "-shm"):
                    cur = live.with_name(live.name + suffix)
                    if cur.exists():
                        aside = cur.with_name(cur.name + f".before-restore-{stamp}")
                        os.replace(cur, aside)
                        moved.append((cur, aside))
                os.replace(new, live)
                restored.append(str(rel).replace("\\", "/"))
        except BaseException:
            for cur, aside in reversed(moved):  # put the user's files back
                if aside.exists():
                    os.replace(aside, cur)
            raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {"user": uid, "restored": restored, "archive": Path(archive).name}


def restore_gateway_db(archive: Path, master: bytes, out: Path) -> Path:
    """Write the archived ``gateway.db`` to a NEW file ``out`` (never over the live database)."""
    out = Path(out)
    if out.exists():
        raise RestoreError(f"{out.name} already exists; choose a new file name")
    manifest = verify_archive(archive, master)
    if "gateway.db" not in manifest.get("members", []):
        raise RestoreError("the archive holds no gateway.db")
    fh, reader, tar = _open_tar(Path(archive), master)
    partial = out.with_name(out.name + PARTIAL)
    try:
        for member in tar:
            if member.name == "gateway.db":
                with open(partial, "wb") as dst:
                    shutil.copyfileobj(tar.extractfile(member), dst)
        reader.verify_to_end()
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    finally:
        tar.close()
        fh.close()
    os.replace(partial, out)
    return out


def list_archives(dest: Path) -> list[dict]:
    """Newest last: ``{name, kind, user, stamp, epoch, size}`` for every finished archive in ``dest``."""
    found = []
    if not Path(dest).is_dir():
        return found
    for p in Path(dest).iterdir():
        if not p.is_file():
            continue
        m, u = _FULL_RE.match(p.name), _USER_RE.match(p.name)
        if m:
            found.append({"name": p.name, "kind": "full", "user": None, "stamp": m.group(1)})
        elif u:
            found.append({"name": p.name, "kind": "user", "user": int(u.group(2)), "stamp": u.group(1)})
        else:
            continue
        found[-1].update(epoch=_epoch(found[-1]["stamp"]), size=p.stat().st_size)
    return sorted(found, key=lambda a: (a["stamp"], a["name"]))


class EncryptedBackupScheduler:
    """Drop-in for ``BackupScheduler`` (same ``run_once``/``backup_user``/``last_result``/``start``/``stop``)."""

    def __init__(self, *, data_root: Path, gateway_db: Path | None, dest: Path, master: bytes,
                 user_ids: Callable[[], Iterable[int]], interval_seconds: float = 86400, keep: int = 14,
                 clock: Callable[[], float] = time.time, secure_dir: Callable[[Path], None] | None = None) -> None:
        self._data_root, self._gateway_db, self._dest = Path(data_root), (Path(gateway_db) if gateway_db else None), Path(dest)
        self._master, self._user_ids = master, user_ids
        self._interval, self._keep = float(interval_seconds), max(1, int(keep))
        self._clock, self._secure_dir, self._secured = clock, secure_dir, False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: dict = {"at": None, "archive": None, "users": 0, "errors": [], "ok": None}
        self._used: set[str] = set()

    def _prepare(self) -> None:
        self._dest.mkdir(parents=True, exist_ok=True)
        if self._secure_dir is not None and not self._secured:
            self._secure_dir(self._dest)
            self._secured = True

    def _stamp(self) -> str:
        base = self._clock()
        bump = 0
        while True:
            s = datetime.fromtimestamp(base + bump, tz=timezone.utc).strftime(STAMP_FORMAT)
            if s not in self._used and not any(self._dest.glob(s + "*")):
                self._used.add(s)
                return s
            bump += 1

    def run_once(self) -> Path:
        with self._lock:
            self._prepare()
            stamp = self._stamp()
            try:
                ids = sorted(int(i) for i in self._user_ids())
                path, rep = write_archive(self._dest / (stamp + SUFFIX), self._master, data_root=self._data_root,
                                          user_ids=ids, gateway_db=self._gateway_db, now=self._clock())
            except Exception as exc:  # noqa: BLE001 - recorded for the health page, then re-raised for the caller
                self._last = {"at": self._clock(), "archive": None, "users": 0,
                              "errors": [type(exc).__name__], "ok": False}
                log.error("backup failed: %s", type(exc).__name__)
                raise
            self._last = {"at": self._clock(), "archive": path.name, "users": len(rep["users"]),
                          "errors": rep["errors"], "ok": not rep["errors"]}
            self._prune()
            log.info("backup %s: %d users, %d errors", path.name, len(rep["users"]), len(rep["errors"]))
            return path

    def backup_user(self, user_id: int, into: Path | None = None) -> Path:
        """A snapshot of one user (before deleting or migrating them)."""
        with self._lock:
            self._prepare()
            stamp = self._stamp()
            path, _ = write_archive(self._dest / f"{stamp}.user{int(user_id)}{SUFFIX}", self._master,
                                    data_root=self._data_root, user_ids=[int(user_id)], gateway_db=None,
                                    now=self._clock(), label="user")
            self._prune()
            return path

    def _prune(self) -> None:
        arcs = list_archives(self._dest)
        full = [a for a in arcs if a["kind"] == "full"]
        for a in full[:max(0, len(full) - self._keep)]:
            (self._dest / a["name"]).unlink(missing_ok=True)
        per_user: dict[int, list[dict]] = {}
        for a in arcs:
            if a["kind"] == "user":
                per_user.setdefault(a["user"], []).append(a)
        for items in per_user.values():
            for a in items[:max(0, len(items) - self._keep)]:
                (self._dest / a["name"]).unlink(missing_ok=True)
        for p in self._dest.glob("*" + PARTIAL):
            try:
                if self._clock() - p.stat().st_mtime > 86400:
                    p.unlink(missing_ok=True)
            except OSError:
                pass

    def complete_sets(self) -> list[Path]:
        return [self._dest / a["name"] for a in list_archives(self._dest) if a["kind"] == "full"]

    def last_result(self) -> dict:
        return dict(self._last, errors=list(self._last["errors"]))

    def newest_full_epoch(self) -> float | None:
        full = [a for a in list_archives(self._dest) if a["kind"] == "full"]
        return full[-1]["epoch"] if full else None

    def _due(self) -> bool:
        newest = self.newest_full_epoch()
        return newest is None or self._clock() - newest >= self._interval

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
        if self._thread is not None:
            self._thread.join(timeout=30)
        self._thread = None


__all__ = ["EncryptedBackupScheduler", "RestoreError", "WrongKeyError", "CorruptBackupError", "write_archive",
           "verify_archive", "restore_user", "restore_gateway_db", "list_archives", "workspace_in_use"]
