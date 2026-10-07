"""PlanStore: the access layer over ``plan.db`` (the ``.rpx`` plan file). WP2.2 / P1.2.

WP4.1 finalised the row model (``documentation/reference/PLAN_ROWS_MODEL.md``): the
plan CSV importer (``src/csv_exchange``) and conversion step C3 (``src/legacy_conversion``)
write it; the product read and write paths move onto it in WP4.2-WP4.5.

Schema v1 (``PRAGMA user_version = 1``, ``PRAGMA application_id = PLAN_APPLICATION_ID``)
---------------------------------------------------------------------------------------
``plan_rows``       the sectioned plan rows. ``row_id`` is ``INTEGER PRIMARY KEY
                    AUTOINCREMENT``: ids are stable for the life of the file and never
                    reused after a delete, so the grid's ``row_index`` can be a ``row_id``.
                    Display order inside a section is ``(sort_order, row_id)``; sections
                    are in creation order (their lowest ``row_id``), which after an import
                    is the order of the legacy CSV set. Text columns are ``TEXT NOT NULL
                    DEFAULT ''`` (``value`` is text because the plan CSVs are text);
                    ``section`` must be non-empty. A ``(section, subsection, label)`` key
                    may repeat; the last row in display order is the effective one.
``plan_revisions``  one row per snapshot: ``id, created_at, source, note, rows_sha256,
                    row_count``.
``revision_rows``   the retained full copy of ``plan_rows`` (ids included) for each
                    revision, cascade-deleted with it. Retention keeps the newest N
                    revisions (``plan_meta['revision_retention']``, default
                    ``DEFAULT_REVISION_RETENTION``).
``plan_meta``       ``key -> value`` text pairs for plan-level facts.

Revision hash
-------------
``revision()`` hashes the rows' *content and order*, not their ids or raw ``sort_order``
numbers. Sections are taken in code-point order of their name and rows within a section in
display order; each row is serialised as the compact JSON array
``[section, subsection, label, value, units, notes]`` (UTF-8, ``ensure_ascii=False``), one
per line after the header line ``plan_rows/v1``; the digest is SHA-256 hex. So renumbering
``sort_order`` without changing the order, or deleting and re-inserting identical rows
(new ids), leaves the hash unchanged, while editing a field, adding/removing a row or moving
a row changes it.

Schema v2 (WP6.1) adds the flat dataset tables ``holdings_lots``, ``liabilities``,
``hsa_schedule`` and ``target_allocation`` (see ``datasets.py``); they are reached through
``store.holdings``, ``store.liabilities``, ``store.hsa_schedule`` and ``store.target_allocation``.
They are not part of ``plan_rows`` revisions or the revision hash.

Schema v3 (WP6.3a) adds the spending tables ``spending_taxonomy`` and ``spending_aliases``
(same conventions); they are reached through the spending repository ``store.spending``
(``spending_repo.py``: ``store.spending.taxonomy``, ``store.spending.aliases``; the rest of the
spending set is stubbed there until WP6.3b/c). ``store.dataset(name)`` resolves any flat dataset
by its ``csv_exchange`` name (``"holdings"``, ``"spending_taxonomy"`` ...).

Schema v4 (WP6.3b) adds ``spending_budget``, ``spending_budget_lines`` and
``spending_tier_overrides`` (same conventions), reached as ``store.spending.budget``,
``store.spending.budget_lines`` and ``store.spending.tier_overrides``.

Schema v5 (WP6.3c) adds ``spending_rules``, ``spending_category_map`` and
``spending_group_budget`` (same conventions; ``store.spending.rules`` / ``.category_map`` /
``.group_budget``) and ``revision_datasets``, the revision-scoped copy of flat datasets: a
revision taken with ``snapshot_revision(..., datasets={name: rows})`` retains those datasets'
rows beside its ``plan_rows`` copy (``revision_dataset_rows``, ``restore_dataset_from_revision``).
These are the spending recovery copies: sources ``pre-recovery`` (the budget as it was before a
recovery merge) and ``budget-recovery-seed`` (a known-good budget to recover from) are never
pruned by retention (``PROTECTED_REVISION_SOURCES``).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, TypedDict, TypeVar, runtime_checkable

from .. import platform_runtime
from ._base import _SqliteStore
from .datasets import SCHEMA_V2_DDL, SCHEMA_V3_DDL, SCHEMA_V4_DDL, SCHEMA_V5_DDL, FlatDatasetRepository
from .spending_repo import SpendingRepo
from .errors import IntegrityError, NotFoundError, ValidationError

PLAN_APPLICATION_ID = 0x5250504C  # "RPPL"
DEFAULT_REVISION_RETENTION = 20
RETENTION_KEY = "revision_retention"
HASH_HEADER = "plan_rows/v1"
# Revision sources retention never prunes: the spending recovery copies (WP6.3c).
PROTECTED_REVISION_SOURCES = ("pre-recovery", "budget-recovery-seed")

TEXT_FIELDS = ("section", "subsection", "label", "value", "units", "notes")
ROW_FIELDS = (*TEXT_FIELDS, "sort_order")
_ROW_COLUMNS = "row_id, " + ", ".join(ROW_FIELDS)

_SCHEMA_V1 = f"""
PRAGMA application_id = {PLAN_APPLICATION_ID};
CREATE TABLE plan_rows (
    row_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    section     TEXT    NOT NULL CHECK (section <> ''),
    subsection  TEXT    NOT NULL DEFAULT '',
    label       TEXT    NOT NULL DEFAULT '',
    value       TEXT    NOT NULL DEFAULT '',
    units       TEXT    NOT NULL DEFAULT '',
    notes       TEXT    NOT NULL DEFAULT '',
    sort_order  INTEGER NOT NULL
);
CREATE INDEX ix_plan_rows_section_order ON plan_rows (section, sort_order, row_id);
CREATE TABLE plan_revisions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT    NOT NULL,
    source       TEXT    NOT NULL CHECK (source <> ''),
    note         TEXT    NOT NULL DEFAULT '',
    rows_sha256  TEXT    NOT NULL,
    row_count    INTEGER NOT NULL
);
CREATE TABLE revision_rows (
    revision_id INTEGER NOT NULL REFERENCES plan_revisions (id) ON DELETE CASCADE,
    row_id      INTEGER NOT NULL,
    section     TEXT    NOT NULL,
    subsection  TEXT    NOT NULL,
    label       TEXT    NOT NULL,
    value       TEXT    NOT NULL,
    units       TEXT    NOT NULL,
    notes       TEXT    NOT NULL,
    sort_order  INTEGER NOT NULL,
    PRIMARY KEY (revision_id, row_id)
) WITHOUT ROWID;
CREATE TABLE plan_meta (
    key   TEXT PRIMARY KEY CHECK (key <> ''),
    value TEXT NOT NULL
) WITHOUT ROWID;
INSERT INTO plan_meta (key, value) VALUES ('{RETENTION_KEY}', '{DEFAULT_REVISION_RETENTION}');
"""

PLAN_MIGRATIONS: tuple[str, ...] = (_SCHEMA_V1, SCHEMA_V2_DDL, SCHEMA_V3_DDL, SCHEMA_V4_DDL, SCHEMA_V5_DDL)
PLAN_SCHEMA_VERSION = len(PLAN_MIGRATIONS)


_FLAT_DATASET_ATTRS = frozenset({"holdings", "liabilities", "hsa_schedule", "target_allocation"})


# ------------------------------------------------------------------ validation helpers
def _check_text(name: str, value: Any, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{name} must be str, got {type(value).__name__}")
    if not allow_empty and not value:
        raise ValidationError(f"{name} must not be empty")
    return value


def _check_int(name: str, value: Any, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{name} must be int, got {type(value).__name__}")
    if minimum is not None and value < minimum:
        raise ValidationError(f"{name} must be >= {minimum}, got {value}")
    return value


def _check_field(name: str, value: Any) -> Any:
    if name == "sort_order":
        return _check_int(name, value)
    return _check_text(name, value, allow_empty=name != "section")


def hash_rows(rows: Iterable[Mapping[str, Any] | tuple]) -> str:
    """SHA-256 of rows already in canonical order (see module docstring).

    Accepts row dicts or tuples whose first six items are ``TEXT_FIELDS`` in order.
    """
    h = hashlib.sha256()
    h.update(HASH_HEADER.encode("utf-8"))
    for row in rows:
        fields = [row[f] for f in TEXT_FIELDS] if isinstance(row, Mapping) else list(row[:6])
        h.update(b"\n")
        h.update(json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return h.hexdigest()


_PLAN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def validate_plan_id(plan_id: Any) -> str:
    """A plan id is also a directory name: 1-64 of ``[A-Za-z0-9_-]``, starting alphanumeric,
    not a Windows device name."""
    if not isinstance(plan_id, str) or not _PLAN_ID_RE.fullmatch(plan_id) or plan_id.upper() in _WINDOWS_RESERVED:
        raise ValidationError(f"invalid plan id: {plan_id!r}")
    return plan_id


# ------------------------------------------------------------------------- per-plan paths
@dataclass(frozen=True)
class PlanPaths:
    plan_id: str
    outputs_dir: Path
    backups_dir: Path


def plan_paths(plan_id: str, *, base_dir: str | Path | None = None) -> PlanPaths:
    """Per-plan output and backup folders, derived from the plan's registry id.

    ``base_dir`` defaults to ``platform_runtime.workspace_root()`` (which honours the
    workspace env override and the frozen per-user root). Layout::

        <base>/output/plans/<plan_id>/          workbook, HTML, PDF for this plan
        <base>/local_state/plan_backups/<plan_id>/

    Pure derivation: nothing is created on disk.
    """
    validate_plan_id(plan_id)
    base = Path(base_dir) if base_dir is not None else platform_runtime.workspace_root()
    return PlanPaths(
        plan_id=plan_id,
        outputs_dir=base / "output" / "plans" / plan_id,
        backups_dir=base / "local_state" / "plan_backups" / plan_id,
    )


# --------------------------------------------------------------------------------- store
class PlanStore(_SqliteStore):
    """Rows, revisions and meta of one plan file. Open with ``PlanStore.open(path)``.

    Rows are returned as plain dicts with keys ``row_id`` + ``ROW_FIELDS``. Every write is
    atomic; bare calls auto-commit, calls inside ``with store.transaction():`` commit or
    roll back together.
    """

    KIND = "plan"
    APPLICATION_ID = PLAN_APPLICATION_ID
    MIGRATIONS = PLAN_MIGRATIONS

    # ------------------------------------------------------------- flat datasets (WP6.1)
    @property
    def holdings(self) -> FlatDatasetRepository:
        return FlatDatasetRepository(self, "holdings_lots")

    @property
    def liabilities(self) -> FlatDatasetRepository:
        return FlatDatasetRepository(self, "liabilities")

    @property
    def hsa_schedule(self) -> FlatDatasetRepository:
        return FlatDatasetRepository(self, "hsa_schedule")

    @property
    def target_allocation(self) -> FlatDatasetRepository:
        return FlatDatasetRepository(self, "target_allocation")

    # ----------------------------------------------------------- spending set (WP6.3)
    @property
    def spending(self) -> SpendingRepo:
        """The plan's spending set (taxonomy, aliases; budget, rules ... from WP6.3b/c)."""
        return SpendingRepo(self)

    def dataset(self, name: str) -> FlatDatasetRepository:
        """A flat dataset by its ``csv_exchange`` name: ``holdings``, ``liabilities``,
        ``hsa_schedule``, ``target_allocation``, ``spending_<name>`` (``spending_taxonomy`` ->
        ``self.spending.taxonomy``)."""
        if name in _FLAT_DATASET_ATTRS:
            return getattr(self, name)
        if name.startswith("spending_"):
            try:
                return self.spending.dataset(name[len("spending_"):])
            except KeyError:
                pass
        raise KeyError(f"unknown plan dataset {name!r}")

    # ----------------------------------------------------------------------- rows
    def sections(self) -> list[str]:
        """Distinct section names in code-point order."""
        with self._read() as con:
            return [r[0] for r in con.execute("SELECT DISTINCT section FROM plan_rows ORDER BY section")]

    def rows(self, section: str) -> list[dict[str, Any]]:
        """Rows of ``section`` in display order; ``[]`` for an unknown section."""
        _check_text("section", section)
        with self._read() as con:
            cur = con.execute(
                f"SELECT {_ROW_COLUMNS} FROM plan_rows WHERE section = ? ORDER BY sort_order, row_id", (section,)
            )
            return [dict(r) for r in cur]

    def section_order(self) -> list[str]:
        """Section names in display order: by each section's lowest ``row_id`` (creation
        order; after an import, the order of the CSV set). ``sectioned_data`` uses it."""
        with self._read() as con:
            return [r[0] for r in con.execute(
                "SELECT section FROM plan_rows GROUP BY section ORDER BY MIN(row_id)")]

    def all_rows(self) -> list[dict[str, Any]]:
        """Every row in canonical order (sections by name, then display order)."""
        with self._read() as con:
            cur = con.execute(f"SELECT {_ROW_COLUMNS} FROM plan_rows ORDER BY section, sort_order, row_id")
            return [dict(r) for r in cur]

    def get_row(self, row_id: int) -> dict[str, Any]:
        _check_int("row_id", row_id)
        with self._read() as con:
            r = con.execute(f"SELECT {_ROW_COLUMNS} FROM plan_rows WHERE row_id = ?", (row_id,)).fetchone()
        if r is None:
            raise NotFoundError(f"plan row {row_id} not found")
        return dict(r)

    def insert_row(
        self,
        section: str,
        *,
        subsection: str = "",
        label: str = "",
        value: str = "",
        units: str = "",
        notes: str = "",
        sort_order: int | None = None,
    ) -> int:
        """Append a row and return its new, never-reused ``row_id``.

        ``sort_order=None`` places it after the section's current last row
        (``max(sort_order) + 1``, or 0 for a new section).
        """
        fields = {"section": section, "subsection": subsection, "label": label,
                  "value": value, "units": units, "notes": notes}
        for name, val in fields.items():
            _check_field(name, val)
        if sort_order is not None:
            _check_int("sort_order", sort_order)
        with self._write() as con:
            if sort_order is None:
                sort_order = con.execute(
                    "SELECT COALESCE(MAX(sort_order) + 1, 0) FROM plan_rows WHERE section = ?", (section,)
                ).fetchone()[0]
            cur = con.execute(
                f"INSERT INTO plan_rows ({', '.join(ROW_FIELDS)}) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (*fields.values(), sort_order),
            )
            return int(cur.lastrowid)

    def set_row(self, row_id: int, **fields: Any) -> dict[str, Any]:
        """Update some of ``ROW_FIELDS`` on an existing row; return the updated row."""
        _check_int("row_id", row_id)
        if not fields:
            raise ValidationError("set_row needs at least one field")
        unknown = sorted(set(fields) - set(ROW_FIELDS))
        if unknown:
            raise ValidationError(f"unknown plan row field(s): {', '.join(unknown)}")
        for name, val in fields.items():
            _check_field(name, val)
        names = [f for f in ROW_FIELDS if f in fields]
        with self._write() as con:
            cur = con.execute(
                f"UPDATE plan_rows SET {', '.join(f'{n} = ?' for n in names)} WHERE row_id = ?",
                (*(fields[n] for n in names), row_id),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"plan row {row_id} not found")
            return dict(con.execute(f"SELECT {_ROW_COLUMNS} FROM plan_rows WHERE row_id = ?", (row_id,)).fetchone())

    def delete_row(self, row_id: int) -> None:
        _check_int("row_id", row_id)
        with self._write() as con:
            if con.execute("DELETE FROM plan_rows WHERE row_id = ?", (row_id,)).rowcount == 0:
                raise NotFoundError(f"plan row {row_id} not found")

    def clear_rows(self) -> int:
        """Delete every row (ids are not reused); return how many were deleted."""
        with self._write() as con:
            return con.execute("DELETE FROM plan_rows").rowcount

    # ------------------------------------------------------------- keyed access (WP4.1)
    def find_rows(self, section: str, subsection: str, label: str) -> list[dict[str, Any]]:
        """Rows with exactly this ``(section, subsection, label)`` key, in display order.

        Usually zero or one; a key can repeat (the legacy CSV set has such duplicates),
        and then the last row is the effective one (see ``sectioned_data``).
        """
        for name, val in (("section", section), ("subsection", subsection), ("label", label)):
            _check_text(name, val)
        with self._read() as con:
            cur = con.execute(
                f"SELECT {_ROW_COLUMNS} FROM plan_rows WHERE section = ? AND subsection = ? AND label = ? "
                "ORDER BY sort_order, row_id",
                (section, subsection, label),
            )
            return [dict(r) for r in cur]

    def set_value(
        self,
        section: str,
        subsection: str,
        label: str,
        value: str,
        *,
        units: str | None = None,
        notes: str | None = None,
    ) -> int:
        """Write ``value`` under a key and return the row id written.

        Updates the effective row (the last one in display order) when the key exists,
        otherwise appends a new row at the end of the section. ``units`` / ``notes`` are
        written only when given. This is the one keyed write for plan settings (feature
        switches, the plan tier) and for endpoints that address a field by name.
        """
        fields = {"section": section, "subsection": subsection, "label": label, "value": value}
        for name, val in fields.items():
            _check_field(name, val)
        extra = {k: v for k, v in (("units", units), ("notes", notes)) if v is not None}
        for name, val in extra.items():
            _check_text(name, val)
        with self._write():
            existing = self.find_rows(section, subsection, label)
            if existing:
                row_id = existing[-1]["row_id"]
                self.set_row(row_id, value=value, **extra)
                return row_id
            return self.insert_row(section, subsection=subsection, label=label, value=value, **extra)

    def sectioned_data(self) -> dict[str, dict[str, dict[str, str]]]:
        """The engine view: ``{section: {subsection: {label: value}}}``.

        Same read rules and the same key order as the legacy ``data_io.load_csv`` over the
        CSV set the plan was imported from: sections in creation order, rows in display
        order, the last row of a repeated key wins (keeping the key's first position),
        values and keys stripped, rows without a label (or with a ``#`` section) skipped.
        """
        out: dict[str, dict[str, dict[str, str]]] = {}
        with self._read() as con:
            cur = con.execute(
                "SELECT r.section, r.subsection, r.label, r.value FROM plan_rows AS r "
                "JOIN (SELECT section, MIN(row_id) AS first_id FROM plan_rows GROUP BY section) AS f "
                "ON f.section = r.section ORDER BY f.first_id, r.sort_order, r.row_id"
            )
            for section, subsection, label, value in cur:
                sec, sub, lbl = section.strip(), subsection.strip(), label.strip()
                if not sec or sec.startswith("#") or not lbl:
                    continue
                out.setdefault(sec, {}).setdefault(sub, {})[lbl] = value.strip()
        return out

    # ------------------------------------------------------------------ revisions
    def revision(self) -> str:
        """Deterministic SHA-256 of the current rows (content + order; see module docstring)."""
        with self._read() as con:
            cur = con.execute(
                f"SELECT {', '.join(TEXT_FIELDS)} FROM plan_rows ORDER BY section, sort_order, row_id"
            )
            return hash_rows(tuple(r) for r in cur)

    @property
    def revision_retention(self) -> int:
        try:
            return max(1, int(self._meta(RETENTION_KEY) or DEFAULT_REVISION_RETENTION))
        except ValueError:
            return DEFAULT_REVISION_RETENTION

    def set_revision_retention(self, keep: int) -> None:
        """Keep at most ``keep`` (>= 1) revisions; prunes immediately."""
        _check_int("keep", keep, minimum=1)
        with self._write() as con:
            con.execute(
                "INSERT INTO plan_meta (key, value) VALUES (?, ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (RETENTION_KEY, str(keep)),
            )
            self._prune(con, keep)

    def snapshot_revision(
        self, source: str, note: str = "", *, datasets: Mapping[str, Iterable[Mapping[str, Any]]] | None = None
    ) -> int:
        """Copy the current rows into a new revision and return its id; prunes to retention.

        ``datasets`` (``{flat dataset name: rows}``) is retained with the revision as its
        revision-scoped dataset copies (recovery copies); see ``revision_dataset_rows``."""
        _check_text("source", source, allow_empty=False)
        _check_text("note", note)
        with self._write() as con:
            rev_id = self._snapshot(con, source, note, prune=False)
            for name, rows in (datasets or {}).items():
                self._store_revision_dataset(con, rev_id, name, rows)
            self._prune(con, self.revision_retention)
            return rev_id

    def revision_dataset_rows(self, revision_id: int, dataset: str) -> list[dict[str, str]]:
        """The rows of flat dataset ``dataset`` retained with a revision (``[]`` when it kept none)."""
        _check_int("revision_id", revision_id)
        with self._read() as con:
            self._revision_header(con, revision_id)
            return [
                json.loads(r[0])
                for r in con.execute(
                    "SELECT row FROM revision_datasets WHERE revision_id = ? AND dataset = ? ORDER BY position",
                    (revision_id, dataset),
                )
            ]

    def latest_revision(self, source: str) -> dict[str, Any] | None:
        """The newest revision header of ``source`` (``None`` when there is none)."""
        _check_text("source", source, allow_empty=False)
        with self._read() as con:
            r = con.execute(
                "SELECT id, created_at, source, note, rows_sha256, row_count FROM plan_revisions "
                "WHERE source = ? ORDER BY id DESC LIMIT 1",
                (source,),
            ).fetchone()
        return None if r is None else dict(r)

    def restore_dataset_from_revision(self, revision_id: int, dataset: str) -> int:
        """Replace the live flat dataset ``dataset`` with the rows retained by a revision;
        returns the rows written (``NotFoundError`` when the revision kept no such dataset)."""
        rows = self.revision_dataset_rows(revision_id, dataset)
        if not rows:
            raise NotFoundError(f"plan revision {revision_id} holds no {dataset!r} copy")
        return self.dataset(dataset).replace_all(rows)

    def discard_revisions(self, source: str) -> int:
        """Delete every revision of ``source`` (and its copies); returns how many."""
        _check_text("source", source, allow_empty=False)
        with self._write() as con:
            return con.execute("DELETE FROM plan_revisions WHERE source = ?", (source,)).rowcount

    @staticmethod
    def _store_revision_dataset(con: Any, revision_id: int, name: str, rows: Iterable[Mapping[str, Any]]) -> None:
        _check_text("dataset", name, allow_empty=False)
        con.executemany(
            "INSERT INTO revision_datasets (revision_id, dataset, position, row) VALUES (?, ?, ?, ?)",
            [
                (revision_id, name, i, json.dumps({str(k): ("" if v is None else str(v)) for k, v in r.items()}, ensure_ascii=False))
                for i, r in enumerate(rows)
            ],
        )

    def list_revisions(self) -> list[dict[str, Any]]:
        """Revision headers, newest first."""
        with self._read() as con:
            cur = con.execute(
                "SELECT id, created_at, source, note, rows_sha256, row_count FROM plan_revisions ORDER BY id DESC"
            )
            return [dict(r) for r in cur]

    def revision_rows(self, revision_id: int) -> list[dict[str, Any]]:
        """The retained rows of a revision, in canonical order (for compare / preview)."""
        _check_int("revision_id", revision_id)
        with self._read() as con:
            self._revision_header(con, revision_id)
            cur = con.execute(
                f"SELECT {_ROW_COLUMNS} FROM revision_rows WHERE revision_id = ? "
                "ORDER BY section, sort_order, row_id",
                (revision_id,),
            )
            return [dict(r) for r in cur]

    def restore_revision(self, revision_id: int, *, backup: bool = True) -> int | None:
        """Replace all plan rows with a revision's copy (original row ids kept).

        With ``backup=True`` (default) the current rows are first saved as a
        ``source='pre-restore'`` revision, whose id is returned. The retained copy is
        verified against its recorded hash and count first (``IntegrityError`` on mismatch);
        the whole operation is one transaction.
        """
        _check_int("revision_id", revision_id)
        with self._write() as con:
            header = self._revision_header(con, revision_id)
            rows = [
                tuple(r)
                for r in con.execute(
                    f"SELECT {_ROW_COLUMNS} FROM revision_rows WHERE revision_id = ? "
                    "ORDER BY section, sort_order, row_id",
                    (revision_id,),
                )
            ]
            if len(rows) != header["row_count"] or hash_rows(r[1:] for r in rows) != header["rows_sha256"]:
                raise IntegrityError(f"revision {revision_id} copy does not match its recorded hash")
            backup_id = (
                self._snapshot(con, "pre-restore", f"before restoring revision {revision_id}", prune=False)
                if backup
                else None
            )
            con.execute("DELETE FROM plan_rows")
            con.executemany(f"INSERT INTO plan_rows ({_ROW_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
            self._prune(con, self.revision_retention, protect=revision_id)
            return backup_id

    # ----------------------------------------------------------------------- meta
    def get_meta(self, key: str, default: str | None = None) -> str | None:
        _check_text("key", key, allow_empty=False)
        value = self._meta(key)
        return default if value is None else value

    def set_meta(self, key: str, value: str) -> None:
        _check_text("key", key, allow_empty=False)
        _check_text("value", value)
        if key == RETENTION_KEY:
            raise ValidationError(f"{RETENTION_KEY!r} is set through set_revision_retention()")
        with self._write() as con:
            con.execute(
                "INSERT INTO plan_meta (key, value) VALUES (?, ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    # ------------------------------------------------------------------ internals
    def _meta(self, key: str) -> str | None:
        with self._read() as con:
            r = con.execute("SELECT value FROM plan_meta WHERE key = ?", (key,)).fetchone()
        return None if r is None else r[0]

    @staticmethod
    def _revision_header(con: Any, revision_id: int) -> dict[str, Any]:
        r = con.execute(
            "SELECT id, created_at, source, note, rows_sha256, row_count FROM plan_revisions WHERE id = ?",
            (revision_id,),
        ).fetchone()
        if r is None:
            raise NotFoundError(f"plan revision {revision_id} not found")
        return dict(r)

    def _snapshot(self, con: Any, source: str, note: str, *, prune: bool = True) -> int:
        rows = [
            tuple(r)
            for r in con.execute(f"SELECT {_ROW_COLUMNS} FROM plan_rows ORDER BY section, sort_order, row_id")
        ]
        cur = con.execute(
            "INSERT INTO plan_revisions (created_at, source, note, rows_sha256, row_count) VALUES (?, ?, ?, ?, ?)",
            (self._clock(), source, note, hash_rows(r[1:] for r in rows), len(rows)),
        )
        rev_id = int(cur.lastrowid)
        con.executemany(
            f"INSERT INTO revision_rows (revision_id, {_ROW_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(rev_id, *r) for r in rows],
        )
        if prune:
            self._prune(con, self.revision_retention)
        return rev_id

    @staticmethod
    def _prune(con: Any, keep: int, protect: int | None = None) -> None:
        """Keep the newest ``keep`` revisions (and ``protect``, e.g. the one just restored)."""
        con.execute(
            "DELETE FROM plan_revisions WHERE id NOT IN (SELECT id FROM plan_revisions ORDER BY id DESC LIMIT ?) "
            "AND id IS NOT ? AND source NOT IN (?, ?)",
            (keep, protect, *PROTECTED_REVISION_SOURCES),
        )


# ------------------------------------------------- typed dataset repositories (P4 stubs)
RowT = TypeVar("RowT")


@runtime_checkable
class DatasetRepository(Protocol[RowT]):
    """Interface every typed plan dataset will implement (tables arrive in P4).

    ``rows()`` returns the dataset's rows in its natural order; ``replace_all()``
    atomically replaces the whole dataset and returns the number of rows written.
    """

    def rows(self) -> list[RowT]: ...

    def replace_all(self, rows: Iterable[RowT]) -> int: ...


class HoldingLot(TypedDict):
    """One ``holdings_lots`` row: the legacy CSV columns, as entered (text)."""

    account: str
    symbol: str
    purchase_date: str
    shares: str
    purchase_price: str
    lot_type: str
    note: str


# Rows of the other datasets are plain mappings of CSV column name to text value.
LiabilityRow = dict[str, Any]
HsaScheduleRow = dict[str, Any]
TargetAllocationRow = dict[str, Any]


@runtime_checkable
class HoldingsLotsRepository(DatasetRepository[HoldingLot], Protocol):
    """``holdings_lots`` (replaces ``client_holdings.csv``)."""


@runtime_checkable
class LiabilitiesRepository(DatasetRepository[LiabilityRow], Protocol):
    """``liabilities`` (replaces ``client_liabilities.csv``)."""


@runtime_checkable
class HsaScheduleRepository(DatasetRepository[HsaScheduleRow], Protocol):
    """``hsa_schedule`` (replaces ``client_hsa_schedule.csv``; the build stops writing it)."""


@runtime_checkable
class TargetAllocationRepository(DatasetRepository[TargetAllocationRow], Protocol):
    """``target_allocation`` (replaces ``target_allocation.csv``)."""


__all__ = [
    "DEFAULT_REVISION_RETENTION",
    "DatasetRepository",
    "HoldingLot",
    "HoldingsLotsRepository",
    "HsaScheduleRepository",
    "LiabilitiesRepository",
    "PLAN_APPLICATION_ID",
    "PLAN_MIGRATIONS",
    "PLAN_SCHEMA_VERSION",
    "PlanPaths",
    "PlanStore",
    "ROW_FIELDS",
    "TargetAllocationRepository",
    "hash_rows",
    "plan_paths",
    "validate_plan_id",
]
