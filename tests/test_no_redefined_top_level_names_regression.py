"""Guard against unreachable shadowed top-level definitions in src/.

Python keeps only the LAST `def`/`class` bound to a given module-scope name;
an earlier same-name definition at column 0 is unreachable dead code that
silently disappears at import time (no SyntaxError, no warning). This bit
src/spending_tracker.py, which accumulated three duplicate copies of
load_mapping_rules and a dozen other functions redefined in place across
edits — hundreds of lines nobody could actually reach.

This module walks every .py file under src/ recursively, parses it with the
ast module, and asserts no file defines the same top-level function or class
name more than once.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _redefined_top_level_names(path: Path):
    """Return [(name, [linenos]), ...] for names bound by 2+ top-level def/class nodes."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    by_name: dict[str, list[int]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            by_name.setdefault(node.name, []).append(node.lineno)
    return [(name, linenos) for name, linenos in by_name.items() if len(linenos) > 1]


def _scan(root: Path):
    offenders = []
    for path in sorted(root.rglob("*.py")):
        for name, linenos in _redefined_top_level_names(path):
            offenders.append((path, name, linenos))
    return offenders


def test_no_module_redefines_a_top_level_name():
    offenders = _scan(SRC)
    assert not offenders, (
        "These modules define the same top-level function/class name more than "
        "once. Python binds only the LAST definition, so every earlier one is "
        "unreachable dead code:\n"
        + "\n".join(
            f"  {path.relative_to(ROOT)}: {name!r} at lines {linenos}"
            for path, name, linenos in offenders
        )
    )


def test_detector_catches_a_planted_double_def():
    """Guard against the scan silently passing because the AST logic stopped working."""
    planted = (
        "def foo():\n"
        "    return 1\n"
        "\n"
        "\n"
        "def foo():\n"
        "    return 2\n"
    )
    tree = ast.parse(planted)
    by_name: dict[str, list[int]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            by_name.setdefault(node.name, []).append(node.lineno)
    dupes = [(name, linenos) for name, linenos in by_name.items() if len(linenos) > 1]
    assert dupes == [("foo", [1, 5])], (
        "The double-def detector did not fire on a planted synthetic redefinition; "
        f"got {dupes!r}"
    )
