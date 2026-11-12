"""Import direction: domain modules must not import the server layers (ARC-002 / W2-07).

``src/server`` (HTTP routes) and ``src/server_services`` (request-shaped services) sit above the
domain. A domain module that imports them inverts the layering and drags the HTTP stack into the
engine. Only the desktop adapter (``desktop_api.py``) may reach up, and ``src`` must not import the
separate ``financial_trends_reporter`` app at all.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
UPPER_LAYERS = ("server", "server_services", "http_runtime")
ALLOWED_ADAPTERS = {"desktop_api.py"}
FORBIDDEN_APPS = ("financial_trends_reporter",)


def inversions(source: str) -> list[str]:
    """Imported module names in ``source`` that point at an upper layer or a separate app."""
    bad: list[str] = []
    for node in ast.walk(ast.parse(source)):
        names: list[str] = []
        if isinstance(node, ast.ImportFrom):
            base = node.module or ""
            names = [base] + [f"{base}.{a.name}" if base else a.name for a in node.names]
        elif isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        for name in names:
            parts = [p for p in name.split(".") if p]
            if parts[:1] == ["src"]:
                parts = parts[1:]
            if parts and (parts[0] in UPPER_LAYERS or parts[0] in FORBIDDEN_APPS):
                bad.append(name)
    return bad


def test_checker_flags_a_planted_inversion():
    assert inversions("from ..server_services import plan_tier_service")
    assert inversions("from ...server_services.plan_tier_service import entered_rows")
    assert inversions("import src.server.app_core")
    assert inversions("from financial_trends_reporter.live_snapshot import classify_symbol")
    assert not inversions("from . import module_catalog\nfrom .housing.pricing import estimate_housing_cost")


def test_no_domain_module_imports_the_server_layers():
    offenders: dict[str, list[str]] = {}
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel.split("/")[0] in UPPER_LAYERS or rel in ALLOWED_ADAPTERS:
            continue
        found = inversions(path.read_text(encoding="utf-8"))
        if found:
            offenders[rel] = sorted(set(found))
    assert not offenders, f"domain modules import upward (move the shared rule into the domain): {offenders}"
