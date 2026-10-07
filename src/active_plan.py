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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from . import platform_runtime
from .plan_label_rules import dropped_at_load
from .csv_exchange import (PlanCsvError, PlanCsvRow, plan_csv_set_fingerprint, read_plan_csv_set,
                           sync_plan_rows, write_back_rows)
from .csv_exchange.plan_csv import Key
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


# Serializes the bridge and the row-store edits in this process (the server is threaded);
# across processes the plan file's write lock does (each holds a transaction while it reads
# the CSV set and writes the rows, so no run can store a CSV set read before another's write).
_PLAN_LOCK = threading.RLock()

# What the last bridge run left in sync, per (plan file, CSV folder): (CSV set fingerprint,
# plan revision). A read whose CSV set and plan both still match needs no bridge run, so no
# write lock. Written and read under _PLAN_LOCK; any other change to either side (another
# process, a CSV writer, a swapped plan file) differs from it and runs the bridge.
_SYNCED: dict[tuple[str, str], tuple[str, str]] = {}


def _synced_key(input_dir: str | Path) -> tuple[str, str]:
    return (str(active_plan_path()), str(Path(input_dir).resolve()))


def _pull(store: PlanStore, input_dir: str | Path) -> PlanSyncResult:
    """The bridge on an open store; call inside ``store.transaction()``."""
    fingerprint = plan_csv_set_fingerprint(input_dir)  # before the read: a later change differs
    parsed = read_plan_csv_set(input_dir)
    rows = _engine_rows(parsed.rows)
    if not rows:
        raise EmptyPlanCsvSet(f"no plan CSV rows found in {input_dir}; the plan was left unchanged")
    counts = sync_plan_rows(store, rows)
    _SYNCED[_synced_key(input_dir)] = (fingerprint, store.revision())
    return PlanSyncResult(data=store.sectioned_data(), texts=dict(parsed.texts), counts=counts,
                          files_read=list(parsed.report.files_read), rows_by_file=dict(parsed.rows_by_file))


def sync_active_plan_from_csv(input_dir: str | Path) -> PlanSyncResult:
    """Make the active plan's rows equal the plan CSV set in ``input_dir`` (WP4.2 bridge).

    The one place the CSV writers' edits reach ``plan_rows`` until those writers write the
    rows themselves (WP4.4-4.5); then this function, :func:`edit_active_plan`'s write-back
    and their callers are deleted (P3.5). The CSV set is read inside the rows transaction.
    Raises :class:`EmptyPlanCsvSet`, leaving the plan as it is, when the set holds no rows.
    """
    with _PLAN_LOCK, active_plan_store() as store, store.transaction():
        return _pull(store, input_dir)


def _in_sync(input_dir: str | Path) -> bool:
    """True when neither the CSV set nor the plan changed since the last bridge run (no lock
    on the plan file: a read-only open)."""
    remembered = _SYNCED.get(_synced_key(input_dir))
    if remembered is None or not active_plan_path().is_file():
        return False
    if plan_csv_set_fingerprint(input_dir) != remembered[0]:
        return False
    try:
        with active_plan_store(readonly=True) as store:
            return store.revision() == remembered[1]
    except LookupError:  # not an initialised plan file
        return False


def refresh_active_plan(input_dir: str | Path) -> str:
    """Run the bridge (:func:`sync_active_plan_from_csv`) before reading the rows, so a CSV
    write not yet synced (a writer called with ``sync`` off, the GET-time backfills) is in
    the rows. Nothing runs, and the plan file's write lock is not taken, when the CSV set
    and the plan are as the last run left them.

    A read must not fail because the CSV set is unusable: with no rows in the set, or a part
    file that does not parse (``PlanCsvError``), the rows already stored are served and the
    returned warning says why ("" when the bridge ran or was not needed). Only an edit
    (:func:`edit_active_plan`) needs the CSV set and refuses then.
    """
    with _PLAN_LOCK:
        if _in_sync(input_dir):
            return ""
        try:
            sync_active_plan_from_csv(input_dir)
        except EmptyPlanCsvSet:
            return ""
        except PlanCsvError as exc:
            return f"The plan CSV files could not be read; the stored plan rows are shown: {exc}"
        return ""


