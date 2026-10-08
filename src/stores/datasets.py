"""Typed flat datasets of ``plan.db``: holdings lots, liabilities, HSA schedule and target
allocation (schema v2, WP6.1 / P4.1); spending taxonomy and aliases (schema v3, WP6.3a, reached
through ``store.spending``, see ``spending_repo.py``); spending budget, budget lines and tier
overrides (schema v4, WP6.3b); spending rules, category map and group budget (schema v5, WP6.3c);
YTD transactions, account setup and import history (schema v6, WP6.4).

Each dataset is one table that replaces one legacy CSV file. Columns keep the CSV column
names and are stored as text exactly as entered, so the build parses the same strings it
parsed from the file (no number formatting can move a result). Row order is the
``position`` column (0, 1, 2 ... in file order). The legacy CSV text form lives in
``csv_exchange.flat_csv`` (``dataset_csv_text`` / ``replace_dataset_from_csv_text``).
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from .errors import ValidationError

HOLDINGS_COLUMNS = ("account", "symbol", "purchase_date", "shares", "purchase_price", "lot_type", "note")
LIABILITIES_COLUMNS = (
    "liability_id", "type", "label", "balance", "interest_rate",
    "monthly_payment", "start_year", "payoff_year", "notes",
)
HSA_SCHEDULE_COLUMNS = ("year", "optimizer_amount", "override_amount", "locked", "note")
TARGET_ALLOCATION_COLUMNS = ("asset_class", "target_pct")

# Spending set (WP6.3a). ``group`` is an SQL keyword, so every column name is quoted in SQL.
SPENDING_TAXONOMY_COLUMNS = ("tracking_type", "group", "category_id", "label", "origin", "status", "notes")
SPENDING_ALIASES_COLUMNS = ("match_value", "match_field", "exact", "priority", "category_id", "source")

# Spending budget, budget lines and tier overrides (WP6.3b).
SPENDING_BUDGET_COLUMNS = (
    "kind", "key", "label", "annual_budget", "start_year", "end_year", "one_time_year",
    "notes", "_mode", "line_section", "line_mode", "no_annualize",
)
SPENDING_BUDGET_LINES_COLUMNS = (
    "section", "line_id", "label", "category_id", "start_year", "end_year",
    "one_time_year", "amount_per_year", "mode", "notes",
)
SPENDING_TIER_OVERRIDES_COLUMNS = ("category_id", "tier", "notes")

# Spending rules, category map and group budget (WP6.3c).
SPENDING_RULES_COLUMNS = ("keyword", "category_id", "match_field", "exact", "priority")
SPENDING_CATEGORY_MAP_COLUMNS = ("super_group", "group", "category", "tracking")
SPENDING_GROUP_BUDGET_COLUMNS = ("group", "budget_pct", "budget_override", "notes")

# YTD actuals (WP6.4): the three YTD files' columns, spelled as in the files (they contain spaces).
YTD_TRANSACTIONS_COLUMNS = (
    "Date", "Merchant", "Category", "Account", "Original Statement", "Notes",
    "Amount", "Tags", "Owner", "Monarch Id",
)
YTD_ACCOUNT_SETUP_COLUMNS = (
    "Account", "Role", "Mapped Investment Account", "Prior Year End Date",
    "Prior Year End Balance", "Current Value", "Current Balance", "Notes",
)
YTD_IMPORT_HISTORY_COLUMNS = (
    "Loaded At", "Mode", "Rows Received", "Rows Added", "Rows Skipped",
    "Earliest Transaction Date", "Latest Transaction Date", "Notes", "Rows Updated",
)

_V2_DATASETS: dict[str, tuple[str, ...]] = {
    "holdings_lots": HOLDINGS_COLUMNS,
    "liabilities": LIABILITIES_COLUMNS,
    "hsa_schedule": HSA_SCHEDULE_COLUMNS,
    "target_allocation": TARGET_ALLOCATION_COLUMNS,
}
_V3_DATASETS: dict[str, tuple[str, ...]] = {
    "spending_taxonomy": SPENDING_TAXONOMY_COLUMNS,
    "spending_aliases": SPENDING_ALIASES_COLUMNS,
}
_V4_DATASETS: dict[str, tuple[str, ...]] = {
    "spending_budget": SPENDING_BUDGET_COLUMNS,
    "spending_budget_lines": SPENDING_BUDGET_LINES_COLUMNS,
    "spending_tier_overrides": SPENDING_TIER_OVERRIDES_COLUMNS,
}
_V5_DATASETS: dict[str, tuple[str, ...]] = {
    "spending_rules": SPENDING_RULES_COLUMNS,
    "spending_category_map": SPENDING_CATEGORY_MAP_COLUMNS,
    "spending_group_budget": SPENDING_GROUP_BUDGET_COLUMNS,
}
_V6_DATASETS: dict[str, tuple[str, ...]] = {
    "ytd_transactions": YTD_TRANSACTIONS_COLUMNS,
    "ytd_account_setup": YTD_ACCOUNT_SETUP_COLUMNS,
    "ytd_import_history": YTD_IMPORT_HISTORY_COLUMNS,
}
# Every flat dataset table -> its columns (a later schema version adds its tables here).
_DATASETS: dict[str, tuple[str, ...]] = {
    **_V2_DATASETS, **_V3_DATASETS, **_V4_DATASETS, **_V5_DATASETS, **_V6_DATASETS,
}
YTD_DATASETS: tuple[str, ...] = tuple(_V6_DATASETS)


def _q(name: str) -> str:
    """A quoted SQL identifier (column names are the CSV's, some are keywords)."""
    return '"' + name.replace('"', '""') + '"'


def _ddl(datasets: Mapping[str, tuple[str, ...]], *, quote: bool = True) -> str:
    parts = []
    for table, cols in datasets.items():
        body = ",\n    ".join(f"{_q(c) if quote else c} TEXT NOT NULL DEFAULT ''" for c in cols)
        parts.append(
            f"CREATE TABLE {table} (\n    position INTEGER PRIMARY KEY,\n    {body},\n"
            "    extra TEXT NOT NULL DEFAULT '{}'\n);"
        )
    return "\n".join(parts)


SCHEMA_V2_DDL = _ddl(_V2_DATASETS, quote=False)  # as shipped in v2 (its names need no quoting)
SCHEMA_V3_DDL = _ddl(_V3_DATASETS)
SCHEMA_V4_DDL = _ddl(_V4_DATASETS)
# v5 also adds the revision-scoped dataset copies (recovery copies of a flat dataset: the rows
# of a dataset as they were when a plan revision was taken, JSON per row, cascade-deleted with it).
SCHEMA_V5_DDL = _ddl(_V5_DATASETS) + """
CREATE TABLE revision_datasets (
    revision_id INTEGER NOT NULL REFERENCES plan_revisions (id) ON DELETE CASCADE,
    dataset     TEXT    NOT NULL CHECK (dataset <> ''),
    position    INTEGER NOT NULL,
    row         TEXT    NOT NULL,
    PRIMARY KEY (revision_id, dataset, position)
) WITHOUT ROWID;
"""
SCHEMA_V6_DDL = _ddl(_V6_DATASETS)


class FlatDatasetRepository:
    """One flat dataset table of a ``PlanStore`` (implements ``DatasetRepository``).

    A legacy file can carry columns beyond the known ones (``market_value``, ``asset_class``
    ... in a holdings file); they are kept per row as JSON in ``extra`` and come back from
    ``rows()`` as ordinary keys (``extra_columns()`` lists their names).
    """

    def __init__(self, store: Any, table: str) -> None:
        self._store = store
        self.table = table
        self.columns = _DATASETS[table]

    def rows(self) -> list[dict[str, str]]:
        """Rows in file order, keyed by the CSV column names (known columns first, then any
        extra columns the file carried)."""
        with self._store._read() as con:
            cur = con.execute(f"SELECT {', '.join(map(_q, self.columns))}, extra FROM {self.table} ORDER BY position")
            out = []
            for r in cur:
                row = dict(zip(self.columns, r[:-1]))
                for k, v in json.loads(r[-1]).items():
                    row.setdefault(k, v)
                out.append(row)
            return out

    def extra_columns(self) -> list[str]:
        """Names of the extra (unknown) columns used by any row, sorted."""
        with self._store._read() as con:
            names: set[str] = set()
            for (blob,) in con.execute(f"SELECT extra FROM {self.table}"):
                names.update(json.loads(blob))
        return sorted(names)

    def replace_all(self, rows: Iterable[Mapping[str, Any]]) -> int:
        """Atomically replace the dataset; return the number of rows written.

        Values must be text (``None`` is stored as an empty string); columns other than the
        known ones are kept as extra columns. A failure leaves the old rows in place.
        """
        clean = [self._clean(r) for r in rows]
        marks = ", ".join("?" for _ in range(len(self.columns) + 2))
        with self._store._write() as con:
            con.execute(f"DELETE FROM {self.table}")
            con.executemany(
                f"INSERT INTO {self.table} (position, {', '.join(map(_q, self.columns))}, extra) VALUES ({marks})",
                [(i, *vals, json.dumps(extra, ensure_ascii=False, sort_keys=True)) for i, (vals, extra) in enumerate(clean)],
            )
        return len(clean)

    def count(self) -> int:
        with self._store._read() as con:
            return int(con.execute(f"SELECT COUNT(*) FROM {self.table}").fetchone()[0])

    def _clean(self, row: Mapping[str, Any]) -> tuple[tuple[str, ...], dict[str, str]]:
        if not isinstance(row, Mapping):
            raise ValidationError(f"{self.table} row must be a mapping, got {type(row).__name__}")
        known: list[str] = []
        extra: dict[str, str] = {}
        for k, v in row.items():
            if v is None:
                v = ""
            if not isinstance(k, str) or not k:
                raise ValidationError(f"{self.table} column names must be non-empty text")
            if not isinstance(v, str):
                raise ValidationError(f"{self.table}.{k} must be str, got {type(v).__name__}")
            if k not in self.columns:
                extra[k] = v
        for c in self.columns:
            known.append(row.get(c) or "")
        return tuple(known), extra
