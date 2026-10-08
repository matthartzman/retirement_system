"""The active plan file: where the engine, the build and the server read and edit plan rows.

Design F sections 5A and 7. Until the plan registry is wired (WP8.4: ``app.db``
``plan_registry`` / ``active_plan``), a workspace has exactly one plan and its file is
``<workspace>/plan.rpx`` (``PLAN_FILE_NAME``; the same place ``tests/plan_fixture.make_plan``
builds it). ``RETIREMENT_SYSTEM_PLAN_DB`` (``PLAN_DB_ENV``) overrides the path; the server
sets it for the build subprocess so the build reads the same file the server does, together
with ``RETIREMENT_SYSTEM_PLAN_REVISION`` (``PLAN_REVISION_ENV``: the plan's revision when the
build was requested). WP8.4 replaces the body of :func:`active_plan_path` with the registry lookup.

The build reads through :func:`build_read`: one read transaction on the plan file for the whole
computation (WP7.1). While it is open, every reader below that targets that file (the rows, the
flat datasets, the fingerprint) uses it on that thread, so the build sees one consistent state of
the plan; a write the build itself makes (the default HSA schedule) moves the view forward.

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
from typing import Any, Callable, Iterator

from . import platform_runtime
from .roth_ui_build_guard import canonicalize_roth_rows
from .stores import PlanStore, StoreError
# validate_plan_id is re-exported: product code reaches the plan store through this module
from .stores.plan_store import validate_plan_id  # noqa: F401

PLAN_DB_ENV = "RETIREMENT_SYSTEM_PLAN_DB"
PLAN_REVISION_ENV = "RETIREMENT_SYSTEM_PLAN_REVISION"
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


# ------------------------------------------------------------ the build's read (WP7.1)
_PIN = threading.local()  # per thread: an in-process build must not pin the server's readers


def _same_file(a: str | Path, b: str | Path) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return str(a) == str(b)


@dataclass
class BuildRead:
    """The build's view of the plan (see :func:`build_read`): the plan file, its open store,
    the revision read and the revision the build was requested for (``""`` when not given)."""
    path: Path
    store: PlanStore
    revision: str = ""
    requested_revision: str = ""
    initial_revision: str = ""
    _txn: Any = None

    @property
    def stale(self) -> bool:
        """True when the plan changed between the build request and the build's read."""
        seen = self.initial_revision or self.revision
        return bool(self.requested_revision) and self.requested_revision != seen

    def _begin(self) -> None:
        self._txn = self.store.read_transaction()
        self._txn.__enter__()

    def _end(self) -> None:
        txn, self._txn = self._txn, None
        if txn is not None:
            txn.__exit__(None, None, None)

    def refresh(self, while_released: Any = None) -> None:
        """Move the view to the plan's latest committed state (after the build's own write).
        ``while_released`` runs between the old view ending and the new one starting (a WAL
        checkpoint cannot flush past an open reader)."""
        if self._txn is not None:
            self.initial_revision = self.initial_revision or self.revision
            self._end()
            if while_released is not None:
                while_released()
            self._begin()
            self.revision = self.store.revision()

    def release(self) -> None:
        """End the read and unpin it (idempotent): later reads open the plan file again."""
        if getattr(_PIN, "read", None) is self:
            _PIN.read = None
        self._end()
        self.store.close()


def _pinned(path: str | Path) -> PlanStore | None:
    read = getattr(_PIN, "read", None)
    if read is not None and not read.store.closed and _same_file(read.path, path):
        return read.store
    return None


def _refresh_pin(path: str | Path) -> None:
    read = getattr(_PIN, "read", None)
    if read is not None and not read.store.closed and _same_file(read.path, path):
        read.refresh()


@contextmanager
def _reading(path: str | Path, *, create: bool = False, readonly: bool = False) -> Iterator[PlanStore]:
    """The build's pinned store when ``path`` is the plan it reads, else a store opened for the call."""
    store = _pinned(path)
    if store is not None:
        yield store
        return
    with PlanStore.open(path, create=create, readonly=readonly) as opened:
        yield opened


@contextmanager
def _writing(path: str | Path, *, create: bool = True) -> Iterator[PlanStore]:
    """A writable store on ``path``; afterwards a build reading that plan sees the write."""
    try:
        with PlanStore.open(path, create=create) as store:
            yield store
    finally:
        _refresh_pin(path)


