"""WI-205 / ARC-007 static regression tests (no PyInstaller run needed)."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src import platform_runtime

ROOT = Path(__file__).resolve().parents[1]
SPEC = (ROOT / "retirement_planner.spec").read_text(encoding="utf-8")
DROPPED = ("matplotlib", "reportlab", "PIL", "cryptography")


def _spec_ast() -> ast.Module:
    return ast.parse(SPEC)


def _string_literals(tree: ast.AST) -> list[str]:
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def test_spec_bundles_only_demo_input_folder():
    tree = _spec_ast()
    pairs = [
        (n.elts[0].value, n.elts[1].value)
        for n in ast.walk(tree)
        if isinstance(n, ast.Tuple) and len(n.elts) == 2
        and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in n.elts)
    ]
    input_pairs = [p for p in pairs if p[0] == "input" or p[0].startswith("input/")]
    assert input_pairs == [("input/demo", "input/demo")]


def test_spec_no_longer_collects_or_hides_unused_packages():
    tree = _spec_ast()
    collected = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple):
            collected |= {e.value for e in node.iter.elts if isinstance(e, ast.Constant)}
    assert {"numpy", "scipy", "lxml", "openpyxl"} <= collected
    for pkg in DROPPED:
        assert pkg not in collected
    excludes = next(k for n in ast.walk(tree) if isinstance(n, ast.Call)
                    for k in n.keywords if k.arg == "excludes")
    allowed = set(_string_literals(excludes.value))
    for pkg in DROPPED:
        assert pkg in allowed
    for lit in _string_literals(tree):
        if lit.split(".")[0] in DROPPED:
            assert lit in allowed, lit  # only ever mentioned inside excludes=


def test_spec_hidden_imports_name_only_existing_modules():
    for lit in _string_literals(_spec_ast()):
        if lit.startswith("src."):
            mod = ROOT / Path(*lit.split("."))
            assert mod.with_suffix(".py").exists() or (mod / "__init__.py").exists(), lit


def test_dropped_packages_are_not_imported_anywhere_in_project_code():
    """Import scan backing the removal from the spec and requirements."""
    files = [ROOT / "main.py", ROOT / "build.py"]
    for d in ("src", "tools", "financial_trends_reporter", "Monarch Extractor", "launchers"):
        files += list((ROOT / d).rglob("*.py"))
    offenders = []
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        for n in ast.walk(tree):
            names = []
            if isinstance(n, ast.Import):
                names = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
                names = [n.module]
            elif isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in DROPPED:
                names = [n.value]  # importlib/__import__ style string
            if any(x.split(".")[0] in DROPPED for x in names):
                offenders.append(f"{f.relative_to(ROOT).as_posix()}:{getattr(n, 'lineno', 0)}")
    # tools/generate_system_diagram.py names "PIL" in an import->dist map only.
    offenders = [o for o in offenders if not o.startswith("tools/generate_system_diagram.py")]
    assert offenders == []


@pytest.mark.parametrize("fname", ["requirements.txt", "pyproject.toml"])
def test_manifests_do_not_list_dropped_packages(fname):
    text = (ROOT / fname).read_text(encoding="utf-8").lower()
    for pkg in ("matplotlib", "pillow", "cryptography", "reportlab"):
        assert pkg not in text


def test_frozen_workspace_root_is_per_user_not_bundle(monkeypatch, tmp_path):
    monkeypatch.delenv(platform_runtime.WORKSPACE_ROOT_ENV, raising=False)
    monkeypatch.setattr(platform_runtime.sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert platform_runtime.workspace_root() == tmp_path / "RetirementPlanner"
    assert platform_runtime.workspace_root() != platform_runtime.package_root()
    # explicit override still wins
    monkeypatch.setenv(platform_runtime.WORKSPACE_ROOT_ENV, str(tmp_path / "x"))
    assert platform_runtime.workspace_root() == tmp_path / "x"


def test_workspace_root_from_source_is_unchanged(monkeypatch):
    monkeypatch.delenv(platform_runtime.WORKSPACE_ROOT_ENV, raising=False)
    monkeypatch.setattr(platform_runtime.sys, "frozen", False, raising=False)
    assert platform_runtime.workspace_root() == platform_runtime.package_root()
    assert platform_runtime.seed_frozen_workspace() is False


def test_frozen_seed_copies_demo_once_and_never_overwrites(monkeypatch, tmp_path):
    pkg = tmp_path / "bundle"
    (pkg / "input" / "demo").mkdir(parents=True)
    (pkg / "input" / "demo" / "client_data.csv").write_text("demo", encoding="utf-8")
    monkeypatch.setattr(platform_runtime, "package_root", lambda: pkg)
    monkeypatch.delenv(platform_runtime.WORKSPACE_ROOT_ENV, raising=False)
    monkeypatch.setattr(platform_runtime.sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    ws = tmp_path / "appdata" / "RetirementPlanner"
    assert platform_runtime.seed_frozen_workspace() is True
    assert (ws / "input" / "client_data.csv").read_text(encoding="utf-8") == "demo"
    (ws / "input" / "client_data.csv").write_text("user edit", encoding="utf-8")
    assert platform_runtime.seed_frozen_workspace() is False
    assert (ws / "input" / "client_data.csv").read_text(encoding="utf-8") == "user edit"
