"""WP3: the committed reference.db is fresh and every getter equals its golden.

- ``src/reference/reference.db`` must equal a fresh ``tools/build_reference_db.py``
  run (rebuild with ``python tools/build_reference_db.py`` after editing
  ``reference_src/`` or a slice builder).
- Each ``tests/fixtures/reference_golden/<name>.json`` (the OLD loader's output,
  captured by ``tools/capture_reference_golden.py``) must be reproduced exactly by
  ``GOLDEN_GETTERS[name]`` reading the committed database.
- While a source still exists in both ``reference_src/`` and ``reference_data/``
  (copied, not yet moved), the two copies must not drift.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.stores import RefData
from src.stores.ref_getters import GOLDEN_GETTERS
from src.stores.ref_access import shipped_reference_path
from tests.reference_golden import assert_getter_matches_golden, golden_names
from tools import build_reference_db as tool

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def shipped():
    with RefData.open(shipped_reference_path(), verify=True) as ref:
        yield ref


def test_committed_reference_db_matches_fresh_build():
    problems = tool.check(shipped_reference_path())
    assert problems == [], "reference.db is stale; run `python tools/build_reference_db.py`:\n" + "\n".join(problems)


def test_every_golden_has_a_getter_and_every_getter_a_golden():
    assert sorted(GOLDEN_GETTERS) == golden_names()


@pytest.mark.parametrize("name", golden_names())
def test_getter_matches_old_loader_golden(shipped, name):
    assert_getter_matches_golden(name, GOLDEN_GETTERS[name](shipped))


def test_sources_not_yet_moved_do_not_drift():
    for src in sorted((ROOT / "reference_src").rglob("*")):
        legacy = ROOT / "reference_data" / src.relative_to(ROOT / "reference_src")
        if src.is_file() and legacy.is_file():
            assert src.read_bytes() == legacy.read_bytes(), f"{src.name} differs between reference_src/ and reference_data/"
