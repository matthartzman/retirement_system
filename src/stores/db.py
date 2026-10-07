"""SQLite connection helpers and forward-only schema versioning (WP2.1).

Schemas are Python strings; the version lives in ``PRAGMA user_version``.
A *migration list* is an ordered sequence of SQL scripts: script ``i`` takes the
database from version ``i`` to ``i + 1``. ``migrate`` applies only the missing
tail, each script in its own transaction together with its version bump, so a
failed step leaves the database at the last good version. There is no downgrade.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence

from .errors import SchemaVersionError, StoreError  # re-exported: ``from .db import StoreError`` keeps working

MEMORY = ":memory:"


def connect(path: str | Path = MEMORY, *, readonly: bool = False,
            check_same_thread: bool = True) -> sqlite3.Connection:
    """Open a connection with the project pragmas (WAL, foreign keys, row factory).

    Autocommit mode (``isolation_level=None``): transactions are explicit via
    ``transaction()``. ``readonly`` opens a URI ``mode=ro`` connection and
    raises ``StoreError`` if the file does not exist. ``check_same_thread=False``
    is for a connection shared across threads behind the caller's own lock
    (``RefData`` does this for the process-wide reference handle).
    """
    target = str(path)
    if readonly:
        if target == MEMORY:
            raise StoreError("read-only connection needs a file path")
        p = Path(target)
        if not p.is_file():
            raise StoreError(f"database file not found: {target}")
        con = sqlite3.connect(f"{p.resolve().as_uri()}?mode=ro", uri=True, isolation_level=None,
                              check_same_thread=check_same_thread)
    else:
        con = sqlite3.connect(target, isolation_level=None, check_same_thread=check_same_thread)
    try:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        if not readonly and target != MEMORY:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=NORMAL")
    except BaseException:
        con.close()  # never leave a handle on the file behind a failed open
        raise
    return con


def _end(con: sqlite3.Connection, sql: str) -> None:
    """ROLLBACK that tolerates SQLite having already ended the transaction."""
    try:
        con.execute(sql)
    except sqlite3.Error:
        pass


@contextmanager
def transaction(con: sqlite3.Connection, *, immediate: bool = True) -> Iterator[sqlite3.Connection]:
    """Explicit transaction; commit on success, rollback on any exception.

    Nested use joins the outer transaction via a savepoint. A failed COMMIT
    rolls back before the error propagates, so the connection is never left open.
    """
    if con.in_transaction:
        name = f"sp_{id(object())}"
        con.execute(f"SAVEPOINT {name}")
        try:
            yield con
        except BaseException:
            _end(con, f"ROLLBACK TO {name}")
            _end(con, f"RELEASE {name}")
            raise
        con.execute(f"RELEASE {name}")
        return
    con.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield con
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            _end(con, "ROLLBACK")
        raise


def get_version(con: sqlite3.Connection) -> int:
    return int(con.execute("PRAGMA user_version").fetchone()[0])


def migrate(con: sqlite3.Connection, migrations: Sequence[str]) -> int:
    """Bring ``con`` to ``len(migrations)``; return the resulting version.

    Raises ``SchemaVersionError`` if the database is newer than the code, or if
    a script fails (the failing step is rolled back).
    """
    current = get_version(con)
    target = len(migrations)
    if current > target:
        raise SchemaVersionError(f"database schema v{current} is newer than supported v{target}")
    for ver in range(current, target):
        try:
            con.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise StoreError(f"cannot lock database for migration: {exc}") from exc
        try:
            if get_version(con) > ver:  # another process migrated while we waited for the lock
                _end(con, "ROLLBACK")
                continue
            for stmt in _split(migrations[ver]):
                con.execute(stmt)
            con.execute(f"PRAGMA user_version={ver + 1}")
            con.execute("COMMIT")
        except BaseException as exc:
            if con.in_transaction:
                _end(con, "ROLLBACK")
            if isinstance(exc, sqlite3.Error):
                raise SchemaVersionError(f"migration to v{ver + 1} failed: {exc}") from exc
            raise
    return target


def _split(script: str) -> list[str]:
    """Split a script into statements (no executescript: it would auto-commit)."""
    out, buf = [], ""
    for ch in script:
        buf += ch
        if ch == ";" and sqlite3.complete_statement(buf):
            out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out