@contextmanager
def build_read(path: str | Path | None = None) -> Iterator[BuildRead]:
    """Open the build's one read transaction on the plan file (default: the active plan,
    ``$RETIREMENT_SYSTEM_PLAN_DB``) and pin it for this thread until the block ends or
    :meth:`BuildRead.release`. The plan file is created (empty) and brought to the current
    schema first, as the build's first read always did. ``requested_revision`` is
    ``$RETIREMENT_SYSTEM_PLAN_REVISION``."""
    target = Path(path) if path is not None else active_plan_path()
    PlanStore.open(target).close()  # create when missing, migrate an older schema
    read = BuildRead(target, PlanStore.open(target, create=False, readonly=True),
                     requested_revision=str(os.environ.get(PLAN_REVISION_ENV, "") or "").strip())
    previous = getattr(_PIN, "read", None)
    try:
        read._begin()
        read.revision = read.store.revision()
        _PIN.read = read
        yield read
    finally:
        read.release()
        _PIN.read = previous


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
    try:
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
    finally:
        _refresh_pin(active_plan_path())


def active_plan_data() -> SectionedData:
    """The engine view of the active plan (``PlanStore.sectioned_data()``); ``{}`` for a plan
    with no rows."""
    with _reading(active_plan_path(), create=True) as store:
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
        with _reading(path) as store:
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
        with _reading(target, readonly=True) as store:
            return bool(store.all_rows())
    except LookupError:  # not an initialised plan file
        return False


def build_plan_file_from_csv_folder(dest: str | Path, folder: str | Path) -> int:
    """Build a plan file at ``dest`` from the plan CSV set in ``folder`` through the
    ``csv_exchange`` importer (the demo seed, a fresh frozen workspace); an existing ``dest`` is
    replaced. Rows the old loader dropped at load are dropped too. Returns the rows written."""
    from .csv_exchange import import_flat_datasets, import_plan_csv_set, import_recovery_seed  # noqa: PLC0415 - csv_exchange needs no plan at import

    target = Path(dest)
    for stale in (target, target.with_name(target.name + "-wal"), target.with_name(target.name + "-shm")):
        stale.unlink(missing_ok=True)
    with PlanStore.open(target) as store:
        rows = import_plan_csv_set(folder, store, drop_never_kept=True).rows
        import_flat_datasets(folder, store)
        import_recovery_seed(folder, store)
        return rows


def plan_file_fingerprint(path: str | Path) -> tuple[str, int]:
    """``(revision, row count)`` of a plan file, read-only (the build's input fingerprint)."""
    with _reading(path, readonly=True) as store:
        return store.revision(), len(store.all_rows())


def plan_state(path: str | Path | None = None) -> str:
    """Digest of everything a build reads from the plan file: the plan rows' revision and the
    flat datasets. A build records it with its results; a later difference means the plan changed."""
    import hashlib  # noqa: PLC0415

    target = Path(path) if path is not None else active_plan_path()
    h = hashlib.sha256()
    with _reading(target, readonly=True) as store:
        h.update(store.revision().encode("ascii"))
    for name, digest in sorted(dataset_fingerprint(target).items()):
        h.update(b"\0" + name.encode("utf-8") + b"\0" + digest.encode("ascii"))
    return h.hexdigest()


# ------------------------------------------------------------ build results (WP7.2)
def write_build_results(build_id: str, *, path: str | Path | None = None, plan_state: str | None = None,
                        **parts: dict[str, Any]) -> None:
    """Put parts (``summary=``, ``explorer=``, ``package=``, ``snapshot=``) into the
    ``build_results`` row of ``build_id`` in the plan file; parts not given are kept."""
    with _writing(Path(path) if path is not None else active_plan_path()) as store:
        store.build_results.put(build_id, plan_state=plan_state, **parts)


def read_build_results(build_id: str | None = None, *, path: str | Path | None = None) -> dict[str, Any] | None:
    """The ``build_results`` row of ``build_id`` (the latest build when None) with its parts
    parsed, or None when the plan file has none."""
    target = Path(path) if path is not None else active_plan_path()
    if not target.is_file():
        return None
    try:
        with _reading(target, readonly=True) as store:
            return store.build_results.get(build_id)
    except StoreError:  # no such build, or a file that is not an initialised plan
        return None


def build_part_record(part: str, doc: Any) -> dict[str, Any]:
    """The artifact record of a build-results part (what a file record is for a file)."""
    return PlanStore.build_part_record(part, doc)


def latest_build_stamp(path: str | Path | None = None) -> tuple[str, str] | None:
    """``(build_id, written_at)`` of the latest build's results, or None; changes with every write."""
    target = Path(path) if path is not None else active_plan_path()
    if not target.is_file():
        return None
    try:
        with _reading(target, readonly=True) as store:
            return store.build_results.latest_stamp()
    except StoreError:
        return None


def clear_build_results(path: str | Path | None = None) -> int:
    """Drop every build's results (a new build starts from none)."""
    target = Path(path) if path is not None else active_plan_path()
    if not target.is_file():
        return 0
    try:
        with _writing(target, create=False) as store:
            return store.build_results.clear()
    except StoreError:
        return 0


