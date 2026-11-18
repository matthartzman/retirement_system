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
import stat
import tarfile
import threading
import time
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from . import fsguard
from .backup_crypto import (BackupCryptoError, CorruptBackupError, DecryptingReader, EncryptingWriter,
                            WrongKeyError)

log = logging.getLogger("retirement.gateway.backup_store")

STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
SUFFIX = ".rpbak"
PARTIAL = ".partial"
_FULL_RE = re.compile(r"^(\d{8}T\d{6}Z)\.rpbak$")
_USER_RE = re.compile(r"^(\d{8}T\d{6}Z)\.user(\d+)\.rpbak$")
FORMAT = 3  # 2: every registered plan file of a user (multiple plans); 3: plus each plan's Financial Insight files
_APP_DB_REL = Path("local_state") / "app.db"
# What a user's plan file may be called in an archive (the worker names them: plan.rpx, plans/<32 hex>.rpx,
# saved_plans/<sanitised name>.rpx). Anything else is never written back, whoever signed the archive.
_PLAN_REL = r"plan\.rpx|plans/[0-9a-f]{32}\.rpx|saved_plans/[A-Za-z0-9 ._()-]{1,100}\.rpx"
_PLAN_REL_RE = re.compile(rf"^(?:{_PLAN_REL})$")
_MEMBER_RE = re.compile(rf"^users/([1-9]\d*)/(app\.db|{_PLAN_REL})$")
_LIVE_PLAN_GLOBS = ("plan.rpx", "plans/*.rpx", "saved_plans/*.rpx")
# Financial Insight files of a plan (format 3): <workspace>/output/plans/<plan_id>/insights/<file>, archived as
# users/<uid>/insights/<plan_id>/<file>. Only these small, hand-made files: the balances SQLite beside them is
# rebuilt from the Monarch export and is not backed up. A separate, strict family: _MEMBER_RE is not widened.
INSIGHT_FILES = ("financial_trends_log.jsonl", "passthrough_decisions.json", "live_snapshot_settings.json")
INSIGHT_MAX_BYTES = 64 * 1024 * 1024  # larger is skipped and reported, never truncated
_INSIGHT_PLAN_ID = r"[0-9a-f]{32}|plan"  # a registry id, or the unregistered workspace plan's stem
_INSIGHT_PLAN_ID_RE = re.compile(rf"^(?:{_INSIGHT_PLAN_ID})$")
_INSIGHT_REL = rf"insights/(?:{_INSIGHT_PLAN_ID})/(?:{'|'.join(re.escape(n) for n in INSIGHT_FILES)})"
_INSIGHT_MEMBER_RE = re.compile(rf"^users/([1-9]\d*)/({_INSIGHT_REL})$")
_INSIGHT_LIVE = Path("output") / "plans"
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


def _insight_live_rel(rel: str) -> Path:
    """``insights/<plan_id>/<file>`` (archive name) -> ``output/plans/<plan_id>/insights/<file>`` (workspace)."""
    _, plan_id, name = rel.split("/")
    return _INSIGHT_LIVE / plan_id / "insights" / name


def _live_insight_rels(root: Path) -> list[str]:
    """Archive names of the insight files present in a workspace (allowlisted names, regular files only)."""
    rels: list[str] = []
    base = Path(root) / _INSIGHT_LIVE
    try:
        folders = sorted(base.iterdir()) if base.is_dir() else []
    except OSError:
        return rels
    for folder in folders:
        if not _INSIGHT_PLAN_ID_RE.fullmatch(folder.name):
            continue
        for name in INSIGHT_FILES:
            if os.path.lexists(folder / "insights" / name):
                rels.append(f"insights/{folder.name}/{name}")
    return rels


def _read_insight(root: Path, rel: str, uid: int, errors: list[str]) -> bytes | None:
    """The bytes to archive for one insight file, or None (skipped; the reason is added to ``errors``).

    No link on the way, a regular file, at most INSIGHT_MAX_BYTES. The trend log is read once; a last line
    without its newline is a torn write and is dropped (reported); other lines are kept as they are (the app
    quarantines an unparseable line itself), but a count of them is reported."""
    src = Path(root) / _insight_live_rel(rel)
    if fsguard.has_reparse_point(src, root):
        errors.append(f"user {uid} {rel}: link inside the workspace, skipped")
        return None
    try:
        st = os.lstat(src)
        if not stat.S_ISREG(st.st_mode):
            errors.append(f"user {uid} {rel}: not a regular file, skipped")
            return None
        if st.st_size > INSIGHT_MAX_BYTES:
            errors.append(f"user {uid} {rel}: larger than {INSIGHT_MAX_BYTES // (1024 * 1024)} MB, skipped")
            return None
        with open(src, "rb") as fh:
            data = fh.read(INSIGHT_MAX_BYTES + 1)
    except OSError as exc:
        errors.append(f"user {uid} {rel}: {type(exc).__name__}")
        return None
    if len(data) > INSIGHT_MAX_BYTES:  # grew while being read
        errors.append(f"user {uid} {rel}: larger than {INSIGHT_MAX_BYTES // (1024 * 1024)} MB, skipped")
        return None
    if rel.endswith(".jsonl") and data:
        if not data.endswith(b"\n"):
            cut = data.rfind(b"\n") + 1
            data = data[:cut]
            errors.append(f"user {uid} {rel}: a torn last line was left out")
        bad = 0
        for line in data.splitlines():
            if not line.strip():
                continue
            try:
                ok = isinstance(json.loads(line), dict)
            except ValueError:
                ok = False
            bad += not ok
        if bad:
            errors.append(f"user {uid} {rel}: {bad} unparseable line(s) kept as they are")
    return data


