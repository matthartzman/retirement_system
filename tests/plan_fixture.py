"""Single entry point for tests that need a plan (WP0.2).

Today a plan is a folder of CSVs: ``tests/fixtures/sample_plan_frozen/`` (or
``input/demo/``) copied into a workspace. Later file-elimination phases change
how a plan is laid down and read; they should change only the internals of this
module, not the ~150 tests that call it.

API
---
``make_plan(tmp_path, fixture="sample_frozen")``
    Lay a fixture plan down in ``tmp_path/input`` and return a ``PlanWorkspace``
    (``.root``, ``.input_dir``, ``.data()``, ``.config()``).
``plan_data(fixture=None)``
    Sectioned ``client_data`` rows (``load_csv`` shape) of the session plan.
``plan_config(...)``
    Engine-ready config (``parse_client``) of the session plan.
``fixture_dir(fixture)``
    Source folder of a named fixture, for the few tests that must read a
    committed file directly.

``fixture=None`` means the shared session workspace that ``tests/conftest.py``
seeds from the frozen sample plan (``TEST_INPUT_DIR``).
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


def plan_config(fixture: str | None = None, **parse_kwargs):
    """Engine-ready config via ``parse_client`` (the shape most tests want)."""
    from src.data_io import parse_client
    return parse_client(plan_data(fixture), "", **parse_kwargs)


@dataclass(frozen=True)
class PlanWorkspace:
    root: Path
    input_dir: Path
    fixture: str

    def data(self):
        from src.data_io import load_csv
        return load_csv(self.input_dir / "client_data.csv")

    def config(self, **parse_kwargs):
        from src.data_io import parse_client
        return parse_client(self.data(), "", **parse_kwargs)


def make_plan(tmp_path, fixture: str = DEFAULT_FIXTURE, *, input_subdir: str = "input",
              withhold=()) -> PlanWorkspace:
    """Copy a fixture plan into ``tmp_path/<input_subdir>`` (fresh, writable).

    ``withhold`` names fixture files to leave out (missing-file scenarios)."""
    root = Path(tmp_path)
    input_dir = root / input_subdir
    input_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(fixture_dir(fixture).iterdir()):
        if f.is_file() and f.name not in withhold:
            shutil.copy(f, input_dir / f.name)
    return PlanWorkspace(root=root, input_dir=input_dir, fixture=fixture)
