"""Rental properties of a plan file (WP12.4): ``RentalRepo``, reached as ``store.rental``.

Design ``docs/superpowers/specs/2026-10-05-rental-property-module-design.md`` section 3. Three
typed tables (schema v9), unlike the text-only flat datasets: numbers are ``REAL`` / ``INTEGER``,
a blank is ``NULL``.

``rental_properties``       one row per property (order = ``property_id``); names are unique
                            ignoring case.
``rental_improvements``     capital improvements of a property (``year``, optional ``month``,
                            ``amount``), in entry order; cascade-deleted with the property.
``rental_year_overrides``   per-year ``gross_rent`` / ``operating_expenses`` that replace the
                            formulas, one row per (property, year); cascade-deleted likewise.

Rows go in and come out as the plain dicts ``parse_rental_properties`` takes (one dict per
property; ``improvements`` a list of rows, ``overrides`` a list of rows with a ``year``). A
``NULL`` is left out of the dict, so a stored row means exactly what the keys present mean.
This layer checks types only (a number is a number); the meaning (ranges, kind rules, missing
required values, defaults such as month 7) is the parse boundary's job at build time, so a
half-filled property can be saved and is kept while the feature is off.

Carried passive losses and accumulated depreciation are computed by the engine, never stored.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from .errors import ValidationError

# Column groups, named as the parser's keys (src/parsing/rental_properties.py).
TEXT_COLUMNS = ("kind", "owner", "notes")
REAL_COLUMNS = (
    # money
    "purchase_price", "closing_costs", "current_value", "monthly_rent", "property_tax", "insurance", "hoa",
    "utilities", "other_expenses", "loan_balance", "loan_monthly_payment", "prior_suspended_loss", "sale_price",
    "value_at_conversion", "adjusted_basis_at_conversion",
    # shares and rates
    "land_share", "vacancy_rate", "maintenance_pct", "management_pct", "selling_cost_pct",
    "appreciation", "rent_growth", "expense_growth", "property_tax_growth", "loan_rate",
)
INT_COLUMNS = (
    "purchase_year", "value_as_of_year", "rental_start_year", "rental_end_year", "loan_balance_year",
    "placed_in_service_year", "sale_year", "conversion_year",
    "purchase_month", "placed_in_service_month", "sale_month", "conversion_month", "loan_term_years",
)
BOOL_COLUMNS = ("active_participation",)
PROPERTY_COLUMNS = (*TEXT_COLUMNS, *REAL_COLUMNS, *INT_COLUMNS, *BOOL_COLUMNS)
_PROPERTY_KEYS = {"name", "improvements", "overrides", *PROPERTY_COLUMNS}

IMPROVEMENT_KEYS = ("year", "month", "amount", "description")
OVERRIDE_REAL_COLUMNS = ("gross_rent", "operating_expenses")
OVERRIDE_KEYS = ("year", *OVERRIDE_REAL_COLUMNS, "notes")


def _property_ddl() -> str:
    cols = ",\n    ".join(
        [f"{c} TEXT NOT NULL DEFAULT ''" for c in TEXT_COLUMNS if c != "kind"]
        + [f"{c} REAL" for c in REAL_COLUMNS]
        + [f"{c} INTEGER" for c in INT_COLUMNS]
        + [f"{c} INTEGER CHECK ({c} IN (0, 1))" for c in BOOL_COLUMNS]
    )
    return (
        "CREATE TABLE rental_properties (\n"
        "    property_id INTEGER PRIMARY KEY,\n"
        "    name        TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK (name <> ''),\n"
        "    kind        TEXT NOT NULL DEFAULT 'standalone',\n"
        f"    {cols}\n);"
    )


SCHEMA_V9_DDL = _property_ddl() + """
CREATE TABLE rental_improvements (
    property_id INTEGER NOT NULL REFERENCES rental_properties (property_id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    year        INTEGER,
    month       INTEGER,
    amount      REAL,
    description TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (property_id, position)
) WITHOUT ROWID;
CREATE TABLE rental_year_overrides (
    property_id        INTEGER NOT NULL REFERENCES rental_properties (property_id) ON DELETE CASCADE,
    year               INTEGER NOT NULL,
    gross_rent         REAL,
    operating_expenses REAL,
    notes              TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (property_id, year)
) WITHOUT ROWID;
"""


# ------------------------------------------------------------------------------ coercion
def _blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _real(v: Any, where: str, field: str) -> float | None:
    if _blank(v):
        return None
    if isinstance(v, bool):
        raise ValidationError(f"{where}: {field} must be a number, got {v!r}")
    if isinstance(v, (int, float)):
        x = float(v)
    else:
        text = str(v).strip().replace(",", "").replace("$", "")
        pct = text.endswith("%")
        try:
            x = float(text.rstrip("%").strip())
        except ValueError:
            raise ValidationError(f"{where}: {field} must be a number, got {v!r}") from None
        x = x / 100.0 if pct else x
    if not math.isfinite(x):
        raise ValidationError(f"{where}: {field} must be a finite number, got {v!r}")
    return x


def _int(v: Any, where: str, field: str) -> int | None:
    x = _real(v, where, field)
    if x is None:
        return None
    if x != int(x):
        raise ValidationError(f"{where}: {field} must be a whole number, got {v!r}")
    return int(x)


def _flag(v: Any, where: str, field: str) -> int | None:
    if _blank(v):
        return None
    if isinstance(v, bool):
        return int(v)
    text = str(v).strip().lower()
    if text in ("true", "yes", "y", "1", "1.0"):
        return 1
    if text in ("false", "no", "n", "0", "0.0"):
        return 0
    raise ValidationError(f"{where}: {field} must be yes or no, got {v!r}")


def _text(v: Any, where: str, field: str) -> str:
    if v is None:
        return ""
    if not isinstance(v, str):
        raise ValidationError(f"{where}: {field} must be text, got {type(v).__name__}")
    return v.strip()


def _unknown(row: Mapping[str, Any], allowed: Iterable[str], where: str) -> None:
    extra = sorted(str(k) for k in row if k not in set(allowed))
    if extra:
        raise ValidationError(f"{where}: unknown field(s) {', '.join(extra)}")


def _clean_property(row: Any, index: int) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise ValidationError(f"rental property {index + 1} must be a mapping, got {type(row).__name__}")
    name = _text(row.get("name"), f"rental property {index + 1}", "name")
    if not name:
        raise ValidationError(f"rental property {index + 1}: name is required")
    where = f"rental property {name!r}"
    _unknown(row, _PROPERTY_KEYS, where)
    out: dict[str, Any] = {"name": name}
    for c in TEXT_COLUMNS:
        out[c] = _text(row.get(c), where, c)
    out["kind"] = out["kind"] or "standalone"
    for c in REAL_COLUMNS:
        out[c] = _real(row.get(c), where, c)
    for c in INT_COLUMNS:
        out[c] = _int(row.get(c), where, c)
    for c in BOOL_COLUMNS:
        out[c] = _flag(row.get(c), where, c)
    out["improvements"] = _clean_improvements(row.get("improvements"), where)
    out["overrides"] = _clean_overrides(row.get("overrides"), where)
    return out


def _clean_improvements(rows: Any, where: str) -> list[dict[str, Any]]:
    if _blank(rows):
        return []
    if not isinstance(rows, (list, tuple)):
        raise ValidationError(f"{where}: improvements must be a list of rows")
    out = []
    for j, imp in enumerate(rows):
        at = f"{where}, improvement {j + 1}"
        if not isinstance(imp, Mapping):
            raise ValidationError(f"{at}: must be a mapping")
        _unknown(imp, IMPROVEMENT_KEYS, at)
        out.append({
            "year": _int(imp.get("year"), at, "year"),
            "month": _int(imp.get("month"), at, "month"),
            "amount": _real(imp.get("amount"), at, "amount"),
            "description": _text(imp.get("description"), at, "description"),
        })
    return out


def _clean_overrides(raw: Any, where: str) -> list[dict[str, Any]]:
    if _blank(raw):
        return []
    if isinstance(raw, Mapping):
        items = [({"year": y, **ov} if isinstance(ov, Mapping) else ov) for y, ov in raw.items()]
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        raise ValidationError(f"{where}: overrides must be rows by year")
    out: dict[int, dict[str, Any]] = {}
    for j, ov in enumerate(items):
        at = f"{where}, override {j + 1}"
        if not isinstance(ov, Mapping):
            raise ValidationError(f"{at}: must be a mapping with a year")
        _unknown(ov, OVERRIDE_KEYS, at)
        year = _int(ov.get("year"), at, "year")
        if year is None:
            raise ValidationError(f"{at}: year is required")
        if year in out:
            raise ValidationError(f"{where}: two overrides for {year}")
        out[year] = {
            "year": year,
            **{c: _real(ov.get(c), at, c) for c in OVERRIDE_REAL_COLUMNS},
            "notes": _text(ov.get("notes"), at, "notes"),
        }
    return [out[y] for y in sorted(out)]


def _names_unique(rows: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for r in rows:
        key = r["name"].casefold()
        if key in seen:
            raise ValidationError(f"rental properties: two are named {r['name']!r}; names must differ")
        seen.add(key)


def _present(row: Mapping[str, Any]) -> dict[str, Any]:
    """Drop the NULL / empty-text keys: what is left is what was entered."""
    return {k: v for k, v in row.items() if v is not None and v != ""}


# --------------------------------------------------------------------------- repository
class RentalRepo:
    """The rental property set of one open ``PlanStore`` (``store.rental``).

    Cheap to create; it holds no state beyond the store. Writes join the store's enclosing
    ``transaction()`` like every other store write.
    """

    def __init__(self, store: Any) -> None:
        self._store = store

    def count(self) -> int:
        with self._store._read() as con:
            return int(con.execute("SELECT COUNT(*) FROM rental_properties").fetchone()[0])

    def names(self) -> list[str]:
        with self._store._read() as con:
            return [r[0] for r in con.execute("SELECT name FROM rental_properties ORDER BY property_id")]

    def properties(self) -> list[dict[str, Any]]:
        """Every property in entry order, as ``parse_rental_properties`` input rows."""
        with self._store._read() as con:
            props = [dict(r) for r in con.execute("SELECT * FROM rental_properties ORDER BY property_id")]
            imps: dict[int, list[dict[str, Any]]] = {}
            for r in con.execute("SELECT * FROM rental_improvements ORDER BY property_id, position"):
                imps.setdefault(r["property_id"], []).append(_present({k: r[k] for k in IMPROVEMENT_KEYS}))
            ovs: dict[int, list[dict[str, Any]]] = {}
            for r in con.execute("SELECT * FROM rental_year_overrides ORDER BY property_id, year"):
                ovs.setdefault(r["property_id"], []).append(_present({k: r[k] for k in OVERRIDE_KEYS}))
        out = []
        for p in props:
            pid = p.pop("property_id")
            row = _present(p)
            if "active_participation" in row:
                row["active_participation"] = bool(row["active_participation"])
            row["improvements"] = imps.get(pid, [])
            row["overrides"] = ovs.get(pid, [])
            out.append(row)
        return out

    def get(self, name: str) -> dict[str, Any] | None:
        key = str(name).strip().casefold()
        return next((p for p in self.properties() if p["name"].casefold() == key), None)

    def replace_all(self, rows: Iterable[Mapping[str, Any]]) -> int:
        """Atomically replace the whole set; returns the number of properties written. A bad
        row leaves the old set in place."""
        clean = [_clean_property(r, i) for i, r in enumerate(rows)]
        _names_unique(clean)
        with self._store._write() as con:
            con.execute("DELETE FROM rental_properties")  # children cascade
            for pid, p in enumerate(clean, start=1):
                self._insert(con, pid, p)
        return len(clean)

    def upsert(self, row: Mapping[str, Any]) -> int:
        """Add the property, or replace the one with the same name (any case) keeping its place
        in the order; returns its ``property_id``."""
        p = _clean_property(row, 0)
        with self._store._write() as con:
            found = con.execute("SELECT property_id FROM rental_properties WHERE name = ?", (p["name"],)).fetchone()
            if found is not None:
                pid = int(found[0])
                con.execute("DELETE FROM rental_properties WHERE property_id = ?", (pid,))
            else:
                pid = int(con.execute("SELECT COALESCE(MAX(property_id), 0) + 1 FROM rental_properties").fetchone()[0])
            self._insert(con, pid, p)
        return pid

    def delete(self, name: str) -> bool:
        """Remove the property named ``name`` (any case) with its improvements and overrides;
        ``False`` when there is none."""
        with self._store._write() as con:
            cur = con.execute("DELETE FROM rental_properties WHERE name = ?", (str(name).strip(),))
            return cur.rowcount > 0

    @staticmethod
    def _insert(con: Any, pid: int, p: Mapping[str, Any]) -> None:
        cols = ("property_id", "name", *PROPERTY_COLUMNS)
        con.execute(
            f"INSERT INTO rental_properties ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
            (pid, p["name"], *(p[c] for c in PROPERTY_COLUMNS)),
        )
        con.executemany(
            "INSERT INTO rental_improvements (property_id, position, year, month, amount, description) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(pid, i, im["year"], im["month"], im["amount"], im["description"]) for i, im in enumerate(p["improvements"])],
        )
        con.executemany(
            "INSERT INTO rental_year_overrides (property_id, year, gross_rent, operating_expenses, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            [(pid, ov["year"], ov["gross_rent"], ov["operating_expenses"], ov["notes"]) for ov in p["overrides"]],
        )


__all__ = ["RentalRepo", "SCHEMA_V9_DDL", "PROPERTY_COLUMNS"]