def _registered_plan_rels(app_db_bytes: bytes, root: Path, uid: int, errors: list[str]) -> list[str]:
    """Workspace-relative POSIX names of the plan files the user's registry lists, each re-verified here:
    the registry is a user-writable file, so nothing in it is trusted (inside the workspace, no link on the
    way, a name the worker could have given, a regular file; the demo plan is reproducible and left out)."""
    rels: list[str] = []
    try:
        con = sqlite3.connect(":memory:")
        try:
            image = bytearray(app_db_bytes)
            image[18] = image[19] = 1  # a WAL-mode image cannot be opened in memory; read it as a rollback-journal file
            con.deserialize(bytes(image))
            rows = con.execute("SELECT path, kind FROM plan_registry").fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return rels
    base = os.path.normcase(os.path.abspath(root))
    for raw, kind in rows:
        if kind == "demo":
            continue
        path = Path(os.path.abspath(str(raw)))
        norm = os.path.normcase(str(path))
        if not norm.startswith(base + os.sep):
            errors.append(f"user {uid}: a plan file outside the workspace, skipped")
            continue
        try:
            rel = path.relative_to(Path(os.path.abspath(root))).as_posix()
        except ValueError:  # same folder spelled in another case: not the name the worker gave it
            errors.append(f"user {uid}: a plan file with an unexpected name, skipped")
            continue
        if not _PLAN_REL_RE.fullmatch(rel):
            errors.append(f"user {uid}: a plan file with an unexpected name, skipped")
            continue
        if fsguard.has_reparse_point(path, root):
            errors.append(f"user {uid} {rel}: link inside the workspace, skipped")
            continue
        if path.is_file() and rel not in rels:
            rels.append(rel)
    return rels


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
                    app_db = root / _APP_DB_REL
                    app_bytes = b""
                    rels = ["plan.rpx"]  # the workspace plan is always backed up, registered or not
                    if app_db.is_file() and not fsguard.has_reparse_point(app_db, root):
                        try:
                            app_bytes = sqlite_bytes(app_db)
                            rels += [r for r in _registered_plan_rels(app_bytes, root, uid, errors) if r not in rels]
                        except Exception as exc:  # noqa: BLE001 - reported per user, never fatal
                            errors.append(f"user {uid} app.db: {type(exc).__name__}")
                            log.error("backup of user %s app.db failed: %s", uid, type(exc).__name__)
                    elif app_db.is_file():
                        errors.append(f"user {uid} app.db: link inside the workspace, skipped")
                    for rel in rels:
                        src = root / rel
                        if fsguard.has_reparse_point(src, root):
                            errors.append(f"user {uid} {rel}: link inside the workspace, skipped")
                            log.error("backup of user %s %s skipped: a link inside the workspace", uid, rel)
                            continue
                        if not src.is_file():
                            continue
                        try:
                            _add(tar, f"users/{int(uid)}/{rel}", sqlite_bytes(src), now)
                            members.append(f"users/{int(uid)}/{rel}")
                            got = True
                        except Exception as exc:  # noqa: BLE001 - reported per user, never fatal
                            errors.append(f"user {uid} {rel}: {type(exc).__name__}")
                            log.error("backup of user %s %s failed: %s", uid, rel, type(exc).__name__)
                    for rel in _live_insight_rels(root):
                        data = _read_insight(root, rel, int(uid), errors)
                        if data is None:
                            log.error("backup of user %s %s skipped", uid, rel)
                            continue
                        _add(tar, f"users/{int(uid)}/{rel}", data, now)
                        members.append(f"users/{int(uid)}/{rel}")
                        got = True
                    if app_bytes:
                        _add(tar, f"users/{int(uid)}/app.db", app_bytes, now)
                        members.append(f"users/{int(uid)}/app.db")
                        got = True
                    if got:
                        users.append(int(uid))
                if gateway_db is not None and Path(gateway_db).is_file():
                    try:
                        _add(tar, "gateway.db", sqlite_bytes(gateway_db), now)
                        members.append("gateway.db")
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"gateway.db: {type(exc).__name__}")
                        log.error("backup of gateway.db failed: %s", type(exc).__name__)
                manifest = {"format": FORMAT, "label": label, "created_utc": datetime.fromtimestamp(now, timezone.utc).isoformat(),
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
    """Replace one user's ``app.db`` and plan files from the archive; no other user is touched.

    The whole archive is authenticated first.  The user's current files are moved aside as
    ``*.before-restore-<stamp>`` (kept until you delete them) and the restored files swapped in.
    A format 2 archive is one point in time for all of the user's plans, so every live plan file
    (plan.rpx, plans/*.rpx, saved_plans/*.rpx) and app.db is moved aside, including plans made after
    the backup; a format 1 archive (plan.rpx and app.db only) replaces just those two.
    A format 3 archive also holds each plan's insight files (``INSIGHT_FILES``): they are restored, and live
    insight files the archive does not hold move aside too. Older archives leave the live insight files alone.
    """
    uid = int(user_id)
    workspace = Path(data_root) / "users" / str(uid)
    manifest = verify_archive(archive, master)
    try:
        fmt = int(manifest.get("format", 1))
    except (TypeError, ValueError):
        fmt = 1
    with_insights = fmt >= 3

    def _match(name: str):
        m = _MEMBER_RE.match(name) or (_INSIGHT_MEMBER_RE.match(name) if with_insights else None)
        return m if m and int(m.group(1)) == uid else None

    wanted = [m for m in manifest.get("members", []) if isinstance(m, str) and _match(m)]
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
                m = _match(member.name)
                if not m or not member.isfile():
                    continue
                if m.group(2).startswith("insights/") and member.size > INSIGHT_MAX_BYTES:
                    continue
                target = staging / m.group(2)
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "wb") as out:
                    shutil.copyfileobj(tar.extractfile(member), out)
            reader.verify_to_end()
        finally:
            tar.close()
            fh.close()
        moved: list[tuple[Path, Path]] = []
        placed: list[Path] = []
        try:
            incoming = sorted((p.relative_to(staging).as_posix() for p in staging.rglob("*") if p.is_file()),
                              key=lambda n: (n == "app.db", n))  # the registry last
            full_set = fmt >= 2
            targets = list(incoming)
            if with_insights:  # live insight files that the archive does not hold move aside too
                for rel in _live_insight_rels(workspace):
                    cur = workspace / _insight_live_rel(rel)
                    if cur.is_file() and not cur.is_symlink() and rel not in targets:
                        targets.append(rel)
            if full_set:  # live plan files that the archive does not hold move aside too
                for pattern in _LIVE_PLAN_GLOBS:
                    for cur in workspace.glob(pattern):
                        rel = cur.relative_to(workspace).as_posix()
                        if cur.is_file() and not cur.is_symlink() and rel not in targets:
                            targets.append(rel)
                if "app.db" not in targets and (workspace / _APP_DB_REL).is_file():
                    targets.append("app.db")
            for member in targets:
                insight = member.startswith("insights/")
                rel = _APP_DB_REL if member == "app.db" else _insight_live_rel(member) if insight else Path(member)
                live = workspace / rel
                if fsguard.has_reparse_point(live, workspace):
                    raise RestoreError(f"user {uid}'s folder holds a link; remove it before restoring")
                live.parent.mkdir(parents=True, exist_ok=True)
                for suffix in ("",) if insight else ("", "-wal", "-shm"):
                    cur = live.with_name(live.name + suffix)
                    if cur.exists():
                        aside = cur.with_name(cur.name + f".before-restore-{stamp}")
                        os.replace(cur, aside)
                        moved.append((cur, aside))
                if member in incoming:
                    os.replace(staging / member, live)
                    placed.append(live)
                    restored.append(str(rel).replace("\\", "/"))
        except BaseException:
            for live in placed:  # a restored file that had no live copy before must not stay behind
                live.unlink(missing_ok=True)
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
    try:
        suspend_restored_shares(partial)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    os.replace(partial, out)
    return out


def suspend_restored_shares(db_path: Path) -> int:
    """Phase 9 (C16): in a restored ``gateway.db``, every active share becomes ``suspended`` (reason ``restored``) and
    no share keeps a published body (bodies are not archived). The owner enables each one again, which republishes
    it. Without this an old ``gateway.db`` would bring back shares revoked since. Returns how many were suspended."""
    import sqlite3  # noqa: PLC0415

    con = sqlite3.connect(db_path, isolation_level=None)
    try:
        con.execute("PRAGMA journal_mode=DELETE")  # no -wal or -shm file is left beside the restored copy
        if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='shares'").fetchone() is None:
            return 0  # a database from before Phase 9 has no shares
        con.execute("BEGIN IMMEDIATE")
        n = con.execute("UPDATE shares SET state='suspended', state_reason='restored' WHERE state='active'").rowcount
        con.execute("UPDATE shares SET published_at=NULL, published_rev=NULL, snapshot_sha256=NULL, snapshot_bytes=NULL")
        con.execute("COMMIT")
        return int(n)
    finally:
        con.close()


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
