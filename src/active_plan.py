"""The active plan file: where the engine, the build and the server read and edit plan rows.

Design F sections 5A and 7. Until the plan registry is wired (WP8.4: ``app.db``
``plan_registry`` / ``active_plan``), a workspace has exactly one plan and its file is
``<workspace>/plan.rpx`` (``PLAN_FILE_NAME``; the same place ``tests/plan_fixture.make_plan``
builds it). ``RETIREMENT_SYSTEM_PLAN_DB`` (``PLAN_DB_ENV``) overrides the path; the server
sets it for the build subprocess so the build reads the same file the server does.
WP8.4 replaces the body of :func:`active_plan_path` with the registry lookup.

``plan_rows`` is the only store of the sectioned plan data (WP4.5 deleted the CSV working
copy, its bridge and the JSON/YAML mirrors). Two entries:

* readers use :func:`active_plan_data` (the engine view, ``PlanStore.sectioned_data()``) or
  open the store with :func:`active_plan_store`;
* writers edit through :func:`edit_active_plan`: one transaction on the plan file, the Roth
  controls made canonical and the protected retirement dates kept before it commits.
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from . import platform_runtime
from .roth_ui_build_guard import canonicalize_roth_rows
from .stores import PlanStore

PLAN_DB_ENV = "RETIREMENT_SYSTEM_PLAN_DB"
PLAN_FILE_NAME = "plan.rpx"

SectionedData = dict[str, dict[str, dict[str, str]]]
Key = tuple[str, str, str]  # (section, subsection, label)

# Easy-to-lose fields: a save that blanks one of these keeps the value the plan already holds
# (a blank incoming value never erases a retirement date; entering another value replaces it).
PROTECTED_PLAN_KEYS: frozenset[Key] = frozenset({
    ("Household", "", "member_1_retirement_date"),
    ("Household", "", "member_2_retirement_date"),
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


# Serializes the row edits in this process (the server is threaded); across processes the
# plan file's write lock does (``store.transaction()`` holds it from the first read).
_PLAN_LOCK = threading.RLock()


@dataclass
class PlanEdit:
    """What :func:`edit_active_plan` yields: the open store to edit; after the block,
    ``revision`` is the plan's revision and ``final_values`` every key's value as the plan
    holds it once the edit is complete (the plan's own rules can differ from what the
    caller set: canonical Roth values, protected retirement dates)."""
    store: PlanStore
    revision: str = ""
    final_values: dict[Key, str] = field(default_factory=dict)


def _protected_values(store: PlanStore) -> dict[Key, tuple[int, str]]:
    out: dict[Key, tuple[int, str]] = {}
    for section, subsection, label in PROTECTED_PLAN_KEYS:
        for row in store.find_rows(section, subsection, label):
            if str(row["value"]).strip():
                out[(section, subsection, label)] = (row["row_id"], row["value"])
    return out


def _keep_protected_values(store: PlanStore, before: dict[Key, tuple[int, str]]) -> None:
    """Put a protected value back when the edit blanked it (a deleted row stays deleted)."""
    for key, (_row_id, value) in before.items():
        rows = store.find_rows(*key)
        if rows and not str(rows[-1]["value"]).strip():
            store.set_row(rows[-1]["row_id"], value=value)


@contextmanager
def edit_active_plan(*, protect_values: bool = True) -> Iterator[PlanEdit]:
    """Edit the active plan's rows in one transaction; every row writer's one entry.

    Yields a :class:`PlanEdit`; the caller edits ``edit.store`` by ``row_id`` or key (an
    exception rolls everything back and propagates). Before the commit the Roth controls are
    made canonical (``roth_ui_build_guard``) and, unless ``protect_values`` is off (a blank
    plan, which clears them on purpose), a protected retirement date the edit blanked is put
    back. After the block ``PlanEdit.revision`` is the plan's revision.
    """
    with _PLAN_LOCK, active_plan_store() as store:
        edit = PlanEdit(store)
        with store.transaction():
            before = _protected_values(store) if protect_values else {}
            yield edit
            canonicalize_roth_rows(store)  # a Roth control is stored canonical (the guard)
            if before:
                _keep_protected_values(store, before)
            edit.final_values = {(r["section"], r["subsection"], r["label"]): r["value"] for r in store.all_rows()}
        edit.revision = store.revision()


def active_plan_data() -> SectionedData:
    """The engine view of the active plan (``PlanStore.sectioned_data()``); ``{}`` for a plan
    with no rows."""
    with active_plan_store() as store:
        return store.sectioned_data()


def peek_plan_data() -> SectionedData:
    """The engine view without touching disk: never creates or writes the plan file
    (``{}`` when there is no plan file yet or it is not an initialised plan)."""
    path = active_plan_path()
    if not path.is_file():
        return {}
    try:
        with PlanStore.open(path, create=False) as store:
            return store.sectioned_data()
    except LookupError:  # stores.NotFoundError: not an initialised plan file
        return {}


def plan_db_env(env: dict[str, Any]) -> dict[str, Any]:
    """Set ``PLAN_DB_ENV`` in a subprocess environment to the active plan file."""
    env[PLAN_DB_ENV] = str(active_plan_path())
    return env
