"""Every permission a route requires must exist in the vocabulary.

Motivation (system review 2026-08-04, architect finding
`plan-forms-api-permanently-403`): POST /api/plan/forms and
PATCH /api/plan/forms/<section_path> both called ``_require("edit_config")``,
but LOCAL_PERMISSIONS has no such member. ``permissions.require()`` raises
PermissionError for any unlisted permission and app_core converts that to a
403, so the DB-first Plan Forms write API -- named in
documentation/DB_CANONICAL_MIGRATION_PLAN.md as the Phase 2/3 target shape for
all writes -- could never succeed. It went unnoticed because the only test
touching it asserted the route string appears in the route manifest, never
that it responds.

A typo in any future ``_require("...")`` would fail exactly the same way: at
runtime, as a 403, with nothing failing at import or in CI. This test walks the
AST of every server module and fails on any literal that is not a real
permission, which turns that class of bug into a red test instead of a
silently dead endpoint.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.permissions import LOCAL_PERMISSIONS

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "src" / "server"

# Helpers that take a permission name as their first positional argument.
PERMISSION_CALLERS = {"_require", "require", "can"}


def _permission_literals(path: Path) -> list[tuple[str, int]]:
    """Return (permission, lineno) for each literal permission argument."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name not in PERMISSION_CALLERS:
            continue
        first = node.args[0]
        # Non-literal (a variable or f-string) is out of scope: this test
        # deliberately checks only what it can resolve statically.
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            found.append((first.value, first.lineno))
    return found


def _server_modules() -> list[Path]:
    return sorted(SERVER_DIR.glob("*.py"))


def test_server_modules_exist():
    assert _server_modules(), f"no server modules found under {SERVER_DIR}"


@pytest.mark.parametrize("module", _server_modules(), ids=lambda p: p.name)
def test_every_required_permission_is_defined(module: Path):
    unknown = [
        (perm, lineno)
        for perm, lineno in _permission_literals(module)
        if perm not in LOCAL_PERMISSIONS
    ]
    assert not unknown, (
        f"{module.relative_to(ROOT)} requires permissions that do not exist in "
        f"permissions.LOCAL_PERMISSIONS, so every request to those routes 403s:\n"
        + "\n".join(f"  line {lineno}: {perm!r}" for perm, lineno in unknown)
        + f"\nValid permissions: {sorted(LOCAL_PERMISSIONS)}"
    )


def test_the_plan_forms_write_routes_are_reachable():
    """Regression guard for the specific routes that were dead.

    Asserts the permission they gate on is real -- i.e. that the bug above
    cannot silently return, even if someone reintroduces a bespoke name.
    """
    routes = SERVER_DIR / "workbook_routes.py"
    perms = dict((p, n) for p, n in _permission_literals(routes))
    assert "write_config" in perms, (
        "workbook_routes.py no longer requires write_config anywhere; the Plan "
        "Forms write endpoints are expected to gate on it."
    )
    assert "edit_config" not in perms, (
        "edit_config is back in workbook_routes.py. It is not a member of "
        "LOCAL_PERMISSIONS, so any route requiring it returns 403 unconditionally."
    )