def plan_db_env(env: dict[str, Any]) -> dict[str, Any]:
    """Set ``PLAN_DB_ENV`` in a subprocess environment to the active plan file and
    ``PLAN_REVISION_ENV`` to its current revision (dropped when the file cannot be read yet)."""
    path = active_plan_path()
    env[PLAN_DB_ENV] = str(path)
    revision = ""
    if path.is_file():
        try:
            with PlanStore.open(path, create=False, readonly=True) as store:
                revision = store.revision()
        except StoreError:  # not initialised, or an older schema the build migrates first
            revision = ""
    if revision:
        env[PLAN_REVISION_ENV] = revision
    else:
        env.pop(PLAN_REVISION_ENV, None)
    return env


# ----------------------------------------------------------------- flat datasets (WP6)
# Holdings, liabilities, HSA schedule and target allocation are tables of the plan file.
# Readers get CSV text (the shape their parsers take) or ``None`` for "no rows".
def _dataset_text(path: Path, name: str) -> str | None:
    from .csv_exchange import dataset_csv_text  # noqa: PLC0415

    if not path.is_file():
        return None
    try:
        with _reading(path) as store:
            repo = store.dataset(name)
            return dataset_csv_text(repo) if repo.count() else None
    except LookupError:  # stores.NotFoundError: not an initialised plan file
        return None


def active_dataset_text(name: str) -> str | None:
    """CSV text of dataset ``name`` in the active plan; ``None`` when there is no plan file or
    the table is empty. Never creates a plan file."""
    return _dataset_text(active_plan_path(), name)


def active_dataset_rows(name: str) -> list[dict[str, str]]:
    """Rows of dataset ``name`` (``"spending_budget_lines"`` ...) in the active plan (``[]`` when
    there is no plan file). Never creates a plan file."""
    return _dataset_rows(active_plan_path(), name)


def dataset_text_for_input_dir(input_dir: str | Path, name: str) -> str | None:
    """For code handed a workspace's ``input`` folder: the active plan when it is the live
    workspace's ``input``, else the ``plan.rpx`` of the workspace that holds it."""
    live = platform_runtime.workspace_root() / "input"
    try:
        same = Path(input_dir).resolve() == live.resolve()
    except OSError:
        same = False
    return active_dataset_text(name) if same else _dataset_text(Path(input_dir).parent / PLAN_FILE_NAME, name)


def write_active_dataset(name: str, text: str) -> int:
    """Replace dataset ``name`` of the active plan from CSV text (creating the plan file when
    there is none); returns the rows written."""
    from .csv_exchange import replace_dataset_from_csv_text  # noqa: PLC0415

    from .csv_exchange.flat_csv import HSA_SCHEDULE_SAVED_KEY  # noqa: PLC0415

    with _writing(active_plan_path()) as store:
        with store.transaction():
            written = replace_dataset_from_csv_text(store.dataset(name), text)
            if name == "hsa_schedule":
                store.set_meta(HSA_SCHEDULE_SAVED_KEY, "1")
        return written


def active_hsa_schedule_saved() -> bool:
    """True once the household's HSA schedule has been saved or seeded (even with zero rows), so
    an empty table means "cleared on purpose", not "never set". False when there is no plan file."""
    from .csv_exchange.flat_csv import HSA_SCHEDULE_SAVED_KEY  # noqa: PLC0415

    path = active_plan_path()
    if not path.is_file():
        return False
    try:
        with _reading(path, readonly=True) as store:
            return store.get_meta(HSA_SCHEDULE_SAVED_KEY) is not None
    except LookupError:  # not an initialised plan file
        return False


def dataset_fingerprint(path: str | Path) -> dict[str, str]:
    """``{file name: sha256 of the dataset's CSV text}`` for the non-empty datasets of a plan
    file (the build's input fingerprint)."""
    import hashlib  # noqa: PLC0415

    from .csv_exchange import FLAT_DATASET_FILES, dataset_csv_text  # noqa: PLC0415

    out: dict[str, str] = {}
    with _reading(path) as store:
        for name, file in FLAT_DATASET_FILES.items():
            repo = store.dataset(name)
            if repo.count():
                out[file] = hashlib.sha256(dataset_csv_text(repo).encode("utf-8")).hexdigest()
    return out


# ------------------------------------------------------------- spending set (WP6.3)
# The spending taxonomy and aliases are tables of the plan file (``store.spending``). The
# spending readers are handed a workspace root (``<root>/input`` was their folder): the live
# workspace means the active plan, any other root means the ``plan.rpx`` in it.
def plan_path_for_workspace(root: str | Path) -> Path:
    """The plan file of workspace ``root``: the active plan for the live workspace, else
    ``<root>/plan.rpx``."""
    try:
        same = Path(root).resolve() == platform_runtime.workspace_root().resolve()
    except OSError:
        same = False
    return active_plan_path() if same else Path(root) / PLAN_FILE_NAME


