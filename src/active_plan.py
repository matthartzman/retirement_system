"""The active plan file: where the engine, the build and the server read plan rows (WP4.2).

Design F sections 5A and 7. Until the plan registry is wired (WP8.4: ``app.db``
``plan_registry`` / ``active_plan``), a workspace has exactly one plan and its file is
``<workspace>/plan.rpx`` (``PLAN_FILE_NAME``; the same place ``tests/plan_fixture.make_plan``
builds it). ``RETIREMENT_SYSTEM_PLAN_DB`` (``PLAN_DB_ENV``) overrides the path; the server
sets it for the build subprocess so the build reads the same file the server does.
WP8.4 replaces the body of :func:`active_plan_path` with the registry lookup.

Readers use :func:`active_plan_data` (the engine view, ``PlanStore.sectioned_data()``).

Transition until WP4.4 / 4.5 switch the remaining writers: ``plan_rows`` is the plan's
truth, and the plan CSV set in ``input/`` is a working copy kept equal to it for the writers
that still edit CSV. One mechanism, two directions:

* the remaining CSV writers end with ``app_core._sync_config_backends()``, which calls
  :func:`sync_active_plan_from_csv` (CSV set -> rows; ``csv_exchange.sync_plan_rows`` keeps
  a row's id while its key survives);
* the row-store writers (the grid, ``/api/plan/forms``; WP4.3) edit through
  :func:`edit_active_plan`, which writes every key they touch back into the CSV set
  (``csv_exchange.write_back_rows``) in the same transaction, so the next bridge run reads
  their edit back instead of overwriting it, and a CSV writer that reads its file sees it.

A plan file with no rows is filled from the CSV set on first read, as the old SQLite
snapshot was.
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from . import platform_runtime
from .plan_label_rules import dropped_at_load
from .csv_exchange import PlanCsvRow, read_plan_csv_set, sync_plan_rows, write_back_rows
from .stores import PlanStore

PLAN_DB_ENV = "RETIREMENT_SYSTEM_PLAN_DB"
PLAN_FILE_NAME = "plan.rpx"

SectionedData = dict[str, dict[str, dict[str, str]]]


def active_plan_path() -> Path:
    """The active plan file: ``$RETIREMENT_SYSTEM_PLAN_DB`` or ``<workspace>/plan.rpx``.

    A relative override is taken against the workspace root. Resolved on every call
    (the workspace root can be redirected after import, e.g. by the test harness).
    """
    raw = str(os.environ.get(PLAN_DB_ENV, "") or "").strip()
    root = platform_runtime.workspace_root()
    if raw:
        p = Path(raw).expanduser()
        return p if p.is_absolute() else root / p
    return root / PLAN_FILE_NAME


def active_plan_store(*, readonly: bool = False) -> PlanStore:
    """Open the active plan (created when missing unless ``readonly``). Close it after use."""
    return PlanStore.open(active_plan_path(), create=not readonly, readonly=readonly)


def _engine_rows(rows: list[PlanCsvRow]) -> list[PlanCsvRow]:
    """The CSV rows the plan keeps: the old loader's two load-time drops still apply."""
    return [r for r in rows if not dropped_at_load(r.section, r.subsection, r.label)]


class EmptyPlanCsvSet(FileNotFoundError):
    """The plan CSV set holds no plan rows (folder or files missing, or every file empty).

    Raised instead of syncing: an empty set must never wipe the plan's rows (the old
    ``import_csv_to_sqlite`` raised ``FileNotFoundError`` and kept its snapshot)."""


@dataclass
class PlanSyncResult:
    data: SectionedData          # the plan's sectioned view after the sync
    texts: dict[str, str]        # file name -> text of each plan CSV read
    counts: dict[str, int]       # csv_exchange.sync_plan_rows counts
    files_read: list[str]
    rows_by_file: dict[str, int]  # file name -> data rows the file holds


def sync_active_plan_from_csv(input_dir: str | Path) -> PlanSyncResult:
    """Make the active plan's rows equal the plan CSV set in ``input_dir`` (WP4.2 bridge).

    The one place the CSV writers' edits reach ``plan_rows`` until those writers write the
    rows themselves (WP4.4-4.5); then this function, :func:`edit_active_plan`'s write-back
    and their callers are deleted (P3.5).
    Raises :class:`EmptyPlanCsvSet`, leaving the plan as it is, when the set holds no rows.
    """
    parsed = read_plan_csv_set(input_dir)
    rows = _engine_rows(parsed.rows)
    if not rows:
        raise EmptyPlanCsvSet(f"no plan CSV rows found in {input_dir}; the plan was left unchanged")
    with active_plan_store() as store:
        counts = sync_plan_rows(store, rows)
        data = store.sectioned_data()
    return PlanSyncResult(data=data, texts=dict(parsed.texts), counts=counts,
                          files_read=list(parsed.report.files_read), rows_by_file=dict(parsed.rows_by_file))


