"""Remote-access accounts (``data/access.db``): scrypt-hashed passwords, lockout and sign-in throttle.

Kept apart from the financial data. Passwords are never stored or logged in readable form.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DB_FILENAME = "access.db"
MIN_PASSWORD_LENGTH = 10
MAX_FAILED_BEFORE_LOCK = 5
LOCK_SECONDS = 15 * 60
THROTTLE_WINDOW_SECONDS = 10 * 60
THROTTLE_FREE_FAILURES = 20
THROTTLE_MAX_DELAY_SECONDS = 60.0
SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL,
    username TEXT NOT NULL UNIQUE,
    pw_hash BLOB NOT NULL,
    pw_salt BLOB NOT NULL,
    scrypt_n INTEGER NOT NULL,
    must_change INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    failed_count INTEGER NOT NULL DEFAULT 0,
    locked_until REAL NOT NULL DEFAULT 0,
    last_signin_at REAL
)
"""


@dataclass(frozen=True)
class LoginResult:
    ok: bool
    user_id: int | None
    must_change: bool
    reason: Literal["ok", "bad", "locked"]


class AccessStore:
    def __init__(self, path: Path, scrypt_n: int = 2**15) -> None:
        self.path = Path(path)
        self._n = scrypt_n
        self._lock = threading.RLock()
        self._failures: list[float] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            conn = self._conn()
            try:
                conn.execute(_SCHEMA)
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                self._init_extra(conn)
                conn.commit()
            finally:
                conn.close()

    def _init_extra(self, conn: sqlite3.Connection) -> None:
        """Hook for further tables (the activity log)."""

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _run(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute one statement, commit, and return a cursor whose rows are already fetched."""
        with self._lock:
            conn = self._conn()
            try:
                cur = conn.execute(sql, params)
                rows = cur.fetchall()
                conn.commit()
                result = _Result(rows, cur.lastrowid)
            finally:
                conn.close()
            return result  # type: ignore[return-value]

    @staticmethod
    def _hash(password: str, salt: bytes, n: int) -> bytes:
        return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=8, p=1, maxmem=128 * 1024 * 1024, dklen=32)

    @staticmethod
    def _check_password(password: str) -> None:
        if len(password or "") < MIN_PASSWORD_LENGTH:
            raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")

    # ---- people ----
    def add_user(self, display_name: str, username: str, temp_password: str, now: float = 0.0) -> int:
        username = (username or "").strip().lower()
        if not username or not (display_name or "").strip():
            raise ValueError("name and username are required")
        self._check_password(temp_password)
        salt = secrets.token_bytes(16)
        try:
            cur = self._run(
                "INSERT INTO users(display_name, username, pw_hash, pw_salt, scrypt_n, must_change, created_at, updated_at)"
                " VALUES (?,?,?,?,?,1,?,?)",
                (display_name.strip(), username, self._hash(temp_password, salt, self._n), salt, self._n, now, now),
            )
        except sqlite3.IntegrityError:
            raise ValueError("that username is already in use") from None
        return int(cur.lastrowid)

    def get_user(self, user_id: int) -> dict | None:
        rows = self._run("SELECT * FROM users WHERE id=?", (user_id,)).fetchall()
        return dict(rows[0]) if rows else None

    def list_users(self, now: float = 0.0) -> list[dict]:
        rows = self._run("SELECT * FROM users ORDER BY display_name").fetchall()
        return [
            {
                "id": r["id"], "display_name": r["display_name"], "username": r["username"],
                "last_signin_at": r["last_signin_at"], "must_change": bool(r["must_change"]),
                "locked": r["locked_until"] > now,
            }
            for r in rows
        ]

    def delete_user(self, user_id: int) -> None:
        self._run("DELETE FROM users WHERE id=?", (user_id,))

    def set_password(self, user_id: int, new_password: str, must_change: bool, now: float = 0.0) -> None:
        """Set a password and clear any lockout (an owner reset or a person's own change)."""
        self._check_password(new_password)
        salt = secrets.token_bytes(16)
        self._run(
            "UPDATE users SET pw_hash=?, pw_salt=?, scrypt_n=?, must_change=?, updated_at=?, failed_count=0, locked_until=0 WHERE id=?",
            (self._hash(new_password, salt, self._n), salt, self._n, int(must_change), now, user_id),
        )

    def touch_last_signin(self, user_id: int, now: float) -> None:
        self._run("UPDATE users SET last_signin_at=? WHERE id=?", (now, user_id))

    def check_current_password(self, user_id: int, password: str) -> bool:
        user = self.get_user(user_id)
        if not user:
            return False
        digest = self._hash(password or "", user["pw_salt"], user["scrypt_n"])
        return hmac.compare_digest(digest, user["pw_hash"])

    # ---- sign-in ----
    def verify_login(self, username: str, password: str, now: float) -> LoginResult:
        username = (username or "").strip().lower()
        with self._lock:
            rows = self._run("SELECT * FROM users WHERE username=?", (username,)).fetchall()
            if not rows:
                self._hash(password or "", b"\0" * 16, self._n)  # same work as a real check
                self._failures.append(now)
                return LoginResult(False, None, False, "bad")
            row = rows[0]
            if row["locked_until"] > now:
                return LoginResult(False, row["id"], False, "locked")
            digest = self._hash(password or "", row["pw_salt"], row["scrypt_n"])
            if hmac.compare_digest(digest, row["pw_hash"]):
                self._run("UPDATE users SET failed_count=0 WHERE id=?", (row["id"],))
                return LoginResult(True, row["id"], bool(row["must_change"]), "ok")
            self._failures.append(now)
            failed, locked_until = row["failed_count"] + 1, 0.0
            if failed >= MAX_FAILED_BEFORE_LOCK:
                failed, locked_until = 0, now + LOCK_SECONDS
            self._run("UPDATE users SET failed_count=?, locked_until=? WHERE id=?", (failed, locked_until, row["id"]))
            return LoginResult(False, row["id"], False, "locked" if locked_until else "bad")

    def global_delay(self, now: float) -> float:
        """Seconds sign-ins must be refused for: 0 until ~20 failures in 10 minutes, then growing."""
        with self._lock:
            self._failures = [t for t in self._failures if now - t < THROTTLE_WINDOW_SECONDS]
            over = len(self._failures) - THROTTLE_FREE_FAILURES
            if over <= 0:
                return 0.0
            return min(THROTTLE_MAX_DELAY_SECONDS, float(2 ** min(over, 10)))

    def last_failure_at(self) -> float:
        with self._lock:
            return self._failures[-1] if self._failures else 0.0


class _Result:
    def __init__(self, rows: list, lastrowid: int | None) -> None:
        self._rows = rows
        self.lastrowid = lastrowid

    def fetchall(self) -> list:
        return self._rows
