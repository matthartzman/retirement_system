"""Shared identity store: accounts, app grants, session epochs, activity and the admin audit.

Generalised from the Financial Insights ``AccessStore``. One SQLite file (``local_state/identity.db``)
holds every sign-in for every app. Passwords are scrypt-hashed and never stored or logged readably.
Schema version starts at 3 so it continues from ``access.db``'s ``user_version = 2``.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from src import access_core
from src.access_core import LOCK_SECONDS, MAX_FAILED_BEFORE_LOCK, MIN_PASSWORD_LENGTH  # noqa: F401 - public names

DB_FILENAME = "identity.db"
LEGACY_ACCESS_DB = "access.db"
SCHEMA_VERSION = 3
THROTTLE_WINDOW_SECONDS = 10 * 60
THROTTLE_FREE_FAILURES = 20
THROTTLE_MAX_DELAY_SECONDS = 60.0
MONEY_VIEWS = ("dollars", "percent", "both")
APPS = ("insights", "planner")
ROLES = ("admin", "user")
STATUSES = ("active", "disabled")

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
    last_signin_at REAL,
    role TEXT NOT NULL DEFAULT 'user',
    status TEXT NOT NULL DEFAULT 'active',
    expires_at REAL,
    session_epoch INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS app_grants (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    app TEXT NOT NULL,
    money_view TEXT,
    views TEXT,
    granted_by TEXT NOT NULL DEFAULT '',
    granted_at REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, app)
);
CREATE TABLE IF NOT EXISTS totp (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    secret BLOB NOT NULL,
    enrolled_at REAL NOT NULL,
    last_used_step INTEGER NOT NULL DEFAULT 0,
    recovery_codes TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at REAL NOT NULL,
    person TEXT NOT NULL,
    listener TEXT NOT NULL,
    event TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    app TEXT NOT NULL DEFAULT 'insights'
);
CREATE TABLE IF NOT EXISTS admin_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at REAL NOT NULL,
    admin TEXT NOT NULL,
    action TEXT NOT NULL,
    target_user TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT ''
);
"""


@dataclass(frozen=True)
class LoginResult:
    ok: bool
    user_id: int | None
    must_change: bool
    reason: Literal["ok", "bad", "locked"]


class LastAdminError(ValueError):
    """The change would leave no active administrator."""


def default_db_path() -> Path:
    from src import platform_runtime

    return platform_runtime.workspace_root() / "local_state" / DB_FILENAME