def refresh_active_plan(input_dir: str | Path) -> PlanSyncResult | None:
    """Run the bridge (:func:`sync_active_plan_from_csv`) before reading or editing the rows,
    so a CSV write not yet synced (a writer called with ``sync`` off, the GET-time
    backfills) is in the rows. ``None`` when the CSV set holds no rows (the rows stay)."""
    try:
        return sync_active_plan_from_csv(input_dir)
    except EmptyPlanCsvSet:
        return None


_EDIT_LOCK = threading.RLock()

Key = tuple[str, str, str]


def _row_fields(rows: list[dict[str, Any]]) -> dict[Key, tuple[str, str, str]]:
    return {(r["section"], r["subsection"], r["label"]): (r["value"], r["units"], r["notes"]) for r in rows}


@contextmanager
def edit_active_plan(input_dir: str | Path, write_file: Callable[[str, str], Any]) -> Iterator[PlanStore]:
    """Edit the active plan's rows in one transaction; the row-store writers' one entry (WP4.3).

    1. :func:`refresh_active_plan`: the rows equal the CSV set before the edit;
    2. yields the open store inside ``transaction()``; the caller edits by ``row_id`` or key
       (an exception rolls everything back and propagates);
    3. before the commit, every key whose row was set, inserted or deleted is written back
       into the CSV set (``csv_exchange.write_back_rows``) through ``write_file(name, text)``
       (the server's plan-data file writer, which also keeps ``client_files`` current); a
       write-back that would not read back as the rows raises ``PlanCsvError`` and rolls the
       edit back instead of letting the next bridge run lose it;
    4. after the commit, the bridge runs again, so ``write_file``'s own rules (canonical Roth
       values, protected retirement dates) reach the rows.

    With no CSV set (nothing to refresh from) the whole plan is written out. Serialized in
    this process by a lock. Read the result through :func:`active_plan_store` afterwards.
    """
    with _EDIT_LOCK:
        synced = refresh_active_plan(input_dir)
        if synced is not None:
            texts = synced.texts
        else:
            texts = read_plan_csv_set(input_dir).texts if Path(input_dir).is_dir() else {}
        with active_plan_store() as store:
            before = _row_fields(store.all_rows())
            with store.transaction():
                yield store
                after_rows = store.all_rows()
                after = _row_fields(after_rows)
                touched = set(after) if synced is None else {
                    k for k in set(before) | set(after) if before.get(k) != after.get(k)}
                if touched:
                    for name, text in write_back_rows(texts, after_rows, touched).items():
                        write_file(name, text)
        if touched:
            refresh_active_plan(input_dir)


def active_plan_data(bootstrap_input_dir: str | Path | None = None) -> SectionedData:
    """The engine view of the active plan (``PlanStore.sectioned_data()``).

    When the plan has no rows yet and ``bootstrap_input_dir`` holds a plan CSV set, the
    plan is filled from it first (the first run after an upgrade, or a fresh workspace).
    """
    with active_plan_store() as store:
        if store.section_order() or bootstrap_input_dir is None:
            return store.sectioned_data()
    if not Path(bootstrap_input_dir).is_dir():
        return {}
    try:
        return sync_active_plan_from_csv(bootstrap_input_dir).data
    except EmptyPlanCsvSet:
        return {}


def peek_plan_data(fallback_input_dir: str | Path | None = None) -> SectionedData:
    """The engine view without touching disk: never creates or writes the plan file.

    Reads the active plan when it exists and has rows; otherwise (no plan file yet, or
    one not yet filled) the plan CSV set in ``fallback_input_dir`` is read in memory, so a
    read before the first bootstrap sees the same values the bootstrap will store.
    """
    path = active_plan_path()
    if path.is_file():
        try:
            with PlanStore.open(path, create=False) as store:
                data = store.sectioned_data()
            if data:
                return data
        except LookupError:  # stores.NotFoundError: not an initialised plan file
            pass
    if fallback_input_dir is None or not Path(fallback_input_dir).is_dir():
        return {}
    out: SectionedData = {}
    for row in _engine_rows(read_plan_csv_set(fallback_input_dir).rows):
        out.setdefault(row.section, {}).setdefault(row.subsection, {})[row.label] = row.value
    return out


def plan_db_env(env: dict[str, Any]) -> dict[str, Any]:
    """Set ``PLAN_DB_ENV`` in a subprocess environment to the active plan file."""
    env[PLAN_DB_ENV] = str(active_plan_path())
    return env
