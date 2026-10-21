"""WI-037: kernel and stage modules must not import planning_engines (circular dependency)."""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def _imports_planning_engines(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[-1] == "planning_engines":
                return True
            if any(a.name == "planning_engines" for a in node.names):
                return True
        elif isinstance(node, ast.Import):
            if any(a.name.split(".")[-1] == "planning_engines" for a in node.names):
                return True
    return False


def test_stage_modules_do_not_import_planning_engines():
    offenders = [p.name for p in (SRC / "projection_stages").glob("*.py") if _imports_planning_engines(p)]
    assert offenders == []


def test_engine_kernels_do_not_import_planning_engines_or_stages():
    p = SRC / "engine_kernels.py"
    assert not _imports_planning_engines(p)
    assert "projection_stages" not in p.read_text(encoding="utf-8").replace("`projection_stages`", "").replace("(or ``projection_stages``)", "")
