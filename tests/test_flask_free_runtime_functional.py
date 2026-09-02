from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PACKAGES = {"flask", "werkzeug", "jinja2", "markupsafe", "click", "itsdangerous", "waitress"}


def test_runtime_requirements_do_not_include_flask_family():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for name in FORBIDDEN_PACKAGES:
        assert name not in text


def test_pyinstaller_spec_does_not_collect_flask_family():
    text = (ROOT / "retirement_planner.spec").read_text(encoding="utf-8").lower()
    for name in FORBIDDEN_PACKAGES:
        assert f'"{name}"' not in text
        assert f"'{name}'" not in text


def test_server_source_does_not_import_external_flask_or_werkzeug():
    offenders = []
    for path in (ROOT / "src").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in {"flask", "werkzeug"}:
                        offenders.append(f"{path.relative_to(ROOT)} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".", 1)[0]
                if root in {"flask", "werkzeug"}:
                    offenders.append(f"{path.relative_to(ROOT)} imports from {node.module}")
    assert offenders == []


def test_stdlib_route_registry_import_and_smoke_requests():
    from src.server import create_app

    app = create_app()
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/ping" in rules
    assert "/api/runtime" in rules
    assert "/api/config/rows" in rules

    client = app.test_client()
    ping = client.get("/api/ping", headers={"X-User-Role": "admin"})
    assert ping.status_code == 200
    assert ping.get_json()["success"] is True

    runtime = client.get("/api/runtime", headers={"X-User-Role": "admin"})
    assert runtime.status_code == 200
    assert runtime.get_json()["version"]
