"""WP0.2: the plan-fixture helper and the ratchet that keeps tests on it."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests import plan_fixture as pf

TESTS = Path(__file__).resolve().parent
ALLOWED = {"conftest.py", "plan_fixture.py", Path(__file__).name}
# Ceilings may only go down. Remaining direct users: the golden-master suite
# (it derives paths from the fixture dir) and two path-constant readers.
FROZEN_LITERAL_CEILING = 0
DIRECT_CLIENT_DATA_CEILING = 2


def test_make_plan_lays_down_every_fixture_file(tmp_path):
    plan = pf.make_plan(tmp_path)
    src = {f.name for f in pf.fixture_dir().iterdir() if f.is_file()}
    assert {f.name for f in plan.input_dir.iterdir()} == src
    assert plan.input_dir == tmp_path / "input"


def test_make_plan_withhold_and_demo(tmp_path):
    plan = pf.make_plan(tmp_path, "demo", withhold=("client_holdings.csv",))
    assert not (plan.input_dir / "client_holdings.csv").exists()
    assert (plan.input_dir / "client_data.csv").is_file()


def test_make_plan_data_and_config_roundtrip(tmp_path):
    plan = pf.make_plan(tmp_path)
    assert plan.data() == pf.plan_data("sample_frozen")
    assert plan.config()["plan_start"] == pf.plan_config("sample_frozen")["plan_start"]


def test_unknown_fixture_is_a_clear_error(tmp_path):
    with pytest.raises(KeyError, match="unknown plan fixture"):
        pf.make_plan(tmp_path, "nope")


def _scan(pattern):
    rx = re.compile(pattern)
    return sorted(f.name for f in TESTS.glob("*.py")
                  if f.name not in ALLOWED and rx.search(f.read_text(encoding="utf-8")))


def test_tests_name_the_frozen_fixture_only_through_the_helper():
    hits = _scan(r"""["']sample_plan_frozen["']""")
    assert len(hits) <= FROZEN_LITERAL_CEILING, f"use tests.plan_fixture instead: {hits}"


def test_direct_client_data_reads_have_not_grown():
    hits = _scan(r"""TEST_INPUT_DIR / ['"]client_data\.csv['"]""")
    assert len(hits) <= DIRECT_CLIENT_DATA_CEILING, f"use plan_data()/plan_config(): {hits}"
