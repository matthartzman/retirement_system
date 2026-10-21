"""AppStore: the access layer over ``app.db`` (per-install state that survives plan swaps).

WP2.2 / P1.2. The product reaches it through ``src/app_state.open_app_store`` (WP8).

Schema v1 (``PRAGMA user_version = 1``, ``PRAGMA application_id = APP_APPLICATION_ID``)
-------------------------------------------------------------------------------------
``plan_registry``  ``plan_id`` (PK, also the per-plan folder name, see ``plan_paths``),
                   ``path`` (absolute, UNIQUE), ``name``, ``kind`` in ``PLAN_KINDS``,
                   ``last_opened`` (UTC ISO text, NULL until first activated).
``active_plan``    at most one row (``id = 1``): ``plan_id`` (FK to the registry),
                   ``switched_at``. A registered plan cannot be removed while active.
``settings``       ``key -> value``; the value is JSON text (``json.dumps``, sorted keys,
                   no NaN/Infinity), returned decoded.

Schema v2 (WP8.3: small per-install logs and caches, all keyed by a ``scope`` text where one
install can hold several: a workspace id, an output folder, a backup folder, a price-cache id)
-------------------------------------------------------------------------------------------
``audit_events``     ``id``, ``ts`` (epoch seconds), ``event``, ``workspace_id``, ``user_id``,
                     ``payload`` (the redacted JSON line the old ``audit_log.jsonl`` held).
``admin_change_log`` ``id``, ``scope``, ``ts``, ``event`` (JSON); newest ``ADMIN_CHANGE_KEEP`` per scope.
``run_history``      ``id``, ``scope``, ``entry`` (JSON); newest ``limit`` per scope.
``last_build``       ``scope`` (PK), ``data`` (JSON): the last build's timing / QC record.
``backup_manifest``  ``scope``, ``filename`` (PK together), ``created_at``, ``manifest`` (JSON).
``price_cache``      ``scope``, ``symbol`` (PK together), ``record`` (JSON quote record).

Schema v3 (WI-038: the snapshot and build-history tables that lived in the legacy
``retirement_system_v10.db``; the legacy database is no longer written)
-------------------------------------------------------------------------------------------
``local_settings``   ``key`` (PK), ``value_json``, ``updated_at``.
``result_snapshots`` ``result_id`` (PK), ``created_at``, ``plan_snapshot_id``, ``result_json``,
                     ``event_log_json``, ``result_sha256``; newest ``DEFAULT_RESULT_SNAPSHOT_RETENTION`` kept.
``kpi_snapshots``    ``snapshot_id`` (PK), ``created_at``, ``build_id``, the headline KPI columns, ``kpi_json``.
``build_events``     ``event_id``, ``created_at``, ``build_id``, ``stage``, ``event_type``, ``detail_json``.
``price_snapshots``  ``snapshot_id``, ``workspace_id``, ``symbol``, ``price``, ``source``, ``status``, ``as_of``.
``pricing_snapshot_freezes``  ``workspace_id`` (PK), ``active``, ``frozen_at``, ``source``, ``snapshot_json``.

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

_SCHEMA_V2 = """
CREATE TABLE audit_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           REAL NOT NULL,
    event        TEXT NOT NULL,
    workspace_id TEXT NOT NULL DEFAULT '',
    user_id      TEXT NOT NULL DEFAULT '',
    payload      TEXT NOT NULL
);
CREATE TABLE admin_change_log (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    ts    REAL NOT NULL,
    event TEXT NOT NULL
);
CREATE INDEX admin_change_log_scope ON admin_change_log (scope, ts);
CREATE TABLE run_history (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    entry TEXT NOT NULL
);
CREATE INDEX run_history_scope ON run_history (scope, id);
CREATE TABLE last_build (
    scope TEXT PRIMARY KEY,
    data  TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE backup_manifest (
    scope      TEXT NOT NULL,
    filename   TEXT NOT NULL,
    created_at TEXT NOT NULL,
    manifest   TEXT NOT NULL,
    PRIMARY KEY (scope, filename)
) WITHOUT ROWID;
CREATE TABLE price_cache (
    scope  TEXT NOT NULL,
    symbol TEXT NOT NULL,
    record TEXT NOT NULL,
    PRIMARY KEY (scope, symbol)
) WITHOUT ROWID;
"""

_SCHEMA_V3 = """
CREATE TABLE local_settings (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE result_snapshots (
    result_id        TEXT PRIMARY KEY,
    created_at       TEXT NOT NULL,
    plan_snapshot_id TEXT,
    result_json      TEXT NOT NULL,
    event_log_json   TEXT NOT NULL,
    result_sha256    TEXT NOT NULL
);
CREATE TABLE build_events (
    event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    build_id    TEXT,
    stage       TEXT,
    event_type  TEXT,
    detail_json TEXT NOT NULL
);
CREATE TABLE kpi_snapshots (
    snapshot_id               TEXT PRIMARY KEY,
    created_at                TEXT NOT NULL,
    build_id                  TEXT,
    probability_of_success    REAL,
    terminal_nw_deterministic REAL,
    terminal_nw_mc_median     REAL,
    terminal_nw_mc_p10        REAL,
    terminal_nw_mc_p90        REAL,
    lifetime_tax              REAL,
    lcv                       REAL,
    eltr                      REAL,
    fcv                       REAL,
    eftr                      REAL,
    total_roth_conversions    REAL,
    after_tax_terminal_nw     REAL,
    npv_future_taxes          REAL,
    terminal_nw_mc_p5         REAL,
    kpi_json                  TEXT NOT NULL
);
CREATE TABLE price_snapshots (
    snapshot_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT DEFAULT 'local',
    symbol       TEXT,
    price        REAL,
    source       TEXT,
    status       TEXT DEFAULT 'OK',
    as_of        TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE pricing_snapshot_freezes (
    workspace_id  TEXT PRIMARY KEY,
    active        INTEGER NOT NULL DEFAULT 1,
    frozen_at     TEXT NOT NULL,
    source        TEXT,
    snapshot_json TEXT NOT NULL
);
"""

APP_MIGRATIONS: tuple[str, ...] = (_SCHEMA_V1, _SCHEMA_V2, _SCHEMA_V3)
APP_SCHEMA_VERSION = len(APP_MIGRATIONS)

ADMIN_CHANGE_KEEP = 250

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

    # ------------------------------------------------------- audit / change log / history
    def append_audit_event(
        self, event: str, payload: str, *, ts: float, workspace_id: str = "", user_id: str = ""
    ) -> None:
        """Record one audit event; ``payload`` is the (already redacted) JSON text."""
        with self._write() as con:
            con.execute(
                "INSERT INTO audit_events (ts, event, workspace_id, user_id, payload) VALUES (?, ?, ?, ?, ?)",
                (float(ts), str(event), str(workspace_id), str(user_id), str(payload)),
            )

    def audit_events(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Audit events, oldest first (the newest ``limit`` when given); ``payload`` stays JSON text."""
        sql = "SELECT id, ts, event, workspace_id, user_id, payload FROM audit_events ORDER BY id"
        with self._read() as con:
            rows = [dict(r) for r in con.execute(sql)]
        return rows if limit is None else rows[-max(0, int(limit)):]

    def append_admin_change(self, scope: str, event: dict[str, Any], *, ts: float, keep: int = ADMIN_CHANGE_KEEP) -> None:
        with self._write() as con:
            con.execute("INSERT INTO admin_change_log (scope, ts, event) VALUES (?, ?, ?)", (scope, float(ts), _dumps(event)))
            con.execute(
                "DELETE FROM admin_change_log WHERE scope = ? AND id NOT IN "
                "(SELECT id FROM admin_change_log WHERE scope = ? ORDER BY id DESC LIMIT ?)",
                (scope, scope, max(1, int(keep))),
            )

    def admin_changes(self, scope: str) -> list[dict[str, Any]]:
        """The scope's change events, oldest first."""
        with self._read() as con:
            return [json.loads(r[0]) for r in con.execute("SELECT event FROM admin_change_log WHERE scope = ? ORDER BY id", (scope,))]

    def append_run_history(self, scope: str, entry: Any, *, limit: int = 50) -> int:
        """Append an entry, keep the newest ``limit``; return how many remain."""
        limit = max(1, int(limit))
        with self._write() as con:
            con.execute("INSERT INTO run_history (scope, entry) VALUES (?, ?)", (scope, _dumps(entry)))
            con.execute(
                "DELETE FROM run_history WHERE scope = ? AND id NOT IN "
                "(SELECT id FROM run_history WHERE scope = ? ORDER BY id DESC LIMIT ?)",
                (scope, scope, limit),
            )
            return con.execute("SELECT count(*) FROM run_history WHERE scope = ?", (scope,)).fetchone()[0]

    def run_history(self, scope: str) -> list[Any]:
        with self._read() as con:
            return [json.loads(r[0]) for r in con.execute("SELECT entry FROM run_history WHERE scope = ? ORDER BY id", (scope,))]

    def set_last_build(self, scope: str, data: dict[str, Any]) -> None:
        with self._write() as con:
            con.execute(
                "INSERT INTO last_build (scope, data) VALUES (?, ?) ON CONFLICT (scope) DO UPDATE SET data = excluded.data",
                (scope, _dumps(data)),
            )

    def last_build(self, scope: str) -> dict[str, Any] | None:
        with self._read() as con:
            r = con.execute("SELECT data FROM last_build WHERE scope = ?", (scope,)).fetchone()
        return None if r is None else json.loads(r[0])

    # ------------------------------------------------------- backup manifests / price cache
    def put_backup_manifest(self, scope: str, manifest: dict[str, Any]) -> None:
        """Insert or replace the manifest of ``manifest['filename']`` (``created_at`` is indexed)."""
        with self._write() as con:
            con.execute(
                "INSERT OR REPLACE INTO backup_manifest (scope, filename, created_at, manifest) VALUES (?, ?, ?, ?)",
                (scope, str(manifest["filename"]), str(manifest.get("created_at") or ""), _dumps(manifest)),
            )

    def backup_manifests(self, scope: str) -> list[dict[str, Any]]:
        """The scope's manifests, oldest first (by ``created_at``, then filename)."""
        with self._read() as con:
            cur = con.execute("SELECT manifest FROM backup_manifest WHERE scope = ? ORDER BY created_at, filename", (scope,))
            return [json.loads(r[0]) for r in cur]

    def delete_backup_manifest(self, scope: str, filename: str) -> bool:
        with self._write() as con:
            return con.execute("DELETE FROM backup_manifest WHERE scope = ? AND filename = ?", (scope, filename)).rowcount > 0

    def price_cache(self, scope: str) -> dict[str, dict[str, Any]]:
        with self._read() as con:
            return {k: json.loads(v) for k, v in con.execute("SELECT symbol, record FROM price_cache WHERE scope = ?", (scope,))}

    def replace_price_cache(self, scope: str, records: dict[str, Any]) -> None:
        """Make the scope's cache exactly ``records`` (one transaction)."""
        with self._write() as con:
            con.execute("DELETE FROM price_cache WHERE scope = ?", (scope,))
            con.executemany(
                "INSERT INTO price_cache (scope, symbol, record) VALUES (?, ?, ?)",
                [(scope, str(k), _dumps(v)) for k, v in records.items()],
            )

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


def _dumps(value: Any) -> str:
    """JSON text for log / cache rows (the old files tolerated non-JSON leaves via ``default=str``)."""
    return json.dumps(value, sort_keys=True, default=str)
