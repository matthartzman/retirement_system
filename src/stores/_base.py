"""Shared open / close / transaction / error-mapping machinery for the writable stores."""
from __future__ import annotations

import datetime as _dt
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Sequence, TypeVar

from . import db
from .errors import IntegrityError, NotFoundError, SchemaVersionError, StoreError

Clock = Callable[[], str]
S = TypeVar("S", bound="_SqliteStore")


def utc_now() -> str:
    """Default clock: UTC ISO-8601 with microseconds (sortable text)."""
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="microseconds")


@contextmanager
def map_sqlite_errors() -> Iterator[None]:
    """Translate ``sqlite3`` exceptions into the store error model."""
    try:
        yield
    except sqlite3.IntegrityError as exc:
        raise IntegrityError(str(exc)) from exc
    except sqlite3.Error as exc:
        raise StoreError(f"{type(exc).__name__}: {exc}") from exc


class _SqliteStore:
    """One connection to one store database.

    Subclasses set ``KIND`` (for messages), ``APPLICATION_ID`` (stamped into the
    file header by migration v1 so a plan.db cannot be opened as an app.db) and
    ``MIGRATIONS`` (forward-only scripts; ``len(MIGRATIONS)`` is the schema version).

    Every public write runs inside ``self._write()``: a transaction of its own
    when called bare, or a savepoint inside an enclosing ``transaction()`` block,
    so each call is atomic either way.
    """

    KIND: str = "store"
    APPLICATION_ID: int = 0
    MIGRATIONS: Sequence[str] = ()

    def __init__(self, con: sqlite3.Connection, *, path: str, readonly: bool, clock: Clock | None) -> None:
        self._con_: sqlite3.Connection | None = con
        self.path = path
        self.readonly = readonly
        self._clock = clock or utc_now

    # ----------------------------------------------------------------- lifecycle
    @classmethod
    def open(
        cls: type[S],
        path: str | Path = db.MEMORY,
        *,
        create: bool = True,
        readonly: bool = False,
        clock: Clock | None = None,
    ) -> S:
        """Open (and, if allowed, create and migrate) a store database.

        - ``create=False``: the file must already exist and be initialised
          (``NotFoundError`` otherwise). ``":memory:"`` always needs ``create=True``.
        - ``readonly=True``: no migration is attempted; the file must already be at
          the current schema version (``SchemaVersionError`` otherwise).
        - A file that is some other SQLite database (tables but no version, or a
          different application id) is refused with ``StoreError``.
        - A database newer than this code raises ``SchemaVersionError``.
        """
        target = str(path)
        is_memory = target == db.MEMORY
        if readonly and is_memory:
            raise StoreError("a read-only store needs a file path")
        if not create and is_memory:
            raise NotFoundError("an in-memory store can only be opened with create=True")
        if not is_memory and (readonly or not create) and not Path(target).is_file():
            raise NotFoundError(f"{cls.KIND} database not found: {target}")
        with map_sqlite_errors():
            con = db.connect(target, readonly=readonly)
        try:
            with map_sqlite_errors():
                cls._check_and_migrate(con, target, create=create and not readonly, readonly=readonly)
        except BaseException:
            con.close()
            raise
        return cls(con, path=target, readonly=readonly, clock=clock)

    @classmethod
    def _check_and_migrate(cls, con: sqlite3.Connection, target: str, *, create: bool, readonly: bool) -> None:
        version = db.get_version(con)
        app_id = int(con.execute("PRAGMA application_id").fetchone()[0])
        current = len(cls.MIGRATIONS)
        if version == 0:
            if con.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]:
                raise StoreError(f"{target} is not a valid {cls.KIND}.db (unversioned tables present)")
            if not create:
                raise NotFoundError(f"{target} is not an initialised {cls.KIND}.db")
        elif app_id != cls.APPLICATION_ID:
            raise StoreError(f"{target} is not a valid {cls.KIND}.db (application_id {app_id:#x})")
        if version > current:
            raise SchemaVersionError(f"{cls.KIND} schema v{version} is newer than supported v{current}")
        if readonly:
            if version < current:
                raise SchemaVersionError(
                    f"{cls.KIND} schema v{version} needs an upgrade to v{current}; open it writable first"
                )
            return
        db.migrate(con, cls.MIGRATIONS)

    def close(self) -> None:
        """Close the connection (idempotent). Rolls back an unfinished transaction."""
        con, self._con_ = self._con_, None
        if con is not None:
            if con.in_transaction:
                con.execute("ROLLBACK")
            con.close()

    @property
    def closed(self) -> bool:
        return self._con_ is None

    def __enter__(self: S) -> S:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def schema_version(self) -> int:
        return db.get_version(self._con)

    # -------------------------------------------------------------- transactions
    @property
    def _con(self) -> sqlite3.Connection:
        if self._con_ is None:
            raise StoreError(f"{self.KIND} store is closed")
        return self._con_

    @contextmanager
    def transaction(self: S) -> Iterator[S]:
        """Group several writes into one atomic unit (nested blocks become savepoints).

        Commits on normal exit, rolls back on any exception. Yields the store.
        """
        self._require_writable()
        with map_sqlite_errors(), db.transaction(self._con):
            yield self

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        self._require_writable()
        with map_sqlite_errors(), db.transaction(self._con) as con:
            yield con

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        with map_sqlite_errors():
            yield self._con

    def _require_writable(self) -> None:
        if self.readonly:
            raise StoreError(f"{self.KIND} store was opened read-only")
        self._con  # raises if closed