def _dataset_rows(path: Path, name: str) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with _reading(path) as store:
            return store.dataset(name).rows()
    except LookupError:  # stores.NotFoundError: not an initialised plan file
        return []


def workspace_dataset_rows(root: str | Path, name: str) -> list[dict[str, str]]:
    """Rows of dataset ``name`` (``"spending_taxonomy"`` ...) in the plan of workspace ``root``
    (``[]`` when there is no plan file). Never creates a plan file."""
    return _dataset_rows(plan_path_for_workspace(root), name)


def dataset_rows_for_input_dir(input_dir: str | Path, name: str) -> list[dict[str, str]]:
    """:func:`workspace_dataset_rows` for code handed a workspace's ``input`` folder."""
    return workspace_dataset_rows(Path(input_dir).parent, name)


def write_workspace_dataset_rows(root: str | Path, name: str, rows: list[dict[str, Any]]) -> int:
    """Replace dataset ``name`` in the plan of workspace ``root`` (created when missing) with
    ``rows`` (text values; ``None`` is stored empty). Returns the rows written."""
    with _writing(plan_path_for_workspace(root)) as store:
        return store.dataset(name).replace_all(rows)


def write_dataset_rows_for_input_dir(input_dir: str | Path, name: str, rows: list[dict[str, Any]]) -> int:
    """:func:`write_workspace_dataset_rows` for code handed a workspace's ``input`` folder."""
    return write_workspace_dataset_rows(Path(input_dir).parent, name, rows)


def append_dataset_row_for_input_dir(input_dir: str | Path, name: str, row: dict[str, Any]) -> int:
    """Append one row to dataset ``name`` of the plan behind a workspace's ``input`` folder (the
    plan is created when missing); read and write are one transaction. Returns the row count."""
    with _writing(plan_path_for_workspace(Path(input_dir).parent)) as store:
        repo = store.dataset(name)
        with store.transaction():
            rows = repo.rows()
            rows.append(row)
            return repo.replace_all(rows)


def transform_dataset_rows_for_input_dir(
    input_dir: str | Path, name: str, fn: Callable[[list[dict[str, str]]], list[dict[str, Any]]]
) -> int:
    """Replace dataset ``name`` of the plan behind a workspace's ``input`` folder with
    ``fn(current rows)`` (the plan is created when missing). The read and the write are one
    transaction, so a concurrent writer (another process on the same plan file) cannot be lost.
    Returns the row count written."""
    with _writing(plan_path_for_workspace(Path(input_dir).parent)) as store:
        repo = store.dataset(name)
        with store.transaction():
            return repo.replace_all(fn(repo.rows()))


# ------------------------------------------------- spending recovery copies (WP6.3c)
# A zeroed budget is recoverable from two plan revisions of the plan file: ``budget-recovery-seed``
# (a known-good budget) and ``pre-recovery`` (the budget as it was before a recovery merge); each
# retains the ``spending_budget`` rows beside its plan-rows copy (``PlanStore.snapshot_revision``).
def workspace_recovery_seed_rows(root: str | Path) -> list[dict[str, str]]:
    """The recovery seed budget rows of the plan of workspace ``root`` (``[]`` when there is
    none or no plan file). Never creates a plan file."""
    path = plan_path_for_workspace(root)
    if not path.is_file():
        return []
    try:
        with _reading(path) as store:
            return store.spending.recovery_seed()
    except LookupError:  # not an initialised plan file
        return []


def write_workspace_recovery_seed(root: str | Path, rows: list[dict[str, Any]]) -> int:
    """Make ``rows`` the recovery seed of the plan of workspace ``root`` (replacing the previous
    seed). Returns the rows kept."""
    with _writing(plan_path_for_workspace(root)) as store:
        return store.spending.set_recovery_seed(rows)


def keep_workspace_pre_recovery_copy(root: str | Path, rows: list[dict[str, Any]]) -> bool:
    """Keep ``rows`` (the budget before a recovery merge) as the plan's one-time ``pre-recovery``
    revision; False when one exists already or ``rows`` is empty."""
    with _writing(plan_path_for_workspace(root)) as store:
        return store.spending.keep_pre_recovery_copy(rows)


def restore_workspace_pre_recovery_copy(root: str | Path) -> int:
    """Put the budget back to its ``pre-recovery`` copy; returns the rows restored (0 when there
    is no copy)."""
    path = plan_path_for_workspace(root)
    if not path.is_file():
        return 0
    with _writing(path, create=False) as store:
        return store.spending.restore_pre_recovery_copy()
