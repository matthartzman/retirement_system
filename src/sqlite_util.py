"""Small SQLite helper: a connection that commits on success and is *closed* on exit.

``with sqlite3.connect(p) as con`` only commits or rolls back; the connection stays open
until garbage collection. On Windows an open handle makes replacing or deleting the
database file fail with ``WinError 5``, which Load Saved Plan and snapshot restore do.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def connect(path: str | Path) -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(path)
    try:
        with con:
            yield con
    finally:
        con.close()


def harden(con: sqlite3.Connection) -> None:
    """Connection settings for files that may be hostile (S-03): schema objects may not call unsafe SQL functions
    (``trusted_schema=OFF``), corrupt cell sizes are detected (``cell_size_check=ON``) and, where the Python and SQLite
    build supports it, defensive mode blocks writes to shadow tables and ``writable_schema``."""
    con.execute("PRAGMA trusted_schema=OFF")
    con.execute("PRAGMA cell_size_check=ON")
    setconfig = getattr(con, "setconfig", None)  # Python 3.12+
    flag = getattr(sqlite3, "SQLITE_DBCONFIG_DEFENSIVE", None)
    if setconfig is not None and flag is not None:
        try:
            setconfig(flag, True)
        except sqlite3.Error:  # an SQLite build without the option: the pragmas above still apply
            pass


def foreign_objects(con: sqlite3.Connection, allowed: frozenset[str] = frozenset()) -> list[tuple[str, str]]:
    """``(type, name)`` of every trigger or view in the file that the application schema does not own.

    The application's own schemas define no triggers or views, so ``allowed`` is empty today. A trigger fires on the
    application's own writes and during in-place upgrades, so a file with one is refused before anything runs."""
    rows = con.execute("SELECT type, name FROM sqlite_master WHERE type IN ('trigger', 'view') ORDER BY type, name").fetchall()
    return [(str(r[0]), str(r[1])) for r in rows if str(r[1]) not in allowed]
