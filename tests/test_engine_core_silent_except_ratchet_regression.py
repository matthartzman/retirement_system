"""WI-029 / QA-007: no silent broad except in the calculation core.

Every handler in planning_engines.py and src/projection_stages that swallows an
error must name the expected exception types and log the fallback once; a bare
or ``except Exception`` whose body is only ``pass``/``continue`` is a ratchet
failure.
"""
import ast
import logging
from pathlib import Path

import pytest

from src import fallback_log
from src.projection_stages.budget_rollups import category_budget_rollup

ROOT = Path(__file__).resolve().parents[1]
CORE = [ROOT / "src" / "planning_engines.py", *sorted((ROOT / "src" / "projection_stages").glob("*.py"))]


def _is_broad(handler):
    t = handler.type
    return t is None or (isinstance(t, ast.Name) and t.id in ("Exception", "BaseException"))


def _silent_broad_handlers():
    found = []
    for path in CORE:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.ExceptHandler) and _is_broad(node)
                    and all(isinstance(s, (ast.Pass, ast.Continue)) for s in node.body)):
                found.append(f"{path.name}:{node.lineno}")
    return found


def test_no_silent_broad_except_in_engine_core():
    assert _silent_broad_handlers() == []


@pytest.fixture(autouse=True)
def _fresh_log():
    fallback_log.reset_fallback_log()


def test_fallback_is_logged_once_per_site_and_type(caplog):
    with caplog.at_level(logging.WARNING, logger="retirement_system.engine_fallback"):
        for _ in range(3):
            fallback_log.log_fallback("site.a", ValueError("bad"), year=2030)
        fallback_log.log_fallback("site.a", TypeError("other"))
    msgs = [r.getMessage() for r in caplog.records]
    assert len(msgs) == 2
    assert "site.a" in msgs[0] and "year=2030" in msgs[0]


def test_budget_rollup_bad_value_is_logged_not_swallowed(caplog):
    c = {"spending_category_rollup_by_year": {2030: {"groceries": "n/a", "fuel": 100.0}}}
    with caplog.at_level(logging.WARNING, logger="retirement_system.engine_fallback"):
        total = category_budget_rollup(c, 2030, ["groceries", "fuel"], lambda *a: 1.0)
    assert total == pytest.approx(100.0)
    assert any("budget_rollup.category" in r.getMessage() for r in caplog.records)
