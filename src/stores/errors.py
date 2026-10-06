"""Store-layer error model (WP2.2).

Every error a store raises is a ``StoreError``. Callers catch the narrowest
class they can act on:

- ``NotFoundError``      a row / revision / plan / file that was asked for does not exist
                         (also a ``LookupError``).
- ``ValidationError``    the caller passed a bad argument (unknown field, wrong type,
                         empty key, bad kind ...); nothing was written (also a ``ValueError``).
- ``IntegrityError``     a database constraint rejected the write (duplicate id or path,
                         foreign key, CHECK) or stored data failed a consistency check.
                         Subclass of ``ValidationError``: from the caller's side it is
                         still "this write is not acceptable".
- ``SchemaVersionError`` the database is newer than the code, needs an upgrade it
                         cannot get (read-only open), or a migration failed.

Any other ``sqlite3.Error`` surfaces as a plain ``StoreError`` with the original
exception chained.
"""
from __future__ import annotations


class StoreError(Exception):
    """Base class for all store-layer errors."""


class NotFoundError(StoreError, LookupError):
    """The requested record or database does not exist."""


class ValidationError(StoreError, ValueError):
    """An argument was rejected before touching the database."""


class IntegrityError(ValidationError):
    """A database constraint or stored-data consistency check failed."""


class SchemaVersionError(StoreError):
    """Database is newer than this code understands, or a migration failed."""


__all__ = ["IntegrityError", "NotFoundError", "SchemaVersionError", "StoreError", "ValidationError"]
