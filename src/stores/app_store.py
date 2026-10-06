"""AppStore: the access layer over ``app.db`` (per-install state that survives plan swaps).

WP2.2 / P1.2. Nothing in the product imports this yet (P6 moves app state onto it).

Schema v1 (``PRAGMA user_version = 1``, ``PRAGMA application_id = APP_APPLICATION_ID``)
-------------------------------------------------------------------------------------
``plan_registry``  ``plan_id`` (PK, also the per-plan folder name, see ``plan_paths``),
                   ``path`` (absolute, UNIQUE), ``name``, ``kind`` in ``PLAN_KINDS``,
                   ``last_opened`` (UTC ISO text, NULL until first activated).
``active_plan``    at most one row (``id = 1``): ``plan_id`` (FK to the registry),
                   ``switched_at``. A registered plan cannot be removed while active.
``settings``       ``key -> value``; the value is JSON text (``json.dumps``, sorted keys,
                   no NaN/Infinity), returned decoded.

Secrets never go here (design decision 5: OS credential store).
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from ._base import _SqliteStore
from .errors import NotFoundError, StoreError, ValidationError
from .plan_store import validate_plan_id

APP_APPLICATION_ID = 0x52504150  # "RPAP"
PLAN_KINDS = ("user", "demo", "case")

_SCHEMA_V1 = f"""
PRAGMA application_id = {APP_APPLICATION_ID};
CREATE TABLE plan_registry (
    plan_id     TEXT PRIMARY KEY CHECK (plan_id <> ''),
    path        TEXT NOT NULL UNIQUE CHECK (path <> ''),
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('user', 'demo', 'case')),
    last_opened TEXT
) WITHOUT ROWID;
CREATE TABLE active_plan (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    plan_id     TEXT NOT NULL REFERENCES plan_registry (plan_id),
    switched_at TEXT NOT NULL
);
CREATE TABLE settings (
    key   TEXT PRIMARY KEY CHECK (key <> ''),
    value TEXT NOT NULL
) WITHOUT ROWID;
"""

APP_MIGRATIONS: tuple[str, ...] = (_SCHEMA_V1,)
APP_SCHEMA_VERSION = len(APP_MIGRATIONS)

_PLAN_COLUMNS = "plan_id, path, name, kind, last_opened"
_PLAN_ORDER = "ORDER BY last_opened IS NULL, last_opened DESC, name, plan_id"


def _check_str(name: str, value: Any, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{name} must be str, got {type(value).__name__}")
    if not allow_empty and not value.strip():
        raise ValidationError(f"{name} must not be empty")
    return value


def _check_path(path: Any) -> str:
    if not isinstance(path, (str, Path)) or not str(path).strip():
        raise ValidationError(f"plan path must be a non-empty str or Path, got {path!r}")
    p = Path(path)
    if not p.is_absolute():
        raise ValidationError(f"plan path must be absolute: {path!s}")
    return os.path.normpath(str(p))


def _check_kind(kind: Any) -> str:
    if kind not in PLAN_KINDS:
        raise ValidationError(f"plan kind must be one of {PLAN_KINDS}, got {kind!r}")
    return kind


class AppStore(_SqliteStore):
    """Plan registry, active plan and settings of one install. Open with ``AppStore.open(path)``."""

    KIND = "app"
    APPLICATION_ID = APP_APPLICATION_ID
    MIGRATIONS = APP_MIGRATIONS

    # -------------------------------------------------------------- plan registry
    def register_plan(
        self, path: str | Path, name: str, kind: str = "user", *, plan_id: str | None = None
    ) -> dict[str, Any]:
        """Add a plan file to the registry and return its record.

        ``plan_id`` defaults to a fresh UUID4 hex. A duplicate id or path raises
        ``IntegrityError``. Registering does not activate the plan.
        """
        stored_path = _check_path(path)
        _check_str("name", name)
        _check_kind(kind)
        plan_id = uuid.uuid4().hex if plan_id is None else validate_plan_id(plan_id)
        with self._write() as con:
            con.execute(
                "INSERT INTO plan_registry (plan_id, path, name, kind, last_opened) VALUES (?, ?, ?, ?, NULL)",
                (plan_id, stored_path, name, kind),
            )
            return self._plan(con, plan_id)

    def update_plan(self, plan_id: str, *, name: str | None = None, path: str | Path | None = None) -> dict[str, Any]:
        """Rename a plan and/or point it at a new file (Save As); return the record."""
        validate_plan_id(plan_id)
        changes: dict[str, str] = {}
        if name is not None:
            changes["name"] = _check_str("name", name)
        if path is not None:
            changes["path"] = _check_path(path)
        if not changes:
            raise ValidationError("update_plan needs name and/or path")
        with self._write() as con:
            cur = con.execute(
                f"UPDATE plan_registry SET {', '.join(f'{k} = ?' for k in changes)} WHERE plan_id = ?",
                (*changes.values(), plan_id),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"plan {plan_id!r} is not registered")
            return self._plan(con, plan_id)

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        validate_plan_id(plan_id)
        with self._read() as con:
            return self._plan(con, plan_id)

    def list_plans(self, kind: str | None = None) -> list[dict[str, Any]]:
        """Registered plans, most recently opened first (never-opened last, then by name)."""
        with self._read() as con:
            if kind is None:
                cur = con.execute(f"SELECT {_PLAN_COLUMNS} FROM plan_registry {_PLAN_ORDER}")
            else:
                cur = con.execute(
                    f"SELECT {_PLAN_COLUMNS} FROM plan_registry WHERE kind = ? {_PLAN_ORDER}", (_check_kind(kind),)
                )
            return [dict(r) for r in cur]

    def remove_plan(self, plan_id: str) -> None:
        """Forget a plan (the file itself is untouched). The active plan cannot be removed."""
        validate_plan_id(plan_id)
        with self._write() as con:
            active = con.execute("SELECT plan_id FROM active_plan WHERE id = 1").fetchone()
            if active is not None and active[0] == plan_id:
                raise ValidationError(f"plan {plan_id!r} is active; switch plans before removing it")
            if con.execute("DELETE FROM plan_registry WHERE plan_id = ?", (plan_id,)).rowcount == 0:
                raise NotFoundError(f"plan {plan_id!r} is not registered")

    # ----------------------------------------------------------------- active plan
    def set_active_plan(self, plan_id: str) -> dict[str, Any]:
        """Make a registered plan the active one, stamp ``last_opened``; return its record."""
        validate_plan_id(plan_id)
        now = self._clock()
        with self._write() as con:
            if con.execute("UPDATE plan_registry SET last_opened = ? WHERE plan_id = ?", (now, plan_id)).rowcount == 0:
                raise NotFoundError(f"plan {plan_id!r} is not registered")
            con.execute(
                "INSERT INTO active_plan (id, plan_id, switched_at) VALUES (1, ?, ?) "
                "ON CONFLICT (id) DO UPDATE SET plan_id = excluded.plan_id, switched_at = excluded.switched_at",
                (plan_id, now),
            )
            return self._plan(con, plan_id)

    def active_plan(self) -> dict[str, Any] | None:
        """The active plan's registry record, or ``None`` when no plan is active."""
        with self._read() as con:
            r = con.execute(
                f"SELECT {', '.join('r.' + c.strip() for c in _PLAN_COLUMNS.split(','))} "
                "FROM active_plan a JOIN plan_registry r ON r.plan_id = a.plan_id WHERE a.id = 1"
            ).fetchone()
            return None if r is None else dict(r)

    def clear_active_plan(self) -> None:
        with self._write() as con:
            con.execute("DELETE FROM active_plan")

    # -------------------------------------------------------------------- settings
    def get_setting(self, key: str, default: Any = None) -> Any:
        _check_str("key", key)
        with self._read() as con:
            r = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return default if r is None else _loads(key, r[0])

    def set_setting(self, key: str, value: Any) -> None:
        """Store any JSON-serialisable value (``ValidationError`` otherwise, including NaN)."""
        _check_str("key", key)
        try:
            text = json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"setting {key!r} is not JSON-serialisable: {exc}") from exc
        with self._write() as con:
            con.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (key, text),
            )

    def delete_setting(self, key: str) -> bool:
        """Remove a setting; return whether it existed."""
        _check_str("key", key)
        with self._write() as con:
            return con.execute("DELETE FROM settings WHERE key = ?", (key,)).rowcount > 0

    def settings(self) -> dict[str, Any]:
        """All settings, decoded, keyed in sorted order."""
        with self._read() as con:
            return {k: _loads(k, v) for k, v in con.execute("SELECT key, value FROM settings ORDER BY key")}

    # ------------------------------------------------------------------- internals
    @staticmethod
    def _plan(con: Any, plan_id: str) -> dict[str, Any]:
        r = con.execute(f"SELECT {_PLAN_COLUMNS} FROM plan_registry WHERE plan_id = ?", (plan_id,)).fetchone()
        if r is None:
            raise NotFoundError(f"plan {plan_id!r} is not registered")
        return dict(r)


__all__ = ["APP_APPLICATION_ID", "APP_MIGRATIONS", "APP_SCHEMA_VERSION", "AppStore", "PLAN_KINDS"]


def _loads(key: str, text: str):
    try:
        return json.loads(text)
    except ValueError as exc:
        raise StoreError(f"setting {key!r} holds invalid JSON") from exc
