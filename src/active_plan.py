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
  controls made canonical before it commits (and, for the grid and the forms, the protected
  retirement dates kept).
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

# Easy-to-lose fields: a grid or form save that blanks one of these keeps the value the plan
# already holds (a blank incoming value never erases a retirement date; entering another value
# replaces it). This is the retired file writer's rule (``_merge_protected_client_data_values``),
# which only guarded the saves of the household's own data: the config grid and the forms
# (Member 1 / Member 2 pages). It never applied to Start New Plan, the demo swap, Save As / Load /
# restore or an import, nor to the strategy endpoints and the UI-row backfill. The same scoping
# holds here: protection is opt-in (``edit_active_plan(protect_values=True)``) and only the grid
# and the forms ask for it (``app_core._edit_active_plan_protected``). A date that is not blank in
# the plan is the only thing protected; a household with no Member 2 starts blank and stays editable,
# and a row the edit deletes stays deleted.
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
def edit_active_plan(*, protect_values: bool = False) -> Iterator[PlanEdit]:
    """Edit the active plan's rows in one transaction; every row writer's one entry.

    Yields a :class:`PlanEdit`; the caller edits ``edit.store`` by ``row_id`` or key (an
    exception rolls everything back and propagates). Before the commit the Roth controls are
    made canonical (``roth_ui_build_guard``) and, when ``protect_values`` is on (the config grid
    and the forms; see ``PROTECTED_PLAN_KEYS``), a protected retirement date the edit blanked is
    put back. Every other caller (blank plan, strategy endpoints, backfill) leaves it off.
    After the block ``PlanEdit.revision`` is the plan's revision.
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


def peek_plan_data(workspace_root: str | Path | None = None) -> SectionedData:
    """The engine view without touching disk: never creates or writes the plan file
    (``{}`` when there is no plan file yet or it is not an initialised plan).

    ``workspace_root`` names another workspace (its ``plan.rpx``); the default is the active plan.
    """
    path = Path(workspace_root) / PLAN_FILE_NAME if workspace_root is not None else active_plan_path()
    if not path.is_file():
        return {}
    try:
        with PlanStore.open(path, create=False) as store:
            return store.sectioned_data()
    except LookupError:  # stores.NotFoundError: not an initialised plan file
        return {}


def peek_plan_data_for_input_dir(input_dir: str | Path) -> SectionedData:
    """The plan view for code that is handed a workspace's ``input`` folder (the YTD readers):
    the active plan when ``input_dir`` is the live workspace's ``input``, else the ``plan.rpx`` of
    the workspace that holds ``input_dir`` (the ``<workspace>/input`` + ``<workspace>/plan.rpx``
    layout ``tests.plan_fixture.make_plan`` builds)."""
    live = platform_runtime.workspace_root() / "input"
    try:
        same = Path(input_dir).resolve() == live.resolve()
    except OSError:
        same = False
    return peek_plan_data() if same else peek_plan_data(Path(input_dir).parent)


def ensure_plan_file(path: str | Path) -> Path:
    """Create an empty, initialised plan file at ``path`` when there is none (never touches an
    existing one)."""
    target = Path(path)
    if not target.is_file():
        PlanStore.open(target).close()
    return target


def plan_file_has_rows(path: str | Path) -> bool:
    """True when ``path`` is an initialised plan file holding at least one row."""
    target = Path(path)
    if not target.is_file():
        return False
    try:
        with PlanStore.open(target, create=False, readonly=True) as store:
            return bool(store.all_rows())
    except LookupError:  # not an initialised plan file
        return False


def build_plan_file_from_csv_folder(dest: str | Path, folder: str | Path) -> int:
    """Build a plan file at ``dest`` from the plan CSV set in ``folder`` through the
    ``csv_exchange`` importer (the demo seed, a fresh frozen workspace); an existing ``dest`` is
    replaced. Rows the old loader dropped at load are dropped too. Returns the rows written."""
    from .csv_exchange import import_plan_csv_set  # noqa: PLC0415 - csv_exchange needs no plan at import

    target = Path(dest)
    for stale in (target, target.with_name(target.name + "-wal"), target.with_name(target.name + "-shm")):
        stale.unlink(missing_ok=True)
    with PlanStore.open(target) as store:
        return import_plan_csv_set(folder, store, drop_never_kept=True).rows


def plan_file_fingerprint(path: str | Path) -> tuple[str, int]:
    """``(revision, row count)`` of a plan file, read-only (the build's input fingerprint)."""
    with PlanStore.open(path, create=False, readonly=True) as store:
        return store.revision(), len(store.all_rows())


def plan_db_env(env: dict[str, Any]) -> dict[str, Any]:
    """Set ``PLAN_DB_ENV`` in a subprocess environment to the active plan file."""
    env[PLAN_DB_ENV] = str(active_plan_path())
    return env