class IdentityStore:
    def __init__(self, path: Path, scrypt_n: int = 2**15) -> None:
        self.path = Path(path)
        self._n = scrypt_n
        self._lock = threading.RLock()
        self._throttle = access_core.FailureThrottle(THROTTLE_WINDOW_SECONDS, THROTTLE_FREE_FAILURES, THROTTLE_MAX_DELAY_SECONDS)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            conn = self._conn()
            try:
                conn.executescript(_SCHEMA)
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                conn.commit()
            finally:
                conn.close()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _run(self, sql: str, params: tuple = ()) -> "_Result":
        """Execute one statement, commit, and return a result whose rows are already fetched."""
        with self._lock:
            conn = self._conn()
            try:
                cur = conn.execute(sql, params)
                rows = cur.fetchall()
                conn.commit()
                return _Result(rows, cur.lastrowid, cur.rowcount)
            finally:
                conn.close()

    @staticmethod
    def _now(now: float | None) -> float:
        return time.time() if now is None else float(now)

    @staticmethod
    def _check_money_view(money_view: str) -> None:
        if money_view not in MONEY_VIEWS:
            raise ValueError("money view must be dollars, percent or both")

    @staticmethod
    def _check_app(app: str) -> None:
        if app not in APPS:
            raise ValueError("app must be insights or planner")

    # ---- admin rule ----
    @staticmethod
    def _is_active_admin(user: dict, now: float) -> bool:
        return (user["role"] == "admin" and user["status"] == "active"
                and (user["expires_at"] is None or user["expires_at"] > now))

    def _other_active_admins(self, user_id: int, now: float) -> int:
        rows = self._run("SELECT * FROM users WHERE role='admin' AND status='active' AND id<>?", (user_id,)).fetchall()
        return sum(1 for r in rows if r["expires_at"] is None or r["expires_at"] > now)

    def _guard_last_admin(self, user_id: int, now: float) -> None:
        user = self.get_user(user_id)
        if user and self._is_active_admin(user, now) and self._other_active_admins(user_id, now) == 0:
            raise LastAdminError("the last active administrator cannot be demoted, disabled, expired or deleted")

    # ---- people ----
    def add_user(self, display_name: str, username: str, temp_password: str, now: float | None = None, *,
                 role: str = "user", expires_at: float | None = None, notes: str = "",
                 money_view: str | None = "percent", insights: bool = True, must_change: bool = True,
                 granted_by: str = "") -> int:
        """Create an account. ``insights=True`` (the default) also gives the Financial Insights grant."""
        now = self._now(now)
        username = (username or "").strip().lower()
        if not username or not (display_name or "").strip():
            raise ValueError("name and username are required")
        if role not in ROLES:
            raise ValueError("role must be admin or user")
        access_core.check_password_policy(temp_password)
        if insights:
            self._check_money_view(money_view or "percent")
        salt = access_core.new_salt()
        try:
            cur = self._run(
                "INSERT INTO users(display_name, username, pw_hash, pw_salt, scrypt_n, must_change, created_at, updated_at,"
                " role, expires_at, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (display_name.strip(), username, access_core.hash_password(temp_password, salt, self._n), salt, self._n,
                 int(must_change), now, now, role, expires_at, (notes or "")[:500]),
            )
        except sqlite3.IntegrityError:
            raise ValueError("that username is already in use") from None
        uid = int(cur.lastrowid)
        if insights:
            self.set_grant(uid, "insights", money_view=money_view or "percent", granted_by=granted_by, now=now, bump=False)
        return uid

    def get_user(self, user_id: int) -> dict | None:
        rows = self._run("SELECT * FROM users WHERE id=?", (user_id,)).fetchall()
        if not rows:
            return None
        user = dict(rows[0])
        grant = self.get_grant(user_id, "insights")
        user["money_view"] = (grant or {}).get("money_view") or "percent"  # Financial Insights compatibility shape
        return user

    def get_user_by_username(self, username: str) -> dict | None:
        rows = self._run("SELECT id FROM users WHERE username=?", ((username or "").strip().lower(),)).fetchall()
        return self.get_user(rows[0]["id"]) if rows else None

    def list_users(self, now: float | None = None) -> list[dict]:
        now = self._now(now)
        out = []
        for r in self._run("SELECT * FROM users ORDER BY display_name").fetchall():
            grants = self.list_grants(r["id"])
            out.append({
                "id": r["id"], "display_name": r["display_name"], "username": r["username"], "role": r["role"],
                "status": r["status"], "expires_at": r["expires_at"], "notes": r["notes"],
                "expired": r["expires_at"] is not None and r["expires_at"] <= now,
                "last_signin_at": r["last_signin_at"], "must_change": bool(r["must_change"]),
                "locked": r["locked_until"] > now, "session_epoch": r["session_epoch"],
                "money_view": next((g["money_view"] for g in grants if g["app"] == "insights"), None) or "percent",
                "grants": grants,
            })
        return out

    def update_user(self, user_id: int, *, display_name: str | None = None, role: str | None = None,
                    expires_at: float | None | Literal["keep"] = "keep", notes: str | None = None,
                    now: float | None = None) -> None:
        now = self._now(now)
        user = self.get_user(user_id)
        if not user:
            raise ValueError("no such user")
        sets: list[str] = []
        params: list = []
        bump = False
        if display_name is not None:
            if not display_name.strip():
                raise ValueError("name is required")
            sets.append("display_name=?")
            params.append(display_name.strip())
        if role is not None:
            if role not in ROLES:
                raise ValueError("role must be admin or user")
            if role != user["role"] and user["role"] == "admin":
                self._guard_last_admin(user_id, now)
            sets.append("role=?")
            params.append(role)
        if expires_at != "keep":
            if expires_at is not None and expires_at <= now:
                self._guard_last_admin(user_id, now)
                bump = True
            sets.append("expires_at=?")
            params.append(expires_at)
        if notes is not None:
            sets.append("notes=?")
            params.append(notes[:500])
        if not sets:
            return
        sets.append("updated_at=?")
        params.append(now)
        if bump:
            sets.append("session_epoch=session_epoch+1")
        self._run(f"UPDATE users SET {', '.join(sets)} WHERE id=?", (*params, user_id))

    def set_status(self, user_id: int, status: str, now: float | None = None) -> None:
        if status not in STATUSES:
            raise ValueError("status must be active or disabled")
        now = self._now(now)
        if status == "disabled":
            self._guard_last_admin(user_id, now)
        self._run("UPDATE users SET status=?, updated_at=?, session_epoch=session_epoch+?, failed_count=0 WHERE id=?",
                  (status, now, 1 if status == "disabled" else 0, user_id))

    def delete_user(self, user_id: int, now: float | None = None) -> None:
        self._guard_last_admin(user_id, self._now(now))
        self._run("DELETE FROM app_grants WHERE user_id=?", (user_id,))
        self._run("DELETE FROM totp WHERE user_id=?", (user_id,))
        self._run("DELETE FROM users WHERE id=?", (user_id,))

    def set_password(self, user_id: int, new_password: str, must_change: bool, now: float | None = None,
                     end_sessions: bool = True) -> None:
        """Set a password and clear any lockout. Ends the person's sessions unless ``end_sessions`` is False."""
        access_core.check_password_policy(new_password)
        salt = access_core.new_salt()
        self._run(
            "UPDATE users SET pw_hash=?, pw_salt=?, scrypt_n=?, must_change=?, updated_at=?, failed_count=0, locked_until=0,"
            " session_epoch=session_epoch+? WHERE id=?",
            (access_core.hash_password(new_password, salt, self._n), salt, self._n, int(must_change), self._now(now),
             1 if end_sessions else 0, user_id),
        )

    def end_sessions(self, user_id: int) -> int:
        """Bump the epoch so every app ends this person's sessions on its next request."""
        self._run("UPDATE users SET session_epoch=session_epoch+1 WHERE id=?", (user_id,))
        return self.session_epoch(user_id) or 0

    def session_epoch(self, user_id: int) -> int | None:
        rows = self._run("SELECT session_epoch FROM users WHERE id=?", (user_id,)).fetchall()
        return int(rows[0]["session_epoch"]) if rows else None

    def touch_last_signin(self, user_id: int, now: float) -> None:
        self._run("UPDATE users SET last_signin_at=? WHERE id=?", (now, user_id))

    def check_current_password(self, user_id: int, password: str) -> bool:
        user = self.get_user(user_id)
        return bool(user) and access_core.password_matches(password, user["pw_salt"], user["scrypt_n"], user["pw_hash"])

    def can_sign_in(self, user_id: int, now: float | None = None) -> bool:
        """Active and not expired (an app grant is checked separately with ``get_grant``)."""
        now = self._now(now)
        user = self.get_user(user_id)
        return bool(user) and user["status"] == "active" and (user["expires_at"] is None or user["expires_at"] > now)

    # ---- grants ----
    def set_grant(self, user_id: int, app: str, *, money_view: str | None = None, views: list[str] | None = None,
                  granted_by: str = "", now: float | None = None, bump: bool = True) -> None:
        self._check_app(app)
        if app == "insights":
            money_view = money_view or "percent"
            self._check_money_view(money_view)
        else:
            money_view, views = None, None
        if not self.get_user(user_id):
            raise ValueError("no such user")
        existing = self.get_grant(user_id, app)
        changed = existing is not None and (existing["money_view"] != money_view or existing["views"] != views)
        self._run(
            "INSERT INTO app_grants(user_id, app, money_view, views, granted_by, granted_at) VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(user_id, app) DO UPDATE SET money_view=excluded.money_view, views=excluded.views,"
            " granted_by=excluded.granted_by, granted_at=excluded.granted_at",
            (user_id, app, money_view, None if views is None else json.dumps(list(views)), granted_by, self._now(now)),
        )
        if bump and changed:
            self.end_sessions(user_id)

    def set_money_view(self, user_id: int, money_view: str) -> None:
        self._check_money_view(money_view)
        grant = self.get_grant(user_id, "insights")
        if not grant:
            raise ValueError("this person has no Financial Insights access")
        self.set_grant(user_id, "insights", money_view=money_view, views=grant["views"],
                       granted_by=grant["granted_by"], now=grant["granted_at"])

    def revoke_grant(self, user_id: int, app: str) -> None:
        self._check_app(app)
        if self.get_grant(user_id, app) is not None:
            self._run("DELETE FROM app_grants WHERE user_id=? AND app=?", (user_id, app))
            self.end_sessions(user_id)

    @staticmethod
    def _grant_dict(r: sqlite3.Row) -> dict:
        return {"user_id": r["user_id"], "app": r["app"], "money_view": r["money_view"],
                "views": None if r["views"] is None else json.loads(r["views"]),
                "granted_by": r["granted_by"], "granted_at": r["granted_at"]}

    def get_grant(self, user_id: int, app: str) -> dict | None:
        rows = self._run("SELECT * FROM app_grants WHERE user_id=? AND app=?", (user_id, app)).fetchall()
        return self._grant_dict(rows[0]) if rows else None

    def list_grants(self, user_id: int) -> list[dict]:
        rows = self._run("SELECT * FROM app_grants WHERE user_id=? ORDER BY app", (user_id,)).fetchall()
        return [self._grant_dict(r) for r in rows]

    # ---- sign-in ----
    def verify_login(self, username: str, password: str, now: float) -> LoginResult:
        """Check username and password. A disabled or expired account is refused exactly like a wrong password."""
        username = (username or "").strip().lower()
        with self._lock:
            rows = self._run("SELECT * FROM users WHERE username=?", (username,)).fetchall()
            if not rows:
                access_core.burn_password_check(password, self._n)
                self._throttle.record(now)
                return LoginResult(False, None, False, "bad")
            row = rows[0]
            if row["status"] != "active" or (row["expires_at"] is not None and row["expires_at"] <= now):
                access_core.burn_password_check(password, self._n)
                return LoginResult(False, None, False, "bad")
            if row["locked_until"] > now:
                return LoginResult(False, row["id"], False, "locked")
            if access_core.password_matches(password, row["pw_salt"], row["scrypt_n"], row["pw_hash"]):
                self._run("UPDATE users SET failed_count=0 WHERE id=?", (row["id"],))
                return LoginResult(True, row["id"], bool(row["must_change"]), "ok")
            self._throttle.record(now)
            failed, locked_until = access_core.failure_outcome(row["failed_count"], now)
            self._run("UPDATE users SET failed_count=?, locked_until=? WHERE id=?", (failed, locked_until, row["id"]))
            return LoginResult(False, row["id"], False, "locked" if locked_until else "bad")

    def global_delay(self, now: float) -> float:
        return self._throttle.delay(now)

    def last_failure_at(self) -> float:
        return self._throttle.last_failure_at()

    # ---- activity log (never holds passwords, tokens or cookies) ----
    def log_event(self, person: str, listener: str, event: str, details: str = "", source: str = "",
                  now: float | None = None, app: str = "insights") -> None:
        self._run(
            "INSERT INTO activity(at, person, listener, event, details, source, app) VALUES (?,?,?,?,?,?,?)",
            (self._now(now), person, listener, event, details[:300], source[:100], app),
        )

    def read_events(self, person: str | None = None, since: float | None = None, until: float | None = None,
                    limit: int = 500, app: str | None = None) -> list[dict]:
        clauses: list[str] = []
        params: list = []
        for col, op, val in (("person", "=", person), ("at", ">=", since), ("at", "<=", until), ("app", "=", app)):
            if val is not None and val != "":
                clauses.append(f"{col}{op}?")
                params.append(val)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._run(f"SELECT at, person, listener, event, details, source, app FROM activity {where}"
                         " ORDER BY at DESC, id DESC LIMIT ?", (*params, int(limit))).fetchall()
        return [dict(r) for r in rows]

    # ---- admin audit (never passwords, codes, secrets, amounts or full account numbers) ----
    def log_admin(self, admin: str, action: str, target_user: str = "", details: str = "", now: float | None = None) -> None:
        self._run("INSERT INTO admin_audit(at, admin, action, target_user, details) VALUES (?,?,?,?,?)",
                  (self._now(now), admin[:100], action[:100], target_user[:100], details[:300]))

    def read_audit(self, limit: int = 500) -> list[dict]:
        rows = self._run("SELECT at, admin, action, target_user, details FROM admin_audit ORDER BY at DESC, id DESC LIMIT ?",
                         (int(limit),)).fetchall()
        return [dict(r) for r in rows]

    # ---- migration from the Financial Insights access.db ----
    def migrate_access_db(self, access_path: Path) -> dict:
        """Copy users, hashes and activity from ``access.db`` once, then rename it to ``access.db.migrated``.

        Does nothing unless the file exists and this store has no users yet. Hashes and salts are copied
        unchanged, so nobody resets a password. The old ``money_view`` becomes the ``insights`` grant.
        The old file is renamed, never deleted.
        """
        access_path = Path(access_path)
        result: dict = {"migrated": False, "users": 0, "events": 0, "renamed_to": None}
        if not access_path.exists():
            return result
        with self._lock:
            if self._run("SELECT COUNT(*) AS n FROM users").fetchall()[0]["n"]:
                return result
            src = sqlite3.connect(access_path)
            src.row_factory = sqlite3.Row
            try:
                cols = {r["name"] for r in src.execute("PRAGMA table_info(users)")}
                users = [dict(r) for r in src.execute("SELECT * FROM users")] if cols else []
                has_activity = bool(src.execute("SELECT 1 FROM sqlite_master WHERE name='activity'").fetchall())
                events = [dict(r) for r in src.execute("SELECT * FROM activity ORDER BY id")] if has_activity else []
            finally:
                src.close()
            conn = self._conn()
            try:
                with conn:
                    for u in users:
                        conn.execute(
                            "INSERT INTO users(id, display_name, username, pw_hash, pw_salt, scrypt_n, must_change, created_at,"
                            " updated_at, failed_count, locked_until, last_signin_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            (u["id"], u["display_name"], u["username"], u["pw_hash"], u["pw_salt"], u["scrypt_n"],
                             u["must_change"], u["created_at"], u["updated_at"], u["failed_count"], u["locked_until"],
                             u["last_signin_at"]))
                        mv = u["money_view"] if "money_view" in cols and u["money_view"] in MONEY_VIEWS else "percent"
                        conn.execute("INSERT INTO app_grants(user_id, app, money_view, views, granted_by, granted_at)"
                                     " VALUES (?, 'insights', ?, NULL, 'migration', ?)", (u["id"], mv, u["created_at"]))
                    for e in events:
                        conn.execute("INSERT INTO activity(at, person, listener, event, details, source, app)"
                                     " VALUES (?,?,?,?,?,?,'insights')",
                                     (e["at"], e["person"], e["listener"], e["event"], e["details"], e["source"]))
            finally:
                conn.close()
            target = access_path.with_name(access_path.name + ".migrated")
            n = 1
            while target.exists():
                n += 1
                target = access_path.with_name(f"{access_path.name}.migrated.{n}")
            access_path.rename(target)
            result.update(migrated=True, users=len(users), events=len(events), renamed_to=str(target))
        return result


def open_identity_store(path: Path | None = None, *, legacy_access_path: Path | None = None,
                        scrypt_n: int = 2**15) -> IdentityStore:
    """Open (creating if needed) the identity store, migrating a legacy ``access.db`` on first start."""
    store = IdentityStore(path or default_db_path(), scrypt_n=scrypt_n)
    if legacy_access_path is not None:
        store.migrate_access_db(legacy_access_path)
    return store


class _Result:
    def __init__(self, rows: list, lastrowid: int | None, rowcount: int = -1) -> None:
        self._rows = rows
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    def fetchall(self) -> list:
        return self._rows