@dataclass
class PlanEdit:
    """What :func:`edit_active_plan` yields: the open store to edit; after the block,
    ``revision`` is the plan's revision, ``touched`` the keys written back and
    ``final_values`` every key's value as the plan holds it once the edit is complete (the
    file writer's own rules can differ from what the caller set)."""
    store: PlanStore
    revision: str = ""
    touched: frozenset[Key] = frozenset()
    final_values: dict[Key, str] = field(default_factory=dict)


def _row_fields(rows: list[dict[str, Any]]) -> dict[Key, tuple[str, str, str]]:
    return {(r["section"], r["subsection"], r["label"]): (r["value"], r["units"], r["notes"]) for r in rows}


@contextmanager
def edit_active_plan(input_dir: str | Path, write_file: Callable[[str, str], Any],
                     restore_file: Callable[[str, str], Any] | None = None) -> Iterator[PlanEdit]:
    """Edit the active plan's rows in one transaction; the row-store writers' one entry (WP4.3).

    All in one ``transaction()`` on the plan file:

    1. the bridge: the rows equal the CSV set before the edit (a CSV writer may not have
       synced yet). A part file that does not parse fails the edit here (``PlanCsvError``);
       the edit needs the CSV set to write back into;
    2. yields a :class:`PlanEdit`; the caller edits ``edit.store`` by ``row_id`` or key (an
       exception rolls everything back and propagates);
    3. the new text of every changed CSV file is computed first (``csv_exchange.write_back_rows``,
       pure; a result that would not read back as the rows raises ``PlanCsvError`` before
       anything is written), then written through ``write_file(name, text)`` (the server's
       plan-data file writer, which also keeps ``client_files`` current);
    4. the bridge again, so ``write_file``'s own rules (canonical Roth values, protected
       retirement dates) reach the rows.

    Failure is safe: when anything after the first file write fails (a write, the second
    bridge run, the commit), the previous text of every file written is put back through
    ``restore_file`` (default ``write_file``; a file the edit created is removed) and the rows
    roll back, so a failed edit leaves neither the rows nor the CSV set changed. The restore is
    best effort (a restore that itself fails is skipped and the original error propagates).

    With no CSV set (nothing to refresh from) the whole plan is written out. After the
    block, ``PlanEdit.revision`` is the plan's revision.
    """
    restore = restore_file or write_file
    originals: dict[str, str] = {}
    written: list[list[Any]] = []   # [file name, what write_file returned], in write order

    def put_back() -> None:
        while written:
            name, result = written.pop()
            try:
                if name in originals:
                    restore(name, originals[name])
                else:  # a file the edit created
                    (result if isinstance(result, Path) else Path(input_dir) / name).unlink(missing_ok=True)
            except Exception:
                pass  # best effort; the original error is what the caller sees

    with _PLAN_LOCK, active_plan_store() as store:
        edit = PlanEdit(store)
        try:
            with store.transaction():
                try:
                    texts = _pull(store, input_dir).texts
                    full = False
                except EmptyPlanCsvSet:
                    texts = read_plan_csv_set(input_dir).texts if Path(input_dir).is_dir() else {}
                    full = True
                originals.update(texts)
                before = _row_fields(store.all_rows())
                try:
                    yield edit
                    after_rows = store.all_rows()
                    after = _row_fields(after_rows)
                    touched = set(after) if full else {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
                    if touched:
                        new_texts = write_back_rows(texts, after_rows, touched)  # pure; validated read-back
                        for name, text in new_texts.items():
                            written.append(entry := [name, None])  # before the write: a failing write may leave the file
                            entry[1] = write_file(name, text)
                        try:
                            _pull(store, input_dir)
                        except EmptyPlanCsvSet:
                            pass  # the edit removed every row; the rows are empty too
                except BaseException:
                    put_back()
                    _SYNCED.pop(_synced_key(input_dir), None)
                    raise
                edit.final_values = {(r["section"], r["subsection"], r["label"]): r["value"] for r in store.all_rows()}
        except BaseException:
            put_back()  # a commit that failed after the files were written
            _SYNCED.pop(_synced_key(input_dir), None)
            raise
        edit.touched = frozenset(touched)
        edit.revision = store.revision()


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
