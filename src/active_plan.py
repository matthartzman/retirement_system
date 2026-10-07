"""The active plan file: where the engine, the build and the server read plan rows (WP4.2).

Design F sections 5A and 7. Until the plan registry is wired (WP8.4: ``app.db``
``plan_registry`` / ``active_plan``), a workspace has exactly one plan and its file is
``<workspace>/plan.rpx`` (``PLAN_FILE_NAME``; the same place ``tests/plan_fixture.make_plan``
builds it). ``RETIREMENT_SYSTEM_PLAN_DB`` (``PLAN_DB_ENV``) overrides the path; the server
sets it for the build subprocess so the build reads the same file the server does.
WP8.4 replaces the body of :func:`active_plan_path` with the registry lookup.

Readers use :func:`active_plan_data` (the engine view, ``PlanStore.sectioned_data()``).

Transition until WP4.3 / 4.4 / 4.5 switch the writers: the plan CSV set in ``input/`` is
still what the writers edit. Every CSV writer ends with ``app_core._sync_config_backends()``,
which calls :func:`sync_active_plan_from_csv`, so the plan rows follow each write
(``csv_exchange.sync_plan_rows`` keeps a row's id while its key survives). A plan file with
no rows is filled from the CSV set on first read, as the old SQLite snapshot was.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import platform_runtime
from .csv_exchange import PlanCsvRow, read_plan_csv_set, sync_plan_rows
from .stores import PlanStore

PLAN_DB_ENV = "RETIREMENT_SYSTEM_PLAN_DB"
PLAN_FILE_NAME = "plan.rpx"

SectionedData = dict[str, dict[str, dict[str, str]]]

# The legacy loader (config_backend.load_csv) dropped these at every load: the Sell Home
# scenario once carried its own copy of the home's value and basis; the current model
# reads them from Other Assets. The CSV set can still hold them, so the sync drops them
# (conversion step C3 drops them once for good).
RETIRED_SCENARIO_HOME_LABELS = frozenset({
    "home_sale_price", "home_basis", "home_value", "house_value", "value_as_of_plan_start",
    "current_home_value", "current_value", "market_value",
})


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
    return [
        r for r in rows
        if r.label.lower() != "label"
        and not (r.section == "Scenarios" and r.subsection == "Sell Home" and r.label in RETIRED_SCENARIO_HOME_LABELS)
    ]


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
    rows_by_file: dict[str, int]  # file name -> number of plan rows it contributed


def sync_active_plan_from_csv(input_dir: str | Path) -> PlanSyncResult:
    """Make the active plan's rows equal the plan CSV set in ``input_dir`` (WP4.2 bridge).

    The one place the CSV writers' edits reach ``plan_rows`` until those writers write the
    rows themselves (WP4.3-4.5); then this function and its callers are deleted.
    Raises :class:`EmptyPlanCsvSet`, leaving the plan as it is, when the set holds no rows.
    """
    parsed = read_plan_csv_set(input_dir)
    rows = _engine_rows(parsed.rows)
    if not rows:
        raise EmptyPlanCsvSet(f"no plan CSV rows found in {input_dir}; the plan was left unchanged")
    rows_by_file: dict[str, int] = {}
    for row in parsed.rows:
        rows_by_file[row.source_file] = rows_by_file.get(row.source_file, 0) + 1
    with active_plan_store() as store:
        counts = sync_plan_rows(store, rows)
        data = store.sectioned_data()
    return PlanSyncResult(data=data, texts=dict(parsed.texts), counts=counts,
                          files_read=list(parsed.report.files_read), rows_by_file=rows_by_file)


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
