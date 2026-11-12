"""No wildcard imports in src/ (system review 2026-11-10, W1-02 / ARC-001).

A wildcard import hides the real dependency surface and lets a later import
silently shadow an earlier definition. Import the names you use explicitly.
"""
from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def test_src_has_no_wildcard_imports():
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
                offenders.append(f"{path.relative_to(SRC.parent)}:{node.lineno}")
    assert not offenders, "wildcard imports found: " + ", ".join(offenders)


def test_core_declares_an_explicit_public_surface():
    from src import core

    assert isinstance(core.__all__, list) and core.__all__
    missing = [name for name in core.__all__ if not hasattr(core, name)]
    assert not missing, f"core.__all__ names that do not exist: {missing}"
