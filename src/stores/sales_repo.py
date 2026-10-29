"""Realized-sales ledger of a plan file (schema v17): ``SalesRepo``, reached as ``store.sales``.

Typed tables (not flat text datasets), so a plan revision neither copies them nor, on restore, rewrites them:
a restore leaves every ledger row as it is (it only rewrites plan rows, flat datasets and rental).

``realized_sales``       one row per lot (or part of a lot) sold. Never hard-deleted: ``status`` goes
                         ``confirmed`` <-> ``voided`` so an undo is reversible.
``sale_candidates``      the unmatched queue: sale events not yet tied to lots. Never feeds tax or returns.
``realized_adjustments`` year-level inputs the ledger cannot derive (carryforward, state-rate override).

Nothing reads these tables yet (Phase 1 step 1.1); the helpers that derive holding period and gain live elsewhere.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from .errors import NotFoundError, ValidationError

TAX_CLASSES = ("taxable", "pre_tax", "roth", "hsa")
HOLDING_PERIODS = ("short", "long", "unknown")
WASH_FLAGS = ("none", "possible", "confirmed_by_user")
SALE_SOURCES = ("holdings_diff", "monarch", "manual", "1099b")
SALE_STATUSES = ("confirmed", "voided")
CANDIDATE_SOURCES = ("monarch", "holdings_diff")
CANDIDATE_STATES = ("unmatched", "confirmed", "dismissed", "not_a_sale")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(repr(v) for v in values)


SCHEMA_V17_DDL = f"""
CREATE TABLE realized_sales (
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
    revision_ref    INTEGER
);
CREATE INDEX ix_realized_sales_date ON realized_sales (sale_date);
CREATE INDEX ix_realized_sales_monarch ON realized_sales (monarch_id) WHERE monarch_id IS NOT NULL;
CREATE TABLE sale_candidates (
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
    updated_at          TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_sale_candidates_monarch ON sale_candidates (monarch_id) WHERE monarch_id IS NOT NULL;
CREATE TABLE realized_adjustments (
    tax_year            INTEGER NOT NULL PRIMARY KEY,
    carryforward_short  REAL NOT NULL DEFAULT 0,
    carryforward_long   REAL NOT NULL DEFAULT 0,
    state_rate_override REAL,
    updated_at          TEXT NOT NULL
) WITHOUT ROWID;
"""

_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
_SALE_FIELDS = (
    "sale_date", "settle_date", "account", "tax_class", "symbol", "shares", "proceeds", "fees", "basis",
    "purchase_date", "holding_period", "gain", "wash_flag", "wash_note", "source", "monarch_id", "lot_key",
    "official_proceeds", "official_basis", "official_gain", "official_holding_period", "revision_ref",
)


def _iso(name: str, value: Any, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not _ISO.fullmatch(value):
        raise ValidationError(f"{name} must be an ISO date (YYYY-MM-DD), got {value!r}")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{name} is not a real date: {value!r}") from exc
    return value


def _one_of(name: str, value: Any, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise ValidationError(f"{name} must be one of {', '.join(allowed)}; got {value!r}")
    return value


def _num(name: str, value: Any, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} must be a number, got {value!r}")
    return float(value)


class SalesRepo:
    """The ledger tables of one open ``PlanStore`` (``store.sales``). Cheap to create;
    writes join the store's enclosing ``transaction()`` like every other store write."""

    def __init__(self, store: Any) -> None:
        self._store = store

    # ------------------------------------------------------------------ realized_sales
    def insert_sale(self, **f: Any) -> int:
        """Record one lot sold; returns ``sale_id``. ``symbol`` is upper-cased. Derived fields (holding
        period, gain) are the caller's: this class only validates shape."""
        unknown = set(f) - set(_SALE_FIELDS)
        if unknown:
            raise ValidationError(f"unknown sale field(s): {', '.join(sorted(unknown))}")
        symbol = str(f.get("symbol") or "").strip().upper()
        if not symbol:
            raise ValidationError("a sale needs a symbol")
        account = str(f.get("account") or "").strip()
        if not account:
            raise ValidationError("a sale needs an account")
        shares = _num("shares", f.get("shares"))
        if shares <= 0:
            raise ValidationError("shares must be > 0")
        values = {
            "sale_date": _iso("sale_date", f.get("sale_date")),
            "settle_date": _iso("settle_date", f.get("settle_date"), optional=True),
            "account": account,
            "tax_class": _one_of("tax_class", f.get("tax_class"), TAX_CLASSES),
            "symbol": symbol,
            "shares": shares,
            "proceeds": _num("proceeds", f.get("proceeds")),
            "fees": _num("fees", f.get("fees", 0.0)),
            "basis": _num("basis", f.get("basis")),
            "purchase_date": _iso("purchase_date", f.get("purchase_date"), optional=True),
            "holding_period": _one_of("holding_period", f.get("holding_period"), HOLDING_PERIODS),
            "gain": _num("gain", f.get("gain"), optional=True),
            "wash_flag": _one_of("wash_flag", f.get("wash_flag", "none"), WASH_FLAGS),
            "wash_note": str(f.get("wash_note", "")),
            "source": _one_of("source", f.get("source"), SALE_SOURCES),
            "monarch_id": f.get("monarch_id") or None,
            "lot_key": str(f.get("lot_key", "")),
            "official_proceeds": _num("official_proceeds", f.get("official_proceeds"), optional=True),
            "official_basis": _num("official_basis", f.get("official_basis"), optional=True),
            "official_gain": _num("official_gain", f.get("official_gain"), optional=True),
            "official_holding_period": f.get("official_holding_period"),
            "revision_ref": f.get("revision_ref"),
        }
        now = self._store._clock()
        cols = ", ".join(values)
        with self._store._write() as con:
            cur = con.execute(
                f"INSERT INTO realized_sales ({cols}, created_at, updated_at) VALUES ({', '.join('?' * (len(values) + 2))})",
                (*values.values(), now, now))
            return int(cur.lastrowid)

    def get_sale(self, sale_id: int) -> dict[str, Any]:
        with self._store._read() as con:
            r = con.execute("SELECT * FROM realized_sales WHERE sale_id = ?", (sale_id,)).fetchone()
        if r is None:
            raise NotFoundError(f"no sale {sale_id}")
        return dict(r)

    def list_sales(self, *, year: int | None = None, include_voided: bool = False) -> list[dict[str, Any]]:
        """Sales by trade date then id; ``year`` filters on the tax year of ``sale_date``."""
        where, args = [], []
        if not include_voided:
            where.append("status = 'confirmed'")
        if year is not None:
            where.append("sale_date >= ? AND sale_date < ?")
            args += [f"{int(year):04d}-01-01", f"{int(year) + 1:04d}-01-01"]
        sql = "SELECT * FROM realized_sales" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY sale_date, sale_id"
        with self._store._read() as con:
            return [dict(r) for r in con.execute(sql, args)]

    def _set_status(self, sale_id: int, status: str) -> None:
        with self._store._write() as con:
            cur = con.execute("UPDATE realized_sales SET status = ?, updated_at = ? WHERE sale_id = ?",
                              (status, self._store._clock(), sale_id))
            if cur.rowcount == 0:
                raise NotFoundError(f"no sale {sale_id}")

    def set_wash_flag(self, sale_id: int, wash_flag: str, wash_note: str = "") -> None:
        """Set the possible-wash flag and its note on one ledger row (the detector's write)."""
        flag = _one_of("wash_flag", wash_flag, WASH_FLAGS)
        with self._store._write() as con:
            cur = con.execute("UPDATE realized_sales SET wash_flag = ?, wash_note = ?, updated_at = ? WHERE sale_id = ?",
                              (flag, str(wash_note or ""), self._store._clock(), sale_id))
            if cur.rowcount == 0:
                raise NotFoundError(f"no sale {sale_id}")

    def void_sale(self, sale_id: int) -> None:
        """Undo a sale. The row is kept (``status='voided'``) so ``unvoid_sale`` can bring it back."""
        self._set_status(sale_id, "voided")

    def unvoid_sale(self, sale_id: int) -> None:
        self._set_status(sale_id, "confirmed")

    # ------------------------------------------------------------------ sale_candidates
    def add_candidate(self, *, source: str, sale_date: str, account: str, symbol: str | None = None,
                      shares: float | None = None, price: float | None = None, amount: float | None = None,
                      monarch_id: str | None = None) -> tuple[int, bool]:
        """Queue an unmatched sale; returns ``(candidate_id, created)``. A candidate with a ``monarch_id``
        already queued is left as it is (re-importing the same file is a no-op); one without is always new."""
        _one_of("source", source, CANDIDATE_SOURCES)
        _iso("sale_date", sale_date)
        monarch_id = monarch_id or None
        now = self._store._clock()
        with self._store._write() as con:
            if monarch_id is not None:
                r = con.execute("SELECT candidate_id FROM sale_candidates WHERE monarch_id = ?", (monarch_id,)).fetchone()
                if r is not None:
                    return int(r[0]), False
            cur = con.execute(
                "INSERT INTO sale_candidates (source, sale_date, account, symbol, shares, price, amount, monarch_id, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (source, sale_date, account, (symbol.strip().upper() if symbol else None),
                 _num("shares", shares, optional=True), _num("price", price, optional=True),
                 _num("amount", amount, optional=True), monarch_id, now, now))
            return int(cur.lastrowid), True

    def list_candidates(self, *, state: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM sale_candidates" + (" WHERE state = ?" if state else "") + " ORDER BY sale_date, candidate_id"
        with self._store._read() as con:
            rows = [dict(r) for r in con.execute(sql, (state,) if state else ())]
        for r in rows:
            r["confirmed_sale_ids"] = json.loads(r["confirmed_sale_ids"])
        return rows

    def set_candidate_state(self, candidate_id: int, state: str, *, confirmed_sale_ids: list[int] | None = None) -> None:
        _one_of("state", state, CANDIDATE_STATES)
        with self._store._write() as con:
            cur = con.execute(
                "UPDATE sale_candidates SET state = ?, confirmed_sale_ids = ?, updated_at = ? WHERE candidate_id = ?",
                (state, json.dumps([int(i) for i in confirmed_sale_ids or []]), self._store._clock(), candidate_id))
            if cur.rowcount == 0:
                raise NotFoundError(f"no sale candidate {candidate_id}")

    # ------------------------------------------------------------------ realized_adjustments
    def set_adjustment(self, tax_year: int, *, carryforward_short: float = 0.0, carryforward_long: float = 0.0,
                       state_rate_override: float | None = None) -> None:
        with self._store._write() as con:
            con.execute(
                "INSERT INTO realized_adjustments (tax_year, carryforward_short, carryforward_long, state_rate_override, updated_at) "
                "VALUES (?,?,?,?,?) ON CONFLICT (tax_year) DO UPDATE SET carryforward_short = excluded.carryforward_short, "
                "carryforward_long = excluded.carryforward_long, state_rate_override = excluded.state_rate_override, "
                "updated_at = excluded.updated_at",
                (int(tax_year), _num("carryforward_short", carryforward_short), _num("carryforward_long", carryforward_long),
                 _num("state_rate_override", state_rate_override, optional=True), self._store._clock()))

    def adjustment(self, tax_year: int) -> dict[str, Any] | None:
        with self._store._read() as con:
            r = con.execute("SELECT * FROM realized_adjustments WHERE tax_year = ?", (int(tax_year),)).fetchone()
        return dict(r) if r else None

    def adjustments(self) -> list[dict[str, Any]]:
        with self._store._read() as con:
            return [dict(r) for r in con.execute("SELECT * FROM realized_adjustments ORDER BY tax_year")]
