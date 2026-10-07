"""Single entry point for tests that need a plan (WP0.2; plan file since WP4.1).

A plan is laid down as the fixture's CSV folder (``tests/fixtures/sample_plan_frozen/`` or
``input/demo/``) copied into a workspace **and** a plan file (``plan.db``, the ``.rpx``)
built from those CSVs by the ``csv_exchange`` importer. Later file-elimination phases
change how a plan is laid down and read; they should change only the internals of this
module, not the ~150 tests that call it.

API
---
``make_plan(tmp_path, fixture="sample_frozen")``
    Lay a fixture plan down in ``tmp_path/input``, build ``tmp_path/plan.rpx`` from it and
    return a ``PlanWorkspace`` (``.root``, ``.input_dir``, ``.plan_db``, ``.data()``,
    ``.store_data()``, ``.store()``, ``.config()``).
``plan_data(fixture=None)``
    Sectioned ``client_data`` rows (``load_csv`` shape) of the session plan.
``plan_config(...)``
    Engine-ready config (``parse_client``) of the session plan.
``fixture_dir(fixture)``
    Source folder of a named fixture, for the few tests that must read a
    committed file directly.
``plain(config)``
    A ``parse_client`` result with objects turned into their attributes, so two
    configs compare by value.

``fixture=None`` means the shared session workspace that ``tests/conftest.py``
seeds from the frozen sample plan (``TEST_INPUT_DIR``).

Invariant for WP4.2 (``tests/test_plan_rows_fixture_equivalence_regression.py``):
``ws.store_data()`` (read from ``plan.rpx``) equals ``ws.data()`` (``load_csv`` over the
CSVs), key order included, for every fixture.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = {
    "sample_frozen": ROOT / "tests" / "fixtures" / "sample_plan_frozen",
    "demo": ROOT / "input" / "demo",
}
DEFAULT_FIXTURE = "sample_frozen"
PLAN_FILE_NAME = "plan.rpx"


def fixture_dir(fixture: str = DEFAULT_FIXTURE) -> Path:
    try:
        return FIXTURES[fixture]
    except KeyError:
        raise KeyError(f"unknown plan fixture {fixture!r}; known: {sorted(FIXTURES)}") from None


def _session_input_dir() -> Path:
    from conftest import TEST_INPUT_DIR
    return TEST_INPUT_DIR


def _input_dir_for(fixture: str | None) -> Path:
    return _session_input_dir() if fixture is None else fixture_dir(fixture)


def plan_data(fixture: str | None = None):
    """Sectioned client_data rows, as ``load_csv`` returns them."""
    from src.data_io import load_csv
    return load_csv(_input_dir_for(fixture) / "client_data.csv")


def plain(obj, seen=None):
    """A parsed config (or any part of it) with objects (tax lots, the lot engine) turned into
    their attributes, so two ``parse_client`` results compare by value, not by object id."""
    seen = set() if seen is None else seen
    if isinstance(obj, dict):
        return {k: plain(v, seen) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        items = [plain(v, seen) for v in obj]
        return sorted(items, key=repr) if isinstance(obj, (set, frozenset)) else items
    if isinstance(obj, float) and obj != obj:
        return "nan"
    slots = [s for cls in type(obj).__mro__ for s in getattr(cls, "__slots__", ())]
    if (hasattr(obj, "__dict__") or slots) and not isinstance(obj, type):
        if id(obj) in seen:
            return f"<cycle {type(obj).__name__}>"
        seen.add(id(obj))
        attrs = dict(getattr(obj, "__dict__", {}))
        attrs.update({s: getattr(obj, s, None) for s in slots})
        return (type(obj).__name__, plain(attrs, seen))
    return obj


def plan_config(fixture: str | None = None, **parse_kwargs):
    """Engine-ready config via ``parse_client`` (the shape most tests want)."""
    from src.data_io import parse_client
    return parse_client(plan_data(fixture), "", **parse_kwargs)


@dataclass(frozen=True)
class PlanWorkspace:
    root: Path
    input_dir: Path
    fixture: str

    @property
    def plan_db(self) -> Path:
        """The workspace's plan file, built from the fixture CSVs by ``make_plan``."""
        return self.root / PLAN_FILE_NAME

    def store(self, *, readonly: bool = False):
        """Open the plan file (``PlanStore``; use as a context manager or ``close()`` it)."""
        from src.stores import PlanStore
        return PlanStore.open(self.plan_db, create=False, readonly=readonly)

    def data(self):
        from src.data_io import load_csv
        return load_csv(self.input_dir / "client_data.csv")

    def store_data(self):
        """``data()``'s plan-file twin: the sectioned view of ``plan_rows``."""
        with self.store(readonly=True) as store:
            return store.sectioned_data()

    def config(self, **parse_kwargs):
        from src.data_io import parse_client
        return parse_client(self.data(), "", **parse_kwargs)


def _build_plan_file(input_dir: Path, plan_db: Path) -> None:
    from src.csv_exchange import import_flat_datasets, import_plan_csv_set
    from src.stores import PlanStore
    for stale in (plan_db, plan_db.with_name(plan_db.name + "-wal"), plan_db.with_name(plan_db.name + "-shm")):
        stale.unlink(missing_ok=True)
    with PlanStore.open(plan_db) as store:
        import_plan_csv_set(input_dir, store)
        import_flat_datasets(input_dir, store)


def make_plan(tmp_path, fixture: str = DEFAULT_FIXTURE, *, input_subdir: str = "input",
              withhold=()) -> PlanWorkspace:
    """Copy a fixture plan into ``tmp_path/<input_subdir>`` (fresh, writable) and build
    ``tmp_path/plan.rpx`` from the copied CSVs.

    ``withhold`` names fixture files to leave out (missing-file scenarios)."""
    root = Path(tmp_path)
    input_dir = root / input_subdir
    input_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(fixture_dir(fixture).iterdir()):
        if f.is_file() and f.name not in withhold:
            shutil.copy(f, input_dir / f.name)
    plan = PlanWorkspace(root=root, input_dir=input_dir, fixture=fixture)
    _build_plan_file(input_dir, plan.plan_db)
    return plan


def stage_plan_csv(tmp_path, files: dict[str, str], *, input_subdir: str = "plan_input") -> Path:
    """A small hand-written plan for readers that take a workspace's ``input`` folder (the YTD
    and spending readers): the given plan CSV files (``{"client_spending.csv": text, ...}``) are
    written to ``tmp_path/<input_subdir>`` and imported into ``tmp_path/plan.rpx``. Returns the
    input folder, which is what those readers are handed. It is not named ``input`` by default,
    so the taxonomy-scoped blend stays off (unit-test fixtures, like the old flat tmp folder)."""
    input_dir = Path(tmp_path) / input_subdir
    input_dir.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (input_dir / name).write_text(text, encoding="utf-8")
    _build_plan_file(input_dir, Path(tmp_path) / PLAN_FILE_NAME)
    return input_dir
