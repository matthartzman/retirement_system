"""RefData skeleton over the read-only, shipped ``reference.db`` (WP2.3).

Layout (schema v1): ``ref_meta(key, value)`` holds ``schema``, ``data_version`` and
``content_hash``; every other table is a data table. The content hash is SHA-256 over
all data tables (sorted by table name; rows in primary-key/rowid order; compact JSON
per row), computed from the database content itself so no file is read directly.
``open`` verifies it. Getters return plain Python structures (list of dicts).
Later WPs add typed getters per slice; ``build`` exists for the release tool and tests.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import db
from .errors import NotFoundError, StoreError, ValidationError

REF_SCHEMA_VERSION = 1
REF_APPLICATION_ID = 0x52504644  # "RPFD"
_META = "ref_meta"
_IDENT = __import__("re").compile(r"[A-Za-z_][A-Za-z0-9_]*")
_MIGRATIONS = (
    f"PRAGMA application_id={REF_APPLICATION_ID}; "
    f"CREATE TABLE {_META} (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;",
)


class RefDataError(StoreError):
    """reference.db is missing, malformed or fails its content hash."""


def _data_tables(con: sqlite3.Connection) -> list[str]:
    return [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != ? ORDER BY name",
        (_META,),
    )]


def compute_content_hash(con: sqlite3.Connection) -> str:
    h = hashlib.sha256()
    for t in _data_tables(con):
        cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
        h.update(json.dumps([t, cols], separators=(",", ":")).encode())
        for row in con.execute(f'SELECT * FROM "{t}" ORDER BY rowid'):
            h.update(b"\n" + json.dumps(list(row), separators=(",", ":"), default=str).encode())
    return h.hexdigest()


class RefData:
    """Read-only access to reference.db."""

    def __init__(self, con: sqlite3.Connection, path: str) -> None:
        self._con: sqlite3.Connection | None = con
        self.path = path
        self._meta = {r[0]: r[1] for r in con.execute(f"SELECT key, value FROM {_META}")}

    @classmethod
    def open(cls, path: str | Path, *, verify: bool = True) -> "RefData":
        try:
            con = db.connect(path, readonly=True)
        except StoreError as exc:
            raise RefDataError(f"reference data not available: {exc}") from exc
        try:
            if con.execute("PRAGMA application_id").fetchone()[0] != REF_APPLICATION_ID:
                raise RefDataError(f"{path} is not a reference database")
            if db.get_version(con) != REF_SCHEMA_VERSION:
                raise RefDataError(f"reference schema v{db.get_version(con)} unsupported (need v{REF_SCHEMA_VERSION})")
            ref = cls(con, str(path))
            if verify and ref.content_hash != compute_content_hash(con):
                raise RefDataError("reference data content hash mismatch (corrupt or modified)")
            return ref
        except sqlite3.Error as exc:
            con.close()
            raise RefDataError(f"reference data unreadable: {exc}") from exc
        except RefDataError:
            con.close()
            raise

    # ---------------------------------------------------------------- metadata
    @property
    def data_version(self) -> str:
        return self._meta.get("data_version", "")

    @property
    def content_hash(self) -> str:
        return self._meta.get("content_hash", "")

    def meta(self) -> dict[str, str]:
        return dict(self._meta)

    # ----------------------------------------------------------------- getters
    def tables(self) -> list[str]:
        return _data_tables(self._c())

    def table(self, name: str) -> list[dict[str, Any]]:
        """All rows of a data table as plain dicts, in stored order."""
        if name not in self.tables():
            raise NotFoundError(f"reference table {name!r} not found")
        return [dict(r) for r in self._c().execute(f'SELECT * FROM "{name}" ORDER BY rowid')]

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None

    def __enter__(self) -> "RefData":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _c(self) -> sqlite3.Connection:
        if self._con is None:
            raise StoreError("reference data is closed")
        return self._con


def build(path: str | Path, tables: Mapping[str, tuple[Sequence[str], Iterable[Sequence[Any]]]],
          *, data_version: str) -> str:
    """Write a deterministic reference.db; return its content hash (release tool / tests)."""
    p = Path(path)
    if p.exists():
        raise ValidationError(f"refusing to overwrite {p}")
    con = db.connect(p)
    try:
        db.migrate(con, _MIGRATIONS)
        with db.transaction(con):
            for name in sorted(tables):
                cols, rows = tables[name]
                if not _IDENT.fullmatch(name) or name == _META or not all(_IDENT.fullmatch(c) for c in cols):
                    raise ValidationError(f"invalid reference table/column name in {name!r}")
                con.execute(f'CREATE TABLE "{name}" ({", ".join(chr(34) + c + chr(34) for c in cols)})')
                con.executemany(
                    f'INSERT INTO "{name}" VALUES ({", ".join("?" * len(cols))})',
                    [tuple(r) for r in rows],
                )
            digest = compute_content_hash(con)
            con.executemany(f"INSERT INTO {_META} VALUES (?, ?)", [
                ("schema", str(REF_SCHEMA_VERSION)), ("data_version", data_version), ("content_hash", digest)])
        con.execute("PRAGMA journal_mode=DELETE")
    finally:
        con.close()
    return digest
