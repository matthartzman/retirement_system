"""``gateway.db``: gateway accounts, TOTP secrets, sessions and the authoritative audit log.

Kept apart from every user's plan data and from the trends reporter's ``access.db``. Passwords are
scrypt hashes, session cookies are stored only as SHA-256 hashes, and the audit log never holds
passwords, codes, secrets or cookie values. The schema version is ``PRAGMA user_version``;
``_MIGRATIONS`` is applied in order, one transaction per step.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal

from src import access_core
from src.access_core import LOCK_SECONDS, MAX_FAILED_BEFORE_LOCK  # noqa: F401 - part of this module's API

from . import totp
from .secret_box import PREFIX as SEALED_PREFIX
from .secret_box import SecretBox, default_secret_box

LOG = logging.getLogger("retirement.gateway.store")

SCHEMA_VERSION = 3
ROLES = ("admin", "user")
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,31}$")
IDLE_SECONDS = 15 * 60
ABSOLUTE_SECONDS = 12 * 3600
PENDING_SECONDS = 5 * 60
TOUCH_EVERY_SECONDS = 30
AUDIT_DETAILS_MAX = 300
# scrypt (n=2**15, r=8) holds ~32 MiB while it runs: only this many password hashes at once, and a caller
# waits at most HASH_WAIT_SECONDS for a slot before the gateway answers 503 (P7-O3).
DEFAULT_HASH_CONCURRENCY = 4
HASH_WAIT_SECONDS = 20.0

_MIGRATIONS: list[tuple[int, list[str]]] = [
    (1, [
        """CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
            pw_hash BLOB NOT NULL,
            pw_salt BLOB NOT NULL,
            scrypt_n INTEGER NOT NULL,
            must_change INTEGER NOT NULL DEFAULT 1,
            disabled INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            locked_until REAL NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            last_login_at REAL
        )""",
        """CREATE TABLE totp_secrets (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            secret TEXT NOT NULL,
            created_at REAL NOT NULL,
            enrolled_at REAL,
            last_used_step INTEGER
        )""",
        """CREATE TABLE sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            stage TEXT NOT NULL CHECK (stage IN ('pending', 'active')),
            csrf_token TEXT NOT NULL,
            created_at REAL NOT NULL,
            last_seen REAL NOT NULL,
            expires_at REAL NOT NULL,
            client_ip TEXT NOT NULL DEFAULT ''
        )""",
        "CREATE INDEX sessions_user ON sessions(user_id)",
        """CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at REAL NOT NULL,
            actor_user_id INTEGER,
            actor_username TEXT NOT NULL DEFAULT '',
            event TEXT NOT NULL,
            target_user_id INTEGER,
            target_username TEXT NOT NULL DEFAULT '',
            details TEXT NOT NULL DEFAULT '',
            client_ip TEXT NOT NULL DEFAULT '',
            listener TEXT NOT NULL DEFAULT ''
        )""",
    ]),
    # Phase 3: one Windows account per user. No foreign key: the row must outlive the gateway user so a
    # failed account cleanup can be retried. ``secret`` is the account password, DPAPI-protected for the
    # gateway's own account; it is never returned by any route or written to a log.
    (2, [
        """CREATE TABLE worker_accounts (
            user_id INTEGER PRIMARY KEY,
            account_name TEXT NOT NULL UNIQUE,
            sid TEXT NOT NULL DEFAULT '',
            secret BLOB NOT NULL,
            state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'disabled', 'removing')),
            created_at REAL NOT NULL,
            rotated_at REAL NOT NULL
        )""",
    ]),
    # Admin console phase 2: access expiry (epoch seconds, NULL = never) and admin-only notes. Additive, so an
    # older database keeps every row and works unchanged.
    (3, [
        "ALTER TABLE users ADD COLUMN expires_at REAL",
        "ALTER TABLE users ADD COLUMN notes TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE users ADD COLUMN modules TEXT NOT NULL DEFAULT '{}'",
    ]),
]


KEEP = object()  # "leave this field as it is" for ``set_profile``
NOTES_MAX = 500
MODULE_KEYS = ("snapshot", "trends", "projections")  # Financial Insight's three views (not enforced on the server yet)
MONEY_VIEWS = ("dollars", "percent", "both")


def modules_of(raw) -> dict:
    """The stored Financial Insight flags for a person, always in full: the three views (default off) and money view."""
    try:
        data = json.loads(raw) if isinstance(raw, str) and raw else {}
    except ValueError:
        data = {}
    data = data if isinstance(data, dict) else {}
    out = {k: data.get(k) is True for k in MODULE_KEYS}
    out["money_view"] = data.get("money_view") if data.get("money_view") in MONEY_VIEWS else "percent"
    return out


def _expired(expires_at: float | None, now: float) -> bool:
    return expires_at is not None and now >= expires_at


@dataclass(frozen=True)
class Actor:
    """Who is acting, for the audit log: a signed-in user, or a server-side CLI (``user_id`` None)."""

    user_id: int | None
    username: str
    client_ip: str = ""
    listener: str = ""


@dataclass(frozen=True)
class LoginCheck:
    ok: bool
    user_id: int | None
    reason: Literal["ok", "bad", "locked", "unknown", "disabled"]


class LastAdminError(ValueError):
    """The change would leave no active admin."""


class HashBusyError(RuntimeError):
    """Every password-hashing slot stayed busy for the whole wait; the caller should retry shortly."""


def _token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


class GatewayStore:
    def __init__(self, path: Path | str, scrypt_n: int = access_core.DEFAULT_SCRYPT_N, *,
                 hash_concurrency: int = DEFAULT_HASH_CONCURRENCY, hash_wait: float = HASH_WAIT_SECONDS,
                 secret_box: SecretBox | None = None) -> None:
        self._box = secret_box if secret_box is not None else default_secret_box()
        self.path = Path(path)
        self._n = int(scrypt_n)
        self._hash_slots = threading.BoundedSemaphore(max(1, int(hash_concurrency)))
        self._hash_wait = float(hash_wait)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        finally:
            conn.close()
        self._migrate()

    # ---- plumbing ----
    def _hash(self, password: str, salt: bytes, n: int) -> bytes:
        """``access_core.hash_password`` under the concurrency cap (P7-O3)."""
        if not self._hash_slots.acquire(timeout=self._hash_wait):
            raise HashBusyError("the server is busy checking passwords")
        try:
            return access_core.hash_password(password, salt, n)
        finally:
            self._hash_slots.release()

    def _password_matches(self, password: str, salt: bytes, n: int, expected: bytes) -> bool:
        return hmac.compare_digest(self._hash(password, salt, n), expected)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        finally:
            conn.close()

    def _read(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        conn = self._connect()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def _migrate(self) -> None:
        with self._tx() as conn:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                raise RuntimeError(f"gateway.db schema version {version} is newer than this gateway ({SCHEMA_VERSION})")
            for target, statements in _MIGRATIONS:
                if target <= version:
                    continue
                for sql in statements:
                    conn.execute(sql)
                conn.execute(f"PRAGMA user_version = {int(target)}")
            # Version 3 gained ``modules`` after it was first written; a database already at 3 gets it here.
            if "modules" not in {r[1] for r in conn.execute("PRAGMA table_info(users)")}:
                conn.execute("ALTER TABLE users ADD COLUMN modules TEXT NOT NULL DEFAULT '{}'")

    def schema_version(self) -> int:
        return int(self._read("PRAGMA user_version")[0][0])

    # ---- audit ----
    def audit(self, event: str, *, now: float, actor: Actor, target_user_id: int | None = None,
              target_username: str = "", details: str = "", conn: sqlite3.Connection | None = None) -> None:
        params = (now, actor.user_id, (actor.username or "")[:64], event[:64], target_user_id, (target_username or "")[:64],
                  (details or "")[:AUDIT_DETAILS_MAX], (actor.client_ip or "")[:64], (actor.listener or "")[:16])
        sql = ("INSERT INTO audit_log(at, actor_user_id, actor_username, event, target_user_id, target_username, details,"
               " client_ip, listener) VALUES (?,?,?,?,?,?,?,?,?)")
        if conn is not None:
            conn.execute(sql, params)
            return
        with self._tx() as c:
            c.execute(sql, params)

    def read_audit(self, limit: int = 200) -> list[dict]:
        limit = max(1, min(int(limit), 5000))
        rows = self._read("SELECT at, actor_user_id, actor_username, event, target_user_id, target_username, details,"
                          " client_ip, listener FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    # ---- users ----
    @staticmethod
    def _norm_username(username: str) -> str:
        name = (username or "").strip().lower()
        if not USERNAME_RE.match(name):
            raise ValueError("username must be 2-32 characters: letters, digits, dot, dash or underscore")
        return name

    @staticmethod
    def _check_role(role: str) -> None:
        if role not in ROLES:
            raise ValueError("role must be admin or user")

    @staticmethod
    def check_password(password: str) -> None:
        access_core.check_password_policy(password, MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH)

    def create_user(self, username: str, display_name: str, role: str, password: str, *, now: float, actor: Actor,
                    must_change: bool = True, event: str = "user created") -> int:
        name = self._norm_username(username)
        display = (display_name or "").strip()[:80] or name
        self._check_role(role)
        self.check_password(password)
        salt = access_core.new_salt()
        digest = self._hash(password, salt, self._n)
        try:
            with self._tx() as conn:
                cur = conn.execute(
                    "INSERT INTO users(username, display_name, role, pw_hash, pw_salt, scrypt_n, must_change, created_at,"
                    " updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (name, display, role, digest, salt, self._n, int(bool(must_change)), now, now))
                uid = int(cur.lastrowid)
                self.audit(event, now=now, actor=actor, target_user_id=uid, target_username=name, details=f"role {role}",
                           conn=conn)
        except sqlite3.IntegrityError:
            raise ValueError("that username is already in use") from None
        return uid

    def get_user(self, user_id: int) -> dict | None:
        rows = self._read("SELECT * FROM users WHERE id=?", (int(user_id),))
        return dict(rows[0]) if rows else None

    def find_user(self, username: str) -> dict | None:
        rows = self._read("SELECT * FROM users WHERE username=?", ((username or "").strip().lower(),))
        return dict(rows[0]) if rows else None

    def list_users(self, now: float) -> list[dict]:
        rows = self._read(
            "SELECT u.id, u.username, u.display_name, u.role, u.disabled, u.locked_until, u.must_change, u.last_login_at,"
            " u.created_at, u.expires_at, u.notes, u.modules, t.enrolled_at, t.user_id AS has_totp FROM users u LEFT JOIN totp_secrets t ON t.user_id = u.id"
            " ORDER BY u.username")
        return [{
            "id": r["id"], "username": r["username"], "display_name": r["display_name"], "role": r["role"],
            "disabled": bool(r["disabled"]), "locked": r["locked_until"] > now, "must_change": bool(r["must_change"]),
            "totp": "enrolled" if r["enrolled_at"] is not None else ("pending" if r["has_totp"] is not None else "none"),
            "last_login_at": r["last_login_at"], "created_at": r["created_at"],
            "expires_at": r["expires_at"], "expired": _expired(r["expires_at"], now), "notes": r["notes"],
            "modules": modules_of(r["modules"]),
        } for r in rows]

    def count_active_admins(self, conn: sqlite3.Connection | None = None, now: float | None = None) -> int:
        """Admins who can sign in: not disabled and not past their access expiry."""
        sql = "SELECT COUNT(*) FROM users WHERE role='admin' AND disabled=0 AND (expires_at IS NULL OR expires_at > ?)"
        params = (time.time() if now is None else now,)
        if conn is not None:
            return int(conn.execute(sql, params).fetchone()[0])
        return int(self._read(sql, params)[0][0])

    @staticmethod
    def _locked_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM users WHERE id=?", (int(user_id),)).fetchone()
        if row is None:
            raise LookupError("no such user")
        return row

    def _guard_last_admin(self, conn: sqlite3.Connection, row: sqlite3.Row, now: float) -> None:
        usable = row["role"] == "admin" and not row["disabled"] and not _expired(row["expires_at"], now)
        if usable and self.count_active_admins(conn, now) <= 1:
            raise LastAdminError("this is the last active admin; promote another admin first")

    def set_role(self, user_id: int, role: str, *, now: float, actor: Actor) -> None:
        self._check_role(role)
        with self._tx() as conn:
            row = self._locked_user(conn, user_id)
            if row["role"] == role:
                return
            if role != "admin":
                self._guard_last_admin(conn, row, now)
            conn.execute("UPDATE users SET role=?, updated_at=? WHERE id=?", (role, now, row["id"]))
            self._end_user_sessions(conn, row["id"])
            self.audit("role changed", now=now, actor=actor, target_user_id=row["id"], target_username=row["username"],
                       details=f"{row['role']} -> {role}", conn=conn)

    def set_disabled(self, user_id: int, disabled: bool, *, now: float, actor: Actor) -> None:
        with self._tx() as conn:
            row = self._locked_user(conn, user_id)
            if bool(row["disabled"]) == bool(disabled):
                return
            if disabled:
                self._guard_last_admin(conn, row, now)
                self._end_user_sessions(conn, row["id"])
            conn.execute("UPDATE users SET disabled=?, updated_at=? WHERE id=?", (int(bool(disabled)), now, row["id"]))
            self.audit("user disabled" if disabled else "user enabled", now=now, actor=actor, target_user_id=row["id"],
                       target_username=row["username"], conn=conn)

    def delete_user(self, user_id: int, *, now: float, actor: Actor) -> None:
        with self._tx() as conn:
            row = self._locked_user(conn, user_id)
            self._guard_last_admin(conn, row, now)
            conn.execute("DELETE FROM users WHERE id=?", (row["id"],))
            self.audit("user deleted", now=now, actor=actor, target_user_id=row["id"], target_username=row["username"],
                       conn=conn)

    @staticmethod
    def check_profile(*, display_name=KEEP, notes=KEEP, expires_at=KEEP, modules=KEEP) -> dict:
        """Validate and clean the editable profile fields; keys left at KEEP are omitted from the result."""
        out: dict = {}
        if display_name is not KEEP:
            if not isinstance(display_name, str):
                raise ValueError("the name must be text")
            name = display_name.strip()
            if not name or len(name) > 80 or any(ord(c) < 32 or ord(c) == 127 for c in name):
                raise ValueError("the name must be 1 to 80 characters, with no control characters")
            out["display_name"] = name
        if notes is not KEEP:
            if not isinstance(notes, str):
                raise ValueError("notes must be text")
            if len(notes) > NOTES_MAX or any((ord(c) < 32 and c not in "\n\r\t") or ord(c) == 127 for c in notes):
                raise ValueError(f"notes can be up to {NOTES_MAX} characters, with no control characters")
            out["notes"] = notes
        if expires_at is not KEEP:
            if expires_at is not None:
                if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)) \
                        or not math.isfinite(expires_at) or expires_at <= 0:
                    raise ValueError("the access end must be a date, or empty for never")
                expires_at = float(expires_at)
            out["expires_at"] = expires_at
        if modules is not KEEP:
            if not isinstance(modules, dict) or set(modules) - set(MODULE_KEYS) - {"money_view"}:
                raise ValueError("modules must name only snapshot, trends, projections and money_view")
            if any(not isinstance(modules[k], bool) for k in MODULE_KEYS if k in modules):
                raise ValueError("each module must be on or off")
            if "money_view" in modules and modules["money_view"] not in MONEY_VIEWS:
                raise ValueError("money view must be dollars, percent or both")
            out["modules"] = json.dumps(modules_of(json.dumps(modules)), sort_keys=True)
        return out

    def set_profile(self, user_id: int, *, now: float, actor: Actor, display_name=KEEP, notes=KEEP,
                    expires_at=KEEP, modules=KEEP) -> dict:
        """Edit name, notes and access expiry. Returns ``{"expired": bool, "expiry_changed_access": bool}``.

        The audit row lists which fields changed but never the notes text. Making the last usable admin expire
        is refused like demoting or disabling them.
        """
        fields = self.check_profile(display_name=display_name, notes=notes, expires_at=expires_at, modules=modules)
        with self._tx() as conn:
            row = self._locked_user(conn, user_id)
            before = _expired(row["expires_at"], now)
            changed = [k for k, v in fields.items()
                       if (modules_of(row[k]) != modules_of(v) if k == "modules" else row[k] != v)]
            after = _expired(fields.get("expires_at", row["expires_at"]), now)
            if not changed:
                return {"expired": after, "expiry_changed_access": False}
            if after and not before:
                usable_admin = row["role"] == "admin" and not row["disabled"]
                if usable_admin and self.count_active_admins(conn, now) <= 1:
                    raise LastAdminError("this is the last active admin; promote another admin first")
            sets = ", ".join(f"{k}=?" for k in changed)
            conn.execute(f"UPDATE users SET {sets}, updated_at=? WHERE id=?",
                         tuple(fields[k] for k in changed) + (now, row["id"]))
            if after:
                self._end_user_sessions(conn, row["id"])
            label = {"display_name": "name", "notes": "notes", "expires_at": "expiry", "modules": "modules"}
            self.audit("profile changed", now=now, actor=actor, target_user_id=row["id"],
                       target_username=row["username"], details=", ".join(label[k] for k in changed), conn=conn)
        return {"expired": after, "expiry_changed_access": after != before}

    def end_sessions(self, user_id: int, *, now: float, actor: Actor) -> int:
        """Sign a person out everywhere. Returns how many sessions were removed."""
        with self._tx() as conn:
            row = self._locked_user(conn, user_id)
            n = int(conn.execute("SELECT COUNT(*) FROM sessions WHERE user_id=?", (row["id"],)).fetchone()[0])
            self._end_user_sessions(conn, row["id"])
            self.audit("sessions ended", now=now, actor=actor, target_user_id=row["id"],
                       target_username=row["username"], details=f"{n} session(s)", conn=conn)
        return n

    def set_password(self, user_id: int, password: str, *, must_change: bool, now: float, actor: Actor,
                     event: str = "password changed", keep_session: str | None = None) -> None:
        """Set a password, clear any lockout and end the user's sessions (except ``keep_session``, a cookie value)."""
        self.check_password(password)
        salt = access_core.new_salt()
        digest = self._hash(password, salt, self._n)
        with self._tx() as conn:
            row = self._locked_user(conn, user_id)
            conn.execute("UPDATE users SET pw_hash=?, pw_salt=?, scrypt_n=?, must_change=?, failed_count=0, locked_until=0,"
                         " updated_at=? WHERE id=?", (digest, salt, self._n, int(bool(must_change)), now, row["id"]))
            self._end_user_sessions(conn, row["id"], except_hash=_token_hash(keep_session) if keep_session else None)
            self.audit(event, now=now, actor=actor, target_user_id=row["id"], target_username=row["username"], conn=conn)

    def unlock(self, user_id: int, *, now: float, actor: Actor, event: str | None = "user unlocked") -> None:
        with self._tx() as conn:
            row = self._locked_user(conn, user_id)
            conn.execute("UPDATE users SET failed_count=0, locked_until=0, updated_at=? WHERE id=?", (now, row["id"]))
            if event:
                self.audit(event, now=now, actor=actor, target_user_id=row["id"], target_username=row["username"], conn=conn)

    def check_current_password(self, user_id: int, password: str) -> bool:
        user = self.get_user(user_id)
        if not user:
            return False
        return self._password_matches(password, user["pw_salt"], user["scrypt_n"], user["pw_hash"])

    # ---- sign-in ----
    def verify_password(self, username: str, password: str, now: float) -> LoginCheck:
        user = self.find_user(username)
        if user is None:
            self._hash(password, access_core._DUMMY_SALT, self._n)
            return LoginCheck(False, None, "unknown")
        if user["locked_until"] > now:
            self._hash(password, access_core._DUMMY_SALT, self._n)
            return LoginCheck(False, user["id"], "locked")
        matches = self._password_matches(password, user["pw_salt"], user["scrypt_n"], user["pw_hash"])
        if user["disabled"]:
            return LoginCheck(False, user["id"], "disabled")
        if matches and _expired(user["expires_at"], now):
            return LoginCheck(False, user["id"], "expired")  # same generic error as any failure; not a lockout count
        if matches:
            # Not cleared here: wrong second-factor codes keep counting until the sign-in completes
            # (``touch_login``), so re-entering the password cannot reset an attacker's guess budget.
            return LoginCheck(True, user["id"], "ok")
        locked = self.record_failure(user["id"], now)
        return LoginCheck(False, user["id"], "locked" if locked else "bad")

    def record_failure(self, user_id: int, now: float) -> bool:
        """Count one failed password or code; True when this failure locks the account."""
        with self._tx() as conn:
            row = conn.execute("SELECT failed_count, locked_until FROM users WHERE id=?", (int(user_id),)).fetchone()
            if row is None:
                return False
            if row["locked_until"] > now:
                return True  # a failure that raced past the lock check must not erase the lock
            failed, locked_until = access_core.failure_outcome(row["failed_count"], now)
            conn.execute("UPDATE users SET failed_count=?, locked_until=? WHERE id=?", (failed, locked_until, int(user_id)))
            if locked_until:
                self._end_user_sessions(conn, int(user_id), stage="pending")
            return bool(locked_until)

    def clear_failures(self, user_id: int) -> None:
        with self._tx() as conn:
            conn.execute("UPDATE users SET failed_count=0 WHERE id=?", (int(user_id),))

    def is_locked(self, user_id: int, now: float) -> bool:
        user = self.get_user(user_id)
        return bool(user and user["locked_until"] > now)

    def touch_login(self, user_id: int, now: float) -> None:
        with self._tx() as conn:
            conn.execute("UPDATE users SET last_login_at=?, failed_count=0 WHERE id=?", (now, int(user_id)))

    # ---- TOTP ----
    def _totp_row(self, user_id: int) -> sqlite3.Row | None:
        rows = self._read("SELECT * FROM totp_secrets WHERE user_id=?", (int(user_id),))
        return rows[0] if rows else None

    def _totp_secret(self, user_id: int) -> str | None:
        """The clear secret, or None when there is none or this account cannot open the sealed one."""
        row = self._totp_row(user_id)
        return self._box.unprotect(row["secret"]) if row else None

    def protect_totp_secrets(self) -> int:
        """Seal every clear-text TOTP secret in place (P7-O1); the number sealed. Safe to repeat.

        Run by the gateway service at start-up, never by a CLI run as another account: DPAPI seals for the account
        that calls it. Freed pages are overwritten and the WAL is truncated so the old clear text does not linger."""
        sealed = 0
        with self._tx() as conn:
            conn.execute("PRAGMA secure_delete=ON")
            rows = conn.execute("SELECT user_id, secret FROM totp_secrets WHERE substr(secret, 1, ?) <> ?",
                                (len(SEALED_PREFIX), SEALED_PREFIX)).fetchall()
            for row in rows:
                blob = self._box.protect(row["secret"])
                if self._box.unprotect(blob) != row["secret"]:
                    raise RuntimeError("a sealed TOTP secret did not read back; leaving the database unchanged")
                conn.execute("UPDATE totp_secrets SET secret=? WHERE user_id=?", (blob, row["user_id"]))
                sealed += 1
        if sealed:
            conn = self._connect()
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                conn.close()
            LOG.info("sealed %d TOTP secret(s) in gateway.db", sealed)
        return sealed

    def unreadable_totp_users(self) -> list[int]:
        """Users whose sealed TOTP secret this account cannot open (a database restored on another machine)."""
        rows = self._read("SELECT user_id, secret FROM totp_secrets ORDER BY user_id")
        return [int(r["user_id"]) for r in rows if self._box.unprotect(r["secret"]) is None]

    def totp_status(self, user_id: int) -> Literal["none", "pending", "enrolled"]:
        row = self._totp_row(user_id)
        if row is None:
            return "none"
        return "enrolled" if row["enrolled_at"] is not None else "pending"

    def begin_totp_enrolment(self, user_id: int, now: float) -> str:
        with self._tx() as conn:
            row = conn.execute("SELECT * FROM totp_secrets WHERE user_id=?", (int(user_id),)).fetchone()
            if row is not None and row["enrolled_at"] is not None:
                raise ValueError("two-factor is already set up; an admin can reset it")
            if row is not None:
                existing = self._box.unprotect(str(row["secret"]))
                if existing is not None:
                    return existing
                conn.execute("DELETE FROM totp_secrets WHERE user_id=?", (int(user_id),))  # sealed elsewhere: start over
            secret = totp.new_secret()
            conn.execute("INSERT INTO totp_secrets(user_id, secret, created_at) VALUES (?,?,?)",
                         (int(user_id), self._box.protect(secret), now))
            return secret

    def _use_code(self, user_id: int, code: str, now: float, enrolled: bool) -> bool:
        with self._tx() as conn:
            row = conn.execute("SELECT * FROM totp_secrets WHERE user_id=?", (int(user_id),)).fetchone()
            if row is None or (row["enrolled_at"] is not None) != enrolled:
                return False
            secret = self._box.unprotect(row["secret"])
            if secret is None:
                LOG.error("the TOTP secret of user %s cannot be opened on this machine; an admin must reset it", user_id)
                return False
            step = totp.verify(secret, code, now, row["last_used_step"])
            if step is None:
                return False
            conn.execute("UPDATE totp_secrets SET last_used_step=?, enrolled_at=COALESCE(enrolled_at, ?) WHERE user_id=?",
                         (step, now, int(user_id)))
            return True

    def confirm_totp(self, user_id: int, code: str, now: float) -> bool:
        return self._use_code(user_id, code, now, enrolled=False)

    def verify_totp(self, user_id: int, code: str, now: float) -> bool:
        return self._use_code(user_id, code, now, enrolled=True)

    def reset_totp(self, user_id: int, *, now: float, actor: Actor, event: str | None = "totp reset") -> None:
        with self._tx() as conn:
            row = self._locked_user(conn, user_id)
            conn.execute("DELETE FROM totp_secrets WHERE user_id=?", (row["id"],))
            self._end_user_sessions(conn, row["id"])
            if event:
                self.audit(event, now=now, actor=actor, target_user_id=row["id"], target_username=row["username"], conn=conn)

    # ---- sessions ----
    def create_session(self, user_id: int, stage: str, now: float, client_ip: str) -> tuple[str, str]:
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        life = PENDING_SECONDS if stage == "pending" else ABSOLUTE_SECONDS
        with self._tx() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at <= ? OR (stage='active' AND last_seen <= ?)",
                         (now, now - IDLE_SECONDS))
            conn.execute("INSERT INTO sessions(token_hash, user_id, stage, csrf_token, created_at, last_seen, expires_at,"
                         " client_ip) VALUES (?,?,?,?,?,?,?,?)",
                         (_token_hash(token), int(user_id), stage, csrf, now, now, now + life, (client_ip or "")[:64]))
        return token, csrf

    def get_session(self, token: str | None, now: float) -> dict | None:
        if not token:
            return None
        h = _token_hash(token)
        rows = self._read("SELECT s.*, u.username, u.display_name, u.role, u.must_change, u.disabled, u.expires_at AS user_expires_at FROM sessions s"
                          " JOIN users u ON u.id = s.user_id WHERE s.token_hash=?", (h,))
        if not rows:
            return None
        sess = dict(rows[0])
        if _expired(sess.pop("user_expires_at"), now):
            self.end_session(token)
            return None
        idle = sess["stage"] == "active" and now - sess["last_seen"] >= IDLE_SECONDS
        if now >= sess["expires_at"] or idle or sess["disabled"]:
            self.end_session(token)
            return None
        return sess

    def touch_session(self, token: str, now: float) -> None:
        with self._tx() as conn:
            conn.execute("UPDATE sessions SET last_seen=? WHERE token_hash=? AND ? - last_seen >= ?",
                         (now, _token_hash(token), now, TOUCH_EVERY_SECONDS))

    def rotate_session(self, token: str, stage: str, now: float) -> tuple[str, str]:
        """Replace a session with a fresh cookie value and CSRF token (used when the stage changes)."""
        new_token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        life = PENDING_SECONDS if stage == "pending" else ABSOLUTE_SECONDS
        with self._tx() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE token_hash=?", (_token_hash(token),)).fetchone()
            if row is None:
                raise LookupError("no such session")
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (row["token_hash"],))
            conn.execute("INSERT INTO sessions(token_hash, user_id, stage, csrf_token, created_at, last_seen, expires_at,"
                         " client_ip) VALUES (?,?,?,?,?,?,?,?)",
                         (_token_hash(new_token), row["user_id"], stage, csrf, now, now, now + life, row["client_ip"]))
        return new_token, csrf

    def end_session(self, token: str | None) -> None:
        with self._tx() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token or ""),))

    @staticmethod
    def _end_user_sessions(conn: sqlite3.Connection, user_id: int, except_hash: str | None = None,
                           stage: str | None = None) -> None:
        sql, params = "DELETE FROM sessions WHERE user_id=?", [int(user_id)]
        if except_hash:
            sql += " AND token_hash<>?"
            params.append(except_hash)
        if stage:
            sql += " AND stage=?"
            params.append(stage)
        conn.execute(sql, tuple(params))

    def count_user_sessions(self, user_id: int, now: float) -> int:
        """Active, unexpired sessions the user still has (the supervisor stops a worker after the last)."""
        rows = self._read("SELECT COUNT(*) FROM sessions WHERE user_id=? AND stage='active' AND expires_at>? AND ?-last_seen<?",
                          (int(user_id), now, now, IDLE_SECONDS))
        return int(rows[0][0])

    def user_ids(self) -> set[int]:
        return {int(r[0]) for r in self._read("SELECT id FROM users")}

    # ---- worker accounts (Phase 3) ----
    def put_worker_account(self, user_id: int, account_name: str, sid: str, secret: bytes, now: float) -> None:
        with self._tx() as conn:
            conn.execute("INSERT INTO worker_accounts(user_id, account_name, sid, secret, state, created_at, rotated_at)"
                         " VALUES (?,?,?,?, 'active', ?, ?)", (int(user_id), account_name, sid, secret, now, now))

    def get_worker_account(self, user_id: int) -> dict | None:
        rows = self._read("SELECT * FROM worker_accounts WHERE user_id=?", (int(user_id),))
        return dict(rows[0]) if rows else None

    def list_worker_accounts(self) -> list[dict]:
        return [dict(r) for r in self._read("SELECT user_id, account_name, sid, state, created_at, rotated_at"
                                            " FROM worker_accounts ORDER BY user_id")]

    def update_worker_account(self, user_id: int, *, sid: str | None = None, secret: bytes | None = None,
                              state: str | None = None, rotated_at: float | None = None) -> None:
        sets, params = [], []
        for col, val in (("sid", sid), ("secret", secret), ("state", state), ("rotated_at", rotated_at)):
            if val is not None:
                sets.append(f"{col}=?")
                params.append(val)
        if not sets:
            return
        with self._tx() as conn:
            conn.execute(f"UPDATE worker_accounts SET {', '.join(sets)} WHERE user_id=?", (*params, int(user_id)))

    def delete_worker_account(self, user_id: int) -> None:
        with self._tx() as conn:
            conn.execute("DELETE FROM worker_accounts WHERE user_id=?", (int(user_id),))

    def end_user_sessions(self, user_id: int) -> None:
        with self._tx() as conn:
            self._end_user_sessions(conn, user_id)
