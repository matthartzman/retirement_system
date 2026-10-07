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
