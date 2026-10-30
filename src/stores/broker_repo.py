"""Broker activity imports of a plan file (schema v19): ``BrokerRepo``, reached as ``store.broker``.

``broker_imports``     one row per committed activity file (broker, plan account, date range, counts). ``status``
                       goes ``applied`` -> ``reverted``; a reverted import keeps its row for the history.
``broker_activity``    every row of a committed file, keyed on ``row_key`` (unique), with links to the sale candidate
                       it fed and the holdings lot it created or matched (``lot_ref`` JSON).
``broker_account_map`` remembered file-name pattern (e.g. ``fidelity:5678``) -> plan account.

v19 also rebuilds ``sale_candidates`` (source ``broker``, state ``superseded``, columns ``fees``, ``settle_date``,
``broker_key``) and ``realized_sales`` (source ``broker``): SQLite cannot alter a CHECK, so each is copied, dropped and
renamed with its ids and indexes preserved. Design: ``2026-10-30-broker-activity-bulk-import-design-and-plan.md``.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from .errors import NotFoundError, ValidationError
from .sales_repo import (CANDIDATE_SOURCES, CANDIDATE_STATES, HOLDING_PERIODS, SALE_SOURCES, SALE_STATUSES,
                         TAX_CLASSES, WASH_FLAGS, _in)

IMPORT_STATUSES = ("applied", "reverted")
_SALE_COLUMNS = ("sale_id, sale_date, settle_date, account, tax_class, symbol, shares, proceeds, fees, basis, purchase_date, "
                 "holding_period, gain, wash_flag, wash_note, source, monarch_id, lot_key, status, official_proceeds, "
                 "official_basis, official_gain, official_holding_period, created_at, updated_at, revision_ref, statement_id")
_CANDIDATE_COLUMNS = ("candidate_id, source, sale_date, account, symbol, shares, price, amount, monarch_id, state, "
                      "confirmed_sale_ids, created_at, updated_at")

SCHEMA_V19_DDL = f"""
CREATE TABLE realized_sales_v19 (
    sale_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_date       TEXT NOT NULL,
    settle_date     TEXT,
    account         TEXT NOT NULL CHECK (account <> ''),
    tax_class       TEXT NOT NULL CHECK (tax_class IN ({_in(TAX_CLASSES)})),
    symbol          TEXT NOT NULL CHECK (symbol <> ''),
    shares          REAL NOT NULL CHECK (shares > 0),
    proceeds        REAL NOT NULL,
    fees            REAL NOT NULL DEFAULT 0,
    basis           REAL NOT NULL,
    purchase_date   TEXT,
    holding_period  TEXT NOT NULL CHECK (holding_period IN ({_in(HOLDING_PERIODS)})),
    gain            REAL,
    wash_flag       TEXT NOT NULL DEFAULT 'none' CHECK (wash_flag IN ({_in(WASH_FLAGS)})),
    wash_note       TEXT NOT NULL DEFAULT '',
    source          TEXT NOT NULL CHECK (source IN ({_in(SALE_SOURCES)})),
    monarch_id      TEXT,
    lot_key         TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'confirmed' CHECK (status IN ({_in(SALE_STATUSES)})),
    official_proceeds       REAL,
    official_basis          REAL,
    official_gain           REAL,
    official_holding_period TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    revision_ref    INTEGER,
    statement_id    INTEGER
);
INSERT INTO realized_sales_v19 ({_SALE_COLUMNS}) SELECT {_SALE_COLUMNS} FROM realized_sales;
DROP TABLE realized_sales;
ALTER TABLE realized_sales_v19 RENAME TO realized_sales;
CREATE INDEX ix_realized_sales_date ON realized_sales (sale_date);
CREATE INDEX ix_realized_sales_monarch ON realized_sales (monarch_id) WHERE monarch_id IS NOT NULL;
CREATE TABLE sale_candidates_v19 (
    candidate_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    source              TEXT NOT NULL CHECK (source IN ({_in(CANDIDATE_SOURCES)})),
    sale_date           TEXT NOT NULL,
    account             TEXT NOT NULL,
    symbol              TEXT,
    shares              REAL,
    price               REAL,
    amount              REAL,
    monarch_id          TEXT,
    state               TEXT NOT NULL DEFAULT 'unmatched' CHECK (state IN ({_in(CANDIDATE_STATES)})),
    confirmed_sale_ids  TEXT NOT NULL DEFAULT '[]',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    fees                REAL,
    settle_date         TEXT,
    broker_key          TEXT
);
INSERT INTO sale_candidates_v19 ({_CANDIDATE_COLUMNS}) SELECT {_CANDIDATE_COLUMNS} FROM sale_candidates;
DROP TABLE sale_candidates;
ALTER TABLE sale_candidates_v19 RENAME TO sale_candidates;
CREATE UNIQUE INDEX ux_sale_candidates_monarch ON sale_candidates (monarch_id) WHERE monarch_id IS NOT NULL;
CREATE UNIQUE INDEX ux_sale_candidates_broker ON sale_candidates (broker_key) WHERE broker_key IS NOT NULL;
CREATE TABLE broker_imports (
    import_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    broker      TEXT NOT NULL CHECK (broker <> ''),
    account     TEXT NOT NULL CHECK (account <> ''),
    file_name   TEXT NOT NULL DEFAULT '',
    date_from   TEXT,
    date_to     TEXT,
    rows_total  INTEGER NOT NULL DEFAULT 0,
    rows_new    INTEGER NOT NULL DEFAULT 0,
    summary     TEXT NOT NULL DEFAULT '{{}}',
    status      TEXT NOT NULL DEFAULT 'applied' CHECK (status IN ({_in(IMPORT_STATUSES)})),
    imported_at TEXT NOT NULL
);
CREATE TABLE broker_activity (
    activity_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id        INTEGER NOT NULL,
    row_key          TEXT NOT NULL UNIQUE,
    broker           TEXT NOT NULL,
    account          TEXT NOT NULL,
    run_date         TEXT NOT NULL,
    settle_date      TEXT,
    kind             TEXT NOT NULL,
    sweep            INTEGER NOT NULL DEFAULT 0 CHECK (sweep IN (0, 1)),
    action           TEXT NOT NULL DEFAULT '',
    symbol           TEXT,
    description      TEXT NOT NULL DEFAULT '',
    quantity         REAL,
    price            REAL,
    commission       REAL,
    fees             REAL,
    accrued_interest REAL,
    amount           REAL NOT NULL DEFAULT 0,
    candidate_id     INTEGER,
    lot_ref          TEXT
);
CREATE INDEX ix_broker_activity_account ON broker_activity (account, run_date);
CREATE INDEX ix_broker_activity_import ON broker_activity (import_id);
CREATE TABLE broker_account_map (
    file_pattern TEXT NOT NULL PRIMARY KEY,
    account      TEXT NOT NULL CHECK (account <> '')
) WITHOUT ROWID;
"""

_ACTIVITY_FIELDS = ("row_key", "broker", "account", "run_date", "settle_date", "kind", "sweep", "action", "symbol",
                    "description", "quantity", "price", "commission", "fees", "accrued_interest", "amount",
                    "candidate_id", "lot_ref")


class BrokerRepo:
    def __init__(self, store: Any) -> None:
        self._store = store

    # ------------------------------------------------------------------ imports
    def add_import(self, *, broker: str, account: str, file_name: str = "", date_from: str | None = None,
                   date_to: str | None = None, rows_total: int = 0, rows_new: int = 0,
                   summary: Mapping[str, Any] | None = None) -> int:
        if not str(broker).strip() or not str(account).strip():
            raise ValidationError("an import needs a broker and an account")
        with self._store._write() as con:
            cur = con.execute(
                "INSERT INTO broker_imports (broker, account, file_name, date_from, date_to, rows_total, rows_new, summary, "
                "imported_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (broker, account, file_name or "", date_from, date_to, int(rows_total), int(rows_new),
                 json.dumps(dict(summary or {}), sort_keys=True), self._store._clock()))
            return int(cur.lastrowid)

    @staticmethod
    def _import(r: Any) -> dict[str, Any]:
        d = dict(r)
        d["summary"] = json.loads(d["summary"] or "{}")
        return d

    def get_import(self, import_id: int) -> dict[str, Any]:
        with self._store._read() as con:
            r = con.execute("SELECT * FROM broker_imports WHERE import_id = ?", (import_id,)).fetchone()
        if r is None:
            raise NotFoundError(f"no broker import {import_id}")
        return self._import(r)

    def list_imports(self, *, account: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM broker_imports" + (" WHERE account = ?" if account else "") + " ORDER BY import_id"
        with self._store._read() as con:
            return [self._import(r) for r in con.execute(sql, (account,) if account else ())]

    def set_import_status(self, import_id: int, status: str) -> None:
        if status not in IMPORT_STATUSES:
            raise ValidationError(f"status must be one of {', '.join(IMPORT_STATUSES)}")
        with self._store._write() as con:
            if con.execute("UPDATE broker_imports SET status = ? WHERE import_id = ?", (status, import_id)).rowcount == 0:
                raise NotFoundError(f"no broker import {import_id}")

    # ------------------------------------------------------------------ activity rows
    def add_rows(self, import_id: int, rows: Iterable[Mapping[str, Any]]) -> list[int]:
        """Insert rows (``_ACTIVITY_FIELDS``); a ``row_key`` already stored is a ``ValidationError`` (callers filter
        with ``existing_keys`` first)."""
        ids = []
        with self._store._write() as con:
            for r in rows:
                vals = [r.get(f) for f in _ACTIVITY_FIELDS]
                vals[_ACTIVITY_FIELDS.index("sweep")] = 1 if r.get("sweep") else 0
                lot_ref = r.get("lot_ref")
                vals[_ACTIVITY_FIELDS.index("lot_ref")] = json.dumps(lot_ref, sort_keys=True) if lot_ref else None
                try:
                    cur = con.execute(f"INSERT INTO broker_activity (import_id, {', '.join(_ACTIVITY_FIELDS)}) "
                                      f"VALUES ({', '.join('?' * (len(_ACTIVITY_FIELDS) + 1))})", (import_id, *vals))
                except Exception as exc:  # sqlite3.IntegrityError on a duplicate row_key
                    raise ValidationError(f"activity row {r.get('row_key')} is already imported") from exc
                ids.append(int(cur.lastrowid))
        return ids

    def existing_keys(self, keys: Iterable[str]) -> set[str]:
        keys = list(keys)
        found: set[str] = set()
        with self._store._read() as con:
            for i in range(0, len(keys), 500):
                chunk = keys[i:i + 500]
                found |= {r[0] for r in con.execute(
                    f"SELECT row_key FROM broker_activity WHERE row_key IN ({', '.join('?' * len(chunk))})", chunk)}
        return found

    def activity(self, *, account: str | None = None, import_id: int | None = None, year: int | None = None,
                 kinds: Iterable[str] | None = None) -> list[dict[str, Any]]:
        where, args = [], []
        if account is not None:
            where.append("account = ?"); args.append(account)
        if import_id is not None:
            where.append("import_id = ?"); args.append(import_id)
        if year is not None:
            where.append("run_date >= ? AND run_date < ?"); args += [f"{int(year):04d}-01-01", f"{int(year) + 1:04d}-01-01"]
        kinds = list(kinds or [])
        if kinds:
            where.append(f"kind IN ({', '.join('?' * len(kinds))})"); args += kinds
        sql = "SELECT * FROM broker_activity" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY run_date, activity_id"
        with self._store._read() as con:
            rows = [dict(r) for r in con.execute(sql, args)]
        for r in rows:
            r["sweep"] = bool(r["sweep"])
            r["lot_ref"] = json.loads(r["lot_ref"]) if r["lot_ref"] else None
        return rows

    def delete_import_rows(self, import_id: int) -> int:
        with self._store._write() as con:
            return con.execute("DELETE FROM broker_activity WHERE import_id = ?", (import_id,)).rowcount

    # ------------------------------------------------------------------ account map
    def account_for(self, file_pattern: str | None) -> str | None:
        if not file_pattern:
            return None
        with self._store._read() as con:
            r = con.execute("SELECT account FROM broker_account_map WHERE file_pattern = ?", (file_pattern,)).fetchone()
        return r[0] if r else None

    def remember_account(self, file_pattern: str, account: str) -> None:
        if not file_pattern or not str(account).strip():
            return
        with self._store._write() as con:
            con.execute("INSERT INTO broker_account_map (file_pattern, account) VALUES (?, ?) "
                        "ON CONFLICT(file_pattern) DO UPDATE SET account = excluded.account", (file_pattern, account))
