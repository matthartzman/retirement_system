"""Read access to the flat datasets of a plan (WP6): holdings, liabilities, HSA schedule,
target allocation. Readers get CSV text (the shape the parsers already take) or ``None`` when
the plan has no rows for the dataset, which every reader treats as "no file"."""
from __future__ import annotations

from pathlib import Path

from . import platform_runtime
from .active_plan import PLAN_FILE_NAME, active_plan_path
from .csv_exchange import FLAT_DATASET_FILES, dataset_csv_text, replace_dataset_from_csv_text
from .stores import PlanStore


def _dataset_text(path: Path, name: str) -> str | None:
    if not path.is_file():
        return None
    try:
        with PlanStore.open(path, create=False) as store:
            repo = getattr(store, name)
            return dataset_csv_text(repo) if repo.count() else None
    except LookupError:  # stores.NotFoundError: not an initialised plan file
        return None


def active_dataset_text(name: str) -> str | None:
    """CSV text of dataset ``name`` in the active plan; ``None`` when there is no plan file or
    the table is empty. Never creates a plan file."""
    return _dataset_text(active_plan_path(), name)


def dataset_text_for_input_dir(input_dir: str | Path, name: str) -> str | None:
    """For code handed a workspace's ``input`` folder: the active plan when it is the live
    workspace's ``input``, else the ``plan.rpx`` of the workspace that holds it (the layout
    ``tests.plan_fixture.make_plan`` builds)."""
    live = platform_runtime.workspace_root() / "input"
    try:
        same = Path(input_dir).resolve() == live.resolve()
    except OSError:
        same = False
    return active_dataset_text(name) if same else _dataset_text(Path(input_dir).parent / PLAN_FILE_NAME, name)


# Legacy file name -> dataset name (``client_holdings.csv`` -> ``holdings``).
DATASET_BY_FILE: dict[str, str] = {file: name for name, file in FLAT_DATASET_FILES.items()}


def write_active_dataset(name: str, text: str) -> int:
    """Replace dataset ``name`` of the active plan from CSV text (creating the plan file when
    there is none); returns the rows written."""
    from .active_plan import active_plan_store  # noqa: PLC0415

    with active_plan_store() as store:
        return replace_dataset_from_csv_text(getattr(store, name), text)


def dataset_fingerprint(path: str | Path) -> dict[str, str]:
    """``{file name: sha256 of the dataset's CSV text}`` for the non-empty datasets of a plan file
    (read-only; the build's input fingerprint)."""
    import hashlib  # noqa: PLC0415

    out: dict[str, str] = {}
    with PlanStore.open(path, create=False) as store:
        for name, file in FLAT_DATASET_FILES.items():
            repo = getattr(store, name)
            if repo.count():
                out[file] = hashlib.sha256(dataset_csv_text(repo).encode("utf-8")).hexdigest()
    return out
